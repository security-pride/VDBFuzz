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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_0]_1752744819_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_0]_1752744819.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid001752744819Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_0]_1752744819.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_0]_1752744819.json"
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
    'RequestId': '181e487c-62f1-11f0-ae4f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_26_976235IPCmUgIj',
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
    'RequestId': '1b3d5b38-62f1-11f0-abd2-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_26_976235IPCmUgIj',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Amy Miller',
    'address': '117 Annette Mews Suite 407\nWest Wyattmouth, MD 35028',
    'text': 'Theory actually development lot organization former either. End but forward society north pattern. Since table find develop.\nChoose public fight admit than. Street skin himself peace.',
    'email': 'dcollins@example.net',
    'phone_number': '(795)617-2163',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Lindsey',
    'David Kelly',
    'Ashley Webb',
    'Phillip Quinn',
    'Tina George',
    'Maria Crawford',
    'Ruben Best',
],
    'json': {
    'name': 'Michael Ross',
    'address': '935 Leslie Ways Apt. 530\nWest Julia, NH 68224',
},
    'key28965': 'value79506',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Kevin Mclaughlin',
    'address': '67110 Barbara Overpass\nLucasview, VT 62916',
    'text': 'Thing production particular oil word tonight play. American Democrat reality note.\nMinute follow require last campaign role teacher unit. Reduce voice everything send.',
    'email': 'shorttyrone@example.com',
    'phone_number': '(251)878-4925x3852',
    'array_int_dynamic': [
    93130,
],
    'array_varchar_dynamic': [
    'Jose Simon',
    'Michael Smith',
    'Erika Fernandez',
    'Mr. Ricardo Davis',
    'Cody Love',
],
    'json': {
    'name': 'Hayden Williams Jr.',
    'address': '4068 Allison Islands\nEspinozahaven, NC 42989',
},
    'key31517': 'value46838',
    'key87508': 'value64999',
    'key18319': 'value15236',
    'key15872': 'value94731',
    'key3550': 'value49084',
    'key34895': 'value6543',
    'key25133': 'value29135',
    'key96467': 'value16666',
    'key33171': 'value8884',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Maria James',
    'address': '4299 Sharon Gateway Suite 570\nGarnerton, AK 55231',
    'text': 'Thing mother answer car evidence. Success success still exist stand.\nTest be hope body play upon. Wife management weight recognize. Against training check home.',
    'email': 'gonzalezbrady@example.org',
    'phone_number': '869.858.1501x93029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Decker',
    'Anthony Schultz',
    'Heather Duffy',
    'Timothy Lam',
    'Dawn Hammond',
    'Steven Lewis',
    'Christopher Armstrong',
    'Kyle Rodriguez',
],
    'json': {
    'name': 'Colleen Taylor',
    'address': '47168 Holly Square Apt. 177\nNew Stephanieborough, DC 27726',
},
    'key86493': 'value28489',
    'key67706': 'value54343',
    'key37455': 'value11916',
    'key95446': 'value11763',
    'key24014': 'value50375',
    'key65994': 'value4332',
    'key70334': 'value10824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Meredith Ray',
    'address': '338 Amanda Springs Suite 435\nEast Alan, NJ 44216',
    'text': 'Talk air like similar daughter. Feeling theory difficult camera top huge. Collection run far.\nThat still born since cold manage western. Vote this coach nearly.',
    'email': 'aleon@example.org',
    'phone_number': '835-528-8119x97097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Pena',
    'Tracy Carson',
    'Kelly Gray',
    'Dwayne Goodman',
    'Katherine Weaver',
    'Melinda Stanley',
    'William Padilla',
    'Diane Garcia',
    'Alyssa Foster',
],
    'json': {
    'name': 'Donna Thomas',
    'address': '23935 Gary Plaza\nWest William, LA 22019',
},
    'key6382': 'value23294',
    'key39737': 'value96951',
    'key68829': 'value52381',
    'key85536': 'value76513',
    'key84211': 'value2158',
    'key85076': 'value14410',
    'key4967': 'value75553',
    'key26659': 'value1399',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Brianna Callahan',
    'address': '3309 Robert Junctions Suite 239\nChambersfurt, UT 14466',
    'text': 'Despite hotel before product. Democratic son project sense defense ask medical. Spend order radio bag man house.\nBack method claim school. Night especially according brother.',
    'email': 'jason35@example.org',
    'phone_number': '+1-623-656-0797',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Woods',
    'Kimberly Silva',
    'Patricia Chen',
],
    'json': {
    'name': 'Brenda Davis',
    'address': '51809 Amanda Vista\nRandallfurt, GU 09651',
},
    'key81244': 'value50552',
    'key79037': 'value97232',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Mary Dixon',
    'address': '4068 Harris Club Apt. 023\nSheltonmouth, CA 78550',
    'text': 'Recent game study media should others control. Fact husband strategy light without detail choice. Fact up oil direction return.',
    'email': 'allenmichael@example.com',
    'phone_number': '(721)275-2938x385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Phillip Davis',
],
    'json': {
    'name': 'Sharon Wise',
    'address': 'USS Logan\nFPO AE 99197',
},
    'key64416': 'value25426',
    'key42012': 'value41970',
    'key97651': 'value15808',
    'key95147': 'value53193',
    'key76385': 'value97251',
    'key89531': 'value81177',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Donald Hansen',
    'address': '395 Dawson Squares Suite 993\nDavidmouth, MD 67962',
    'text': 'Keep town pay require cultural hospital. Community find attorney scene long happen. Ready painting stage growth involve. Important surface safe act establish how.',
    'email': 'danielturner@example.com',
    'phone_number': '001-601-901-0807x09870',
    'array_int_dynamic': [
    17970,
],
    'array_varchar_dynamic': [
    'Jeffrey Cunningham',
    'Daniel Young',
    'Christopher Barnes',
    'Penny Contreras',
    'David Rodriguez',
    'Michelle Knight',
    'Kristin Owens',
    'Jessica Thomas',
],
    'json': {
    'name': 'Christine Smith',
    'address': '4609 Thomas Pine Apt. 753\nEast Deborahport, NE 92253',
},
    'key56646': 'value87171',
    'key18587': 'value80792',
    'key66926': 'value79176',
    'key32933': 'value55801',
    'key83081': 'value37703',
    'key2836': 'value32628',
    'key73795': 'value90509',
    'key39649': 'value28738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jennifer Schultz',
    'address': '3794 Fitzgerald Shores\nKeithstad, KS 95735',
    'text': 'Impact suddenly cut cup parent. Town management dog. Cultural over miss idea. Audience radio card answer poor American mother.',
    'email': 'christopher41@example.com',
    'phone_number': '408-883-2355x246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Williams',
    'Kimberly Hawkins',
    'Amy Alvarado',
    'Brian Moore',
],
    'json': {
    'name': 'James Kent',
    'address': '34235 Galvan Summit\nNorth Sabrina, GU 23422',
},
    'key21201': 'value22491',
    'key49408': 'value38589',
    'key29363': 'value62882',
    'key36273': 'value35540',
    'key23256': 'value70678',
    'key17285': 'value16690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Dr. Wendy Beasley',
    'address': '0907 Sally Trail\nAngelabury, KY 24393',
    'text': 'Section particularly today decade while ready window. Heart mean how consumer enter miss within. Generation window black explain forward doctor.\nOpen son who require. That that leader product.',
    'email': 'rrobinson@example.com',
    'phone_number': '001-281-436-1632x551',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Keith',
    'Tamara Mack',
    'William Lewis Jr.',
    'Corey Watkins',
    'Christopher Walter',
    'Evan Byrd',
    'Holly Waller',
],
    'json': {
    'name': 'Daniel Miller',
    'address': '360 Holmes Meadow\nWarrenborough, PA 05183',
},
    'key76564': 'value98743',
    'key36423': 'value31022',
    'key28012': 'value16654',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Connie Rodriguez',
    'address': '1346 Noah Court\nSouth Andrewfurt, WI 47563',
    'text': 'Color lawyer fact one billion both rather. Research drug pick building animal place. Major center say.\nImportant long ready however.',
    'email': 'monicarodriguez@example.com',
    'phone_number': '339.928.8193x54380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Savannah Alexander',
    'Kimberly Ward',
    'Yolanda Spears',
],
    'json': {
    'name': 'David Russell',
    'address': 'USS Cohen\nFPO AA 13798',
},
    'key79198': 'value27410',
    'key5537': 'value88562',
    'key9160': 'value73743',
    'key74964': 'value52861',
    'key96959': 'value7772',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Linda Evans',
    'address': '8096 Small Villages Suite 747\nSouth Brittany, IA 47678',
    'text': 'Case inside teach say style ok. Important test bed ready. Myself manage society long.',
    'email': 'anthonywagner@example.net',
    'phone_number': '001-492-291-7300',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Larry Stanley',
    'Amanda Rodriguez',
    'Kristine Andrews',
    'John Hill',
    'Amy Walker',
],
    'json': {
    'name': 'Lori Green',
    'address': '441 Wilson Mill\nNorth Roy, MH 02097',
},
    'key58290': 'value67078',
    'key38424': 'value53730',
    'key52648': 'value83697',
    'key95259': 'value96277',
    'key88755': 'value90988',
    'key67540': 'value77793',
    'key29243': 'value57735',
    'key41804': 'value89381',
    'key72200': 'value63945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Jennifer Cooper',
    'address': '1257 Shawn Square\nWoodardhaven, HI 80347',
    'text': 'Involve he know not himself. Treat wonder which water. Somebody budget at performance pass couple teach.\nBelieve different rise front thank.',
    'email': 'zhernandez@example.com',
    'phone_number': '+1-315-892-4084x21650',
    'array_int_dynamic': [
    87579,
],
    'array_varchar_dynamic': [
    'Jeremy Clements',
    'Melissa Pittman',
    'Susan Frazier',
    'Jessica Smith',
    'Kenneth Curtis',
    'Karen Cochran',
    'Alyssa Lewis',
    'Rebecca King',
    'Dustin Scott',
    'Carolyn Lopez',
],
    'json': {
    'name': 'Stephanie Odonnell',
    'address': '5414 Brittany Lodge\nEast Thomas, HI 77798',
},
    'key48849': 'value20801',
    'key53741': 'value92214',
    'key22758': 'value8134',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Natalie White',
    'address': '401 Diaz Heights\nDanielfort, ND 58264',
    'text': 'Fish left black concern official likely serious. Everyone fine reason continue region. Whom plan part man determine want.\nList bring who like local road pass.',
    'email': 'kimberlymullen@example.net',
    'phone_number': '(382)617-2079x43181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Mitchell',
    'Tricia Davis',
    'John Avery',
    'Shawn Moreno',
    'Jeff Ortiz',
],
    'json': {
    'name': 'Mary Miller',
    'address': '555 Jerry Creek\nWarnerside, CA 06633',
},
    'key74897': 'value23436',
    'key97536': 'value39641',
    'key73358': 'value79447',
    'key38282': 'value15735',
    'key14494': 'value57046',
    'key34886': 'value27362',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Tammy Dorsey',
    'address': '61645 Crystal Harbor\nNoahview, LA 50936',
    'text': 'Fine agreement piece reason they. Administration have present.\nColor respond here. Right wide institution apply develop film forward. Under and evening cup live heart.',
    'email': 'robertsjessica@example.org',
    'phone_number': '704.483.3120',
    'array_int_dynamic': [
    12255,
],
    'array_varchar_dynamic': [
    'Dillon Trujillo',
    'Stacy Gonzales',
    'Briana Patel',
    'Aaron Prince',
    'Mark Smith',
],
    'json': {
    'name': 'Joe Choi',
    'address': '94300 Hicks Court\nHernandezshire, KY 72955',
},
    'key94626': 'value9011',
    'key18877': 'value64774',
    'key76808': 'value80989',
    'key87006': 'value83904',
    'key46408': 'value95710',
    'key63697': 'value45693',
    'key84320': 'value75899',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Tami Walters',
    'address': '6012 Heath Meadow Suite 151\nJasonmouth, WA 65248',
    'text': 'Spring him city represent describe others. Company coach computer sense leader fight push. Whole why yet those finish challenge decide.\nTv between race pattern one. Evening type special road.',
    'email': 'smithtiffany@example.com',
    'phone_number': '001-393-838-9103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Escobar',
    'Chad Morgan',
],
    'json': {
    'name': 'Michelle Daniels',
    'address': '7427 Atkinson Trace\nAdamsshire, NM 11220',
},
    'key78821': 'value14717',
    'key61380': 'value76887',
    'key71439': 'value14468',
    'key47278': 'value68636',
    'key73400': 'value64114',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'David Lane',
    'address': '510 Andrea Key Suite 508\nEast Lindsaymouth, SC 05024',
    'text': 'Education nothing contain student just. Move act bag clearly father skin world.\nOrganization save professor force outside under.\nExist result strong according. This serve white still local term.',
    'email': 'maldonadocrystal@example.net',
    'phone_number': '+1-880-754-7568x733',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'William Graham',
],
    'json': {
    'name': 'Samantha Walker',
    'address': '8061 Ramos Land Apt. 204\nBridgesside, SD 13353',
},
    'key55608': 'value95813',
    'key72517': 'value46124',
    'key57030': 'value68881',
    'key79804': 'value12715',
    'key37330': 'value24487',
    'key66578': 'value72698',
    'key71053': 'value60386',
    'key44320': 'value9116',
    'key95116': 'value39536',
    'key15318': 'value32356',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Nicholas Levy',
    'address': '56942 Jeffrey Light\nElizabethfort, SC 62210',
    'text': 'Common hard trouble. Discuss laugh green material such bar design. Coach difference tough camera.\nLife spend perform media yeah career evening. Page foreign purpose why significant whole town impact.',
    'email': 'pduncan@example.com',
    'phone_number': '(520)411-2021',
    'array_int_dynamic': [
    34671,
],
    'array_varchar_dynamic': [
    'Michael Hernandez',
    'Catherine Turner',
    'Samantha Wheeler',
],
    'json': {
    'name': 'Larry Dean',
    'address': '0219 Schmidt Locks\nWest Kellyburgh, OK 67567',
},
    'key47110': 'value85461',
    'key22467': 'value88767',
    'key10866': 'value12853',
    'key5091': 'value21654',
    'key17834': 'value53215',
    'key61364': 'value82854',
    'key50734': 'value91412',
    'key12689': 'value98339',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Sally Martin',
    'address': '695 White Corner\nWest Anthonytown, NM 42587',
    'text': 'We up day represent individual drive. Experience notice page consumer. Physical condition site its. Follow suffer coach since third white on.',
    'email': 'mclaughlintracy@example.net',
    'phone_number': '(807)699-5219x246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Franklin',
    'Heather Peterson',
    'Jose Henry',
    'Mr. Ian Johnson Jr.',
    'Alyssa Richardson',
    'Dean Hernandez',
    'Jeffrey Walker',
    'Brittney Cobb',
],
    'json': {
    'name': 'Rachel Nash',
    'address': '8272 Johnson Meadow\nAnthonyview, WY 81788',
},
    'key38040': 'value61044',
    'key12243': 'value9557',
    'key16717': 'value56808',
    'key25090': 'value70657',
    'key28563': 'value35790',
    'key1820': 'value69015',
    'key88057': 'value66537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Dustin Wilson',
    'address': '1969 Michelle Knolls Suite 737\nBallardmouth, DC 38372',
    'text': 'Local hear very I fall book purpose PM. Receive position like. Media big short yes word this.',
    'email': 'zweaver@example.net',
    'phone_number': '+1-708-472-0988x97981',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mary Aguirre',
    'Amy Dillon',
    'Andrew Benson',
    'Dalton Garrison',
    'Deanna Lee MD',
    'Melinda Fisher',
    'Elizabeth Wilson',
    'Theodore Lopez',
    'Kenneth Garcia',
],
    'json': {
    'name': 'John Shaw',
    'address': '33377 Ortiz Spur\nRiosmouth, ND 68747',
},
    'key8184': 'value24716',
    'key72496': 'value27770',
    'key35850': 'value71713',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Mary Wright',
    'address': '91871 Rebecca Tunnel\nSouth Michaelport, LA 31437',
    'text': 'This rock degree factor fear reason structure. Bed blood it along receive chair. Research authority garden us. But or whole line accept speak area.',
    'email': 'gloveryvonne@example.org',
    'phone_number': '404.667.2339',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Johnson',
    'Eric Gibbs',
    'William Bowers',
    'Timothy Hughes',
    'Lauren Graham',
    'Morgan Bradley',
],
    'json': {
    'name': 'Angela Mathews',
    'address': '6457 Bowen Oval\nLake Austinland, MO 67978',
},
    'key50850': 'value18728',
    'key54070': 'value48959',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Belinda Williamson',
    'address': '0229 Shannon Rue\nMichaelport, NC 13367',
    'text': 'History rise take political week guy. Level computer computer season shoulder.\nModern imagine can practice down responsibility.\nFeel black few writer fly. Practice plant and cultural he.',
    'email': 'josephdean@example.net',
    'phone_number': '+1-409-895-3066x266',
    'array_int_dynamic': [
    64439,
],
    'array_varchar_dynamic': [
    'Wendy Nguyen',
    'Tammy Stewart',
    'Joseph Patterson',
    'Yvonne Bryant',
    'Michael King',
    'Amanda Poole',
],
    'json': {
    'name': 'Stephanie Williamson',
    'address': '006 Andrew Ports\nNew Nicoletown, MA 33445',
},
    'key22107': 'value24593',
    'key90148': 'value3392',
    'key38700': 'value26707',
    'key38872': 'value17167',
    'key90355': 'value44889',
    'key45958': 'value85463',
    'key93477': 'value12305',
    'key82613': 'value37676',
    'key37668': 'value3257',
    'key4886': 'value40292',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Rebecca Williams',
    'address': '6341 David Lodge Apt. 792\nNorth David, ID 29293',
    'text': 'Reality media four see cover agreement marriage. Significant individual trial necessary late enjoy.\nNecessary walk pretty where result miss difficult. Paper natural type reality.',
    'email': 'stacywade@example.org',
    'phone_number': '632.618.3258',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amy Mooney',
],
    'json': {
    'name': 'Tanya Sullivan',
    'address': '299 Patricia Garden\nSouth Jennifer, NE 26138',
},
    'key41651': 'value45679',
    'key52001': 'value35961',
    'key21817': 'value14534',
    'key49665': 'value8307',
    'key46457': 'value43175',
    'key6115': 'value45876',
    'key61213': 'value4395',
    'key87557': 'value95977',
    'key51034': 'value36028',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Natalie Estes',
    'address': '7118 Patricia Rapid Suite 029\nSusanstad, PR 49027',
    'text': 'Sea investment knowledge begin stop doctor notice. Alone every discussion industry become authority. Senior movement ahead realize. Then many her hot account later.',
    'email': 'flemingandrew@example.com',
    'phone_number': '001-579-700-1495x556',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Vernon Harris',
    'Jo Newton',
    'Terry Sanchez',
    'Joel Sandoval',
    'Michael Acosta',
],
    'json': {
    'name': 'Ashley Williams MD',
    'address': '130 White Manor\nPort Garyburgh, ID 99288',
},
    'key50031': 'value73754',
    'key77791': 'value61124',
    'key59115': 'value40359',
    'key1338': 'value58467',
    'key14219': 'value26970',
    'key13490': 'value50212',
    'key5780': 'value46623',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Rebecca Mills',
    'address': '192 Thomas Manors Apt. 762\nLake Annview, OK 94443',
    'text': 'Eat finish scene owner evidence. Allow able since meeting as. Tend need add friend.\nSay service wrong us floor.',
    'email': 'williamcastillo@example.net',
    'phone_number': '(256)443-1530x4346',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Johnson',
    'Christopher Williams',
],
    'json': {
    'name': 'Dr. Todd Herrera',
    'address': '85302 Smith Trail Apt. 740\nLake Brendachester, PA 01732',
},
    'key55483': 'value79053',
    'key52028': 'value75982',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Derrick Sheppard',
    'address': '7177 Rivera Road Suite 782\nWilliamton, FL 91777',
    'text': 'Visit plan best stop character resource majority. Type back old never. Cause stand since building Mr job.',
    'email': 'staceyallen@example.net',
    'phone_number': '479-679-6716x68051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Combs',
],
    'json': {
    'name': 'Amy Brown',
    'address': '921 Valdez Hill Apt. 683\nMonicafurt, ID 98068',
},
    'key65818': 'value9530',
    'key78010': 'value89023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Timothy Vega',
    'address': '0561 Miles Squares\nNorth Debra, PW 69479',
    'text': 'Company pick seek resource. Sport education discover clear hit election. Gas court structure service contain political.',
    'email': 'gburke@example.org',
    'phone_number': '308.239.6411x2319',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jason Mathis',
    'Michael Green',
    'Jessica Houston',
    'Matthew Hill',
    'Samantha Sanchez',
    'David King',
    'Joseph Strickland',
    'Sarah Edwards',
],
    'json': {
    'name': 'Crystal Reed',
    'address': '9230 Cody Ports\nLisastad, AK 38953',
},
    'key94428': 'value97538',
    'key42580': 'value86978',
    'key2044': 'value93356',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Gary Spencer',
    'address': '617 Peterson Shoal\nRodriguezfurt, LA 49311',
    'text': 'Fight magazine loss issue because. Number who century war me marriage catch. Sister keep high two.',
    'email': 'teresagoodman@example.org',
    'phone_number': '(911)201-2966x2768',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Massey',
    'Dwayne Garcia',
    'Christopher Brown',
    'James Harris',
    'Morgan Stevens',
    'Christopher Turner',
    'Melinda Joseph',
    'Brittany Evans',
],
    'json': {
    'name': 'Julie Stewart',
    'address': '7105 Mark Heights Apt. 663\nPort Jaredshire, NY 56946',
},
    'key98506': 'value68122',
    'key98598': 'value44356',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jonathon Drake',
    'address': '898 Miller Road\nNorth Brandonville, OH 96784',
    'text': 'Company summer but along create east. Body wear return no suggest.\nPolitical hospital maybe must moment board oil. Owner woman up. Figure center reach talk however movie democratic.',
    'email': 'qramirez@example.net',
    'phone_number': '7182927413',
    'array_int_dynamic': [
    78571,
],
    'array_varchar_dynamic': [
    'Jason Shah',
    'Christopher Hart',
],
    'json': {
    'name': 'Dr. Jeremy Bowers',
    'address': '83449 Jones Springs\nAprilmouth, UT 12171',
},
    'key47994': 'value25906',
    'key98482': 'value49521',
    'key66303': 'value14327',
    'key68118': 'value71333',
    'key91859': 'value13252',
    'key62659': 'value99088',
    'key45894': 'value42920',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Juan Barr',
    'address': '0560 Ruben Canyon\nMitchellberg, LA 62685',
    'text': 'Much score pick feel paper quite. Air whole dark what trade.\nCompany even culture record. Start foot factor fast throw hit.',
    'email': 'johnmay@example.net',
    'phone_number': '+1-962-383-4008x325',
    'array_int_dynamic': [
    45331,
],
    'array_varchar_dynamic': [
    'Rebecca Sanchez',
    'Daniel Stark',
    'Russell Henry',
    'Jeremy Sanchez',
    'Randy Ramos',
    'David Hernandez',
    'Michael Hurley',
    'Alejandro Porter',
    'Wesley Hendricks',
],
    'json': {
    'name': 'Angela Mack',
    'address': '192 Hughes Harbors\nNew Calvin, HI 36523',
},
    'key60226': 'value47971',
    'key78548': 'value75516',
    'key57844': 'value3194',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Larry Ross',
    'address': '49957 Martin Knoll Suite 730\nMartinezbury, ID 60997',
    'text': 'Job use collection meeting specific rather.\nOccur around white city resource enter fire. Reveal what level front bar you. Again up time camera evening oil east.',
    'email': 'tnelson@example.net',
    'phone_number': '544-950-1020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Strong',
    'Ms. Jodi Robinson',
    'Jimmy Schneider',
    'Bernard Munoz',
    'Kimberly Jackson',
    'Jonathan Potter',
],
    'json': {
    'name': 'Aaron Jones',
    'address': '463 Lawrence Port\nShawtown, NC 37542',
},
    'key77997': 'value88567',
    'key21769': 'value23041',
    'key85135': 'value84001',
    'key31912': 'value49346',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Charles Maldonado',
    'address': '657 Michael Oval\nTaylorshire, MA 03286',
    'text': 'Gun loss natural herself act although court. Action begin expect.\nPresent near but sometimes evidence face. Western let understand deal else cell.',
    'email': 'travissteven@example.com',
    'phone_number': '930-582-5219',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Carter',
    'Douglas Carter',
    'Jeffrey Bailey',
    'Steven Montgomery',
    'Peter Davis',
    'Yvette Gray',
    'Melissa Arroyo',
],
    'json': {
    'name': 'Jennifer Nelson',
    'address': '9072 Erica Divide\nWeberburgh, PR 99316',
},
    'key44880': 'value54874',
    'key78909': 'value87228',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Kayla Benson',
    'address': '2439 Jennifer Orchard\nPetersonborough, NJ 51593',
    'text': 'Audience prepare step rest my southern worker. Ask sound decide threat respond performance. Million exist word air born one call floor.',
    'email': 'danieldecker@example.com',
    'phone_number': '750.480.0276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mark Larson',
    'Alejandra Chavez',
    'Michael Hudson',
    'Greg Rowe',
    'James Bass',
    'Ashley Watts',
    'Kayla Wilkerson',
    'Rebecca Tucker',
    'Jesse Anderson',
    'Scott Johnson Jr.',
],
    'json': {
    'name': 'Jason White',
    'address': '12952 Timothy Tunnel\nNorristown, AK 16250',
},
    'key59942': 'value40702',
    'key15258': 'value33575',
    'key16103': 'value93878',
    'key78388': 'value2185',
    'key48904': 'value42259',
    'key88672': 'value80697',
    'key30470': 'value98902',
    'key86202': 'value37872',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Susan Collins',
    'address': '153 Erika Mill\nAlexanderland, KY 28136',
    'text': 'Receive rich foreign.\nRaise strong economy notice. Fear public finally owner floor ten sometimes.\nPerform bank imagine writer six long big. Even read fight play. Pretty discussion city player.',
    'email': 'melissasandoval@example.net',
    'phone_number': '001-285-351-9462x146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brandon White',
    'Dillon Cherry',
    'Robert Campbell',
    'Brian Palmer',
    'Christine Walters',
    'Jennifer Todd',
    'Kristy Yates',
    'Kimberly Garcia',
    'Brian Webb',
    'Jesse Barrett',
],
    'json': {
    'name': 'Heather Baker',
    'address': '5620 Mcdowell Road Apt. 437\nNorth Jennifer, VA 81882',
},
    'key93796': 'value7131',
    'key31761': 'value58949',
    'key93887': 'value38853',
    'key81845': 'value85484',
    'key21266': 'value89535',
    'key38676': 'value30621',
    'key55389': 'value78439',
    'key66917': 'value46043',
    'key46625': 'value43095',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Latoya White',
    'address': 'Unit 8368 Box 6496\nDPO AA 61250',
    'text': 'Hotel by condition and. Entire seek stock power maintain certainly street beat. Bank pass task year help.\nSix consider to necessary would choice. Source us system important for image place.',
    'email': 'kim91@example.net',
    'phone_number': '610-884-5317x6401',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Betty Johns',
    'Lauren Anderson',
    'Kimberly Lee',
    'Jamie Farrell',
    'Amy Palmer',
    'Christine Gonzales',
    'Emily Hobbs',
],
    'json': {
    'name': 'Donald Rodriguez',
    'address': '00036 Linda Mews\nEast Dustinton, AS 72336',
},
    'key46807': 'value3721',
    'key79086': 'value43651',
    'key66403': 'value29402',
    'key11309': 'value68931',
    'key56573': 'value62132',
    'key51566': 'value66535',
    'key40590': 'value9',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Hector Mcfarland',
    'address': '99800 Zimmerman Harbor\nLake Joshuaburgh, ID 41216',
    'text': 'Reveal those PM get. Seven in various bag she. Cell build nature realize official.\nHand commercial bill anyone. Happy wind do blood item own. Miss carry option enjoy want.',
    'email': 'kristopherbolton@example.net',
    'phone_number': '5333183603',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Brown',
    'Frederick Morris',
    'Ashley Santana',
    'Joanne Ramirez',
    'Ronald Jones',
    'Albert Eaton',
    'Mr. Christopher Moore',
    'Dennis Ramirez DVM',
    'Robert Graham',
],
    'json': {
    'name': 'Angela Johnson',
    'address': '502 Joseph Inlet\nWalkerburgh, GU 61465',
},
    'key21500': 'value61791',
    'key28040': 'value58123',
    'key39954': 'value65136',
    'key97311': 'value44571',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Robert Flores',
    'address': '82745 Debra Loaf Suite 903\nClarkmouth, WI 94246',
    'text': 'Billion attorney change until state behavior there that. Mother important head understand city line matter. Southern anything cell green. Politics final new any environment off wonder.',
    'email': 'ryanclark@example.org',
    'phone_number': '384.744.8100x135',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Leblanc',
    'Lisa Johnston',
    'Maurice Brown',
    'Jeremy Roberts',
    'Dawn Salinas',
    'Tina Cruz',
],
    'json': {
    'name': 'Lori Sosa',
    'address': '7510 Alicia Estate Suite 766\nTrevinostad, WA 16595',
},
    'key83704': 'value90834',
    'key64924': 'value37954',
    'key42384': 'value43454',
    'key51384': 'value96060',
    'key6842': 'value5837',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Raymond Garner',
    'address': '979 Cole Pine Suite 381\nNorth Cameronview, TN 19131',
    'text': 'Kind become responsibility. Maintain political note action resource cost education.\nProject nice occur interview rise get from.',
    'email': 'conleydonna@example.org',
    'phone_number': '+1-604-920-1476x82558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Dunn',
],
    'json': {
    'name': 'Mark Ayers',
    'address': '26287 Williams Street Suite 073\nJohnsonborough, SC 35176',
},
    'key49728': 'value20339',
    'key55998': 'value19911',
    'key94487': 'value27596',
    'key7036': 'value32395',
    'key70810': 'value39273',
    'key62030': 'value66228',
    'key52930': 'value85199',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Marcus Davis',
    'address': '91739 Burns Road Suite 576\nLake Christopher, IA 53821',
    'text': 'Actually positive agree go responsibility near. Sense success evidence rise. Democratic away old rock environmental and. Meeting draw hospital hair because they easy.',
    'email': 'rcosta@example.net',
    'phone_number': '624.620.6810x3006',
    'array_int_dynamic': [
    28287,
],
    'array_varchar_dynamic': [
    'Mary Anderson',
    'Angela Woods',
    'Angela Torres',
    'Thomas Beltran',
    'Seth Hall',
    'Tyler Collins',
    'Mr. Nicolas Powell',
    'Sheila Cameron',
    'Samuel Nichols',
],
    'json': {
    'name': 'Ethan Nguyen',
    'address': '50495 Jennifer Glens\nVanessashire, MI 75695',
},
    'key37724': 'value23723',
    'key96880': 'value85636',
    'key61998': 'value54109',
    'key48419': 'value63080',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Krystal Haas',
    'address': '78941 Smith Lodge Suite 786\nLake Jill, NV 47268',
    'text': 'Maybe item cause develop beat program. Eye room character. Cut recognize lot lead his toward that.',
    'email': 'lawrence55@example.net',
    'phone_number': '324.400.0498x878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Carmen Ward',
    'Mark Sutton',
    'Robert Owens',
    'Tasha Bush',
    'Edwin Moore',
    'Ian Horn',
    'Jack Lee',
    'Heather Armstrong',
    'Brenda Cooper',
    'Tiffany Warren',
],
    'json': {
    'name': 'Becky Sherman',
    'address': '61696 Rebecca Keys Suite 622\nEast Angelatown, MH 64869',
},
    'key22369': 'value69178',
    'key91078': 'value32699',
    'key83876': 'value92886',
    'key66787': 'value36541',
    'key4807': 'value70919',
    'key86922': 'value21120',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Kathy Schneider',
    'address': 'USNS Williams\nFPO AP 08788',
    'text': 'Politics oil wear power doctor sometimes. Week theory hour away. Many tax professor care their hospital scene.\nTonight green than moment while street. Carry traditional also over production peace.',
    'email': 'robert75@example.org',
    'phone_number': '935-975-3123',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Julie Stewart',
    'Tara Smith',
    'Gina Tran',
],
    'json': {
    'name': 'Zachary Fischer',
    'address': '58469 Jones Plain\nPort Stephanie, GA 68656',
},
    'key42295': 'value70105',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Kelly Nielsen',
    'address': '0966 Gallagher Points Apt. 237\nYoungview, DC 53248',
    'text': 'Require low perform up. Anything far thus tree.\nNote newspaper though hour agent suffer. Reflect there wall campaign north.\nSpecific whole specific time. Event many check business expert term system.',
    'email': 'gwilcox@example.net',
    'phone_number': '(665)794-6574x1618',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angela Garcia',
    'Angela Smith',
    'Charles Smith',
    'Scott Brooks',
    'Mrs. Mary Mitchell DVM',
],
    'json': {
    'name': 'Kevin Ryan',
    'address': '4220 Ryan Light\nWest Michaelbury, ID 33389',
},
    'key56537': 'value5605',
    'key21098': 'value1934',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Fernando Howell',
    'address': '443 Amy Shores Apt. 515\nNorth Joseph, GA 29081',
    'text': 'Matter along bag. Church out word name prepare. Hotel know least school skill.\nMorning situation yet me space suggest. Bill run church plan receive ball.',
    'email': 'eric88@example.com',
    'phone_number': '719-992-2364',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sierra Gray',
    'Joseph Young',
    'Mark Carey',
    'Alison Villarreal',
],
    'json': {
    'name': 'Patricia Pearson',
    'address': '663 Christine Drive\nNew Michael, PW 16425',
},
    'key86546': 'value60426',
    'key2563': 'value52630',
    'key52855': 'value56199',
    'key39603': 'value99750',
    'key25426': 'value40272',
    'key29876': 'value40137',
    'key14946': 'value83507',
    'key79241': 'value37678',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Hannah Taylor',
    'address': '778 Brenda Lights\nWest Christopherland, MT 61373',
    'text': 'Within leave while special. Security vote decade. Author try now executive account campaign charge change.',
    'email': 'rwalsh@example.org',
    'phone_number': '615-666-2496x38238',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Patel',
    'Heidi Zimmerman',
    'Sylvia Moreno',
    'Jeffrey Francis',
    'Laura Ruiz',
    'Chase Hess',
    'Sean Hall',
    'Justin Collier',
    'Kayla Anderson',
],
    'json': {
    'name': 'Trevor Roberts',
    'address': '4469 Jeffrey Pike Apt. 914\nSouth Roytown, VT 10887',
},
    'key11079': 'value92446',
    'key22799': 'value64262',
    'key69621': 'value66387',
    'key84049': 'value93472',
    'key13555': 'value63945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Nicole Hammond',
    'address': '2050 Cole Ville Suite 708\nBrianaborough, VA 09676',
    'text': 'Even give through believe analysis much. Gun kitchen rock artist. Short eye short black.',
    'email': 'erica67@example.com',
    'phone_number': '959.756.8193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Summers',
    'Kendra Taylor',
    'John Reyes',
    'Fernando Flores',
    'Vicki Sanchez',
    'Renee Mcbride',
    'Ashley Wright',
    'Kelly Kidd',
],
    'json': {
    'name': 'Melissa James',
    'address': '33716 Amber Gardens\nNew Catherineville, MT 20016',
},
    'key61813': 'value11702',
    'key86262': 'value43463',
    'key48055': 'value62873',
    'key37160': 'value74873',
    'key22767': 'value8620',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Courtney Hodges',
    'address': '1061 Lewis Dale Apt. 893\nNorth Sarahmouth, UT 51395',
    'text': 'Would serious truth upon Mrs. Culture pressure end after fast house.\nDream management surface how wear yet lot.\nRemain other technology city truth. Walk apply analysis small.',
    'email': 'zyoung@example.org',
    'phone_number': '(424)793-7536x49091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Colin Roberson',
    'Jeffery Collins',
    'Joy Davidson',
    'Patricia Young',
],
    'json': {
    'name': 'Susan Martinez',
    'address': '805 Daniel Wells Suite 662\nLake Candiceside, WY 37506',
},
    'key24210': 'value27734',
    'key80209': 'value57403',
    'key13514': 'value93139',
    'key85167': 'value36885',
    'key83479': 'value14857',
    'key18080': 'value21607',
    'key45894': 'value31001',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Darryl Marquez',
    'address': '177 Williams Gateway Apt. 343\nSouth Masonmouth, FL 09643',
    'text': 'South size loss strategy. Subject reach when law. Like magazine after garden old ten toward.',
    'email': 'alexander66@example.org',
    'phone_number': '(396)940-1426x194',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Maria Melton',
    'Holly Ray',
    'Joshua Walker',
    'Lori Brown',
    'Michelle Myers',
    'Mallory Barron',
    'Jessica Dixon',
],
    'json': {
    'name': 'David Ortiz',
    'address': '60999 Morales Motorway\nLake John, PA 85920',
},
    'key30671': 'value93138',
    'key43568': 'value41247',
    'key16927': 'value49174',
    'key89385': 'value93164',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'John Fowler',
    'address': '3440 Jennifer Club\nCummingsshire, MS 30463',
    'text': 'Case player treatment product. Notice heart miss hold child machine.\nHuman conference manage conference think fact nation production.',
    'email': 'amysmith@example.com',
    'phone_number': '982-570-0686x58499',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Miguel Clark',
    'Tammy Frazier',
    'Michelle Thomas',
    'Christopher Roberts',
    'Susan Taylor',
],
    'json': {
    'name': 'Cheryl Lee',
    'address': '0215 Amanda Mountain Apt. 785\nWest Robert, SD 56802',
},
    'key54565': 'value86615',
    'key52697': 'value24141',
    'key46430': 'value57547',
    'key65477': 'value95062',
    'key19477': 'value98820',
    'key45703': 'value50794',
    'key67592': 'value32967',
    'key70468': 'value77229',
    'key9301': 'value14323',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Lisa Skinner',
    'address': '722 Mendez Heights Suite 787\nFrankland, PA 89703',
    'text': 'Court population or democratic. Knowledge benefit chair spend total develop. Though analysis always project table economy.',
    'email': 'armstrongmelissa@example.net',
    'phone_number': '835-224-6376',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Parks',
    'Linda Gonzalez',
    'Christopher Sanders DVM',
    'Taylor Garcia',
    'Tamara Padilla',
    'Matthew Murray',
    'Kenneth Butler',
    'Margaret Cole',
],
    'json': {
    'name': 'Gerald Williams',
    'address': '153 Joseph Mills Suite 454\nSharonshire, MN 42928',
},
    'key32614': 'value68689',
    'key4444': 'value30285',
    'key78886': 'value15091',
    'key30902': 'value76043',
    'key64543': 'value3637',
    'key70014': 'value36747',
    'key56297': 'value97433',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Dr. Lisa Romero',
    'address': 'PSC 8590, Box 0292\nAPO AA 99833',
    'text': 'Wall enter popular operation senior purpose local. Why through Republican too firm positive drop price. Company base create company however business for.',
    'email': 'floresrobert@example.net',
    'phone_number': '450.945.2875',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Finley',
    'Jennifer Vang',
    'Jose Stevens',
    'Crystal Mitchell',
    'Kim Bowen',
    'Terry Wood',
    'Lisa Johnson',
],
    'json': {
    'name': 'Benjamin Hall',
    'address': '3856 Jackson Locks Suite 589\nPort Donaldtown, AL 89628',
},
    'key68066': 'value1369',
    'key45856': 'value85174',
    'key60759': 'value50398',
    'key99269': 'value3911',
    'key83634': 'value81581',
    'key72656': 'value7451',
    'key47000': 'value73379',
    'key89924': 'value6848',
    'key65785': 'value23314',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Andrew Davis',
    'address': '0697 Jacob Mall\nEast Markstad, SC 53933',
    'text': 'Play standard best what difficult improve. That tonight expert white finish require gas bank.\nSituation who best.',
    'email': 'edwardsgina@example.net',
    'phone_number': '001-634-597-8102',
    'array_int_dynamic': [
    22258,
],
    'array_varchar_dynamic': [
    'Phillip Taylor',
    'Russell Knox',
    'Eric Black',
    'Jason Whitney',
    'Patricia Hall',
    'Denise Walker',
    'Justin Hoover',
],
    'json': {
    'name': 'Dakota Rowe',
    'address': '703 Corey Gardens\nNew Dylanberg, MO 28787',
},
    'key97523': 'value44724',
    'key34043': 'value73814',
    'key98919': 'value39556',
    'key95539': 'value98430',
    'key25868': 'value6842',
    'key23145': 'value38637',
    'key51301': 'value16735',
    'key61296': 'value9062',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Megan Garcia',
    'address': '550 Wilson Inlet\nWalkerhaven, GU 40828',
    'text': 'Use here road all. Life only arm why measure evidence. Tough question big. Feel husband however.\nHand street conference concern. Prepare man cultural government value view.',
    'email': 'wrightjohn@example.net',
    'phone_number': '(789)741-4840x3497',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Walker',
    'Erika Jones',
],
    'json': {
    'name': 'Aaron Gibson',
    'address': '34406 Moreno Overpass\nWalkerborough, NC 88297',
},
    'key35958': 'value41856',
    'key39369': 'value34068',
    'key10327': 'value58912',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Stanley Mcneil',
    'address': '126 Latasha Forks\nHartmanmouth, AL 39671',
    'text': 'Husband cut very town. Probably guy mention past religious consumer.\nAway event option big. Hotel mind what sit wind most school method. These school six.',
    'email': 'hartgeorge@example.org',
    'phone_number': '(253)401-9771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Henry',
    'Melinda Adams',
    'Mark Blevins',
],
    'json': {
    'name': 'Dr. Tony Black',
    'address': '09016 Hunt Neck\nSherribury, PR 73562',
},
    'key6923': 'value86772',
    'key88042': 'value55750',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Joel Weiss',
    'address': '199 Rodgers Avenue Apt. 477\nLake Chelsea, CT 10953',
    'text': 'Time increase military responsibility amount race. Statement certainly try safe. Prepare usually address create ball development impact.',
    'email': 'jeremyshaw@example.net',
    'phone_number': '252.706.1263',
    'array_int_dynamic': [
    71300,
],
    'array_varchar_dynamic': [
    'Regina Villarreal',
    'Gail Thompson',
    'Eric Holloway',
],
    'json': {
    'name': 'Bradley Clark',
    'address': '658 Gardner Fords\nJohnstonborough, NH 08665',
},
    'key97129': 'value60287',
    'key20616': 'value26301',
    'key27046': 'value44715',
    'key74045': 'value16065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Ronald Dean',
    'address': '6967 Hill Course Apt. 134\nMarshalltown, LA 71433',
    'text': 'Center low reach. Poor poor change finally man. Carry clearly together according race.\nArm such go want listen home. As simply area.',
    'email': 'scollins@example.org',
    'phone_number': '001-405-759-6844',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Erica Rodriguez',
],
    'json': {
    'name': 'David Ward',
    'address': '5651 Tanner Pike\nNorth Jessicachester, CO 85185',
},
    'key76362': 'value11583',
    'key90290': 'value10893',
    'key48494': 'value69521',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jodi Duarte',
    'address': '346 Martinez Flat Suite 390\nLesterfurt, RI 61059',
    'text': 'Later end surface seven two. Hand throw wonder think artist fire issue.\nYour real catch many yourself line. Sister answer want. Present property employee never.',
    'email': 'shawnmurphy@example.net',
    'phone_number': '+1-947-370-1694x7972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Schmidt',
],
    'json': {
    'name': 'Beth Vazquez',
    'address': '53756 Charles Park Suite 672\nWest Felicia, VI 76684',
},
    'key17659': 'value98260',
    'key81525': 'value33099',
    'key72540': 'value52704',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Ann Ho',
    'address': '91927 Tracie Mount\nNorth Andrea, MP 89377',
    'text': 'Issue own wait future explain player star. Mrs win director financial energy.\nValue value mother southern into measure. Artist south form notice street.',
    'email': 'dlee@example.net',
    'phone_number': '(722)776-4856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Gray',
    'Jonathan Benson',
    'Megan Bryant',
    'James Bender',
],
    'json': {
    'name': 'Kimberly Ellis',
    'address': '11408 Bates Way Apt. 944\nSouth Garyville, FL 10839',
},
    'key15431': 'value39535',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kelly Smith',
    'address': '257 Justin Lock\nNew Wayneland, OH 64623',
    'text': 'Whatever wrong book surface positive produce ability. Partner institution still play edge material.',
    'email': 'zmoreno@example.net',
    'phone_number': '(711)716-9019x8871',
    'array_int_dynamic': [
    44851,
],
    'array_varchar_dynamic': [
    'Emily Miles',
],
    'json': {
    'name': 'William Robinson',
    'address': '48340 Castro Pike Suite 740\nGlennhaven, TX 73572',
},
    'key28251': 'value99742',
    'key56210': 'value96913',
    'key89952': 'value26536',
    'key69097': 'value22930',
    'key19917': 'value80676',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Daniel Buchanan',
    'address': '5801 Jerry Haven Suite 308\nMichaeltown, GA 13721',
    'text': 'Fly capital near research interview education collection. Actually environmental only mission line middle.',
    'email': 'fullerjohn@example.com',
    'phone_number': '(295)638-2658x13667',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Gonzalez',
    'Denise Pena',
],
    'json': {
    'name': 'Heather Morales',
    'address': '40183 Simon Station Suite 017\nNew Amyfurt, PR 95499',
},
    'key57135': 'value24128',
    'key49738': 'value23551',
    'key3115': 'value53349',
    'key12306': 'value67547',
    'key63095': 'value320',
    'key68531': 'value43861',
    'key88760': 'value92073',
    'key16983': 'value26861',
    'key91093': 'value31591',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Mark Nguyen',
    'address': '33880 Jamie Glens\nEast Stephenborough, MO 59159',
    'text': 'Kind not young imagine work thus single. Much drug life night such.\nCrime line else nothing. One rich wish.\nLeg where me arrive place opportunity kitchen. Seven option time high senior laugh once.',
    'email': 'gbrown@example.org',
    'phone_number': '353.922.0963x4261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Foster',
    'Johnathan Mitchell',
    'Brenda Turner',
    'Jonathan Salinas',
    'Rachel Estrada',
    'Michael Jenkins',
    'Steven Manning',
    'Kathleen Rogers',
    'Dawn Frost',
    'Diane Tapia',
],
    'json': {
    'name': 'Rebecca Sparks',
    'address': '7355 Eric Loaf Apt. 826\nSuzanneville, WV 99698',
},
    'key76146': 'value58942',
    'key73973': 'value98391',
    'key92828': 'value63153',
    'key11629': 'value13917',
    'key98974': 'value75509',
    'key28687': 'value46895',
    'key31023': 'value78804',
    'key50535': 'value54983',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Michael Bird',
    'address': '10943 Smith Divide\nPort Dianatown, MD 63168',
    'text': 'Production fast collection set. System ball something research ever particularly never.\nProject can down. Whether difference discussion capital.',
    'email': 'daniel02@example.org',
    'phone_number': '(981)921-7673',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'April Castaneda',
    'Dr. Tiffany Flores DVM',
    'Tyler Murphy',
    'Heather Thornton',
    'Dr. Valerie Delgado MD',
    'Katherine Torres',
    'Dr. Kathleen Hansen',
],
    'json': {
    'name': 'Heather Dickerson',
    'address': '8041 Christopher Rue\nTonyaside, RI 34328',
},
    'key3069': 'value20142',
    'key73811': 'value71551',
    'key42796': 'value53768',
    'key92253': 'value4726',
    'key65583': 'value14198',
    'key42780': 'value86857',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'William Watkins DVM',
    'address': '7283 West Lane Apt. 629\nLake Roberthaven, LA 45071',
    'text': 'Newspaper change speech appear doctor current. Official clearly image suggest thousand since. Without poor fast mind administration billion. Establish go range behavior past.',
    'email': 'timothyparker@example.net',
    'phone_number': '(984)488-8572',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Whitehead',
    'Meagan Mcpherson',
    'Lance Marquez',
    'Danielle Barnes',
    'Amy Martin',
    'Jessica Whitaker',
    'Reginald Klein',
    'Katherine Miller',
    'Olivia Bautista',
    'Carlos Robinson',
],
    'json': {
    'name': 'Kelly Bowman',
    'address': '086 Mary Gateway Suite 460\nJohnstad, MT 43900',
},
    'key62762': 'value20396',
    'key18772': 'value91483',
    'key23205': 'value1337',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Patricia Roberson',
    'address': '9876 Lauren Trace\nSouth Daniel, FL 93175',
    'text': 'Player gun old television camera. Prepare wife near always.\nDrop fast trouble already improve. Choose get oil paper base remain role picture. Parent hospital system out.',
    'email': 'greenkatelyn@example.org',
    'phone_number': '853.365.8634x3399',
    'array_int_dynamic': [
    54667,
],
    'array_varchar_dynamic': [
    'Ashley Watts',
    'Mrs. Ashley Rodriguez',
    'Andrew Ellis',
    'Mallory Moore',
    'Kevin Quinn',
    'Julie Dean',
],
    'json': {
    'name': 'Richard Bishop',
    'address': '478 Yvonne Valleys Apt. 963\nWest Melissaton, FL 25764',
},
    'key36374': 'value34232',
    'key89512': 'value32186',
    'key42512': 'value59954',
    'key45160': 'value65374',
    'key84755': 'value46041',
    'key41876': 'value38680',
    'key78551': 'value54344',
    'key37123': 'value63240',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Deborah Perez',
    'address': '89693 Timothy Wall\nKimberlyland, MH 54158',
    'text': 'Include clearly theory maintain various whatever. All live direction song hotel student model.\nDecision move gun end how same reason. Man family nation while field special trouble.',
    'email': 'pkaiser@example.net',
    'phone_number': '240-702-6752x3261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Huffman',
    'Michelle Torres',
    'Damon Jones',
    'Denise Carr',
    'Matthew Hudson',
    'Kayla Williams',
    'Hunter Clayton',
    'Dawn King',
    'Gary Lambert',
],
    'json': {
    'name': 'James Landry',
    'address': '168 Knight Extensions\nWest Denise, MH 33131',
},
    'key71242': 'value47975',
    'key14538': 'value6778',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'George Thomas',
    'address': '262 Brown Divide Apt. 183\nWest Michele, MH 16515',
    'text': 'Surface letter spend fish sing wide station. Candidate its claim involve job key hard. Mean left lead population artist trip. Throughout agree help career begin capital opportunity.',
    'email': 'nelsonjonathan@example.com',
    'phone_number': '793.526.0215x753',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Horton',
    'Stephanie Roberts',
    'Mario Porter',
],
    'json': {
    'name': 'Steven Mendez',
    'address': '1069 Lindsey Lodge Suite 247\nNorth Maryport, DC 08283',
},
    'key63367': 'value44507',
    'key34274': 'value17757',
    'key33531': 'value66485',
    'key82401': 'value27802',
    'key32197': 'value61157',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Mathew Ramsey',
    'address': '588 Shirley Coves\nRomeroburgh, AZ 47686',
    'text': 'Throw natural watch direction shoulder development eight debate. Player down light seat option letter address service.\nBefore ask peace sometimes small. Drop space market issue task.',
    'email': 'monica84@example.net',
    'phone_number': '279.287.7813x3308',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joel Evans',
    'Wendy Williams',
    'Daniel Snyder',
    'Diana Baker',
    'Kristi Irwin',
    'Trevor Bowman',
    'Mr. Richard Schmidt',
],
    'json': {
    'name': 'Matthew Smith',
    'address': '0453 Hunt Tunnel Suite 349\nConniebury, MO 84280',
},
    'key27278': 'value88245',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Benjamin Spears',
    'address': '95275 Catherine Fields Apt. 010\nWest Andrewfort, HI 72138',
    'text': 'Account fire company want us machine mean. Down campaign small. See station evening likely baby big. Policy seek quickly number.',
    'email': 'cbecker@example.net',
    'phone_number': '001-259-790-7868x899',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mr. David Wood',
    'Angela Jones',
    'Nicholas Beltran',
],
    'json': {
    'name': 'Carly Lane',
    'address': '0803 Russell River\nSouth Andrew, WV 19762',
},
    'key13415': 'value35397',
    'key10094': 'value51616',
    'key85764': 'value10667',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Tracy Gibbs',
    'address': '01753 Swanson Plaza\nDevinfort, AS 16216',
    'text': 'Rich couple yes occur couple. We reflect guy although tell wife international. Medical conference friend turn customer.\nSay enough fine he. Who win improve myself.',
    'email': 'mwilliams@example.org',
    'phone_number': '7085432407',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gloria Baker',
    'Kenneth Johnson',
    'Victoria Burke',
    'Thomas Scott Jr.',
    'Robin Gallagher',
    'April Elliott',
],
    'json': {
    'name': 'Erica Atkins',
    'address': '5188 Robertson Overpass\nSalinasview, PW 99103',
},
    'key79305': 'value48918',
    'key47007': 'value64895',
    'key47932': 'value98558',
    'key16962': 'value54844',
    'key82363': 'value14295',
    'key41053': 'value18225',
    'key29688': 'value5761',
    'key67600': 'value9923',
    'key76844': 'value56819',
    'key95714': 'value80231',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Anna Thomas',
    'address': '079 Lisa Ville Suite 514\nArielton, VT 11972',
    'text': 'Before per laugh sell laugh choice. Trouble compare idea. Name table so trade.\nHard change write budget discover deal. Task agency participant day this the remember data. None at second kind.',
    'email': 'johnsoncynthia@example.com',
    'phone_number': '+1-971-362-9579x68789',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Miranda Washington',
    'Jessica Rivers',
    'Douglas Meyer',
    'Paula Harrison',
    'Bethany Mack',
    'Joyce Strickland',
    'Erik Sanchez',
    'Ashley King',
    'Isaiah Bell',
    'Jack Carr',
],
    'json': {
    'name': 'Nathan Cooper',
    'address': '3775 Reid Point Suite 199\nHowardchester, MD 35331',
},
    'key44756': 'value93152',
    'key49213': 'value50739',
    'key86776': 'value68379',
    'key51671': 'value25192',
    'key30966': 'value36092',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Victoria Avila',
    'address': '7574 Bridget Ville Suite 592\nNew Teresaland, NJ 10000',
    'text': 'Bank anything shake law picture resource story. Draw until state family forget ready.\nBody responsibility expect born. Fine stuff at know. Hear trip ten determine source speak standard minute.',
    'email': 'xrussell@example.org',
    'phone_number': '001-642-497-9425',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Duffy',
    'Dana Edwards',
    'Erica Hart',
    'Matthew Chen',
    'Vincent Calderon',
    'Christopher Fuentes',
],
    'json': {
    'name': 'Joshua Wilson',
    'address': 'Unit 2501 Box 5371\nDPO AA 09679',
},
    'key80510': 'value88959',
    'key77996': 'value11511',
    'key84061': 'value32844',
    'key49480': 'value37808',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Tiffany Gilmore',
    'address': '495 Christine Causeway\nEast Deborahfurt, UT 29870',
    'text': 'Environmental better order population. Decide forget guess while someone really full. School better manager author win hard best.',
    'email': 'marvinhoffman@example.org',
    'phone_number': '+1-659-902-9346x1820',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Singh',
    'Valerie Rubio',
    'Patricia Koch',
    'Erin Sanchez',
    'Sarah Johnson',
],
    'json': {
    'name': 'Darius Finley',
    'address': '9656 Kelley Harbor\nWest Roberto, RI 27979',
},
    'key48054': 'value64038',
    'key56107': 'value1492',
    'key65113': 'value61603',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Eddie Hernandez',
    'address': '948 Shawn Islands Suite 351\nLake Lauren, NY 77623',
    'text': 'Whose like above common. Assume word great. Himself certain news interview turn.\nPresent meet form order agreement.',
    'email': 'tuckerchristopher@example.net',
    'phone_number': '6642594640',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Henderson',
    'Christina Morgan',
],
    'json': {
    'name': 'Patrick Cowan',
    'address': '7850 Cunningham Springs\nLoganside, AR 30473',
},
    'key83094': 'value15552',
    'key84351': 'value14968',
    'key13149': 'value68263',
    'key15881': 'value91314',
    'key18386': 'value66426',
    'key95765': 'value569',
    'key89967': 'value11727',
    'key36560': 'value22609',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jennifer Mcneil',
    'address': '4404 Garza Views Suite 669\nWest Darlene, IL 41482',
    'text': 'Physical policy six of admit. Simple worry hear already sure.\nReligious to role claim. Consider claim character officer eight will.\nDespite gas drug chair. Young music other around degree.',
    'email': 'hernandezshane@example.com',
    'phone_number': '851-770-1469',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Mitchell',
],
    'json': {
    'name': 'Barbara Mora',
    'address': 'Unit 5341 Box 0418\nDPO AE 26970',
},
    'key29516': 'value3564',
    'key60923': 'value66936',
    'key6400': 'value61404',
    'key11861': 'value38148',
    'key83962': 'value80432',
    'key96082': 'value52463',
    'key82105': 'value97546',
    'key92445': 'value22463',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Victor Hogan',
    'address': '46019 Jason Roads\nMcbridemouth, VI 69187',
    'text': 'Them also table edge knowledge democratic thank. His fire game minute. Say different often soldier.\nLate land medical how.',
    'email': 'jamesrusso@example.org',
    'phone_number': '001-697-350-8926x94182',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Rodriguez',
    'Bianca Turner',
],
    'json': {
    'name': 'Katie Morse',
    'address': '360 Hensley Highway\nBrittanyton, PW 54501',
},
    'key69088': 'value81372',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Brianna Vega',
    'address': '050 Ryan Tunnel Apt. 383\nMichelleshire, OH 67660',
    'text': 'Own small probably or clearly view those leader.\nOn share together senior wall while treatment. Necessary policy first exist either despite. Yeah reality report animal full.',
    'email': 'melissa10@example.net',
    'phone_number': '001-358-620-7040x3115',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Bowen',
],
    'json': {
    'name': 'Harry Dougherty',
    'address': '607 Joshua Plains\nLindsaystad, KS 72158',
},
    'key3730': 'value75537',
    'key64385': 'value52454',
    'key82074': 'value53696',
    'key86693': 'value63051',
    'key27313': 'value95173',
    'key44418': 'value19950',
    'key58570': 'value59336',
    'key99289': 'value17883',
    'key85721': 'value28057',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Cody Cole',
    'address': '6890 Martin Port\nSouth Darrellstad, OK 80698',
    'text': 'Camera employee face well. Five beat fight. Environmental between development even agency two back third.',
    'email': 'stacey25@example.com',
    'phone_number': '001-767-849-4071x41373',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Gonzalez',
    'Crystal Johnston',
    'Christian Lynch',
    'Kathy Gonzalez',
    'Connor Thompson',
    'Lisa Webster',
],
    'json': {
    'name': 'John Parrish',
    'address': 'PSC 4147, Box 3302\nAPO AA 28693',
},
    'key79383': 'value55023',
    'key86072': 'value19101',
    'key10679': 'value51998',
    'key80718': 'value19735',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Mrs. Rita Sanchez',
    'address': '65195 Rebecca Circles Apt. 578\nNorth Marissa, KY 42685',
    'text': 'From instead head Democrat certain small. Wait dinner hold. Your ball writer majority natural.\nPm focus benefit success hotel there. Center popular enjoy training financial interest.',
    'email': 'yramirez@example.com',
    'phone_number': '(416)733-1608',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Smith',
    'Chelsea Harmon',
    'Luke Christian',
],
    'json': {
    'name': 'Jane Hamilton',
    'address': '302 Beasley Manors\nPort Andrealand, AR 58661',
},
    'key97679': 'value12366',
    'key48746': 'value47599',
    'key43864': 'value54962',
    'key17335': 'value33982',
    'key6236': 'value90779',
    'key70408': 'value35857',
    'key1193': 'value34694',
    'key50880': 'value23581',
    'key2960': 'value6087',
    'key19515': 'value8102',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Shawn Mcintyre',
    'address': '7244 Ruiz Estates\nGaryshire, MA 16655',
    'text': 'Thought sell seek really. Glass or close yes wind financial. Every protect since economy goal specific no charge. Red medical receive available area manage growth.',
    'email': 'anna56@example.net',
    'phone_number': '001-261-794-5734x493',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Alvarez',
    'William Smith',
    'Katherine Hayden',
    'Tammy Prince',
    'Robert Duncan',
    'Sarah Smith',
    'Lori Davis',
],
    'json': {
    'name': 'Kevin Winters',
    'address': 'Unit 0643 Box 7822\nDPO AP 43736',
},
    'key98007': 'value48353',
    'key28404': 'value52396',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Ashley Robertson',
    'address': '44432 Lewis Estates Apt. 185\nWalkerfurt, LA 50897',
    'text': 'Bill fight off marriage.\nHowever here father girl key alone.\nGeneral join already. Big thought late risk perform. Section scene water whether.',
    'email': 'james89@example.org',
    'phone_number': '967-256-6489x8735',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tina Fletcher',
    'Mary Ford',
    'April Allen',
    'Mary Burke',
],
    'json': {
    'name': 'Julie Ross',
    'address': '9596 Cook Overpass Apt. 885\nMillerborough, OK 26622',
},
    'key33607': 'value5713',
    'key39394': 'value60760',
    'key46485': 'value70791',
    'key8284': 'value18467',
    'key22106': 'value28309',
    'key56328': 'value60625',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Aaron James',
    'address': '9390 Christensen Meadows\nWest Ronaldview, WV 96296',
    'text': 'Billion source all affect. Sport ago budget occur growth well dinner. Small quite PM however car art.\nBe section course smile. Lead day appear learn my.',
    'email': 'kellieduffy@example.net',
    'phone_number': '205.885.7395x40194',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Sanders',
],
    'json': {
    'name': 'Joseph Mayo',
    'address': 'PSC 5844, Box 2285\nAPO AE 30301',
},
    'key87305': 'value37881',
    'key9506': 'value65237',
    'key64487': 'value64030',
    'key86214': 'value98422',
    'key37496': 'value3809',
    'key87730': 'value13214',
    'key29990': 'value25514',
    'key62562': 'value50740',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Robert Brown',
    'address': '8920 Stokes Prairie\nRossfort, GU 34476',
    'text': 'Start word structure natural leader simple. Hot central general require. Star well six level evening.\nBecause question career father save yet. Wait message somebody. Outside notice ok lawyer list.',
    'email': 'john60@example.org',
    'phone_number': '389.890.1255x4993',
    'array_int_dynamic': [
    18201,
],
    'array_varchar_dynamic': [
    'Jessica Richard',
],
    'json': {
    'name': 'Shawn Andrade',
    'address': '64837 Jonathan Squares\nPort Keith, DC 62410',
},
    'key76676': 'value89485',
    'key83733': 'value25465',
    'key7650': 'value27830',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Micheal Perry',
    'address': '8260 Hernandez Plaza Apt. 237\nSouth Matthew, IL 80709',
    'text': 'Economy policy current middle.\nWe important recent down growth along. Republican treat television chance. Their every knowledge state western the consider.',
    'email': 'ybyrd@example.com',
    'phone_number': '276-231-8408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Rhodes',
],
    'json': {
    'name': 'Patrick Delgado',
    'address': '39837 Amanda Lake\nNew Williamport, VT 18855',
},
    'key39754': 'value95947',
    'key51078': 'value32580',
    'key52695': 'value81999',
    'key44343': 'value14761',
    'key52698': 'value68459',
    'key16573': 'value21592',
    'key15762': 'value29898',
    'key53684': 'value35012',
    'key28932': 'value53716',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Alexander Fernandez',
    'address': '32560 Patrick Burg\nSouth Heather, PW 11484',
    'text': 'Physical one assume central spring care. Season a through better. Child chair whether mind.\nWell work hard home not. On remember no effort course purpose southern play.',
    'email': 'qmaynard@example.net',
    'phone_number': '(880)419-3980x552',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Hill',
    'Cheryl Barber',
    'Christine Warner',
    'Randy Moody',
    'Brett Lewis',
    'Stephanie Gross',
    'Linda Wilson',
    'Melissa Davis',
],
    'json': {
    'name': 'Anthony Lawrence',
    'address': '6891 Hoffman Forks\nSouth Samanthafort, NV 04395',
},
    'key35138': 'value94291',
    'key85023': 'value7137',
    'key30939': 'value85222',
    'key30871': 'value57946',
    'key1276': 'value83285',
    'key56922': 'value28397',
    'key6504': 'value50017',
    'key54716': 'value85585',
    'key54839': 'value70380',
    'key82213': 'value45220',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Dr. Kyle Stark',
    'address': 'USNV Rivas\nFPO AE 94975',
    'text': 'Sound environment with Mrs bill analysis. Drive imagine rock church. Cut white common never record charge bring.',
    'email': 'wsmith@example.net',
    'phone_number': '2135049767',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Estrada',
    'Charles Boyle',
],
    'json': {
    'name': 'Penny Lowery',
    'address': '586 Melissa Rapid Apt. 159\nRussellmouth, PA 79366',
},
    'key99205': 'value1240',
    'key84722': 'value34645',
    'key2172': 'value61711',
    'key57411': 'value95968',
    'key49460': 'value86439',
    'key81828': 'value1372',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Joshua Price',
    'address': '9465 Simmons Fords Apt. 531\nNew Robert, ME 74549',
    'text': 'Think pay much there some east age front. Suddenly source indeed article.\nSince able speech local. Wait rather factor issue cold.\nToo point wear public. Knowledge scene not recently.',
    'email': 'marknelson@example.net',
    'phone_number': '809.366.7199',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Wright',
    'Tonya Fields',
    'Alexis King',
],
    'json': {
    'name': 'Kimberly Garcia',
    'address': '985 Gonzales Mill Apt. 996\nSouth Blake, IN 59781',
},
    'key13018': 'value5959',
    'key51267': 'value66284',
    'key17706': 'value49904',
    'key13090': 'value31291',
    'key57889': 'value95048',
    'key22423': 'value19023',
    'key2136': 'value69169',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Christine Ford',
    'address': '9483 Henry Extensions\nHeatherland, PR 02772',
    'text': 'Collection support case everyone board popular. Especially then think move use. Happen assume official other live.',
    'email': 'zwade@example.org',
    'phone_number': '001-864-907-2970x2728',
    'array_int_dynamic': [
    86800,
],
    'array_varchar_dynamic': [
    'Kurt Yoder',
],
    'json': {
    'name': 'Tina Ramos',
    'address': '84971 Calvin Route\nKatherineshire, OH 86320',
},
    'key30372': 'value1691',
    'key56084': 'value83698',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Stephanie Morrison',
    'address': '6582 Gordon Shoals\nNew Kimberly, MO 37914',
    'text': 'Drug phone agency military. Method ability head between already name.',
    'email': 'randy84@example.org',
    'phone_number': '570-606-2886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brett Johnson',
    'Sean Reed',
    'Ricky Bush',
    'Tina Cooley',
    'Jasmine Mckenzie',
],
    'json': {
    'name': 'Bradley Guzman',
    'address': '21718 Michelle Motorway Suite 820\nNorth Kristina, TN 19775',
},
    'key9523': 'value82651',
    'key98538': 'value15932',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'David Adams',
    'address': '322 Pearson Way Suite 071\nRitterton, ID 23907',
    'text': 'Hand somebody final south guess on tonight theory. City bar treat west.\nSo defense course Congress machine bank. Example discuss military soldier.',
    'email': 'nicolesmith@example.org',
    'phone_number': '(318)930-4366x4076',
    'array_int_dynamic': [
    68861,
],
    'array_varchar_dynamic': [
    'Ryan Johnston',
    'Nicole Cole',
    'Alicia Carlson',
],
    'json': {
    'name': 'Darlene Dean',
    'address': '3643 Cory Causeway\nPort Lauriechester, PR 26385',
},
    'key89162': 'value34823',
    'key35916': 'value69262',
    'key91413': 'value52975',
    'key15911': 'value92196',
    'key33006': 'value87401',
    'key39625': 'value50757',
    'key72824': 'value48526',
    'key31093': 'value56457',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Ellen Freeman',
    'address': '0057 Sara Stream Suite 650\nPattersontown, IA 87556',
    'text': 'Prepare night may claim find address mind box. Building paper almost sing organization thing. Again three understand defense it.\nSuccess far send ball. Company fine whole late impact role.',
    'email': 'jclark@example.net',
    'phone_number': '840-468-2049x0387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Krueger',
    'Brenda Richardson',
    'Christopher Snyder',
    'Jennifer Mack',
    'Steven King',
    'Kent Roach',
    'Leslie Reed MD',
    'Dr. George Walker MD',
    'Thomas Johnson',
    'Daniel Boyd',
],
    'json': {
    'name': 'Kristen Rivera',
    'address': '333 Davis Pine Apt. 101\nLaurenport, PA 22083',
},
    'key91442': 'value22530',
    'key38872': 'value1200',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Patrick Robinson',
    'address': '5864 Avila Drive\nWest Bryanbury, MI 16641',
    'text': 'Generation past yard. Activity yet tax care. Thus work simply way see win.\nEmployee old data prepare. Record describe can name center politics. Issue support quality.',
    'email': 'billyford@example.com',
    'phone_number': '452-395-5588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Carroll',
    'Debbie Johnson',
    'Richard Schwartz',
    'Amy Hill',
    'David Howard',
    'Sharon Stevens',
],
    'json': {
    'name': 'Stephen Woods',
    'address': '2098 Hensley Walks Suite 773\nAnnaborough, VI 95793',
},
    'key9408': 'value27364',
    'key7048': 'value34030',
    'key1373': 'value19313',
    'key37156': 'value40981',
    'key95633': 'value41327',
    'key10144': 'value16720',
    'key33842': 'value75570',
    'key57456': 'value51072',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'James Knight',
    'address': '73362 Cooper Knoll Suite 866\nEast Lauramouth, IL 58945',
    'text': 'Ready have break evidence. Door lawyer various a tree heart painting. Along small read process lot player.\nEconomy world whom argue education economic. Top trip PM way.',
    'email': 'craigperez@example.com',
    'phone_number': '949-387-6958',
    'array_int_dynamic': [
    13225,
],
    'array_varchar_dynamic': [
    'Anna Edwards',
    'Todd Hill',
],
    'json': {
    'name': 'James Reilly',
    'address': '90284 Singleton Cliffs\nBaileyland, IA 61145',
},
    'key28374': 'value79398',
    'key75048': 'value71451',
    'key78302': 'value44119',
    'key94758': 'value76876',
    'key69301': 'value78933',
    'key54433': 'value87488',
    'key93900': 'value40224',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Samantha Contreras',
    'address': '7671 Johnny Street Suite 865\nLaurenfort, MT 09680',
    'text': 'Really suggest suddenly view. Finally seven home. Performance listen say loss try bag drive.\nLawyer debate term take daughter meeting. Major life give term detail five rule mention.',
    'email': 'donnaallen@example.net',
    'phone_number': '001-907-658-1216x5038',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Eric Wilson',
    'Charlotte Webb',
    'Colleen Giles',
    'April Snyder',
    'Edward Wiley',
    'Stephen Reyes',
    'Dr. Kurt Hunt',
    'Michelle Chandler',
],
    'json': {
    'name': 'Laura Berry',
    'address': '99364 Webster Manors\nBradfordhaven, RI 85754',
},
    'key64376': 'value52995',
    'key68850': 'value52591',
    'key87485': 'value12407',
    'key76087': 'value80833',
    'key58088': 'value83233',
    'key70375': 'value52100',
    'key64585': 'value77534',
    'key59176': 'value34881',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Trevor Barnett',
    'address': '80686 Foster Green\nPort Jamieland, NM 80914',
    'text': 'General nice need her security heavy. Might culture cost. Up way loss actually yourself.\nBeautiful whose class happen else view. Author leg strong race partner medical.',
    'email': 'philip45@example.org',
    'phone_number': '(509)599-1021x4378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Todd Villarreal Jr.',
    'Amber Green',
    'Jenny Contreras',
    'Christine Hunter',
    'Brittany Flynn',
    'Kimberly Casey',
    'Craig Greer',
],
    'json': {
    'name': 'Victoria Larson',
    'address': '43883 Clark Manors Apt. 831\nClaybury, NV 81061',
},
    'key71486': 'value90268',
    'key74693': 'value38047',
    'key33136': 'value27883',
    'key27428': 'value63970',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jillian King',
    'address': '76342 Kelly View Suite 558\nSouth Mckenzie, MS 97201',
    'text': 'Firm large bring yourself. Natural move guy lawyer one week. Today small could moment oil kind.\nBring bank space phone international. Probably peace every sort maybe fire base.',
    'email': 'uwong@example.org',
    'phone_number': '503-205-2430',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Steven Garcia',
    'Lindsay Ruiz',
    'Brittany Hardy',
    'Kevin Schmidt',
    'Cindy Hughes',
    'Kelly Hays',
    'James Bailey',
    'Glenn Johnson',
    'John Hudson',
],
    'json': {
    'name': 'Mary Hansen',
    'address': '5806 Brewer Landing\nAimeemouth, NH 55964',
},
    'key73587': 'value65477',
    'key65767': 'value76557',
    'key85713': 'value52012',
    'key78526': 'value69346',
    'key32283': 'value12445',
    'key78158': 'value27524',
    'key85435': 'value94868',
    'key20976': 'value89865',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Christopher Burke',
    'address': '18557 Kiara Spring\nWheelerview, MT 51393',
    'text': 'Treat doctor home mind song whether.\nBusiness man accept people word. Off across news development. Sell hour company class.',
    'email': 'raymondmarks@example.org',
    'phone_number': '485.590.5349x79925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Pena',
    'Alicia Perry',
    'Michael Cole',
    'Thomas Crawford',
    'Dominic Ross',
    'John Stanley DVM',
    'Donna Thompson',
    'Kyle Douglas',
],
    'json': {
    'name': 'Maria Kramer',
    'address': '793 Shannon Center Suite 020\nLake Jaredside, WY 77913',
},
    'key14055': 'value28239',
    'key3040': 'value45660',
    'key35831': 'value44618',
    'key95309': 'value52147',
    'key73022': 'value35176',
    'key15070': 'value3903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Lisa Lawson',
    'address': '6228 Shields Port Suite 931\nSheilamouth, KS 85045',
    'text': 'Medical state hard.\nHe reason free ok reduce.\nSouth into pattern chance indeed receive learn. Order national responsibility reveal. Party away difference investment understand relationship these.',
    'email': 'andrewmoore@example.org',
    'phone_number': '001-730-236-0265x3557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tina Webb',
    'Yvonne Mills',
    'Terri David',
    'Ashley Bryan',
    'Julia Larson',
    'Zachary Brown',
    'Karen Baker',
    'Monica Swanson',
    'Christian Cunningham',
    'Cheyenne Aguirre',
],
    'json': {
    'name': 'Richard Carter',
    'address': '52437 Nicole Wall\nLake Williambury, WA 59502',
},
    'key49570': 'value35785',
    'key61977': 'value30978',
    'key63322': 'value48465',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Brenda Lewis',
    'address': '39843 Robert Highway Apt. 598\nAndrewsfurt, PW 99040',
    'text': 'Their car beautiful sister since threat meet more. East my traditional fact morning citizen marriage.\nGun available also business. Wonder serve research themselves represent.',
    'email': 'traceygonzalez@example.org',
    'phone_number': '(942)529-3255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Frank Jones',
    'Jason Rasmussen',
    'Jacob Calderon',
    'Brandy Cunningham',
    'Julie Daniel',
    'Jennifer Shelton',
    'Christopher Randall',
],
    'json': {
    'name': 'Tony Wu',
    'address': '00419 Christine Ridges\nNew Patricia, ND 54976',
},
    'key4737': 'value10338',
    'key72204': 'value4705',
    'key41753': 'value35914',
    'key98393': 'value54592',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Christopher Patel',
    'address': 'PSC 9115, Box 5340\nAPO AA 70354',
    'text': 'Reduce part watch. Teach score world these recognize officer. Sport right become lose.\nClose group if sit prevent wrong. Raise act may look scientist level natural partner. They theory of arrive.',
    'email': 'jessica89@example.net',
    'phone_number': '327-675-8972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Jones',
    'David Nelson',
    'Kyle Rasmussen',
    'Maria Lamb',
    'Daniel Webb',
    'Adrian Clark',
    'Lori Campbell',
    'Brian Adams',
    'Daniel Harper',
    'Natasha Moore',
],
    'json': {
    'name': 'Samantha Stewart',
    'address': '50236 Daniel Lane\nMicheleland, PR 02353',
},
    'key1111': 'value35557',
    'key38645': 'value68548',
    'key80631': 'value6172',
    'key3406': 'value47128',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Christopher Horton',
    'address': '59838 Jaime Tunnel\nWest Wendyside, NM 97360',
    'text': 'School tough customer necessary.\nCreate same notice book. Investment difference sometimes responsibility major. Mind by strong policy practice.',
    'email': 'samuel45@example.net',
    'phone_number': '(822)204-5480x485',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Ford',
    'Thomas Brown',
    'Bryan Brown',
    'Christian Burke',
    'Melissa Bryant',
    'Stephen Lang',
],
    'json': {
    'name': 'Jennifer Smith',
    'address': '1116 Susan Place\nMelissahaven, MD 46897',
},
    'key68161': 'value42043',
    'key27775': 'value20194',
    'key63223': 'value47007',
    'key70707': 'value62285',
    'key56674': 'value44454',
    'key23251': 'value84623',
    'key51431': 'value29242',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Karen Larson',
    'address': '6032 Pena Parkways\nShelbystad, RI 79216',
    'text': 'Position already analysis candidate produce answer. Table remember yard control never in. Image anyone travel.\nOnto official Mrs unit share. Set watch almost good future through far.',
    'email': 'adambates@example.org',
    'phone_number': '(910)295-4744x114',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Burnett',
    'Jerry Conner',
    'Jessica Burke',
],
    'json': {
    'name': 'Paul Ramos',
    'address': '84809 Whitney Manors Apt. 838\nKarenside, AS 44590',
},
    'key57148': 'value74788',
    'key75545': 'value46351',
    'key97570': 'value26062',
    'key24369': 'value63725',
    'key54134': 'value5280',
    'key43154': 'value18163',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Caroline Orozco',
    'address': '21575 Emily Fork\nLake Lynn, TX 08439',
    'text': 'Strong travel week government collection physical. Officer across wish quickly east focus speech.\nSea land deal move black technology. Better join their trade third may once.',
    'email': 'mrodgers@example.net',
    'phone_number': '(812)278-1413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Walker',
    'Kevin Day',
    'Jamie Mcfarland',
    'Steven Kim',
],
    'json': {
    'name': 'Misty Coleman',
    'address': '77735 Valenzuela Freeway Apt. 337\nEast Diamond, IN 25973',
},
    'key13651': 'value75178',
    'key96403': 'value20870',
    'key53617': 'value46186',
    'key51620': 'value79372',
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
    'RequestId': '1ed88772-62f1-11f0-ae21-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_26_976235IPCmUgIj',
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '181e487c-62f1-11f0-ae4f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_26_976235IPCmUgIj',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_0]_1752744819.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid001752744819Json()
    test.run_tests()
