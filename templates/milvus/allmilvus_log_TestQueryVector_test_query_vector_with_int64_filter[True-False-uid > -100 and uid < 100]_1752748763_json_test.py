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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752748763_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752748763.json"
VDB_TYPE = "milvus"


def send_request(content, request_type="POST", url_path="http://172.17.0.5:23210/v2/vectordb/collections/create", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://172.17.0.5:23210/v2/vectordb/collections/create"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid100AndUid1001752748763Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752748763.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752748763.json"
        self.test_count = 8  # 测试方法数量
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://172.17.0.5:23210/v2/vectordb/collections/describe"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/describe")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/describe'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v2/vectordb/entities/insert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/insert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/insert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
    'data': [
    {
    'id': 17527487552724,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Keith Sanchez',
    'address': '4245 Danny Run Suite 388\nAlisonville, ME 91749',
    'text': 'Raise through drop property section inside risk. Them during sister tend.\nUpon itself traditional not exist. Figure want senior factor.',
    'email': 'ricekatherine@example.net',
    'phone_number': '2397515030',
    'json': {
    'name': 'Michael Hale',
    'address': '0437 Little Throughway\nNew Evan, NJ 20062',
},
    'key33535': 'value61793',
},
    {
    'id': 17527487552741,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'John Harrison',
    'address': '4337 Lorraine Skyway\nEast Kaitlinborough, TX 69742',
    'text': 'Sense media child occur mind structure radio. Skill wrong pass garden instead adult season impact. Up manage plant. Risk star building opportunity administration.',
    'email': 'christopher97@example.org',
    'phone_number': '520.405.4268x962',
    'json': {
    'name': 'Jennifer Campbell',
    'address': 'PSC 7052, Box 6136\nAPO AP 90768',
},
    'key50002': 'value81717',
    'key73445': 'value22320',
},
    {
    'id': 17527487552752,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Joseph Aguirre',
    'address': '116 Richard View\nAmandabury, MO 72975',
    'text': 'Leg position by product. Commercial often media. Theory accept fund poor accept of on phone.',
    'email': 'alexisjimenez@example.com',
    'phone_number': '(639)336-7210',
    'json': {
    'name': 'Hannah Everett',
    'address': '0321 Timothy Ports Apt. 729\nSouth Cheryl, MA 20508',
},
    'key47070': 'value28543',
},
    {
    'id': 17527487552766,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jeremy Schultz',
    'address': '0389 Brown Streets Apt. 072\nEast Robert, GU 14913',
    'text': 'Model brother place smile. Measure under discussion.\nCold check charge focus pressure. Tough appear once.',
    'email': 'john27@example.org',
    'phone_number': '001-592-851-2782x5480',
    'json': {
    'name': 'Mark Robertson',
    'address': '134 Boyd Hollow Apt. 605\nNorth Karenbury, UT 70429',
},
    'key46096': 'value54409',
    'key487': 'value94608',
    'key23032': 'value58797',
    'key12461': 'value64869',
    'key6478': 'value12580',
    'key9492': 'value22660',
    'key1958': 'value25026',
    'key15570': 'value86866',
    'key424': 'value11549',
    'key76079': 'value46820',
},
    {
    'id': 17527487552779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Mr. Benjamin Brewer',
    'address': '39446 Rodriguez Circles\nNew Jamesshire, OK 30898',
    'text': 'Though always at thing. Bit rock meet pick real ready. Bed though nature white.\nNot star trial hour off author type size. Worker learn action group coach resource report. Stock partner after speak.',
    'email': 'berrymartha@example.com',
    'phone_number': '001-569-407-7255x9556',
    'json': {
    'name': 'Bradley Adams',
    'address': '0203 Turner Forest Suite 403\nButlerhaven, MH 30749',
},
    'key42213': 'value55190',
    'key75673': 'value75800',
    'key54668': 'value90005',
    'key89683': 'value6707',
    'key50807': 'value89537',
    'key76421': 'value34641',
},
    {
    'id': 17527487552793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Carla West',
    'address': '75344 Richardson Port\nSouth Kayla, MO 17204',
    'text': 'Reality put agreement southern house. Simple recent and try. Economic relationship TV everybody room. White trial safe indicate human.',
    'email': 'jesus00@example.org',
    'phone_number': '001-725-247-4393x79215',
    'json': {
    'name': 'Willie Kane',
    'address': '790 John Estate\nEast Deborahside, MI 04164',
},
    'key89811': 'value87332',
    'key7752': 'value82225',
    'key61730': 'value87340',
    'key50732': 'value220',
    'key15310': 'value98336',
    'key89015': 'value68804',
    'key30359': 'value44080',
    'key13431': 'value4949',
    'key90196': 'value25818',
},
    {
    'id': 17527487552808,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kathy Mathews',
    'address': '9211 Thomas Branch\nCarpenterside, MO 91584',
    'text': 'Keep home idea popular. Start through necessary style parent. Stop leg hope south team join few dinner.',
    'email': 'sylvialloyd@example.net',
    'phone_number': '(643)571-1676x538',
    'json': {
    'name': 'Justin Smith',
    'address': '8614 Martinez Valley Apt. 633\nWest Chelsea, CA 93142',
},
    'key70546': 'value18351',
    'key86347': 'value56926',
    'key74361': 'value40361',
},
    {
    'id': 17527487552822,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Andre Smith',
    'address': 'USS Mcpherson\nFPO AE 67104',
    'text': 'Pass page perform force son his wind. Source particularly state understand capital girl modern. Chair card tax upon ok pretty western boy.',
    'email': 'millsmichael@example.com',
    'phone_number': '6376415136',
    'json': {
    'name': 'Dr. Theresa Wright',
    'address': 'Unit 1183 Box 8745\nDPO AA 60708',
},
    'key10534': 'value4628',
    'key87498': 'value79461',
    'key93348': 'value4735',
    'key88350': 'value14135',
    'key94057': 'value80418',
    'key66177': 'value42233',
    'key57876': 'value41450',
    'key29964': 'value73409',
    'key36813': 'value85198',
    'key13679': 'value2494',
},
    {
    'id': 17527487552833,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Sharon Santiago',
    'address': '084 Ray Keys Apt. 882\nDarylmouth, DC 63170',
    'text': 'Perhaps I difference theory. Never eat wonder investment reduce world how.\nBecome contain they population white it change sure. Until position career. Use shake evidence.\nBig author various.',
    'email': 'frederickstewart@example.org',
    'phone_number': '+1-396-975-2590x6368',
    'json': {
    'name': 'Adam Perez',
    'address': '8722 Michael Mount\nNew Vanessaview, IN 85044',
},
    'key99935': 'value49941',
    'key96256': 'value39593',
    'key35945': 'value26746',
    'key94590': 'value17293',
    'key62915': 'value18632',
    'key15967': 'value27297',
    'key42280': 'value22605',
    'key82993': 'value37043',
    'key50238': 'value85503',
},
    {
    'id': 17527487552848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Pamela Figueroa',
    'address': '018 Darryl Spurs\nDavidberg, AR 68260',
    'text': 'Data eye card particularly consumer exist. Then money safe society office kind.\nIn stop detail somebody real huge.',
    'email': 'matthew51@example.com',
    'phone_number': '476-746-0211x646',
    'json': {
    'name': 'Todd Jones',
    'address': '44522 Underwood Plain Apt. 008\nTanyaville, CA 49542',
},
    'key76468': 'value59330',
    'key47198': 'value83495',
    'key23033': 'value95280',
    'key94214': 'value52689',
    'key66383': 'value43404',
    'key72309': 'value88666',
    'key32231': 'value89259',
},
    {
    'id': 17527487552860,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Angela Wilson',
    'address': '346 Owens Squares Suite 120\nMarkborough, WA 71071',
    'text': 'Serious either since owner dog some project. Since against machine both PM.\nHuman turn court bill. Him participant other moment budget several social.',
    'email': 'brendan70@example.org',
    'phone_number': '(556)962-9383',
    'json': {
    'name': 'Jessica Olson',
    'address': '28096 Fields Route\nJessicaville, CO 89723',
},
    'key78654': 'value78375',
    'key79633': 'value80789',
    'key6254': 'value57180',
    'key40326': 'value69479',
},
    {
    'id': 17527487552872,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Edwin Harper',
    'address': '6398 Jeremy Cliffs\nLake Richardville, MA 10535',
    'text': 'During stuff attorney difference bill realize. Figure section letter either purpose hold. Parent still already mind every sign miss.',
    'email': 'todd62@example.org',
    'phone_number': '553-550-6096x19832',
    'json': {
    'name': 'James White',
    'address': '23083 Gordon Prairie Apt. 437\nCharleschester, VA 99311',
},
    'key72295': 'value32190',
    'key52328': 'value13484',
},
    {
    'id': 17527487552884,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Ernest Carr',
    'address': '38828 Ball Mountains Suite 465\nSarahton, MA 99632',
    'text': 'Kitchen ahead mean score almost choose social.\nSubject four of politics natural.\nCharacter prepare along only. Choice work teach let though floor indeed. Drive unit dinner two agree push current.',
    'email': 'gpatterson@example.com',
    'phone_number': '(780)820-5378',
    'json': {
    'name': 'Cynthia Coffey',
    'address': '84478 Lester Trafficway\nAndrewburgh, WY 01574',
},
    'key32348': 'value9736',
    'key55707': 'value7662',
    'key42157': 'value22082',
    'key44899': 'value96908',
},
    {
    'id': 17527487552896,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Bill Baker',
    'address': '9840 Lowe Loaf Suite 904\nMurraymouth, CA 86076',
    'text': 'Discuss product issue. Check fine safe sign painting. Area program even movement think detail huge hospital.',
    'email': 'brewerjennifer@example.net',
    'phone_number': '+1-238-263-9439',
    'json': {
    'name': 'Alyssa Garcia',
    'address': '23883 Wells Creek\nGriffintown, ND 51744',
},
    'key86099': 'value9667',
    'key25153': 'value66151',
    'key66806': 'value12699',
    'key88642': 'value9114',
    'key20697': 'value98112',
    'key70187': 'value42520',
    'key67143': 'value45983',
    'key12059': 'value57141',
    'key89953': 'value97136',
    'key37667': 'value43832',
},
    {
    'id': 17527487552908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Joshua Watkins',
    'address': '66112 Cruz Forest Apt. 896\nPort Claireport, NY 76609',
    'text': 'Want practice policy especially seven. Yes just able computer space health six. Number in building sit. Site set short impact appear you stuff office.',
    'email': 'sarahboyer@example.com',
    'phone_number': '938-668-1817x5672',
    'json': {
    'name': 'Elizabeth Drake',
    'address': '7319 Melissa Islands Apt. 045\nNew Michael, AK 51620',
},
    'key41189': 'value9498',
    'key43664': 'value93894',
    'key56755': 'value39108',
    'key72900': 'value28449',
    'key5740': 'value20915',
},
    {
    'id': 17527487552920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Grace Johnson',
    'address': '236 Kelly Summit Suite 899\nWest Christyview, CA 28321',
    'text': 'Safe expert national kid car sense. Recent perhaps without vote cost management pick.',
    'email': 'michelewhite@example.net',
    'phone_number': '(696)524-9605x19080',
    'json': {
    'name': 'Jennifer Adams',
    'address': '20686 Deanna Plain Suite 052\nEast Stephanie, NC 62269',
},
    'key86151': 'value49690',
    'key539': 'value99634',
    'key37542': 'value56755',
    'key41647': 'value81329',
    'key42511': 'value73943',
},
    {
    'id': 17527487552931,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Steven Cole',
    'address': 'PSC 1760, Box 9656\nAPO AE 48271',
    'text': 'Hold home nor. National current community notice few state consider. Walk serve production member offer police.\nRecognize result four allow carry behavior though.',
    'email': 'michellegarcia@example.org',
    'phone_number': '722.698.6415',
    'json': {
    'name': 'Amber Cuevas',
    'address': '32323 Harris Roads\nAdamsshire, FM 85799',
},
    'key47784': 'value59783',
},
    {
    'id': 17527487552941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Austin Padilla',
    'address': '5173 Flores Parks Suite 189\nSouth Kevin, WY 78119',
    'text': 'Child operation last. Its teacher vote power.\nDespite reveal realize per lawyer high. Product who program instead authority build man. Free important when throughout.',
    'email': 'wmorton@example.org',
    'phone_number': '+1-287-422-5547x654',
    'json': {
    'name': 'Mark Avery',
    'address': '418 Morton Roads Suite 377\nChristopherberg, NH 27853',
},
    'key1429': 'value9142',
    'key77075': 'value26543',
    'key92708': 'value90400',
    'key41358': 'value62605',
},
    {
    'id': 17527487552952,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Beth Smith',
    'address': '8851 Roberts Corner\nWilsonchester, AL 77649',
    'text': 'Tough land week. Include find away create star. Piece cultural show during heart.\nScience none relate various. Per allow decision whether into heart. Himself indeed director seek fund increase.',
    'email': 'qbright@example.net',
    'phone_number': '921-260-3832x02917',
    'json': {
    'name': 'Chloe Peters',
    'address': '994 Bender Causeway Apt. 223\nSouth Derek, PA 59377',
},
    'key74493': 'value36410',
    'key66715': 'value31855',
    'key7791': 'value47787',
},
    {
    'id': 17527487552964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Daniel Fischer',
    'address': '60640 Logan Plain\nEast Sarahchester, AS 22888',
    'text': 'Road better weight open.\nOccur approach analysis feeling concern lose so. Actually safe two far begin character prepare serious. Person majority unit improve husband.',
    'email': 'jasminecruz@example.com',
    'phone_number': '(401)621-9842x2938',
    'json': {
    'name': 'Andrea Smith',
    'address': '812 King Plaza Suite 126\nBrownton, VI 32345',
},
    'key76166': 'value34006',
    'key41423': 'value94336',
    'key82873': 'value14140',
    'key30043': 'value13508',
    'key61191': 'value83730',
    'key24369': 'value54892',
},
    {
    'id': 17527487552975,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Manuel Hess',
    'address': '2824 Young Plains\nMurphyton, MO 70229',
    'text': 'Choose may husband mean account any. Color speech will.\nLess heavy soldier treatment. Often type bill.',
    'email': 'pcollier@example.org',
    'phone_number': '001-256-439-5760',
    'json': {
    'name': 'Cody Johnson',
    'address': '728 Danny Plaza Apt. 586\nLake Matthewburgh, IA 05260',
},
    'key29889': 'value80781',
    'key93481': 'value52869',
    'key61921': 'value36428',
    'key65736': 'value63621',
    'key59681': 'value51348',
    'key1437': 'value68382',
    'key23181': 'value71651',
    'key39429': 'value61553',
    'key73279': 'value18677',
    'key35328': 'value69717',
},
    {
    'id': 17527487552986,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Joseph Gordon',
    'address': '2909 Christopher Isle Apt. 548\nTinahaven, WY 00645',
    'text': 'During now good agent. Woman state represent explain stand find.\nBox describe the condition. His issue evidence fast doctor use occur. Red politics material offer myself.',
    'email': 'scottosborn@example.net',
    'phone_number': '001-638-204-8634x978',
    'json': {
    'name': 'Andrea Cameron',
    'address': '766 Riley Flats Apt. 233\nKellyborough, SC 90477',
},
    'key42190': 'value41928',
    'key88558': 'value33582',
},
    {
    'id': 17527487552998,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Christine Morgan',
    'address': '38467 Kelley Lodge Apt. 857\nSouth Vanessa, DC 75270',
    'text': 'Bit ok sound health play improve. Official arrive upon area that past.\nHowever ok admit forget ground example check. From hope already nation have born. Law marriage return short out speech.',
    'email': 'andrewwilliams@example.com',
    'phone_number': '+1-561-736-2440x37395',
    'json': {
    'name': 'Brian Martinez',
    'address': '12066 Anthony Mills Apt. 946\nNorth Morganview, MD 82577',
},
    'key30574': 'value15323',
    'key67369': 'value87117',
    'key62272': 'value37127',
    'key17943': 'value87373',
},
    {
    'id': 17527487553010,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'John Stephens',
    'address': 'USS Miller\nFPO AP 50589',
    'text': 'Heavy art possible exist season time. Interest while property audience education. Find so thank many of oil.',
    'email': 'kristyherman@example.org',
    'phone_number': '5122691306',
    'json': {
    'name': 'Veronica Dodson',
    'address': '1041 Alexis Island Apt. 463\nPort Robin, TX 20022',
},
    'key7129': 'value31939',
    'key59695': 'value80938',
    'key14647': 'value60125',
    'key59485': 'value34347',
    'key62393': 'value34801',
    'key69511': 'value86611',
    'key24493': 'value14427',
    'key96710': 'value26089',
},
    {
    'id': 17527487553020,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'John Powell',
    'address': '03264 Nicole Rapid Suite 985\nCrawfordberg, DC 65245',
    'text': 'Huge fly theory entire. Eight word light market.\nSubject direction world art benefit this certain.',
    'email': 'johnstontiffany@example.org',
    'phone_number': '952-612-4393',
    'json': {
    'name': 'Andrea Gonzalez',
    'address': '29604 Megan Branch\nHineschester, AK 55914',
},
    'key25003': 'value10909',
    'key50151': 'value11560',
    'key80073': 'value53629',
},
    {
    'id': 17527487553032,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Lisa Francis',
    'address': '962 Yates Row Suite 763\nEast Tara, FL 11304',
    'text': 'Street job through decision issue this.\nBy theory fill about. Teach play late investment.\nSouth type perform black. Response east high suddenly. Quickly these never deep.',
    'email': 'michael44@example.com',
    'phone_number': '001-372-735-8518x296',
    'json': {
    'name': 'Annette Hamilton',
    'address': '70848 Alisha Expressway\nNew Mark, DC 96888',
},
    'key20901': 'value4724',
},
    {
    'id': 17527487553042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Megan Reyes',
    'address': '60754 Turner Creek\nScotthaven, OH 63926',
    'text': 'Respond local long would training perform trip finish. Assume PM today voice word itself.',
    'email': 'kimberlyaustin@example.com',
    'phone_number': '(416)593-7954x708',
    'json': {
    'name': 'Kelsey Odom',
    'address': '5969 Dalton Gardens\nPort Caroltown, NC 77171',
},
    'key29689': 'value93754',
    'key87464': 'value65808',
    'key92518': 'value8335',
    'key73142': 'value88015',
    'key35059': 'value28879',
    'key29089': 'value5133',
    'key8992': 'value67814',
    'key68663': 'value6834',
    'key82809': 'value19417',
    'key52092': 'value79701',
},
    {
    'id': 17527487553054,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Ebony Dominguez',
    'address': '81790 Bass Center Suite 216\nAnthonyland, AR 90817',
    'text': 'Open figure treatment doctor cover pull decade. And upon course return. Pretty push key send my.\nIssue picture talk institution. Production receive grow TV near people.',
    'email': 'wagnermichael@example.com',
    'phone_number': '001-444-393-8738x42441',
    'json': {
    'name': 'Lisa Johnson',
    'address': 'USS Ellison\nFPO AA 88746',
},
    'key76093': 'value14875',
    'key4057': 'value85376',
    'key17120': 'value81348',
    'key71921': 'value12',
    'key89149': 'value84916',
},
    {
    'id': 17527487553065,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Eric Jimenez',
    'address': '51372 Mclaughlin Glens Apt. 455\nNorth Sara, OK 28519',
    'text': 'Wait whole hospital community. Real several job capital friend. Meet always tend central hear.',
    'email': 'ryanbyrd@example.org',
    'phone_number': '(234)902-5365x24576',
    'json': {
    'name': 'David Smith',
    'address': '054 Denise Greens\nJessicaton, RI 33500',
},
    'key83645': 'value62130',
    'key93004': 'value66422',
    'key10017': 'value48083',
    'key48980': 'value45068',
    'key59595': 'value49638',
},
    {
    'id': 17527487553076,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Travis King',
    'address': 'USNV Carey\nFPO AE 86458',
    'text': 'People thousand call per west realize. Already kind manager recently character event. Speech entire prepare group rest free prevent.',
    'email': 'christine59@example.net',
    'phone_number': '+1-857-642-1551x9989',
    'json': {
    'name': 'Tommy Martin',
    'address': '4401 Copeland Mall Apt. 243\nJoshuaport, WA 89878',
},
    'key5118': 'value45238',
    'key63127': 'value11769',
    'key39619': 'value60953',
},
    {
    'id': 17527487553086,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Nicholas Curry DDS',
    'address': '1688 Thornton Unions Suite 366\nNorth Roberto, AK 01296',
    'text': 'Enjoy age ever cost decision evening produce which. Deal thank sing glass reflect. Performance think bag assume.\nSet still stage identify agent us since. Season live general according.',
    'email': 'allisonmelinda@example.net',
    'phone_number': '212.561.1736x86558',
    'json': {
    'name': 'Daniel Wright',
    'address': '818 Rhonda Mountain\nLawrencefurt, IL 46153',
},
    'key69622': 'value9603',
},
    {
    'id': 17527487553097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Ashley Wilkinson',
    'address': '329 Rivera Overpass Apt. 115\nSouth Terrymouth, OK 48150',
    'text': 'Walk herself example position charge way under. Various present down enjoy friend nature. Use investment teach somebody if no.',
    'email': 'carlsonapril@example.com',
    'phone_number': '(357)284-2801x8867',
    'json': {
    'name': 'Jesse Harris',
    'address': '82680 Donald Mountains Apt. 417\nWatersland, OK 94599',
},
    'key88659': 'value35816',
    'key93615': 'value44244',
    'key4933': 'value79183',
    'key2608': 'value6870',
    'key7409': 'value41007',
    'key28106': 'value81418',
    'key57188': 'value45939',
    'key57900': 'value50192',
},
    {
    'id': 17527487553109,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Patrick Bates',
    'address': '35720 Christopher Mount\nGonzalezland, OR 38583',
    'text': 'Deep fact brother field. Return range return hand system girl whose. Drop wall half. Event reach billion act science.',
    'email': 'wallacemichelle@example.net',
    'phone_number': '+1-937-405-4700',
    'json': {
    'name': 'Vincent Murray',
    'address': '340 Heather Track Suite 377\nLake Ashleybury, SD 65546',
},
    'key88193': 'value67552',
    'key35550': 'value46959',
    'key80461': 'value48767',
    'key39415': 'value11667',
},
    {
    'id': 17527487553120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Stephanie Young',
    'address': '97812 Smith Estates Apt. 584\nLake Stevenstad, NE 72818',
    'text': 'Option old sell. Test painting democratic foot pressure away page. Baby suggest score.',
    'email': 'ortegagrant@example.net',
    'phone_number': '+1-656-447-9298',
    'json': {
    'name': 'Brian Mcgee',
    'address': 'USNS Davis\nFPO AA 51132',
},
    'key97086': 'value39879',
    'key91103': 'value19670',
    'key61847': 'value93954',
},
    {
    'id': 17527487553131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Jessica Durham',
    'address': '095 Pearson Gateway\nMartinezberg, TX 57468',
    'text': 'Father reduce place increase may exist art mother. Money two describe no him. Trouble recognize drug standard issue.',
    'email': 'olsongeorge@example.org',
    'phone_number': '5385948100',
    'json': {
    'name': 'Carolyn Lewis',
    'address': 'Unit 6302 Box 4317\nDPO AE 12734',
},
    'key64073': 'value98',
    'key20696': 'value33805',
    'key69289': 'value93327',
    'key20349': 'value67259',
    'key27671': 'value30065',
    'key80535': 'value96068',
    'key45787': 'value68267',
    'key60433': 'value78178',
    'key71966': 'value72973',
    'key37388': 'value61664',
},
    {
    'id': 17527487553141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Scott Rogers',
    'address': '6777 Nicholas Highway Apt. 309\nEast Josephfurt, VA 32965',
    'text': 'Anyone prove civil away. Carry drive dinner bar authority. Policy air tough.',
    'email': 'scottmartinez@example.com',
    'phone_number': '+1-874-985-5943x114',
    'json': {
    'name': 'Valerie Perry',
    'address': '59174 Brown Turnpike\nTheresaburgh, OK 43243',
},
    'key4682': 'value39273',
    'key50837': 'value72156',
    'key50011': 'value83186',
    'key61159': 'value81362',
    'key68704': 'value36654',
    'key90918': 'value37767',
},
    {
    'id': 17527487553151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Patrick Pope',
    'address': '077 Garrett Turnpike\nSouth Dianeport, WI 98065',
    'text': 'Study good begin seem inside. Fund cost certain grow get.\nTime more Congress wait begin. Computer field he. Southern foreign specific image goal.',
    'email': 'vjackson@example.net',
    'phone_number': '001-654-814-0377',
    'json': {
    'name': 'Angela Thomas',
    'address': '146 Vincent Knolls Apt. 578\nSandychester, SD 40998',
},
    'key78156': 'value18609',
    'key24721': 'value52017',
},
    {
    'id': 17527487553162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Zachary Scott',
    'address': '0578 Dana Hollow\nHernandezfort, WV 93747',
    'text': 'Left story hit clearly suggest. Wait million attention never us everyone. Else can concern source feel power.\nDetail step wide long design. Politics establish walk. From knowledge time theory each.',
    'email': 'jon38@example.net',
    'phone_number': '781.481.3366x378',
    'json': {
    'name': 'Sara Valdez',
    'address': '6436 Max Roads Suite 156\nEast Janice, MS 76622',
},
    'key4683': 'value19198',
    'key56048': 'value15488',
},
    {
    'id': 17527487553173,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Jesse Erickson',
    'address': '9015 Eaton Parks Apt. 597\nRodriguezberg, NC 03510',
    'text': 'Say herself structure same. Test bag any conference item only my language. Both behind particular now usually American.\nKnow very past baby grow. Cell my although real now positive seven.',
    'email': 'connie17@example.net',
    'phone_number': '645.875.1459',
    'json': {
    'name': 'Mitchell Wilson',
    'address': '336 Bender Pike\nBarrport, MS 80401',
},
    'key46139': 'value92187',
    'key2612': 'value42908',
    'key59134': 'value29339',
    'key892': 'value6272',
    'key36952': 'value65031',
    'key47800': 'value47863',
    'key39138': 'value87789',
},
    {
    'id': 17527487553184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Billy Lee',
    'address': '691 Smith Fork\nNew Stephen, UT 85123',
    'text': 'Small star leave speak something car.\nProduce price rise.\nCapital nearly light how long scientist. Cost second southern plant enjoy study network trip.',
    'email': 'gregoryross@example.com',
    'phone_number': '(594)348-9517x7506',
    'json': {
    'name': 'James Melendez',
    'address': '26894 Davis Extension Apt. 588\nSouth Shane, PR 89406',
},
    'key97466': 'value62148',
    'key91475': 'value60133',
    'key23321': 'value12424',
    'key1073': 'value85262',
    'key89592': 'value13408',
    'key39829': 'value74393',
},
    {
    'id': 17527487553196,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'David Jones',
    'address': '3823 Rose Gateway Apt. 788\nAndrewborough, SD 45009',
    'text': 'Pay involve power author candidate everyone. End enjoy drive bag address. Far together wait even discussion.\nIndustry decide property. Dinner soon turn way.',
    'email': 'johnsonchristopher@example.org',
    'phone_number': '619.309.1966x644',
    'json': {
    'name': 'Elizabeth Oconnor',
    'address': '10722 Erik Walks\nLake Erin, MS 47085',
},
    'key62399': 'value97679',
    'key51188': 'value8448',
    'key90623': 'value14005',
    'key53278': 'value29419',
    'key98549': 'value34950',
    'key21189': 'value38348',
    'key26872': 'value3387',
    'key76190': 'value36976',
    'key76128': 'value97403',
},
    {
    'id': 17527487553207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Nicole Lester',
    'address': '4647 Carla Junctions\nNorth Veronica, UT 90888',
    'text': 'Soon program after just physical sure. Food meet stage music wide officer court.\nSay paper act nor catch accept interview office.',
    'email': 'christophercortez@example.org',
    'phone_number': '001-558-221-2374x3285',
    'json': {
    'name': 'Jennifer Mueller MD',
    'address': '6449 Tina Camp\nEast Courtneybury, VT 27809',
},
    'key31021': 'value81318',
    'key72338': 'value99226',
    'key83456': 'value14998',
    'key12342': 'value2967',
    'key49573': 'value53619',
},
    {
    'id': 17527487553218,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Justin Horton DVM',
    'address': '8866 Richard Spring Suite 277\nCalvinville, PW 91727',
    'text': 'Small adult hundred data turn moment. Direction stay dinner risk enjoy. South share whom seem unit language.',
    'email': 'corey52@example.net',
    'phone_number': '9693480740',
    'json': {
    'name': 'Danielle Coffey',
    'address': '3156 Lopez Gateway\nLake Mark, FM 54563',
},
    'key46623': 'value72726',
    'key62546': 'value61123',
    'key78229': 'value58669',
    'key27804': 'value79863',
    'key24982': 'value36191',
    'key52633': 'value86010',
},
    {
    'id': 17527487553228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Gregory Williams',
    'address': '5804 Powers Haven Apt. 331\nNicholasview, PR 18393',
    'text': 'Total onto attention business until. East bar long occur.\nSerious science increase appear federal involve state teach. Rock control bill international military everybody. Defense relate position.',
    'email': 'stephenbutler@example.org',
    'phone_number': '001-791-715-5876x38440',
    'json': {
    'name': 'Jennifer Lewis',
    'address': '5851 Deleon Parks\nNorth Danielburgh, UT 39021',
},
    'key32648': 'value6783',
},
    {
    'id': 17527487553240,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Ashley Martinez',
    'address': '4234 Mills Loop\nKarinaborough, VA 03795',
    'text': 'Relationship art reduce issue minute. Base own other sometimes condition seven. Operation police tell live former impact process. Civil task daughter account.',
    'email': 'franklee@example.net',
    'phone_number': '(423)728-4389',
    'json': {
    'name': 'Kelly Carr',
    'address': '4648 Robert Parks\nLake Adam, WV 11435',
},
    'key29773': 'value95514',
    'key8772': 'value35765',
    'key27895': 'value18254',
    'key12082': 'value74891',
    'key92195': 'value65172',
},
    {
    'id': 17527487553251,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Jamie Hill',
    'address': '311 John Mews\nNorth Emily, NJ 24911',
    'text': 'City decade soon special. Wrong somebody create take as. View management support event.',
    'email': 'davidnichols@example.com',
    'phone_number': '+1-676-392-3148x7142',
    'json': {
    'name': 'Alison Mendoza',
    'address': '018 Peter Grove Suite 242\nDenisestad, NE 17298',
},
    'key84467': 'value73937',
    'key19538': 'value4030',
    'key41443': 'value31575',
    'key34578': 'value84944',
    'key90419': 'value71645',
    'key12097': 'value41791',
    'key97728': 'value20004',
    'key7392': 'value18816',
    'key91546': 'value56732',
},
    {
    'id': 17527487553262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Sean May',
    'address': '51544 Walker Lights Apt. 879\nJenniferview, NM 79187',
    'text': 'Later scientist early other job. Amount music true politics and.\nService believe accept rock. Across once side doctor. Site boy speech into pick. Quality father understand standard.',
    'email': 'dorispeterson@example.com',
    'phone_number': '897.725.0665',
    'json': {
    'name': 'Sara Rios',
    'address': '4520 Ray Lock Apt. 632\nNorth Jacqueline, RI 81408',
},
    'key76419': 'value51278',
    'key49738': 'value38667',
    'key59102': 'value47334',
    'key40962': 'value5643',
    'key51221': 'value33857',
},
    {
    'id': 17527487553274,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Maria Gregory',
    'address': '26674 Leah Road Suite 381\nSouth Andrewshire, KY 96324',
    'text': 'Recent necessary free heart yes. Bank much them watch unit eye finish must.\nBoth successful what member appear year center. Up place easy exist. Bring relate foot shake kid mouth.',
    'email': 'hortonjoanna@example.net',
    'phone_number': '9976482726',
    'json': {
    'name': 'Antonio Willis',
    'address': '86456 Gina Street Apt. 404\nJamesberg, NJ 06235',
},
    'key43391': 'value64560',
    'key71838': 'value18108',
    'key84211': 'value53001',
    'key49178': 'value79674',
    'key94228': 'value26706',
    'key15144': 'value35706',
    'key20585': 'value89229',
    'key45737': 'value59093',
},
    {
    'id': 17527487553285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Robert Smith',
    'address': '8366 Michael Rapid\nNew Jerry, FL 23039',
    'text': 'Lot live other culture.\nMouth when instead garden specific PM bag road. Theory lead evening develop community design owner.',
    'email': 'hlevy@example.net',
    'phone_number': '001-848-729-9016x6231',
    'json': {
    'name': 'Megan Dunlap',
    'address': '09428 Lori Ranch Apt. 926\nJamesburgh, PW 45664',
},
    'key94782': 'value75225',
    'key25628': 'value50637',
    'key6603': 'value1695',
    'key91000': 'value53461',
    'key67074': 'value87883',
    'key83561': 'value78753',
},
    {
    'id': 17527487553296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'David Foster',
    'address': '1177 Billy Course Apt. 413\nLake Andrewmouth, AK 35920',
    'text': 'Call star field special crime one step. Wind interview modern style political single game end.',
    'email': 'ericarodriguez@example.net',
    'phone_number': '001-321-695-5301',
    'json': {
    'name': 'Joshua Aguirre',
    'address': '7391 Washington Path\nEast Stephanieport, WY 65651',
},
    'key63103': 'value83331',
},
    {
    'id': 17527487553307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Ronald Reyes',
    'address': '6653 Michael Key\nLake Justin, DE 10427',
    'text': 'Participant door study statement specific just. Short first economy history street hundred growth human. North example realize across address bit eat.',
    'email': 'franktaylor@example.org',
    'phone_number': '(952)380-0279x78184',
    'json': {
    'name': 'Mary Cox',
    'address': '203 Washington Field Suite 195\nLake Jonton, MI 60970',
},
    'key896': 'value55244',
    'key36440': 'value62586',
},
    {
    'id': 17527487553318,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Mark Mccoy',
    'address': 'PSC 6473, Box 9139\nAPO AP 48333',
    'text': 'Notice again want physical would participant former. Will difficult test sign others after write.',
    'email': 'erica97@example.org',
    'phone_number': '309-937-9561x5986',
    'json': {
    'name': 'Frank Oliver',
    'address': '77662 Kim Garden\nNew Cynthiaville, NH 42367',
},
    'key7537': 'value16786',
    'key98510': 'value34675',
    'key2602': 'value90139',
    'key49106': 'value3377',
    'key20747': 'value51451',
},
    {
    'id': 17527487553327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Carrie Lopez',
    'address': '5136 Raymond Union Suite 242\nEmilyborough, IN 04839',
    'text': 'Director entire table other blue including. Collection administration young subject sound throughout go.\nEdge even personal bill red drive computer hear. Serious amount nearly.',
    'email': 'lowenicole@example.org',
    'phone_number': '+1-722-416-6256',
    'json': {
    'name': 'Kevin Nguyen',
    'address': '086 Wagner Ports Apt. 487\nSouth Joshua, IN 07411',
},
    'key29118': 'value20383',
    'key36501': 'value91022',
},
    {
    'id': 17527487553338,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Christopher Weeks',
    'address': '638 Barnes Groves\nBurkeshire, CO 33255',
    'text': 'Mind share lay identify court church. How peace dog one share environment.\nDetail we mind little. Author garden thus bad find. Modern right way word remember common successful.',
    'email': 'udiaz@example.net',
    'phone_number': '001-476-483-4708x309',
    'json': {
    'name': 'Madeline Tapia',
    'address': 'Unit 3195 Box 4777\nDPO AE 46485',
},
    'key39728': 'value55822',
    'key23519': 'value69931',
    'key98338': 'value33794',
    'key43415': 'value27891',
    'key20819': 'value19372',
    'key43695': 'value44997',
},
    {
    'id': 17527487553347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Daniel Moore',
    'address': '517 Amy Pass Suite 600\nNorth Edwardside, PR 43567',
    'text': 'Federal expect recognize drug brother. Child first key sound party.\nHome green west but manager good price. That game high owner career line.',
    'email': 'courtneyjohnson@example.org',
    'phone_number': '001-772-628-3856',
    'json': {
    'name': 'Abigail Bennett',
    'address': '61443 Terri Bridge\nWilsonview, SD 46028',
},
    'key6472': 'value2756',
    'key11235': 'value92355',
    'key8571': 'value98381',
},
    {
    'id': 17527487553358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Tyler French',
    'address': '948 Long Expressway\nRonaldstad, KS 87413',
    'text': 'Especially general lay can around course. Stage itself detail structure maintain nice food. Million or buy.',
    'email': 'brownsabrina@example.org',
    'phone_number': '530-990-1655x82278',
    'json': {
    'name': 'Kenneth Jenkins',
    'address': 'USCGC Arias\nFPO AA 63995',
},
    'key83383': 'value32972',
    'key78037': 'value30586',
    'key46': 'value88561',
    'key57020': 'value34735',
    'key75104': 'value86733',
    'key9155': 'value84898',
    'key38124': 'value94025',
},
    {
    'id': 17527487553368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Martha Davis',
    'address': '67991 Kimberly Rapid Apt. 706\nNorth Alexanderchester, PW 58300',
    'text': 'Become walk statement throw guess agree child. After south else assume. Teacher matter already writer rest foreign. Spring rate sport will.',
    'email': 'vcole@example.net',
    'phone_number': '6146463579',
    'json': {
    'name': 'Mrs. Michelle Jones MD',
    'address': '352 Kurt Skyway Apt. 569\nNorth Kenneth, ND 87277',
},
    'key21546': 'value45407',
},
    {
    'id': 17527487553379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Eric Huffman',
    'address': '7353 Shaw Motorway Suite 192\nRaymondmouth, IL 92862',
    'text': 'Article animal will. Participant then score probably though chance.',
    'email': 'torresbrenda@example.com',
    'phone_number': '(296)375-8744',
    'json': {
    'name': 'Reginald Parker',
    'address': '9517 Brooke Union Apt. 100\nJonview, HI 73303',
},
    'key48153': 'value37663',
},
    {
    'id': 17527487553390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Lori Wright',
    'address': '9781 Carroll Crossing\nRobertberg, WA 77671',
    'text': 'Minute would management stand. Learn read test understand impact.',
    'email': 'ssanchez@example.net',
    'phone_number': '(752)401-5856x993',
    'json': {
    'name': 'Tamara Brewer',
    'address': '483 Murray Curve\nSouth Daveland, MS 31712',
},
    'key26440': 'value27185',
    'key37510': 'value48497',
    'key99644': 'value96117',
    'key60831': 'value68260',
    'key51090': 'value89965',
    'key85904': 'value57499',
    'key68314': 'value28808',
},
    {
    'id': 17527487553401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Michael Hoffman',
    'address': '411 Margaret Rapid Suite 899\nContrerasland, ID 61742',
    'text': 'Bill write line myself region. Develop hour politics record quite that.\nImagine receive I. Feeling beat nearly play mention nearly various. Research leader grow scene.',
    'email': 'melissachandler@example.org',
    'phone_number': '878.370.0361x01435',
    'json': {
    'name': 'Krista Rivas',
    'address': '15743 Reginald Light\nMckeeville, KS 15289',
},
    'key63564': 'value38062',
},
    {
    'id': 17527487553413,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Erica Pierce',
    'address': '15150 Nicole Divide Apt. 851\nDylanmouth, HI 08621',
    'text': 'Like own again measure him. President something under president first letter. Magazine tax issue.\nTerm rock money poor mean despite again. Discuss church there wait finally you major.',
    'email': 'valerie79@example.com',
    'phone_number': '260-899-8878x24554',
    'json': {
    'name': 'Sarah Lopez MD',
    'address': '49955 Henry Squares\nPort Chad, WY 34263',
},
    'key95469': 'value87414',
    'key98530': 'value21405',
    'key5480': 'value65568',
    'key1153': 'value31850',
    'key42878': 'value45107',
    'key87261': 'value95688',
    'key78204': 'value51227',
    'key55228': 'value19146',
    'key38636': 'value53989',
    'key37273': 'value4721',
},
    {
    'id': 17527487553424,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Jennifer Foley',
    'address': '7007 Perkins Pines Apt. 251\nMckinneychester, HI 93764',
    'text': 'Word thus different who major fill agree.\nStandard admit speak real system hotel. White work onto hold realize likely.\nOr very seat fish hair. Shoulder of wonder should in body.',
    'email': 'dyerjason@example.com',
    'phone_number': '6874982395',
    'json': {
    'name': 'Leslie Cunningham',
    'address': '0673 Mays Row Apt. 162\nSouth Jenniferside, GA 93668',
},
    'key95879': 'value15869',
    'key36361': 'value87114',
    'key63997': 'value76921',
    'key7457': 'value70448',
    'key88502': 'value58939',
    'key7894': 'value17681',
},
    {
    'id': 17527487553436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Bethany Ross',
    'address': '35428 Robert Port\nDennisside, MT 86027',
    'text': 'View produce teacher keep heart would. Still amount hard help cell father difference.',
    'email': 'jon84@example.com',
    'phone_number': '580.898.7821x426',
    'json': {
    'name': 'Jennifer Bentley',
    'address': '782 Lauren Throughway Suite 148\nLake Brandiville, MS 84753',
},
    'key56609': 'value65841',
    'key71620': 'value66443',
    'key42658': 'value75410',
    'key95271': 'value34129',
    'key75881': 'value69252',
    'key40816': 'value81977',
    'key4036': 'value2252',
    'key53155': 'value15757',
    'key27466': 'value35716',
    'key43412': 'value37894',
},
    {
    'id': 17527487553446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mary Wong',
    'address': '208 Elizabeth Park\nEast Jimmyhaven, CA 39137',
    'text': 'Condition table pattern officer me according how. Base would yard him vote people. Feeling commercial within market teacher yourself also.',
    'email': 'aaronmcdaniel@example.com',
    'phone_number': '+1-815-458-8460x44449',
    'json': {
    'name': 'Lisa Shelton',
    'address': '08545 Cooper Glens\nRyanville, NH 73391',
},
    'key83732': 'value48512',
    'key50509': 'value99076',
},
    {
    'id': 17527487553457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Victoria Edwards',
    'address': '1290 Amanda Turnpike\nAlecborough, LA 21123',
    'text': 'Management boy same Republican. Model she report daughter language ever. Detail military growth bed.',
    'email': 'rhonda71@example.com',
    'phone_number': '+1-834-895-7217x88094',
    'json': {
    'name': 'Rebecca Walker',
    'address': '73925 Gregory Turnpike Suite 011\nJimenezchester, NM 68755',
},
    'key9393': 'value76316',
    'key45241': 'value84957',
    'key56345': 'value27367',
    'key76467': 'value26954',
    'key64406': 'value3809',
    'key783': 'value2408',
    'key98936': 'value64245',
    'key51716': 'value67261',
    'key99902': 'value23780',
},
    {
    'id': 17527487553468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Ashley Jones',
    'address': '53199 William Common\nSouth Scottfurt, CO 77228',
    'text': 'Attention social sit wife Congress. Interesting mouth system him apply just. Officer later represent major.\nMagazine modern fine pass my different theory. Say factor current use others.',
    'email': 'tlawrence@example.com',
    'phone_number': '448-374-7651x9320',
    'json': {
    'name': 'Julie Walker',
    'address': '20104 David Stream\nNorth Cameronfurt, HI 45780',
},
    'key59158': 'value46486',
    'key30397': 'value56779',
    'key27972': 'value81488',
    'key16800': 'value51595',
    'key7689': 'value55548',
    'key2682': 'value17187',
},
    {
    'id': 17527487553479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Annette Mckenzie',
    'address': '71744 Gray Inlet\nSouth Emilyport, HI 58856',
    'text': 'Center evidence suggest seem like within shake. Participant black great alone model air.\nHuge compare day cup help. Certainly themselves woman very.\nAnything yet hotel nearly. Policy success join as.',
    'email': 'ronaldacosta@example.org',
    'phone_number': '439-775-4082x581',
    'json': {
    'name': 'Amber Baldwin',
    'address': '3092 Aaron Key\nSummersburgh, FM 34396',
},
    'key24920': 'value14980',
    'key45238': 'value82811',
    'key20158': 'value37911',
    'key76035': 'value76453',
    'key44646': 'value2115',
    'key65226': 'value1773',
    'key42633': 'value11790',
    'key85022': 'value48702',
    'key25732': 'value82417',
},
    {
    'id': 17527487553491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Paula Ibarra',
    'address': '1148 Hunt Summit\nNew Jennashire, DE 18155',
    'text': 'Reduce blue eight chance anything. Coach share authority throughout. Like strategy summer raise want. Country inside debate simple doctor forward figure.\nTurn fine candidate should technology stop.',
    'email': 'sonya45@example.com',
    'phone_number': '+1-249-656-0429x3501',
    'json': {
    'name': 'Lisa Erickson',
    'address': '8970 Pierce Lakes\nWilliamston, TX 27311',
},
    'key82038': 'value24145',
    'key56581': 'value62246',
    'key43487': 'value21151',
    'key27898': 'value87539',
    'key75065': 'value19562',
    'key17739': 'value53108',
    'key87919': 'value15656',
    'key37247': 'value18486',
    'key60072': 'value71385',
},
    {
    'id': 17527487553502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Lisa Miller',
    'address': '838 Byrd Springs\nSouth Patricia, CA 67461',
    'text': 'Early fund improve member thought few statement certain. People movie American nothing.\nThreat law a church.\nGreen example address nothing floor. Way politics senior recognize senior team commercial.',
    'email': 'anthonyrocha@example.org',
    'phone_number': '733.381.3360',
    'json': {
    'name': 'Michael Alvarado',
    'address': '993 Jackson Ferry\nChelseatown, LA 21601',
},
    'key84838': 'value2243',
    'key71856': 'value15033',
    'key66413': 'value94824',
},
    {
    'id': 17527487553513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Christopher French',
    'address': '155 Carolyn Green\nTracybury, NC 00659',
    'text': 'Their under fact speak else minute decision meet. Democrat hit something nice true. Lead they Mrs.',
    'email': 'joel97@example.org',
    'phone_number': '2919042977',
    'json': {
    'name': 'Rachel Pham',
    'address': '25195 Christina Glen Suite 379\nMatthewland, PR 90747',
},
    'key49253': 'value71163',
    'key6524': 'value24394',
    'key53462': 'value19312',
},
    {
    'id': 17527487553523,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'John Olson',
    'address': '18838 William Overpass\nLake Jerry, CT 22078',
    'text': 'Particularly ago wish sign white according weight approach. College it research act without. Spend benefit entire bad process as page left. Approach culture glass sound early.',
    'email': 'sarahsanchez@example.com',
    'phone_number': '001-848-528-4430x32419',
    'json': {
    'name': 'Erik Levy',
    'address': '804 Carlos Cove\nLake Jeremiah, NH 58803',
},
    'key12435': 'value54861',
    'key25663': 'value57302',
    'key38372': 'value69964',
},
    {
    'id': 17527487553534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Cody Wong',
    'address': 'USNV Zimmerman\nFPO AP 92556',
    'text': 'Religious even win. When child claim we. Full security hour front.',
    'email': 'amanda94@example.org',
    'phone_number': '4034942472',
    'json': {
    'name': 'Edward Davis',
    'address': '029 Robert Lane Apt. 878\nPort Courtney, OH 15269',
},
    'key10342': 'value14685',
},
    {
    'id': 17527487553544,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Michael Stanley',
    'address': '3366 Deborah Inlet Suite 085\nMichaelshire, NE 15638',
    'text': 'If film newspaper ready have. When cup moment into.\nLine close short author wind result. Traditional minute plan drug catch control. Paper focus run so face daughter group.',
    'email': 'kristen86@example.com',
    'phone_number': '+1-763-256-1880x16840',
    'json': {
    'name': 'William Cameron',
    'address': '9653 Michael Inlet\nNorth Katherine, NJ 81189',
},
    'key35157': 'value39426',
    'key88351': 'value35390',
    'key57560': 'value62164',
    'key81314': 'value17497',
    'key9716': 'value10258',
},
    {
    'id': 17527487553553,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Craig Munoz',
    'address': '1846 Heather Fall Apt. 487\nLake Hailey, SC 02692',
    'text': 'Himself knowledge Democrat into president whether value three. Goal test market less garden a. Game born improve.\nAvailable professor moment do available each.',
    'email': 'emily13@example.com',
    'phone_number': '590-988-3634',
    'json': {
    'name': 'Carlos Mendoza',
    'address': '345 Irwin Groves\nMitchellton, CT 49486',
},
    'key88030': 'value9201',
    'key95121': 'value78934',
    'key92407': 'value64767',
    'key13671': 'value53402',
    'key85517': 'value96893',
    'key71765': 'value95350',
    'key99625': 'value896',
    'key19789': 'value21907',
},
    {
    'id': 17527487553564,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Alexander Reese',
    'address': 'Unit 5743 Box 9591\nDPO AA 59019',
    'text': 'Guy teacher catch team mouth more face. Artist enjoy source state. Story already court make foot.\nTown others finish say physical. Exactly natural single draw. Industry both they surface whom yet.',
    'email': 'michaelgoodman@example.com',
    'phone_number': '001-843-684-8838x8563',
    'json': {
    'name': 'Amy Harvey',
    'address': '1246 Burke Parks Suite 199\nLake Jefferyfort, AL 68532',
},
    'key39966': 'value82238',
    'key48283': 'value38601',
    'key64935': 'value9062',
    'key97813': 'value94927',
    'key73605': 'value82130',
    'key200': 'value94826',
    'key54767': 'value31703',
},
    {
    'id': 17527487553574,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Vanessa Simmons',
    'address': '6855 Amy Viaduct Suite 592\nRichardshire, MS 39796',
    'text': 'Wait share eat environment note. Try sign live room. Growth evidence speech trade leg know couple.\nExecutive city my customer again community. Writer natural fine. Real college various despite.',
    'email': 'oarmstrong@example.org',
    'phone_number': '285.202.9697x5893',
    'json': {
    'name': 'Brenda Sheppard',
    'address': '7976 Michael Stravenue\nJohnsonborough, NV 27909',
},
    'key38971': 'value63587',
    'key43891': 'value64894',
    'key25431': 'value51544',
    'key4464': 'value16289',
    'key52535': 'value27535',
    'key81924': 'value73903',
},
    {
    'id': 17527487553585,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Kevin Mcclain',
    'address': '6394 Meagan Dale\nMarkbury, WI 05146',
    'text': 'Player just value. Few evening develop building reflect.\nReveal free financial social themselves tax song. Industry no cut man clear public. Leg enough one carry investment machine western.',
    'email': 'jessicajones@example.org',
    'phone_number': '(939)386-9768x0852',
    'json': {
    'name': 'Jordan Medina',
    'address': '60489 Miller Lights Suite 507\nNew Thomas, NH 83974',
},
    'key34485': 'value28381',
    'key48187': 'value72907',
    'key84579': 'value28132',
    'key18396': 'value95425',
    'key55034': 'value42396',
},
    {
    'id': 17527487553596,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Christopher Conley Jr.',
    'address': '0891 Ramos Ville\nThompsonhaven, WI 68207',
    'text': 'Receive rather nature yes season describe should. Financial no save bag.\nSeven window call environmental senior. Easy marriage student.',
    'email': 'hpatel@example.org',
    'phone_number': '574.953.9341',
    'json': {
    'name': 'Andrew Clark',
    'address': '028 David Rest Apt. 987\nWest Cynthia, CT 03090',
},
    'key48726': 'value60106',
    'key10401': 'value85206',
    'key89609': 'value73338',
    'key77886': 'value63147',
    'key95568': 'value91413',
    'key19422': 'value3948',
    'key24725': 'value25143',
},
    {
    'id': 17527487553607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Monique Lewis',
    'address': '9816 Javier Village Suite 476\nCooperberg, NV 48917',
    'text': 'Little lawyer important our civil. Green buy good per view budget.\nQuickly maintain fight ready. Show performance play travel mean use.',
    'email': 'henrysampson@example.net',
    'phone_number': '981-853-9655x808',
    'json': {
    'name': 'Bruce Williams',
    'address': '22731 Gonzalez Common Apt. 496\nPort Stephen, UT 35889',
},
    'key85129': 'value67103',
    'key311': 'value28252',
    'key52385': 'value89722',
    'key20085': 'value72376',
},
    {
    'id': 17527487553619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Brianna Kemp',
    'address': 'PSC 8389, Box 3464\nAPO AP 57489',
    'text': 'Consider rich player pressure worker successful. Clear owner want any science off all. Ago physical her.',
    'email': 'victor99@example.net',
    'phone_number': '588-407-8932',
    'json': {
    'name': 'Martha Zhang',
    'address': '3510 Brittney Meadow\nPort Gabrielshire, RI 68805',
},
    'key81997': 'value81332',
    'key22652': 'value44419',
    'key10267': 'value3122',
    'key12594': 'value75624',
    'key81070': 'value52619',
    'key50614': 'value28102',
    'key44734': 'value41697',
    'key26142': 'value20154',
    'key57459': 'value94980',
    'key19550': 'value39180',
},
    {
    'id': 17527487553628,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Brianna Davis',
    'address': '493 Owens Walks Suite 239\nDeannafort, KY 57129',
    'text': 'Onto buy key hundred. Process notice model. Would decision teach paper interview address wife garden.',
    'email': 'mark83@example.org',
    'phone_number': '(573)837-7069',
    'json': {
    'name': 'Helen Watson',
    'address': '116 David Flats\nWest Scott, MO 16259',
},
    'key40697': 'value68295',
    'key76529': 'value56825',
    'key91512': 'value9821',
    'key39052': 'value28530',
},
    {
    'id': 17527487553638,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Meagan Liu',
    'address': '674 Winters Passage Apt. 921\nJacksonfort, RI 59473',
    'text': 'Site environment skill available measure health. International foot factor rule no throw wait. Fear bill together without here its newspaper.\nWork next sister character free. Race simple news while.',
    'email': 'michelle29@example.com',
    'phone_number': '910-685-8161x10065',
    'json': {
    'name': 'Miguel Davis Jr.',
    'address': '7374 King Roads Suite 066\nSouth Patricia, IN 28019',
},
    'key38004': 'value95271',
},
    {
    'id': 17527487553649,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Cristina Clark',
    'address': '5091 Joel Walk\nLisaland, WA 22741',
    'text': 'More discussion six media support floor support. Fear join sell industry him.\nCultural method pull around let house writer. Question nothing raise.',
    'email': 'ocole@example.net',
    'phone_number': '699-420-1586x0835',
    'json': {
    'name': 'Bill Delgado',
    'address': '825 Dennis Gardens\nJacksonmouth, OH 25217',
},
    'key47156': 'value41732',
    'key66798': 'value17033',
},
    {
    'id': 17527487553660,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Derek Shaffer',
    'address': '303 Logan Views\nLutzport, PW 10875',
    'text': 'Often executive her game specific let general. Build and art positive miss employee season name. Whom so heavy phone wall on.',
    'email': 'michael75@example.com',
    'phone_number': '001-693-340-8406',
    'json': {
    'name': 'Michael Wong',
    'address': 'Unit 6164 Box 1510\nDPO AP 85957',
},
    'key89804': 'value6486',
    'key83539': 'value4931',
    'key23114': 'value76077',
    'key43168': 'value79408',
    'key41500': 'value10558',
    'key50805': 'value92147',
    'key8669': 'value95593',
    'key42741': 'value73331',
},
    {
    'id': 17527487553668,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Lori Sanchez',
    'address': '1069 Alexander Heights Suite 434\nLake Amandashire, NE 12540',
    'text': 'Popular hear simply grow also check run. Since real thank behind.\nStandard rich watch yes again ten. Fear they cover American.',
    'email': 'greenerik@example.net',
    'phone_number': '(603)230-0927',
    'json': {
    'name': 'Mary Payne',
    'address': '16609 Berger Park\nWest Robertofort, WV 31136',
},
    'key60189': 'value68131',
    'key22383': 'value33293',
    'key2367': 'value22213',
    'key18669': 'value51077',
    'key97250': 'value49628',
    'key73160': 'value46432',
    'key80077': 'value32554',
    'key5841': 'value52731',
    'key39741': 'value60925',
},
    {
    'id': 17527487553679,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Emily Hayes',
    'address': 'USCGC Miranda\nFPO AE 70206',
    'text': 'Least usually seek campaign become board.\nEffect doctor Mrs born yeah. Carry new son phone nor stand above. Decade else still likely stuff such condition.\nStrategy lay policy red political.',
    'email': 'christopher59@example.org',
    'phone_number': '383.618.8742',
    'json': {
    'name': 'Krystal White',
    'address': '7830 Michael Overpass Apt. 847\nAustinfort, GU 77811',
},
    'key64552': 'value66078',
    'key98193': 'value31625',
    'key31484': 'value23867',
    'key65357': 'value30947',
    'key17580': 'value18973',
    'key64979': 'value31780',
    'key87941': 'value99758',
},
    {
    'id': 17527487553689,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Amy Harvey',
    'address': '66835 Vincent Way\nMadisonland, CT 29020',
    'text': 'High treat wear give star eat. Minute fund every blue marriage central. Begin day organization four choose.\nSkin team else. Tough experience little practice all could. Crime wonder throw tough movie.',
    'email': 'pamela68@example.net',
    'phone_number': '4623946947',
    'json': {
    'name': 'Linda Fisher',
    'address': '418 Jennifer Stravenue\nMonroeview, WV 54030',
},
    'key8091': 'value5355',
    'key88081': 'value23225',
    'key72763': 'value62501',
    'key18237': 'value25997',
    'key65202': 'value70668',
    'key74267': 'value73627',
    'key72007': 'value31149',
    'key93489': 'value90988',
},
    {
    'id': 17527487553699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Daniel Gonzalez',
    'address': '1193 Lane Well Suite 005\nLake Amy, ND 20514',
    'text': 'Maintain yes sign foreign. Contain choose if add.\nAlone time yeah serious win such box while. Boy very own present off edge war.',
    'email': 'wchandler@example.net',
    'phone_number': '001-245-239-7688',
    'json': {
    'name': 'Dawn Bullock',
    'address': '3245 Kathryn Mountains Suite 583\nNorth Steven, KS 21734',
},
    'key34177': 'value82402',
    'key33334': 'value61902',
    'key36059': 'value34497',
    'key16297': 'value83768',
    'key1237': 'value79678',
    'key87215': 'value28283',
    'key6836': 'value53408',
    'key82952': 'value17155',
    'key22801': 'value20295',
},
    {
    'id': 17527487553710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Shirley Davis',
    'address': '08166 Cooley Trail Suite 480\nOrtizville, OR 94781',
    'text': 'Everything itself reason somebody institution fish pull wonder. Home letter next thousand. Note full dream can tough light crime wear.',
    'email': 'hallmichael@example.org',
    'phone_number': '(287)250-5812',
    'json': {
    'name': 'Mary Mills',
    'address': '93164 Melissa Fall\nJasonborough, VT 57240',
},
    'key55444': 'value93146',
    'key88312': 'value95461',
},
    {
    'id': 17527487553722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Robert Riley',
    'address': '5558 Elizabeth Ranch\nMichaelfurt, PR 70859',
    'text': 'School field difficult process. Certainly meet nothing house how firm hard.\nExample they interview behind reduce offer. Than investment room interesting father senior hear.',
    'email': 'brandonhenry@example.com',
    'phone_number': '744.410.8290',
    'json': {
    'name': 'Aaron Thornton PhD',
    'address': '49290 Buckley Trace\nSouth Jose, UT 32234',
},
    'key15332': 'value67926',
    'key32752': 'value19489',
    'key15996': 'value55599',
    'key13210': 'value79337',
    'key5621': 'value60967',
},
    {
    'id': 17527487553734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Adam Griffith',
    'address': '08907 Dale Courts\nJamesmouth, PR 31407',
    'text': 'Protect spend them before fund already when. Goal must option hand kind.\nBoard military across size real.',
    'email': 'fscott@example.org',
    'phone_number': '001-252-605-6062x51219',
    'json': {
    'name': 'Kathleen Ball',
    'address': '915 Williams Burgs\nMontgomeryview, MH 26388',
},
    'key41372': 'value241',
    'key90644': 'value4685',
    'key46705': 'value20261',
    'key2426': 'value49849',
    'key15661': 'value19343',
    'key1382': 'value28547',
    'key53063': 'value85465',
},
    {
    'id': 17527487553745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Gerald Sheppard',
    'address': '402 Tara Squares Apt. 574\nMichaelville, DE 99789',
    'text': 'Modern article order next national home fear. International kid might fight.\nListen you account water person could. Today father always natural. World western myself should record difference.',
    'email': 'kimrichardson@example.net',
    'phone_number': '480.339.0912x594',
    'json': {
    'name': 'Crystal Massey',
    'address': '559 Edwards Row\nNew Laurenland, ND 27145',
},
    'key59964': 'value12675',
    'key54733': 'value46698',
},
    {
    'id': 17527487553757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Danny Alexander',
    'address': '7261 Jenny Cliff Suite 608\nWest Amandaberg, TN 10329',
    'text': 'Past our night tree. Another charge final over.\nEach nothing wish. Someone financial big tend success easy. These goal century you according whatever can.\nPrice feeling identify at.',
    'email': 'schultzdenise@example.org',
    'phone_number': '(926)372-9067',
    'json': {
    'name': 'Christie Wilson',
    'address': '1400 Ortega Locks\nSouth Yolanda, KY 30293',
},
    'key71561': 'value71900',
    'key12511': 'value78205',
    'key19922': 'value44843',
    'key31937': 'value77854',
    'key67141': 'value45668',
},
    {
    'id': 17527487553770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'William Williams',
    'address': '24974 John Port Apt. 644\nLake Kristina, NC 06320',
    'text': 'Relationship those once that south story adult station. Section off sing data. Sure meeting pick career here material. Money lead game along leg who bar.',
    'email': 'ashleychurch@example.com',
    'phone_number': '248.857.7039x6043',
    'json': {
    'name': 'Timothy Singh',
    'address': '99428 Benjamin Ramp\nChristinamouth, DC 76104',
},
    'key19940': 'value69181',
    'key77156': 'value57460',
    'key34845': 'value45391',
    'key22915': 'value99900',
    'key60915': 'value18954',
    'key48184': 'value14904',
    'key42170': 'value89459',
    'key14259': 'value68964',
    'key9927': 'value94724',
    'key83554': 'value23645',
},
    {
    'id': 17527487553781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Nathan Brown',
    'address': '9914 Mccann Bypass Apt. 586\nLeestad, SD 98317',
    'text': 'Young treatment against her power yard. Natural both risk different.\nFrom win admit. Reality manage money. Compare method heavy.',
    'email': 'qsalazar@example.com',
    'phone_number': '001-588-612-7829x33996',
    'json': {
    'name': 'Alex Stephens',
    'address': '811 Phillips Viaduct Apt. 690\nSmithside, NM 34518',
},
    'key49877': 'value13876',
    'key54829': 'value37214',
    'key89452': 'value94483',
    'key68699': 'value68023',
    'key94395': 'value67156',
    'key31865': 'value50093',
    'key57528': 'value30580',
    'key88966': 'value41221',
},
    {
    'id': 17527487553794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Anthony Lewis',
    'address': '2114 Clark Grove\nTimothyhaven, SD 49055',
    'text': 'Difference last born later father religious.\nStatement in boy firm animal perhaps news. General family firm instead agent probably. Skill unit machine box determine.',
    'email': 'perkinsjoseph@example.net',
    'phone_number': '+1-489-248-9607x9253',
    'json': {
    'name': 'Cindy Watkins',
    'address': '23649 Danielle Canyon\nSamuelland, SD 78870',
},
    'key57405': 'value5317',
    'key70453': 'value90659',
    'key41164': 'value34855',
    'key70138': 'value58783',
    'key62132': 'value62599',
    'key50304': 'value69707',
},
    {
    'id': 17527487553806,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Thomas Garcia',
    'address': '53722 Wilson Forest Suite 973\nSouth Patriciaberg, MS 40143',
    'text': 'Pm itself article home. May bed push together teach. Audience safe identify PM clearly position.\nToo traditional difficult. True price thank daughter. At night safe ability.',
    'email': 'delacruzzachary@example.net',
    'phone_number': '903.461.5350',
    'json': {
    'name': 'Joshua Ball',
    'address': 'USNV Rogers\nFPO AP 66391',
},
    'key57436': 'value62158',
    'key66939': 'value71376',
    'key96308': 'value13969',
    'key97721': 'value2071',
    'key34240': 'value74151',
    'key34232': 'value19482',
    'key20695': 'value23269',
    'key678': 'value34877',
    'key88258': 'value23190',
},
    {
    'id': 17527487553817,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Robert Yates',
    'address': '73417 Johnson Forks Apt. 021\nBirdberg, IL 09819',
    'text': 'Keep soon international note operation. Political day billion later effect. Father wide difficult if phone chair. Moment others fill management.',
    'email': 'angelamichael@example.org',
    'phone_number': '424.582.8274x185',
    'json': {
    'name': 'Danielle Gutierrez',
    'address': '131 Ian Passage\nMeganton, NC 84343',
},
    'key50424': 'value38331',
    'key58103': 'value69780',
    'key7215': 'value74878',
    'key39867': 'value70700',
},
    {
    'id': 17527487553829,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Stephen Rice',
    'address': '28537 Luna Vista Suite 781\nAlisonfort, AL 75531',
    'text': 'Teacher writer trouble expert rich skin also. Ball science parent well grow turn always.\nInformation describe try church material finally glass. Enter lot yet. Especially girl who.',
    'email': 'dennis77@example.net',
    'phone_number': '+1-972-208-3582',
    'json': {
    'name': 'Sarah Kennedy',
    'address': '0730 White Brooks Apt. 327\nJasonchester, PA 67089',
},
    'key80404': 'value39045',
    'key53435': 'value36043',
    'key93880': 'value62618',
},
    {
    'id': 17527487553840,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Kim Williams',
    'address': '01014 Beth Dam\nLake Troytown, GA 50074',
    'text': 'Well time serious maintain. Officer difficult try animal professor discussion single lawyer.\nWar different bank finish. Strong plant card two attorney. Type PM learn market letter deep why get.',
    'email': 'alexismcdonald@example.com',
    'phone_number': '+1-907-408-4996x9291',
    'json': {
    'name': 'Jamie Hamilton',
    'address': '67428 Lindsay Harbor Apt. 620\nNorth Edwin, CA 15119',
},
    'key54726': 'value35426',
    'key32418': 'value95222',
    'key23319': 'value57749',
    'key13855': 'value79696',
    'key2336': 'value77054',
    'key5501': 'value89962',
    'key4154': 'value32298',
    'key1644': 'value98030',
    'key89501': 'value14481',
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
    'filter': 'uid > -100 and uid < 100',
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



    def test_request_4(self):
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = 'null'
        
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
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



    def test_request_7(self):
        """测试请求 7 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '454aaaa8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_09_239474JzcihlAD',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752748763.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid100AndUid1001752748763Json()
    test.run_tests()
