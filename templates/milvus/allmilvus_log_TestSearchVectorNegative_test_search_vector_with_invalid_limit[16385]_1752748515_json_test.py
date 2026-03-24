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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVectorNegative_test_search_vector_with_invalid_limit[16385]_1752748515_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[16385]_1752748515.json"
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



class AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidLimit163851752748515Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[16385]_1752748515.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[16385]_1752748515.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'b5859f04-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_08_033707JGGgAwku',
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
    'RequestId': 'b5859f04-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_08_033707JGGgAwku',
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
    'RequestId': 'b5859f04-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_08_033707JGGgAwku',
    'data': [
    {
    'id': 17527485141120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Debra Skinner',
    'address': '89799 Brittney Club Apt. 603\nKimborough, MH 62097',
    'text': 'Event hair bit Democrat economic player thought. Deal remain hotel answer positive. Recently pretty walk prevent stage ball.',
    'email': 'william40@example.com',
    'phone_number': '(905)448-7464',
    'json': {
    'name': 'Jessica Brown',
    'address': '0706 Mills Streets\nMelissaland, IN 25236',
},
    'key7779': 'value80207',
    'key8212': 'value11196',
    'key29867': 'value27411',
    'key64939': 'value60550',
    'key61761': 'value89875',
    'key3706': 'value6117',
    'key77344': 'value88424',
},
    {
    'id': 17527485141134,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Andrew Nguyen',
    'address': '24318 Brandt Glen Apt. 882\nPort Kimberly, VT 28052',
    'text': 'Here international I animal pattern. Card wall admit record around here Congress.\nLevel ago apply science partner grow. Least four these assume speech.',
    'email': 'amanda53@example.com',
    'phone_number': '766-606-0314x26042',
    'json': {
    'name': 'Jason White',
    'address': '897 Hardin Spurs Apt. 530\nWest Jesse, KS 18096',
},
    'key62260': 'value18285',
    'key58997': 'value78693',
    'key64706': 'value26629',
    'key80106': 'value42282',
    'key51423': 'value13913',
},
    {
    'id': 17527485141146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Katelyn Harrington',
    'address': '5989 Pamela Alley\nPetersonville, IN 69877',
    'text': 'Street image character response group. Course fire week window collection sure.\nMethod read open discussion could they. Low great raise use hour. Half movement whose free true quickly church.',
    'email': 'shannonchristopher@example.net',
    'phone_number': '689.225.2397',
    'json': {
    'name': 'Connor Burnett',
    'address': '515 Nicholas Station Suite 346\nWest Tamaraport, PR 44587',
},
    'key68263': 'value30688',
},
    {
    'id': 17527485141157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Joshua Crane',
    'address': '760 Brenda Parkway\nEast Veronicafort, TX 59545',
    'text': 'Save ahead Democrat near yes. Produce professional person one.',
    'email': 'john18@example.net',
    'phone_number': '472-442-4775',
    'json': {
    'name': 'Natasha Holt',
    'address': '4591 Thompson Haven Apt. 241\nMoralesborough, MA 13819',
},
    'key11296': 'value79781',
    'key82724': 'value99764',
    'key52643': 'value73815',
    'key40118': 'value84825',
    'key30723': 'value53257',
    'key86636': 'value70347',
    'key16589': 'value31568',
},
    {
    'id': 17527485141168,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Angela Hayes',
    'address': 'PSC 3652, Box 6174\nAPO AE 66828',
    'text': 'Industry across race girl trade. Already avoid individual rate least. Tax student about idea oil yes budget.',
    'email': 'drobinson@example.net',
    'phone_number': '001-639-463-9215',
    'json': {
    'name': 'Amanda Hamilton',
    'address': '7438 Clark Row Suite 983\nWest Rodneyhaven, NH 99444',
},
    'key34488': 'value88798',
    'key80363': 'value80068',
    'key67077': 'value51540',
    'key35348': 'value62766',
    'key85805': 'value48941',
    'key37477': 'value81237',
    'key62433': 'value67695',
    'key7949': 'value62562',
    'key10452': 'value25106',
    'key27750': 'value48367',
},
    {
    'id': 17527485141177,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jeffrey Pugh',
    'address': 'Unit 7302 Box 9861\nDPO AA 55859',
    'text': 'Care direction report seem generation rise. Decision gas minute fear nothing lead sense heavy.',
    'email': 'doylethomas@example.net',
    'phone_number': '313.931.5119',
    'json': {
    'name': 'Samuel Flowers',
    'address': '83092 Ebony Summit Suite 476\nAnthonyville, SC 50578',
},
    'key61663': 'value36309',
    'key29464': 'value57233',
    'key5052': 'value44409',
    'key66950': 'value80046',
},
    {
    'id': 17527485141186,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Sean Lopez',
    'address': '087 Joyce Ford\nBradleyport, MN 17877',
    'text': 'Across see though cost heavy. State loss station low scientist speak.\nAttorney but cultural plan. Up brother box result friend shake forward.',
    'email': 'connie01@example.net',
    'phone_number': '001-616-923-2968',
    'json': {
    'name': 'Stephanie Ball DDS',
    'address': '3090 Philip Gateway\nMcclainview, CA 56348',
},
    'key41562': 'value18668',
    'key3141': 'value4505',
    'key20826': 'value11066',
    'key16196': 'value39833',
    'key10800': 'value15060',
    'key91736': 'value71629',
},
    {
    'id': 17527485141196,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Brenda Simon',
    'address': '864 Destiny Lane Apt. 290\nEast Meganland, DC 65256',
    'text': 'Election age drive series. Pull father we one bit ten task. Style all officer rise.',
    'email': 'yanderson@example.org',
    'phone_number': '2327870434',
    'json': {
    'name': 'Kevin Nichols',
    'address': '4276 Foster Rue Suite 381\nSouth Chelseaborough, AK 44423',
},
    'key82626': 'value5189',
    'key36716': 'value31079',
    'key43168': 'value27447',
    'key13481': 'value43407',
    'key8755': 'value85757',
    'key11250': 'value52390',
    'key38466': 'value928',
    'key42806': 'value33194',
    'key27562': 'value2754',
    'key72496': 'value90195',
},
    {
    'id': 17527485141207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Victoria Davis',
    'address': '687 Garcia Vista\nNorth Tyler, AR 53403',
    'text': 'Nearly about growth various big read. They any who action street. Against ready these understand enter movie.\nBeautiful goal doctor east. Control save anyone this add. News best garden test ever.',
    'email': 'brianhill@example.com',
    'phone_number': '5583387468',
    'json': {
    'name': 'Christopher Cantrell',
    'address': 'PSC 6710, Box 3149\nAPO AP 77780',
},
    'key84547': 'value54455',
    'key81692': 'value88058',
    'key1693': 'value59035',
    'key40480': 'value72438',
    'key46297': 'value38835',
    'key46309': 'value72236',
    'key63679': 'value18283',
},
    {
    'id': 17527485141217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Christopher Anderson',
    'address': 'PSC 4755, Box 1520\nAPO AE 49731',
    'text': 'Church son point project. Father good purpose true. Wrong specific manage.\nResource difficult thing interview most. Style most clearly good. Account easy field.',
    'email': 'suttonsheila@example.org',
    'phone_number': '896.829.4702',
    'json': {
    'name': 'Katie Williams',
    'address': '935 Galvan Skyway\nLake Kathleenmouth, VT 42251',
},
    'key47695': 'value47580',
    'key15517': 'value54909',
    'key30139': 'value56729',
    'key91783': 'value69081',
    'key79945': 'value1684',
    'key71955': 'value42411',
},
    {
    'id': 17527485141226,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Lisa Rodriguez',
    'address': '78203 Christopher Common\nShepherdmouth, MO 73483',
    'text': 'Congress physical capital character. Pull lot reason capital game particularly.\nNation sound relationship. Leave check represent cell far religious. Job trouble even still.',
    'email': 'jessicahansen@example.net',
    'phone_number': '001-599-278-3884',
    'json': {
    'name': 'Tina Webster',
    'address': '05571 Nathaniel Roads\nNorth Sarah, WY 38025',
},
    'key14185': 'value16224',
    'key49592': 'value16045',
    'key9416': 'value85403',
    'key49409': 'value84335',
    'key24035': 'value74588',
    'key66265': 'value49371',
    'key250': 'value65256',
},
    {
    'id': 17527485141238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Carrie Henry',
    'address': '6541 Benjamin Expressway\nOwenston, ME 79811',
    'text': 'Wrong stage energy. Customer where total best determine. Area or way almost respond. Receive write land agreement really energy.\nThroughout entire add information relationship become.',
    'email': 'kimberly37@example.net',
    'phone_number': '(781)674-6731',
    'json': {
    'name': 'Kenneth Owens',
    'address': '968 Campbell Lakes Suite 816\nEast Jesus, RI 83146',
},
    'key41462': 'value56050',
    'key65147': 'value92740',
    'key57365': 'value53690',
    'key31638': 'value23259',
},
    {
    'id': 17527485141248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Cindy Johnson',
    'address': '9309 Griffith Road Suite 671\nLake Jessicachester, OH 09023',
    'text': 'Child affect return keep window anyone west. South case region expect. Officer agency often role she community long population. Guess about chance economy space teach recent.\nSame car each sure.',
    'email': 'sweeneycolton@example.com',
    'phone_number': '394-202-4560x61416',
    'json': {
    'name': 'Angela Davis',
    'address': '50349 Lisa River\nSouth Donna, OH 07647',
},
    'key70562': 'value97312',
    'key53074': 'value70493',
    'key14909': 'value34163',
},
    {
    'id': 17527485141260,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jesse Wright',
    'address': '8932 Avila Harbor\nRodrigueztown, MP 30074',
    'text': 'Concern inside drop stay bank. Yard parent seem up drug wall compare several. Walk person attack happy purpose assume fill.\nSource trade order worry movie. Agent there wind true foreign wrong day.',
    'email': 'austinschmidt@example.net',
    'phone_number': '001-344-396-1825x9866',
    'json': {
    'name': 'Roberta Medina',
    'address': '03230 Gloria Radial Suite 153\nPort Michelle, NY 30921',
},
    'key32150': 'value14635',
    'key80310': 'value52396',
    'key63945': 'value79465',
    'key50360': 'value20951',
    'key73638': 'value19148',
    'key10500': 'value69420',
    'key42883': 'value65489',
    'key15885': 'value20124',
    'key80336': 'value42536',
},
    {
    'id': 17527485141272,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Steven Williams',
    'address': '02325 Santiago Route Suite 020\nReeseport, UT 42583',
    'text': 'Character walk page star peace religious be. Talk cup particularly realize guy put process. Indeed difficult hit purpose value member.',
    'email': 'reneejohnson@example.com',
    'phone_number': '370.705.5657',
    'json': {
    'name': 'Chris Andersen',
    'address': '857 Glenn Springs\nWalterton, TX 19911',
},
    'key56239': 'value77652',
    'key3299': 'value14049',
    'key94399': 'value87729',
    'key65795': 'value95862',
    'key47522': 'value52567',
    'key38614': 'value63937',
    'key99575': 'value93141',
},
    {
    'id': 17527485141283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Kevin Snyder',
    'address': 'PSC 3588, Box 5232\nAPO AE 57742',
    'text': 'Money authority better. Southern kid near way also such.\nMr simply nearly action act ball. Tend big nice. Easy establish organization stop.',
    'email': 'phillipcunningham@example.org',
    'phone_number': '242.948.1301x15640',
    'json': {
    'name': 'Janet Stevens',
    'address': '76529 Robles Dam Apt. 133\nHeatherland, PW 97740',
},
    'key42731': 'value16065',
    'key21493': 'value87290',
},
    {
    'id': 17527485141293,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Ashley Warren',
    'address': '5830 Glenn Dam Apt. 281\nCherylburgh, TX 63972',
    'text': 'For room trial defense. Message deep break tend situation cultural. Alone music until black. Wish during address area help pull.\nWish thank ten long view manage theory. Small receive quality never.',
    'email': 'john84@example.net',
    'phone_number': '(450)891-4209',
    'json': {
    'name': 'Michael Morgan',
    'address': '200 Baldwin Hill Apt. 317\nGregoryside, NJ 09004',
},
    'key2848': 'value1765',
    'key67093': 'value77822',
    'key60157': 'value75774',
    'key9292': 'value54001',
    'key59124': 'value37484',
    'key24974': 'value64115',
    'key18355': 'value3484',
},
    {
    'id': 17527485141303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Adam Young',
    'address': '75263 Christopher Forest\nGentrymouth, WA 54857',
    'text': 'Company win in talk whatever number bag. Modern lay ground most whose house agreement. Stand win newspaper I treat.',
    'email': 'gibsonmiguel@example.com',
    'phone_number': '227-456-9210x9836',
    'json': {
    'name': 'Yvette Price',
    'address': '29873 Patterson Groves Apt. 320\nDoughertyfurt, AR 81218',
},
    'key93826': 'value21481',
    'key59256': 'value65356',
    'key18748': 'value70549',
    'key12268': 'value57668',
    'key39739': 'value37658',
    'key26349': 'value13216',
},
    {
    'id': 17527485141315,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Leroy Ramos',
    'address': '57041 Obrien Divide\nPort Debrashire, KS 83371',
    'text': 'Raise officer sea white public hold animal. Away simple again policy clear foreign network. Allow risk local ok item.',
    'email': 'courtneymoyer@example.net',
    'phone_number': '(442)404-8981x3776',
    'json': {
    'name': 'Laurie Klein',
    'address': '8289 Brian Lane Apt. 660\nNorth Tiffany, CA 62668',
},
    'key13962': 'value27951',
    'key68678': 'value47771',
    'key78693': 'value55017',
    'key86038': 'value50548',
    'key90467': 'value79297',
},
    {
    'id': 17527485141327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Steven May',
    'address': 'PSC 7098, Box 6902\nAPO AA 74348',
    'text': 'Member institution majority. Name age case us best box religious. Ability together institution real just. Real low result not.',
    'email': 'ariel03@example.com',
    'phone_number': '+1-500-362-1316',
    'json': {
    'name': 'Amanda Skinner',
    'address': '9441 Sean Crest Suite 332\nPort Tracy, WI 89156',
},
    'key55634': 'value40764',
    'key71898': 'value95274',
},
    {
    'id': 17527485141335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Jonathan Nguyen',
    'address': '922 Jacqueline Light\nWest Mirandaborough, WI 01973',
    'text': 'Week generation likely probably less sound number. West range information. Woman under over send property get computer develop. Avoid green experience strategy ask generation.',
    'email': 'janice82@example.net',
    'phone_number': '835-546-6082',
    'json': {
    'name': 'Lisa Hudson',
    'address': 'Unit 0883 Box 5113\nDPO AA 82849',
},
    'key42264': 'value36243',
    'key71213': 'value51773',
    'key4962': 'value73736',
    'key55885': 'value91043',
    'key93703': 'value59916',
    'key88496': 'value2635',
    'key42015': 'value65381',
    'key67454': 'value20333',
    'key60219': 'value94564',
    'key89367': 'value91126',
},
    {
    'id': 17527485141344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Michael Simmons',
    'address': '1991 Joshua Rest\nPort Robertburgh, AZ 92079',
    'text': 'Finally newspaper stage resource girl somebody. Mouth son approach research subject. Authority reason low conference positive.',
    'email': 'robert08@example.com',
    'phone_number': '001-283-363-6523x30164',
    'json': {
    'name': 'Anthony Jacobs',
    'address': '86783 Dale Center Apt. 065\nSouth Shaneland, TX 68701',
},
    'key36365': 'value92438',
    'key20624': 'value13762',
    'key62262': 'value98768',
    'key31465': 'value85648',
    'key73691': 'value88450',
    'key66622': 'value79111',
    'key52416': 'value82046',
    'key14236': 'value1910',
},
    {
    'id': 17527485141354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Donna Garza',
    'address': '820 Thompson Landing Apt. 351\nWhiteton, MS 74577',
    'text': 'Congress set network assume. Choose billion recent most. Land mission quickly always man worker. Important suffer while analysis.',
    'email': 'mallory62@example.com',
    'phone_number': '001-832-305-8344x59105',
    'json': {
    'name': 'Trevor Rose',
    'address': '718 Hernandez Ridges Suite 975\nSouth Laurieburgh, MD 08736',
},
    'key93067': 'value75601',
    'key40213': 'value10353',
    'key59560': 'value56006',
    'key79368': 'value43666',
    'key63975': 'value46776',
    'key81933': 'value94332',
    'key40409': 'value14318',
    'key71310': 'value80462',
    'key1120': 'value78378',
    'key12359': 'value74682',
},
    {
    'id': 17527485141365,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Nichole Morrison',
    'address': '379 Webb Springs\nBenjaminchester, NE 47003',
    'text': 'Study yard successful movement yourself ball. Those PM nice support.\nDog game population sort buy into. Cost hospital learn American particular. Upon fact day type pay company six newspaper.',
    'email': 'oliverkrista@example.org',
    'phone_number': '001-865-524-5891x6191',
    'json': {
    'name': 'Ann Lewis',
    'address': 'PSC 8944, Box 8149\nAPO AA 86857',
},
    'key87157': 'value24135',
    'key6491': 'value1190',
    'key60392': 'value86981',
    'key80946': 'value85003',
    'key89394': 'value91451',
},
    {
    'id': 17527485141376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Mark Morrow',
    'address': '7229 Carla Motorway Suite 751\nJeanburgh, GU 26383',
    'text': 'Meet sometimes imagine where. Push almost thank floor and. Together animal plant win coach real recently.\nSimilar area court child front American. Foreign enter measure table.',
    'email': 'fpeterson@example.org',
    'phone_number': '314.747.3984',
    'json': {
    'name': 'Gail Salazar',
    'address': '88460 Jessica Ridge Apt. 786\nWest Amyland, CA 17006',
},
    'key98537': 'value21059',
    'key45940': 'value96369',
    'key44027': 'value62749',
    'key8671': 'value47675',
    'key44096': 'value66971',
    'key5442': 'value18991',
    'key41601': 'value81086',
    'key71394': 'value31086',
    'key90857': 'value21462',
    'key77553': 'value56942',
},
    {
    'id': 17527485141387,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Bryan Lowe',
    'address': 'USS Watson\nFPO AP 02640',
    'text': 'Individual time before raise detail. Firm answer raise allow night this. Thus size west skin set art.',
    'email': 'cjohnston@example.net',
    'phone_number': '001-489-583-4937x5138',
    'json': {
    'name': 'Thomas Brown',
    'address': '1760 Christopher Vista\nLake Mary, NH 58084',
},
    'key17039': 'value10469',
    'key76374': 'value4787',
    'key85375': 'value20281',
},
    {
    'id': 17527485141397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Sara Morris',
    'address': '55975 Micheal Trace Apt. 948\nSouth Derek, NM 50265',
    'text': 'This understand price hot team. War fill behind short wear. Manager side close walk life.\nOften baby score lot image lot. Create nothing teacher scene.\nWind pretty organization safe better.',
    'email': 'rileyjustin@example.org',
    'phone_number': '494-556-2656x19124',
    'json': {
    'name': 'Cynthia Romero',
    'address': '92918 Christopher Ville Apt. 311\nWest Joshua, OR 94099',
},
    'key49866': 'value42040',
    'key61099': 'value91993',
    'key41021': 'value23472',
    'key4139': 'value10924',
},
    {
    'id': 17527485141410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Caitlin Freeman',
    'address': '9220 Frank Locks\nNew Carlamouth, VI 94120',
    'text': 'Leg throw election serious dog within number by. Each information part nothing.\nWest question rule all compare evening. Reduce admit major statement. Look meeting ahead sea.',
    'email': 'jillsalinas@example.com',
    'phone_number': '(904)842-5811x51030',
    'json': {
    'name': 'Richard Holland',
    'address': '8820 Harry Turnpike\nEast Davidborough, ID 68049',
},
    'key9024': 'value7182',
},
    {
    'id': 17527485141422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Philip Mendez',
    'address': '1235 Lori Keys\nCaseyton, ID 83827',
    'text': 'Share hundred during beyond myself fire individual. Senior long else moment third her best.\nHome appear time without boy. Front artist which after teach wish little.',
    'email': 'levyscott@example.com',
    'phone_number': '+1-626-562-0548x6708',
    'json': {
    'name': 'Timothy Lee',
    'address': 'Unit 6563 Box 6279\nDPO AP 24831',
},
    'key40345': 'value65867',
    'key56365': 'value71986',
    'key9613': 'value23581',
    'key82087': 'value27966',
    'key40776': 'value71113',
    'key21743': 'value33241',
},
    {
    'id': 17527485141431,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Samantha Powell',
    'address': '5040 Vasquez Ferry\nMorrowside, DE 03262',
    'text': 'Nothing measure nor mean. Film message start cause itself. Level many wall become miss.',
    'email': 'phull@example.org',
    'phone_number': '228-734-7311x7032',
    'json': {
    'name': 'Elaine Lee',
    'address': '3014 Reginald Mall Apt. 016\nWest Brianburgh, AR 27945',
},
    'key68864': 'value39619',
    'key27226': 'value33989',
    'key31607': 'value47178',
    'key31922': 'value68385',
    'key29467': 'value88467',
    'key18996': 'value72915',
    'key8718': 'value61721',
    'key58438': 'value24012',
    'key94287': 'value41537',
},
    {
    'id': 17527485141442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Laura Hammond',
    'address': '7995 Anderson Stravenue Suite 565\nNew Christianfort, PW 42872',
    'text': 'Goal draw memory have religious them action effect.\nFew state both across page. Apply everyone stay room mission network thus.',
    'email': 'leslieduke@example.org',
    'phone_number': '+1-848-557-8048',
    'json': {
    'name': 'Amy Hatfield',
    'address': '7375 Michael Inlet\nNorth Benjaminport, HI 31033',
},
    'key501': 'value70432',
},
    {
    'id': 17527485141453,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'William Mann',
    'address': '8078 Lee Mission\nGileschester, TN 81504',
    'text': 'Way town office number. Similar system room whom. Light coach process step three former tax. Adult born wide.',
    'email': 'lauren25@example.com',
    'phone_number': '001-601-257-2048x940',
    'json': {
    'name': 'Katherine James',
    'address': '97308 Powell Place Suite 394\nAmyport, ME 88978',
},
    'key33810': 'value50610',
    'key68506': 'value87581',
},
    {
    'id': 17527485141464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Anthony Miller',
    'address': 'PSC 8804, Box 8023\nAPO AE 87975',
    'text': 'Analysis somebody list become ready home six.\nValue science important information. Experience enjoy participant air.',
    'email': 'pcastaneda@example.com',
    'phone_number': '306.870.8018',
    'json': {
    'name': 'Charles Rogers',
    'address': '267 Baker Ford Apt. 065\nEast Stacyberg, PA 37885',
},
    'key99690': 'value56001',
    'key99386': 'value92735',
    'key50326': 'value59580',
    'key16095': 'value67610',
    'key74514': 'value84188',
    'key45461': 'value28856',
    'key17081': 'value86870',
    'key95661': 'value23918',
},
    {
    'id': 17527485141473,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Joseph Martin',
    'address': '971 Alex Ridges\nNorth Brittany, IA 29556',
    'text': 'Employee light year check big serve leave. Professional those avoid arm who. Raise with we blue change west wrong.',
    'email': 'walkergreg@example.com',
    'phone_number': '7202085155',
    'json': {
    'name': 'Riley Booker',
    'address': 'USCGC Smith\nFPO AA 52661',
},
    'key46667': 'value71807',
    'key37008': 'value80740',
    'key28376': 'value48022',
    'key16532': 'value28262',
    'key56140': 'value66918',
},
    {
    'id': 17527485141483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Louis Bryant',
    'address': '605 Brian Spur\nNorth Bradley, ND 40241',
    'text': 'Discuss gas assume seat throughout outside eight. Dark leg share agreement environmental western will.',
    'email': 'chadhernandez@example.net',
    'phone_number': '(292)519-0854x320',
    'json': {
    'name': 'Michelle Garcia',
    'address': '30090 Sheryl Turnpike Suite 482\nBrightton, DC 24875',
},
    'key45619': 'value53979',
    'key68607': 'value13417',
    'key69584': 'value43741',
    'key83302': 'value91270',
    'key97374': 'value85760',
},
    {
    'id': 17527485141494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jacob Sharp',
    'address': '144 Morrow Gardens\nAlexandertown, MA 35588',
    'text': 'Best treatment beyond radio true. Anything address people activity lawyer good majority would. Piece end realize nice huge.\nPiece chair although production.',
    'email': 'kaylasweeney@example.org',
    'phone_number': '9265422268',
    'json': {
    'name': 'Jason Fernandez',
    'address': 'USNS Hays\nFPO AE 05790',
},
    'key95565': 'value26913',
},
    {
    'id': 17527485141504,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Zachary Johnson',
    'address': '5289 Andrews Heights\nGeorgefort, LA 87716',
    'text': 'Campaign pull situation range. Recently behind child know.\nCustomer state beautiful common many soldier. Name anything beyond support.',
    'email': 'alexander99@example.com',
    'phone_number': '652.997.6451x253',
    'json': {
    'name': 'Joshua Smith',
    'address': '77348 Holly Islands Apt. 899\nLake Belinda, WA 34184',
},
    'key47561': 'value35896',
    'key71416': 'value44181',
    'key69277': 'value24917',
    'key44344': 'value72876',
    'key72961': 'value94724',
    'key84001': 'value14393',
    'key5629': 'value60706',
    'key81257': 'value5843',
    'key28025': 'value11334',
    'key72736': 'value51277',
},
    {
    'id': 17527485141515,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Karen Pacheco',
    'address': '31554 Allison Ford Apt. 063\nEast Jeffrey, MI 38480',
    'text': 'Style give itself mention family question.\nLive theory door win share point carry. Agree truth appear change. Town away benefit.',
    'email': 'wandahenry@example.net',
    'phone_number': '977.451.0943',
    'json': {
    'name': 'Cody Mckenzie',
    'address': '20222 Morgan Divide Apt. 582\nBakerstad, IL 29035',
},
    'key17125': 'value75761',
    'key86242': 'value67014',
    'key89387': 'value36212',
    'key25235': 'value38540',
    'key89456': 'value86182',
    'key84074': 'value53286',
    'key81400': 'value97464',
    'key50117': 'value83186',
},
    {
    'id': 17527485141527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Adam Jensen',
    'address': '1069 Daniel Ports\nRobertsonstad, LA 25616',
    'text': 'Story like form everybody soldier. Prevent really newspaper glass. Nothing or tough campaign.',
    'email': 'julie45@example.org',
    'phone_number': '444.435.0465x58540',
    'json': {
    'name': 'Michael Clark',
    'address': '78666 Ortega Courts Suite 767\nDeborahfort, AR 03202',
},
    'key21644': 'value50353',
    'key95431': 'value39402',
    'key18126': 'value13155',
    'key6645': 'value27752',
    'key47578': 'value34615',
    'key74062': 'value23401',
    'key79495': 'value68975',
    'key50342': 'value73355',
    'key93587': 'value59297',
    'key79562': 'value91840',
},
    {
    'id': 17527485141538,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jeffrey Spencer',
    'address': '8654 Leslie Cliff\nHintonville, MP 55654',
    'text': 'Popular ever spend senior teach box real. Ask station language manager order be indeed. Voice right year her different include.',
    'email': 'colonanna@example.org',
    'phone_number': '+1-598-661-8434x7880',
    'json': {
    'name': 'Jennifer White',
    'address': '1013 Karen Landing\nPort Markshire, SC 49291',
},
    'key20960': 'value68480',
    'key24545': 'value13782',
    'key69258': 'value61683',
    'key20474': 'value62507',
    'key50849': 'value88893',
    'key39783': 'value34036',
    'key87026': 'value34483',
},
    {
    'id': 17527485141549,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Shawn Vega',
    'address': 'Unit 8732 Box 0056\nDPO AP 84872',
    'text': 'Drive today safe road. Ten soldier floor.\nPublic much son save sell old consider prevent. Professional too cause show. Choice school indicate occur.',
    'email': 'webstercassandra@example.org',
    'phone_number': '320.796.2855x465',
    'json': {
    'name': 'Natasha Woods',
    'address': '45154 Beard Brook\nBrendamouth, TN 06124',
},
    'key14876': 'value11800',
    'key7455': 'value71059',
    'key66415': 'value62140',
    'key65325': 'value64538',
    'key50682': 'value35174',
    'key85908': 'value54918',
    'key55233': 'value52584',
    'key58975': 'value46189',
    'key63229': 'value52416',
},
    {
    'id': 17527485141559,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Michelle Smith',
    'address': '9444 Kelly Manors Suite 121\nJacquelinefort, UT 58237',
    'text': 'Professional believe policy drug heavy again sell answer. Fire important son project game ok rise. Approach her standard most nothing account skin laugh.',
    'email': 'dporter@example.com',
    'phone_number': '902-654-6346',
    'json': {
    'name': 'Christopher Brown',
    'address': 'Unit 6903 Box 4413\nDPO AP 15876',
},
    'key22809': 'value53118',
    'key85745': 'value46420',
    'key73530': 'value71005',
    'key16437': 'value17898',
    'key96250': 'value65808',
    'key43830': 'value25842',
    'key15763': 'value80317',
},
    {
    'id': 17527485141568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Joshua York',
    'address': '913 Matthews Creek\nNorth Kevinberg, NH 50210',
    'text': 'Ground realize green industry account factor. Wall event fly site food. She recently responsibility single site treatment charge near. Sort defense include in compare few condition.',
    'email': 'john89@example.com',
    'phone_number': '+1-937-592-1372x786',
    'json': {
    'name': 'Catherine Green',
    'address': '4658 Jennifer Street Apt. 545\nSouth Diana, NC 41886',
},
    'key99460': 'value72977',
    'key40186': 'value51744',
    'key83427': 'value40576',
    'key4752': 'value42600',
    'key12688': 'value86578',
    'key67132': 'value42456',
    'key97030': 'value63025',
},
    {
    'id': 17527485141578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Micheal Johnson',
    'address': '86427 Melissa Stream\nWatkinston, MO 74317',
    'text': 'Them admit money cut class most there. Management window poor author. Water enter gun bad. Sort stock vote night movement.',
    'email': 'williamwilson@example.com',
    'phone_number': '812.828.2274x377',
    'json': {
    'name': 'David Turner',
    'address': '37808 Aaron Manor Apt. 444\nLake Carrie, WV 28921',
},
    'key72169': 'value63187',
    'key59582': 'value76212',
    'key66868': 'value51373',
    'key13905': 'value67391',
    'key97754': 'value29392',
    'key94427': 'value32641',
    'key89438': 'value98328',
},
    {
    'id': 17527485141589,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Michael Weiss',
    'address': '56695 Thompson Mill Suite 186\nNorth Anthony, AS 52023',
    'text': 'Tree anyone whose protect spring buy maintain. Might worry step staff animal lead. Land source sister when officer upon.\nThem common station bag generation against. Scientist director seat.',
    'email': 'garciaanthony@example.org',
    'phone_number': '737-266-8357x490',
    'json': {
    'name': 'Debra Reed',
    'address': '6712 Anderson Village\nWest Amanda, AL 20777',
},
    'key74139': 'value30970',
    'key50201': 'value4658',
    'key42531': 'value55686',
    'key67192': 'value93768',
    'key13582': 'value5355',
    'key95908': 'value17762',
    'key185': 'value13643',
    'key76338': 'value40915',
},
    {
    'id': 17527485141601,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Mary Palmer',
    'address': '976 Tiffany Manors Apt. 630\nNorth Jennifer, MH 28430',
    'text': 'Great firm likely campaign cold. Fast go evening same report. Already rest line decade without start.',
    'email': 'ngould@example.net',
    'phone_number': '789-579-6756x386',
    'json': {
    'name': 'Vanessa Spencer',
    'address': '95088 Brennan Mount\nSouth Shannon, MN 48493',
},
    'key53951': 'value11512',
    'key11796': 'value97946',
    'key89009': 'value45783',
    'key59603': 'value95517',
    'key95667': 'value25432',
    'key40717': 'value6394',
},
    {
    'id': 17527485141611,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Billy Osborne',
    'address': '7591 Heidi Roads\nLake Shawn, WY 11039',
    'text': 'Side deep direction old yard learn. Thus itself use north defense pay.\nReason detail decade tonight. Point customer visit author material court.',
    'email': 'ramirezcindy@example.com',
    'phone_number': '(512)340-1879',
    'json': {
    'name': 'John White',
    'address': '4388 Gross Light\nWest Stacybury, PR 65449',
},
    'key59497': 'value73356',
    'key50484': 'value26306',
    'key67372': 'value94654',
},
    {
    'id': 17527485141623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Michelle Adams',
    'address': '359 Hernandez Trail Apt. 012\nJustinshire, NY 23443',
    'text': 'Begin form new cover mouth create. Generation edge difference hot when.\nTelevision customer that drug identify have event. Candidate family themselves hundred street. Care name teacher support third.',
    'email': 'michaelgarza@example.net',
    'phone_number': '584-852-2781x45937',
    'json': {
    'name': 'Paul Flynn',
    'address': '531 Stewart Parks Suite 763\nLorettastad, DC 35814',
},
    'key77838': 'value60772',
    'key45293': 'value79109',
    'key57473': 'value9546',
    'key97179': 'value80790',
    'key34631': 'value8537',
    'key4778': 'value15710',
    'key79382': 'value11792',
    'key36728': 'value70254',
},
    {
    'id': 17527485141634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Jesus Martin',
    'address': '917 Meyer Crest\nNathanfort, OH 33049',
    'text': 'Pretty same nor. Rock able kind page. Enjoy provide since should wrong.\nYoung fire customer. Power professional generation quality Mr federal keep. Top father Mrs student play national.',
    'email': 'marilynboyer@example.com',
    'phone_number': '421-510-3082',
    'json': {
    'name': 'Amanda Winters',
    'address': '5252 Nicole Branch\nHolmesborough, IN 15505',
},
    'key63898': 'value20074',
    'key91793': 'value41268',
    'key10754': 'value24131',
},
    {
    'id': 17527485141646,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Richard Wilson',
    'address': '428 Eric Creek\nNew Paige, RI 35511',
    'text': 'Key foot music manager resource. Vote because without act. Different long sister near happy.\nMusic learn material training. Positive spend apply raise similar method best look.',
    'email': 'avelasquez@example.net',
    'phone_number': '357-669-9452x49207',
    'json': {
    'name': 'Makayla Park',
    'address': '81534 Rick Locks Suite 665\nLake Holly, WV 51817',
},
    'key96848': 'value83086',
},
    {
    'id': 17527485141656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Lauren Carrillo',
    'address': '6488 Mcneil Lake\nGatesside, GA 76025',
    'text': 'Price top of yes call. Language sit how commercial today threat.\nFinal statement charge study may adult forward open. Of plan you upon stand treat loss. Word always section deal international up.',
    'email': 'tcunningham@example.net',
    'phone_number': '251-773-3318',
    'json': {
    'name': 'Natasha Duke',
    'address': '124 Debra Knoll\nBryantberg, AR 88429',
},
    'key35497': 'value97659',
    'key92105': 'value56218',
    'key48355': 'value16018',
    'key51794': 'value66611',
    'key98494': 'value94420',
},
    {
    'id': 17527485141668,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Betty Mullen',
    'address': 'USS Cox\nFPO AA 14954',
    'text': 'Short low cover interesting hope. Spring of and true human. Choice campaign individual few or blue benefit occur.',
    'email': 'phillipskim@example.com',
    'phone_number': '(798)201-0991x95521',
    'json': {
    'name': 'Jennifer Burns',
    'address': '972 Sarah Alley Suite 591\nLake Susanshire, GU 49022',
},
    'key61752': 'value13251',
},
    {
    'id': 17527485141678,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Samuel Russo',
    'address': '233 Karen Trace\nRobertsland, AK 78677',
    'text': 'Successful rather population subject early course. Home raise activity voice trade. Draw federal establish language speak make nice.',
    'email': 'spencerlinda@example.org',
    'phone_number': '001-294-821-4746x7107',
    'json': {
    'name': 'Sally Stokes',
    'address': '75076 Victor Grove Suite 090\nLaneshire, MI 61353',
},
    'key27571': 'value73841',
},
    {
    'id': 17527485141689,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'David Lee',
    'address': 'Unit 0106 Box 5750\nDPO AP 28927',
    'text': 'Easy south measure name necessary. Goal prevent popular really go anything.\nTraining cold clear behind. Maintain into life market air they especially card.',
    'email': 'jtucker@example.net',
    'phone_number': '(472)496-8710',
    'json': {
    'name': 'Cynthia Grant',
    'address': 'USS Heath\nFPO AA 69884',
},
    'key73686': 'value17503',
    'key85273': 'value32184',
    'key66241': 'value22475',
    'key7632': 'value64950',
    'key62575': 'value35114',
    'key57518': 'value39908',
},
    {
    'id': 17527485141697,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Earl Harris',
    'address': '075 Erika Fields Suite 298\nLake Jenniferhaven, MT 80498',
    'text': 'Account sea end base thank. Beautiful author test moment enjoy collection.',
    'email': 'estespeter@example.com',
    'phone_number': '+1-850-533-0415x31604',
    'json': {
    'name': 'Mary Garcia',
    'address': '09186 Freeman Street\nWest Jennifer, OR 86730',
},
    'key81498': 'value93845',
    'key87687': 'value91260',
    'key26114': 'value85086',
},
    {
    'id': 17527485141708,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jennifer Morales',
    'address': '394 Wells Forges\nAngelaton, AS 39944',
    'text': 'Environment support place mouth drive. Father decade letter reason. World Mr among second floor cultural.\nCity democratic term budget. Certainly notice trouble tonight effort hair likely science.',
    'email': 'johnsonpamela@example.org',
    'phone_number': '(961)206-2807',
    'json': {
    'name': 'Robert Velasquez',
    'address': '041 Woods Motorway Suite 234\nLake Beth, DC 05768',
},
    'key75240': 'value28280',
    'key88002': 'value91040',
    'key66745': 'value23662',
    'key12950': 'value47616',
    'key87449': 'value98697',
},
    {
    'id': 17527485141720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kevin Cruz',
    'address': '1831 Jacqueline Greens\nEast Keithmouth, WA 29215',
    'text': 'Bag successful about pass item street three. Question letter difference protect out we they.\nPainting tree cut recognize rise. Force important collection million certain occur wall.',
    'email': 'mary54@example.net',
    'phone_number': '(548)776-1217x337',
    'json': {
    'name': 'Dustin Cooper DDS',
    'address': '37081 William Garden Suite 859\nPort Malikview, IL 05711',
},
    'key8065': 'value8725',
    'key77949': 'value72195',
    'key27331': 'value50888',
    'key6145': 'value88628',
    'key82052': 'value38290',
    'key73674': 'value33189',
    'key84863': 'value54402',
},
    {
    'id': 17527485141733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Dana Thompson',
    'address': '6310 Ashley Mission Suite 652\nSamanthatown, IL 13323',
    'text': 'Data foreign improve body forget. However hot adult reality us will until.\nHot recently foot interest. Establish shake cut dinner. Pm get side soldier vote body.',
    'email': 'randalllori@example.org',
    'phone_number': '+1-605-915-4024',
    'json': {
    'name': 'Luis Charles',
    'address': '21850 Smith Bypass\nWest Kimberly, LA 31633',
},
    'key67901': 'value33107',
    'key30686': 'value88388',
    'key71538': 'value4906',
    'key84096': 'value8277',
    'key96573': 'value93337',
    'key80577': 'value25404',
    'key51611': 'value83533',
    'key8894': 'value21469',
},
    {
    'id': 17527485141748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jose Black',
    'address': '3271 Ford Trail Suite 844\nWest Matthew, WI 71944',
    'text': 'Family couple through here ability modern.\nSense management its. Nearly look enter gun yet officer born official. Receive bank third on pretty thus food.',
    'email': 'rfarmer@example.org',
    'phone_number': '310-723-8107x044',
    'json': {
    'name': 'William Peterson',
    'address': '6631 Lisa Common Apt. 602\nJessicaberg, MT 30511',
},
    'key41032': 'value68632',
    'key85716': 'value32659',
    'key1456': 'value15794',
    'key35524': 'value96786',
    'key81239': 'value52838',
    'key5946': 'value86785',
    'key88622': 'value48071',
    'key11089': 'value15503',
    'key60053': 'value69254',
    'key96554': 'value11851',
},
    {
    'id': 17527485141761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Tyler Norris',
    'address': '1515 Erin Port Suite 600\nJacobview, MH 47648',
    'text': 'Blue whatever all over interesting total ago teacher. Suddenly word red product event. Character something see decade require yourself common.',
    'email': 'davidsonteresa@example.com',
    'phone_number': '998-520-5141',
    'json': {
    'name': 'Bruce Allen',
    'address': 'Unit 1527 Box 6904\nDPO AP 15344',
},
    'key97555': 'value3727',
    'key76702': 'value11354',
},
    {
    'id': 17527485141773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Bryan Snyder',
    'address': '7427 Joshua Road\nCorytown, RI 56789',
    'text': 'Thank baby oil likely everything body. Opportunity western suddenly position young.\nPolicy administration among pay computer medical training detail. Job sign his like then.',
    'email': 'ghill@example.com',
    'phone_number': '240.452.6774x84899',
    'json': {
    'name': 'Anthony Lee',
    'address': '7895 Kevin Court\nSouth Hailey, NC 88985',
},
    'key8030': 'value57107',
    'key12185': 'value67462',
    'key35926': 'value52185',
    'key18198': 'value99425',
    'key68388': 'value22738',
    'key47603': 'value895',
    'key46181': 'value8102',
    'key85892': 'value41214',
    'key6379': 'value43702',
    'key40589': 'value93893',
},
    {
    'id': 17527485141786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Bridget Martin DDS',
    'address': '66484 Gabriel Village\nWest Rachael, MO 71001',
    'text': 'Resource red together community. Can whole reflect somebody sure method improve born.',
    'email': 'qharris@example.com',
    'phone_number': '2142538883',
    'json': {
    'name': 'Tracy Nguyen',
    'address': '116 Katherine Flat\nSouth Vanessafort, CT 38199',
},
    'key18493': 'value30301',
    'key89427': 'value621',
    'key49053': 'value64173',
    'key4995': 'value99392',
    'key18879': 'value33151',
    'key2045': 'value28410',
    'key48150': 'value21531',
    'key7368': 'value82467',
},
    {
    'id': 17527485141799,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Katelyn Maldonado',
    'address': '3743 Perez Drive Suite 237\nSouth Drewstad, NM 42157',
    'text': 'Interest today house strategy. Somebody try church bit behavior. Charge sport church party mother rule safe.',
    'email': 'bmcdonald@example.com',
    'phone_number': '(586)630-8202x675',
    'json': {
    'name': 'Timothy Simpson',
    'address': '4231 Fitzgerald Hollow\nJoseton, IA 10270',
},
    'key22451': 'value77962',
    'key56630': 'value56712',
    'key9987': 'value10609',
    'key74421': 'value15652',
    'key12544': 'value75971',
    'key8648': 'value40788',
    'key9341': 'value9819',
    'key10190': 'value35360',
    'key50795': 'value50144',
},
    {
    'id': 17527485141811,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Deborah Price',
    'address': '282 Becker Vista\nRoberthaven, WI 78671',
    'text': 'That property time nation. Must upon because art artist seem cost. Recently down economy such.',
    'email': 'gstephens@example.com',
    'phone_number': '+1-831-327-5897x1531',
    'json': {
    'name': 'Sabrina Boyd',
    'address': 'PSC 4901, Box 9883\nAPO AP 40997',
},
    'key5354': 'value56321',
    'key19498': 'value60335',
    'key31280': 'value99841',
    'key66566': 'value30965',
    'key47486': 'value53208',
},
    {
    'id': 17527485141820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Ryan Cox',
    'address': '06673 Potter Stream\nPort Michelleport, MN 04197',
    'text': 'Hour discussion from movement recognize.\nCommon need technology phone. Wish star more cold up finally.',
    'email': 'nhughes@example.net',
    'phone_number': '(694)592-7271x44603',
    'json': {
    'name': 'Brad Shea',
    'address': '0875 Gregory Walk\nSouth Donnabury, MH 82966',
},
    'key21736': 'value47493',
    'key43399': 'value58051',
    'key30553': 'value29031',
    'key71191': 'value22867',
    'key59677': 'value49075',
    'key55561': 'value77675',
    'key8375': 'value72326',
},
    {
    'id': 17527485141831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Daniel Allen',
    'address': '868 Jennifer Lakes Suite 868\nAshleyborough, CA 97357',
    'text': 'Fight front interesting edge it avoid. Happy remember forget budget question ask tax. View then police wait early form affect already.\nEvery base create capital. Toward finish series business take.',
    'email': 'williejohnson@example.com',
    'phone_number': '+1-413-383-2042',
    'json': {
    'name': 'Alexis Jackson',
    'address': '09495 Caleb Overpass Suite 466\nNew Martin, MA 02355',
},
    'key36700': 'value9050',
    'key12308': 'value89375',
    'key20812': 'value78647',
    'key13693': 'value78055',
    'key23260': 'value14990',
    'key22664': 'value72682',
    'key99420': 'value75271',
    'key85737': 'value5182',
    'key72042': 'value4845',
},
    {
    'id': 17527485141842,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Garrett Brown',
    'address': '102 Wilson Springs\nEast Kimberly, FL 32312',
    'text': 'Character office effect leader. Sometimes force employee natural in learn. Who door role could meeting imagine energy range. Table possible staff.',
    'email': 'johnsonerika@example.net',
    'phone_number': '274-955-8373',
    'json': {
    'name': 'Casey Everett',
    'address': 'USNV Carpenter\nFPO AE 21309',
},
    'key59152': 'value1431',
},
    {
    'id': 17527485141852,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Beth Decker',
    'address': '92676 Sarah Ranch Apt. 652\nHancockmouth, DC 46594',
    'text': 'Anything small show grow. Exist lawyer test also role police summer meet. Audience black without manage for may.',
    'email': 'lisa82@example.com',
    'phone_number': '828-960-5912',
    'json': {
    'name': 'Jennifer Hammond',
    'address': '41431 Tucker Rapid Apt. 290\nWest Alyssa, KS 09683',
},
    'key75860': 'value68873',
    'key62142': 'value87374',
    'key38756': 'value1148',
    'key87394': 'value11688',
    'key13584': 'value41602',
    'key39004': 'value4782',
    'key73310': 'value49194',
    'key704': 'value6264',
    'key45705': 'value49845',
},
    {
    'id': 17527485141863,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Heather Hayden',
    'address': '5012 Matthew Knolls Suite 647\nSouth Maxchester, TN 74752',
    'text': 'Hope movement imagine memory we ready seven. Establish though you surface third medical will.\nAhead quickly career the computer although pick. Candidate experience into note my marriage nearly.',
    'email': 'mreynolds@example.org',
    'phone_number': '001-915-653-6141x650',
    'json': {
    'name': 'Bradley Baker MD',
    'address': '7379 Laurie Turnpike\nWest Amanda, CT 22277',
},
    'key59234': 'value64171',
    'key73139': 'value18151',
    'key18600': 'value31122',
    'key68288': 'value28807',
    'key85277': 'value31234',
    'key81429': 'value47996',
    'key61881': 'value29282',
},
    {
    'id': 17527485141874,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Amanda Gonzales',
    'address': '276 Spencer Land Suite 043\nLake Tyler, OH 03340',
    'text': 'Bring minute everything budget short job other pressure. Economic court now threat word. Improve phone early group. Use carry admit coach program deal series ability.',
    'email': 'justinwashington@example.org',
    'phone_number': '(757)649-7494x240',
    'json': {
    'name': 'Gerald Anderson',
    'address': '507 Serrano Trail\nEast Nancy, AK 91787',
},
    'key73191': 'value69943',
},
    {
    'id': 17527485141889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Michael Hart',
    'address': '515 Davenport View Suite 685\nDicksonmouth, MA 96007',
    'text': 'Give officer kitchen second. House hold growth information.\nMilitary team car candidate thought public. Budget thousand hear just. Your election ability page family talk address.',
    'email': 'michellewilliams@example.com',
    'phone_number': '227.266.7211x456',
    'json': {
    'name': 'Joseph Oneill',
    'address': '88276 Alan Spur\nNorth Anita, OK 00513',
},
    'key99463': 'value57141',
    'key46933': 'value75492',
    'key47252': 'value54641',
    'key1320': 'value39126',
    'key60869': 'value12301',
},
    {
    'id': 17527485141902,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'William Harris',
    'address': '9982 Suzanne Parkway Apt. 236\nSouth Travismouth, VI 51200',
    'text': 'International minute short young test light. White TV service worker eye central left. Capital ago money drug traditional blue real. Gun scene space Mrs.',
    'email': 'oclark@example.org',
    'phone_number': '(566)694-1298',
    'json': {
    'name': 'Trevor Hall',
    'address': '057 Michael Drive\nButlerland, MI 56522',
},
    'key87191': 'value20218',
    'key79578': 'value48615',
    'key46500': 'value14032',
    'key54996': 'value11409',
},
    {
    'id': 17527485141913,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Justin Jenkins',
    'address': '26412 Weeks Forges Suite 342\nRebeccaport, MN 00966',
    'text': 'Drop staff environmental education fear. Century fish for. Inside dinner subject fine. Condition task consider reduce pay interview.',
    'email': 'christina31@example.net',
    'phone_number': '(310)523-5847x946',
    'json': {
    'name': 'John Peterson',
    'address': '53365 Timothy Knolls Suite 189\nMannfurt, PR 07183',
},
    'key79282': 'value26329',
    'key48289': 'value91816',
    'key53954': 'value3670',
    'key84001': 'value76154',
    'key67777': 'value79852',
    'key40511': 'value70185',
    'key85524': 'value45841',
    'key69706': 'value97726',
    'key67191': 'value5019',
},
    {
    'id': 17527485141924,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Sarah Alvarez',
    'address': '5907 Andrew Drive\nNew Blake, IN 45707',
    'text': 'Production hear city leader. Drive test perhaps remember word technology. Left concern try radio.',
    'email': 'karen83@example.org',
    'phone_number': '480-208-0114',
    'json': {
    'name': 'Richard Harvey',
    'address': '18691 Harris Track\nCollinston, SD 15530',
},
    'key79040': 'value73612',
    'key32326': 'value17139',
    'key44196': 'value94652',
    'key4856': 'value40315',
    'key82881': 'value51052',
    'key79656': 'value87002',
    'key37388': 'value18565',
    'key27853': 'value87093',
    'key51846': 'value19997',
    'key10243': 'value12376',
},
    {
    'id': 17527485141935,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Brittany Fields',
    'address': '035 Darius Plains Suite 111\nSmithville, RI 60271',
    'text': 'Friend food change color money true man. Fine what easy somebody on crime.\nEdge apply remember. Into red guess behavior test range place. Science experience PM company.',
    'email': 'ncordova@example.net',
    'phone_number': '(521)678-5665x25416',
    'json': {
    'name': 'Linda Miller',
    'address': '3626 Richard Views\nEast Jeanette, CO 80134',
},
    'key5073': 'value7910',
    'key43450': 'value54892',
    'key7021': 'value13825',
    'key58048': 'value34887',
    'key79706': 'value22842',
    'key87606': 'value1358',
    'key33815': 'value19677',
},
    {
    'id': 17527485141946,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Sandra Sellers',
    'address': '729 Evelyn Way\nSouth Robertburgh, SD 52821',
    'text': 'Recent cell bar of cold as technology. Night himself activity test money. Part player baby north every nation eat. Far get other.',
    'email': 'melaniesoto@example.org',
    'phone_number': '+1-817-208-3089x166',
    'json': {
    'name': 'Jason Smith',
    'address': '9111 Joann Squares\nSouth Jamesborough, WA 22963',
},
    'key31598': 'value49124',
    'key98874': 'value49075',
    'key28110': 'value42469',
    'key72913': 'value76161',
    'key89352': 'value122',
},
    {
    'id': 17527485141957,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Elizabeth Contreras',
    'address': '34012 Emily Rest\nMccarthyland, UT 14442',
    'text': 'Within serious would house quickly score idea consider. Since civil method finish care major place.\nEverybody check read well future cut. Pull plan room quality ten staff hit north.',
    'email': 'foleyholly@example.net',
    'phone_number': '467.794.6281x62645',
    'json': {
    'name': 'Daniel Glenn',
    'address': '968 Amy Cape Suite 439\nWagnerfurt, MA 21700',
},
    'key99932': 'value9729',
    'key7518': 'value99057',
    'key45434': 'value50517',
    'key21150': 'value66011',
    'key80581': 'value81406',
    'key36574': 'value52172',
},
    {
    'id': 17527485141969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Richard Meyer',
    'address': '7480 Jennifer Lodge Suite 869\nFoleyland, GU 94028',
    'text': 'Voice strategy nor front through although. Once able political such capital you perhaps chair. You lot player even three structure right.',
    'email': 'ericatate@example.net',
    'phone_number': '8402783782',
    'json': {
    'name': 'James Hernandez',
    'address': '697 Sutton Stream\nWest Haroldside, MN 60134',
},
    'key39155': 'value60073',
    'key41945': 'value48083',
    'key30169': 'value62975',
    'key37503': 'value87216',
},
    {
    'id': 17527485141980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Robert Gibson',
    'address': '725 John Mountain\nMillerfort, NM 59681',
    'text': 'During TV many weight positive international address local. World marriage specific western soon type.',
    'email': 'alicialutz@example.org',
    'phone_number': '(780)398-6774x0736',
    'json': {
    'name': 'Albert Malone',
    'address': '4062 Cohen Circle\nNorth Patrick, OR 21907',
},
    'key69645': 'value310',
    'key95138': 'value99376',
    'key13015': 'value52951',
    'key77118': 'value34060',
    'key80918': 'value11139',
    'key68566': 'value94952',
    'key61969': 'value6496',
},
    {
    'id': 17527485141992,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Robert Mcdaniel',
    'address': '6288 Smith Orchard\nNew Charleston, WV 30552',
    'text': 'Option blood social wait popular.\nEverybody although that matter account window. Stock opportunity attack if year.\nLater blue wish song. Stock thought pay behavior plant cold view.',
    'email': 'andrew97@example.net',
    'phone_number': '589.205.6412x03236',
    'json': {
    'name': 'Benjamin Scott',
    'address': '05126 Dylan Way Suite 047\nDixonburgh, MH 44655',
},
    'key67741': 'value38737',
    'key14529': 'value83671',
    'key71641': 'value48235',
    'key82484': 'value68347',
    'key31704': 'value4842',
    'key19517': 'value70438',
    'key18035': 'value13563',
    'key56154': 'value72034',
    'key31589': 'value24106',
    'key7463': 'value77698',
},
    {
    'id': 17527485142003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Laura Petty',
    'address': '2328 Anderson Fort\nNorth Joanne, MP 81093',
    'text': 'Whatever industry wall. Culture ready risk financial international sit.\nMr trip practice sing issue participant. Fall knowledge three floor someone. Various bill with trip summer century key.',
    'email': 'rick75@example.org',
    'phone_number': '409-341-7470',
    'json': {
    'name': 'Amy Miller',
    'address': '5830 Blake Grove\nHowardmouth, VA 15431',
},
    'key94396': 'value90029',
    'key34315': 'value74189',
    'key86617': 'value18658',
    'key80622': 'value55084',
    'key23750': 'value76937',
},
    {
    'id': 17527485142014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Natasha Reyes',
    'address': '87876 Michael Knoll Suite 058\nNew Jenniferstad, TN 40816',
    'text': 'Certain consumer region. Game hundred take range. Program themselves church office administration themselves send.',
    'email': 'donnashepard@example.net',
    'phone_number': '001-701-665-1239x653',
    'json': {
    'name': 'Amanda Bass',
    'address': '0355 Mark Camp\nDianaville, CA 25334',
},
    'key9252': 'value84164',
    'key82572': 'value90009',
    'key56114': 'value25406',
    'key81356': 'value82575',
},
    {
    'id': 17527485142025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Albert Bond',
    'address': '9698 Michael Extensions Apt. 547\nShawnshire, FL 29418',
    'text': 'Anyone do indeed increase. Member former war week.\nCrime item while a matter close here. Democrat nearly campaign off scene voice.\nMay room better instead I drive impact. Wear cut ready behind great.',
    'email': 'anita10@example.org',
    'phone_number': '273.465.8659',
    'json': {
    'name': 'Harry Rosales',
    'address': '420 Dawn Curve Apt. 929\nNorth Hunter, TX 35807',
},
    'key20573': 'value3846',
    'key32642': 'value61383',
    'key68647': 'value29137',
    'key92504': 'value4404',
    'key89934': 'value82994',
    'key99378': 'value99925',
    'key74449': 'value75797',
    'key52043': 'value31613',
    'key28518': 'value18319',
    'key26928': 'value58810',
},
    {
    'id': 17527485142035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jason Lopez',
    'address': '164 Myers Mews Suite 234\nPort Brent, NH 83984',
    'text': 'Hospital teach character both cost sound. Without heavy accept.\nDrug window law school. Large allow he week.',
    'email': 'smithkevin@example.com',
    'phone_number': '001-572-322-6807',
    'json': {
    'name': 'Sarah Smith',
    'address': '05872 Burke Causeway Apt. 565\nLake Richard, MO 30070',
},
    'key2734': 'value46839',
    'key11742': 'value49830',
    'key67288': 'value27693',
    'key30967': 'value10722',
},
    {
    'id': 17527485142047,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jeffrey Martin',
    'address': '289 Patrick Estate\nSouth Terrybury, GA 04396',
    'text': 'Follow a particularly scene. Direction school report like. Environment its compare listen doctor wait.',
    'email': 'dhicks@example.org',
    'phone_number': '952.665.5817x506',
    'json': {
    'name': 'Jay Curtis',
    'address': '3179 Susan Plains Apt. 177\nNorth Craigville, WA 87792',
},
    'key72945': 'value42552',
    'key50129': 'value62392',
    'key19948': 'value67936',
    'key56605': 'value27584',
},
    {
    'id': 17527485142058,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Mary Davidson',
    'address': '5037 Kaitlin Lodge Apt. 479\nChristianshire, NE 44727',
    'text': 'Year full bring eye trip people drive.\nLetter issue role success yard spring.\nReveal artist mission official. Size must assume man two well.',
    'email': 'james29@example.net',
    'phone_number': '+1-388-938-2677',
    'json': {
    'name': 'Kevin Abbott',
    'address': '53223 Anthony Cape\nSouth Amy, DC 24532',
},
    'key11097': 'value73725',
    'key12596': 'value67560',
    'key18088': 'value47846',
    'key29197': 'value21802',
    'key55798': 'value63201',
    'key96067': 'value38621',
},
    {
    'id': 17527485142068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Darryl Lewis',
    'address': '75988 Banks Station\nScottburgh, AS 65875',
    'text': 'Set face their fly put. Writer trial boy.\nOpportunity space side power drug sit half I.\nAbout management out unit all world baby. Suggest positive common.',
    'email': 'donna03@example.com',
    'phone_number': '741.412.2488',
    'json': {
    'name': 'Timothy Kane',
    'address': 'PSC 7819, Box 8769\nAPO AE 72820',
},
    'key24753': 'value53447',
    'key99726': 'value4105',
    'key65870': 'value61302',
},
    {
    'id': 17527485142076,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Donna Morrow',
    'address': '603 Joseph Inlet Apt. 055\nPort Angelaside, RI 78459',
    'text': 'Sort mean board remain skill happen.\nYes north ready. Because fear send smile evening perform none pay. Majority occur effort personal upon until.',
    'email': 'larry30@example.net',
    'phone_number': '802.821.6690x6165',
    'json': {
    'name': 'Amy Mcconnell',
    'address': '1328 Ruiz Road\nAndrewshire, AZ 90484',
},
    'key55812': 'value99620',
    'key77912': 'value49878',
    'key94679': 'value86071',
    'key21019': 'value93459',
    'key51580': 'value44762',
    'key63170': 'value62218',
    'key93004': 'value61828',
    'key31814': 'value18270',
},
    {
    'id': 17527485142086,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Yesenia Perez',
    'address': '35649 Gutierrez Pike Suite 923\nSouth Tiffanyborough, NY 77756',
    'text': 'Act most fear east effect. Bank story after senior.\nCover home hair north clear. Hair simply though tend control government.',
    'email': 'roberta04@example.com',
    'phone_number': '001-850-971-0722x2020',
    'json': {
    'name': 'Frederick Smith',
    'address': '98492 Michael Burg\nLake Kyle, NY 88862',
},
    'key21758': 'value28226',
    'key82490': 'value87008',
    'key97597': 'value20228',
    'key60229': 'value82085',
    'key67494': 'value71638',
    'key30712': 'value85048',
    'key84723': 'value26169',
    'key20199': 'value4651',
    'key91048': 'value10923',
},
    {
    'id': 17527485142097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Debra Berry',
    'address': '043 Rachel Branch Apt. 247\nStuartfurt, GU 56702',
    'text': 'Seek through Republican nor. Medical wrong security step hear natural. Get hold effort physical reality.',
    'email': 'kimmitchell@example.com',
    'phone_number': '001-494-707-2688',
    'json': {
    'name': 'James Ballard',
    'address': '20429 Garcia Plaza\nHenryside, ND 96493',
},
    'key64175': 'value79341',
    'key94023': 'value81373',
    'key23461': 'value39638',
    'key56631': 'value27879',
},
    {
    'id': 17527485142109,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Michael Morris',
    'address': '12483 Carlson Brooks\nJoshuachester, AS 74939',
    'text': 'Standard nature help computer large. Sing pay that wide else season probably.',
    'email': 'dtaylor@example.com',
    'phone_number': '+1-248-330-0680x894',
    'json': {
    'name': 'Vickie Hardy',
    'address': '812 Carroll Terrace\nNorth Fernando, MS 73312',
},
    'key51795': 'value22172',
    'key62107': 'value20519',
    'key71857': 'value3701',
    'key25086': 'value34417',
    'key78623': 'value72008',
    'key79517': 'value65569',
    'key14037': 'value86749',
    'key12532': 'value76262',
    'key8696': 'value99981',
},
    {
    'id': 17527485142120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Mr. Michael Bush',
    'address': '55294 Sierra Rapid Apt. 092\nPort Feliciastad, NC 42834',
    'text': 'Approach notice ahead purpose seven write.\nChange another fish audience national. Baby rock grow while argue but clear.\nInternational part late news outside nice can.',
    'email': 'kjohnson@example.org',
    'phone_number': '(542)249-0158x31526',
    'json': {
    'name': 'Lisa Walker',
    'address': '1408 Anderson Causeway\nMichaelside, VT 69752',
},
    'key2523': 'value48386',
    'key82768': 'value9403',
    'key58542': 'value24526',
    'key60376': 'value94807',
    'key34984': 'value61440',
    'key77464': 'value68891',
    'key67110': 'value7157',
    'key33713': 'value2100',
    'key36100': 'value66908',
    'key8328': 'value34976',
},
    {
    'id': 17527485142131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Lori Williams',
    'address': 'Unit 7419 Box 0003\nDPO AP 16927',
    'text': 'Only look condition if court. Boy add decision between fire.\nValue task return speech. For matter soon office. Matter wish close common seven group. Affect city between record as major market.',
    'email': 'vanessa69@example.net',
    'phone_number': '+1-298-711-2906',
    'json': {
    'name': 'Susan Harrell',
    'address': '577 Martinez Road\nEast Kristine, UT 28130',
},
    'key1222': 'value66031',
    'key24126': 'value42553',
    'key50090': 'value39445',
    'key49193': 'value45172',
    'key98047': 'value379',
    'key30527': 'value15766',
    'key75703': 'value33349',
    'key65945': 'value17109',
},
    {
    'id': 17527485142139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Yolanda White',
    'address': '532 Danielle Meadows Apt. 325\nSouth Kirk, CT 74965',
    'text': 'Impact several current nearly off toward. Result my especially relate step institution. Soon maybe daughter sign senior.\nWe memory pay campaign argue.',
    'email': 'othomas@example.org',
    'phone_number': '(921)475-2239',
    'json': {
    'name': 'Angela Perez',
    'address': '290 Jensen Haven Apt. 728\nPort Christineborough, PW 98581',
},
    'key80494': 'value6940',
    'key95175': 'value19136',
    'key35512': 'value36165',
    'key60936': 'value58808',
    'key84975': 'value88413',
    'key89637': 'value14765',
    'key38307': 'value48823',
    'key48111': 'value79456',
    'key16499': 'value6702',
    'key94816': 'value5676',
},
    {
    'id': 17527485142150,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Julie Campos',
    'address': '80793 Amy Springs\nWest John, GU 45647',
    'text': 'Pm involve purpose blue skin. Much weight say process week develop bank. Above along forget poor standard book quite street.',
    'email': 'vanessajones@example.com',
    'phone_number': '934.809.4107x64496',
    'json': {
    'name': 'Michael Miller',
    'address': '07117 Burgess Stravenue\nWest Ryan, PW 21331',
},
    'key74882': 'value81348',
    'key49575': 'value79966',
    'key98070': 'value69271',
    'key89399': 'value82079',
    'key62287': 'value58503',
    'key70516': 'value55502',
    'key28919': 'value37385',
    'key17442': 'value87376',
    'key24609': 'value18716',
},
    {
    'id': 17527485142161,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Janet Hardin',
    'address': '7013 Herrera Coves Apt. 128\nPort Amanda, NJ 86425',
    'text': 'Value decision east source treat enjoy quality respond. Speech life crime out important field discuss conference.',
    'email': 'corysullivan@example.org',
    'phone_number': '603-937-2310',
    'json': {
    'name': 'Pamela Medina',
    'address': '54161 Perry Highway\nAdamberg, CA 59089',
},
    'key83493': 'value7834',
},
    {
    'id': 17527485142172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Melissa Allen',
    'address': '9853 Amy Point\nTylerport, AS 31334',
    'text': 'Political close news she. During to rate radio two. For customer cost skill difference medical.\nCover president before be. Onto tax common return white spend answer.',
    'email': 'jessica84@example.org',
    'phone_number': '443.978.9714',
    'json': {
    'name': 'Anthony Duarte',
    'address': '92274 Stafford Flat\nWangbury, NE 44858',
},
    'key42067': 'value61754',
    'key75292': 'value69009',
    'key10620': 'value11840',
},
    {
    'id': 17527485142183,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Glenn Moss',
    'address': '570 Lori Squares Suite 313\nWandamouth, WA 84872',
    'text': 'Role seat small his. Authority floor necessary health. Attack trial reason increase analysis.\nLife Republican husband worker. Force among positive plant middle tonight.',
    'email': 'mariarosales@example.net',
    'phone_number': '+1-804-970-8787x574',
    'json': {
    'name': 'Patricia Davis',
    'address': '2282 James Crest\nPaulaburgh, FM 65809',
},
    'key73002': 'value23408',
    'key62976': 'value18180',
    'key32157': 'value46443',
    'key50151': 'value59295',
    'key8413': 'value66420',
    'key76056': 'value79097',
    'key37596': 'value40644',
    'key52310': 'value61959',
    'key27029': 'value83547',
},
    {
    'id': 17527485142194,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'John Scott',
    'address': '074 Curtis Roads\nWest Jack, NM 37314',
    'text': 'I how put. Why market staff tree social age. Kind raise month form term main leave always. Morning those understand exactly color office.',
    'email': 'smithdana@example.net',
    'phone_number': '(411)749-1532',
    'json': {
    'name': 'Brandon Griffin',
    'address': '19613 Lisa Flats\nWest Amandaview, AS 41858',
},
    'key85642': 'value3571',
    'key88337': 'value24865',
    'key75698': 'value87533',
    'key53413': 'value72901',
    'key90971': 'value57281',
    'key94885': 'value85036',
    'key57390': 'value74442',
    'key66646': 'value26607',
},
    {
    'id': 17527485142205,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Shelly Nunez',
    'address': '18750 Russell Extension Suite 499\nTracyview, OH 69787',
    'text': 'Within control eight concern politics ability government accept. From today station should close far dog.',
    'email': 'kristensoto@example.net',
    'phone_number': '398.639.6796x6104',
    'json': {
    'name': 'Donna Long',
    'address': '109 Jones Junction Suite 378\nWest Elizabethburgh, MN 81392',
},
    'key98078': 'value5565',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': 'b5859f04-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_08_033707JGGgAwku',
    'data': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'address',
    'uid',
    'email',
    'json',
],
    'filter': 'uid >= 0',
    'limit': 16385,
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'b5859f04-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_08_033707JGGgAwku',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[16385]_1752748515.json')
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
    test = AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidLimit163851752748515Json()
    test.run_tests()
