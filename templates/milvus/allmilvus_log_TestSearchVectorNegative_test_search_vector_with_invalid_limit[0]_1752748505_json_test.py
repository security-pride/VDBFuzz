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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVectorNegative_test_search_vector_with_invalid_limit[0]_1752748505_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[0]_1752748505.json"
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



class AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidLimit01752748505Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[0]_1752748505.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[0]_1752748505.json"
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
    'RequestId': 'aff611a4-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_34_58_705003UdRExveH',
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
    'RequestId': 'aff611a4-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_34_58_705003UdRExveH',
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
    'RequestId': 'aff611a4-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_34_58_705003UdRExveH',
    'data': [
    {
    'id': 17527485047826,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jason Chavez',
    'address': '0430 Christina Villages\nLake Sarahport, NJ 70308',
    'text': 'List sound speak everybody. Within myself toward support western.\nPoint scientist with me remember. Fact commercial cultural spend service later.',
    'email': 'mary37@example.net',
    'phone_number': '825.256.0560x77030',
    'json': {
    'name': 'Troy Glover',
    'address': '95775 Leslie Mountain Suite 329\nClarkton, TX 04935',
},
    'key31247': 'value54614',
    'key59784': 'value52642',
    'key21042': 'value53714',
    'key22706': 'value86493',
    'key18929': 'value29296',
    'key61876': 'value3959',
    'key74014': 'value53175',
    'key84877': 'value24596',
    'key18634': 'value16700',
},
    {
    'id': 17527485047841,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Zachary Lee',
    'address': '6016 Steven Brooks Apt. 918\nEast Austin, KY 38084',
    'text': 'Ask box left knowledge show management. Through pressure management ok early.\nTest assume now letter firm piece machine. Art claim sort serious. Letter nothing responsibility.',
    'email': 'brandonblanchard@example.com',
    'phone_number': '3722065165',
    'json': {
    'name': 'Joshua Estrada',
    'address': '749 Ho Union\nKleinberg, TN 22630',
},
    'key79006': 'value23430',
    'key13574': 'value31943',
    'key42485': 'value15481',
    'key56691': 'value22714',
    'key88544': 'value94572',
},
    {
    'id': 17527485047853,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Stephanie Bradley',
    'address': '996 Oconnell Squares\nJohnstonburgh, NC 54245',
    'text': 'Head quickly speech special into. Professor action hot bank bag your able space.\nPresident money wear military. Police pretty attack back pay fact.\nPrepare charge space seven.',
    'email': 'kennedyjason@example.org',
    'phone_number': '758.740.1349x2701',
    'json': {
    'name': 'William Butler',
    'address': 'Unit 4199 Box 1334\nDPO AA 13715',
},
    'key82340': 'value69989',
    'key6365': 'value44621',
    'key67643': 'value50946',
    'key46067': 'value48104',
    'key91513': 'value53264',
},
    {
    'id': 17527485047864,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Nicolas Gutierrez',
    'address': '955 Riddle Crossroad Apt. 977\nTorresstad, WA 16186',
    'text': 'True on what best.\nKnowledge up plan policy chair investment beautiful. Program technology continue organization culture skill leave. Speech everything page much.',
    'email': 'abenson@example.org',
    'phone_number': '(797)365-0493',
    'json': {
    'name': 'Eric Lynn',
    'address': '116 Judy Stream Apt. 755\nGreenborough, VT 60971',
},
    'key38624': 'value12243',
    'key88560': 'value23499',
    'key16501': 'value44960',
    'key34919': 'value89859',
    'key4383': 'value23359',
    'key19105': 'value31061',
    'key37366': 'value33563',
    'key54368': 'value60332',
    'key45994': 'value20380',
},
    {
    'id': 17527485047875,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Stacey Hamilton',
    'address': '72175 Brian Shore\nLake Trevor, CA 71045',
    'text': 'Around face theory. Event off yourself who end Republican glass.\nStage executive land determine development. Possible despite gas difficult. Financial least home during yourself exactly edge.',
    'email': 'andrewthompson@example.net',
    'phone_number': '001-656-638-4584',
    'json': {
    'name': 'Jeremy Marsh',
    'address': '78324 Christensen Curve Apt. 465\nFaulknerport, VI 63245',
},
    'key65995': 'value96213',
    'key77944': 'value33088',
    'key88061': 'value29763',
    'key12510': 'value12802',
    'key79813': 'value17621',
    'key30508': 'value63036',
},
    {
    'id': 17527485047887,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Elizabeth Garrison',
    'address': '1982 Olson Trail Suite 518\nNew Aaron, CO 65471',
    'text': 'Low public interesting me customer think. Site notice here challenge too.\nClass part these economy dark finish thus. Paper sure book child.',
    'email': 'cjones@example.org',
    'phone_number': '+1-829-651-4721x259',
    'json': {
    'name': 'Leah Brooks',
    'address': '2469 Martinez Stravenue Apt. 565\nEugenechester, WY 71353',
},
    'key26617': 'value35317',
    'key42008': 'value17507',
    'key80124': 'value87963',
    'key5838': 'value4076',
},
    {
    'id': 17527485047898,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Jaime Anderson',
    'address': '22098 Page Junctions\nLake Karenport, NM 81199',
    'text': 'Break civil across glass help. Movement factor civil one. History practice like determine century hold kid. Imagine Republican base offer.',
    'email': 'tylersteele@example.net',
    'phone_number': '388-595-6607',
    'json': {
    'name': 'Samantha Gomez',
    'address': '34012 Tate Island Suite 143\nEast Natashaborough, OK 33900',
},
    'key14444': 'value98893',
    'key19975': 'value81147',
    'key95350': 'value68077',
    'key63675': 'value79425',
    'key31463': 'value84311',
    'key75088': 'value80430',
    'key79690': 'value8440',
},
    {
    'id': 17527485047910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Diana Lee',
    'address': '820 Jimmy Extension Suite 919\nRodriguezchester, TN 61268',
    'text': 'Fight interview identify member more human success. Suffer could address station region inside since. Arrive boy direction big answer test.',
    'email': 'vanessa02@example.net',
    'phone_number': '919.944.4704x81530',
    'json': {
    'name': 'Nicholas Coleman',
    'address': '7735 Wilson Place\nPort Cathyton, AZ 61165',
},
    'key75642': 'value88570',
    'key23231': 'value87038',
    'key68620': 'value26891',
    'key29796': 'value91266',
    'key97666': 'value29778',
    'key4261': 'value8865',
    'key27458': 'value32902',
},
    {
    'id': 17527485047921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Brittany Holder',
    'address': '167 Victoria Lock\nLake Tyrone, NY 64879',
    'text': 'Most pressure whom town condition.\nMrs site interest already. Activity key floor.\nTax reason process let democratic term require. Music until improve account wind. Experience friend environment a.',
    'email': 'shannonroach@example.com',
    'phone_number': '+1-552-272-5485x42579',
    'json': {
    'name': 'Kevin Garcia',
    'address': '9702 Justin Springs Apt. 651\nScottberg, PW 12957',
},
    'key67645': 'value24199',
    'key24515': 'value52237',
    'key81272': 'value46274',
    'key83132': 'value53539',
},
    {
    'id': 17527485047933,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Rebecca Henry',
    'address': 'PSC 9072, Box 6516\nAPO AP 00909',
    'text': 'Change reason manage what. Theory mean white above hospital whom commercial. Bit democratic check own central interest maintain. Market grow gas four blood real clear.',
    'email': 'vanessareed@example.com',
    'phone_number': '001-960-762-6563x74731',
    'json': {
    'name': 'Walter Kramer',
    'address': '936 Alvarez Terrace Apt. 470\nPort Kristinaside, WY 78838',
},
    'key27340': 'value16379',
},
    {
    'id': 17527485047943,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'William Brennan',
    'address': '87989 Kelly Corner Suite 598\nRodriguezside, TX 17582',
    'text': 'Simple produce we particularly positive material turn young. Event whose rule itself any whose. Recently heart place claim land.',
    'email': 'wiseemily@example.net',
    'phone_number': '+1-613-297-8651x188',
    'json': {
    'name': 'Andrea Vega',
    'address': '62628 Holmes Light Apt. 596\nNew Michelleberg, WA 12518',
},
    'key58621': 'value41699',
    'key99320': 'value16488',
    'key43802': 'value47672',
    'key36326': 'value67904',
    'key93175': 'value21904',
    'key68964': 'value32892',
    'key54100': 'value45279',
},
    {
    'id': 17527485047954,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Lauren Moreno',
    'address': 'PSC 1881, Box 6966\nAPO AP 07400',
    'text': 'Night certain up political.\nStructure day ask. World finish lay nothing discover road. Executive executive medical TV must operation.\nAdmit forward pass get him. Continue someone song imagine relate.',
    'email': 'dperez@example.com',
    'phone_number': '+1-436-882-4013x90892',
    'json': {
    'name': 'Jennifer Lopez',
    'address': '7621 Butler Forest\nMatthewview, PW 55873',
},
    'key25872': 'value23778',
    'key78109': 'value14325',
    'key49490': 'value9776',
    'key71776': 'value80410',
    'key28484': 'value69299',
    'key44585': 'value22901',
},
    {
    'id': 17527485047963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'David Mitchell',
    'address': '288 Reyes Junction Apt. 095\nSouth Jennifer, WI 52065',
    'text': 'Huge money side. Concern energy early seek. Through call voice central.',
    'email': 'sawyerchristopher@example.org',
    'phone_number': '7043180043',
    'json': {
    'name': 'Emily Melton',
    'address': '39607 White Way\nSantostown, VA 33181',
},
    'key28336': 'value90499',
    'key44196': 'value11486',
    'key49096': 'value87099',
},
    {
    'id': 17527485047974,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Brian Cole',
    'address': '5083 Murphy Square Apt. 695\nWhitneyville, NJ 19355',
    'text': 'System generation firm over scientist less. Half while player value perhaps. Performance season maybe article sense me.',
    'email': 'jamesderek@example.org',
    'phone_number': '225-664-0170x24191',
    'json': {
    'name': 'Michael Jones',
    'address': '666 Sarah Rue Apt. 024\nNew Jamesview, ME 38773',
},
    'key49281': 'value74485',
    'key19534': 'value64946',
    'key5109': 'value39739',
    'key28454': 'value56850',
    'key74819': 'value23570',
    'key95122': 'value72638',
    'key55418': 'value6868',
    'key41896': 'value74402',
    'key72923': 'value73864',
    'key81672': 'value62768',
},
    {
    'id': 17527485047986,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Willie Cook',
    'address': '51474 Garner Lights Suite 570\nSouth Jason, NE 08534',
    'text': 'General final fish power. Continue miss sell run well. Best soldier water huge guess.\nMajority understand shoulder trade range dream. Catch could line stay ago.',
    'email': 'vchristensen@example.net',
    'phone_number': '362-476-1261x32433',
    'json': {
    'name': 'Debra Anderson',
    'address': '5106 Kenneth Knolls\nNew Mindy, ND 64844',
},
    'key70129': 'value57590',
    'key51220': 'value87139',
    'key28565': 'value85528',
    'key74759': 'value66843',
    'key61469': 'value79452',
    'key6256': 'value8974',
    'key76510': 'value5552',
    'key16588': 'value82135',
    'key34472': 'value45133',
},
    {
    'id': 17527485047997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Olivia Scott',
    'address': '22545 Kara Village\nMichaelborough, NM 04018',
    'text': 'Book off too take few total. Firm picture far necessary language guess.\nFine again idea where none keep. Great fine wide arrive trip. Doctor television five body commercial wall environmental.',
    'email': 'dukebrenda@example.net',
    'phone_number': '935-341-4207x21556',
    'json': {
    'name': 'Alicia Williams',
    'address': '116 Shelton Spur Apt. 916\nPort Michellemouth, NJ 53432',
},
    'key88107': 'value7872',
},
    {
    'id': 17527485048009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Jeremy Davenport',
    'address': '907 Brian Street\nSteventon, KY 46152',
    'text': 'Clearly make can field.\nTv indicate risk society successful respond talk. Themselves animal plan year.\nDirection little affect next. Around so church daughter language camera audience on.',
    'email': 'xgrant@example.net',
    'phone_number': '+1-866-679-7548',
    'json': {
    'name': 'Nicole Ellis',
    'address': '182 Kayla Prairie\nWest Cameron, AK 90774',
},
    'key54057': 'value36968',
    'key74524': 'value98376',
    'key3907': 'value90830',
    'key87830': 'value12902',
},
    {
    'id': 17527485048019,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tyler Brown',
    'address': '3878 Nancy Corner\nAndreachester, MA 05294',
    'text': 'Study operation person animal story agency. Say fish run.\nDream tell seek dark nearly option big. Market have order.',
    'email': 'zmiller@example.com',
    'phone_number': '973-347-7963',
    'json': {
    'name': 'Jeffrey Robinson',
    'address': '4474 Miller Pass\nPort Georgebury, AS 96439',
},
    'key54285': 'value79137',
    'key10469': 'value52242',
    'key69312': 'value25167',
},
    {
    'id': 17527485048030,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Rachel Anderson',
    'address': '51131 Stephanie Centers\nPort Virginiamouth, WA 84895',
    'text': 'Teach work yet early important today radio. Material idea appear each cover. Report lawyer career during per.\nBank fill million side tonight and me. Half majority maintain turn.',
    'email': 'carrolldavid@example.org',
    'phone_number': '793-870-9190x8495',
    'json': {
    'name': 'Amy Reese',
    'address': '627 Jones Locks\nStevenchester, NH 69417',
},
    'key15902': 'value37001',
    'key99838': 'value56253',
    'key73457': 'value31203',
    'key31442': 'value35654',
    'key71568': 'value63797',
    'key62157': 'value29878',
    'key90612': 'value52906',
    'key64451': 'value31004',
    'key34141': 'value82363',
    'key11229': 'value70383',
},
    {
    'id': 17527485048041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Michelle Miller DVM',
    'address': '7701 Velasquez Isle\nEast Kimfurt, ID 27187',
    'text': 'Choice somebody could since not eat. Billion capital present religious month model.\nEven bad leader college audience behind.',
    'email': 'kdunlap@example.com',
    'phone_number': '426.480.3842x417',
    'json': {
    'name': 'Phyllis Davis',
    'address': '37144 Donald Fall Apt. 448\nLake George, CO 75330',
},
    'key96859': 'value97138',
    'key47977': 'value57227',
    'key79111': 'value33401',
    'key25444': 'value98992',
    'key77481': 'value42023',
    'key14883': 'value72321',
    'key5110': 'value64305',
    'key81471': 'value87963',
    'key50044': 'value26684',
    'key99843': 'value85857',
},
    {
    'id': 17527485048053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Frank Williams',
    'address': '5339 Jeffrey Ford\nScottville, AR 28121',
    'text': 'Agent bring probably area life fill. Already war similar us plan chance life like.\nEffort mention policy suffer bill through call. Reason later moment because piece network.',
    'email': 'delgadojennifer@example.com',
    'phone_number': '3536740932',
    'json': {
    'name': 'Bryan Davis',
    'address': '18709 Estrada Road Suite 728\nLawrenceland, OK 53188',
},
    'key63840': 'value59169',
    'key72980': 'value99790',
    'key61436': 'value76024',
    'key41361': 'value98854',
    'key77456': 'value93042',
    'key24285': 'value40495',
},
    {
    'id': 17527485048064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Patricia Shields',
    'address': 'PSC 9130, Box 0735\nAPO AP 37813',
    'text': 'Understand remain quite kind challenge picture against. Build evidence prove.\nWrong look prove product point or. Sport rise policy where. Own need know window report low.',
    'email': 'michael43@example.net',
    'phone_number': '545.647.5871',
    'json': {
    'name': 'Mark Mann',
    'address': '626 Brittney Square\nPort Philipberg, ID 71059',
},
    'key31402': 'value54101',
    'key69790': 'value24316',
    'key81361': 'value19359',
    'key92014': 'value99993',
},
    {
    'id': 17527485048073,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Michelle Richardson',
    'address': '644 Martinez Garden\nJuliefort, CT 20670',
    'text': 'Vote president include heavy. Hope present interesting good art.\nStep unit also network. Parent boy few in hard into. Although suggest let forget red young.',
    'email': 'cory97@example.org',
    'phone_number': '+1-288-910-1073x91698',
    'json': {
    'name': 'Stephanie Lee',
    'address': '5142 Allen Ridge Apt. 092\nNorth Jonathan, IA 92911',
},
    'key12799': 'value45877',
    'key77115': 'value73618',
    'key50290': 'value90929',
    'key77778': 'value94051',
    'key47931': 'value1240',
},
    {
    'id': 17527485048083,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Maria Garcia',
    'address': '43814 Gray Island\nNorth Nicholasview, TN 31386',
    'text': 'Record current management citizen. Real high blue political scene way through must.\nName else by southern I. But consider past who.',
    'email': 'iboone@example.net',
    'phone_number': '001-632-945-1206',
    'json': {
    'name': 'Mr. Anthony Schmidt',
    'address': '5515 Barnes Pass\nNew Lori, TN 08807',
},
    'key40143': 'value70799',
    'key31450': 'value3294',
    'key21794': 'value93205',
    'key70236': 'value78338',
    'key52675': 'value93316',
},
    {
    'id': 17527485048094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Jesus Ochoa',
    'address': '8611 Michael Walks Apt. 652\nEast Kyleside, ND 63690',
    'text': 'Image man camera two store. Key be company down. Year early bag reason federal concern.\nTelevision care them special movement. Hit fast door approach address.',
    'email': 'lthomas@example.org',
    'phone_number': '4722595165',
    'json': {
    'name': 'Julia Davis DVM',
    'address': '5574 Cox Court Apt. 670\nNorth Laura, MN 89667',
},
    'key86578': 'value39594',
},
    {
    'id': 17527485048105,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Alicia Michael',
    'address': '9626 Benjamin Trail\nNorth Kayla, MD 92773',
    'text': 'Make in long cause finish kitchen sometimes child. Heart theory opportunity.\nWonder middle kitchen expert other. Trial book blood cup during. Early majority baby.',
    'email': 'xmedina@example.com',
    'phone_number': '495-256-5293x87078',
    'json': {
    'name': 'Mark Blevins',
    'address': '129 Ruiz Crossing Suite 013\nBryanttown, MT 18278',
},
    'key38928': 'value52992',
},
    {
    'id': 17527485048116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Danielle Sanchez',
    'address': '9664 Gregg Parks Apt. 603\nNew Bradleyville, MA 02029',
    'text': 'Possible politics protect the time. Stuff treat difference report. Civil bank detail last read.',
    'email': 'tim42@example.net',
    'phone_number': '732-658-2322x1434',
    'json': {
    'name': 'Victoria Larson',
    'address': '86789 Lisa Path\nKimberlyport, TX 77249',
},
    'key93095': 'value42486',
    'key76646': 'value73992',
    'key62342': 'value91715',
},
    {
    'id': 17527485048127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Sue Vance',
    'address': '3554 Reed Overpass Suite 600\nVanessamouth, NV 60346',
    'text': 'Present whole begin question. Argue far talk whom specific.\nCommercial huge child that. Enough onto training financial manage vote sense. Party ball organization book hit court trouble.',
    'email': 'tparks@example.net',
    'phone_number': '320.675.6158x56633',
    'json': {
    'name': 'James Anderson',
    'address': 'USS Alvarez\nFPO AA 46088',
},
    'key61195': 'value58895',
    'key98365': 'value69585',
},
    {
    'id': 17527485048137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Stephanie Kemp',
    'address': 'PSC 8530, Box 4182\nAPO AP 02996',
    'text': 'I community good pretty. Spring church throughout natural eat card. Mission practice home.\nChance media despite red. Science experience especially site can.\nWestern student carry.',
    'email': 'helen60@example.org',
    'phone_number': '(720)695-5771x9885',
    'json': {
    'name': 'Catherine Curtis',
    'address': '5260 Gonzales Divide\nKevinton, ME 98283',
},
    'key43881': 'value29382',
    'key18803': 'value71838',
    'key15796': 'value73306',
    'key8118': 'value95707',
    'key51129': 'value60559',
},
    {
    'id': 17527485048145,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Kelly Gonzalez',
    'address': '4101 Jesus Highway\nPort Staceymouth, MD 83003',
    'text': 'Key stock participant. Send another run we.',
    'email': 'wilsonheather@example.net',
    'phone_number': '+1-456-947-1666x14785',
    'json': {
    'name': 'Carla Arias',
    'address': '72705 Reyes Way Suite 166\nPort Jennifer, HI 42469',
},
    'key70022': 'value6025',
    'key34574': 'value5532',
    'key91427': 'value37068',
},
    {
    'id': 17527485048157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'John Williamson',
    'address': '07454 Eric Isle Apt. 690\nSouth Melissaport, VI 32355',
    'text': 'And sport begin value walk style agree wear. Take week hit moment each gun ready board.',
    'email': 'michaelbrewer@example.com',
    'phone_number': '554-583-4947x1451',
    'json': {
    'name': 'Haley Wolf',
    'address': '56733 Decker Ridge Suite 495\nMcconnellchester, NM 26729',
},
    'key5974': 'value57594',
    'key90590': 'value71901',
    'key46788': 'value84489',
    'key28984': 'value14525',
},
    {
    'id': 17527485048169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Brooke Abbott',
    'address': '15541 Scott Plaza\nEmilyville, WY 76142',
    'text': 'Dark page one soon sing one. Left live country unit. Seat site hot.\nParticularly off southern cultural. Cup see unit history yes. Tonight should operation site statement.',
    'email': 'geraldnewman@example.net',
    'phone_number': '302.294.4398',
    'json': {
    'name': 'Elizabeth Palmer',
    'address': '48569 Kristen Brook Suite 854\nArcherfort, MD 05699',
},
    'key97015': 'value31982',
    'key98783': 'value4881',
    'key12351': 'value50830',
    'key35546': 'value23728',
    'key54038': 'value90766',
    'key74926': 'value65356',
    'key10353': 'value54066',
    'key15650': 'value42647',
    'key16936': 'value78347',
    'key77272': 'value90776',
},
    {
    'id': 17527485048181,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Barbara Martin',
    'address': '0684 Laurie Stravenue Apt. 937\nGrantbury, MT 14734',
    'text': 'Prove culture bring focus current.\nPay leader image standard career. According wonder late compare add now.\nMovie event movie source. Vote despite current.',
    'email': 'aaron93@example.net',
    'phone_number': '210.211.0860x5094',
    'json': {
    'name': 'Jeremy Morrow',
    'address': '6126 Christopher Bypass\nPort Robertoside, TX 98490',
},
    'key81116': 'value51312',
    'key10323': 'value59860',
    'key40416': 'value22220',
    'key42344': 'value99345',
    'key96878': 'value48843',
},
    {
    'id': 17527485048191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Carlos Delacruz',
    'address': '61141 Davis Shoal\nSouth Heather, SC 51922',
    'text': 'Really design watch nor. More himself work father education. Base international should around yourself really success Mr.',
    'email': 'beckerlaurie@example.net',
    'phone_number': '765-394-6928x267',
    'json': {
    'name': 'David Burgess',
    'address': '980 Lisa Bypass\nStephanieshire, FL 69778',
},
    'key44981': 'value42864',
    'key99785': 'value49870',
    'key63898': 'value69876',
    'key86979': 'value67065',
    'key10647': 'value30307',
    'key76338': 'value55830',
},
    {
    'id': 17527485048202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Holly Patel',
    'address': 'USS Gonzalez\nFPO AP 33710',
    'text': 'Cup tough choice how information lawyer produce.\nSimply cold at hear audience result remain. Machine worry early enjoy federal.',
    'email': 'nolandavid@example.net',
    'phone_number': '3097160260',
    'json': {
    'name': 'Jeffrey Beard',
    'address': '33880 Joshua Key\nPort Lori, RI 55257',
},
    'key22101': 'value35034',
    'key59353': 'value34885',
    'key57373': 'value21253',
    'key13388': 'value31984',
    'key56462': 'value26509',
    'key93128': 'value92323',
    'key82866': 'value44520',
    'key50010': 'value9694',
},
    {
    'id': 17527485048212,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Carrie Jones',
    'address': '33181 Jessica Points Suite 059\nNew Barbaraview, PR 21579',
    'text': 'Detail however car pull. Sit similar kid create practice present make. Indicate fear respond.\nBag ten husband box. Require move message both natural.',
    'email': 'gmoore@example.org',
    'phone_number': '499-391-0777',
    'json': {
    'name': 'Amanda Newton',
    'address': '512 Donald Inlet\nEast Paigefurt, AS 62545',
},
    'key39906': 'value20535',
    'key14076': 'value36609',
},
    {
    'id': 17527485048223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Andrew Serrano',
    'address': '6678 Christopher Tunnel\nMaynardmouth, WY 67843',
    'text': 'Skin nature factor result. Hard important become oil least point program.',
    'email': 'pattywright@example.com',
    'phone_number': '898-749-7991x02072',
    'json': {
    'name': 'Cindy Blackwell',
    'address': '361 Brooks Trail Suite 323\nEast Jeanettetown, TN 47258',
},
    'key60874': 'value92413',
    'key46907': 'value16137',
    'key16145': 'value82801',
    'key96115': 'value17446',
    'key48006': 'value58462',
    'key39311': 'value96127',
    'key56548': 'value66276',
    'key9494': 'value45639',
    'key9124': 'value5193',
},
    {
    'id': 17527485048235,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Robert Smith',
    'address': '15225 Shelton Forks\nWest Robin, OK 77158',
    'text': 'Knowledge international key beat form own attorney. While protect ready rest thought Democrat.\nThere true bad relate daughter goal. Should unit billion everyone.',
    'email': 'ptorres@example.net',
    'phone_number': '373.583.8270x70634',
    'json': {
    'name': 'Aaron Walsh',
    'address': '10919 Lewis Junction\nSouth Lee, IN 34191',
},
    'key52513': 'value74472',
},
    {
    'id': 17527485048246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Brian Jacobs',
    'address': '4802 Donald Plains Apt. 191\nWest Susan, MS 24976',
    'text': 'Town experience among. Visit cause form remember middle message.\nWar television as these whose. Decide phone choice ball position.',
    'email': 'larryavila@example.com',
    'phone_number': '001-859-757-0518x029',
    'json': {
    'name': 'Shirley Warner',
    'address': '63789 Morgan Inlet Suite 176\nWalkerland, OR 35185',
},
    'key69016': 'value85993',
},
    {
    'id': 17527485048258,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Rachel Spencer',
    'address': '3378 Karen Neck Suite 758\nNorth Jeffreymouth, OR 26518',
    'text': 'Shake mention call four guy gas. Indeed help type message will little walk buy.\nCover table whom before gun remain risk. Skill tell hour might key cost little.',
    'email': 'timothythompson@example.net',
    'phone_number': '274.308.6650',
    'json': {
    'name': 'Eric Tapia',
    'address': '362 Kimberly Expressway Apt. 931\nHowardtown, VT 23479',
},
    'key89380': 'value72195',
    'key70770': 'value69666',
    'key97219': 'value28322',
    'key35184': 'value12791',
    'key33462': 'value21166',
    'key25652': 'value94120',
    'key81802': 'value64667',
},
    {
    'id': 17527485048269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Kyle Dunn',
    'address': '92901 Smith Vista\nPort Paula, NE 16490',
    'text': 'Also nearly million structure six him. Million man court consumer population any.\nThink probably American dream pay without identify. Station medical speech system meet. Deal manage energy town why.',
    'email': 'iyoung@example.net',
    'phone_number': '+1-451-810-7164',
    'json': {
    'name': 'Tiffany Ruiz',
    'address': '4337 Rachel Lodge\nPort Patricia, VI 36552',
},
    'key92457': 'value50724',
    'key8599': 'value31230',
    'key34832': 'value89008',
    'key18565': 'value15311',
    'key61144': 'value88768',
    'key42371': 'value51145',
    'key14145': 'value38610',
    'key13771': 'value10143',
},
    {
    'id': 17527485048280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Sheryl Nelson',
    'address': '301 Davis Trace\nSharonton, OK 80012',
    'text': 'Decade sense art system group.\nComputer unit dinner meeting. Gas story admit. Right idea benefit three. Follow unit thousand even feeling believe ten.',
    'email': 'xstewart@example.net',
    'phone_number': '(958)494-8360',
    'json': {
    'name': 'Jonathan Boyer',
    'address': '90685 Linda Squares\nSmithfort, WA 17932',
},
    'key15413': 'value11293',
    'key31155': 'value40854',
    'key45488': 'value33128',
    'key70902': 'value85267',
    'key90967': 'value56981',
},
    {
    'id': 17527485048291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Richard Floyd',
    'address': '591 Merritt Inlet Suite 065\nNorth Gary, MA 91127',
    'text': 'Explain arm himself thank offer improve.\nSource real make order shoulder amount push. Yourself magazine in natural throw suddenly.',
    'email': 'rileykendra@example.net',
    'phone_number': '(436)608-0017x389',
    'json': {
    'name': 'Michael Barker',
    'address': '6784 Morris Field\nMorrowside, RI 08874',
},
    'key44824': 'value3908',
    'key84489': 'value16026',
},
    {
    'id': 17527485048303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Michael Oconnell',
    'address': '2873 Hanson Overpass Apt. 135\nSouth Patricia, CT 16507',
    'text': 'Father me hear music black. Firm piece beyond leg hold sure.\nCivil yet hit whom effect. Here really expert choose few special activity offer.\nBody commercial of pattern.',
    'email': 'bartonsonya@example.com',
    'phone_number': '(645)716-8166',
    'json': {
    'name': 'Virginia Turner',
    'address': '79506 Jessica Parks Suite 653\nLake Joshuaville, NY 58884',
},
    'key47416': 'value48684',
    'key84510': 'value68517',
    'key75925': 'value59814',
    'key95621': 'value22843',
    'key18787': 'value37060',
},
    {
    'id': 17527485048314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Mariah Ware',
    'address': 'Unit 7186 Box 2083\nDPO AP 30721',
    'text': 'Yard buy deep after bag return. Tell become between support miss.\nBecome want wife everybody reveal clear. Amount nor discussion.\nGo write outside speech.',
    'email': 'charlesharris@example.org',
    'phone_number': '001-356-563-0708x12622',
    'json': {
    'name': 'Tommy Johnson',
    'address': 'Unit 3693 Box 4052\nDPO AP 93604',
},
    'key36262': 'value19572',
    'key2970': 'value16558',
    'key44619': 'value69056',
    'key89143': 'value3278',
    'key63635': 'value36351',
    'key58136': 'value597',
    'key48548': 'value70278',
    'key10011': 'value37659',
    'key78051': 'value4721',
},
    {
    'id': 17527485048322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Julie Hunter',
    'address': '7396 Michael Crossroad Suite 412\nJessicahaven, LA 69653',
    'text': 'Leave relationship book baby tonight while.\nStrategy prepare tonight. Try sing medical sometimes. Range myself dark when.',
    'email': 'david51@example.org',
    'phone_number': '001-235-680-6781x1824',
    'json': {
    'name': 'Sarah Owen',
    'address': '487 Farmer Shoals Suite 769\nRichardberg, AK 53826',
},
    'key22720': 'value42911',
},
    {
    'id': 17527485048332,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Rachel Thompson',
    'address': 'USS Robinson\nFPO AP 61984',
    'text': 'Nature indeed than only cultural door. Meeting fight image. Girl decade risk base better executive.',
    'email': 'michael22@example.net',
    'phone_number': '5708468826',
    'json': {
    'name': 'Molly Moore',
    'address': '733 Helen Canyon\nHansenport, PR 68470',
},
    'key55491': 'value62805',
    'key27887': 'value59307',
    'key81059': 'value55589',
    'key74317': 'value6822',
    'key41453': 'value40358',
    'key61733': 'value53774',
    'key9005': 'value19970',
},
    {
    'id': 17527485048341,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Brenda Flores',
    'address': '822 Philip Ports Apt. 323\nDurhamport, MH 30602',
    'text': 'Apply fear meeting already citizen.\nHit fund cultural serve. Would level line more improve work.',
    'email': 'teresahale@example.org',
    'phone_number': '7864971984',
    'json': {
    'name': 'David Newman',
    'address': '94474 Lisa Summit Apt. 414\nNew Richardbury, NE 88950',
},
    'key98666': 'value22066',
    'key24063': 'value40615',
    'key70933': 'value953',
    'key62423': 'value24381',
    'key71713': 'value47425',
},
    {
    'id': 17527485048352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Michael Kline',
    'address': '1813 Elizabeth Harbor\nRiggsstad, CO 99587',
    'text': 'Energy chair program drive fear author. Successful job glass. Present think third play nature quickly.\nMajor accept art. Kitchen top blue teach it could my.',
    'email': 'laurenhubbard@example.org',
    'phone_number': '001-850-796-6480x8463',
    'json': {
    'name': 'Joseph Gamble',
    'address': '06103 Sanders Meadow\nLindashire, WV 15470',
},
    'key75307': 'value99248',
    'key45900': 'value80490',
    'key9330': 'value91717',
    'key7506': 'value32259',
    'key30252': 'value94542',
    'key41461': 'value86241',
    'key81645': 'value86664',
},
    {
    'id': 17527485048364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Douglas Hall',
    'address': 'PSC 8792, Box 9554\nAPO AP 79477',
    'text': 'Couple would final real girl imagine education. Now best unit operation reality dog catch.\nUsually program respond. Probably cup herself sit. One protect real accept. Very believe need democratic.',
    'email': 'zdecker@example.net',
    'phone_number': '+1-658-215-6488x244',
    'json': {
    'name': 'Kevin Jenkins',
    'address': '212 Evans Via Suite 455\nNorth Danastad, PA 93074',
},
    'key60054': 'value15985',
    'key35514': 'value90801',
    'key63224': 'value26812',
    'key8707': 'value74991',
    'key16867': 'value29281',
    'key40123': 'value22340',
    'key37600': 'value50368',
    'key56596': 'value9094',
},
    {
    'id': 17527485048373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Leslie Johnson',
    'address': '379 Emma Road\nLake Robertburgh, VI 68817',
    'text': 'Plan southern night Mr story. Establish example other civil responsibility market service board. Start hold ever eye.\nGoal believe from wonder. Especially stand price sense.',
    'email': 'samuelsanchez@example.net',
    'phone_number': '653-483-0151x458',
    'json': {
    'name': 'Angel Fuentes',
    'address': '175 Jacob Centers Suite 785\nPort Jameshaven, OK 77122',
},
    'key39352': 'value86128',
    'key30846': 'value63896',
    'key20026': 'value79946',
    'key58445': 'value62816',
    'key48569': 'value14064',
    'key84748': 'value29720',
    'key53248': 'value13450',
    'key86326': 'value84993',
},
    {
    'id': 17527485048384,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Robert Romero',
    'address': '940 Morgan Manor\nHernandezburgh, MT 95565',
    'text': 'Eight land others field study wind spring. Take natural project mouth market. Finish win also meet here carry leave skin.',
    'email': 'granttammy@example.net',
    'phone_number': '232.580.7605x7738',
    'json': {
    'name': 'James Molina',
    'address': 'USCGC Gamble\nFPO AE 76163',
},
    'key90654': 'value37735',
    'key30421': 'value16226',
    'key64188': 'value68476',
    'key23132': 'value15270',
},
    {
    'id': 17527485048394,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Keith French',
    'address': '06728 Campos Canyon\nDavidsonland, LA 15249',
    'text': 'Event level point firm position response. Attorney often begin audience improve story.\nDecision support president. Tend hope only so.\nBody former up think dark.',
    'email': 'katrinacruz@example.org',
    'phone_number': '413.857.1691x9739',
    'json': {
    'name': 'Eric Arellano',
    'address': '7106 Rodriguez Lock Apt. 322\nChristensenview, CT 81381',
},
    'key26766': 'value3498',
    'key89140': 'value86620',
    'key10454': 'value81784',
    'key86566': 'value88345',
    'key45611': 'value34339',
    'key63818': 'value38831',
    'key36671': 'value46565',
},
    {
    'id': 17527485048407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Shane Rodriguez',
    'address': '88195 Erin Prairie Suite 850\nEast Crystal, NM 68333',
    'text': 'Become age collection no window indicate. Them mention anything threat describe third investment.\nStar no author society lot. Dog despite account plant them.',
    'email': 'patrick19@example.org',
    'phone_number': '(755)713-4504',
    'json': {
    'name': 'Terri Rodriguez',
    'address': '00668 Matthew Shoal\nNew Kristenmouth, MO 43633',
},
    'key99098': 'value13149',
    'key75389': 'value12611',
    'key59629': 'value34876',
    'key17215': 'value96458',
    'key90226': 'value76631',
    'key77725': 'value26890',
    'key71775': 'value26238',
    'key70940': 'value28304',
    'key24590': 'value15422',
},
    {
    'id': 17527485048417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Lisa Lopez',
    'address': '04132 Baker Mills\nMerrittland, AL 44883',
    'text': 'Give field air rest of at book these. Almost their perform TV rise why to past.\nCertain speech civil star simply. Public admit response. Week each Mr.',
    'email': 'olsondavid@example.com',
    'phone_number': '725.825.7896x93911',
    'json': {
    'name': 'Briana Hall',
    'address': '71407 Simmons Glens Apt. 993\nJoshuaville, NH 52677',
},
    'key82301': 'value62546',
    'key65304': 'value21927',
    'key6218': 'value48895',
    'key73226': 'value77975',
    'key859': 'value76141',
    'key47068': 'value48885',
},
    {
    'id': 17527485048428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Stacey Goodman',
    'address': '02949 Martinez Highway Apt. 959\nWilliammouth, PW 84723',
    'text': 'Remember such town onto hold. Scene federal put school on child wear. Religious guy watch me color.\nAbility assume front half consider pass. Military boy education modern computer someone purpose.',
    'email': 'joe77@example.org',
    'phone_number': '7623624542',
    'json': {
    'name': 'Justin Hunt',
    'address': '272 Huff Views Apt. 480\nLake Jamie, ME 35598',
},
    'key63401': 'value58215',
    'key18629': 'value28295',
    'key34078': 'value88179',
    'key17845': 'value57810',
    'key24780': 'value43953',
    'key31640': 'value19024',
    'key27288': 'value93825',
    'key99314': 'value38341',
    'key13361': 'value20726',
    'key84550': 'value48255',
},
    {
    'id': 17527485048440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Charles Rose',
    'address': '7961 Carter Prairie\nNew Lisaberg, SC 40666',
    'text': 'Argue debate seek part follow hot raise no. Than others member building live own like. Field floor bit hair arrive tough pick. Model every his system know arrive.',
    'email': 'campbelljustin@example.org',
    'phone_number': '662-667-1688',
    'json': {
    'name': 'Kathryn Taylor',
    'address': '5189 Michael Ridges\nFreybury, VT 81560',
},
    'key69186': 'value41218',
    'key20480': 'value21817',
    'key15497': 'value43316',
    'key43052': 'value75457',
},
    {
    'id': 17527485048451,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Charles Drake',
    'address': '006 Kenneth Station\nCraigland, VA 84331',
    'text': 'Risk create never pick suffer wide measure. Kind image lawyer. Nor join western stay floor.\nCareer whatever man technology. Example agent bring.',
    'email': 'obrienbilly@example.com',
    'phone_number': '+1-938-238-4043x6031',
    'json': {
    'name': 'Melissa Cochran',
    'address': 'Unit 6963 Box 8296\nDPO AE 09175',
},
    'key3546': 'value14679',
    'key89485': 'value19890',
    'key61588': 'value79973',
    'key13926': 'value64949',
},
    {
    'id': 17527485048460,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Joel Arroyo',
    'address': '2149 Samantha Mountain\nNorth Lynn, CA 10712',
    'text': 'Myself teacher this thing future. Defense society resource no your. Speech maintain less century whole environment teach.\nWould one speech class international. Close very account none.',
    'email': 'alanbridges@example.org',
    'phone_number': '949.397.7438x6616',
    'json': {
    'name': 'Susan Rosales DDS',
    'address': '241 Cory Underpass\nTheresaview, CT 64191',
},
    'key26911': 'value53996',
    'key19706': 'value60626',
},
    {
    'id': 17527485048470,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Joe Alvarado',
    'address': '99976 Brittany Lakes Suite 708\nGuzmantown, MN 54718',
    'text': 'Your entire create energy create.\nSend certainly social suffer individual.\nTraditional low store stage.',
    'email': 'lisawood@example.com',
    'phone_number': '+1-640-273-1754x297',
    'json': {
    'name': 'Kimberly Scott',
    'address': '113 Cook Expressway Apt. 548\nColinton, MT 23796',
},
    'key92248': 'value98876',
},
    {
    'id': 17527485048482,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jay Huynh',
    'address': '381 Benitez Landing Suite 661\nWest Garrettburgh, NE 63590',
    'text': 'Else education officer among adult. Member resource religious back.\nProfessional sometimes seek.',
    'email': 'ahill@example.org',
    'phone_number': '+1-807-664-8342',
    'json': {
    'name': 'Laurie Chavez',
    'address': '96895 Robert Points\nGarciaside, TN 54330',
},
    'key85271': 'value30873',
    'key14947': 'value89365',
    'key30566': 'value74394',
    'key84773': 'value91633',
    'key37043': 'value86686',
    'key39445': 'value16691',
    'key59829': 'value97292',
    'key47021': 'value29663',
    'key99070': 'value8605',
},
    {
    'id': 17527485048493,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Aaron Morrison',
    'address': '4942 Lori Circles\nHerringhaven, MO 73534',
    'text': 'Success movie four defense ever. Admit company structure doctor. National growth run many.\nSpring although need throughout. Box however hair large.',
    'email': 'patricia78@example.org',
    'phone_number': '001-308-567-4598',
    'json': {
    'name': 'Paige Scott',
    'address': '2892 Schwartz Pine\nDeanchester, AZ 45656',
},
    'key16064': 'value62664',
    'key770': 'value35442',
    'key23971': 'value38063',
    'key48224': 'value73639',
    'key30659': 'value59603',
    'key25034': 'value46985',
    'key88266': 'value36735',
    'key72343': 'value92394',
    'key99456': 'value46131',
},
    {
    'id': 17527485048504,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Jonathan Acosta',
    'address': '214 Morris Squares\nNorth Sharon, NJ 93646',
    'text': 'No author seat allow. Leg key study nice cultural be voice.\nOf represent of land build subject. Particularly everyone involve room share how production.',
    'email': 'qryan@example.com',
    'phone_number': '703.646.6087x749',
    'json': {
    'name': 'Carrie Reilly',
    'address': '9208 Howe Fork Apt. 131\nNew Candace, OR 31255',
},
    'key37614': 'value68236',
    'key63483': 'value77822',
    'key23622': 'value50299',
    'key73189': 'value69079',
    'key39671': 'value8117',
    'key20290': 'value16255',
    'key798': 'value22897',
    'key59544': 'value44697',
    'key79992': 'value21188',
},
    {
    'id': 17527485048515,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Michael Callahan',
    'address': '673 Freeman Squares Apt. 475\nKennethton, WI 43240',
    'text': 'Drop situation father important. Low next base of.\nDinner travel bank. Nature seem difficult see table hot become water.',
    'email': 'lisasmith@example.com',
    'phone_number': '(454)378-6886',
    'json': {
    'name': 'James Carter',
    'address': '2175 Bell Pike Suite 916\nSouth Curtis, VA 68718',
},
    'key19788': 'value48016',
    'key41686': 'value43280',
    'key20653': 'value27928',
    'key47615': 'value55022',
    'key14664': 'value31361',
    'key30429': 'value7740',
    'key7412': 'value18415',
    'key55421': 'value39611',
    'key27379': 'value79274',
},
    {
    'id': 17527485048527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Crystal Turner',
    'address': '434 Golden Camp Apt. 249\nJamesland, GA 60681',
    'text': 'Course American heavy fly rich. Actually great already same action third any. Usually town you maybe lose their.',
    'email': 'samanthasteele@example.net',
    'phone_number': '545.904.4720',
    'json': {
    'name': 'Gregory Gordon',
    'address': 'PSC 4495, Box 0609\nAPO AE 44366',
},
    'key74482': 'value89091',
    'key18178': 'value30267',
    'key32997': 'value25552',
    'key3900': 'value54758',
},
    {
    'id': 17527485048537,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Richard Frank',
    'address': '952 Smith Fields Apt. 999\nSouth Sarah, IL 62367',
    'text': 'Degree all mouth professional city. Them nation enjoy follow probably.',
    'email': 'nolanhannah@example.org',
    'phone_number': '(987)720-2077x0545',
    'json': {
    'name': 'Michelle Ramos',
    'address': '02650 Arnold Knoll Apt. 291\nSeanfort, IN 51788',
},
    'key6304': 'value61103',
    'key25713': 'value18704',
    'key41752': 'value39217',
    'key50784': 'value14093',
    'key2319': 'value8178',
    'key46258': 'value40151',
    'key20777': 'value96646',
    'key57547': 'value89885',
    'key80210': 'value66317',
},
    {
    'id': 17527485048548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Rebecca West',
    'address': '24912 Scott Orchard\nNorth Barbara, AZ 91954',
    'text': 'Difficult science stay most. Beyond image century detail order ball again. Nearly political poor reveal. Budget heart dog.',
    'email': 'gambleashley@example.com',
    'phone_number': '+1-664-596-9745',
    'json': {
    'name': 'Christie Christensen',
    'address': '26315 Christy Cliffs Apt. 097\nSouth Samantha, IN 50975',
},
    'key66988': 'value28437',
    'key37647': 'value40926',
},
    {
    'id': 17527485048559,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Matthew Tanner',
    'address': '57806 James Brook Apt. 641\nMackview, AZ 14505',
    'text': 'Particularly administration reduce civil rest. Candidate school subject be. Else audience here bed.\nEstablish adult organization thing wear hear measure. Artist just east phone near.',
    'email': 'longkellie@example.com',
    'phone_number': '+1-680-504-4195x06217',
    'json': {
    'name': 'Karen Lopez',
    'address': '5557 Joy Parkways Suite 983\nHensleyfurt, AK 57840',
},
    'key30095': 'value63295',
    'key72495': 'value74375',
    'key93221': 'value61778',
    'key99198': 'value56678',
    'key71500': 'value5763',
    'key40227': 'value19040',
},
    {
    'id': 17527485048571,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Marcus Solis',
    'address': '1391 Rick Mountain\nBrownchester, FL 02295',
    'text': 'Media family skill paper send concern voice. Than ever popular break here study.\nMeeting task if send situation. Know occur issue data. Eight hospital ball avoid bring half current.',
    'email': 'austinjarvis@example.net',
    'phone_number': '+1-214-683-3390x672',
    'json': {
    'name': 'Alvin Gallagher',
    'address': '432 Young Prairie\nKyleville, UT 30239',
},
    'key86211': 'value49807',
    'key93182': 'value84754',
    'key93584': 'value91568',
    'key5586': 'value87232',
    'key14631': 'value53957',
    'key58830': 'value69512',
    'key40196': 'value75468',
    'key54209': 'value15031',
    'key26206': 'value64911',
},
    {
    'id': 17527485048583,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Lance Taylor',
    'address': '6963 Christian Ridges\nPort Brianbury, IA 97688',
    'text': 'Really offer similar never know common pass mission. Big kid sport test space bring. Receive hot beat.\nSister play ten event body. Outside key oil under. Speak develop animal myself.',
    'email': 'jennaavila@example.net',
    'phone_number': '+1-522-763-0658x0696',
    'json': {
    'name': 'Franklin Harris',
    'address': '19020 Russo Prairie\nWest Kimberly, NJ 58260',
},
    'key32209': 'value11743',
    'key96396': 'value54225',
    'key93428': 'value434',
    'key68824': 'value33387',
    'key11729': 'value83356',
},
    {
    'id': 17527485048594,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Mrs. Christine Patterson',
    'address': 'USS Hernandez\nFPO AE 55907',
    'text': 'It theory physical analysis Congress. Stay image level represent real decade. Certain each knowledge much themselves difficult fear effort.',
    'email': 'kristiejohnson@example.com',
    'phone_number': '506.565.8056',
    'json': {
    'name': 'Jamie Brown',
    'address': '5490 Ryan Freeway\nSouth Lawrencefurt, DC 58256',
},
    'key55374': 'value65265',
    'key15433': 'value2667',
},
    {
    'id': 17527485048604,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Rachel Smith',
    'address': '68639 Gerald Place\nLake Raven, FL 41238',
    'text': 'Record surface five my husband bag nearly buy. Send art discuss window interesting significant.',
    'email': 'jessica97@example.net',
    'phone_number': '791-354-6207x9070',
    'json': {
    'name': 'Bryan Lewis',
    'address': '40302 Johnson Ferry\nEast Wendyshire, KS 40962',
},
    'key92817': 'value83428',
    'key72540': 'value53549',
    'key9160': 'value41555',
    'key31739': 'value54297',
    'key24160': 'value78139',
    'key26921': 'value54280',
    'key82765': 'value11300',
},
    {
    'id': 17527485048614,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Casey Jones',
    'address': '54332 Lindsey Manors Suite 254\nWyattborough, MA 49699',
    'text': 'In marriage growth thing. Easy world talk sit. Financial recognize school page.\nOrder growth yeah southern after experience film. Add also wide education college season surface.',
    'email': 'sarahjones@example.com',
    'phone_number': '331-758-5640x144',
    'json': {
    'name': 'Melissa Rice',
    'address': '201 Bonnie Hills\nLake Debbie, NV 06299',
},
    'key7183': 'value87109',
    'key30061': 'value27440',
    'key11779': 'value40851',
    'key82171': 'value64038',
    'key45441': 'value57022',
    'key12666': 'value19599',
    'key65596': 'value19652',
    'key28897': 'value78288',
},
    {
    'id': 17527485048625,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jennifer Lopez',
    'address': '0318 Rebecca Isle\nAlanchester, ME 62837',
    'text': 'Challenge human relate development necessary include bed threat. Human travel after great work.\nMrs continue themselves or garden. Environment claim organization life crime or.',
    'email': 'craig55@example.org',
    'phone_number': '001-259-913-9674x599',
    'json': {
    'name': 'Charlene Moore',
    'address': '910 Smith Fort\nPort John, RI 93972',
},
    'key81689': 'value20776',
    'key41482': 'value3471',
    'key12766': 'value79624',
    'key56867': 'value25172',
    'key16216': 'value42610',
    'key21905': 'value52762',
    'key96705': 'value48600',
    'key52537': 'value97594',
    'key17259': 'value22767',
},
    {
    'id': 17527485048636,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Andrew Dodson',
    'address': 'USCGC Powell\nFPO AA 71312',
    'text': 'Window collection early any into. Receive back participant buy age. Particular pattern worker anything case crime particularly. Mrs four cut behavior now type TV.',
    'email': 'vwheeler@example.org',
    'phone_number': '+1-480-846-5511x1073',
    'json': {
    'name': 'Cassandra Hull',
    'address': '40243 Kenneth Centers\nDavidland, WA 10269',
},
    'key30238': 'value3236',
    'key87157': 'value79814',
},
    {
    'id': 17527485048645,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Wyatt Lawson',
    'address': '9761 Smith Key\nEast Marciaburgh, NM 62461',
    'text': 'Involve police notice.\nIssue station actually. Whether within little take tell last sort own.',
    'email': 'seanwhite@example.com',
    'phone_number': '888-749-0718',
    'json': {
    'name': 'Richard Spencer',
    'address': '942 Jackson Plaza\nNew Pamelaberg, MA 94794',
},
    'key91046': 'value3372',
    'key19890': 'value39587',
    'key86387': 'value43284',
    'key22469': 'value4436',
    'key31757': 'value23005',
    'key84070': 'value14706',
    'key58728': 'value67446',
},
    {
    'id': 17527485048656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Marc Harris',
    'address': '14434 James Courts\nLake Richard, PW 90134',
    'text': 'Could social perform east light. Politics guy dark student pick former term major.',
    'email': 'fhansen@example.com',
    'phone_number': '918.726.6942',
    'json': {
    'name': 'Ralph Lowe',
    'address': '2585 Dennis Overpass\nSouth Marystad, AR 41995',
},
    'key92129': 'value81563',
    'key77900': 'value87819',
    'key11743': 'value48924',
    'key11382': 'value61909',
    'key91569': 'value75383',
    'key72443': 'value67950',
    'key63364': 'value69032',
},
    {
    'id': 17527485048666,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Rebecca Bates',
    'address': '37572 Sandra Terrace\nWest Jadeland, WY 04579',
    'text': 'Message add summer happen. Since few fight song business enter.\nControl near society guess. Within perhaps letter provide race resource different speak. Read through future yes occur stay.',
    'email': 'nathanielshields@example.com',
    'phone_number': '+1-283-508-8483',
    'json': {
    'name': 'Lindsey Velasquez',
    'address': '055 Tracey Underpass Apt. 277\nErinshire, OK 50881',
},
    'key22975': 'value38257',
    'key90107': 'value6340',
    'key38344': 'value13088',
    'key7746': 'value63667',
},
    {
    'id': 17527485048678,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'David King',
    'address': '89367 Matthew Lakes\nDavisville, DC 79491',
    'text': 'Car eye there own week hour. Into tonight fire water individual story such.\nBreak push take act professional tree control. Outside finish nice natural seat. When this amount.',
    'email': 'gloriaburton@example.org',
    'phone_number': '001-364-641-2618x3424',
    'json': {
    'name': 'Brendan Barber',
    'address': 'Unit 0889 Box 6046\nDPO AA 48652',
},
    'key69364': 'value34519',
},
    {
    'id': 17527485048687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Hailey Rodgers',
    'address': '591 Sonya Flat Suite 143\nNew Tiffanytown, PA 69786',
    'text': 'Difference morning baby country much. Four edge drug pattern. Authority play resource thing especially. List environmental suddenly experience leave myself voice.',
    'email': 'frollins@example.net',
    'phone_number': '418.689.9613x556',
    'json': {
    'name': 'Timothy Phillips',
    'address': '4340 Wendy Station\nHernandezstad, LA 11343',
},
    'key20186': 'value1689',
    'key85519': 'value41393',
    'key67205': 'value63602',
    'key65587': 'value3964',
    'key74061': 'value29361',
    'key26814': 'value75444',
},
    {
    'id': 17527485048698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Erin Holt',
    'address': '74012 Rodriguez Branch Apt. 198\nWest Elizabeth, NV 07226',
    'text': 'Our try scientist walk face. Three benefit professor production turn our. South boy mean every station somebody.',
    'email': 'stephanie46@example.org',
    'phone_number': '647-797-1908x593',
    'json': {
    'name': 'Melanie Davila',
    'address': '59217 Tate Springs\nEast Teresa, IL 92117',
},
    'key84012': 'value33091',
    'key19039': 'value18439',
    'key27003': 'value93717',
    'key5697': 'value90232',
    'key2211': 'value85160',
    'key76183': 'value53490',
    'key26944': 'value67763',
    'key38122': 'value20078',
},
    {
    'id': 17527485048708,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Paul Bartlett',
    'address': '9357 Jessica Wells Apt. 859\nJustinfurt, ND 91358',
    'text': 'Approach past serious whom read. Perhaps around contain leave.\nTell though act lawyer possible safe. Feel happen these option. Year church report adult responsibility hit.',
    'email': 'michael75@example.org',
    'phone_number': '2884981271',
    'json': {
    'name': 'Jeffrey Thomas',
    'address': '0443 Emily Court\nWilliamside, DE 16507',
},
    'key27919': 'value73808',
    'key63612': 'value53400',
    'key53877': 'value88690',
    'key85933': 'value87656',
    'key64351': 'value78504',
    'key34159': 'value32267',
    'key33705': 'value76954',
    'key87617': 'value52305',
    'key74867': 'value5144',
},
    {
    'id': 17527485048719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Derek Gonzalez',
    'address': '41186 Valdez Isle Apt. 975\nNorth Kimberlychester, VT 17907',
    'text': 'Develop success money nearly situation role never capital. Stuff country church need. Style point chair whatever record.\nSign use without beyond affect. Science kitchen about mention.',
    'email': 'danielaustin@example.com',
    'phone_number': '2515833502',
    'json': {
    'name': 'Martin Payne',
    'address': 'PSC 0788, Box 8664\nAPO AP 06587',
},
    'key36135': 'value65083',
    'key76733': 'value54854',
    'key98746': 'value70767',
    'key70256': 'value65227',
    'key76100': 'value35060',
    'key93509': 'value85733',
    'key24072': 'value76754',
    'key67239': 'value77519',
},
    {
    'id': 17527485048729,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Matthew Martinez',
    'address': '81874 Saunders Fork Suite 399\nKellerberg, FL 69857',
    'text': 'Impact charge imagine lot talk bank maybe.\nGlass kitchen describe move everybody century wall. As pass others address leg.',
    'email': 'gregory14@example.com',
    'phone_number': '001-522-808-5148x093',
    'json': {
    'name': 'Elizabeth Knox',
    'address': '446 Potter Valley Suite 552\nNoblemouth, AR 27284',
},
    'key73904': 'value96278',
    'key1759': 'value92399',
    'key64044': 'value23234',
},
    {
    'id': 17527485048739,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Danielle Allen',
    'address': '335 Wilson Via Suite 305\nKimberlyton, IL 82001',
    'text': 'Sell actually first arrive film. Down plan safe foreign see health. Window stuff young democratic course bar.',
    'email': 'jonathan88@example.org',
    'phone_number': '(393)704-7076x89420',
    'json': {
    'name': 'Jesse Austin',
    'address': '8620 Mindy Gardens Suite 889\nNew Dean, MA 13801',
},
    'key90416': 'value58800',
    'key72390': 'value49855',
},
    {
    'id': 17527485048750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Samantha Ward',
    'address': '2344 Benjamin Gardens Apt. 804\nSouth Raymond, WV 42922',
    'text': 'Same degree behind your interesting. Bag future late. Remember skin usually example less this recognize.',
    'email': 'allison82@example.net',
    'phone_number': '714.293.0190x148',
    'json': {
    'name': 'Thomas Lee',
    'address': '1399 Pamela Ville Suite 106\nGillland, VI 28466',
},
    'key61148': 'value32261',
},
    {
    'id': 17527485048760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Joshua Drake',
    'address': '567 Hale Route\nNew Jonathanstad, MT 41690',
    'text': 'Billion head mouth important. Rate move party pay experience.\nTough yeah far financial modern far common. Your party right great parent from fact.',
    'email': 'erindavis@example.com',
    'phone_number': '(411)531-9820',
    'json': {
    'name': 'Margaret Walker',
    'address': '945 Sharp Plains Suite 157\nMaldonadohaven, FM 41134',
},
    'key14023': 'value34997',
    'key56270': 'value57924',
    'key49978': 'value46224',
    'key32453': 'value11595',
    'key33413': 'value88360',
},
    {
    'id': 17527485048772,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Teresa Howe',
    'address': '2687 Jennifer Crossing Apt. 891\nSouth Jessicaport, NE 46673',
    'text': 'Current suffer recognize pass build Mrs budget however. After still herself join court pass.',
    'email': 'catherine53@example.net',
    'phone_number': '599-297-6428',
    'json': {
    'name': 'Wendy White',
    'address': '10603 Dennis Plain Apt. 434\nNew Brandon, AS 94907',
},
    'key53338': 'value70450',
    'key81904': 'value3838',
    'key35892': 'value88720',
    'key38100': 'value11218',
    'key38238': 'value61311',
    'key61952': 'value65550',
    'key23418': 'value68211',
    'key19341': 'value84947',
},
    {
    'id': 17527485048782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Karen Sullivan',
    'address': '10946 Conrad Creek Suite 203\nLamton, CO 34578',
    'text': 'State election growth scientist name. Major goal reflect outside.\nHim they truth rock represent personal idea. Accept future mission whom soon remember table response.',
    'email': 'jacob55@example.com',
    'phone_number': '539.243.9855x773',
    'json': {
    'name': 'Mary Alvarez',
    'address': '610 Jennifer Crossing Apt. 327\nSouth Joseph, CO 83371',
},
    'key44356': 'value73491',
    'key26540': 'value52005',
    'key89687': 'value18166',
    'key91720': 'value12738',
    'key77285': 'value28136',
    'key5236': 'value23946',
    'key87258': 'value55228',
    'key1642': 'value92261',
    'key83019': 'value57123',
    'key84755': 'value75283',
},
    {
    'id': 17527485048793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Benjamin Friedman MD',
    'address': '9164 Maldonado Drives Apt. 754\nLloydmouth, PW 48808',
    'text': 'Building choice serious appear. Stay bed land with owner plant imagine. Especially charge responsibility.',
    'email': 'christopher15@example.org',
    'phone_number': '8932697639',
    'json': {
    'name': 'Carl Higgins',
    'address': '797 Chapman Stream\nLake Whitneymouth, WI 47061',
},
    'key72788': 'value96566',
    'key61091': 'value77058',
    'key40910': 'value11156',
    'key44385': 'value18432',
    'key88546': 'value64441',
    'key51238': 'value15374',
},
    {
    'id': 17527485048807,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Elizabeth Brown',
    'address': '286 Michael Unions\nPort Kristiburgh, WV 72332',
    'text': 'Watch market for ability. Amount whole wind space mouth.\nFinancial piece manage seem everything energy. Network floor hard them down situation. Remember effect worker door.',
    'email': 'melissatate@example.com',
    'phone_number': '001-934-242-7068',
    'json': {
    'name': 'Jonathan Marsh',
    'address': '04189 John Island Apt. 932\nSteventown, GU 42488',
},
    'key64176': 'value49128',
    'key52218': 'value55005',
    'key34645': 'value38535',
},
    {
    'id': 17527485048820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Robert Abbott',
    'address': '331 James Ville\nNorth Samuel, WI 59718',
    'text': 'Wear spring six side partner somebody. Full during talk skin. Memory president fire artist.\nAmong nature dark hotel. Investment relationship direction man suddenly during yeah.',
    'email': 'ukim@example.com',
    'phone_number': '589.471.6108',
    'json': {
    'name': 'Keith Peterson',
    'address': '7321 Bruce Lane\nCaseybury, ME 29265',
},
    'key98325': 'value26714',
    'key13917': 'value52721',
    'key48740': 'value8815',
    'key42702': 'value46042',
    'key17967': 'value13249',
    'key80266': 'value77749',
    'key999': 'value20584',
    'key36509': 'value63917',
    'key26264': 'value81681',
    'key14899': 'value74199',
},
    {
    'id': 17527485048832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Gregory Schroeder',
    'address': 'USS Proctor\nFPO AE 83292',
    'text': 'Develop lead theory interesting ready number. Level some central firm professional himself that. Political pressure lose.',
    'email': 'melissalewis@example.com',
    'phone_number': '001-435-636-7269x4934',
    'json': {
    'name': 'Tara Pierce',
    'address': '36359 Stevens View\nNorth Donna, WV 17828',
},
    'key8890': 'value72900',
    'key55034': 'value3331',
    'key38830': 'value23744',
},
    {
    'id': 17527485048842,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Hector Scott',
    'address': '2232 Bradley Mount Suite 346\nSouth Jennifer, MN 71778',
    'text': 'More feel benefit believe. Training like catch political middle road part.\nHave visit total thus then thus agree. Late movement day character.',
    'email': 'jelliott@example.net',
    'phone_number': '001-616-946-2583x3072',
    'json': {
    'name': 'Jill Dudley',
    'address': '315 Carroll Estate Suite 573\nEast Kevinberg, MI 08463',
},
    'key15593': 'value61360',
},
    {
    'id': 17527485048854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Justin Jenkins',
    'address': '7710 Michael Springs\nEast John, PA 04361',
    'text': 'Sea talk rate good building begin. Wear question risk event.\nArea this usually common. Sister loss no town kid.',
    'email': 'kandrews@example.net',
    'phone_number': '+1-362-277-1209x99107',
    'json': {
    'name': 'Wesley Carpenter',
    'address': '90947 Ramirez Parks Suite 957\nDanielburgh, CO 01982',
},
    'key48316': 'value58779',
    'key87385': 'value64401',
    'key94602': 'value39797',
    'key15996': 'value357',
    'key96300': 'value16349',
    'key77523': 'value77486',
    'key24505': 'value30795',
},
    {
    'id': 17527485048865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Dennis Odonnell',
    'address': '94808 Kelly Haven Suite 930\nLake Michaelhaven, MP 09736',
    'text': 'Four decide goal where reduce power company. War center measure employee test stuff argue. Middle same career third year.\nHistory TV suggest. Out energy project end mother strong history hospital.',
    'email': 'cannonrobert@example.org',
    'phone_number': '998.765.4250x6562',
    'json': {
    'name': 'Veronica Rojas',
    'address': '6669 Silva Pike Suite 121\nHestermouth, AZ 58554',
},
    'key34012': 'value33993',
    'key47881': 'value47132',
    'key79655': 'value19496',
    'key84670': 'value69218',
    'key46499': 'value62247',
    'key65503': 'value5198',
},
    {
    'id': 17527485048877,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Ms. Shelby Wang DDS',
    'address': '647 Patrick Courts\nJohnsonfurt, VT 03478',
    'text': 'When speak reality our. Despite newspaper probably spring conference run political represent. Production consider base rich south important.',
    'email': 'april08@example.org',
    'phone_number': '001-536-998-4600',
    'json': {
    'name': 'Alec Gilbert',
    'address': '995 Andrade Mountain Apt. 830\nReyesfort, HI 78934',
},
    'key22965': 'value58435',
},
    {
    'id': 17527485048888,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Manuel Perez',
    'address': '0717 Felicia Street Suite 197\nMelindaburgh, VI 91235',
    'text': 'Contain kitchen soldier who safe design nor. Whether get draw bring during institution certainly.',
    'email': 'john93@example.org',
    'phone_number': '001-378-764-0499x606',
    'json': {
    'name': 'Lindsay Phillips',
    'address': '268 Bishop Port Apt. 806\nDiazchester, DE 94739',
},
    'key10981': 'value54030',
    'key35501': 'value40907',
    'key78209': 'value28950',
    'key98912': 'value68405',
    'key84348': 'value25385',
    'key31327': 'value68745',
    'key47833': 'value90077',
    'key26312': 'value95701',
    'key73450': 'value49043',
    'key49443': 'value89578',
},
    {
    'id': 17527485048899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Anthony Duncan',
    'address': '41616 Shannon Ferry Suite 783\nRobertshire, CO 70587',
    'text': 'Best fish pass night fly. Movement win simple boy.\nWrite rate bad so. Each hot or cell sign seek. Direction myself under check staff painting peace people.',
    'email': 'higginssusan@example.org',
    'phone_number': '001-786-960-1770',
    'json': {
    'name': 'Mr. Robert Adams',
    'address': '7692 Huffman Forge Apt. 267\nLindaport, GU 23999',
},
    'key1717': 'value59487',
    'key75643': 'value42715',
    'key16514': 'value13869',
    'key50646': 'value81129',
    'key80898': 'value41655',
    'key39265': 'value19462',
    'key92276': 'value28170',
    'key26307': 'value37188',
    'key71190': 'value53759',
    'key71738': 'value77012',
},
    {
    'id': 17527485048911,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Michael Adams',
    'address': '23209 Lopez Rapids\nMicheleview, NV 85678',
    'text': 'Lawyer voice crime including you explain inside. Management major and energy.\nProtect particularly staff thus nation smile light finish. Respond young assume answer whole together treat.',
    'email': 'phyllis55@example.org',
    'phone_number': '4209264739',
    'json': {
    'name': 'Alejandra English',
    'address': '26863 Mary Glen Suite 571\nEast Amberchester, MP 03904',
},
    'key44475': 'value53798',
    'key83807': 'value88425',
    'key8707': 'value96241',
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
    'RequestId': 'aff611a4-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_34_58_705003UdRExveH',
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
    'limit': 0,
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
    'RequestId': 'aff611a4-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_34_58_705003UdRExveH',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_limit[0]_1752748505.json')
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
    test = AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidLimit01752748505Json()
    test.run_tests()
