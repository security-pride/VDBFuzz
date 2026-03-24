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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-2]_1752744109_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-2]_1752744109.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId12810021752744109Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-2]_1752744109.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-2]_1752744109.json"
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
    'RequestId': '773a32c3-62ef-11f0-b8cc-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_47_549259LwfZBbPh',
    'dimension': 128,
    'primaryField': 'id',
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
    'RequestId': '775b79c4-62ef-11f0-898e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_47_549259LwfZBbPh',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Bonnie Hutchinson',
    'address': '4083 Anderson Valleys Apt. 553\nHubbardton, PW 20225',
    'text': 'Food her let serve. A short home option mention whom war. Leader who reality else.',
    'email': 'nichole51@example.com',
    'phone_number': '+1-512-779-3000x66569',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Webb',
    'Mallory Riggs',
    'Melissa Washington',
],
    'json': {
    'name': 'Logan Daugherty',
    'address': '034 Vanessa Common\nEast Katrina, GA 23574',
},
    'key13321': 'value81269',
    'key70031': 'value2835',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'John Vincent',
    'address': '65769 Wilson Burg Suite 813\nEast Andrewview, KS 58432',
    'text': 'Prevent rule instead result guess. Born think company who.\nUsually manage sit today action. Sport subject add indicate anyone finally. Ball member project support eat moment.',
    'email': 'jordanmorrow@example.com',
    'phone_number': '8935143625',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Herbert Hatfield',
    'Darryl Rogers',
    'Jordan Murphy',
    'Abigail Rivera',
],
    'json': {
    'name': 'Dave Webster',
    'address': '9491 Margaret Shores\nNew Kevinfort, GA 43873',
},
    'key91995': 'value55141',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jimmy Lopez',
    'address': '26947 Maria Vista Apt. 296\nGinaton, IN 51680',
    'text': 'From situation keep. Suggest born station story. Direction unit tough radio.\nHope plan arrive culture western such season large. Exactly information even believe west. Red billion give big above now.',
    'email': 'stewartmatthew@example.com',
    'phone_number': '+1-225-742-9549x7804',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Kelly',
    'Jessica Howe',
    'Michael Jones',
    'Alicia Ingram',
    'David Jimenez',
    'Matthew Mendoza',
],
    'json': {
    'name': 'John Bishop',
    'address': '63891 Fischer Pines\nLake Andrea, FL 73525',
},
    'key20721': 'value68559',
    'key81700': 'value43894',
    'key92144': 'value76296',
    'key55251': 'value4824',
    'key90848': 'value36797',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'David Flores',
    'address': 'USCGC Molina\nFPO AA 04112',
    'text': 'Attack huge summer ball mother. Main head whose forget. Social affect election around professor cost.\nDo bag total onto believe thousand. Whom body career part service out weight.',
    'email': 'bbaldwin@example.net',
    'phone_number': '856.274.5018x0411',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Patty Thomas',
    'Isaac King MD',
    'Jennifer Greene',
    'Alan Lee',
    'Adam Jackson',
    'Spencer Parks',
],
    'json': {
    'name': 'Eric Santana',
    'address': '8934 Merritt Squares\nCameronborough, VI 98387',
},
    'key61035': 'value29924',
    'key15517': 'value60911',
    'key14070': 'value22854',
    'key89214': 'value22464',
    'key55401': 'value30093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Courtney Fowler',
    'address': '17902 Garza Viaduct Suite 861\nSouth Michael, UT 39408',
    'text': 'Anyone receive suffer girl itself sometimes. Local agreement arm my tend reduce Congress condition.\nGas help focus establish. His end message believe security fill effort.',
    'email': 'laurathomas@example.org',
    'phone_number': '(884)576-6257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angel Jones',
    'Sarah Powell',
    'Sharon Hobbs',
],
    'json': {
    'name': 'Bradley Fernandez',
    'address': '2013 Kelly Forge Suite 736\nAmandashire, TX 07664',
},
    'key66201': 'value29096',
    'key4156': 'value95028',
    'key73333': 'value80797',
    'key58447': 'value72573',
    'key73128': 'value21943',
    'key90210': 'value49222',
    'key97866': 'value63904',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Bryan Mccormick',
    'address': '19073 Estrada Inlet Apt. 164\nLake Michaelfort, MA 83327',
    'text': 'Identify contain five debate arm. Economic executive family.\nRich capital sing receive option still onto until. Future own leave person according.\nWriter PM even moment economic class long.',
    'email': 'qmartin@example.org',
    'phone_number': '(757)699-0566x5013',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Hernandez',
    'James Garcia',
    'Mitchell Brown',
    'Mr. Christopher Peterson MD',
],
    'json': {
    'name': 'Roger Olson',
    'address': '1089 Carpenter Court\nNorth Kathryn, PA 03990',
},
    'key74608': 'value19589',
    'key38369': 'value40074',
    'key36165': 'value49258',
    'key75108': 'value17632',
    'key44738': 'value23038',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Wendy Martinez',
    'address': '5398 Stephanie Port Suite 624\nSouth Roberthaven, AL 94279',
    'text': 'Possible morning figure attorney. Look himself most under course past many. Recognize place money run ball.\nThe spend technology watch tough take computer. Institution foot weight western.',
    'email': 'hallann@example.org',
    'phone_number': '656-691-2027x208',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Donald Moran',
    'Nicholas Wall',
    'Christopher Green',
    'Debra Butler',
],
    'json': {
    'name': 'Steven Clayton',
    'address': 'PSC 5583, Box 0340\nAPO AA 59164',
},
    'key50804': 'value79854',
    'key19575': 'value87236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Cynthia Hawkins',
    'address': '894 Quinn Village Suite 211\nRobertport, WY 32626',
    'text': 'Plan economic opportunity. Middle reveal my great moment rock.\nAnother certain vote poor decision top likely. Write Mr imagine article often onto fly.',
    'email': 'jdoyle@example.net',
    'phone_number': '896-624-4239x49525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Ho',
    'Chris Cole',
    'Danielle Fox',
    'Walter Gates',
    'Michael Rivas',
],
    'json': {
    'name': 'Amanda Berger',
    'address': '54357 Lawrence Prairie Suite 425\nNorth Amber, DC 91926',
},
    'key89082': 'value65795',
    'key76835': 'value59817',
    'key32278': 'value92530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Matthew James',
    'address': 'PSC 7767, Box 1495\nAPO AP 54462',
    'text': 'Sea participant government record time figure type. Head indeed family describe authority.\nVoice which could outside worry. Actually star go both last.',
    'email': 'zunigakristen@example.org',
    'phone_number': '001-521-631-6982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Maddox',
    'Robert Valdez',
],
    'json': {
    'name': 'Lisa Morris',
    'address': '0939 Pierce Run Suite 168\nCraigburgh, ME 19130',
},
    'key89917': 'value84898',
    'key9495': 'value16722',
    'key79758': 'value46775',
    'key95996': 'value48600',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Daniel Peterson',
    'address': '799 Brian Flat\nEast Michael, RI 49697',
    'text': 'Reveal test person language ago lot send control. Inside she generation life consider necessary. Any month name police.\nFriend go picture. Almost government assume just receive ball reason.',
    'email': 'rushjoe@example.com',
    'phone_number': '504.684.6826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Gray',
    'Debra Shields',
    'Darrell Carter',
    'Kristina Reid',
    'Jonathan Holland',
],
    'json': {
    'name': 'Frank Baker',
    'address': '54410 Murphy Harbors Apt. 493\nWest Jasmin, NY 12254',
},
    'key97812': 'value43854',
    'key98086': 'value19373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Joseph Warren',
    'address': '19747 Danielle Cliff Apt. 462\nWest Michael, FL 98028',
    'text': 'Show sound including performance morning. Age result read offer. Condition fire theory science conference trip chair. Seven act space never believe leg.',
    'email': 'kimberlyking@example.com',
    'phone_number': '3014346137',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Logan Sullivan',
    'Kevin Collins',
    'George Simon',
    'Melissa Hansen',
    'Shannon Delgado DVM',
],
    'json': {
    'name': 'Robert Bishop',
    'address': '73954 Ashlee Circle\nMillschester, FL 48604',
},
    'key50254': 'value91261',
    'key11553': 'value40634',
    'key61745': 'value70969',
    'key17493': 'value34176',
    'key63284': 'value27764',
    'key19724': 'value12737',
    'key48376': 'value91642',
    'key79548': 'value34908',
    'key77148': 'value35024',
    'key28683': 'value7061',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Richard Wilson',
    'address': '771 Payne Gardens Suite 214\nKrystaltown, RI 29721',
    'text': 'College have risk least determine trade born late. Attorney lay stock us whole each. Education sometimes bank able at research street maybe.',
    'email': 'ipark@example.net',
    'phone_number': '001-358-478-7836x23353',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Hill',
],
    'json': {
    'name': 'Gary Bell',
    'address': '3864 Sarah Circle Apt. 561\nWest Kimberly, AR 99882',
},
    'key56002': 'value16899',
    'key85212': 'value26926',
    'key35513': 'value94143',
    'key96799': 'value83287',
    'key43012': 'value25641',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Sarah Ingram',
    'address': '299 Stephanie Cape Suite 897\nWest Matthew, VA 23848',
    'text': 'Ten time sit doctor born. Its whether avoid vote president.\nI check loss his member they.\nStrong realize cause news who this recent.',
    'email': 'courtneyvargas@example.org',
    'phone_number': '950-372-5348x6513',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Rios',
    'Joseph Roach',
    'Chelsea Green',
    'Joseph Long',
    'Gina Bauer',
    'Christopher Herrera',
    'Drew Patterson',
    'Ashley Murillo',
    'Fernando Murphy',
],
    'json': {
    'name': 'Joshua Hall',
    'address': 'PSC 0363, Box 7332\nAPO AE 46851',
},
    'key58858': 'value70284',
    'key42089': 'value34183',
    'key7905': 'value27986',
    'key78420': 'value54186',
    'key54071': 'value9633',
    'key49260': 'value63943',
    'key79722': 'value41357',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Eric Hoffman',
    'address': '2512 Brooke Ridge\nScottton, MO 43263',
    'text': 'Partner rise indicate as happy glass. Response blue career fight. Some speech them rate pass night.\nChallenge care amount. According training in.',
    'email': 'guzmananthony@example.com',
    'phone_number': '(768)419-0214',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Hall',
    'Michael Trevino',
    'Thomas Spears',
    'John Jones',
    'Alicia Patel',
    'Kimberly Williams DDS',
    'Angela Wright',
],
    'json': {
    'name': 'Catherine Bowman',
    'address': '2905 Edward Shoal\nMelissaville, AZ 40741',
},
    'key64933': 'value91747',
    'key70562': 'value97701',
    'key71385': 'value41850',
    'key11591': 'value33252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jessica Schmitt',
    'address': '0736 Jones Path Suite 066\nWigginston, ME 33643',
    'text': 'Over strong green ok. Over land view upon. On source simple particular car research weight.',
    'email': 'matthew52@example.com',
    'phone_number': '(802)478-0553',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Nolan',
    'Ashley Rivera',
    'Tyler Romero',
    'Ariana Edwards',
    'Tara Davis',
    'Nicolas Fox',
],
    'json': {
    'name': 'Steven Velasquez',
    'address': '26155 Jay Stravenue\nPort Richard, MD 08905',
},
    'key38682': 'value31832',
    'key81039': 'value53392',
    'key64786': 'value60835',
    'key69132': 'value92893',
    'key4094': 'value74360',
    'key40876': 'value58010',
    'key73725': 'value87973',
    'key10399': 'value59233',
    'key96430': 'value17566',
    'key81981': 'value25093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jeffrey Phelps',
    'address': '067 Patty Radial\nPort Nataliefurt, AL 63237',
    'text': 'Yourself prove practice who man become staff speech. Model simply but important pull. Hold probably she should truth.\nChild expert administration often level.\nProve force stop dark low various.',
    'email': 'sonyagallegos@example.org',
    'phone_number': '395-387-8102',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brian Anderson',
    'Nathan Crawford',
    'Corey Roberts',
    'Jeremy Hawkins',
    'Benjamin Marks',
    'Anthony Irwin',
    'Shannon Murphy',
],
    'json': {
    'name': 'Walter Crosby',
    'address': '3534 Thomas Springs Apt. 187\nTanyatown, MD 41856',
},
    'key59454': 'value83868',
    'key96242': 'value24321',
    'key19317': 'value26054',
    'key97951': 'value32306',
    'key3278': 'value86908',
    'key91003': 'value58181',
    'key55472': 'value91213',
    'key82547': 'value88479',
    'key31083': 'value22298',
    'key61092': 'value59725',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'John Baker',
    'address': '0677 Allison Ports\nCarolville, IL 47114',
    'text': 'Decide worry want such meeting top. Create difference commercial enjoy. Fact sit soldier above interest. Economic safe entire expect writer.',
    'email': 'chungjason@example.com',
    'phone_number': '(649)341-2810',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Montes',
    'Pedro Powell',
    'Carolyn Cohen',
    'Joshua Francis',
    'Heather Bailey',
    'Melissa Foster',
    'Rodney Myers',
    'Casey Fuller',
    'Barbara Green',
    'Michelle Bowman',
],
    'json': {
    'name': 'Timothy Lawson',
    'address': '7181 Anthony Estates\nNorth Raymond, FL 61007',
},
    'key68564': 'value35945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Paula Brown',
    'address': '36236 Mackenzie Row Apt. 521\nOsbornbury, MP 76308',
    'text': 'General son woman enter authority team group. Word sing program imagine. Place area boy you information share.',
    'email': 'kathleen60@example.com',
    'phone_number': '001-379-773-2880',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Robinson',
    'Sarah Jones',
    'Robin Anderson',
    'Michelle Blevins DVM',
    'Peter Shaw',
    'Jonathan Dudley',
    'Jessica Lee',
    'Jesus Tucker',
    'Austin Stevenson',
],
    'json': {
    'name': 'Dan Pham',
    'address': '872 Joseph Run\nLake John, NJ 45446',
},
    'key1943': 'value36956',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Stephen Bennett',
    'address': '733 Espinoza Course Apt. 540\nHollandstad, RI 75562',
    'text': 'Animal front especially point least. Another thousand find mouth development.\nDevelop investment subject live. Indicate project stage stage.',
    'email': 'thomasking@example.org',
    'phone_number': '+1-642-411-7487',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Richard Cohen',
    'Jay Cook',
    'Stacie Turner',
    'Donna Hoover',
    'Mr. Thomas Taylor',
],
    'json': {
    'name': 'Aaron Daniel',
    'address': '00447 Dalton Ferry Suite 822\nPierceland, OR 13065',
},
    'key34449': 'value24883',
    'key38896': 'value41974',
    'key75484': 'value7454',
    'key16680': 'value17986',
    'key70226': 'value53310',
    'key54786': 'value99873',
    'key58587': 'value81311',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Erin Moore',
    'address': '100 Sharp Forks\nPort Wandaside, MO 28139',
    'text': 'Assume lose expert police. Decade young old street win. Difficult time theory general hope list yourself. Either produce second happen address.',
    'email': 'ophillips@example.net',
    'phone_number': '001-306-858-4679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Douglas',
    'Jason Miles',
    'Robert Kaiser',
    'Jessica Ellis',
    'Eric Griffith',
    'Michael Graham',
    'Connor Perkins',
    'Cynthia Gardner',
],
    'json': {
    'name': 'Grace Taylor',
    'address': '1860 Tyler Stravenue Suite 838\nNorth Kevin, CA 06805',
},
    'key27889': 'value52941',
    'key14427': 'value39829',
    'key25984': 'value41460',
    'key27234': 'value86020',
    'key28314': 'value84287',
    'key76527': 'value77201',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Jennifer Rollins',
    'address': '100 Joseph Pike Apt. 127\nNorth Crystal, RI 84347',
    'text': 'North customer actually four. Condition teacher candidate know south like. Student as land nice together.\nYes happen indeed after exactly. Enough question blue. Best until discover fight player keep.',
    'email': 'reginaldsalazar@example.org',
    'phone_number': '+1-802-458-2336x06381',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Carol Beck',
],
    'json': {
    'name': 'Gary Lawrence',
    'address': '51869 Fletcher Shore Apt. 913\nJonesmouth, RI 17121',
},
    'key46157': 'value19716',
    'key70307': 'value32119',
    'key96961': 'value81800',
    'key53422': 'value25550',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Tiffany Valencia',
    'address': '57844 Villarreal Vista Apt. 939\nStephenmouth, MI 82161',
    'text': 'Himself safe heavy direction else young state. Office collection significant necessary.\nMilitary note near whether tell seek hope woman. Own address finish of bed world leg rather.',
    'email': 'romerosergio@example.com',
    'phone_number': '+1-679-666-3793',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Kline',
    'Shannon Williams',
    'Angela Carter',
    'Isaiah Newman',
],
    'json': {
    'name': 'Robert Jensen',
    'address': '12267 Stevenson Hollow Suite 200\nMooreberg, GU 64374',
},
    'key19596': 'value81944',
    'key90362': 'value62552',
    'key73703': 'value27835',
    'key23090': 'value65227',
    'key79387': 'value79006',
    'key97141': 'value58970',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Misty Robinson',
    'address': '9084 King Gateway\nSandrachester, NE 52540',
    'text': 'Whose degree head success car around here. Feeling middle might force produce step join.\nTheir both myself size. Light cover identify news next deal. You although safe pretty wind affect.',
    'email': 'melissa43@example.com',
    'phone_number': '(648)384-2927',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cindy White',
    'Mike Joseph',
    'Jonathan Herrera',
    'Kristin Espinoza',
],
    'json': {
    'name': 'Melissa Webb',
    'address': '661 Thomas Coves Suite 233\nEast Lindsayland, TX 95613',
},
    'key23697': 'value48751',
    'key84931': 'value8391',
    'key11909': 'value52834',
    'key81920': 'value97853',
    'key85969': 'value56394',
    'key7815': 'value9596',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Dustin Robbins',
    'address': '98354 Melissa Alley\nMorrowmouth, DC 36422',
    'text': 'Write time social. Money material score defense friend ground human. Light policy plan report policy population she technology. Student building recently relate record spring vote.',
    'email': 'jasmine02@example.org',
    'phone_number': '001-472-424-2086x0966',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lori Lopez',
    'Jacob Hall',
    'Christopher Jackson',
    'Valerie Parker',
    'Sierra Watson',
    'Jessica Zimmerman',
    'Mary Ruiz',
    'Erica Williams',
    'Linda Todd',
    'Jessica Garcia',
],
    'json': {
    'name': 'Tanner Cobb',
    'address': '123 Barajas Glen\nNew Johnbury, RI 48316',
},
    'key54432': 'value34402',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Sherri Robinson',
    'address': '71138 Moss Expressway Suite 263\nSteveberg, VA 08508',
    'text': 'Pm dinner scene maybe. Learn hospital side decision door notice off. No road now memory.\nInformation effect area defense. Toward property account.',
    'email': 'monica85@example.org',
    'phone_number': '+1-320-805-1838',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Chavez',
    'Jermaine Fox',
],
    'json': {
    'name': 'Alexis Miles',
    'address': '469 Norman Coves\nMichelleberg, GA 50644',
},
    'key98758': 'value85420',
    'key73583': 'value25312',
    'key29516': 'value64833',
    'key84763': 'value7465',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Nathaniel Washington MD',
    'address': 'PSC 0774, Box 5157\nAPO AP 10052',
    'text': 'Those tree after quite own soon official. Over herself audience can though spring break weight.\nInternational enough American defense. Allow hard add reality store team drive.',
    'email': 'gelliott@example.com',
    'phone_number': '(297)398-2751x1662',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Adkins',
    'Jacqueline Reyes',
    'Lisa Armstrong',
    'Denise Allen',
    'Kayla Simmons',
    'Robert Craig',
    'Jennifer Clark',
    'Kevin Sanders',
],
    'json': {
    'name': 'Mr. Scott Holmes MD',
    'address': '49104 Glover Station\nNew Richardbury, UT 97693',
},
    'key76851': 'value60284',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Kim Moore',
    'address': '43265 Daniel Lane\nNew Johnberg, OK 82625',
    'text': 'If someone each especially thousand develop program. Among last help modern leg.',
    'email': 'joshua70@example.com',
    'phone_number': '001-383-583-8989x633',
    'array_int_dynamic': [
    78905,
],
    'array_varchar_dynamic': [
    'Christopher Williams',
    'Richard Brandt',
    'Jeffrey Nguyen',
    'Jeanette Daugherty',
    'Makayla Fritz',
    'Beth Kline',
    'Mrs. Elaine Schwartz',
    'Kimberly Carter',
],
    'json': {
    'name': 'Mark Whitaker PhD',
    'address': '58825 Steven Manor Suite 249\nLake Tylerbury, MD 70772',
},
    'key8546': 'value70819',
    'key49349': 'value45337',
    'key77871': 'value84049',
    'key61437': 'value57065',
    'key45373': 'value38120',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Stephanie King',
    'address': '5605 Levine Square Suite 863\nLake Wendy, MN 13736',
    'text': 'Of may system exactly miss same. Fall low particularly receive bad five hope. Enjoy probably increase will pressure fact pull wide.',
    'email': 'melissaberg@example.com',
    'phone_number': '+1-881-459-6483x8566',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Roy Cordova',
],
    'json': {
    'name': 'Heather Lee',
    'address': '260 Jenkins Gardens\nNorth Tonyachester, OR 97101',
},
    'key43210': 'value21506',
    'key43878': 'value5796',
    'key39635': 'value28646',
    'key24195': 'value16163',
    'key63980': 'value98001',
    'key1675': 'value40549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Brittany Maddox',
    'address': 'USCGC Willis\nFPO AE 43528',
    'text': 'Other official wait not. Drug year sea piece writer. Draw paper result eat while.\nNecessary manage language old community. Group four choose edge fish when step.',
    'email': 'heather28@example.org',
    'phone_number': '315.880.0943x1701',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Calvin Anderson',
    'Mrs. Angela Mcguire',
],
    'json': {
    'name': 'Ryan Gregory',
    'address': '653 Williams Plains\nWrightchester, VA 59150',
},
    'key82714': 'value53304',
    'key30965': 'value68784',
    'key75437': 'value66115',
    'key14': 'value54892',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Bryce Smith',
    'address': 'PSC 3299, Box 3711\nAPO AE 63529',
    'text': 'This last option page return. Congress mind push own boy.\nNow if rise thank show. Seek game care rule speak social wear. Why book everything begin pass religious.',
    'email': 'jeremiahjackson@example.org',
    'phone_number': '(710)394-4875x65483',
    'array_int_dynamic': [
    18136,
],
    'array_varchar_dynamic': [
    'Brian Sherman',
    'Jonathon Davis',
    'Steve Bates',
    'Nichole Davis',
    'Erica White',
    'Tim Cox',
    'Melissa Duarte',
    'Mary Adams',
    'Larry Thompson',
    'Jasmine Gonzalez',
],
    'json': {
    'name': 'Sabrina Hayden',
    'address': '80040 Huang Fort Suite 397\nNicholasburgh, NC 89899',
},
    'key53641': 'value37687',
    'key79987': 'value55509',
    'key41188': 'value64272',
    'key19488': 'value59249',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Tony Bishop',
    'address': 'Unit 3510 Box 5739\nDPO AA 34741',
    'text': 'Rise his type huge figure against. Help cold us drug trial study time. Rest no college than lawyer anyone ball.\nPlace out music region bar return or. Candidate now morning yourself again.',
    'email': 'yhoffman@example.net',
    'phone_number': '413-207-0051x57003',
    'array_int_dynamic': [
    60654,
],
    'array_varchar_dynamic': [
    'Alan Frederick',
    'Geoffrey Yates III',
    'Alison Williams',
    'Dr. John Parker',
    'Deborah Ray',
],
    'json': {
    'name': 'Karen Shelton',
    'address': '403 Randall Vista Apt. 813\nPort Kara, WI 81994',
},
    'key70831': 'value53645',
    'key12078': 'value19523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Christopher Parrish',
    'address': '5581 Matthew Centers\nNorth Hannahborough, IL 43741',
    'text': 'Around what can often protect drug. Half form officer nature project since exactly. Record agreement any section nature.',
    'email': 'stephanie06@example.org',
    'phone_number': '9366612383',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Russell Juarez',
    'Stephanie Johnson',
    'Melissa Gross',
    'Jimmy Jensen',
    'Matthew West',
],
    'json': {
    'name': 'Mr. Brian Obrien',
    'address': '981 Felicia Grove Suite 192\nMcbridefurt, IN 44120',
},
    'key70249': 'value32349',
    'key2294': 'value60848',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Alvin Blankenship',
    'address': '823 Keith Terrace Suite 189\nNorth Larry, CO 22672',
    'text': 'Right free action company. Attack during away risk table. Phone win stage record investment.\nEmployee sort once sound. Thought interest need sometimes hot fight onto.',
    'email': 'francissandra@example.net',
    'phone_number': '(237)457-2628x127',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Diana Ramirez',
    'Lindsey Harrison',
    'Cameron Cooper',
    'Jean Wall',
    'Mark Mueller',
    'Sarah Hill',
    'Phillip Wiley',
    'Jane Duffy',
    'Stephanie Moore',
],
    'json': {
    'name': 'Angel Day',
    'address': 'PSC 9264, Box 2072\nAPO AE 23297',
},
    'key17049': 'value69905',
    'key1327': 'value39707',
    'key99075': 'value95650',
    'key62293': 'value86926',
    'key76127': 'value73510',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Mark Washington',
    'address': '0504 Thompson Forest Apt. 208\nLuismouth, TX 67488',
    'text': 'Less coach receive executive significant better. Off surface rock. Itself sense institution forget.\nAir certain program local real.',
    'email': 'jeffreywatson@example.org',
    'phone_number': '3095828590',
    'array_int_dynamic': [
    62162,
],
    'array_varchar_dynamic': [
    'George Lee',
    'Troy Moran',
    'Melissa Reed',
    'Melinda Cohen',
    'Casey Smith',
    'Debra Hamilton',
    'Michael Le',
    'Monica Hughes',
    'Diane Clay',
    'Alan Allen',
],
    'json': {
    'name': 'Michael Edwards',
    'address': '474 Roberts Camp Suite 060\nNew Sarabury, AL 98034',
},
    'key79866': 'value96495',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Ronald Meyer',
    'address': '20753 Elizabeth Village Suite 572\nRachelberg, ID 91161',
    'text': 'Sing leader success as cell source today. Boy number store firm compare claim hot. Special Democrat main choice idea pressure consider onto.\nOwner arm industry. From similar herself indeed oil it.',
    'email': 'marcus77@example.net',
    'phone_number': '+1-705-901-6125x46326',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Bailey',
    'Margaret Davis',
    'Alejandro Abbott',
    'Ricardo Gonzalez',
    'Gina Cordova',
    'Marissa Baker',
    'Christopher Huang',
    'Jose Gomez',
],
    'json': {
    'name': 'Samuel Harmon',
    'address': '127 Emily Burg Suite 085\nJasminfort, CT 89475',
},
    'key10096': 'value13773',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Kristin Nolan',
    'address': '26370 Laura Points Apt. 454\nMunozshire, AK 76057',
    'text': 'Here food born. Wish wait least upon blue phone. Citizen pretty guy message local government.\nBut sea somebody others question style. Example accept game light concern necessary.',
    'email': 'anthonylawrence@example.com',
    'phone_number': '+1-327-554-8761x4442',
    'array_int_dynamic': [
    19685,
],
    'array_varchar_dynamic': [
    'George Bryant',
    'Angela Roach',
    'Annette Jordan',
    'Patricia Brown',
    'Joel Horn',
    'Roger Paul',
    'Madison Sanchez',
],
    'json': {
    'name': 'Christopher Cortez',
    'address': '238 Jacob Circles\nKathrynland, IN 25969',
},
    'key33261': 'value17150',
    'key86530': 'value28073',
    'key13598': 'value93377',
    'key2758': 'value1606',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Victor Moore',
    'address': '625 Roberson Rapid\nPort Matthew, MN 83313',
    'text': 'Agent country eye race million practice popular. Serve us I their himself.\nScientist coach we. Answer others really agreement.',
    'email': 'kyle67@example.org',
    'phone_number': '+1-926-204-8250x53050',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Cooper',
    'Hector Moore',
    'Aaron Kane',
    'Richard Smith',
    'Elizabeth Carpenter',
    'Juan Hill',
    'Craig Edwards',
    'Kevin Horne',
],
    'json': {
    'name': 'Kimberly Jones',
    'address': 'USCGC Walker\nFPO AP 55212',
},
    'key90929': 'value74416',
    'key32311': 'value34405',
    'key21196': 'value36922',
    'key95251': 'value99562',
    'key54111': 'value42280',
    'key36382': 'value37470',
    'key92683': 'value19724',
    'key93742': 'value29883',
    'key81474': 'value68880',
    'key72411': 'value15553',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Alejandra Horton',
    'address': '215 Glenda Circles Suite 346\nKimberlytown, OH 26562',
    'text': 'Short star water capital debate student necessary. Quality huge learn. Beat interview catch myself third whether. Spring pattern environmental structure.\nFull mission will heart law term defense.',
    'email': 'jessicalewis@example.net',
    'phone_number': '+1-275-323-3282x74193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'John Nelson',
    'Richard Murphy',
    'Grant Larsen',
    'Emily Howard',
    'Jennifer Brown',
    'Christine Gutierrez',
    'Angela Henderson',
],
    'json': {
    'name': 'Ms. Kimberly Boone',
    'address': '44054 Mcclain Fork Apt. 709\nOneillchester, AL 31871',
},
    'key4063': 'value69697',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Cynthia Hines',
    'address': '5428 Singleton Vista\nWest Paul, AS 67950',
    'text': 'Example shake single military husband. Wonder science fly road physical.\nForget conference money movement. Fill investment hard that early.',
    'email': 'ychen@example.org',
    'phone_number': '968-530-8807',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Adam Thompson',
    'Michael Baird',
    'Michael Mclean',
    'Jonathon Jackson',
    'Diane Dickerson',
],
    'json': {
    'name': 'Anna Joyce',
    'address': '5492 Michelle Groves Suite 012\nJeffreyport, MA 62304',
},
    'key83811': 'value15534',
    'key55603': 'value32304',
    'key65025': 'value62589',
    'key5205': 'value66631',
    'key88013': 'value1655',
    'key1127': 'value84468',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Lauren Howard',
    'address': '48883 Jennifer Locks\nPort Jeffrey, AK 83208',
    'text': 'They provide resource no yet police quickly soon. Teach either son other rest house.\nShake like impact home able coach station. His street occur keep. Prevent issue name.',
    'email': 'andersonray@example.com',
    'phone_number': '(386)652-9301x271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ian Farmer',
    'Jeffrey Guerrero',
    'Michael Rivera',
    'Albert Nelson',
],
    'json': {
    'name': 'Keith Cummings',
    'address': '422 Matthew Inlet Suite 487\nLutzshire, NE 56541',
},
    'key62309': 'value78298',
    'key60901': 'value1169',
    'key26376': 'value1961',
    'key47775': 'value78775',
    'key83287': 'value49075',
    'key45168': 'value7136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Brian Murray',
    'address': '588 Emily Trace\nNew Steven, CO 42436',
    'text': 'Onto understand soon clearly space. Alone page position minute use free. Town current board.\nWhole decide range window fill minute manager. Direction artist course road onto.',
    'email': 'rnelson@example.org',
    'phone_number': '001-836-338-6727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Adam Tucker',
    'Felicia Mora',
],
    'json': {
    'name': 'Charles Smith',
    'address': '399 Anna Dale Apt. 793\nPort Katie, WI 04472',
},
    'key24026': 'value98127',
    'key23045': 'value94058',
    'key56964': 'value19825',
    'key2380': 'value69150',
    'key91674': 'value72724',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Valerie Chase',
    'address': '17686 Wright Lights Suite 561\nWest Christinabury, TX 76627',
    'text': 'Individual improve sure pattern. Continue those wide what tough project camera. Animal scene get compare.\nExplain remain budget movement. Professor statement forward decide.',
    'email': 'dvasquez@example.org',
    'phone_number': '739-589-7538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Garcia',
    'Douglas Turner',
],
    'json': {
    'name': 'Denise Diaz',
    'address': '490 Brian Harbors Suite 924\nTaylorstad, TN 84125',
},
    'key19412': 'value87828',
    'key83521': 'value54286',
    'key81300': 'value35878',
    'key97147': 'value11094',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Wesley Jones',
    'address': 'USNV Benson\nFPO AE 62389',
    'text': 'Read nearly tend image. Surface tend spring much adult change woman. President series born strategy. Some third tough force race fire.',
    'email': 'amullins@example.net',
    'phone_number': '881.634.9140x013',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brian Martinez',
    'Michelle Lester',
    'Tammy Ayala',
    'Adam Allen',
    'Jake West',
    'Patricia Collins',
    'Eric Solis',
    'Douglas Gonzales',
    'Matthew Willis',
    'Brent Miller',
],
    'json': {
    'name': 'Dean Dixon',
    'address': '747 Daniel Course Suite 328\nVictoriafort, ND 34312',
},
    'key94183': 'value55946',
    'key29961': 'value57275',
    'key28771': 'value31715',
    'key92455': 'value99487',
    'key38951': 'value81474',
    'key52624': 'value75437',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Keith Jackson',
    'address': '465 Melissa Mission Apt. 266\nRhodesstad, AR 32672',
    'text': 'Approach left respond heart stuff scientist. Throughout develop left chance word. Rock group lay example particular that case someone. Course charge window involve.',
    'email': 'cdaniels@example.org',
    'phone_number': '465-948-5311x06764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Renee Evans',
    'Anna Jackson',
    'Jody Noble',
    'Tara Hamilton',
    'Justin Evans',
    'Heidi Choi',
    'Terri Hunt',
    'Renee Schneider',
    'Emily Lopez',
],
    'json': {
    'name': 'Melissa Romero',
    'address': '16894 Johnson Stravenue\nEast Melissaberg, MP 06187',
},
    'key4205': 'value72010',
    'key27353': 'value25031',
    'key73578': 'value65',
    'key44596': 'value24863',
    'key35062': 'value70244',
    'key59081': 'value44358',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Linda Carlson',
    'address': '8186 Gonzalez Summit Suite 111\nJohnview, ND 05587',
    'text': 'Particular tonight begin head. Source walk finish you around.\nOrganization here state old actually. Structure born whom serve open direction.',
    'email': 'johnpeters@example.org',
    'phone_number': '412.840.0529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kristina Lewis',
    'Regina Morgan',
    'Mary Smith',
    'Leslie Bradford',
    'Leah Webb',
    'Rachael Ramirez',
    'Susan Perry',
    'Pamela Anderson',
],
    'json': {
    'name': 'Chad Gordon',
    'address': '123 Jason Mount\nSouth Courtney, HI 51375',
},
    'key25727': 'value8137',
    'key94015': 'value56449',
    'key17205': 'value57230',
    'key60265': 'value66101',
    'key42343': 'value8629',
    'key18780': 'value91414',
    'key30764': 'value56971',
    'key17872': 'value48244',
    'key51677': 'value69337',
    'key74778': 'value6499',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Elizabeth Day',
    'address': '9802 Justin Divide Suite 511\nBarnesfort, FL 48460',
    'text': 'Majority improve both reveal four. Dog interview leg those herself why hospital.\nYear into senior watch painting yet. Hotel fish resource computer.',
    'email': 'xrivera@example.net',
    'phone_number': '(443)610-2702x793',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sarah White',
    'Maria Ward',
    'Corey Sanchez',
],
    'json': {
    'name': 'Chloe Bowers',
    'address': '79340 Ramirez Haven Suite 552\nGilmoreport, NV 60384',
},
    'key59056': 'value7978',
    'key63343': 'value74603',
    'key93790': 'value87112',
    'key68783': 'value93394',
    'key7004': 'value17957',
    'key23512': 'value89123',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Amy Snyder',
    'address': '962 Nicholas Terrace\nNew Biancafort, AS 15873',
    'text': 'Clear approach whatever nice. Hope wife store likely treat major. Race college sense ahead guess.',
    'email': 'coxsandra@example.net',
    'phone_number': '001-891-642-2302',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Kennedy',
    'Brian Perez',
    'Holly Reyes',
    'Norma Turner',
    'Benjamin Gaines',
    'Joseph Palmer',
    'Robin Williams',
],
    'json': {
    'name': 'Nicole Moore',
    'address': '40868 Palmer Ports Apt. 231\nEast Amyborough, MH 02925',
},
    'key58884': 'value51033',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Christopher Smith',
    'address': '35143 Lane Locks\nBendermouth, WI 05344',
    'text': 'Relationship individual support later image. Difficult exactly yard every smile.\nTechnology daughter gun management country leader away. Order modern food sense.\nMother town result account see bank.',
    'email': 'april81@example.org',
    'phone_number': '(462)961-8235',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Downs',
    'Ricky French',
    'Kenneth Golden',
],
    'json': {
    'name': 'Joshua Freeman',
    'address': '094 Rowe Centers Suite 060\nNorth Christinabury, CO 05268',
},
    'key56256': 'value27821',
    'key50748': 'value52984',
    'key1309': 'value18643',
    'key24150': 'value68684',
    'key27078': 'value60191',
    'key14825': 'value81229',
    'key5958': 'value80626',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Raymond Dunlap',
    'address': '62804 Jason Roads Apt. 429\nRichardborough, MT 76390',
    'text': 'Around drop hair number phone mind opportunity. Character crime especially wrong measure whatever from. Remain improve feel cut stock.',
    'email': 'ffreeman@example.com',
    'phone_number': '965-704-8379x696',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Johnson',
    'Terri Pitts',
    'Andrew Rios',
    'Adrian Soto',
    'Benjamin Love',
],
    'json': {
    'name': 'Kenneth Williams',
    'address': 'Unit 3783 Box 0298\nDPO AE 02807',
},
    'key68940': 'value65168',
    'key10093': 'value2032',
    'key24308': 'value71280',
    'key5232': 'value68182',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Edward Hall',
    'address': '8859 Bell Curve\nJakeberg, GA 94330',
    'text': 'Sense maintain government policy color.\nWhether practice window data mind. Again money keep teach story financial able. Price religious page word fight movement.',
    'email': 'arthurjones@example.org',
    'phone_number': '318.355.8199',
    'array_int_dynamic': [
    79871,
],
    'array_varchar_dynamic': [
    'Gary Molina',
    'Chelsea White',
],
    'json': {
    'name': 'Mario Jenkins',
    'address': '2711 Williams Plaza\nWest Charles, AZ 03200',
},
    'key68363': 'value51999',
    'key94415': 'value76791',
    'key42033': 'value31445',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Meredith Goodwin',
    'address': 'Unit 6537 Box 0709\nDPO AP 35272',
    'text': 'Reality structure eight agency admit. Morning opportunity someone.\nLoss tree onto base word. Eat each account drop choice. Upon while admit morning source foot.',
    'email': 'hunterdavid@example.net',
    'phone_number': '941.382.3402x45306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amy Morgan',
    'Linda Estrada',
    'Marc Wilson',
    'Peter Parrish',
    'Stephen Cohen',
],
    'json': {
    'name': 'Michelle Bradshaw',
    'address': '1652 Lee Manors Suite 543\nGrahamfurt, CO 94037',
},
    'key31548': 'value8499',
    'key91717': 'value66419',
    'key20793': 'value59021',
    'key41220': 'value19340',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'George Johnson',
    'address': '15866 Randall Canyon Suite 955\nPort Samuel, OH 07116',
    'text': 'Research a fund statement beat information. Most other trade guess.\nRaise build leader light treat. Free agreement capital yet eat fly model. On fill which their old choice.',
    'email': 'haroldbest@example.net',
    'phone_number': '279.380.0564x523',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Gordon Goodman',
],
    'json': {
    'name': 'Donald Carr',
    'address': '34028 Burns Forks Suite 910\nNorth Stacey, MN 23907',
},
    'key45160': 'value2824',
    'key12988': 'value18889',
    'key98012': 'value79032',
    'key43081': 'value11596',
    'key15639': 'value65769',
    'key66174': 'value60039',
    'key1463': 'value76616',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Michelle Park',
    'address': '58581 Randall Bypass Suite 169\nPort Anthony, NE 37309',
    'text': 'Would operation break five officer. Actually not interest thought not personal generation. Have operation history group glass.\nNear throughout show great while apply hour.',
    'email': 'zblackwell@example.net',
    'phone_number': '+1-645-296-3228x68490',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Bauer',
    'Stephanie Martin',
],
    'json': {
    'name': 'Mason Miller',
    'address': '239 Calhoun Station Apt. 866\nChristinefort, IL 20842',
},
    'key54817': 'value37470',
    'key27344': 'value29681',
    'key83449': 'value72959',
    'key26783': 'value54310',
    'key77592': 'value35172',
    'key91088': 'value74074',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Brianna Steele',
    'address': '7040 Edward Orchard Apt. 901\nRoyton, MD 65937',
    'text': 'Finish call need available budget art money. Always listen mother finally young particular already.\nInto natural section whatever mission item.',
    'email': 'ymorales@example.org',
    'phone_number': '(230)761-9574x6829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Martin Glenn',
    'Joseph Harper',
    'Chelsea Nielsen',
    'Felicia Smith',
    'Thomas Hernandez',
    'Franklin Campbell',
],
    'json': {
    'name': 'Karen Le',
    'address': '54867 Mark Ways Suite 276\nHillton, MH 99719',
},
    'key12880': 'value6025',
    'key96923': 'value88272',
    'key7481': 'value46715',
    'key64831': 'value26786',
    'key39844': 'value9132',
    'key72857': 'value61961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Natasha White DVM',
    'address': '314 Brittany View Apt. 796\nWatkinsburgh, DC 97537',
    'text': 'Age meet last common left. Adult easy major possible enough black.\nStart school true direction. Federal end church. Experience often floor across.',
    'email': 'xphillips@example.net',
    'phone_number': '515.217.6116',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Robles',
    'Randy Green',
    'Angela Taylor',
    'David Johnson',
    'William Sanchez',
    'Kristine Knapp',
    'Robin Lee',
    'Donald Delgado',
    'Christopher Jones',
],
    'json': {
    'name': 'Jeff Coleman',
    'address': '41510 Alyssa Orchard Apt. 058\nSouth Cynthiaburgh, WA 96394',
},
    'key57619': 'value14558',
    'key85979': 'value26823',
    'key85402': 'value88605',
    'key45096': 'value33415',
    'key815': 'value64349',
    'key42381': 'value41563',
    'key72757': 'value6751',
    'key74053': 'value56769',
    'key23192': 'value32902',
    'key6309': 'value65978',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Gloria Brown',
    'address': '27683 Kristen Ports Suite 005\nAshleyville, PW 02279',
    'text': 'Kind home difficult civil. Add explain suggest throughout language. Final outside within son body series their.',
    'email': 'escobarhailey@example.org',
    'phone_number': '001-837-781-4835x2064',
    'array_int_dynamic': [
    88485,
],
    'array_varchar_dynamic': [
    'Erik Gomez',
    'Denise Thomas',
    'Theresa Woods',
    'Katrina Moore',
],
    'json': {
    'name': 'Shane Rich',
    'address': '014 Stewart Dale\nEast Jenniferville, RI 69010',
},
    'key31338': 'value24151',
    'key85851': 'value3781',
    'key68608': 'value29031',
    'key77960': 'value83531',
    'key11137': 'value45503',
    'key48709': 'value16696',
    'key58311': 'value41622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Sarah Bates',
    'address': 'PSC 9914, Box 5349\nAPO AP 10321',
    'text': 'Child movement firm those water ready break. Social final box possible country forward both. Structure available use perhaps.',
    'email': 'murphysarah@example.net',
    'phone_number': '(732)973-0787x80264',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Lutz',
    'Monica Vaughan',
    'Adriana Torres',
    'Deborah Perez',
    'Rachel Logan',
],
    'json': {
    'name': 'Ann Evans',
    'address': '1818 Brown Squares Apt. 132\nSaraberg, NV 85129',
},
    'key81150': 'value10491',
    'key82497': 'value45739',
    'key95547': 'value46824',
    'key71058': 'value60638',
    'key69700': 'value76558',
    'key73050': 'value95182',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'James Hancock',
    'address': '88136 Torres Wells Apt. 905\nNew Johnfort, NM 55942',
    'text': 'Office strategy forget around. Truth wonder continue interview. Report cost structure nothing billion sit fire.\nImagine why goal. Book seek quality half.',
    'email': 'bruce59@example.com',
    'phone_number': '824.826.4283x04603',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'John Phillips',
    'Peter King',
],
    'json': {
    'name': 'Juan Mendez',
    'address': '45266 Kayla Locks\nNorth John, KY 79255',
},
    'key33840': 'value73983',
    'key76067': 'value6576',
    'key28177': 'value80209',
    'key4513': 'value26911',
    'key37850': 'value78802',
    'key33216': 'value38299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Monica Thomas',
    'address': 'Unit 7028 Box 0373\nDPO AE 42836',
    'text': 'Beyond discuss past. Kitchen senior note large sport imagine. Television pull defense rest step. Treatment why sea ground operation evening.',
    'email': 'christensenhannah@example.org',
    'phone_number': '+1-800-331-2038',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Raven Hill',
    'Mark Kelly',
    'Susan Jones',
],
    'json': {
    'name': 'Arthur Lee',
    'address': 'USNV Robertson\nFPO AP 60506',
},
    'key72444': 'value56936',
    'key96232': 'value2552',
    'key28941': 'value20605',
    'key4261': 'value76594',
    'key39651': 'value42543',
    'key11579': 'value75877',
    'key28845': 'value49702',
    'key39460': 'value3229',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Mark Kim',
    'address': '28926 Julie Burgs\nEast Ashleyville, OK 03227',
    'text': 'Star drive second military lead start. Church cup lead. For several guy study author research.\nOffer brother analysis. Cause sort need method character. Adult soon common audience carry professor.',
    'email': 'christopherramirez@example.org',
    'phone_number': '676-828-9337',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Crosby',
    'Christopher Cochran',
    'Ray Knox',
    'Jesus Lane',
],
    'json': {
    'name': 'Jamie Davis',
    'address': '489 David Fields\nLake Josephhaven, HI 24319',
},
    'key7492': 'value42492',
    'key84299': 'value49944',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Steven Ashley',
    'address': 'USNS Boyd\nFPO AA 07176',
    'text': 'Car purpose home. Body sea employee may animal.\nAgain would economic reach try. Behind above whose guess. Write whose affect.',
    'email': 'dodsonrobert@example.net',
    'phone_number': '420-296-3196x758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Lewis',
    'Paula Nelson',
    'Karl Richardson',
    'Dr. Melinda Peterson',
    'Logan Peterson',
    'Lydia Howell',
],
    'json': {
    'name': 'Shannon Stewart',
    'address': 'Unit 2996 Box 1110\nDPO AP 79324',
},
    'key65930': 'value47912',
    'key41150': 'value76714',
    'key10367': 'value89045',
    'key58951': 'value13500',
    'key42486': 'value21512',
    'key18444': 'value95397',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Angel Glass',
    'address': '252 Dustin Drive\nSusanshire, OK 38494',
    'text': 'Will indeed care see long. Also painting price total father difference majority.\nProvide relate chance here see capital. Culture pretty wall require. Last find source method.',
    'email': 'proctorallison@example.net',
    'phone_number': '806-895-6166x174',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Johnson',
    'Christopher Kelly',
    'Carmen Fry',
    'Diana Reese',
    'Katherine Sanchez',
    'Andrew Ball',
    'Tiffany Martin',
    'David Walton MD',
],
    'json': {
    'name': 'Robert Hansen',
    'address': '4605 Stone Expressway\nPort Tina, PA 85071',
},
    'key96953': 'value18452',
    'key90199': 'value95364',
    'key42069': 'value5379',
    'key28041': 'value97170',
    'key71184': 'value72965',
    'key64095': 'value8091',
    'key36876': 'value7772',
    'key99400': 'value67990',
    'key3733': 'value74031',
    'key22044': 'value4072',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Leslie Cabrera',
    'address': '547 Larson Street Apt. 462\nJonesfurt, FM 80000',
    'text': 'Nation movement operation by event. Really break environment federal career south despite. Staff Congress call future. Finish everyone special culture clearly report high.',
    'email': 'wpitts@example.net',
    'phone_number': '272.815.3589x1043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Russell White',
    'Veronica Keller',
    'Andrew Cook',
    'Kelly Escobar',
    'Mrs. Christina King',
    'Mark Jones',
    'Patrick Stevens',
    'Rebecca Green',
],
    'json': {
    'name': 'Kelly Donaldson',
    'address': 'USS Whitaker\nFPO AE 82460',
},
    'key15038': 'value6861',
    'key29929': 'value29668',
    'key76611': 'value55827',
    'key49680': 'value6538',
    'key8187': 'value33163',
    'key79096': 'value42694',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Rebecca Brown DDS',
    'address': '8925 Joshua Pine\nNorth Shannon, NV 84377',
    'text': 'Collection ability rather debate everyone young sometimes military. Group size have city specific.\nFight beyond road soon best share. Blue technology after appear hundred age however.',
    'email': 'danielcarter@example.net',
    'phone_number': '9882241284',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Reginald Vaughan',
    'Ryan Salazar',
    'Billy Rollins',
    'Maria Stewart',
    'Cathy Wong',
    'Michael Watson',
    'Laura Morris',
    'Jamie Callahan',
    'Eileen Gonzales',
    'David Garcia',
],
    'json': {
    'name': 'Leslie Roberson',
    'address': '919 Stephanie Lake Suite 766\nSouth Allisonhaven, DE 12594',
},
    'key57173': 'value8277',
    'key43388': 'value73917',
    'key1402': 'value23528',
    'key7154': 'value20732',
    'key96125': 'value33672',
    'key5186': 'value82901',
    'key87504': 'value23975',
    'key16066': 'value41149',
    'key53018': 'value13815',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Courtney Lewis',
    'address': '90994 Thomas Squares Apt. 164\nLukeburgh, PR 05932',
    'text': 'Wife together positive describe into citizen. Certain economy ok bed board rather. Necessary effort those parent most because or.',
    'email': 'charleswhite@example.com',
    'phone_number': '650.364.0172x254',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Noah Nguyen',
    'Brendan Humphrey',
    'Lisa Atkins',
],
    'json': {
    'name': 'Phyllis Wilson',
    'address': '1223 Martinez Mission Suite 245\nSouth Daniel, MA 45912',
},
    'key79081': 'value18634',
    'key92717': 'value82138',
    'key41882': 'value28535',
    'key23873': 'value34345',
    'key75079': 'value28184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Deanna York',
    'address': '5102 Steven Junctions Suite 271\nBrownberg, TX 73567',
    'text': 'Reveal at only six responsibility treatment somebody. Remain trip sing even exist. Yes three list today population if campaign other.',
    'email': 'danielwhite@example.org',
    'phone_number': '(328)269-1237x534',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Adam Rodriguez',
    'Lisa Shea',
    'Paul Figueroa',
    'Tina Esparza DVM',
    'Christopher Fuentes DDS',
    'Heather Adams',
    'Diana Ortiz',
],
    'json': {
    'name': 'Donald Vang',
    'address': '427 Jennifer Meadow\nMariaborough, ND 63876',
},
    'key55555': 'value91674',
    'key67673': 'value65618',
    'key65633': 'value19537',
    'key47845': 'value2218',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kenneth Buchanan',
    'address': '67364 Charles Creek\nTorresshire, ME 10417',
    'text': 'Two difference interest one lay sister. Figure travel nearly one tonight yourself trade.\nTheir just create. Forward huge record leg.\nSafe effort serious light enjoy suddenly nor.',
    'email': 'william52@example.com',
    'phone_number': '(423)834-0449',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Bond',
    'Brandon Cooper',
    'Marc Thompson',
    'Rebecca Brown',
    'Michael Valencia',
    'Elizabeth Spencer',
],
    'json': {
    'name': 'Jennifer Hill',
    'address': '84403 Marshall Square Apt. 794\nLongton, TN 06464',
},
    'key22008': 'value71426',
    'key31082': 'value30659',
    'key89204': 'value66694',
    'key58873': 'value99593',
    'key17222': 'value656',
    'key85824': 'value32376',
    'key46429': 'value17336',
    'key27750': 'value13369',
    'key73778': 'value9088',
    'key185': 'value81710',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jason Harris',
    'address': '43638 Robertson Springs\nLake Jamesville, ME 88511',
    'text': 'Message anything total record want century southern including. Process theory model claim accept whether step.',
    'email': 'douglas24@example.com',
    'phone_number': '429.560.2980x6283',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Travis Donovan',
    'Priscilla Mckinney',
    'Jennifer Nelson',
    'Lisa Adams',
    'Samuel Welch',
    'Peter Norman',
    'Jane Brown',
    'Sarah Valdez',
],
    'json': {
    'name': 'Brandy Gonzalez',
    'address': '674 Hawkins Mission Suite 460\nHermanland, AK 09689',
},
    'key67925': 'value65400',
    'key95859': 'value87505',
    'key5000': 'value33088',
    'key47574': 'value35834',
    'key92652': 'value20090',
    'key22419': 'value96925',
    'key58459': 'value13721',
    'key65676': 'value28843',
    'key56353': 'value78862',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Amy Silva',
    'address': '87324 Perez Junction\nFrankberg, NC 06841',
    'text': 'Tell character vote inside phone. Oil job idea economy.\nData home cultural option play benefit. Increase others section food charge professor. Lay cut act cut.',
    'email': 'dhammond@example.net',
    'phone_number': '001-694-502-3583x6799',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Stephens',
    'Lynn Davis',
    'Brianna Mitchell',
    'Melissa Fox',
    'Jean Abbott',
],
    'json': {
    'name': 'Logan Miller',
    'address': '386 Adam Landing Suite 132\nGordonport, MH 21116',
},
    'key12040': 'value91968',
    'key16307': 'value44427',
    'key38088': 'value50809',
    'key87871': 'value33718',
    'key73034': 'value43759',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Stacie Preston',
    'address': '88632 Paul Forge\nNew Monique, NJ 10440',
    'text': 'From find despite I use city. Doctor theory live tax moment.\nDemocratic race current represent record lead. No appear send system. Room ability window article manage herself.',
    'email': 'williamvalencia@example.org',
    'phone_number': '001-910-221-8457x700',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Bailey',
    'Jacob Erickson',
    'Joshua Cochran',
    'Mark Gonzalez',
    'Tina Pearson',
],
    'json': {
    'name': 'Stephen Fox',
    'address': '625 Holt Islands\nWest Ronald, PW 14486',
},
    'key33632': 'value40309',
    'key72705': 'value71624',
    'key42392': 'value14388',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Max Brown',
    'address': '51400 Carter Hills\nFernandezfurt, MD 42320',
    'text': 'Character last cup reality lead leg.\nSite often be home car these. In like him with.\nYet increase result start ground specific.\nPart always eat. Usually push give. Happen rate care control.',
    'email': 'robert26@example.org',
    'phone_number': '001-336-737-4169x6719',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mary Jones',
    'John Garcia',
    'Catherine Cummings',
    'Mary Ellison',
    'Carl Bowman',
    'Leslie Morgan',
    'Doris Adams',
    'Jared Buckley',
    'Veronica Gallegos',
],
    'json': {
    'name': 'Kevin Miller',
    'address': '696 Deborah Fields\nNorth Andreaview, CA 55802',
},
    'key88823': 'value36111',
    'key434': 'value30902',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Sydney Black',
    'address': '06746 Caitlin Fork\nPort Julia, NM 60584',
    'text': 'Federal record opportunity professional beat. Various sing hear create maintain national.\nWhether former message modern news.',
    'email': 'sherry71@example.net',
    'phone_number': '8268370581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tara Garcia',
    'Wayne Davis',
    'Leslie Scott',
    'Todd Maldonado',
    'Jennifer Summers',
    'Melissa Taylor',
    'Amy Dalton',
    'Joyce Noble',
    'Ryan Hays',
    'Sophia Parker',
],
    'json': {
    'name': 'Nicholas Miller',
    'address': '48475 Williams Square\nPort Rachel, OR 98781',
},
    'key82820': 'value90088',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Erin Bauer',
    'address': '327 Suzanne Parks\nAnnamouth, OK 42738',
    'text': 'Garden ready hope. Cut themselves floor pass cut before.',
    'email': 'edwin21@example.org',
    'phone_number': '895-685-8066',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James James',
    'Matthew Rubio',
    'Rebecca Benjamin',
    'Seth Smith',
    'Steven Harrington',
],
    'json': {
    'name': 'Matthew Foster',
    'address': '9978 Maldonado Green\nJonesshire, OR 23479',
},
    'key43712': 'value81667',
    'key30460': 'value39180',
    'key64098': 'value94610',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Donna Knight',
    'address': '440 Kelly Village Suite 549\nSouth Jennifer, MT 39176',
    'text': 'Movie human by increase interview. Protect as outside in.',
    'email': 'zfry@example.com',
    'phone_number': '624.470.7317',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Richard Jackson',
    'Aaron Perry',
    'Lauren Moore',
    'Jennifer Benson',
    'Jason Bates',
    'Jason Pierce',
    'Wanda Cain',
    'Tricia Ortega',
    'Keith Brooks',
    'John Black',
],
    'json': {
    'name': 'Christine Walker',
    'address': '11591 Hughes Ports\nNew Emily, NE 36491',
},
    'key29975': 'value92788',
    'key89015': 'value6630',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jennifer Serrano',
    'address': '11822 Villa Divide\nSanchezmouth, TN 29852',
    'text': 'Character report although to argue. Option computer seat find along between take its. Green huge minute.',
    'email': 'mfrancis@example.com',
    'phone_number': '3234829424',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Billy Johnson',
],
    'json': {
    'name': 'Brian Martin',
    'address': '411 Rose Drives Suite 442\nCharlesfort, ME 69780',
},
    'key54262': 'value92885',
    'key93902': 'value27181',
    'key71874': 'value45985',
    'key47031': 'value59047',
    'key2003': 'value71737',
    'key22227': 'value33842',
    'key89341': 'value78288',
    'key41249': 'value34741',
    'key65708': 'value38721',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jeremy Holden',
    'address': '831 Stephen Flats Suite 618\nPort James, GA 26611',
    'text': 'Happen require difficult high.\nEvidence responsibility age start old return although. Run local back movie executive blue surface. Argue language tend high.',
    'email': 'rcrawford@example.com',
    'phone_number': '905-840-8608x863',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Megan Johnson',
    'Ashley Stewart',
],
    'json': {
    'name': 'Lori Dalton',
    'address': 'Unit 5214 Box 4328\nDPO AE 38392',
},
    'key71278': 'value73253',
    'key73064': 'value74378',
    'key13389': 'value612',
    'key62742': 'value27813',
    'key51572': 'value81060',
    'key70217': 'value52839',
    'key30874': 'value67090',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Nicholas Mayo',
    'address': '2766 Kylie Prairie\nFoxmouth, MH 34647',
    'text': 'Impact good choose something question production coach.\nAttorney development resource food. Course hear employee wife everyone decide whole machine.',
    'email': 'candace44@example.com',
    'phone_number': '954.396.7373x240',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Rachael Jones',
    'Joseph Keller',
    'Shawn Bennett',
],
    'json': {
    'name': 'Heather Thompson',
    'address': '435 John Land Apt. 997\nWest Elizabeth, WY 17616',
},
    'key73484': 'value73872',
    'key56251': 'value41707',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Marie Williams',
    'address': '1697 Salazar Fields\nWilliamborough, UT 23682',
    'text': 'Fly movement just clearly rest explain open. Raise skin attorney with thus.\nDemocrat condition individual bill laugh population. Pm own large career.',
    'email': 'tyler49@example.com',
    'phone_number': '(429)339-1513',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Annette Edwards',
    'Kimberly Smith',
    'Leroy Sanchez',
    'Gary Chambers',
    'Eric Porter',
    'Michael Reed',
    'Lisa Turner',
    'Patricia Sparks',
],
    'json': {
    'name': 'Mary Costa',
    'address': '90856 Williamson Groves Suite 235\nWest Caleb, UT 78341',
},
    'key19910': 'value13609',
    'key31683': 'value85361',
    'key71113': 'value63650',
    'key20600': 'value11837',
    'key55374': 'value18826',
    'key53943': 'value89986',
    'key28790': 'value92026',
    'key29969': 'value1979',
    'key26759': 'value47828',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Leslie Campbell',
    'address': '043 Cox Street Apt. 544\nStephanieton, ND 43953',
    'text': 'Water fact kind best work similar. Ball fly follow star. Fund positive impact answer series section this everything.\nTheir analysis charge ask back. Store stage fall.',
    'email': 'williamrodriguez@example.org',
    'phone_number': '+1-282-636-0639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Grant',
    'Tamara Cross',
    'Timothy Turner',
    'Kelly Williams',
    'Tiffany Erickson',
    'Mikayla Delacruz',
    'Lance Wong',
    'Cassandra Allen',
],
    'json': {
    'name': 'Patrick Wright',
    'address': '562 Brandy Ferry Apt. 484\nMeghanchester, VT 77588',
},
    'key8483': 'value19252',
    'key64018': 'value9639',
    'key72133': 'value35536',
    'key30093': 'value59008',
    'key61155': 'value60922',
    'key26251': 'value24485',
    'key34499': 'value97828',
    'key93843': 'value30151',
    'key80469': 'value97106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Amanda James',
    'address': '68347 Jessica Rest\nNorth Aaronshire, MA 53992',
    'text': 'Green chair start attorney certainly. Task brother teach fill me cultural everything.',
    'email': 'joe80@example.org',
    'phone_number': '522.581.4637x71565',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Griffin',
    'Tonya Griffith',
    'Andrew Garcia',
    'Erica Clark',
    'Victoria Robertson',
    'Melissa Turner',
],
    'json': {
    'name': 'Tonya Baker',
    'address': '9939 Denise Lodge\nRyanville, AL 55070',
},
    'key65564': 'value94534',
    'key47559': 'value73657',
    'key90340': 'value30609',
    'key82542': 'value88277',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Christopher Bowers',
    'address': '37289 Wagner Road\nDonnabury, CO 63759',
    'text': 'Rule ground game like risk different defense. Charge Republican generation four head position.',
    'email': 'brownryan@example.net',
    'phone_number': '809.641.8682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Johnson',
    'Anthony Charles',
    'Dawn Palmer',
],
    'json': {
    'name': 'Timothy Davenport',
    'address': '79464 Olson Dale\nRaymondfort, VA 47831',
},
    'key90732': 'value77994',
    'key83405': 'value29823',
    'key38400': 'value22309',
    'key90623': 'value47722',
    'key59347': 'value94937',
    'key3966': 'value75404',
    'key45888': 'value23319',
    'key2258': 'value95530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Natalie Clayton',
    'address': '03521 Breanna Meadows Suite 204\nJonesbury, PW 20810',
    'text': 'Then build list current site. Structure opportunity word offer town laugh. Chance his character own. Anything stay teach work resource put.',
    'email': 'bcollins@example.net',
    'phone_number': '(395)438-0837x2634',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brandon James',
    'Morgan Barajas',
    'Anthony Carter',
],
    'json': {
    'name': 'Jeffery Anderson',
    'address': '2875 Heather Forges Suite 270\nPaynefort, SD 07562',
},
    'key17610': 'value40579',
    'key98155': 'value90714',
    'key21489': 'value65498',
    'key20563': 'value66651',
    'key8370': 'value12783',
    'key19591': 'value73024',
    'key61603': 'value7213',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Nicole Perez',
    'address': '776 Corey Cape\nBrownside, FL 68714',
    'text': 'Shake economy factor. Fly rule line worry those find.',
    'email': 'rogersrebecca@example.com',
    'phone_number': '(376)907-8401x34295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brian Saunders',
    'William Gonzalez',
    'Sarah Chavez',
    'Brandon Martin',
    'Stephanie Haas',
    'Joshua Hernandez',
],
    'json': {
    'name': 'Michael Wong',
    'address': 'Unit 5563 Box 4920\nDPO AP 97003',
},
    'key95910': 'value28813',
    'key6785': 'value98725',
    'key31192': 'value38911',
    'key99678': 'value75195',
    'key61966': 'value18529',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Charles Johnson',
    'address': 'USNS Smith\nFPO AA 13802',
    'text': 'Network Republican military might his on. Marriage affect decade receive deal. Detail news point apply.',
    'email': 'jackpugh@example.net',
    'phone_number': '(356)913-7023',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'John Orozco',
    'Dana Paul',
    'Brandi Shaw',
    'Joshua Johnson',
    'Amanda Alexander',
    'David Byrd',
    'Mark Frazier',
    'Sydney Thomas',
    'Kevin Olson',
    'Brooke Brown',
],
    'json': {
    'name': 'Virginia Griffith DVM',
    'address': '9463 Orr Land\nPort Mary, VT 51007',
},
    'key92259': 'value28613',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jeremy Diaz',
    'address': '52634 Wise Camp\nSouth John, SD 69868',
    'text': 'Citizen physical heart use third. Side maybe idea total.\nDuring interesting wish. He action key high pretty special election. Machine hour be value network short.',
    'email': 'ascott@example.com',
    'phone_number': '+1-819-560-3534x210',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brandy Sharp',
    'Robert Jones',
],
    'json': {
    'name': 'Roberto Andrews',
    'address': 'USNV Mcbride\nFPO AA 47331',
},
    'key49736': 'value78081',
    'key27741': 'value39993',
    'key24192': 'value20644',
    'key47462': 'value80181',
    'key17326': 'value20454',
    'key52048': 'value47466',
    'key51596': 'value17268',
    'key11840': 'value82569',
    'key29510': 'value7047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Patricia Mcdonald',
    'address': '0959 Banks Route Apt. 999\nSouth Zachary, NE 67416',
    'text': 'Everybody thought leg design will politics camera. Any candidate attention visit rise picture. Mrs defense win couple.\nWatch threat at receive.',
    'email': 'williamjohnson@example.net',
    'phone_number': '607-412-1516x70403',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Mckee',
    'Mr. Ryan Walton',
    'Carlos Mills',
    'Tina Moore',
    'Christine May',
    'Natasha Butler',
],
    'json': {
    'name': 'Timothy Madden',
    'address': '3501 Laura Roads\nEast Gary, MH 81911',
},
    'key3253': 'value28132',
    'key10125': 'value8021',
    'key20341': 'value85387',
    'key19241': 'value68144',
    'key89121': 'value20126',
    'key65405': 'value27035',
    'key72487': 'value62658',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'John Wu',
    'address': '66340 Amber Lodge\nJordanmouth, MS 86718',
    'text': 'Mention law where interesting. Collection door him level.\nExpert know window. Son yes poor fact least mean grow.\nWhom window trip. Both hour measure recognize participant instead.',
    'email': 'torreskim@example.com',
    'phone_number': '205-994-6837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Hawkins',
    'Christian Phelps',
    'Nancy Jones',
    'Christine Huff',
    'Lynn Duncan',
],
    'json': {
    'name': 'Adam Gray',
    'address': '0557 Aaron Turnpike Apt. 109\nCastanedaborough, NY 07388',
},
    'key69013': 'value15874',
    'key6602': 'value26587',
    'key81844': 'value77450',
    'key32629': 'value66560',
    'key23300': 'value55771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Jennifer Fox',
    'address': '32178 Patricia Pines Suite 379\nEast Bryan, NJ 27506',
    'text': 'Kid figure skill institution score present. Question above get mind language truth. Himself well baby concern skin.\nDraw data analysis home subject himself.',
    'email': 'fhansen@example.com',
    'phone_number': '566-461-7812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Frank',
    'Sharon Davies',
],
    'json': {
    'name': 'Thomas Thompson',
    'address': '37630 Mueller Ridges\nPort Chad, WI 75059',
},
    'key9472': 'value516',
    'key86232': 'value65297',
    'key10454': 'value17894',
    'key96853': 'value70952',
    'key37511': 'value2198',
    'key12680': 'value35816',
    'key52277': 'value61281',
    'key12227': 'value63735',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Donald Wall',
    'address': '814 Timothy Square\nEast Angelashire, NE 12693',
    'text': 'Focus bad step the strong rich product. Seem support move. Human home significant. Nice and nor themselves research start.',
    'email': 'echoi@example.org',
    'phone_number': '822-767-4469x849',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Moss',
    'Bonnie Miller',
    'Heather Anderson',
    'Kathryn Williams',
    'Theresa Thomas',
    'Natasha Mejia',
],
    'json': {
    'name': 'Taylor Weber',
    'address': '07657 Roberts Expressway\nWest Adam, SC 11600',
},
    'key33006': 'value49373',
    'key89003': 'value67446',
    'key41789': 'value53051',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Anne Anderson',
    'address': 'PSC 6133, Box 1704\nAPO AP 21109',
    'text': 'Environment capital including total million something. Wide marriage similar black themselves. How effort rest my prepare. Treat contain check ability thing.',
    'email': 'bradley73@example.net',
    'phone_number': '251-430-9681x6968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Jackson',
    'Jeffrey Schroeder Jr.',
    'Yolanda Robinson',
    'Tiffany Ward',
    'Brandon Harrington',
    'Brandon Cannon',
    'Samantha Jones',
    'Victoria Lopez',
    'Ashley Matthews',
],
    'json': {
    'name': 'Fernando Spencer',
    'address': '553 Alisha Ferry Apt. 434\nNorth Erikhaven, MP 05579',
},
    'key99636': 'value98072',
    'key31652': 'value8654',
    'key84346': 'value38173',
    'key9489': 'value30171',
    'key94999': 'value63962',
    'key40469': 'value28942',
    'key27988': 'value67498',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Tyler Martinez',
    'address': '92958 Jones Roads Apt. 477\nKylemouth, IL 43531',
    'text': 'Church reality behind range industry trouble. Son hot water gas nice whether suddenly. Window effort education necessary final agree stop.',
    'email': 'cynthiajones@example.org',
    'phone_number': '+1-773-765-0201x810',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Mcbride',
    'Carol Davis',
    'Sarah Brown',
    'Amy Black',
    'Patrick Moore',
],
    'json': {
    'name': 'Alexander Webb',
    'address': '734 Kaitlyn Point\nNorth Monica, ID 49670',
},
    'key4834': 'value52336',
    'key3692': 'value53150',
    'key59856': 'value29127',
    'key90917': 'value91420',
    'key34968': 'value53712',
    'key9277': 'value1207',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Jacob Barrera',
    'address': '593 Weaver Plaza\nKristenside, MT 59810',
    'text': 'Everything opportunity upon. End stand home nearly add raise manage beautiful. Lose now one.',
    'email': 'jharvey@example.com',
    'phone_number': '+1-858-747-2250x41213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Beltran',
    'Nancy Bryant',
    'Joseph Baker',
    'Heather Porter',
    'Mary Friedman',
    'Cheryl Turner',
    'Brandon Barnes',
    'James Sherman',
],
    'json': {
    'name': 'Leslie Mathis',
    'address': '3499 Tucker Trafficway Suite 190\nEast Sarahhaven, WI 14476',
},
    'key85750': 'value49223',
    'key52012': 'value65515',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Natalie Krueger',
    'address': '8272 Joseph Place\nSouth Roberthaven, MP 32730',
    'text': 'Near performance middle administration change design main. Join side could specific.',
    'email': 'howens@example.net',
    'phone_number': '355-385-3690x515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Williams',
    'Melanie Larson',
    'Nathan Jackson',
],
    'json': {
    'name': 'Rachel Ray',
    'address': '8503 Anderson Course Suite 548\nNancyborough, NM 57008',
},
    'key3694': 'value30583',
    'key61074': 'value32524',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'David Jefferson MD',
    'address': '9289 Swanson Mountain Apt. 614\nGreenland, NV 95282',
    'text': 'Pull box exist option nothing society need blue. Growth fire argue.\nI thus suddenly eye coach less appear. See others pattern. Bank capital young occur foot church popular.',
    'email': 'norrisdaniel@example.org',
    'phone_number': '(996)883-5937',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Matthew White',
    'James Robinson',
    'Susan Rice',
    'Caitlin Mccoy',
    'Sydney Mendoza',
],
    'json': {
    'name': 'Kim Rodriguez',
    'address': '864 Robert Camp\nBruceville, NE 10458',
},
    'key58068': 'value68069',
    'key21264': 'value18602',
    'key75650': 'value62400',
    'key39490': 'value76295',
    'key62904': 'value3742',
    'key70962': 'value22352',
    'key64138': 'value91937',
    'key23643': 'value80002',
    'key76189': 'value66051',
    'key27867': 'value35141',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'John Roberts',
    'address': '4550 Johnson Prairie Suite 551\nWest Chelsea, MT 74968',
    'text': 'Suffer letter class example official financial hit. Western case someone bed. Son affect prove just pay your.\nHistory star research. Structure agreement statement fast should.',
    'email': 'bowmanchristopher@example.com',
    'phone_number': '(939)429-3305x73171',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Denise Johnson',
    'Rebecca Hoover',
    'Daniel Perez',
    'Dawn Sutton',
    'Elizabeth Webb',
    'Andrew Cunningham',
    'Joseph Carter',
    'Valerie Moore',
],
    'json': {
    'name': 'Rebekah Blevins',
    'address': 'Unit 7127 Box 6546\nDPO AE 17522',
},
    'key80424': 'value66270',
    'key97053': 'value69461',
    'key28543': 'value99153',
    'key74107': 'value37999',
    'key76454': 'value56785',
    'key17581': 'value98884',
    'key88448': 'value52967',
    'key31531': 'value60874',
    'key87412': 'value40151',
    'key43536': 'value64709',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Sabrina Stone',
    'address': '11244 Torres Expressway\nHeathertown, DE 46410',
    'text': 'Act realize these down because. Just owner see perform space yet particular computer.\nWorry single price her statement. Turn hour last organization draw learn according.',
    'email': 'mcmahonryan@example.net',
    'phone_number': '(411)216-4666x9221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Sellers',
    'Ms. Rebekah Myers',
    'Gina Hernandez',
    'Dawn Adams',
    'Michael Flowers',
    'Eric Lewis',
],
    'json': {
    'name': 'Melissa Fields',
    'address': '46270 Matthew Mount\nPort Derek, LA 45745',
},
    'key27306': 'value88483',
    'key39156': 'value57378',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Tammy Ball',
    'address': '058 Williams Gateway Apt. 451\nBartlettmouth, LA 25304',
    'text': 'He very know evening official. Car eight college course small hold a.\nFly trade any ready outside. Authority between ready maintain.',
    'email': 'vernon13@example.com',
    'phone_number': '723-218-4230x8189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Patterson',
],
    'json': {
    'name': 'Joseph Wells',
    'address': '7887 Angela Loop\nPort Kevin, UT 73320',
},
    'key24162': 'value35565',
    'key33123': 'value72968',
    'key19718': 'value28829',
    'key76966': 'value64512',
    'key64469': 'value21897',
    'key67200': 'value50399',
    'key65235': 'value79755',
    'key59452': 'value37200',
    'key30902': 'value53537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Luke Henry',
    'address': '3307 Ricky Neck\nKarichester, MD 74664',
    'text': 'Customer story me executive blue sound. Writer exist same study. Many nothing space PM. Agree amount you beautiful future.',
    'email': 'jamesfrazier@example.com',
    'phone_number': '378-255-9227',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Russell Wagner',
    'Sara Mason',
    'Zachary Wells',
],
    'json': {
    'name': 'Maria Hoover',
    'address': '44401 Thomas Forest\nMillerhaven, VT 26137',
},
    'key87811': 'value63598',
    'key86861': 'value44895',
    'key79403': 'value98950',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Kristopher Contreras',
    'address': '745 Andrews Prairie Apt. 720\nRichardton, FL 45016',
    'text': 'Stuff place generation federal everyone success suggest. Purpose price true black box.\nWhat man issue sure cover. What phone few life live.',
    'email': 'robert75@example.net',
    'phone_number': '2689433497',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Butler',
    'Thomas Walker',
    'Frank Ballard',
    'Kristen Anderson',
    'Joshua Moore',
    'Adrian Taylor',
    'Christina Reynolds',
    'Louis Warren',
    'Angela Turner',
    'Tina Aguilar',
],
    'json': {
    'name': 'Sara Harrison',
    'address': 'USCGC Smith\nFPO AA 42639',
},
    'key40508': 'value36198',
    'key42070': 'value1500',
    'key34436': 'value50433',
    'key63884': 'value30042',
    'key84075': 'value96272',
    'key29077': 'value47363',
    'key72313': 'value27903',
    'key78568': 'value14648',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Charles Howe',
    'address': '2955 Ashley Highway\nPort Jay, PW 19217',
    'text': 'Accept sea thought together radio opportunity or. Wrong upon parent chair apply nation. Let provide today treatment.',
    'email': 'perezerin@example.org',
    'phone_number': '255-542-3796x68485',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Shari English',
    'Traci Strong',
    'Tamara Thomas',
    'Timothy Hammond',
    'Rick Pearson',
    'Loretta Wright',
    'Juan Smith',
],
    'json': {
    'name': 'Matthew Foley',
    'address': '8212 Henry Isle Apt. 122\nLake Mathewside, GU 83028',
},
    'key73570': 'value18550',
    'key48223': 'value27628',
    'key48002': 'value36546',
    'key87988': 'value75273',
    'key51563': 'value8470',
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
    'RequestId': '773a32c3-62ef-11f0-b8cc-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_47_549259LwfZBbPh',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-2]_1752744109.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId12810021752744109Json()
    test.run_tests()
