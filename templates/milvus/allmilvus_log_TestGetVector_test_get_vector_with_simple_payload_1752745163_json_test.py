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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestGetVector_test_get_vector_with_simple_payload_1752745163_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752745163.json"
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



class AllmilvusLogtestgetvectorTestGetVectorWithSimplePayload1752745163Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752745163.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752745163.json"
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
    'RequestId': 'e783150f-62f1-11f0-9b47-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_39_14_925169cwHzFWIS',
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
    'RequestId': 'eaa26f9b-62f1-11f0-8e0b-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_39_14_925169cwHzFWIS',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Angela Schmidt',
    'address': '296 John Row Apt. 097\nPort Kaylamouth, MD 03439',
    'text': 'Part special series. Cultural chance whether page military. Girl those soldier.\nBook card yet word crime. Have west pretty manager accept. Five learn trouble star know nice form.',
    'email': 'pattonpamela@example.com',
    'phone_number': '933-709-0285',
    'array_int_dynamic': [
    26953,
],
    'array_varchar_dynamic': [
    'Roberta Brown',
    'Lori Ford',
    'Dr. William Wolfe',
    'Robert Bishop',
    'Daniel Alexander',
],
    'json': {
    'name': 'Sally Nelson',
    'address': 'PSC 8271, Box 1578\nAPO AE 64537',
},
    'key18057': 'value73993',
    'key36117': 'value4297',
    'key2131': 'value25150',
    'key7930': 'value74283',
    'key36551': 'value34294',
    'key53257': 'value19659',
    'key61299': 'value11345',
    'key40522': 'value15574',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Maxwell Reyes',
    'address': '227 Philip Bridge\nPort Johnnyfort, AL 45185',
    'text': 'None we bed short our let commercial. Treat economy seat others.\nBuild would respond PM move fight behavior. Democratic growth cup series well option thousand.',
    'email': 'smitherin@example.org',
    'phone_number': '+1-606-524-6901x80743',
    'array_int_dynamic': [
    12481,
],
    'array_varchar_dynamic': [
    'Taylor Spencer',
    'Angela Lopez',
    'Ann Romero',
],
    'json': {
    'name': 'Brianna White',
    'address': '895 Smith Lakes\nEvansburgh, AS 33018',
},
    'key23614': 'value18009',
    'key71527': 'value55232',
    'key69896': 'value36591',
    'key29184': 'value8811',
    'key63792': 'value97149',
    'key93138': 'value40840',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Stephen Thompson',
    'address': '102 Charles Corner\nDonaldborough, SC 90271',
    'text': 'Ask fact part film. Art hope gun.\nFood discussion just floor write section word. Near other position.\nWhen cover opportunity reduce image. Floor they traditional cause central add.',
    'email': 'patrickthompson@example.com',
    'phone_number': '403-673-5507x68148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Wallace',
],
    'json': {
    'name': 'Aaron Coleman',
    'address': '2084 Franklin Causeway\nNorth James, PA 09528',
},
    'key79633': 'value49878',
    'key21441': 'value54524',
    'key18766': 'value90406',
    'key45120': 'value30275',
    'key80210': 'value44739',
    'key42448': 'value18586',
    'key3701': 'value78447',
    'key4988': 'value58417',
    'key46946': 'value25188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Sonya Hall',
    'address': '6827 Keith Motorway\nEast Rickeyshire, AS 79385',
    'text': 'Sign travel mission election.\nInterest lawyer question mean area event growth.\nReality size east you tell kitchen look. Indeed mention attorney establish budget.',
    'email': 'whoward@example.net',
    'phone_number': '(678)795-6364x6436',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Martinez',
],
    'json': {
    'name': 'Dean Jackson',
    'address': '66404 Jose Valleys\nJamesland, PA 55935',
},
    'key34243': 'value43391',
    'key64997': 'value26303',
    'key15863': 'value61456',
    'key5232': 'value55678',
    'key8786': 'value8320',
    'key30888': 'value8022',
    'key4574': 'value46941',
    'key51361': 'value47704',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Hannah Small',
    'address': '165 Jason Center\nGomezshire, UT 72136',
    'text': 'Down government measure action add city. Experience impact up realize ok as trouble. Spend responsibility near allow public.',
    'email': 'joseph02@example.org',
    'phone_number': '471.256.0137',
    'array_int_dynamic': [
    85910,
],
    'array_varchar_dynamic': [
    'Mary Clark',
    'Lauren Wyatt',
],
    'json': {
    'name': 'Nicole Simmons',
    'address': 'Unit 0593 Box 8690\nDPO AP 24414',
},
    'key84177': 'value91039',
    'key39761': 'value43189',
    'key77049': 'value72486',
    'key50903': 'value29453',
    'key85729': 'value96362',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Amy Boyd',
    'address': '708 Ramirez Cape\nPort Margaret, ME 51372',
    'text': 'Statement instead threat organization somebody campaign. Protect on size hand trip most.\nWhile growth simply source door lot stay. It feel charge picture remain option.',
    'email': 'christopher35@example.org',
    'phone_number': '+1-922-893-6870x34812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Meagan Stewart',
    'Jenny Friedman',
    'Kayla Collins',
    'Patrick Morris',
    'Shannon Murray',
    'Julie Garcia',
    'Madison Bray',
    'Tracy Franco',
    'Benjamin Wilson',
],
    'json': {
    'name': 'Melissa Hamilton',
    'address': 'USNS Wilson\nFPO AP 19652',
},
    'key6874': 'value12169',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Lacey Sherman',
    'address': '76836 Carroll Port Suite 605\nEast Megan, OK 45489',
    'text': 'Mother yes receive program approach. Nearly threat attorney couple involve concern site scene.',
    'email': 'reginamorgan@example.net',
    'phone_number': '(955)362-5010x531',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Zuniga MD',
    'Sandra Miller',
    'Wendy Wade',
],
    'json': {
    'name': 'Richard Terry',
    'address': '08632 Taylor Tunnel Suite 307\nEast David, VA 07029',
},
    'key96929': 'value79484',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Melissa Deleon',
    'address': '37353 Amanda Lake\nSouth Yolanda, NV 50106',
    'text': 'Figure throughout live. Care just of real civil already. Significant across out own around.',
    'email': 'wendy04@example.com',
    'phone_number': '(866)400-8771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Boyer',
    'Megan Bowman',
    'Timothy Joyce',
    'Jonathan Hunt',
    'Lauren Miller',
    'Donald Miller',
    'Amber Henderson',
],
    'json': {
    'name': 'Diane Thomas',
    'address': '15105 Judy Mission Apt. 257\nHughesland, IA 60835',
},
    'key12456': 'value18683',
    'key29343': 'value32034',
    'key38574': 'value55641',
    'key9442': 'value99988',
    'key11422': 'value34972',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Ronald Gould',
    'address': '763 Ricky Port Suite 983\nLake Daniel, TN 60847',
    'text': 'Nor whole the lose cold daughter performance learn. Likely player yourself course character throw street.',
    'email': 'markknight@example.com',
    'phone_number': '689-552-1488x11028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'John Mcdonald',
    'Stephanie Gibson',
    'Justin Bullock',
    'Aaron Howard',
    'Jacob Lewis',
    'Nina Wolfe',
    'Kevin Jackson',
    'Thomas Hernandez',
],
    'json': {
    'name': 'Jody Bradford',
    'address': '238 Dennis Port Suite 056\nGriffithview, MO 23383',
},
    'key52590': 'value69752',
    'key97646': 'value63258',
    'key7810': 'value29075',
    'key36793': 'value46464',
    'key27177': 'value9644',
    'key18099': 'value1804',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Danielle Fischer',
    'address': '53931 Stewart Prairie\nNew Derek, MA 04876',
    'text': 'Design at against together miss significant field. Eye per picture impact old yet there. Identify cover certainly police thing though.',
    'email': 'whampton@example.net',
    'phone_number': '(252)486-5597',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Acosta',
    'Sarah Rice',
    'Jennifer Ross',
    'Mr. Jeffrey Bryant PhD',
    'Chelsea Howell',
    'Aaron Johnson',
    'Lauren Sutton',
    'Anne Adkins',
],
    'json': {
    'name': 'Kimberly Hickman',
    'address': '3067 Davies Brook\nLake Jose, AK 37109',
},
    'key68505': 'value15674',
    'key36841': 'value72043',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Laura Curtis',
    'address': '3059 Chapman Crescent Apt. 573\nPort Kelliburgh, ME 64172',
    'text': 'Job community simply something. Various game law concern partner green although.\nFeeling place pick game deep measure almost. Six lot line want.',
    'email': 'rogerserika@example.org',
    'phone_number': '207-857-3301x32740',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Wallace',
],
    'json': {
    'name': 'Raymond West',
    'address': '28890 Christopher Mountain Suite 919\nWest Devonborough, MO 94959',
},
    'key88189': 'value13833',
    'key88296': 'value61472',
    'key1461': 'value67720',
    'key82445': 'value14193',
    'key26591': 'value72190',
    'key17501': 'value87022',
    'key18074': 'value26048',
    'key13572': 'value56708',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Melanie Ortiz',
    'address': '647 Schwartz Walk\nBrandiside, HI 23877',
    'text': 'Image south senior work month certainly scene. Now rock anyone information. Create site environmental here price many common.',
    'email': 'phillipskaitlyn@example.net',
    'phone_number': '8139379029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Wagner',
    'Jesse Flynn',
    'Lisa Williams',
    'Hannah Wright',
    'Emily Thornton',
    'Carla Baxter',
    'Jerry Scott',
    'Michael Rogers',
],
    'json': {
    'name': 'Sara Hensley',
    'address': '5301 Summers Oval Apt. 289\nLittleborough, IN 50025',
},
    'key66232': 'value29923',
    'key36824': 'value1014',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Colleen Wheeler',
    'address': '8969 Hayes Canyon Apt. 426\nEast Amandahaven, NC 51448',
    'text': 'Edge often item surface forward. Peace lead short use trade hospital send. Early full artist present upon anything to.',
    'email': 'tony49@example.org',
    'phone_number': '8738869543',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Cox',
    'Jesse Archer',
    'Emily Hall',
],
    'json': {
    'name': 'William Lyons',
    'address': '51167 Jackson Springs Apt. 055\nPort Emily, OK 70946',
},
    'key24567': 'value11743',
    'key77892': 'value29767',
    'key5013': 'value7263',
    'key32221': 'value28012',
    'key18164': 'value62267',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Alicia Rodriguez',
    'address': 'Unit 1594 Box 4887\nDPO AA 00677',
    'text': 'Bag power trial product land gas say including. Fine at same left box.\nChange his pass position specific. Carry west foot past either. Figure stay government short fly produce.',
    'email': 'nmartinez@example.net',
    'phone_number': '241-404-6748x5673',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mary Henry',
    'Christine Green',
    'John Marks',
    'Mr. Shawn Rhodes PhD',
    'Paige Diaz',
    'Debra Jones',
    'Jessica Sexton',
],
    'json': {
    'name': 'Sabrina Yang',
    'address': '851 Boyd Trace Apt. 797\nNicholasfort, IA 29746',
},
    'key85574': 'value14306',
    'key76537': 'value94448',
    'key62987': 'value30662',
    'key16930': 'value12526',
    'key35910': 'value17200',
    'key47985': 'value56933',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Valerie Martinez',
    'address': '890 James Run Suite 424\nLake Allison, WA 62488',
    'text': 'Friend they quite return rock. Apply necessary media off into within.\nFactor theory word fund. List report view base company.',
    'email': 'erica61@example.com',
    'phone_number': '461.367.2615x9841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Murphy',
    'Michael Maynard',
    'Madison Scott',
    'Daniel Richmond',
],
    'json': {
    'name': 'Mr. Brandon Dixon DVM',
    'address': 'Unit 8481 Box 3591\nDPO AA 82826',
},
    'key36721': 'value54481',
    'key45449': 'value18743',
    'key2728': 'value26068',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'James Hickman',
    'address': '10441 Newton Groves Suite 654\nNew Alexandra, AZ 78966',
    'text': 'Trouble attention pick book strong. Technology take produce foreign common city. Candidate including administration development education real.',
    'email': 'waynewilson@example.com',
    'phone_number': '(297)463-9214',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Desiree Wilkins',
    'Maxwell Zamora',
    'Anthony Tucker',
    'Vanessa Ruiz',
    'Tamara Benson',
    'Kayla Hamilton',
    'Tammy Carter',
],
    'json': {
    'name': 'Misty Odom',
    'address': '28456 Hall Mission\nSouth Reneeton, NY 52867',
},
    'key36942': 'value95975',
    'key1408': 'value78243',
    'key19151': 'value24196',
    'key73227': 'value99135',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Mark Turner',
    'address': '27794 Brittany Estates\nNew Bradleybury, WV 38938',
    'text': 'Share physical close another. Father but play personal affect doctor.\nFriend southern week assume similar wear admit. Recently also same add least treatment ball center.',
    'email': 'sanchezapril@example.com',
    'phone_number': '337-979-5294',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Leah Watson',
    'Chelsea Sandoval',
    'Kenneth Romero',
    'Michele Koch',
    'Terrance Riddle',
],
    'json': {
    'name': 'Christopher Colon',
    'address': '0531 Carl Skyway\nCatherinestad, IA 70566',
},
    'key299': 'value13978',
    'key25237': 'value68097',
    'key41235': 'value93238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Amy Cook',
    'address': '62365 Marshall Road Apt. 805\nLake Andrea, KS 08132',
    'text': 'Go many once figure. Public save boy finish agree.\nLot four so determine these learn way. Natural member value before some movement degree better.',
    'email': 'charlespotter@example.net',
    'phone_number': '001-885-753-2669x9133',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Caldwell',
    'Elizabeth Phillips',
    'Michael Sanchez',
    'Mr. Arthur Mann',
    'Angela Peters',
    'Derrick Thomas',
    'Russell Hill',
    'Edward Sims',
    'Kevin Wagner',
    'Annette Thomas',
],
    'json': {
    'name': 'Joseph Bryant',
    'address': 'USCGC Duran\nFPO AA 03906',
},
    'key59960': 'value25125',
    'key91947': 'value16439',
    'key23706': 'value34964',
    'key46386': 'value56133',
    'key46031': 'value61219',
    'key65701': 'value69223',
    'key33986': 'value83494',
    'key49414': 'value45574',
    'key82821': 'value7398',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Rodney Schmidt',
    'address': 'USCGC Harris\nFPO AP 31886',
    'text': 'Year after throw country relationship catch high try. Government myself give. Grow continue herself we.',
    'email': 'mary85@example.com',
    'phone_number': '+1-324-670-0311x33326',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Bates',
    'Brian Trujillo',
],
    'json': {
    'name': 'Samuel Lucas',
    'address': '19114 Sheri Shoals\nPort Rhondaberg, HI 43466',
},
    'key91590': 'value41803',
    'key5085': 'value68297',
    'key66833': 'value98934',
    'key86155': 'value33579',
    'key32737': 'value65444',
    'key38452': 'value91571',
    'key74950': 'value82233',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Cassandra Miles',
    'address': '97326 Garcia Creek\nNew Debrafort, PA 65097',
    'text': 'Simply take practice I sit. Rate should that walk tough. Agreement agree the if music official conference.\nChurch somebody cause. Together time generation player friend house skill.',
    'email': 'lisa40@example.org',
    'phone_number': '001-549-904-7725',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Belinda Adams',
    'Nicole Anderson',
    'Carolyn Hernandez',
    'Jordan Owens',
    'Jonathan Johnson',
    'Bethany Foster',
    'Dr. Ashlee Lopez',
],
    'json': {
    'name': 'Anthony Fernandez',
    'address': '20971 Bradley Lodge Apt. 761\nPort Lee, MT 17435',
},
    'key51809': 'value79454',
    'key96040': 'value48341',
    'key62427': 'value24454',
    'key41761': 'value19593',
    'key22598': 'value13434',
    'key90649': 'value24976',
    'key28198': 'value42633',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Mrs. Cheryl Vincent',
    'address': '46378 Parker Station\nWest Elizabeth, AS 82411',
    'text': 'Century cold chance vote word participant from. Change step bed organization. Ok smile must close institution head.',
    'email': 'collinsjennifer@example.com',
    'phone_number': '(223)430-6961x2261',
    'array_int_dynamic': [
    71449,
],
    'array_varchar_dynamic': [
    'Richard Good',
    'Michael Barry',
    'Chelsea Fox',
    'Sandra Newman',
    'Larry Dixon',
    'Stephanie Martinez',
    'Kimberly Moreno',
    'Robert Young',
],
    'json': {
    'name': 'Rachel Booth MD',
    'address': '40986 Andrea Motorway Suite 553\nPort Austinfort, TX 28091',
},
    'key53831': 'value69808',
    'key8676': 'value15612',
    'key3955': 'value69610',
    'key96460': 'value53663',
    'key35333': 'value23596',
    'key8804': 'value25978',
    'key11424': 'value1531',
    'key67204': 'value53675',
    'key80938': 'value32306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Eric Miranda',
    'address': '3152 Christina Mews Apt. 016\nMendozaton, PA 60828',
    'text': 'Those try near sea see trip ok. Take sure matter help point.\nFight meeting decade pretty final price. Any PM right use industry let. Answer evidence book woman serious pressure.',
    'email': 'miranda98@example.net',
    'phone_number': '(260)492-3765x53614',
    'array_int_dynamic': [
    45727,
],
    'array_varchar_dynamic': [
    'Jacqueline Kelly',
    'Rita Yoder',
    'Tiffany Wilson',
    'Jeremy Ward DDS',
    'Erika Reed',
],
    'json': {
    'name': 'Amy Brown',
    'address': '53743 Jones Tunnel Apt. 006\nLeebury, CA 92335',
},
    'key3573': 'value67851',
    'key57806': 'value93768',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Stephanie Allen',
    'address': 'PSC 1527, Box 9257\nAPO AA 55882',
    'text': 'Amount leave turn radio family politics. Clearly mission live party.\nStock meet simply today wrong. Drug away natural simple attention and hundred wrong. Mean race even commercial spend evidence.',
    'email': 'javierroberts@example.org',
    'phone_number': '499.566.4628',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Edward Johnson',
],
    'json': {
    'name': 'Richard Peterson',
    'address': '573 Bell Mount\nNorth Richardton, MO 70866',
},
    'key54632': 'value65651',
    'key96317': 'value40981',
    'key65244': 'value59545',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Heather Callahan',
    'address': 'PSC 3465, Box 5162\nAPO AE 44215',
    'text': 'Computer technology either run.\nBed star including or. Respond she war operation bring administration race figure.',
    'email': 'lhamilton@example.net',
    'phone_number': '371.813.8835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Paul Parker',
    'Shannon Mathis',
    'Sarah Luna',
    'Matthew Fischer',
    'Vanessa Ali',
    'Natalie Lewis',
],
    'json': {
    'name': 'Mr. Anthony Williams',
    'address': '2087 Kayla Vista Apt. 783\nNew Heather, NJ 82495',
},
    'key11696': 'value16660',
    'key20015': 'value76481',
    'key40260': 'value30300',
    'key70109': 'value21994',
    'key21184': 'value98819',
    'key65803': 'value3588',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Christy Beltran',
    'address': '97182 Daisy Spring Apt. 859\nJosephburgh, CA 04003',
    'text': 'Drive true morning impact notice until. Politics huge describe six. Child skin daughter together truth perform.',
    'email': 'wendyhurley@example.org',
    'phone_number': '(486)223-2018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Cummings',
    'Tracy Jones',
    'Tony Gordon',
],
    'json': {
    'name': 'Nicole Lee',
    'address': '3364 Kelsey Turnpike Suite 973\nNew Ashleyton, MI 70148',
},
    'key5641': 'value9839',
    'key8664': 'value97069',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jeffrey Perez',
    'address': 'PSC 3032, Box 8110\nAPO AA 53590',
    'text': 'Mission act spend certainly beyond political. Early current hand.\nLetter end car car. Leader eight stop big conference policy standard. Strong happy may politics accept decade resource.',
    'email': 'kristi05@example.org',
    'phone_number': '216-696-2147x169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brent Snyder',
    'Dale Powers',
    'Dana Wolf',
    'Joel Welch',
    'Gregory Deleon',
    'Timothy Griffin',
    'Natasha Vasquez',
    'Micheal Ramos',
    'Richard Flores',
    'Stephen Hansen',
],
    'json': {
    'name': 'Stephen Taylor',
    'address': 'USNV Owen\nFPO AA 43836',
},
    'key15081': 'value55332',
    'key50551': 'value87993',
    'key74869': 'value8946',
    'key29652': 'value26621',
    'key31866': 'value98022',
    'key71939': 'value41406',
    'key55836': 'value26798',
    'key2587': 'value55705',
    'key36693': 'value83239',
    'key89798': 'value21498',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Leslie Dunlap',
    'address': '62987 Antonio Forest\nNew Sheila, MN 61971',
    'text': 'Strong or everyone coach direction across. Travel spend difficult case might. Result personal same.\nBlack rate including election. They behavior range something heart yes fine do.',
    'email': 'charles96@example.com',
    'phone_number': '384.517.8107x70872',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Parker',
    'Chelsea Burke',
    'Andrea Smith',
    'Stephanie Mcguire',
    'Katie Holland',
    'Vincent Robertson',
    'Erika Peterson',
    'Melissa Smith',
    'Alexis Huerta',
],
    'json': {
    'name': 'Daniel Grant',
    'address': '6662 Susan Spurs\nNorth Scott, NC 99513',
},
    'key62188': 'value11409',
    'key2': 'value42982',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Lonnie Jones',
    'address': '13430 Jared Glen Apt. 884\nSouth Gregoryberg, ME 11324',
    'text': 'Five some early painting enjoy look. Set develop establish.\nAllow fight order say outside. Whole not threat American. Do sign morning.',
    'email': 'melissadoyle@example.com',
    'phone_number': '365-856-7679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Chandler',
    'Veronica Guerrero',
    'Garrett Wells',
],
    'json': {
    'name': 'Robert Hahn',
    'address': '744 Stevens Rue\nNorth Tiffany, KS 94734',
},
    'key24568': 'value41926',
    'key44641': 'value71670',
    'key23745': 'value63670',
    'key38737': 'value20117',
    'key41591': 'value16043',
    'key84772': 'value38239',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Amanda Simmons',
    'address': '582 Ryan Common\nKochborough, NC 04619',
    'text': 'Here want ball share no environment receive. Election account this crime. Major film him account reduce best.\nSomething a bit focus market fill laugh. Become instead you school wrong strong court.',
    'email': 'wallacemary@example.org',
    'phone_number': '001-737-909-9194x9568',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Bender',
],
    'json': {
    'name': 'Amanda Hughes',
    'address': '252 Jeremy Lodge Apt. 310\nHallmouth, DE 99514',
},
    'key63258': 'value50786',
    'key66848': 'value21046',
    'key55994': 'value55523',
    'key1965': 'value42385',
    'key78286': 'value33028',
    'key40301': 'value26380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Kathryn Hardin',
    'address': '0914 Yvonne Row\nWest Bradley, MD 02544',
    'text': 'Article anything various effect decide upon. Area season cultural speak fall short moment fight. Apply star risk window.\nProtect network list make ask gas. Event effect tough bed professor.',
    'email': 'hillann@example.com',
    'phone_number': '451.987.2402',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert Torres',
    'Kelly Hernandez',
    'Keith Brown',
    'Erika Barnett',
    'Krystal Brown',
    'Glenn Flores',
    'Heather Barnett',
    'Brittney Wolf',
],
    'json': {
    'name': 'Amanda Daniel',
    'address': '451 Ronnie Court Apt. 701\nNorth Michael, LA 66011',
},
    'key65131': 'value6630',
    'key97987': 'value69705',
    'key92977': 'value20508',
    'key80395': 'value91299',
    'key75422': 'value82359',
    'key19057': 'value65375',
    'key9672': 'value91912',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Rebecca Munoz',
    'address': '4299 Linda Valleys Suite 914\nSimmonsborough, GU 30559',
    'text': 'Could now ground cut improve figure contain. Eye huge take environmental.',
    'email': 'ryannguyen@example.com',
    'phone_number': '724.840.0369',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Pham',
    'Nancy Copeland',
    'Isaiah Berg',
    'Valerie Foster',
    'Andrea Jackson MD',
    'Emily Martinez',
    'Laura Dickerson',
    'Amanda Patterson',
    'John Willis',
    'Angela Martinez',
],
    'json': {
    'name': 'Adriana Wagner',
    'address': '233 Lane Heights Apt. 740\nNew Connorport, IL 93964',
},
    'key16187': 'value78434',
    'key69182': 'value67777',
    'key62808': 'value72239',
    'key46698': 'value87355',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Jonathan Montgomery',
    'address': '3937 Pacheco Spur Suite 688\nPort Seanstad, OR 28029',
    'text': 'Appear picture fight foreign. Crime hear road author rule.\nMost than garden weight amount relate seat. Reflect increase only four.',
    'email': 'rmiles@example.net',
    'phone_number': '(395)939-0677x82342',
    'array_int_dynamic': [
    11737,
],
    'array_varchar_dynamic': [
    'Kenneth Parks',
    'Andrew Rush',
    'Jonathan Gilbert',
    'Matthew Cooper',
    'Allison Rodriguez',
],
    'json': {
    'name': 'Douglas Cisneros',
    'address': '730 Browning Coves\nNorth Charlesfurt, MD 21382',
},
    'key72183': 'value85936',
    'key58413': 'value69658',
    'key56028': 'value504',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Lisa Sheppard',
    'address': '807 Kristina Locks Suite 847\nEast Jasminemouth, VI 72297',
    'text': 'Order not order room whether. Sense former here north fight.\nStill black read stage stuff report popular. Former explain up ever among let customer whatever. Run TV then big.',
    'email': 'sandy18@example.com',
    'phone_number': '+1-692-710-8537',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Rodriguez MD',
    'Joshua Hall',
    'Shawn Holland',
    'James Hess',
    'Joseph Costa',
],
    'json': {
    'name': 'Kyle Smith',
    'address': '6804 Sabrina Walks\nDouglasbury, MD 92884',
},
    'key36473': 'value4463',
    'key17449': 'value78655',
    'key81184': 'value65905',
    'key88910': 'value18392',
    'key81260': 'value43014',
    'key28676': 'value74766',
    'key35413': 'value11266',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Sherry Edwards',
    'address': '91430 Sharon Haven\nLake Jessicashire, NH 03455',
    'text': 'Ready simple direction pressure where concern. Interview any inside share manager share. After meet four leg necessary nothing report.\nFinancial word participant yet. Land case will record.',
    'email': 'sarahparker@example.net',
    'phone_number': '653-866-6372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Martinez',
    'Darrell Johnson',
],
    'json': {
    'name': 'Richard Grant',
    'address': '620 Simpson Burgs\nPort Christopherberg, NV 93247',
},
    'key41610': 'value44775',
    'key60463': 'value73772',
    'key97456': 'value33694',
    'key97027': 'value23203',
    'key47472': 'value54214',
    'key71923': 'value57804',
    'key60022': 'value73478',
    'key5408': 'value19178',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Andrew Roberts',
    'address': '0985 Rodriguez Glens Apt. 747\nNorth Kristinmouth, PR 31926',
    'text': 'Computer actually join sing. Today parent brother effort.\nDuring real policy low road. Late road last.\nMiddle research compare thought plan. Woman do week already weight throw.',
    'email': 'uhiggins@example.org',
    'phone_number': '001-338-536-3452x47566',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Williams',
    'Bryan Brewer',
    'Carolyn Foster',
    'Tiffany Bailey',
    'Laura Howell',
    'Steven Walls',
    'Jamie Day',
    'Terri Velasquez',
    'Lori Wright',
    'Nicole Collins',
],
    'json': {
    'name': 'Donald Weaver',
    'address': '1987 Colleen Stream Suite 493\nGregorystad, NC 68581',
},
    'key22941': 'value24488',
    'key16580': 'value68205',
    'key66829': 'value2759',
    'key79705': 'value68076',
    'key58445': 'value76769',
    'key7258': 'value51518',
    'key54744': 'value17768',
    'key69984': 'value22375',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Brooke Galloway',
    'address': '67747 Fox Place Apt. 120\nLake Joeberg, ME 17048',
    'text': 'Quality red for. Ready lead tough risk. Manage chance purpose this.\nInstead moment five front response force. Suddenly box mind positive.\nWalk note half about better from full prevent.',
    'email': 'howelljesse@example.net',
    'phone_number': '+1-692-890-6117x08125',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jillian Harrison',
    'Emma Brooks',
    'Rachael Smith',
    'Michael Johnson',
    'Tonya Mullins',
    'Sheila Lang',
    'Clayton Chen',
],
    'json': {
    'name': 'Linda Nunez',
    'address': '78810 Miller Circle Apt. 576\nPort Jeremiah, SD 11345',
},
    'key16492': 'value82533',
    'key81733': 'value80027',
    'key35841': 'value38764',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Alicia Horne',
    'address': '334 Hall Bridge Suite 108\nJuanfurt, VA 10614',
    'text': 'Always art late play. Spend from goal me hit stay often. Job wrong subject compare.\nIssue suddenly population we agent. Same full foot run. Other no hold short.',
    'email': 'umartinez@example.com',
    'phone_number': '978.596.2033x606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Karen Harris',
    'Gregory Turner',
    'Jerry Herman',
],
    'json': {
    'name': 'Dillon Johns',
    'address': '841 David Ford Suite 240\nAlexberg, OR 82322',
},
    'key54220': 'value90562',
    'key63490': 'value54253',
    'key58507': 'value77862',
    'key42946': 'value59735',
    'key60611': 'value86445',
    'key84747': 'value99461',
    'key54587': 'value26347',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Kathleen Jackson',
    'address': 'Unit 9952 Box 7810\nDPO AA 03241',
    'text': 'Activity truth television great. Light site foot upon man guy movement. Fear clear improve campaign.\nVarious maintain condition especially city behavior. Number reason wall arrive even age.',
    'email': 'jennifer33@example.com',
    'phone_number': '325.877.4417x1535',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Bowman',
    'Taylor Griffin',
    'Micheal Roach',
    'Diana Davis',
    'Sherri Ferguson',
],
    'json': {
    'name': 'Shannon Riggs',
    'address': '2333 Sierra Stravenue\nDianaton, IN 33408',
},
    'key23818': 'value7056',
    'key60213': 'value35951',
    'key13165': 'value47639',
    'key2498': 'value34978',
    'key38145': 'value12552',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Timothy Spence',
    'address': '533 Tran Valleys\nEast Richard, PA 26048',
    'text': 'Less customer guess establish mouth. Entire theory class model who may morning.\nMr hair itself as. Report suddenly budget none behind.',
    'email': 'changbrian@example.net',
    'phone_number': '776-762-8609',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Mason',
    'Michael Scott',
    'Jason Higgins',
    'Connor Oconnell',
    'David Shaw',
    'Connie Paul',
    'Daniel Schwartz',
    'Zachary Holt',
    'Theresa Mcpherson',
],
    'json': {
    'name': 'Jessica Butler',
    'address': 'PSC 8809, Box 9666\nAPO AA 82034',
},
    'key13344': 'value96452',
    'key38464': 'value73644',
    'key60336': 'value44095',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jared Hart',
    'address': '07381 Kenneth Landing Suite 254\nPort Kyleshire, VT 22992',
    'text': 'Name they several site me. Fish report four response third ever six agree.\nAlthough policy lawyer career paper. Popular include service energy.\nSource address them perform.',
    'email': 'nathan57@example.com',
    'phone_number': '001-421-285-4578x0281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Delacruz',
    'Kimberly Smith',
    'Matthew Nicholson',
    'Victor Oconnor',
    'Tony Hall',
    'Tamara Campos',
    'John Walker',
    'Beth Moore',
    'Chad Taylor',
],
    'json': {
    'name': 'Rebecca Jackson',
    'address': '19808 William Radial\nWest Markborough, AL 75113',
},
    'key69236': 'value46831',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Anthony Parrish',
    'address': '23077 Ebony Meadow\nErikaville, FL 26994',
    'text': 'Skin church card always best degree answer billion. Baby country firm south. Answer behind discussion the take you.\nReflect keep recent stop image not. Yard while less picture trial fire act.',
    'email': 'mary53@example.org',
    'phone_number': '001-906-526-6397x521',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kristin Wolfe',
    'Shane Williams',
    'Ashley Nelson',
    'Donald Stevens',
],
    'json': {
    'name': 'Jeffrey Parrish',
    'address': '2949 Daniels Harbor\nJulieside, AS 11293',
},
    'key4122': 'value3329',
    'key85066': 'value20508',
    'key77762': 'value3465',
    'key31145': 'value97399',
    'key32805': 'value13246',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Joseph Walker',
    'address': '905 Smith Stravenue Suite 582\nLauraberg, CT 61219',
    'text': 'Idea must chance red detail list. Capital style discover resource group vote.\nDescribe moment information so her tree. Table control itself into pressure experience.',
    'email': 'michellehuffman@example.org',
    'phone_number': '5915341957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Renee Wiley',
    'Tony Obrien',
],
    'json': {
    'name': 'Ryan Garcia',
    'address': '274 Albert Ford Apt. 987\nElizabethport, KY 88297',
},
    'key96986': 'value6004',
    'key73183': 'value23440',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Evelyn Powell',
    'address': '79500 Michael Orchard Apt. 290\nNew Timothystad, NY 18999',
    'text': 'Forward by media election. Model wonder school.\nInterest wide cell present. Best always court who public fact large. Often throughout beautiful lay growth difference far.',
    'email': 'anthony86@example.org',
    'phone_number': '4324451843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jill Barber',
    'Jeremy Terrell',
    'Brandon Johnson',
    'Whitney Espinoza',
    'Jacob Mejia',
    'Michael Summers',
    'Jimmy Rios',
    'Ashley Perez',
    'Sarah Gray',
    'Melissa Mitchell',
],
    'json': {
    'name': 'Kimberly Green',
    'address': '1769 Robin Extension Suite 421\nRussellside, MT 35035',
},
    'key62480': 'value94518',
    'key39381': 'value27481',
    'key43265': 'value23649',
    'key40054': 'value72820',
    'key60939': 'value90902',
    'key79943': 'value73017',
    'key3055': 'value99606',
    'key19099': 'value54371',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Judith Guerra',
    'address': 'PSC 2331, Box 3556\nAPO AA 01285',
    'text': 'Investment man star model. General later morning cup. Suddenly garden carry alone quality.\nArrive bag want design. Imagine cause Democrat our.',
    'email': 'collincardenas@example.net',
    'phone_number': '+1-795-259-5344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Luis Gomez',
    'Dennis Miller',
    'Jamie Wood',
    'James Fuller',
    'Timothy Hayes',
    'Jamie Kelly',
    'Bobby Chandler',
    'Amy Pennington MD',
    'Hayden Murphy',
    'Mrs. Michelle Lewis',
],
    'json': {
    'name': 'Sharon Simpson',
    'address': '384 Gerald Knoll\nMelissafort, AL 00913',
},
    'key31371': 'value60571',
    'key45684': 'value28207',
    'key12879': 'value73349',
    'key92038': 'value40466',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Jill Miller',
    'address': '8508 Deborah Field Suite 853\nPort Lauriefort, WY 19567',
    'text': 'Week term much eight down. Tough special cultural move. Old gas anything type. Girl say its stop including enough listen.',
    'email': 'russellpamela@example.com',
    'phone_number': '+1-293-384-3061',
    'array_int_dynamic': [
    58803,
],
    'array_varchar_dynamic': [
    'Stephanie Gray',
    'Megan Davis',
    'Joel Vang',
],
    'json': {
    'name': 'Richard Jones',
    'address': '1777 Patel Harbors Suite 893\nNorth Ann, DC 35207',
},
    'key30220': 'value54057',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Danielle Scott',
    'address': '77976 Bradley Locks\nSouth Toddhaven, AK 17607',
    'text': 'Within he research much exist. Push teacher people include.\nEffect have commercial company my conference. How soon choose away parent forward argue.',
    'email': 'fcollins@example.com',
    'phone_number': '(827)792-6148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Chang',
    'Jessica Stephens',
    'Ricardo Gilbert',
],
    'json': {
    'name': 'Donald Kelley',
    'address': '977 Jimenez Court Suite 625\nJuliefort, AR 05602',
},
    'key95207': 'value10805',
    'key86113': 'value62422',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Benjamin Butler',
    'address': '964 Melissa Glens Apt. 286\nLake Elijah, NC 42092',
    'text': 'Local figure write professor half draw able million. Real administration project phone. Subject much hundred.\nThey stay ago. Hospital parent wish task arrive movement. Theory effect nature friend.',
    'email': 'alexandra39@example.org',
    'phone_number': '882.258.6528x545',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Holder',
    'David Rice',
    'Cameron Williams',
    'Cynthia Ramsey',
    'Dean Jenkins',
],
    'json': {
    'name': 'Timothy Hess',
    'address': '93265 Brown Tunnel\nMedinafurt, CO 06681',
},
    'key46736': 'value66019',
    'key72006': 'value78865',
    'key63952': 'value39103',
    'key28777': 'value49121',
    'key35803': 'value77744',
    'key40407': 'value353',
    'key69620': 'value42635',
    'key34073': 'value86338',
    'key93443': 'value60948',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Susan Anderson',
    'address': '0107 Mcgrath Manor\nSimmonsfort, VI 73529',
    'text': 'Wear baby analysis matter light imagine possible. Easy director not later it. Bring always college never all support.\nNeed may far group behavior.',
    'email': 'dawn65@example.org',
    'phone_number': '4122022075',
    'array_int_dynamic': [
    69796,
],
    'array_varchar_dynamic': [
    'Gabrielle Rodriguez',
    'Christopher Hill',
    'Cathy Jones',
    'Alexis Williams',
    'Sandra Taylor',
    'Melissa Wood',
],
    'json': {
    'name': 'Timothy Ewing',
    'address': '78335 Reeves Ramp Suite 456\nNew Evelynshire, NJ 77569',
},
    'key22094': 'value25260',
    'key27099': 'value77489',
    'key94429': 'value97947',
    'key39852': 'value69045',
    'key20408': 'value1873',
    'key15286': 'value36232',
    'key76733': 'value6315',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Eduardo Jimenez',
    'address': '910 Brittany Street\nNew Joan, TN 34166',
    'text': 'Can suggest every listen yet. Power source reality responsibility ability skill. Can white reduce most.\nAnd street city former. Idea property lay most region tend.',
    'email': 'catherinemartinez@example.com',
    'phone_number': '598.586.6028x9660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Davidson',
],
    'json': {
    'name': 'Michael Sanders',
    'address': 'PSC 9608, Box 8065\nAPO AP 84904',
},
    'key83929': 'value57854',
    'key45731': 'value94946',
    'key35510': 'value7702',
    'key29941': 'value38459',
    'key42025': 'value33162',
    'key30719': 'value29360',
    'key618': 'value49411',
    'key96365': 'value58797',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Justin Jackson',
    'address': '163 Steven Road\nSteelefort, MO 98508',
    'text': 'None part language onto night market. Generation daughter response song possible suggest action continue. Ago improve animal bring beyond growth capital nothing.',
    'email': 'griffinkimberly@example.org',
    'phone_number': '+1-901-738-5390x61517',
    'array_int_dynamic': [
    75559,
],
    'array_varchar_dynamic': [
    'Andrew Franklin',
    'Margaret Miller',
    'Meredith Smith',
    'Harry Christensen',
],
    'json': {
    'name': 'Karl Stevens',
    'address': '6453 Sara Burgs Apt. 265\nEast Brentmouth, ID 13187',
},
    'key781': 'value24005',
    'key52714': 'value86417',
    'key33659': 'value54126',
    'key52037': 'value12418',
    'key70795': 'value12774',
    'key72310': 'value67855',
    'key21512': 'value79409',
    'key27704': 'value4523',
    'key36312': 'value65747',
    'key71480': 'value54306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Eugene Garcia',
    'address': '56260 Jasmin Cape Apt. 977\nLisaland, ME 99789',
    'text': 'Seek season pass. Day everybody middle manager. Brother there white list weight.\nTonight ten chair teach yet. Season occur writer well night government either article.',
    'email': 'judy60@example.org',
    'phone_number': '001-273-655-1140x916',
    'array_int_dynamic': [
    65690,
],
    'array_varchar_dynamic': [
    'Todd Salas',
    'Scott Morris',
    'Mary Berry',
    'Gabriel Riddle',
    'Megan Moore',
    'Mr. Brandon Willis',
],
    'json': {
    'name': 'Deanna Collins',
    'address': '1470 Navarro Bridge\nSpencerchester, FM 32131',
},
    'key70623': 'value33216',
    'key95359': 'value70853',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kenneth Johnson',
    'address': '61054 Timothy Views Apt. 471\nAngelafurt, CA 39775',
    'text': 'Different card before open. Direction choice produce executive.\nCustomer late send take order until grow.',
    'email': 'daniel74@example.org',
    'phone_number': '291.844.9964',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Cameron',
    'Rebecca Hamilton',
    'Tara Walker',
    'Debra Kelly',
    'Renee Robles',
    'Destiny Moreno',
    'Becky Delacruz',
    'William Hill',
    'Patricia Abbott',
    'Zachary Terry',
],
    'json': {
    'name': 'Aaron Schneider',
    'address': 'PSC 6428, Box 6841\nAPO AP 90009',
},
    'key3526': 'value2976',
    'key91516': 'value64068',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Heather Phillips',
    'address': 'PSC 6008, Box 1432\nAPO AA 75528',
    'text': 'Physical toward effect story exist meet from. Society lawyer painting positive likely itself kitchen. Miss growth authority stay just yeah carry.',
    'email': 'matthew93@example.org',
    'phone_number': '+1-225-994-8870x5306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Carly Hernandez',
    'David Moore',
    'Tara Smith',
],
    'json': {
    'name': 'Patrick Davis',
    'address': '561 Gutierrez Mount\nNorth Angelastad, PR 69853',
},
    'key20239': 'value81329',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Kevin Jimenez',
    'address': '045 Moore Port Apt. 991\nGomezbury, IN 22740',
    'text': 'Actually owner teacher among. Give long them to Republican.\nAnd around go garden option public. Woman listen evidence upon and time.',
    'email': 'shawn18@example.org',
    'phone_number': '+1-745-716-4246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Stephens',
    'Felicia Jackson',
    'Christine Miller',
    'Carla Ruiz',
    'Barbara Beltran',
],
    'json': {
    'name': 'Jessica Morgan',
    'address': 'Unit 3992 Box 5473\nDPO AE 96637',
},
    'key15791': 'value26374',
    'key9028': 'value71755',
    'key92680': 'value24813',
    'key55660': 'value5950',
    'key59881': 'value43254',
    'key77693': 'value64927',
    'key996': 'value62185',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Ronald Hicks',
    'address': '97074 Elizabeth Course Apt. 473\nSouth Stephanie, PA 84318',
    'text': 'Beat bar if meeting article available. Television about here. Name world recognize affect policy writer.',
    'email': 'nicholas80@example.org',
    'phone_number': '260.649.2953x0872',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Rhonda Mcclure',
    'Thomas Davis',
    'Ashlee Henry',
    'Justin Thomas',
    'Benjamin Wolf',
    'Mark Warren',
    'Meghan Thompson',
    'Mrs. Amy Hicks MD',
    'Christopher Jones',
    'Jose Smith',
],
    'json': {
    'name': 'Sherry Pierce',
    'address': '214 Hicks Meadows Suite 367\nRobertmouth, PA 71282',
},
    'key25972': 'value81199',
    'key66622': 'value33150',
    'key84168': 'value95972',
    'key86149': 'value42928',
    'key96431': 'value98624',
    'key73409': 'value18782',
    'key86522': 'value38197',
    'key99046': 'value25667',
    'key67674': 'value77359',
    'key32556': 'value10913',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Cheryl Williams',
    'address': '45532 Adams Mountains\nWhitneyshire, IL 45839',
    'text': 'Painting government phone production information. Exist charge its democratic politics mind probably. Them rate structure because. Accept visit try risk focus.',
    'email': 'brendawilliams@example.com',
    'phone_number': '(615)792-4855x378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Kennedy',
    'Wayne Burns',
    'Christopher Jenkins',
],
    'json': {
    'name': 'Patricia Edwards',
    'address': '82267 Brown Parkway\nLake Zacharyfurt, IN 11400',
},
    'key20278': 'value31657',
    'key17398': 'value7656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Jason Payne',
    'address': '46827 Alexander Cape Suite 232\nNorth Rebeccaburgh, VT 24252',
    'text': 'Scene small for school leg. Couple or which high institution. City reduce physical site test although.\nAll everyone word trade. After lawyer travel. Bar up force.',
    'email': 'sarah10@example.net',
    'phone_number': '001-459-979-2118x116',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Angela Chang',
    'Steven Rivera',
    'Emily Adams',
    'Jaime Wood',
    'George Davis',
    'Mario Bennett',
    'Jacob Fischer',
    'David Gray',
    'Gabriella Le',
    'Christopher Anthony',
],
    'json': {
    'name': 'Tina Black',
    'address': '1388 Matthew Mission Apt. 506\nLopezmouth, ND 90755',
},
    'key40065': 'value79282',
    'key40458': 'value45079',
    'key49568': 'value26677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Matthew Mills',
    'address': '433 John Roads Suite 996\nEast Matthewport, IL 65064',
    'text': 'Front run idea difference. Various section near around shake information song.\nDifferent easy various example. Heart week environmental garden.',
    'email': 'gregorymelissa@example.net',
    'phone_number': '(980)636-8372x75135',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Troy Mitchell',
    'Amanda Smith',
    'Tiffany Mcclain',
    'Kathleen Mitchell',
    'Patrick Zamora',
    'Scott Santiago',
    'Holly Turner',
],
    'json': {
    'name': 'Deborah Bradford',
    'address': '833 Rogers Shores Suite 600\nJamiechester, NH 34317',
},
    'key19958': 'value9429',
    'key76376': 'value56131',
    'key47051': 'value34377',
    'key26489': 'value84565',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Allen Wong',
    'address': '87239 Sarah Course Suite 022\nHolmesmouth, MS 17791',
    'text': 'Claim people final for career health.\nQuality shake the report group citizen. Factor office Republican represent chair all sea. Half can risk happen suggest.',
    'email': 'bconner@example.net',
    'phone_number': '910-583-6812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Webb',
    'Christy Watkins',
    'Kristina Miller',
    'Benjamin Flores',
    'Paul Chen',
    'Daniel Montes',
    'Jennifer Green',
],
    'json': {
    'name': 'Justin Newton',
    'address': '419 Rios Ridge Apt. 905\nNorth Mary, WA 00524',
},
    'key59822': 'value66059',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'James Lynch',
    'address': '1208 Aaron Squares Suite 369\nKimshire, ME 92377',
    'text': 'Wonder attorney candidate current range follow senior. Laugh dream pick visit up us. Against end officer specific bill. Teach parent view exist may everybody reason.',
    'email': 'lauren34@example.com',
    'phone_number': '(426)782-2975x6453',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Frank Santos',
],
    'json': {
    'name': 'David Green',
    'address': '27221 Perez Fall Suite 561\nSellerschester, TX 53145',
},
    'key32514': 'value72260',
    'key31382': 'value14727',
    'key5312': 'value76726',
    'key89551': 'value59527',
    'key73024': 'value70937',
    'key94878': 'value79938',
    'key31270': 'value65639',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Nicholas Dunn',
    'address': '244 Gabriella Street\nTeresabury, IL 81712',
    'text': 'Nice student far interview program could. Part into significant television price. Firm bag thank every ready could. Bad under exist reach write.\nBlood pass economy agreement admit range marriage.',
    'email': 'morenojoshua@example.org',
    'phone_number': '(475)602-3906x704',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Randy Bell',
    'Sarah Martin',
    'Michael Glenn',
    'Ashlee Rodriguez',
    'Erika Cox',
    'Amy Johnson',
    'Randy Schmidt',
    'Kelly Sandoval',
],
    'json': {
    'name': 'Joseph Richards',
    'address': '3292 Tiffany Roads\nTonihaven, FM 91283',
},
    'key27736': 'value62526',
    'key75965': 'value47267',
    'key9264': 'value81116',
    'key89383': 'value64023',
    'key5101': 'value40915',
    'key6785': 'value5480',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Patrick Johnson',
    'address': '017 Michael Circles\nNew Timothyside, AR 69093',
    'text': 'Moment memory crime create knowledge others. Item quickly present away. Issue measure too but ago audience strategy late.',
    'email': 'jameswilliams@example.net',
    'phone_number': '001-766-324-3300x26382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Kelley',
    'Melissa Roberts',
    'Ryan Cook',
],
    'json': {
    'name': 'Alexander Snyder',
    'address': '782 Robert Land\nCurryville, NJ 96227',
},
    'key86089': 'value53074',
    'key66962': 'value34998',
    'key67643': 'value95927',
    'key35184': 'value9997',
    'key17671': 'value6317',
    'key77307': 'value66696',
    'key96294': 'value55877',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Manuel Moore',
    'address': 'Unit 4815 Box 2670\nDPO AA 26780',
    'text': 'Pass let father quite federal wall summer play. Job add customer keep authority realize.\nToward lawyer ask choose. Item recently course military join.',
    'email': 'marcus39@example.net',
    'phone_number': '(292)887-8528x4448',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Suzanne Reynolds',
    'Douglas Rodgers',
    'Thomas Gonzalez',
],
    'json': {
    'name': 'Nicole Stafford',
    'address': '911 Lopez Ports Apt. 188\nEast Christopherville, MT 87298',
},
    'key42341': 'value6265',
    'key98604': 'value44061',
    'key13022': 'value60697',
    'key8618': 'value46752',
    'key40944': 'value32456',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mrs. Jennifer Sanchez',
    'address': '6209 Skinner Lodge Apt. 334\nBriantown, TX 30107',
    'text': 'Although live food bit bed big realize cold. Subject weight street fly former blood artist. Congress reflect region choose else loss.\nGround hold color name. Course worker interview security.',
    'email': 'jacqueline62@example.net',
    'phone_number': '+1-726-836-7730x13805',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Atkinson',
    'Kevin Green',
    'Michael Barton',
],
    'json': {
    'name': 'Krista Hicks',
    'address': '6892 Colton Shores Apt. 218\nGrayville, OR 50771',
},
    'key79288': 'value66187',
    'key94345': 'value20081',
    'key62005': 'value46219',
    'key55550': 'value96509',
    'key90483': 'value77131',
    'key27289': 'value86928',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Mary Bailey',
    'address': 'PSC 7790, Box 7439\nAPO AE 71581',
    'text': 'International turn value phone interesting foot capital yard. Study enough receive. Politics range raise dark whose.\nCrime military middle clear about. Manage enough glass resource film.',
    'email': 'qcummings@example.net',
    'phone_number': '+1-238-569-2379x1303',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Farmer',
],
    'json': {
    'name': 'Jason Reyes',
    'address': '22382 Melissa Park Apt. 395\nBurnettstad, PR 25891',
},
    'key61360': 'value77192',
    'key48451': 'value77224',
    'key26130': 'value91755',
    'key35556': 'value36435',
    'key92607': 'value25395',
    'key22556': 'value87344',
    'key89819': 'value14062',
    'key58034': 'value68644',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Melissa Reyes',
    'address': '2177 Griffin Isle\nRodriguezland, MT 89698',
    'text': 'Leader drive possible administration. Sometimes series his effort style political pressure.',
    'email': 'phardin@example.org',
    'phone_number': '872-266-6978',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Gross',
    'Jon Ramsey',
    'Melody Larson',
    'William Lopez',
    'Ashley Simmons',
],
    'json': {
    'name': 'Shane Valencia',
    'address': 'Unit 3227 Box 2778\nDPO AA 91737',
},
    'key98224': 'value45549',
    'key75072': 'value9482',
    'key66703': 'value22482',
    'key65043': 'value7227',
    'key2947': 'value48931',
    'key87236': 'value89583',
    'key14262': 'value66803',
    'key48375': 'value9674',
    'key55372': 'value73432',
    'key96474': 'value24417',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Barbara Waters',
    'address': '612 Miller Rapids Apt. 977\nVegatown, TX 26201',
    'text': 'Choose campaign though myself behind eye. Southern size environmental middle society cup recently son.\nPower same man bit others painting. Picture less behavior hope despite morning.',
    'email': 'lindseynelson@example.com',
    'phone_number': '708.723.3367x7659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Baldwin',
],
    'json': {
    'name': 'Tiffany Hood',
    'address': '918 Calvin Manors\nSouth Devin, NC 31497',
},
    'key78038': 'value80385',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Laura Guzman',
    'address': '7492 Leah Islands\nPrattstad, KY 15419',
    'text': 'Nature husband sit test.\nMust win degree pressure however. Color no radio keep woman. Green even want.\nCentury my inside begin more. Son consider letter success. Thus result these stuff art imagine.',
    'email': 'hahndaniel@example.org',
    'phone_number': '+1-547-402-2289x039',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Garcia',
    'Luis Wells',
    'Patrick Coleman',
    'Stacy Gibson',
    'Douglas Ellis',
],
    'json': {
    'name': 'Nicole Anderson',
    'address': '60524 Kim Manors\nMillershire, MO 98854',
},
    'key46930': 'value34686',
    'key63049': 'value64467',
    'key52139': 'value1187',
    'key19245': 'value22339',
    'key51544': 'value19833',
    'key86599': 'value43691',
    'key80150': 'value32310',
    'key42102': 'value27644',
    'key68369': 'value21150',
    'key13005': 'value44216',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Heather Smith',
    'address': '929 Adams Hills Suite 258\nNew Amandaberg, VI 83449',
    'text': 'Pull wide anything tell upon show. Experience just speech kind by loss.\nNews maintain word require later. Win try media senior. Change same ability product strong nearly.',
    'email': 'dayers@example.net',
    'phone_number': '(757)449-2946x227',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Natasha Ortega',
    'Diane Butler',
    'Michelle Boyer',
    'Sarah Davies',
    'Martin Fisher',
    'Steve Hernandez',
    'Nicholas Garcia',
    'Henry Gutierrez',
],
    'json': {
    'name': 'Daniel Rice',
    'address': '163 Jamie Mountains\nSydneyton, MS 92003',
},
    'key28778': 'value62484',
    'key61925': 'value68446',
    'key14336': 'value45654',
    'key47625': 'value21652',
    'key1663': 'value44810',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Barbara Mcintyre',
    'address': '97541 Fernandez Mountain Suite 979\nNew Molly, DE 28050',
    'text': 'Success son at road standard agree strategy cold. Term employee way. Music building also much term nearly bit.',
    'email': 'brittany56@example.net',
    'phone_number': '539.416.8767',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Carrillo',
    'Cory Wade',
    'Cody Smith',
    'Nathan Richardson',
    'Matthew Miles',
    'Kyle Frank',
    'Pamela Best PhD',
    'Ryan Jones',
    'Michele Davis',
    'Donald Butler',
],
    'json': {
    'name': 'Regina Martin',
    'address': 'USS Barnes\nFPO AE 45368',
},
    'key67930': 'value33059',
    'key43472': 'value94451',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Henry Higgins',
    'address': 'Unit 8622 Box 9936\nDPO AP 43612',
    'text': 'Pull cold tell. Under any simple which evidence claim night apply. North themselves player three week study thing bank.',
    'email': 'dclark@example.net',
    'phone_number': '4065230373',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sabrina Taylor',
    'Michael Wells',
    'Jennifer Johnson',
    'Virginia Brooks',
    'Russell Ramirez',
    'Kimberly Scott',
    'Thomas Thornton',
    'Terry Lopez',
    'Luis Rodriguez',
],
    'json': {
    'name': 'Dr. Luis Rocha',
    'address': 'USS Ibarra\nFPO AA 04180',
},
    'key1595': 'value64817',
    'key16224': 'value46776',
    'key42966': 'value68182',
    'key10842': 'value41408',
    'key27907': 'value83535',
    'key18045': 'value75223',
    'key93169': 'value70502',
    'key47160': 'value30507',
    'key18250': 'value98512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Morgan Bush',
    'address': '72398 Mcintyre Orchard Apt. 159\nPort Joshua, ME 38384',
    'text': 'Capital capital baby leave across produce build dark. Add stock indeed happen item foreign.\nNew such forward often card know.',
    'email': 'pam61@example.org',
    'phone_number': '+1-483-551-0900x4805',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Katrina Molina',
    'Matthew Larson',
    'David Vargas',
    'Antonio Simmons',
],
    'json': {
    'name': 'Catherine Powell',
    'address': '336 Jared Park Suite 325\nGregorybury, KS 96895',
},
    'key45458': 'value55184',
    'key33570': 'value93904',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jessica Bennett',
    'address': '083 Wilson Hill\nScottborough, ME 87387',
    'text': 'Herself father program manager during consider especially. Central down anyone American help four represent. About grow treat worker.',
    'email': 'collinsnicholas@example.net',
    'phone_number': '001-798-567-7144',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Owens',
],
    'json': {
    'name': 'Philip Anderson',
    'address': '117 Jimenez Street Suite 895\nWheelerhaven, LA 69450',
},
    'key38846': 'value99252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Susan Travis',
    'address': '990 Thomas Harbors Suite 222\nMartinton, NJ 24815',
    'text': 'Appear share pressure. Affect summer medical possible serve arm since.\nPerson blood art right have believe begin. Share debate others person more all chair.',
    'email': 'elizabethbell@example.com',
    'phone_number': '(687)289-3778',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Daisy Thompson',
    'David Macias',
    'David Eaton',
    'Angela Hayes',
    'Margaret Smith',
    'Frances Mullins',
    'Curtis Hayes',
    'Michele Arroyo',
    'John Martinez',
],
    'json': {
    'name': 'Cathy Miller',
    'address': '147 Katelyn Station Suite 660\nWest Dianeborough, IN 46583',
},
    'key69496': 'value63738',
    'key54971': 'value6909',
    'key20772': 'value82140',
    'key42626': 'value5011',
    'key54196': 'value12170',
    'key96588': 'value48521',
    'key80068': 'value83913',
    'key17163': 'value1309',
    'key31258': 'value75925',
    'key5207': 'value29024',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Stephanie Moore',
    'address': '37521 David Station\nLake Derek, IL 47035',
    'text': 'Wear force employee safe. Power small never front current happy.',
    'email': 'tmiller@example.org',
    'phone_number': '(409)946-9354',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Danny Johnson',
    'Jennifer Gomez',
    'Joel Hutchinson',
    'Stephen Gilbert',
    'Brandy Pruitt',
    'Gregory Salas',
    'Zachary Mills',
],
    'json': {
    'name': 'Rachel King',
    'address': '404 Hicks Burg\nLake Kristenfort, MH 73884',
},
    'key136': 'value42326',
    'key34464': 'value16766',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jamie Garrison',
    'address': '98944 Jeffrey Loop Suite 280\nPort Kathryn, VT 67416',
    'text': 'Check put see fact fight. Foot include television nor specific.\nBall it physical rate four cold hour. Story other family art forget board.',
    'email': 'chadwilliamson@example.org',
    'phone_number': '001-433-554-9769x6961',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Hernandez DDS',
    'Christopher Hernandez',
    'Dale Lyons',
    'Eric Curry',
],
    'json': {
    'name': 'Jeffery Michael',
    'address': 'USCGC Miller\nFPO AP 42491',
},
    'key82670': 'value28486',
    'key93552': 'value2297',
    'key25865': 'value42649',
    'key48699': 'value76536',
    'key79105': 'value55832',
    'key56116': 'value55757',
    'key41852': 'value26198',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Barry Fleming',
    'address': 'PSC 8093, Box 6295\nAPO AP 47084',
    'text': 'Decade nearly administration without. Traditional put pull record collection apply point. Treat result recognize trade.\nWatch do special picture common whose.',
    'email': 'yvetteking@example.net',
    'phone_number': '001-471-602-0942x98721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Chavez',
    'Mark Gordon',
    'Kevin Smith',
    'Matthew Taylor',
    'Kaitlyn Anderson',
    'Brenda Barnes',
    'Zoe Miller',
    'Adam King',
],
    'json': {
    'name': 'April Mooney',
    'address': '515 Heather Skyway Apt. 470\nKaylafort, MS 54852',
},
    'key42200': 'value84603',
    'key62757': 'value44705',
    'key93169': 'value46026',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Sandra Nelson',
    'address': '597 Vang Shoals Suite 484\nLake Carolview, NY 66668',
    'text': 'Above so themselves. Beyond difference probably.\nShow order television. Movie image media available indicate current boy follow. State little through act as.',
    'email': 'michael06@example.com',
    'phone_number': '996.755.2508x1199',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Chandler',
    'Larry Strong',
    'Christopher Anderson',
    'Mark Johnson',
],
    'json': {
    'name': 'Jennifer Reynolds',
    'address': '391 Manning Shoal Apt. 011\nWest Tammyfurt, TN 55605',
},
    'key86813': 'value5942',
    'key43906': 'value82267',
    'key5732': 'value21158',
    'key33788': 'value66392',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Jessica Harris',
    'address': '048 Justin Shoal Apt. 178\nPort Douglasfort, LA 39995',
    'text': 'Bank serve significant tend toward program wait organization. Right few probably event my final. Form bed wind ground leg.',
    'email': 'joel19@example.com',
    'phone_number': '598-715-0461x9278',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Bush',
    'Autumn Holland MD',
    'Mr. Justin Hill',
    'Jessica Baker',
    'Robert Jacobs',
],
    'json': {
    'name': 'Michael Galvan',
    'address': '78794 Jeanette Camp Suite 074\nStephaniebury, UT 78980',
},
    'key39391': 'value85011',
    'key34353': 'value99144',
    'key49776': 'value65227',
    'key82153': 'value47791',
    'key8085': 'value75197',
    'key31087': 'value8697',
    'key29233': 'value40185',
    'key7660': 'value8903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jacob Lin',
    'address': '219 Davis Pike Apt. 122\nCooperview, AS 14973',
    'text': 'Hope issue test pretty plan meeting. Role foreign discuss away.\nBase end seem age fill choice toward. Soldier however will box. Eye glass ground space call money week.',
    'email': 'rogerfoster@example.org',
    'phone_number': '(904)876-3332',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeff Hardy',
    'Justin Robertson',
    'Paul Preston',
    'Meredith English',
    'Daisy Alvarado',
    'Jeffrey Thompson',
    'Timothy Swanson',
    'Leroy Blake',
    'Kim Stanley',
],
    'json': {
    'name': 'Paul Williamson',
    'address': '41182 Laura Station\nNicoleborough, IA 92566',
},
    'key22129': 'value48795',
    'key25420': 'value22869',
    'key54887': 'value61699',
    'key74040': 'value70777',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Betty Brown',
    'address': '351 Samantha Shoal Apt. 797\nLauraborough, MT 59121',
    'text': 'Instead much student. Leader thousand gas lot save while low energy.\nProduct move surface us ready improve consider.\nFace try general appear. Nothing time get lawyer cut book heart.',
    'email': 'charlesjohnson@example.net',
    'phone_number': '891-726-1636x043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James James',
    'Alexander Rivera',
    'Austin Farley',
    'Charles Taylor',
    'Cheryl Cole',
    'Zachary Garcia',
    'Dillon Miller',
    'Tamara Williams',
    'Eric Davis',
],
    'json': {
    'name': 'Maria Craig',
    'address': '2196 Stephens Manors Apt. 610\nNorth Jenniferport, IN 79197',
},
    'key84555': 'value5913',
    'key4374': 'value88895',
    'key762': 'value51494',
    'key27738': 'value23871',
    'key81322': 'value22402',
    'key23737': 'value34939',
    'key50907': 'value55705',
    'key54319': 'value68164',
    'key69464': 'value39717',
    'key69325': 'value88001',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Dawn Smith',
    'address': '454 Justin Flat\nChenberg, GU 67848',
    'text': 'Talk two level maybe I. Remain put head against shoulder security.\nBreak good there man commercial phone. Several want interesting see ball.',
    'email': 'vangalicia@example.com',
    'phone_number': '2949848082',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Grant',
    'David Johnson',
    'Bryan Schaefer',
],
    'json': {
    'name': 'Tamara Vasquez',
    'address': '53813 Wendy Glens\nSouth Wanda, NJ 34599',
},
    'key33838': 'value26023',
    'key28597': 'value44413',
    'key66044': 'value78264',
    'key78710': 'value52125',
    'key53664': 'value50522',
    'key50347': 'value97733',
    'key43925': 'value71928',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sarah Nelson',
    'address': '8367 Blankenship Run\nLake William, NV 90220',
    'text': 'Interest natural class next cause. Only product above when about herself stand summer.\nAgency talk finish develop job cut operation. Much world song perform financial catch note money.',
    'email': 'ariasbrandi@example.org',
    'phone_number': '(445)230-0582x270',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Adams',
    'Courtney Leblanc',
    'Maria Herrera',
    'Timothy Anderson',
    'Corey Rich',
    'Walter Hunter',
    'Joshua Hughes',
    'Alexander Shannon',
],
    'json': {
    'name': 'Jeremy Washington',
    'address': '4605 Silva Courts Suite 398\nDavidberg, PR 88546',
},
    'key83456': 'value50013',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Eric Farrell',
    'address': 'PSC 0297, Box 5069\nAPO AA 28396',
    'text': 'Training method for education no. Occur step boy goal provide affect third yard. I maintain they step skin.\nFind offer center scientist front natural avoid kid. Economic mention arrive happen.',
    'email': 'meyermarissa@example.net',
    'phone_number': '307-634-1516',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Pope',
    'Lisa Martin',
    'Amanda King',
    'Tiffany Hernandez',
    'Jennifer Jones',
    'Zachary Levy',
    'Chad Gibson',
    'Elizabeth Evans',
],
    'json': {
    'name': 'Tyler Ramos',
    'address': '386 Perez Trail\nDustinborough, WI 28420',
},
    'key54058': 'value41744',
    'key349': 'value4302',
    'key12908': 'value74681',
    'key87825': 'value2595',
    'key7434': 'value54062',
    'key90680': 'value36203',
    'key29897': 'value59831',
    'key73107': 'value95669',
    'key48241': 'value26127',
    'key49401': 'value71993',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Nicole Smith',
    'address': '49511 Lewis Lodge Apt. 057\nEast Jonathanmouth, AZ 47989',
    'text': 'Per hope group without. Four Mr kid table writer feel. Never election agreement present visit.\nLate degree step same your for federal hair. Between city stuff be whatever.',
    'email': 'tiffany32@example.com',
    'phone_number': '+1-223-905-7942x67012',
    'array_int_dynamic': [
    60241,
],
    'array_varchar_dynamic': [
    'Maria Rice',
    'Michelle Perez',
    'Ashley James',
],
    'json': {
    'name': 'Andrea Webster',
    'address': 'PSC 4270, Box 1436\nAPO AE 66519',
},
    'key64458': 'value34997',
    'key17261': 'value65746',
    'key97354': 'value50698',
    'key86557': 'value23056',
    'key35557': 'value64768',
    'key13062': 'value74321',
    'key16507': 'value75170',
    'key65292': 'value49228',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Mark Williams',
    'address': '72203 Edwin Loop\nPort Lawrence, IL 87830',
    'text': 'Law else the country traditional indeed into. Nothing organization yeah boy both color. Later your play future push. Major my such seven newspaper relationship arm.',
    'email': 'sjackson@example.com',
    'phone_number': '(290)341-2781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Randy Jones',
    'Aaron Barker',
    'Linda Montgomery',
    'Lisa Adams',
    'Amy Mcdonald',
],
    'json': {
    'name': 'Monica Hale',
    'address': '875 Amanda Place\nBerryland, WA 61555',
},
    'key97831': 'value69245',
    'key28960': 'value34568',
    'key72634': 'value73034',
    'key24172': 'value97478',
    'key44456': 'value42146',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Gina Wells',
    'address': '279 Costa Station Apt. 465\nPort Timothybury, NH 74355',
    'text': 'Director car few chance society letter. Hospital easy chair. Occur who late.\nPossible whatever rather yard offer source hold. Through tell president bar. Suddenly few coach nothing may.',
    'email': 'teresafox@example.com',
    'phone_number': '960.298.7535x838',
    'array_int_dynamic': [
    52360,
],
    'array_varchar_dynamic': [
    'Erin Gordon',
    'Melanie Smith',
    'Dr. Kylie Stout',
    'Jordan Smith',
    'Jeremy Chavez',
    'Andrea Cox',
],
    'json': {
    'name': 'Lindsay Barnes',
    'address': '787 Denise Landing\nLake Mark, LA 98311',
},
    'key20777': 'value75007',
    'key19973': 'value96847',
    'key22743': 'value93169',
    'key46274': 'value64458',
    'key81206': 'value68896',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Steven Carter',
    'address': '785 Sharon Curve Suite 741\nSouth Morgan, MD 54042',
    'text': 'Water young middle throw. Seem order reveal participant down a. Message car possible great film nice.',
    'email': 'arnoldjessica@example.org',
    'phone_number': '(998)618-1153',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'David Brown',
    'Brianna Combs',
    'Jimmy Edwards',
],
    'json': {
    'name': 'Roger Stone',
    'address': 'PSC 7691, Box 8806\nAPO AP 74687',
},
    'key98978': 'value75202',
    'key6428': 'value17171',
    'key6169': 'value63327',
    'key43269': 'value41391',
    'key27994': 'value1855',
    'key2690': 'value31815',
    'key73919': 'value33461',
    'key98555': 'value46512',
    'key62868': 'value64543',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Stephen Rodriguez',
    'address': '51729 Jackson Parkways\nNorth Jenniferborough, FL 55330',
    'text': 'Town produce on say relate weight.\nActivity suggest by. Officer miss appear catch.\nHospital result blue. Page be together fact know.',
    'email': 'lawsonjennifer@example.com',
    'phone_number': '671.988.5282x77795',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Pierce',
    'Joann Booker',
    'Patricia Dunn',
    'David Reed',
    'David Green',
    'Carmen Jackson DVM',
    'Rachel Foster',
    'David Waller',
    'Theresa Alvarez',
    'Rachel Vasquez',
],
    'json': {
    'name': 'Terri Velasquez',
    'address': '5397 Mary Falls\nNew Diana, KS 32871',
},
    'key36609': 'value90389',
    'key76304': 'value83564',
    'key67288': 'value27258',
    'key59522': 'value53024',
    'key70154': 'value99846',
    'key87065': 'value11383',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Dustin Diaz',
    'address': '8626 Jonathan Brook Apt. 111\nNew Travis, KS 45849',
    'text': 'That drug industry wife each carry. Theory international bar. Nice pick task person along deal foot.',
    'email': 'kevin81@example.org',
    'phone_number': '3796948369',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Petty',
    'Megan Brady',
    'Theresa Nolan',
    'Marc Frey',
    'Wayne Stewart',
    'Jasmine Morris',
    'Maria Little',
    'Laura Sanchez',
    'Joy Mcgee',
    'Cristina Gill',
],
    'json': {
    'name': 'Jeffrey Ball',
    'address': '27497 Martin Circles Apt. 371\nNorth Michellebury, SC 56634',
},
    'key19534': 'value25763',
    'key75343': 'value21173',
    'key48501': 'value14432',
    'key29152': 'value68364',
    'key77041': 'value28729',
    'key82617': 'value7501',
    'key96019': 'value88042',
    'key31938': 'value3170',
    'key3256': 'value44236',
    'key28917': 'value37690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Wesley Ferguson',
    'address': '31884 Michael Flat Apt. 536\nEast Henry, ND 21281',
    'text': 'Word special source decade free. Nature language draw guess space business.\nGirl week practice tend eye court through task. Student perhaps attack. Good half degree seek meet.',
    'email': 'shenderson@example.com',
    'phone_number': '(376)999-2318',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Sanchez',
    'Andrea Gregory',
    'David Bradley',
    'Roger Fernandez',
    'Amber Jenkins',
    'Nicholas Green',
],
    'json': {
    'name': 'Johnny Bennett',
    'address': '93233 James Forks\nNorth Darryl, WA 38780',
},
    'key42364': 'value20393',
    'key77964': 'value94605',
    'key52087': 'value997',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Betty Barnes',
    'address': '83779 Danielle Wall\nLynnhaven, FL 80733',
    'text': 'Catch she health ready production risk public. Idea glass need bring class soon soon. Boy worker key choice theory resource black.',
    'email': 'haroldcisneros@example.org',
    'phone_number': '001-488-436-1867x7648',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Smith',
    'Tamara Walters',
    'Sheila Sherman',
    'Michael Brown',
    'Kenneth Ramirez',
    'Cheyenne Jackson',
    'Michael Key',
],
    'json': {
    'name': 'Travis Ryan',
    'address': '2145 Choi Unions Apt. 488\nRosefort, MD 97788',
},
    'key50655': 'value86242',
    'key65173': 'value20259',
    'key57979': 'value80614',
    'key37773': 'value73152',
    'key65810': 'value17243',
    'key72960': 'value7888',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Roy Valenzuela',
    'address': '30590 Daniel Cape Apt. 547\nWest Mary, AK 79919',
    'text': 'Cost yard not letter property. Although my town. Different perform exactly lead news model space.',
    'email': 'bryan83@example.org',
    'phone_number': '(564)307-9918x12561',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Williams',
],
    'json': {
    'name': 'Timothy Morrow',
    'address': '214 Ray Lakes\nPort Melinda, SC 86685',
},
    'key62751': 'value77604',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'David Perez',
    'address': '0153 Garcia Passage Suite 268\nLake Davidland, GA 47471',
    'text': 'Debate sometimes quickly clear party moment kitchen. Like building trip suddenly consumer fly. These join good follow single book floor.\nStrategy civil out value four fear.',
    'email': 'greenariel@example.org',
    'phone_number': '7398647032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Taylor',
    'Anthony Evans',
    'Andrea Flores',
    'Jennifer Ortega',
    'David Myers',
    'Courtney Phillips',
    'Thomas Shah',
],
    'json': {
    'name': 'Nicole Nelson',
    'address': '7289 Brandt Haven\nLydiatown, MS 26735',
},
    'key73329': 'value8151',
    'key98313': 'value11672',
    'key6426': 'value29437',
    'key2858': 'value40763',
    'key90294': 'value59663',
    'key5422': 'value92496',
    'key37612': 'value57037',
    'key15368': 'value24869',
    'key54595': 'value47107',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Heather Steele',
    'address': '594 Wendy Well Apt. 876\nFreemanburgh, IN 71597',
    'text': 'Do different fly town fill soldier thousand. Back bit newspaper nearly close last want. Follow first detail risk part.',
    'email': 'richard79@example.net',
    'phone_number': '(447)308-3149',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'John Vargas',
    'Robert Rodriguez',
    'Melissa Deleon',
    'Christine Wright DDS',
    'Charles Perkins',
    'Raymond Hubbard',
    'Tamara Rose',
    'Michael Adams',
    'Lindsey Nicholson',
],
    'json': {
    'name': 'Eric Salazar',
    'address': '1736 Chapman Locks Apt. 523\nSouth William, KY 14972',
},
    'key52644': 'value45396',
    'key30157': 'value73115',
    'key14061': 'value42030',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Rhonda Meyer',
    'address': '87230 Smith Trafficway Apt. 015\nFarrellmouth, MS 52934',
    'text': 'Watch trip former up make. Activity lead do discussion.\nGarden take race show develop eye. Weight line morning far.\nScene small glass check produce. Coach among especially. My eat issue add.',
    'email': 'christine75@example.org',
    'phone_number': '994.373.0885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Erica Shepard',
    'Paul Williams',
    'Heather Kelly',
    'Gloria Gibson',
    'John Davis',
    'Noah Ortega',
    'Ann Pena',
],
    'json': {
    'name': 'Lisa Perry',
    'address': '90313 Freeman Rue Suite 963\nFreemanmouth, CT 93117',
},
    'key48518': 'value56265',
    'key41127': 'value13355',
    'key17383': 'value50030',
    'key66822': 'value41633',
    'key48810': 'value57463',
    'key76939': 'value71273',
    'key86449': 'value7334',
    'key35693': 'value21290',
    'key12366': 'value901',
    'key53261': 'value27741',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Brandon Rivas',
    'address': '3988 Bruce Rapid Suite 269\nWest Jeffreyside, MA 39523',
    'text': 'Such better person number. Better unit challenge admit full Mrs. Subject interest rate north major. Realize hear sort language society.',
    'email': 'timothy04@example.com',
    'phone_number': '267-415-6636x167',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Colin Oliver',
    'Stephanie Garrison',
],
    'json': {
    'name': 'Kelly Baldwin',
    'address': '1687 Aaron Ports\nWilliamstown, PW 00538',
},
    'key78710': 'value57036',
    'key87279': 'value3362',
    'key12253': 'value62806',
    'key16202': 'value89245',
    'key26690': 'value9983',
    'key32285': 'value94308',
    'key46772': 'value87378',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Rebecca Allen',
    'address': '74216 Salinas Skyway\nPort Robertmouth, TX 45714',
    'text': 'Onto too use member. Stop particularly note child beautiful.',
    'email': 'melindageorge@example.net',
    'phone_number': '2786215617',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Frederick Jones',
    'Joyce Johnson',
],
    'json': {
    'name': 'Julie Blair',
    'address': '6744 Sharon Rapid\nFergusonside, WV 31132',
},
    'key564': 'value77178',
    'key64246': 'value1886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Robin Green',
    'address': '86255 Shelley Plaza Apt. 101\nWilliamsmouth, FM 38514',
    'text': 'Author thought mean tax either across. Report language though your well. Machine couple professional buy drug grow company.',
    'email': 'utorres@example.org',
    'phone_number': '7067041666',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Bishop',
    'Matthew Miller',
    'Larry Conrad',
    'Alicia Carter',
    'Sylvia Smith',
],
    'json': {
    'name': 'Christian Mckenzie',
    'address': '4709 Kelsey Courts\nNorth Peter, TN 36453',
},
    'key17646': 'value33036',
    'key37573': 'value42224',
    'key66363': 'value6401',
    'key27301': 'value35487',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Logan Norton',
    'address': '87575 Martinez Lake Suite 542\nRobinsonbury, UT 57462',
    'text': 'Budget defense cost notice table actually require. Real recognize center reflect financial.\nYard lead television resource reality Mr build. Dog industry choose any.',
    'email': 'lindseychavez@example.org',
    'phone_number': '(662)916-7786x62299',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Randy Fischer',
],
    'json': {
    'name': 'Charles Roth',
    'address': '813 Wright Loaf\nEast Vanessaville, WV 30035',
},
    'key87505': 'value97357',
    'key24210': 'value75319',
    'key95543': 'value59928',
    'key36329': 'value51703',
    'key77499': 'value19459',
    'key1507': 'value43015',
    'key97609': 'value45755',
    'key75967': 'value31382',
    'key35865': 'value36963',
    'key39371': 'value14723',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v1/vector/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'eb41e49f-62f1-11f0-8fcc-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_39_14_925169cwHzFWIS',
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
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
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/get"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/get")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/get'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'ebdb4d90-62f1-11f0-a6d6-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_39_14_925169cwHzFWIS',
    'outputFields': [
    '*',
],
    'id': 459470532653941867,
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
    'RequestId': 'e783150f-62f1-11f0-9b47-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_39_14_925169cwHzFWIS',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752745163.json')
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
    test = AllmilvusLogtestgetvectorTestGetVectorWithSimplePayload1752745163Json()
    test.run_tests()
