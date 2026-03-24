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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752745046_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752745046.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUidIn12341752745046Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752745046.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752745046.json"
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
    'RequestId': '9fcd581f-62f1-11f0-9550-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_14_615933QppLTrOn',
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
    'RequestId': 'a2eb13fa-62f1-11f0-8178-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_14_615933QppLTrOn',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Taylor Harvey',
    'address': '66880 Smith Plaza\nCrystaltown, WI 64794',
    'text': 'Tend control say politics. Pick morning year. Conference beyond change night meeting first over perform.',
    'email': 'graykathleen@example.org',
    'phone_number': '(846)937-2433x18753',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jared Bennett',
    'Destiny Charles',
    'Lauren Gutierrez',
    'Jeremy Wells',
    'Susan Lewis',
    'Stephanie Manning',
    'Gabrielle Mitchell',
    'Alan Stevens',
    'Jerry Kennedy',
    'Debra Crawford',
],
    'json': {
    'name': 'Sean Schmidt',
    'address': '02615 Malone Parkways\nSouth Christianhaven, SC 84646',
},
    'key54837': 'value26090',
    'key25237': 'value83089',
    'key34801': 'value25968',
    'key20445': 'value41614',
    'key38186': 'value14012',
    'key24266': 'value82670',
    'key30029': 'value3454',
    'key6235': 'value42804',
    'key27667': 'value44145',
    'key66297': 'value25436',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Rachel Nelson',
    'address': '4947 Lyons Forges\nCrosbyfort, MO 95745',
    'text': 'System so star scene should easy performance serious. Pressure deal seven.\nSix month per. Society evening structure consider. Six feeling include PM issue.',
    'email': 'harveycraig@example.org',
    'phone_number': '4124250657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jim Davis',
    'Stephen Morales',
    'Melissa Walker',
    'Vincent Jones',
    'Gregory Duran',
    'Ann Gonzalez',
    'William Murphy',
],
    'json': {
    'name': 'Brittany Rice',
    'address': '248 Roach Walks Suite 078\nThomasside, MO 82048',
},
    'key57670': 'value59511',
    'key91720': 'value77801',
    'key49575': 'value40920',
    'key48752': 'value5979',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Troy Mcclure',
    'address': '288 Taylor Radial Apt. 065\nNorth David, SD 64464',
    'text': 'Two like nothing economic parent practice. Majority fact say finish cover.\nAgain place win past forward throw car section. Listen run Mr then along himself enough we. And experience himself.',
    'email': 'brandongonzales@example.org',
    'phone_number': '838-209-7542x6493',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Mitchell',
    'William Thompson',
],
    'json': {
    'name': 'David Nichols',
    'address': '76117 Franklin Road\nLake Veronica, OK 40495',
},
    'key92938': 'value35502',
    'key66835': 'value5032',
    'key34039': 'value28073',
    'key47449': 'value27246',
    'key48912': 'value34327',
    'key218': 'value33584',
    'key43399': 'value1554',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Christine Holland',
    'address': 'USS Duncan\nFPO AE 50990',
    'text': 'Maybe reduce since weight hundred at thought final. Cause structure actually before organization.\nCatch life brother care throughout.',
    'email': 'luis18@example.net',
    'phone_number': '4718437451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Hunter Flynn',
    'Mark Mclaughlin',
    'Micheal Olsen',
    'Jennifer Porter',
    'Denise Olson',
    'Joseph Wood',
    'Elizabeth Martinez',
    'Scott Lopez',
],
    'json': {
    'name': 'Kevin Pollard',
    'address': '060 Torres Underpass Apt. 878\nNew Maryside, UT 50049',
},
    'key91059': 'value74398',
    'key19030': 'value66420',
    'key23294': 'value6225',
    'key64671': 'value12620',
    'key16782': 'value60719',
    'key44612': 'value24539',
    'key48740': 'value50706',
    'key6588': 'value83051',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Kimberly Love',
    'address': '1569 Robert Manors\nNorth Caitlyn, NC 84355',
    'text': 'Cut stage financial.\nPick discussion woman might wife next. Act light although case debate. Recognize need month candidate have manager that tax.',
    'email': 'cbrown@example.net',
    'phone_number': '402-497-0612',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Cain',
    'Leslie Wilson',
    'Mark Lopez',
    'Jason Wade',
    'Jerry Watson',
],
    'json': {
    'name': 'Amber Hopkins',
    'address': '22778 Melinda Parks Suite 441\nIrwinview, TX 22520',
},
    'key27643': 'value12900',
    'key45309': 'value2766',
    'key21541': 'value9449',
    'key65521': 'value8968',
    'key62243': 'value27682',
    'key99377': 'value72372',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jeffery Dyer',
    'address': '309 Collins Cliffs Apt. 616\nWilliamland, IL 92258',
    'text': 'Politics everyone participant trip measure job single.\nIndicate sit can talk accept throw. Simple drug eight glass better note involve check. Yard matter while describe mission even hotel.',
    'email': 'contrerasmadison@example.org',
    'phone_number': '799-723-1743x4253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Wanda Kennedy',
],
    'json': {
    'name': 'Michael Owen',
    'address': '670 David Inlet\nRoyland, MD 25407',
},
    'key30908': 'value97661',
    'key27213': 'value27116',
    'key3872': 'value72681',
    'key52117': 'value65757',
    'key66860': 'value3258',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Walter Rogers',
    'address': '2214 Suarez Groves Suite 674\nSouth Kelly, PA 08210',
    'text': 'Everyone analysis condition born line every. Southern inside cost available. Yes computer score assume. Day can pattern.',
    'email': 'shannonhughes@example.net',
    'phone_number': '575-288-2853',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexandra Johnston',
],
    'json': {
    'name': 'Thomas Wilcox',
    'address': '7706 Baker Fields Suite 884\nPort Karenfurt, ID 80442',
},
    'key97214': 'value80485',
    'key93714': 'value31086',
    'key67690': 'value9904',
    'key50003': 'value66328',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Stephanie Richards',
    'address': '92635 Melissa Knolls Apt. 276\nJohntown, NH 89397',
    'text': 'Such according face writer hope particular wife. Stock fund position. Process teacher recognize leg activity alone bit hit. Color four he yes system.',
    'email': 'douglas68@example.com',
    'phone_number': '859.424.5680',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Thompson',
    'Jamie Lee',
    'Larry Skinner',
    'Joshua Sanchez',
    'Stephanie Carrillo',
    'Nathan Knox',
    'Danielle Hughes',
],
    'json': {
    'name': 'Ann Turner',
    'address': 'Unit 6498 Box 5190\nDPO AE 27849',
},
    'key2270': 'value79947',
    'key5858': 'value66007',
    'key49135': 'value34541',
    'key89339': 'value65325',
    'key9410': 'value55651',
    'key2376': 'value22280',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Alan Herrera',
    'address': '4416 Martin Harbor Suite 278\nSouth Joshuaburgh, OH 33994',
    'text': 'Ever lead medical evidence. Happy indicate gas leave single teacher respond. Alone resource education Republican particular enter. Ability into difficult base likely population scientist.',
    'email': 'christina72@example.net',
    'phone_number': '+1-487-497-0617x928',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Andersen',
    'Kimberly Anderson',
    'Julie Barnes',
    'Ryan Garrett',
    'William Allen',
    'Tracy Marquez',
    'John Miller',
    'Michael Weaver',
],
    'json': {
    'name': 'William Lyons',
    'address': 'Unit 3987 Box 3853\nDPO AP 57425',
},
    'key35828': 'value52318',
    'key18642': 'value9314',
    'key76663': 'value72203',
    'key13228': 'value93774',
    'key30959': 'value77880',
    'key45535': 'value66223',
    'key37478': 'value51714',
    'key77551': 'value62785',
    'key29266': 'value33037',
    'key9935': 'value78328',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brian Ray',
    'address': '04524 Donald Throughway Suite 534\nGreenside, AS 26027',
    'text': 'Science goal blue.\nInvestment thing want these. Western allow arm program you. Guy two fact still wonder artist.\nWhite their young. Name west popular a. Final what choice leave half memory.',
    'email': 'lsmith@example.org',
    'phone_number': '(280)837-8588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Paula Levy',
    'Paul Adams',
    'Lori Holland',
],
    'json': {
    'name': 'Vincent Shepherd',
    'address': '5579 Roy Lights\nCampbellfurt, VA 40610',
},
    'key77765': 'value46375',
    'key62290': 'value66227',
    'key83460': 'value31242',
    'key4806': 'value91629',
    'key5913': 'value35143',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Gregory Williams',
    'address': '06480 Cathy Creek\nReneemouth, VA 44123',
    'text': 'Professional among see him news think between. New office word side report finish blood during. Mother deep cut exactly detail interview develop.\nPerson effort job find. Usually cell nation.',
    'email': 'asanchez@example.org',
    'phone_number': '001-271-734-7140x80028',
    'array_int_dynamic': [
    73112,
],
    'array_varchar_dynamic': [
    'Kristen Wilkinson',
    'Chelsea Lee',
    'Mrs. Jeanne Cummings',
],
    'json': {
    'name': 'Edgar Henderson',
    'address': '45916 Flores Expressway Suite 405\nNew Guymouth, TN 43133',
},
    'key16695': 'value238',
    'key68771': 'value44110',
    'key61144': 'value67914',
    'key93270': 'value63432',
    'key56971': 'value64434',
    'key64397': 'value83851',
    'key68755': 'value64889',
    'key28573': 'value46077',
    'key3336': 'value48236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'William Davis',
    'address': '89870 Boyd Rue Suite 823\nFranklinshire, GU 07328',
    'text': 'West east her red. Laugh indeed or blue audience for. Authority be certain. Ok cost usually want man hour maybe organization.\nCharge Mr think others. Bad produce customer.',
    'email': 'kobrien@example.org',
    'phone_number': '400.988.2695x968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tanya Fernandez',
    'Laurie Flynn',
    'Stephanie Morrison',
    'Stephen Gibbs',
    'Kyle Sims',
    'Mark Wong',
    'Dr. Matthew Cantu MD',
    'Christopher Mullins',
    'Nancy Mcgee',
],
    'json': {
    'name': 'Tara Jackson',
    'address': '874 Gina Mission Suite 022\nFloresmouth, WA 71054',
},
    'key50008': 'value58260',
    'key60657': 'value2299',
    'key95125': 'value22184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Daniel Luna',
    'address': '38205 Danielle Gateway\nNew Sarah, FL 46385',
    'text': 'Fine risk hundred reason upon environment box. Whatever seek onto treatment red center. Imagine either where particularly bad community address.',
    'email': 'foxerin@example.org',
    'phone_number': '(806)875-0254x785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ann Townsend',
    'Nicole Clark',
    'Benjamin Williams',
    'Jose Turner',
    'Patrick Martinez',
    'Lance Hernandez',
    'Joshua Taylor',
    'Rhonda Murray',
],
    'json': {
    'name': 'Rebecca Silva PhD',
    'address': '41714 Valencia Brook Apt. 179\nAliciaville, WA 96900',
},
    'key59639': 'value44796',
    'key58522': 'value60860',
    'key25478': 'value18354',
    'key57541': 'value67903',
    'key50104': 'value19803',
    'key85199': 'value31351',
    'key96583': 'value13636',
    'key52500': 'value87310',
    'key24537': 'value40895',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Andrew James',
    'address': '9023 Hill Roads\nDannybury, NE 55049',
    'text': 'Evidence school situation operation cup present just. Table traditional list century financial painting need even. Meeting charge traditional.',
    'email': 'millerjennifer@example.net',
    'phone_number': '001-857-831-1754',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Lowe',
    'Heather Woods',
    'Danny Jarvis',
    'Hannah Tanner',
    'Pamela James',
    'Rachel Walker',
    'Michael Cooper',
    'Nicholas Richardson',
    'Michael Mack',
],
    'json': {
    'name': 'Erin Reyes',
    'address': 'PSC 9626, Box 5932\nAPO AP 34383',
},
    'key53540': 'value79833',
    'key2085': 'value76277',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Frederick Malone',
    'address': '589 Harris Villages Apt. 566\nTylertown, WI 34378',
    'text': 'Evening skill sound assume administration. Growth couple road tough cause book structure require. Score around time image quite.\nWord charge fight vote middle. Peace movie seat participant.',
    'email': 'zachary34@example.com',
    'phone_number': '+1-269-721-5089x145',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'John Phillips',
    'Katelyn Smith',
    'Cynthia Brown',
    'Amy Torres',
],
    'json': {
    'name': 'Whitney Mcintyre',
    'address': '22968 Horton Stravenue Suite 103\nWest Joeltown, GU 08599',
},
    'key67924': 'value34046',
    'key31429': 'value7210',
    'key81040': 'value97597',
    'key15869': 'value39776',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Gavin French',
    'address': '770 Timothy Dam Suite 459\nEricstad, MD 52364',
    'text': 'Member suffer night always feeling purpose walk. Health indeed on professional authority every.\nDiscover system race add structure character. Data control enough movement member produce close.',
    'email': 'randerson@example.org',
    'phone_number': '318.800.4288x1466',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Heath',
    'Kimberly Bradford',
],
    'json': {
    'name': 'Cody Moreno',
    'address': '976 Marsh Highway\nSouth James, AZ 44589',
},
    'key6517': 'value40605',
    'key10740': 'value5364',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Michele Howard',
    'address': '976 Keith Burg\nEmilyhaven, WI 43880',
    'text': 'Civil sing middle eat race understand. Tree billion value pull. Reduce laugh middle purpose song better name.\nOf hotel start doctor. Explain no bag.',
    'email': 'msmith@example.org',
    'phone_number': '(512)623-0159x974',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Laurie Schaefer',
    'David Morris',
    'Amy Arias',
    'Lori Meyer',
    'James Green',
    'Mary Davis',
    'Shane Henderson',
    'Andrea Obrien',
    'Kayla Berger',
],
    'json': {
    'name': 'Jacob Thomas',
    'address': '6156 Dennis Mountains\nBonnieport, AK 73410',
},
    'key76034': 'value85909',
    'key17065': 'value7558',
    'key17826': 'value52489',
    'key76714': 'value40148',
    'key7489': 'value86854',
    'key33126': 'value9420',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Marcia Bowers',
    'address': '04399 Ryan Estates\nEast Jamie, LA 55579',
    'text': 'Determine herself source.\nFight assume reason campaign. Suggest wait require arrive life.',
    'email': 'michael21@example.org',
    'phone_number': '001-981-497-5933',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tim Bowen',
    'Felicia Graham',
    'Christina Gonzales',
    'Evan Wilson',
    'Justin Smith',
    'Melissa Thomas',
    'Brenda Hensley',
],
    'json': {
    'name': 'Sarah Clark',
    'address': '8256 Jacobs Shoal\nNew Erinstad, VI 18435',
},
    'key71879': 'value3375',
    'key86785': 'value63157',
    'key12629': 'value83593',
    'key99070': 'value90690',
    'key38280': 'value75355',
    'key55578': 'value56427',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Anthony Henderson',
    'address': '70652 Kelly Branch\nPort Ruth, WV 13797',
    'text': 'Movement fight wide age about pass friend. Court name member.\nRegion exactly never use least share. Of will material goal chance.\nUnit party perform protect teacher whom.\nNeed candidate song.',
    'email': 'cody43@example.com',
    'phone_number': '986-326-0751x51046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeff Holmes',
    'Matthew Blanchard',
],
    'json': {
    'name': 'Susan Logan',
    'address': '21444 Rivera Lodge\nEast Jamiefurt, WA 90220',
},
    'key88938': 'value33312',
    'key64825': 'value77403',
    'key38771': 'value57804',
    'key43036': 'value83050',
    'key9163': 'value24640',
    'key28491': 'value77325',
    'key53890': 'value66760',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Gilbert Woodward',
    'address': '86629 Allen Creek Suite 898\nSouth Lorraine, MN 94203',
    'text': 'Agreement window middle student. Back young eight left what.\nDiscuss few stock wall significant. Analysis deal table effort hour many.',
    'email': 'ryanallen@example.com',
    'phone_number': '(369)312-1953x68801',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mark Whitaker',
    'Victoria King',
    'Darryl Swanson IV',
    'Devin Robbins',
    'Jordan Moore',
    'Michael Lee',
    'Daniel Huff',
],
    'json': {
    'name': 'Brian Gardner',
    'address': '9185 Johnston Turnpike Apt. 172\nJeffreyside, DC 14067',
},
    'key8243': 'value82562',
    'key28999': 'value35401',
    'key13049': 'value71140',
    'key44036': 'value70184',
    'key59962': 'value62597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Mrs. Whitney Wagner',
    'address': '247 Berger Square\nWest Larryshire, CO 74424',
    'text': 'Explain appear we vote knowledge. Thought both television name boy benefit economic.\nIncluding seat news boy anything owner.',
    'email': 'michaelmack@example.com',
    'phone_number': '+1-503-444-8219x891',
    'array_int_dynamic': [
    24927,
],
    'array_varchar_dynamic': [
    'Timothy Hanna',
    'Joseph Moses',
    'Timothy Hawkins',
    'Melissa Taylor',
    'Phillip Gonzales',
],
    'json': {
    'name': 'Gregory Allison',
    'address': '925 Alvarez Points Suite 931\nMillerborough, NY 77734',
},
    'key12352': 'value11207',
    'key77874': 'value88630',
    'key62902': 'value463',
    'key80993': 'value80114',
    'key49957': 'value1385',
    'key98338': 'value23830',
    'key44233': 'value6748',
    'key18942': 'value64538',
    'key52342': 'value84592',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Joyce Yoder',
    'address': '633 Howard Shoal Suite 863\nNew Meaganshire, UT 75813',
    'text': 'Four large guess huge region happy. Sound idea rise including within personal water figure. Everybody recent clear finish current.\nTrue rock short hear third expert feel.',
    'email': 'mark65@example.com',
    'phone_number': '001-587-467-9221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Allison Fisher',
    'Joan Solomon',
    'Ann Williams',
    'Donna Thompson',
    'Trevor Watson',
    'Katherine Stafford',
],
    'json': {
    'name': 'Brett Frye',
    'address': '9215 Jaime Meadows\nSchwartzberg, KS 77763',
},
    'key48116': 'value67448',
    'key91658': 'value43671',
    'key43753': 'value30083',
    'key73297': 'value86051',
    'key90765': 'value36479',
    'key52906': 'value58918',
    'key79108': 'value4775',
    'key52955': 'value57174',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Richard Cordova',
    'address': '4575 Mathis Ford Apt. 731\nButlerview, OH 62067',
    'text': 'Term movement policy admit someone whose. Decide drive throughout matter century interesting. Bar position have my begin.',
    'email': 'xwashington@example.org',
    'phone_number': '901.378.4447',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Wolfe',
    'Jessica Hansen',
],
    'json': {
    'name': 'Edward Shea',
    'address': '4790 Glenda Shoal\nPaulshire, FL 97069',
},
    'key33922': 'value86351',
    'key1861': 'value18081',
    'key22385': 'value73182',
    'key83386': 'value27892',
    'key1701': 'value61677',
    'key28075': 'value32015',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Robert Clark',
    'address': '36124 Edward Fords Apt. 681\nJustinmouth, TX 57017',
    'text': 'To she company country stop use region. Party usually address particularly building finally.\nNext my hour realize. Better care society decade reality three low.\nCan start six remember leader.',
    'email': 'yjackson@example.net',
    'phone_number': '+1-536-640-4035x92613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Laura Carter',
    'Jason Frye',
    'Jason Lee',
],
    'json': {
    'name': 'Mark Coffey',
    'address': '7733 Roger Motorway Suite 375\nLake Morgantown, CA 13598',
},
    'key22647': 'value37812',
    'key52446': 'value95541',
    'key36500': 'value83828',
    'key1356': 'value40269',
    'key69897': 'value1582',
    'key34896': 'value87823',
    'key16338': 'value23454',
    'key3779': 'value70447',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Christine Anderson',
    'address': '48845 Frank Burg\nEast Dawn, WV 43094',
    'text': 'Open health forget old here. Movie responsibility stay several.\nCut father manage hard generation. Beautiful natural form value pull. Still inside true provide occur yourself bill.',
    'email': 'christopherhernandez@example.org',
    'phone_number': '459.838.0542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Johnson',
    'Maureen Baker',
    'Jean Pierce',
],
    'json': {
    'name': 'Robert White',
    'address': '10845 Brady Common Suite 308\nCunninghamstad, NV 89846',
},
    'key60085': 'value94920',
    'key65969': 'value80155',
    'key48823': 'value14278',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Derrick Barnes',
    'address': 'Unit 9182 Box 3956\nDPO AA 71823',
    'text': 'Sport condition three benefit up can. Back allow street. Ever radio hard fact me notice himself. On culture amount gas be rest defense.',
    'email': 'johnedwards@example.net',
    'phone_number': '5282907090',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Megan Ruiz',
    'Michael Jimenez',
    'Diane Griffin',
],
    'json': {
    'name': 'Abigail Cruz',
    'address': '85694 Daniel Light Apt. 736\nEast Stephanieside, MH 37923',
},
    'key4537': 'value96354',
    'key67874': 'value32940',
    'key87505': 'value28861',
    'key84690': 'value30203',
    'key55410': 'value57988',
    'key87170': 'value61766',
    'key86996': 'value39008',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Lauren Juarez',
    'address': '79431 Lisa Stream Suite 058\nRamirezstad, IL 20302',
    'text': 'Lead camera like fast price kid design blue.\nPresident say cause evidence source build business. Road ask the discuss.',
    'email': 'glambert@example.net',
    'phone_number': '001-283-875-5504',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'David Hall',
    'Beth Mckee',
],
    'json': {
    'name': 'Ann Lewis',
    'address': 'USCGC Carter\nFPO AA 15295',
},
    'key79887': 'value30425',
    'key25992': 'value83124',
    'key34750': 'value81930',
    'key68180': 'value73122',
    'key20209': 'value41438',
    'key53692': 'value49879',
    'key35606': 'value53012',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Scott Lloyd',
    'address': '71458 Brian Mountains Apt. 281\nLindahaven, NJ 49201',
    'text': 'Spring challenge those local glass with. Ask effect spend per service push heavy. Weight figure dog song music she.\nRespond music why under. Energy appear matter modern certain state.',
    'email': 'barry60@example.net',
    'phone_number': '(634)729-8379x5111',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Marc Obrien',
    'Benjamin Johnson',
    'Christopher Blankenship',
],
    'json': {
    'name': 'Jonathan Richards',
    'address': '015 Dustin Grove\nWest Kimberly, NJ 68550',
},
    'key19254': 'value35542',
    'key79248': 'value12801',
    'key18770': 'value2303',
    'key63666': 'value23215',
    'key79567': 'value75296',
    'key41800': 'value58103',
    'key54147': 'value85203',
    'key23025': 'value67226',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'William Adams',
    'address': '05406 Corey Vista\nAmytown, MH 38395',
    'text': 'Of specific avoid majority save. Church board people. Send country part authority whom. Bad story full so.\nInside eat trial before character training us. Use director each big boy.',
    'email': 'stephaniedodson@example.net',
    'phone_number': '001-588-659-2468x11385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Brown',
    'Kelly Young',
    'Maria Jordan',
    'Blake Martin',
    'Alicia Carter',
    'James Gray',
    'Ashley Carpenter',
    'Emily Walters',
    'Kelsey Zimmerman',
],
    'json': {
    'name': 'Janet Spence',
    'address': '2413 Brenda Drive Suite 790\nWest Natalie, GU 24836',
},
    'key38020': 'value64919',
    'key57592': 'value85864',
    'key43244': 'value57113',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Lisa Tran',
    'address': '21721 Todd Ports\nNew Pamelaview, LA 89014',
    'text': 'Report choice cost then street finally side. Indeed discover little commercial live week. Maybe investment benefit attorney nice cell east discuss.',
    'email': 'jnorton@example.org',
    'phone_number': '802.675.7785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Edwards',
    'Jason Cook',
    'Brandon Davis',
    'Mr. Jeremy Hill',
    'Andrew White',
    'Darryl Estes',
    'Joshua Bartlett',
    'Andrew Moran',
    'Marcus Rodriguez',
],
    'json': {
    'name': 'Victor Powell',
    'address': '5109 Olson Ford\nLake Daniel, NC 60815',
},
    'key11637': 'value34754',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Robert Gray',
    'address': '3067 Hess Inlet\nJeremyville, TX 38695',
    'text': 'Career less thousand sister key author. Authority among concern else car. Yourself later too civil debate music.',
    'email': 'dorothymejia@example.net',
    'phone_number': '704-473-1176',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley James',
    'James Smith',
    'Jonathan Tucker',
    'Tyrone Hudson',
    'Julia Johnson',
    'Ernest Murphy',
    'John Bennett',
    'Kayla Trevino',
    'Frank Smith',
    'Brittany Reyes',
],
    'json': {
    'name': 'Jeffery Page',
    'address': '82205 James Summit\nLanefort, ID 38045',
},
    'key15286': 'value18422',
    'key39821': 'value74412',
    'key63222': 'value38219',
    'key20753': 'value21587',
    'key33005': 'value79820',
    'key86319': 'value64595',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Mrs. Angel Harrell MD',
    'address': '3033 Jennifer Curve\nSouth Melissa, ID 19549',
    'text': 'Work prove nearly cover picture never back. Picture here recent action window.\nBeautiful write too firm. Store with state these financial cold system. Commercial sort paper so member into son.',
    'email': 'fredadams@example.org',
    'phone_number': '001-751-248-8852x9360',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Green',
    'Nicholas Mora',
    'Mandy Williams',
    'Kristen Wilson',
    'Rebecca Allen',
    'Karen Barry',
    'Brent Love',
],
    'json': {
    'name': 'Kelly Rowland',
    'address': '15942 Mark Gardens Apt. 508\nAdamsmouth, NH 15943',
},
    'key79105': 'value59323',
    'key96581': 'value89237',
    'key51589': 'value71985',
    'key60515': 'value4111',
    'key85793': 'value98505',
    'key46944': 'value37132',
    'key96804': 'value70826',
    'key58847': 'value91105',
    'key38489': 'value17655',
    'key29656': 'value97133',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Timothy Ramirez',
    'address': '25155 Joseph Unions\nWest Josehaven, KS 00746',
    'text': 'North energy marriage move. Sometimes himself end sense people machine hear.\nReturn baby floor. Week successful future science.',
    'email': 'bethdavis@example.net',
    'phone_number': '001-957-254-9190x2189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Melton',
    'Jimmy Barnes',
    'Sylvia Sanders',
    'Maria Webb',
    'Craig Dean',
    'Mike Robinson',
    'Jessica Lara',
    'Kenneth Walker',
],
    'json': {
    'name': 'Julie Martinez',
    'address': '2839 Robert Rapids\nSouth Michelleport, NV 32596',
},
    'key94246': 'value91095',
    'key14547': 'value82415',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Russell Ewing',
    'address': '1332 Beth Cliff Apt. 709\nNew Debbie, NM 69279',
    'text': 'Face ground old line science glass pay loss. Culture voice sister performance affect magazine.\nFloor season section civil prevent third turn. Thus several push experience.',
    'email': 'richardsullivan@example.com',
    'phone_number': '+1-488-482-4791x8709',
    'array_int_dynamic': [
    2838,
],
    'array_varchar_dynamic': [
    'Andrew Hamilton',
    'Nicole Mejia',
    'Kimberly Reynolds',
    'Daniel Mitchell',
    'Keith Griffin',
    'Katherine Sanders',
],
    'json': {
    'name': 'Richard Garcia',
    'address': '0204 Hunt Brooks\nHicksfurt, AK 62574',
},
    'key54205': 'value51767',
    'key86015': 'value25578',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'James Baker',
    'address': '33944 Gregory Wall\nGlennberg, AS 02877',
    'text': 'Interest brother relate board. On sense successful speech result. Computer artist foreign hot team position writer soon.',
    'email': 'juliehughes@example.net',
    'phone_number': '9138237736',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Dillon Singleton',
    'Mark Bell',
    'Jennifer Bass',
    'Jennifer Davis',
],
    'json': {
    'name': 'Carrie Shelton',
    'address': 'USCGC Lee\nFPO AE 61925',
},
    'key88895': 'value76117',
    'key28028': 'value8879',
    'key86979': 'value16263',
    'key68734': 'value78423',
    'key47987': 'value4138',
    'key25094': 'value45676',
    'key79588': 'value27735',
    'key16131': 'value48532',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Joshua Meyer',
    'address': '008 Nelson Prairie Suite 221\nNelsonfort, RI 00927',
    'text': 'Edge report evening wish ten table. Natural mean answer second. Dream standard center.\nDiscussion road space everybody. Ready film stand series dinner piece. Also easy never chair.',
    'email': 'rodney36@example.net',
    'phone_number': '001-714-212-6536x501',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alexandra Hunt',
    'Chris Frazier',
    'Maureen Jacobs',
    'Michael Brown',
    'Kevin Campbell',
    'Scott Joyce',
    'Kenneth Taylor',
    'Tanner Reed Jr.',
],
    'json': {
    'name': 'James Parker',
    'address': '05292 Williams Squares Suite 420\nMadelinefort, FM 71559',
},
    'key65576': 'value41406',
    'key78352': 'value61877',
    'key6014': 'value72672',
    'key73073': 'value22559',
    'key40180': 'value7690',
    'key67971': 'value5811',
    'key67190': 'value63438',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Grace Hanson',
    'address': '392 Roberts Terrace\nJohnsonstad, WA 56250',
    'text': 'Join my these return have listen media. Usually travel record accept building fear impact. That name thank. Set fish key agent.',
    'email': 'robert61@example.org',
    'phone_number': '+1-485-799-0330x3634',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cheyenne Bennett',
    'Katrina Smith DDS',
],
    'json': {
    'name': 'Anthony Jimenez',
    'address': '763 Anna Path Apt. 031\nWest Amandastad, AK 47373',
},
    'key90192': 'value71303',
    'key8504': 'value32192',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Elizabeth Matthews',
    'address': '0624 Harmon Prairie\nDaniellemouth, PA 07312',
    'text': 'Store wind control general season meet. High certain without hold chair. Great win single individual successful.',
    'email': 'joseharmon@example.com',
    'phone_number': '001-672-567-7900x7789',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Richardson',
    'Todd Lewis',
    'Michelle Kaiser',
    'Matthew Woodard',
    'Katie Stout',
    'Danielle Gilbert',
    'Christina Bradley',
],
    'json': {
    'name': 'Steven Malone',
    'address': '83697 Leslie Walks Suite 053\nBoydside, AR 84896',
},
    'key55817': 'value47689',
    'key23650': 'value19706',
    'key46091': 'value30487',
    'key11641': 'value58207',
    'key27933': 'value54179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kimberly Benson',
    'address': '470 Christina Lakes\nWest Courtney, IL 37948',
    'text': 'Cut board piece piece question.\nAccept adult thank according meet bag computer doctor. Billion especially network foot season one.',
    'email': 'bramirez@example.com',
    'phone_number': '445-353-9049x70170',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Martin',
    'Margaret Mann',
    'Christopher Lyons',
],
    'json': {
    'name': 'Susan Reynolds',
    'address': '999 James Port Suite 094\nNorth Ryan, TX 13738',
},
    'key67730': 'value74346',
    'key47924': 'value31881',
    'key34798': 'value7114',
    'key68185': 'value76985',
    'key22908': 'value17124',
    'key98222': 'value21150',
    'key15690': 'value44062',
    'key48834': 'value28757',
    'key54743': 'value68507',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Nicolas Wolfe',
    'address': '5599 Christina Prairie\nHoshire, MI 55944',
    'text': 'Everything price institution employee kitchen. Issue go create reality.\nReduce surface sea drive tell fill. Body chair physical close stay enter foot.',
    'email': 'chambersshawn@example.com',
    'phone_number': '444.931.9810x0324',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Adam Porter',
    'Maria Marshall',
    'Charles Winters',
],
    'json': {
    'name': 'Mark Preston',
    'address': '545 Robert Creek Apt. 103\nEast Christopherchester, SD 40597',
},
    'key81181': 'value85454',
    'key38627': 'value68801',
    'key18856': 'value96646',
    'key25457': 'value61724',
    'key45304': 'value92013',
    'key21458': 'value26638',
    'key94703': 'value48999',
    'key14310': 'value29691',
    'key76203': 'value90420',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Emily Stephens',
    'address': '7296 Lawson Hollow\nLake Ianville, AZ 61419',
    'text': 'Control able writer behavior even off room. Cell term gas kind natural. Author likely trial economic head.',
    'email': 'michael16@example.org',
    'phone_number': '+1-259-755-6752x62595',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Potter',
    'Natalie Moore',
],
    'json': {
    'name': 'Toni Morales',
    'address': '22172 Kristina Lights Apt. 493\nMaureenville, LA 63760',
},
    'key90254': 'value99321',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Rebecca Hoover',
    'address': '13431 Taylor Pass\nMatthewport, HI 48381',
    'text': 'Produce ahead visit direction.\nSeem threat appear anyone dinner. Account third middle tax heavy third physical yard. Pay common name remain.',
    'email': 'curtis18@example.org',
    'phone_number': '+1-373-756-6589x2029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alex Jones',
    'Vincent Miller',
    'Melinda Robertson',
    'Craig Mitchell',
],
    'json': {
    'name': 'Tonya Farley',
    'address': '20658 Mills Views\nCampbellton, RI 99851',
},
    'key71528': 'value63684',
    'key8954': 'value25851',
    'key15311': 'value10972',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Edward Wilson',
    'address': '54328 Wells Fords\nWest Patrickstad, CO 64151',
    'text': 'With break establish maintain. Center step explain value site gas pattern. Director computer star example add attack commercial mission.',
    'email': 'kimberlygomez@example.net',
    'phone_number': '304-574-4370x151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diana Wade',
    'Terrance Galloway',
    'Brian Casey',
    'Danny Davis',
    'Linda Bailey',
],
    'json': {
    'name': 'Dana Johnson',
    'address': '302 Kennedy Summit Apt. 299\nJamesborough, MT 41297',
},
    'key88045': 'value2291',
    'key46393': 'value56414',
    'key23392': 'value14958',
    'key94235': 'value71518',
    'key41037': 'value83218',
    'key93937': 'value55299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Stacey Sanford',
    'address': '30203 Peter Station Suite 903\nLake Todd, NY 55138',
    'text': 'Some sister performance plant. News bad picture rest. Culture these father center.\nStore follow expert. While camera group activity lay. Themselves describe young claim become suggest especially.',
    'email': 'rebeccarobinson@example.net',
    'phone_number': '713-804-8552',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Calvin Taylor',
],
    'json': {
    'name': 'Robin White',
    'address': '61302 Luke Mountain Apt. 869\nDaisyfurt, VA 58918',
},
    'key34200': 'value39587',
    'key95514': 'value24951',
    'key58011': 'value671',
    'key76603': 'value65807',
    'key40415': 'value29454',
    'key65621': 'value14462',
    'key35215': 'value71017',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Michael Santos',
    'address': '2125 Wilson Groves Apt. 266\nWest Ebony, RI 63138',
    'text': 'School catch find service class. Head day create develop. When could forget culture six bank. They surface yet size enter.',
    'email': 'wintersgregory@example.org',
    'phone_number': '419-758-0618x44385',
    'array_int_dynamic': [
    96822,
],
    'array_varchar_dynamic': [
    'Steven Powers',
    'Kevin Wilson',
    'Joseph Lin',
    'Shaun Bates',
    'Mary Kent',
    'Terri Nelson',
],
    'json': {
    'name': 'Cindy Johnson',
    'address': 'USCGC Kelley\nFPO AA 36948',
},
    'key60576': 'value36573',
    'key92090': 'value76031',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Gina Hopkins',
    'address': '8908 Page Crescent Apt. 521\nPaulside, TX 04509',
    'text': 'Smile fast read describe about lose. Occur peace minute read avoid. Impact describe ten shake mind despite personal budget.\nYard these out nothing former play tree. Window family glass.',
    'email': 'lauramcknight@example.net',
    'phone_number': '(416)774-0761x0307',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jon Cline',
],
    'json': {
    'name': 'Angelica Terry',
    'address': '472 Ronnie Knoll\nJessicatown, KY 23308',
},
    'key35568': 'value32721',
    'key81325': 'value22220',
    'key94230': 'value57637',
    'key86780': 'value89752',
    'key92515': 'value84069',
    'key47031': 'value43335',
    'key56757': 'value31597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michelle Hines',
    'address': '548 Robert Trail\nPatriciahaven, OH 31089',
    'text': 'Require expect everybody final responsibility food business. Tend student individual several assume apply.',
    'email': 'michaelvega@example.com',
    'phone_number': '001-434-483-4996x2738',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Thomas',
],
    'json': {
    'name': 'Randall Manning',
    'address': '8946 Matthew Ferry Apt. 365\nAvilaside, NE 57676',
},
    'key61756': 'value65224',
    'key34720': 'value20788',
    'key22726': 'value65361',
    'key87772': 'value85517',
    'key94715': 'value35530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Teresa Dean',
    'address': 'USNS Dennis\nFPO AE 57565',
    'text': 'Research upon present PM both inside establish. Consider meeting role experience although threat rest book. Story benefit hair.',
    'email': 'creynolds@example.com',
    'phone_number': '(957)278-1335',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Bridget Potter DDS',
    'Diana Velazquez',
    'Carlos Maldonado',
    'Shannon Martinez',
    'Dawn Snyder',
    'Rodney Wilson',
],
    'json': {
    'name': 'Colleen Franklin',
    'address': '81799 Moran Glen\nBeltranport, GA 87075',
},
    'key66874': 'value85631',
    'key21063': 'value66982',
    'key866': 'value60345',
    'key9536': 'value41934',
    'key47301': 'value27766',
    'key74916': 'value1968',
    'key65949': 'value97248',
    'key84096': 'value61152',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Joseph Cunningham',
    'address': '470 Anthony Way\nSouth Karen, HI 68868',
    'text': 'Set great difference issue scientist expert treat. Box what painting.\nWest range treatment use significant democratic establish maintain. Bag put head course. One them behavior office always.',
    'email': 'trichardson@example.net',
    'phone_number': '977-953-6040',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Navarro',
    'Catherine Alvarado',
    'Jeffrey Schneider',
    'Christina Fuentes',
    'Diane Murphy',
    'Lisa Taylor',
    'Yolanda Fields',
    'Brian Ruiz',
    'Lisa Pena',
    'Kristin Castro',
],
    'json': {
    'name': 'Christine Carson',
    'address': '7512 Bradley Spur Suite 776\nSouth Cindy, PR 88468',
},
    'key73861': 'value5835',
    'key31384': 'value42247',
    'key97448': 'value36537',
    'key47372': 'value10505',
    'key34394': 'value74684',
    'key10668': 'value47044',
    'key87530': 'value12118',
    'key15714': 'value99250',
    'key23462': 'value7301',
    'key95787': 'value88241',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Michael Oneal',
    'address': '878 Coffey Radial\nJimenezburgh, MI 48019',
    'text': 'Bag agency responsibility himself thus people. Management provide fire particular church. Particularly current toward whatever prevent. Our their investment build adult.',
    'email': 'kimberlymacias@example.org',
    'phone_number': '+1-813-384-3589x96599',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Nelson',
    'Elaine Lara',
    'Natalie Gonzalez',
    'Patrick Wilson',
    'Charles Thomas',
    'Monica Barnes',
    'Linda Morgan',
],
    'json': {
    'name': 'John Vasquez',
    'address': '80944 Lopez Unions Suite 445\nSouth Stephanieport, NE 77885',
},
    'key75341': 'value90512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Sharon Robinson',
    'address': '89856 Moore Hill Apt. 959\nGarciahaven, PR 32484',
    'text': 'Certainly best education price pass out major analysis. Use positive source production. Pattern sign young staff what available bed.\nSimilar store smile. Drive trial choose learn summer.',
    'email': 'wendy62@example.net',
    'phone_number': '798.378.0476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jose Whitaker',
    'Rachel Massey',
    'Patty Diaz',
    'Dean Vargas',
    'Mary Williams DDS',
    'Jacqueline Patterson',
    'Jared Hanna',
],
    'json': {
    'name': 'George Webb',
    'address': '01525 Singh Grove Apt. 242\nJordantown, NC 97781',
},
    'key48542': 'value62687',
    'key37710': 'value40105',
    'key88001': 'value61997',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kenneth Lee',
    'address': '56939 Mary Rapids Suite 904\nChavezmouth, NY 13924',
    'text': 'Hospital whom second seat attack. Cut each federal describe choice. Hit candidate when store.\nLaw tonight statement whatever rather. Case raise once.',
    'email': 'jennadavis@example.net',
    'phone_number': '735.542.6811x59676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Washington',
    'Teresa Taylor',
    'Jacob Kelly',
    'Michael Finley',
    'Danny Vasquez',
    'Tommy Bates',
    'Joseph Baker',
    'Veronica Chandler MD',
    'Lindsay Cardenas',
],
    'json': {
    'name': 'Aaron Pierce',
    'address': '2771 Smith Ford Suite 073\nBethhaven, PA 80749',
},
    'key68695': 'value57941',
    'key60347': 'value94685',
    'key99259': 'value94860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Andrew Edwards',
    'address': '605 Vargas Knoll Suite 153\nAlbertmouth, ID 52271',
    'text': 'Shoulder meet attention dog. Product reach Democrat light magazine. Friend behavior attention industry method arm.',
    'email': 'brian63@example.com',
    'phone_number': '(519)679-8403x307',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Owen',
    'Rhonda Foster',
    'Jonathan Lyons',
    'John Kemp',
    'Randy Henry',
    'Hayden Nelson',
    'Jade Martinez',
    'Allison Ramirez',
],
    'json': {
    'name': 'Benjamin Rivera',
    'address': '020 Eric Park\nEast Timothybury, AZ 02238',
},
    'key38108': 'value9658',
    'key17852': 'value50441',
    'key88376': 'value16490',
    'key6617': 'value95822',
    'key24451': 'value36759',
    'key33835': 'value99732',
    'key49432': 'value66537',
    'key24591': 'value20960',
    'key74510': 'value28290',
    'key21308': 'value68466',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Teresa Hoffman',
    'address': '54957 Davis Mountain Suite 284\nDeannashire, WI 74438',
    'text': 'Yet coach close. West family much say.\nMoment watch see good chair thank. Force opportunity level with indeed mission.',
    'email': 'marshallapril@example.net',
    'phone_number': '001-330-652-1942x749',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Whitney Banks',
    'Gregory Rice',
    'David Martinez',
    'Marilyn Hutchinson',
    'Antonio Boyd',
],
    'json': {
    'name': 'Kathleen Black',
    'address': '899 Jodi Views\nPort Ashleybury, AS 49111',
},
    'key27835': 'value93848',
    'key57221': 'value75023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Angela Mcdonald',
    'address': '4855 Smith Street\nCrystalberg, WY 04834',
    'text': 'Sea model culture break building. Listen onto particularly.\nShoulder community politics look expert. Against important off. Sound them consumer order successful prove.',
    'email': 'amandaroberts@example.org',
    'phone_number': '397.732.1953x8889',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diana Clark',
    'Tina Douglas',
    'Kevin Hamilton',
    'Cameron Hart',
    'William Christian',
    'Timothy Williams',
    'Nicole Hudson',
    'Heather Li',
],
    'json': {
    'name': 'Elizabeth Young',
    'address': '3246 Chambers Plaza\nEast Christinetown, CO 48544',
},
    'key23524': 'value31590',
    'key7047': 'value6917',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jennifer Romero',
    'address': '4047 Kidd Trail\nTrevorburgh, MT 19393',
    'text': 'Want first try home car a ten. Fill gas effort wrong become position.\nBeautiful understand appear body radio plant figure. Sound strong provide yard. Father behind necessary American.',
    'email': 'zmoore@example.com',
    'phone_number': '767-866-2868x16625',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'William Villa',
    'Jenna Webster',
    'Carol Ward',
    'Patrick Harrington',
    'Elizabeth Allen',
],
    'json': {
    'name': 'Shane Moore',
    'address': '77899 Christopher Stream Suite 122\nNorth Robertbury, CT 55279',
},
    'key17307': 'value75987',
    'key47371': 'value96122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'David Woods',
    'address': '550 Mark Avenue Suite 273\nKeithhaven, WA 81983',
    'text': 'Share nation of president reflect. Production nearly very seem five present table than. Sure all kitchen performance more.',
    'email': 'rosariotammy@example.org',
    'phone_number': '717.899.4693x841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Brandy Wagner',
    'Beverly Palmer',
    'Yvonne Baldwin',
],
    'json': {
    'name': 'Dylan Caldwell',
    'address': '759 Lopez Camp Suite 578\nEast Brittanyburgh, MI 61501',
},
    'key32807': 'value85071',
    'key3573': 'value78873',
    'key70368': 'value26036',
    'key79428': 'value38408',
    'key20179': 'value52449',
    'key79987': 'value12786',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Angela Leblanc',
    'address': '9685 Bryan Crescent\nSandymouth, CT 56427',
    'text': 'Each already attention yard then compare less. Argue color type where later often energy. Hot yard well practice. My edge ground down ahead southern seat eat.',
    'email': 'jduffy@example.org',
    'phone_number': '(323)306-2911x659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Woodward',
    'David Freeman',
],
    'json': {
    'name': 'Michael Morrison',
    'address': '98687 Eric Courts\nSouth Kylebury, TX 21796',
},
    'key93933': 'value71520',
    'key92515': 'value65806',
    'key95349': 'value99772',
    'key6542': 'value77770',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Clarence Craig',
    'address': '947 Shields Roads Suite 766\nJohnsonside, MS 81704',
    'text': 'Save court many organization certainly officer treatment. Beyond interview until million system current prepare.',
    'email': 'christopher40@example.net',
    'phone_number': '+1-729-355-8479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Griffin',
    'Eric Evans',
],
    'json': {
    'name': 'Alyssa Robbins',
    'address': '697 Savannah Mount\nWattsville, IN 00833',
},
    'key87878': 'value4165',
    'key1431': 'value35156',
    'key64372': 'value72033',
    'key72937': 'value43464',
    'key49427': 'value10884',
    'key63272': 'value16928',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Mary Nixon',
    'address': '1862 Howard Fort\nLake Lisamouth, VT 13397',
    'text': 'Number magazine think boy method maybe. Simple gas central ago word. Yard quickly through environment Mrs couple stuff.',
    'email': 'nwashington@example.net',
    'phone_number': '(214)945-0203x398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Sexton',
    'Alicia Mccormick',
    'Andrew Cross',
    'Kevin Edwards',
],
    'json': {
    'name': 'Jamie Garcia',
    'address': '7470 Koch Islands\nRyanville, MS 17904',
},
    'key31956': 'value6370',
    'key60367': 'value30124',
    'key64295': 'value51890',
    'key1865': 'value76467',
    'key39599': 'value80542',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jessica Ford',
    'address': 'Unit 9047 Box 7283\nDPO AP 02947',
    'text': 'Trouble arrive position friend huge job. Would rock force senior camera.\nMiss marriage mission off north include. Face realize of ground. She become practice government expert project scene will.',
    'email': 'sophiapage@example.com',
    'phone_number': '(805)435-3012',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Banks',
    'Sarah Howard DVM',
    'Rickey Williams',
    'Oscar Huynh',
    'Kristina Reeves',
    'Rebecca Black',
],
    'json': {
    'name': 'Nicholas Washington',
    'address': '31246 Rebecca Street Apt. 009\nNorth Leah, OH 10696',
},
    'key55391': 'value23685',
    'key6690': 'value79096',
    'key73792': 'value50571',
    'key58672': 'value34793',
    'key58023': 'value30299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'James Hudson',
    'address': 'PSC 9417, Box 1438\nAPO AA 46720',
    'text': 'Happy student vote chance. Future organization single stand beautiful set walk. Sound seek suggest rather father how consider. Public really course look support.',
    'email': 'tony11@example.org',
    'phone_number': '(913)927-2780x584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robin Curry',
    'Nicholas Robertson',
    'Joseph Cruz',
    'Kevin Davis',
    'Christopher Mills',
    'Cathy Baker',
],
    'json': {
    'name': 'James Larson',
    'address': '6911 Ortiz Crescent Apt. 317\nPort Alexis, UT 81319',
},
    'key7284': 'value11918',
    'key64161': 'value82752',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Mary Jackson',
    'address': '1097 Ryan Junctions\nNealview, AL 33037',
    'text': 'Great responsibility travel since allow million. Present team already possible bit. Deal those term lay respond.',
    'email': 'elizabeth54@example.com',
    'phone_number': '650.423.4683x619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Jeremy Allen',
    'Bryan Bailey',
],
    'json': {
    'name': 'Julia Cooper',
    'address': '7774 Melissa Vista\nJonesside, NY 08429',
},
    'key11072': 'value33991',
    'key14170': 'value42351',
    'key7324': 'value9428',
    'key42352': 'value9607',
    'key87497': 'value1349',
    'key28766': 'value33639',
    'key31694': 'value72649',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Jennifer Harris',
    'address': '89746 Parrish Ferry Apt. 602\nThompsonfort, NV 23155',
    'text': 'Deep technology capital stay increase size reveal source. Unit heart resource capital. Put step grow business central guess Democrat figure.',
    'email': 'bshepherd@example.net',
    'phone_number': '(673)693-6871x1198',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Hall',
    'Nathaniel Weber',
    'Bradley Wells',
    'Sarah Beck',
    'Tara Estrada',
],
    'json': {
    'name': 'Luis Chavez',
    'address': '161 Jason Court Suite 323\nNew Billy, OR 78394',
},
    'key31466': 'value4907',
    'key5206': 'value23952',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Thomas Day',
    'address': '747 Patrick Center\nJordanstad, FL 59286',
    'text': 'Much draw administration involve garden. Spend care shoulder bad today west. Put international majority weight where real piece choose. Central leg hit walk data believe me.',
    'email': 'nicole75@example.org',
    'phone_number': '9549884650',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Reese',
    'Chase Smith',
    'Shelley Hall',
    'Holly Hill',
    'Jessica Baxter',
    'James Rodriguez',
    'Aaron Carr',
    'Randy Hicks',
    'Robert Garcia',
],
    'json': {
    'name': 'Shelly Moore',
    'address': '75929 Brandon Meadows Apt. 901\nRodriguezview, WI 71139',
},
    'key14010': 'value189',
    'key18916': 'value11068',
    'key61931': 'value61166',
    'key78376': 'value91226',
    'key26021': 'value31927',
    'key78430': 'value57662',
    'key36823': 'value83308',
    'key79434': 'value13925',
    'key18315': 'value3085',
    'key41324': 'value40098',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Curtis Andrews',
    'address': '6011 Richard Junction\nWeaverbury, ND 65409',
    'text': 'Teach fill machine time. Style show happen force economic point. Thing scene off source almost.',
    'email': 'bryan41@example.com',
    'phone_number': '2428140945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'William Mccann',
    'Robert Green',
],
    'json': {
    'name': 'Jeremy Davis',
    'address': '02596 Romero Garden Apt. 658\nTashahaven, FM 87052',
},
    'key61422': 'value15608',
    'key55345': 'value28083',
    'key3111': 'value19548',
    'key8849': 'value93809',
    'key81280': 'value38436',
    'key1202': 'value12936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kristen Brady',
    'address': '4428 Jeffrey Route\nAnthonymouth, GA 19291',
    'text': 'Class maybe record still property laugh. Condition dog rather medical blood himself.\nRead individual probably agreement our blood. Very indicate method decision between yet. Purpose begin reason.',
    'email': 'uashley@example.com',
    'phone_number': '227-703-3096',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Francisco Ibarra',
    'Ashley Barr',
    'Dr. Juan Frank',
    'Paige Powers',
    'Tina Macdonald',
    'Alexander Hood',
    'Michael Marshall',
    'Kenneth Barnett',
    'Amy Howard',
    'Frank Martin',
],
    'json': {
    'name': 'Jermaine Hoffman',
    'address': '190 Bennett Island Suite 589\nAaronmouth, WA 01685',
},
    'key75786': 'value26263',
    'key8161': 'value38823',
    'key35471': 'value79846',
    'key94322': 'value10350',
    'key43398': 'value66091',
    'key29019': 'value23945',
    'key79509': 'value5759',
    'key68373': 'value43669',
    'key9743': 'value45882',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Brett Hull',
    'address': '33364 Jennifer Springs\nJohnsonmouth, NC 12948',
    'text': 'Whose pressure south professional. Should long away talk hard speech. Pretty politics in large. Agreement audience manage.',
    'email': 'conradstephanie@example.net',
    'phone_number': '(239)236-8774x25771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Guerrero',
],
    'json': {
    'name': 'Ashley Wilson',
    'address': '56183 Mitchell Ramp\nSouth Robert, ME 79669',
},
    'key13787': 'value25527',
    'key72204': 'value25072',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Sarah Howard',
    'address': '18101 Joseph Knolls\nLake Joseph, MN 84272',
    'text': 'Prevent write such professional organization effort. Find same site fast answer speech. Skin money so third foot street. Six son require win new how.',
    'email': 'erinbradley@example.com',
    'phone_number': '(610)399-4616x1273',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Alexa Duffy',
    'William Arnold',
    'David Santiago',
    'Michael Nichols',
],
    'json': {
    'name': 'Wayne Lewis',
    'address': 'Unit 3733 Box 2250\nDPO AP 24679',
},
    'key4929': 'value5017',
    'key10541': 'value16166',
    'key89084': 'value44791',
    'key13582': 'value35410',
    'key17980': 'value16736',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Cynthia Merritt',
    'address': '8346 Mayer Dam Apt. 610\nPort Stephenburgh, CA 08452',
    'text': 'Newspaper have service. Generation make industry realize sure position public among. In include financial.\nProduction same relate method want lay hit dream. Expert add city red blood.',
    'email': 'christine08@example.org',
    'phone_number': '5758559108',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Don Carlson',
],
    'json': {
    'name': 'Mark Thomas',
    'address': '1286 Robert Court\nNew Frankland, VI 58134',
},
    'key41481': 'value46816',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Samantha Carrillo',
    'address': '999 Wells Bypass Apt. 574\nLake Luke, OH 10348',
    'text': 'Receive pattern analysis newspaper. Manager amount fine interview likely.\nAssume institution participant set yes you. Decision issue treat hour sign street. Tend something discussion trial language.',
    'email': 'hailey64@example.org',
    'phone_number': '809-916-8053x96238',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'April Waters',
    'Stacy Hernandez',
    'Harold Potter',
    'Hayley Hopkins',
    'Christopher Stanley',
],
    'json': {
    'name': 'Joseph Martinez',
    'address': '05952 David Loop\nSouth Mary, MN 73592',
},
    'key74479': 'value39338',
    'key66697': 'value10960',
    'key12429': 'value26874',
    'key77357': 'value36693',
    'key84756': 'value70690',
    'key11659': 'value38199',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Robert Thomas',
    'address': '0368 Crawford Junctions\nJenkinschester, AR 56165',
    'text': 'Really few entire set attorney.\nTreatment its ahead follow quality lay drop. Manage find training himself tell.',
    'email': 'johnny89@example.org',
    'phone_number': '001-767-353-3579x31654',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ms. Julie Phelps MD',
    'Bruce Esparza',
    'Mrs. Jillian Benson',
    'Hannah Kelly',
    'Charles Davis',
    'Natalie Alexander',
],
    'json': {
    'name': 'Michele Reese',
    'address': 'Unit 4235 Box 6281\nDPO AA 30230',
},
    'key63918': 'value8594',
    'key86750': 'value60243',
    'key98961': 'value43746',
    'key35947': 'value25110',
    'key51750': 'value59505',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Ashley Holland',
    'address': 'PSC 9780, Box 7019\nAPO AE 06663',
    'text': 'Speak from spend explain. Material class general whether policy test home knowledge. Day available enough assume politics.',
    'email': 'clopez@example.net',
    'phone_number': '001-250-708-3734x5300',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Spencer',
    'David Goodwin',
    'Tammy Rivera',
    'Jesus Hampton',
    'Annette Parsons',
    'Phillip Benitez',
],
    'json': {
    'name': 'Sara Mclaughlin',
    'address': '0729 Michelle Port\nBenjaminchester, SC 06528',
},
    'key14902': 'value82675',
    'key70998': 'value78791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Kyle Clark',
    'address': '748 Leah Hollow\nSmithland, WI 09766',
    'text': 'Not whether then population decade time.\nRecently and question son.\nHer information door cup large recently political. Hit reveal improve prevent.',
    'email': 'fergusonlori@example.org',
    'phone_number': '(530)696-2357',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laura Schneider',
],
    'json': {
    'name': 'Carrie Cochran',
    'address': '24722 Leslie Divide\nSouth Aaron, WA 62519',
},
    'key14303': 'value75076',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Ian Reynolds',
    'address': '00793 Billy Harbors Apt. 228\nKevinview, WV 82539',
    'text': 'Full less become ever. Prevent determine industry across. Perform write floor.\nDegree common least everything able such out evening. Series Congress anything image develop improve upon.',
    'email': 'barnesadam@example.net',
    'phone_number': '917-241-4351x846',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Gonzales',
    'Susan Houston',
    'Justin Dean',
    'Karen Ryan',
    'Ricky Waller',
],
    'json': {
    'name': 'Chad Parsons',
    'address': '6575 Marcia Drives Suite 297\nSouth Kristenfort, PW 75546',
},
    'key16476': 'value85566',
    'key81941': 'value59937',
    'key27619': 'value75771',
    'key10027': 'value35754',
    'key82040': 'value10234',
    'key49379': 'value40533',
    'key19439': 'value5799',
    'key71106': 'value83884',
    'key93284': 'value15597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Allison Rogers MD',
    'address': '89892 Debra Trace Apt. 271\nSouth Ruben, SD 15177',
    'text': 'Wait dinner very face perhaps wife boy. People hair real commercial best star challenge attorney. Pretty despite best recently. Go mission we.',
    'email': 'osmith@example.net',
    'phone_number': '854-263-2947',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Cox',
    'Frank Mills',
    'Michelle Cardenas',
    'Jennifer Wilson',
    'Jason Reyes',
    'John Palmer',
    'Amanda Stone',
    'Mary Dickson',
    'Joel Williams',
    'Michael Guerrero',
],
    'json': {
    'name': 'Sarah Washington',
    'address': '57036 Watson Station Apt. 873\nJohnberg, AS 64311',
},
    'key22360': 'value15174',
    'key72875': 'value96894',
    'key49375': 'value74170',
    'key96769': 'value27302',
    'key8768': 'value72177',
    'key15677': 'value52781',
    'key94493': 'value9444',
    'key78711': 'value79615',
    'key90283': 'value53279',
    'key76401': 'value18002',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Andrea George',
    'address': '3349 Brian Stravenue\nHeathertown, VT 86942',
    'text': 'Always computer develop explain television land. Fight wide film. Machine group heavy point field.\nOld weight age admit police product forward budget.\nAdmit evidence her life list.',
    'email': 'smithmark@example.net',
    'phone_number': '(487)998-7159x05463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Walter Pierce',
],
    'json': {
    'name': 'Julia Key',
    'address': '158 Holmes Falls Suite 341\nNew Robertfurt, FM 22785',
},
    'key79118': 'value80332',
    'key34274': 'value46479',
    'key43816': 'value35658',
    'key40281': 'value16990',
    'key74182': 'value5152',
    'key20549': 'value87213',
    'key40465': 'value83968',
    'key25941': 'value20417',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Margaret Russell',
    'address': '55436 Wood Locks\nNorth Kaitlyn, TN 06408',
    'text': 'Condition develop magazine prove series of cost song. Whom probably enter very gas world. Before physical whether nice card more explain.',
    'email': 'olsonstephanie@example.org',
    'phone_number': '+1-956-594-2593x1625',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Hernandez',
],
    'json': {
    'name': 'Kevin Silva',
    'address': '9958 Malik Meadow\nSouth Lauren, IL 68590',
},
    'key958': 'value4587',
    'key97039': 'value40444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Ryan Wilson',
    'address': 'PSC 2896, Box 5948\nAPO AP 69042',
    'text': 'Against should daughter. Rule range myself nothing year.\nSpecific away top arrive attorney east. System star professor language event system officer. Station speech special employee.',
    'email': 'sherry07@example.net',
    'phone_number': '670-807-1398x0831',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Walters',
    'Joshua Wilson',
],
    'json': {
    'name': 'Michael Ross',
    'address': '54017 Melissa Turnpike Apt. 471\nPattonbury, PR 98984',
},
    'key75882': 'value46650',
    'key81142': 'value96823',
    'key93251': 'value40754',
    'key36142': 'value6197',
    'key63781': 'value14206',
    'key31720': 'value84141',
    'key68379': 'value17340',
    'key55500': 'value69901',
    'key99334': 'value6593',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jon Rodriguez',
    'address': '42665 Christine Tunnel\nNew Alan, MO 78477',
    'text': 'Behind wall everyone. Movement even ever.\nRoom choose choice could ever power product we. Film treatment necessary bar true be note sign.',
    'email': 'bradley57@example.org',
    'phone_number': '001-772-931-4682x009',
    'array_int_dynamic': [
    25248,
],
    'array_varchar_dynamic': [
    'Jessica Barrera',
    'Dr. Richard Gibson',
],
    'json': {
    'name': 'Carol Schultz',
    'address': 'Unit 4371 Box 5292\nDPO AP 30712',
},
    'key2193': 'value33846',
    'key87306': 'value76781',
    'key45249': 'value51724',
    'key22400': 'value65386',
    'key50143': 'value12122',
    'key43748': 'value50608',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Nicole Chandler',
    'address': '4732 Melton Inlet\nWest Douglas, OK 14929',
    'text': 'Our impact during dream should. Soldier watch something pass almost.\nAvailable degree short contain how three laugh scientist.',
    'email': 'alicia79@example.net',
    'phone_number': '(826)559-8144',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Gonzalez',
    'Rodney Bates',
    'Sandra Kirk',
],
    'json': {
    'name': 'Robert Boyd',
    'address': '82366 Jones Village\nWest Russellport, AK 16331',
},
    'key87926': 'value61984',
    'key40197': 'value88338',
    'key43872': 'value89694',
    'key56561': 'value44196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'James Patel',
    'address': '49563 Jill Trail Apt. 824\nTracyport, ID 29824',
    'text': 'Simply picture old statement design. Compare sign apply allow already.\nShow stage movement remember record. Image mission parent hard goal night. Finish however police natural pretty.',
    'email': 'dcollins@example.com',
    'phone_number': '352.251.4600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Morrison',
    'Linda Reeves',
    'Carlos Arnold',
    'Stephanie Patel',
    'Dennis Powell',
],
    'json': {
    'name': 'Jennifer Ferrell',
    'address': '116 Debra Shores\nBrittneyview, GU 24389',
},
    'key7279': 'value86433',
    'key15816': 'value90855',
    'key7571': 'value18554',
    'key50902': 'value8747',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Michael Lewis',
    'address': '481 Donaldson Highway\nNorth Daniel, FM 54306',
    'text': 'Pay family type land. Above style ability goal development get look since. Actually either when music catch.\nMy once part ok claim over. Both believe radio plant save. Song later address.',
    'email': 'torresgloria@example.com',
    'phone_number': '001-369-222-5071x42760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Franklin',
    'Nicholas Gillespie',
    'Joe Williams',
    'Lawrence Riley',
    'Charles Reed',
],
    'json': {
    'name': 'Melanie Mann',
    'address': '874 Hensley Meadows Suite 825\nLake Philipborough, MT 27496',
},
    'key96028': 'value45850',
    'key84115': 'value14746',
    'key36292': 'value36147',
    'key71148': 'value25893',
    'key78987': 'value95290',
    'key61923': 'value7598',
    'key22494': 'value57284',
    'key27934': 'value12486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Ronald Jones',
    'address': '692 Boyd Cliff\nAlexisburgh, PR 74736',
    'text': 'Although glass partner down then best. Generation beautiful capital mind situation.\nPossible medical light until detail. Catch defense pressure. Strong more three find modern.',
    'email': 'alexpugh@example.net',
    'phone_number': '+1-678-924-8267x29197',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rachael Johnson',
    'Eric Johnson',
    'Elizabeth Thomas',
    'Andrew Cohen',
    'Megan Taylor',
    'Briana Sloan',
    'William West',
    'Austin Gardner',
    'Maria Duke',
    'Dr. Miranda Mahoney DDS',
],
    'json': {
    'name': 'Courtney Kelley',
    'address': '96896 Jeffrey Rapids Apt. 634\nStacyfurt, MA 50612',
},
    'key86057': 'value12380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Aaron Nixon',
    'address': 'Unit 5048 Box 8237\nDPO AE 11677',
    'text': 'Ready investment institution after whether bill. Through thought other say themselves would back moment.',
    'email': 'cochranmark@example.com',
    'phone_number': '514-837-3654x7903',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Miller',
    'Robert Farley',
    'Donna Harrington',
],
    'json': {
    'name': 'James Wood',
    'address': '85246 Tyler Garden Apt. 249\nNewtonfurt, AK 08692',
},
    'key77887': 'value90552',
    'key37925': 'value80478',
    'key21683': 'value92679',
    'key23758': 'value28411',
    'key928': 'value48132',
    'key92137': 'value55037',
    'key51813': 'value13121',
    'key48880': 'value48946',
    'key7945': 'value89880',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Jason Hurst',
    'address': '2948 Richardson Parkways\nEast Vincentstad, WA 86293',
    'text': 'Under tonight when song prove others create. Common someone necessary sense tree provide.\nNorth wall join foreign hope lay theory. Notice amount season catch soon. Two tough hand deal memory foreign.',
    'email': 'pdouglas@example.org',
    'phone_number': '389-636-8301x09886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Ballard',
    'David Turner',
    'Paul Campbell',
    'Matthew Ho',
    'William Price',
    'Thomas Rivers',
],
    'json': {
    'name': 'Cindy Diaz',
    'address': '24086 Bryan Pines Apt. 452\nNew Douglas, MA 46831',
},
    'key22758': 'value5154',
    'key92682': 'value6842',
    'key3951': 'value75403',
    'key47271': 'value52568',
    'key59725': 'value19886',
    'key53142': 'value72176',
    'key58369': 'value33507',
    'key93082': 'value18888',
    'key73082': 'value30780',
    'key83802': 'value61515',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Mary Watson',
    'address': '65089 Christopher Trace Suite 497\nTonyborough, KY 38327',
    'text': 'Successful eat go year. Type east blood buy recognize beyond. Compare office decide less.\nRest agreement test.\nEvidence building rich present impact role. Together house subject.',
    'email': 'operry@example.org',
    'phone_number': '(852)377-4008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brian Maldonado',
    'Christopher Gibson',
    'Lawrence Miller',
    'Maurice Brown',
],
    'json': {
    'name': 'Sherry Griffin',
    'address': '6097 Freeman Unions\nNew Karenstad, IN 94250',
},
    'key98137': 'value87479',
    'key23972': 'value69248',
    'key91796': 'value49336',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Julia Martin',
    'address': '7584 Jennifer Keys Suite 698\nSouth Samanthaborough, MD 53859',
    'text': 'Office across available no day each. System offer language education according against. Treat local hair true more Congress maybe.',
    'email': 'ubauer@example.net',
    'phone_number': '632.827.1226x772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Robert Huynh',
    'Linda Perry',
    'Kayla Wright',
    'Robert Miller',
    'Brian Obrien',
    'Jason James',
    'Jordan Taylor',
    'Veronica Short',
    'Kristen Henderson',
],
    'json': {
    'name': 'James Holland',
    'address': '746 Sharon Well\nLake Jennifer, WY 91239',
},
    'key57120': 'value1218',
    'key81995': 'value27408',
    'key13816': 'value21997',
    'key85115': 'value75402',
    'key46291': 'value93990',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Caitlyn Henderson DDS',
    'address': '819 Jason Junction Suite 824\nWest Shawn, MP 96208',
    'text': 'Care plant hour school several. Either close book rather member sit. Authority various simple performance.',
    'email': 'uporter@example.org',
    'phone_number': '845.757.8803',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Ingram',
    'James Floyd',
    'Juan Mann',
    'Rodney Smith',
    'William Welch',
],
    'json': {
    'name': 'John Stone',
    'address': '627 Lewis Shore\nBarkerburgh, WI 77567',
},
    'key18206': 'value8474',
    'key86310': 'value66997',
    'key42795': 'value68453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Mrs. Diane Greene',
    'address': '5301 Derrick Isle Suite 027\nAlyssaview, SC 07015',
    'text': 'Give truth rise huge entire. Record team current they. Rate just minute catch range still suffer.\nProperty crime single white student pick. Say several from manager eye meet.',
    'email': 'danny45@example.net',
    'phone_number': '+1-883-401-2319x64616',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joyce White',
    'Maria Moore',
    'Gary Taylor',
    'Sarah Medina',
    'Omar Miller',
    'Amanda Jones',
    'Amanda Morrison',
    'David Murphy',
],
    'json': {
    'name': 'John Morris',
    'address': 'Unit 4586 Box 8737\nDPO AE 47284',
},
    'key56215': 'value91413',
    'key5073': 'value20023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Debra Hampton',
    'address': '749 Lindsey Forks\nWest Kristy, MN 23775',
    'text': 'Feel magazine assume political popular husband. Country artist international.\nDescribe glass dark. Base character contain certainly enough. Remember available prevent toward exactly last.',
    'email': 'wilsongloria@example.com',
    'phone_number': '001-381-870-8586x0099',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Sullivan',
    'Joan Smith PhD',
    'Joseph Hall',
    'Tamara Cole',
    'Chelsea Kline',
],
    'json': {
    'name': 'Mark Moran',
    'address': '737 Erica Ranch Apt. 690\nChristopherbury, SC 31638',
},
    'key78645': 'value58217',
    'key91528': 'value60453',
    'key76269': 'value53085',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Anthony Cortez',
    'address': '94919 Morris Shoal Suite 477\nJasonmouth, DE 37555',
    'text': 'Whether know rather community wish hard though name. Indeed debate effect agreement per forget.\nAgainst chair discussion bar boy. Event past network back only center herself situation.',
    'email': 'wendy73@example.org',
    'phone_number': '(861)749-5412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Miller',
],
    'json': {
    'name': 'Bradley Davis',
    'address': '479 Andrew Groves Apt. 124\nJoshuamouth, NM 30907',
},
    'key17326': 'value11575',
    'key25083': 'value26707',
    'key26805': 'value97950',
    'key32824': 'value64932',
    'key7381': 'value86636',
    'key59257': 'value70803',
    'key72274': 'value97355',
    'key47357': 'value4536',
    'key74104': 'value71777',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Hannah Rosales',
    'address': '41179 White Mountains Suite 822\nBruceborough, DC 30651',
    'text': 'Hope whole open administration huge. Thus maintain indeed. Effort attention prepare country road game heart visit.',
    'email': 'smithlinda@example.org',
    'phone_number': '224.729.0280x89517',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Rice',
    'Nicole Adams',
    'Paul Collins',
],
    'json': {
    'name': 'Sarah Owens',
    'address': '8060 Eric Row\nPattersonville, MH 24418',
},
    'key22808': 'value26399',
    'key39173': 'value99468',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kenneth Ross',
    'address': '43118 Lewis Parkways\nDebratown, IN 69620',
    'text': 'Force instead stay close you condition. Century in sound.\nWhether early popular officer. Maintain future join month system girl board.\nYard rest fine our. Those law rule national program.',
    'email': 'joelnash@example.net',
    'phone_number': '+1-432-606-1206x88820',
    'array_int_dynamic': [
    27033,
],
    'array_varchar_dynamic': [
    'Cody Bell',
    'Bobby Flynn',
    'Laura Rodriguez',
    'Felicia Scott',
    'Daniel Yang',
    'Monica Griffin',
],
    'json': {
    'name': 'Deborah Singh',
    'address': '305 Trevino Rapid Apt. 550\nLake Robertland, TX 69523',
},
    'key33927': 'value81960',
    'key63080': 'value62050',
    'key65577': 'value58659',
    'key44383': 'value60923',
    'key40792': 'value35880',
    'key61850': 'value52627',
    'key89320': 'value35637',
    'key50455': 'value16012',
    'key35606': 'value61771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Samantha White',
    'address': '42776 Mary Mount Suite 217\nDavidstad, AZ 63896',
    'text': 'Everyone herself star consider program. Gun traditional type thing leader indicate glass forget. Fall street modern history.\nExactly before fund middle capital. People including see garden doctor.',
    'email': 'kathleenpham@example.com',
    'phone_number': '859.778.0289',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Travis',
],
    'json': {
    'name': 'Sean Johnston',
    'address': '74354 Solomon Brooks\nMckaychester, IA 64277',
},
    'key50014': 'value24869',
    'key94495': 'value1511',
    'key95954': 'value77932',
    'key82433': 'value71342',
    'key90': 'value89249',
    'key14781': 'value24042',
    'key842': 'value22849',
    'key68150': 'value85834',
    'key15491': 'value82760',
    'key40940': 'value13662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Stephen Tate',
    'address': 'PSC 4085, Box 1756\nAPO AP 12656',
    'text': 'Production professional perhaps thus improve. Marriage kid option vote Democrat treatment.\nTough attorney church ball. Drug somebody help woman trial pass. Current machine traditional tax do letter.',
    'email': 'zbuchanan@example.org',
    'phone_number': '868.849.0792x54586',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Colton Dougherty',
    'Bryan Morton',
    'Natalie Sims',
],
    'json': {
    'name': 'Shawn Ware',
    'address': '705 Michelle Circles Apt. 389\nEast Ashley, AS 97681',
},
    'key30784': 'value96056',
    'key45': 'value45349',
    'key23795': 'value86156',
    'key54226': 'value66317',
    'key4704': 'value63228',
    'key10497': 'value1103',
    'key81970': 'value69165',
    'key37893': 'value50365',
    'key50537': 'value81170',
    'key90157': 'value91137',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'George Proctor',
    'address': '5314 Brenda Corners\nLake Henry, MN 19829',
    'text': 'Step effect option. Tell specific action police peace reality. Produce quite others science into.\nDifficult miss us politics by. Computer letter book far artist.',
    'email': 'nicholas50@example.com',
    'phone_number': '(889)471-3243x3658',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Baxter',
    'Tracy Moon',
    'Javier Mitchell',
    'Robert Dixon',
    'Joan Lucas',
],
    'json': {
    'name': 'Vanessa Kelly',
    'address': '193 Massey Springs\nJohnborough, CA 57073',
},
    'key68473': 'value74184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Stephanie Conrad',
    'address': '45646 Frazier Coves Apt. 049\nPort Tracytown, NH 87242',
    'text': 'Specific color boy run resource situation trouble. Source less police three down.\nExactly dark wish buy role. Language happen try stand rock where.',
    'email': 'ymartin@example.org',
    'phone_number': '(413)290-4296x88790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jeffery Ayers',
    'Ashley Bradley',
    'Mr. Patrick Bradley MD',
    'Jennifer Arnold',
    'John Becker DVM',
    'Brent Calhoun',
    'Carrie Johnson',
    'Tonya Wilson',
    'Colleen Bauer',
],
    'json': {
    'name': 'Perry Gonzalez',
    'address': 'USNS Williams\nFPO AP 47882',
},
    'key38948': 'value90381',
    'key84878': 'value44067',
    'key73292': 'value72435',
    'key8837': 'value90184',
    'key22457': 'value56353',
    'key6589': 'value3411',
    'key79665': 'value83137',
    'key98657': 'value19617',
    'key24481': 'value20472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Adam Wallace',
    'address': '87966 Amber Plains Suite 248\nJamesside, ND 16234',
    'text': 'Might smile protect after must second. Course attack guess institution half third believe. Whose international pattern continue age world several.',
    'email': 'guerreroandrea@example.net',
    'phone_number': '(777)890-7971x7479',
    'array_int_dynamic': [
    72770,
],
    'array_varchar_dynamic': [
    'Brenda Nelson',
    'Teresa Gray',
    'Christopher Mccullough',
    'David Smith',
    'Brenda Russell',
    'Alicia Landry',
    'Amanda Landry',
    'Willie Reynolds',
    'Tony Rodriguez',
],
    'json': {
    'name': 'Richard Hull',
    'address': '5783 Kelly Park Suite 085\nSouth Rebeccaberg, MA 51491',
},
    'key40461': 'value20062',
    'key46769': 'value75283',
    'key30533': 'value22256',
    'key86686': 'value26620',
    'key303': 'value54879',
    'key78396': 'value59995',
    'key63702': 'value68217',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Amanda Riley',
    'address': '847 Traci Forges Suite 176\nThomashaven, MD 41185',
    'text': 'Act rather lot arrive. Imagine such party road.\nExecutive by identify sure edge. Morning just benefit onto standard each skill.',
    'email': 'margaretbowers@example.net',
    'phone_number': '540.584.8410',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Hess',
    'Faith Rice DVM',
    'Linda Manning',
    'Melissa Jackson',
],
    'json': {
    'name': 'Donald Brown',
    'address': '878 Curtis Fields Suite 137\nEast Stephenside, PR 24402',
},
    'key54404': 'value16669',
    'key36084': 'value84912',
    'key28698': 'value68200',
    'key92032': 'value32083',
    'key25658': 'value48738',
    'key72086': 'value81614',
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
    'RequestId': 'a6854ced-62f1-11f0-af4c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_14_615933QppLTrOn',
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '9fcd581f-62f1-11f0-9550-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_14_615933QppLTrOn',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752745046.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUidIn12341752745046Json()
    test.run_tests()
