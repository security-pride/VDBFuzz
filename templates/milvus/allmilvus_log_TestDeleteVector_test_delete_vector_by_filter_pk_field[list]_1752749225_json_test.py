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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestDeleteVector_test_delete_vector_by_filter_pk_field[list]_1752749225_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[list]_1752749225.json"
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



class AllmilvusLogtestdeletevectorTestDeleteVectorByFilterPkFieldList1752749225Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[list]_1752749225.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[list]_1752749225.json"
        self.test_count = 10  # 测试方法数量
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
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
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
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
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
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
    'data': [
    {
    'id': 17527492091102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Karen Velez',
    'address': '8243 Davis Motorway Suite 339\nNew Tonyfort, WI 29959',
    'text': 'Forget suddenly town interest task around. Bank fund animal single professional clearly.\nMy blood floor fear region sometimes. Century democratic after factor father important.',
    'email': 'phillip26@example.org',
    'phone_number': '2928624085',
    'json': {
    'name': 'Travis Miller',
    'address': '18512 Earl Harbors\nJamesstad, VA 29858',
},
    'key35833': 'value19740',
    'key31683': 'value70817',
    'key50923': 'value13129',
    'key12822': 'value35021',
    'key76671': 'value49556',
    'key57503': 'value26154',
    'key85474': 'value33935',
    'key58166': 'value71635',
    'key71264': 'value2440',
},
    {
    'id': 17527492091117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Donna Bailey',
    'address': '7221 Morales Streets Apt. 194\nNew Megan, MA 00507',
    'text': 'Begin world say offer mind save travel. Open book result development nothing. Medical north machine through us.',
    'email': 'rnixon@example.org',
    'phone_number': '+1-941-417-4736',
    'json': {
    'name': 'Steven Sutton',
    'address': '0169 Knight Manor Suite 689\nNorth John, IL 82708',
},
    'key22187': 'value44697',
    'key2433': 'value59518',
    'key9811': 'value35704',
    'key92856': 'value52281',
    'key13060': 'value83849',
    'key45726': 'value28699',
    'key54417': 'value4329',
},
    {
    'id': 17527492091130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Patrick Guzman',
    'address': '02887 Carroll Camp\nKathrynland, KY 22685',
    'text': 'Result woman bad student. Three leader take crime.\nEvening accept defense American question figure. Organization sell page father.',
    'email': 'webbmegan@example.net',
    'phone_number': '458-270-5844',
    'json': {
    'name': 'Elizabeth Reed',
    'address': 'USNV Gordon\nFPO AP 77818',
},
    'key47243': 'value83833',
    'key94309': 'value88953',
    'key6066': 'value50948',
    'key36261': 'value34313',
    'key56637': 'value68233',
    'key50576': 'value35778',
},
    {
    'id': 17527492091141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Andrew Mccall',
    'address': 'USNV Brooks\nFPO AA 85109',
    'text': 'Huge actually student seat under sing. Type seat citizen avoid cover.\nTry seem movement themselves argue mission minute. Traditional about letter speak tend.\nPosition hear always remember purpose.',
    'email': 'joshua77@example.com',
    'phone_number': '(860)609-6081x5155',
    'json': {
    'name': 'Kayla Parker',
    'address': '4776 Christopher Island\nLivingstonville, SD 01450',
},
    'key72609': 'value20705',
    'key70431': 'value97487',
    'key5251': 'value78182',
    'key36901': 'value53646',
    'key48314': 'value65565',
    'key54760': 'value52059',
    'key67074': 'value81563',
    'key42790': 'value57842',
    'key8009': 'value69738',
},
    {
    'id': 17527492091151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Richard Cooke',
    'address': '362 Glover Throughway Suite 179\nSullivanchester, SC 67666',
    'text': 'Official probably experience doctor appear. Cold yeah however ahead hour along computer.',
    'email': 'eric47@example.net',
    'phone_number': '(772)460-5344',
    'json': {
    'name': 'Kimberly Brown',
    'address': '316 Erica Stravenue\nVanessaland, NV 80616',
},
    'key1504': 'value82337',
    'key17997': 'value84881',
    'key78208': 'value23967',
    'key15437': 'value53361',
    'key13386': 'value91144',
    'key2953': 'value64428',
    'key201': 'value65833',
    'key64272': 'value45835',
    'key26278': 'value12096',
    'key55261': 'value55326',
},
    {
    'id': 17527492091161,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Rhonda Turner',
    'address': '2658 Sandy Fort Suite 817\nSouth Richardton, VA 22078',
    'text': 'Before bag result past company office gun. Field cause no think hospital.\nIndividual side exactly prepare door. Above economy professional least natural property amount from.',
    'email': 'gina68@example.com',
    'phone_number': '949-491-0980x46677',
    'json': {
    'name': 'Rose Johnson',
    'address': '4977 Reed Burg Apt. 263\nLake Mary, PA 89543',
},
    'key1112': 'value40839',
    'key93596': 'value35773',
    'key6549': 'value16647',
    'key90070': 'value98381',
    'key1601': 'value39836',
    'key83646': 'value96156',
    'key37734': 'value11620',
    'key59950': 'value47818',
    'key72592': 'value5711',
},
    {
    'id': 17527492091172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Virginia Thomas',
    'address': '337 Hansen Lakes Apt. 223\nWest Jochester, NH 04499',
    'text': 'Performance attention three clear over tell edge. Series at design step medical. To almost arm own. Size field change begin adult law future third.',
    'email': 'chadmann@example.com',
    'phone_number': '001-598-551-4612x8184',
    'json': {
    'name': 'Laura Wright',
    'address': '88162 Hall Vista\nCarpenterchester, CT 55597',
},
    'key19832': 'value6921',
    'key43690': 'value64003',
    'key7707': 'value81847',
    'key16697': 'value49214',
    'key21049': 'value30080',
    'key46803': 'value40051',
    'key52041': 'value83647',
    'key45131': 'value60089',
    'key90896': 'value57134',
    'key62561': 'value62349',
},
    {
    'id': 17527492091184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Mallory Wong',
    'address': '0608 Douglas Station Apt. 985\nLake Darrenhaven, MT 36253',
    'text': 'Traditional agree large wish. Machine future public them city. Degree first growth for assume. Keep discussion try develop with.',
    'email': 'adam65@example.com',
    'phone_number': '001-923-370-6597',
    'json': {
    'name': 'Nancy Robbins',
    'address': '74529 Maynard Plains Suite 711\nEast Tyler, VA 25585',
},
    'key49938': 'value57224',
},
    {
    'id': 17527492091195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Misty Peterson',
    'address': '56009 Schultz Junctions Apt. 106\nEast Taylor, CT 96527',
    'text': 'Clear by color Republican rate future civil listen. Quality represent by later clearly music.',
    'email': 'randallholly@example.net',
    'phone_number': '809.786.6486x52780',
    'json': {
    'name': 'Timothy Herman',
    'address': '274 Taylor Orchard Apt. 145\nHarrisport, KY 21771',
},
    'key49893': 'value95881',
    'key21529': 'value13747',
},
    {
    'id': 17527492091207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Pamela Ponce',
    'address': 'USNV Norman\nFPO AE 18279',
    'text': 'Would act establish year fall pull seat say. Hot approach billion individual without you. Movie recent ability face.\nWar along prepare site. Manage office view debate.',
    'email': 'ariel40@example.net',
    'phone_number': '(624)212-9446',
    'json': {
    'name': 'Matthew Sellers',
    'address': '941 Laura Mill\nPort Penny, VT 19089',
},
    'key45051': 'value25378',
    'key32287': 'value50007',
    'key1327': 'value70085',
},
    {
    'id': 17527492091216,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Elizabeth Davis',
    'address': '94963 Richmond Skyway Suite 220\nHarmonview, WV 70074',
    'text': 'Lot the course very catch service large. Common item series speech later out.\nThen defense soldier section that throw. Bank themselves strong maybe explain can. Region think those suffer such.',
    'email': 'john85@example.org',
    'phone_number': '+1-721-758-6877x36190',
    'json': {
    'name': 'Andrea Lewis',
    'address': '3333 Susan Stravenue\nMillerborough, WV 52652',
},
    'key90317': 'value51927',
},
    {
    'id': 17527492091227,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Christopher Jacobson',
    'address': '16457 Arnold Heights Suite 109\nJenniferfort, MH 56272',
    'text': 'Simply appear rate of. Admit join science goal attorney choose. Time record strategy executive rate leg medical.',
    'email': 'robertoolsen@example.org',
    'phone_number': '773.511.3245',
    'json': {
    'name': 'Daniel Norris',
    'address': '84195 Bell Pine\nAlexland, AS 92001',
},
    'key52853': 'value41562',
    'key50842': 'value39351',
    'key61185': 'value28881',
    'key55193': 'value47193',
},
    {
    'id': 17527492091238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Andrea Frost',
    'address': '76049 Hanson Mountain\nLake Morganfort, MP 15596',
    'text': 'Yourself leader law technology issue significant six. Exist follow life ever local bring arm. Suggest million successful base.',
    'email': 'angela94@example.org',
    'phone_number': '413.529.9631x4028',
    'json': {
    'name': 'Steven Fry',
    'address': '1534 Carter Point\nLake Kelseyborough, GU 31996',
},
    'key31619': 'value22435',
    'key67305': 'value86129',
    'key40691': 'value57128',
    'key4860': 'value33662',
    'key57076': 'value88431',
    'key98973': 'value15832',
    'key93156': 'value8804',
    'key33584': 'value40939',
},
    {
    'id': 17527492091249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jessica Guerrero',
    'address': '386 Manning Estate Suite 532\nPort Angela, NC 17657',
    'text': 'Tell PM travel prevent simply enjoy research become. Vote eye short Mrs art. Check allow quite.\nNearly become then walk thought teacher. City bring call.',
    'email': 'steven37@example.org',
    'phone_number': '238-223-3261x9090',
    'json': {
    'name': 'Patrick Kirby',
    'address': '24971 Green Island Apt. 322\nEast Victoriaville, KY 08208',
},
    'key94105': 'value63484',
},
    {
    'id': 17527492091260,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'John Clarke',
    'address': '6180 Walker Lodge\nWrightburgh, GA 91580',
    'text': 'World seat us director. Animal current long model score list change sure. Race up guess garden none should stop.',
    'email': 'ijohnson@example.net',
    'phone_number': '001-992-462-0593',
    'json': {
    'name': 'Christina Johnson',
    'address': '9060 Jason Valleys Suite 051\nRowechester, NC 13864',
},
    'key19464': 'value91711',
    'key35991': 'value81307',
    'key87346': 'value34796',
    'key76757': 'value8339',
    'key62045': 'value52275',
    'key81675': 'value65565',
    'key50427': 'value36124',
    'key85570': 'value5876',
    'key83685': 'value15269',
},
    {
    'id': 17527492091271,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jasmine Caldwell',
    'address': '93464 Adkins Roads\nSouth Robert, NJ 72359',
    'text': 'Every cold it war whose. Management nation very arrive option force. True forget realize soon well industry commercial.',
    'email': 'jacksonadams@example.net',
    'phone_number': '441-607-3913',
    'json': {
    'name': 'Brian Myers',
    'address': '8374 Gentry Port Apt. 325\nPamelaborough, NJ 55385',
},
    'key41249': 'value19846',
    'key60592': 'value78724',
    'key52960': 'value76072',
    'key6730': 'value26274',
    'key49018': 'value40705',
    'key6328': 'value11257',
    'key94930': 'value85057',
    'key34817': 'value22523',
    'key42755': 'value83592',
},
    {
    'id': 17527492091283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Cathy Turner',
    'address': '2176 Robert Spring\nNew Ericview, RI 83162',
    'text': 'Early read night cause that kind professor. Perhaps prove growth whole. Partner begin make spend too join soon.',
    'email': 'maria94@example.net',
    'phone_number': '+1-677-991-9896',
    'json': {
    'name': 'Tyler Terry',
    'address': '37868 Hammond Ridge\nWest Rogerburgh, CO 75106',
},
    'key87004': 'value78259',
    'key52157': 'value81042',
    'key71919': 'value91687',
    'key15926': 'value89578',
    'key41511': 'value10186',
    'key34783': 'value4571',
    'key30146': 'value74201',
    'key56927': 'value39938',
},
    {
    'id': 17527492091293,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Charlene Curtis',
    'address': '454 Christopher Trafficway Apt. 242\nEast Pamelastad, NM 45020',
    'text': 'Special hot because conference way indeed take open. Walk side save. Century and candidate relate.\nPerhaps step key bill. Safe quite culture here maybe challenge agree.',
    'email': 'dylandavis@example.net',
    'phone_number': '(297)833-2709x5007',
    'json': {
    'name': 'Justin Graves',
    'address': '41161 Brenda Cove Apt. 667\nArmstrongberg, MA 76943',
},
    'key98859': 'value91372',
    'key85797': 'value94527',
    'key61303': 'value40922',
    'key65090': 'value98869',
    'key56432': 'value56292',
    'key93445': 'value52061',
    'key21682': 'value14289',
},
    {
    'id': 17527492091305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Denise Tucker',
    'address': '05664 Leach Extensions\nLake Matthew, VA 30754',
    'text': 'Consumer power save red five onto might over. Direction simply perhaps service decade maintain various. Plant herself high analysis behavior popular book.',
    'email': 'daniellevelez@example.net',
    'phone_number': '(911)203-7389x05040',
    'json': {
    'name': 'Kenneth Douglas',
    'address': '101 Taylor Unions Suite 019\nHayesshire, CT 12705',
},
    'key85183': 'value2423',
    'key28405': 'value77393',
    'key21529': 'value2146',
    'key41165': 'value45572',
    'key35566': 'value2409',
    'key57953': 'value55245',
    'key26808': 'value11786',
    'key12098': 'value89520',
},
    {
    'id': 17527492091317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Kimberly Bush',
    'address': '9165 Lewis Divide\nAnaside, MA 57674',
    'text': 'Local bit reason alone. Nothing put teach worker. Stage doctor approach where.\nCommunity politics hair arm former why. Shoulder then myself resource deal carry laugh.',
    'email': 'katelyn73@example.org',
    'phone_number': '+1-948-517-6477x8304',
    'json': {
    'name': 'Ian English',
    'address': '4174 Vazquez Ranch\nJoshuaton, MH 81648',
},
    'key89987': 'value58001',
    'key73149': 'value57035',
    'key76643': 'value46420',
    'key79330': 'value34774',
    'key4807': 'value87863',
    'key97689': 'value67030',
    'key77089': 'value74998',
    'key95236': 'value9894',
    'key1421': 'value21515',
},
    {
    'id': 17527492091327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Cory Cook',
    'address': '943 Edward Field Suite 952\nRichardsberg, IN 31959',
    'text': 'Pick learn training recognize serve able society per. Yourself around than wife. Work pick scientist evening.',
    'email': 'madison98@example.net',
    'phone_number': '(974)633-0770',
    'json': {
    'name': 'Samuel Klein',
    'address': '77245 Margaret Rest Suite 787\nWest Bethton, ME 13901',
},
    'key91149': 'value52411',
    'key41641': 'value33060',
    'key54894': 'value16601',
    'key71336': 'value90671',
    'key35873': 'value6480',
    'key48055': 'value70747',
},
    {
    'id': 17527492091337,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Judith Collins',
    'address': '5866 Swanson Land Suite 018\nJimenezview, KY 40370',
    'text': 'Artist performance look admit them strong else. Check body leader cause night card. Purpose war conference lose tax billion.',
    'email': 'maciashannah@example.com',
    'phone_number': '001-431-302-7326x349',
    'json': {
    'name': 'Jonathan Simpson',
    'address': '387 Horn Trail\nWest Amy, MP 69804',
},
    'key49423': 'value2433',
    'key56693': 'value94115',
    'key44941': 'value50511',
    'key39911': 'value229',
    'key93247': 'value23757',
    'key77886': 'value15909',
    'key4481': 'value85426',
    'key75448': 'value45461',
    'key9828': 'value86401',
},
    {
    'id': 17527492091349,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Melinda Mccarty',
    'address': '036 Gibson Tunnel\nJuliehaven, NJ 84641',
    'text': 'Type prepare fine go attorney later book. Must before form. Live actually us we throw book institution size.\nPopulation eye memory soon. Employee word physical simple ability grow national.',
    'email': 'zoe20@example.net',
    'phone_number': '+1-262-546-0041x282',
    'json': {
    'name': 'Crystal Butler',
    'address': '829 Jessica Prairie\nSimonfort, IL 88877',
},
    'key5652': 'value8197',
    'key88581': 'value74019',
    'key71083': 'value42506',
},
    {
    'id': 17527492091361,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Janice Petersen',
    'address': '3716 Brandon River Suite 534\nAllenstad, MH 79558',
    'text': 'Situation sometimes might property. Best law since matter nation. Reason miss kid quite.\nSenior subject him behavior. Week college central building. Really interview able finish good leader military.',
    'email': 'crawfordalyssa@example.net',
    'phone_number': '3415035533',
    'json': {
    'name': 'Patty Hurst',
    'address': '36440 Daniel Corners Suite 097\nJenniferburgh, MS 57776',
},
    'key18212': 'value66931',
    'key30656': 'value29411',
    'key85814': 'value15912',
    'key1109': 'value51074',
    'key46569': 'value56338',
},
    {
    'id': 17527492091372,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Rachel Davis',
    'address': '0774 Ramirez Lakes Suite 285\nLake Jasonville, PR 25311',
    'text': 'Night cell new approach. Interview computer shoulder.\nStreet stop Congress. Style special science Republican seek time explain between. Production produce marriage miss go compare.',
    'email': 'smithbrandon@example.net',
    'phone_number': '+1-771-275-5989',
    'json': {
    'name': 'Jeffrey Bauer',
    'address': '3779 Elizabeth Brook Apt. 608\nLake Carriestad, SC 02034',
},
    'key33280': 'value15702',
},
    {
    'id': 17527492091384,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Wayne Morris',
    'address': '0676 Sandra Mountain\nRandyfort, MN 35447',
    'text': 'Tv wonder will law style agent community. Challenge how live before each require these.\nPut medical card. Pm later toward take impact return. Soon garden activity draw.',
    'email': 'villegasglenn@example.com',
    'phone_number': '001-237-309-9879x48038',
    'json': {
    'name': 'Stephanie Cabrera',
    'address': '4131 Crane Creek Apt. 136\nJesseberg, VI 74931',
},
    'key13186': 'value22038',
    'key21652': 'value83383',
    'key98356': 'value61961',
},
    {
    'id': 17527492091395,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jennifer Smith',
    'address': '72789 Hanson Ramp\nGordonfort, MO 00525',
    'text': 'Station guy example. Learn baby amount news another section fill. According collection production similar concern behind choose.',
    'email': 'ronaldmoore@example.net',
    'phone_number': '200-399-8211x905',
    'json': {
    'name': 'Richard Howell',
    'address': '43662 Elizabeth Burg\nGarciastad, VI 69153',
},
    'key98104': 'value54330',
    'key12653': 'value42894',
},
    {
    'id': 17527492091406,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Robert Davis',
    'address': '2527 Cortez Circles\nWest Paul, OR 36824',
    'text': 'City support indicate. Your feeling fly back power. Rest threat and our beautiful cultural.',
    'email': 'allison58@example.org',
    'phone_number': '(676)856-9610',
    'json': {
    'name': 'Savannah Kennedy',
    'address': 'Unit 6828 Box 8250\nDPO AP 70040',
},
    'key1162': 'value30799',
    'key85135': 'value19321',
    'key42825': 'value54253',
    'key53051': 'value83940',
    'key80855': 'value56294',
},
    {
    'id': 17527492091415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Gabrielle Smith',
    'address': '664 Brown Stravenue\nSamanthaview, MI 67742',
    'text': 'Offer any level our. Exactly grow different general bed statement game speech. Risk this area popular its benefit.\nStudy realize once lay apply your main. Yard prevent crime base.',
    'email': 'derek64@example.com',
    'phone_number': '227.719.5315x06763',
    'json': {
    'name': 'Craig Stephens',
    'address': '26850 Wilkinson Ports Suite 331\nWest Jaredberg, LA 22945',
},
    'key98701': 'value77333',
    'key41338': 'value44567',
    'key79813': 'value73380',
    'key61437': 'value1453',
    'key88781': 'value50586',
    'key96672': 'value51237',
    'key25931': 'value49185',
},
    {
    'id': 17527492091426,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Elizabeth Humphrey',
    'address': '24464 Payne Parkways Suite 202\nTaylorshire, ME 15971',
    'text': 'Factor door improve stage. Nice difference theory surface claim simply. Evening lot under anyone occur thousand student.',
    'email': 'stevencook@example.com',
    'phone_number': '(755)763-0877x4901',
    'json': {
    'name': 'Danielle Mccoy',
    'address': '95728 Mcclure Club Suite 898\nNew Henry, NV 50772',
},
    'key42813': 'value13815',
    'key3645': 'value9151',
    'key79216': 'value76357',
    'key68145': 'value146',
    'key881': 'value44556',
    'key8937': 'value72211',
    'key54266': 'value92745',
    'key34554': 'value87030',
    'key87245': 'value54485',
},
    {
    'id': 17527492091437,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Mary Anderson',
    'address': '49622 Fowler Drives Suite 137\nWest Dustin, UT 02802',
    'text': 'Serve bring apply. Try seat edge mission discuss blue.\nPer music bar anyone debate page someone. Art tough world. Exist less tough enter.',
    'email': 'ewarner@example.org',
    'phone_number': '(730)347-2380x540',
    'json': {
    'name': 'Allison Williams',
    'address': '4462 Victoria Locks Suite 399\nEast Tina, NM 53501',
},
    'key52282': 'value78814',
    'key3732': 'value24377',
    'key64753': 'value27087',
    'key42437': 'value98929',
    'key61371': 'value1543',
    'key99886': 'value8074',
    'key68287': 'value53212',
},
    {
    'id': 17527492091448,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'John Valentine',
    'address': '4781 Jason Rest Apt. 137\nLake Michaelside, AZ 73115',
    'text': 'Because head describe leave build action woman protect. Free general enough give.',
    'email': 'lmueller@example.net',
    'phone_number': '5193776445',
    'json': {
    'name': 'Joshua Lopez',
    'address': 'USCGC Robertson\nFPO AE 81536',
},
    'key53634': 'value33133',
    'key70841': 'value31746',
    'key10493': 'value14935',
    'key10346': 'value92119',
    'key16407': 'value94026',
},
    {
    'id': 17527492091458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Emily Garcia',
    'address': '419 Christine Village\nCodyville, DE 58200',
    'text': 'Tree range market enough nice region. Card candidate seven consumer high.\nBest ability view heart. Sense professor behind ask strong say.',
    'email': 'qdavis@example.com',
    'phone_number': '+1-354-307-0041x60208',
    'json': {
    'name': 'Brandon Petersen',
    'address': '761 Diana Station\nNew Amy, FL 17471',
},
    'key25477': 'value16347',
    'key73860': 'value19942',
    'key83256': 'value51144',
    'key45008': 'value34870',
    'key91408': 'value35480',
    'key2940': 'value58482',
    'key47824': 'value76990',
    'key78644': 'value84626',
    'key36343': 'value32269',
    'key14456': 'value35810',
},
    {
    'id': 17527492091468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jessica Johnson',
    'address': '0865 Jose Summit Apt. 325\nSaramouth, IN 87873',
    'text': 'Situation thing write style break.\nNearly cup good bad memory do magazine. Her reflect suddenly know thousand maintain edge really.',
    'email': 'wellselizabeth@example.org',
    'phone_number': '+1-902-921-5002x724',
    'json': {
    'name': 'Alexander Ford',
    'address': '40090 Ward Path\nMeganstad, NY 26958',
},
    'key44250': 'value15953',
},
    {
    'id': 17527492091479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Kyle Curtis',
    'address': '08151 Alison Land Apt. 875\nFranklinville, SD 37673',
    'text': 'Tend process carry true employee party each them. Always anything partner away audience plan.\nPrevent remain would culture indicate. Radio pick provide to.',
    'email': 'mitchell86@example.net',
    'phone_number': '708.405.3861x494',
    'json': {
    'name': 'Charles Freeman',
    'address': '560 Derek Hill\nNorth Kevin, CA 65812',
},
    'key39622': 'value35343',
    'key12729': 'value54610',
    'key56073': 'value31275',
    'key44794': 'value24830',
    'key88598': 'value42260',
    'key55847': 'value93863',
    'key64215': 'value49287',
},
    {
    'id': 17527492091490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Michael Petersen',
    'address': '01435 Eric Underpass Suite 643\nWilsonborough, CT 99181',
    'text': 'Miss black stuff record. Before meet they surface lose picture current.\nTry door writer future analysis pretty we. Challenge fish source once hour.',
    'email': 'meghanwright@example.net',
    'phone_number': '(881)872-2579',
    'json': {
    'name': 'Michael Leach',
    'address': '3324 Kara Freeway\nSarahberg, DE 41709',
},
    'key48345': 'value57120',
    'key65039': 'value85401',
    'key11873': 'value47716',
    'key99789': 'value14520',
},
    {
    'id': 17527492091501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Benjamin Morris',
    'address': '43596 Choi Pike\nLake Tracy, NV 32094',
    'text': 'Congress because way beat represent many marriage particularly. Even activity its service.\nMillion put future knowledge the new group establish. Practice us life according where six moment.',
    'email': 'moralesedward@example.org',
    'phone_number': '623-378-6960x807',
    'json': {
    'name': 'Eileen Rodriguez',
    'address': '92346 Meghan Fields\nKaylahaven, GA 31886',
},
    'key85476': 'value29415',
    'key88451': 'value10372',
    'key28100': 'value57271',
    'key13993': 'value2467',
    'key45504': 'value43858',
    'key54461': 'value57664',
},
    {
    'id': 17527492091513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Patrick Bennett',
    'address': '548 Glenn Viaduct Apt. 621\nSouth Georgefort, NE 36093',
    'text': 'Arrive father consumer those difficult report.\nField small person hear financial cell. Mention agent PM thank force. In line affect receive whether.\nRealize protect else far have religious star.',
    'email': 'josefernandez@example.net',
    'phone_number': '371.880.1838x06733',
    'json': {
    'name': 'Nicole Garcia',
    'address': '07664 John Ridges\nAlberttown, WY 32112',
},
    'key37075': 'value54281',
    'key56257': 'value53138',
    'key39622': 'value86927',
    'key35236': 'value48332',
    'key98252': 'value64599',
    'key18731': 'value86889',
    'key66153': 'value99734',
},
    {
    'id': 17527492091524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Jason Murphy',
    'address': '82092 Holmes Terrace\nPort Christopher, SC 22263',
    'text': 'Word option short customer rule course. Address today rich movie too.',
    'email': 'roseelizabeth@example.org',
    'phone_number': '6295549369',
    'json': {
    'name': 'Kimberly Berry',
    'address': '9351 Erin Key\nEast Ronald, MS 90353',
},
    'key66257': 'value27423',
    'key50175': 'value46404',
    'key80677': 'value67276',
    'key19554': 'value36607',
    'key15884': 'value20573',
    'key68173': 'value55715',
},
    {
    'id': 17527492091535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jacqueline Lawson',
    'address': '809 Wells Unions Apt. 379\nKatrinaberg, VI 43255',
    'text': 'Only sign evening blue. Thing key image evidence cup must himself. Care open key page.\nComputer hear see realize. Street reveal Republican family threat.',
    'email': 'mdean@example.org',
    'phone_number': '001-536-561-1255x1389',
    'json': {
    'name': 'Christopher Trujillo',
    'address': '89076 Ward Forks Suite 222\nRomanberg, AZ 94886',
},
    'key90896': 'value84028',
    'key65722': 'value7335',
},
    {
    'id': 17527492091547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Stephanie Walker',
    'address': '26751 Duran Summit\nKennedytown, GU 76219',
    'text': 'Person spend kid above. Herself organization energy seven bar able.\nRecently wrong soon memory few. Environment stock pressure although all act. Recent entire accept writer movie sure more.',
    'email': 'jessicagray@example.org',
    'phone_number': '(293)622-4199x764',
    'json': {
    'name': 'Jesse Moore',
    'address': '31708 Kim Tunnel Suite 191\nSouth Thomas, NH 70855',
},
    'key70098': 'value90030',
    'key20627': 'value96042',
    'key12276': 'value94604',
    'key9326': 'value88004',
    'key72156': 'value11139',
    'key89425': 'value52839',
    'key85515': 'value30597',
    'key67164': 'value91504',
},
    {
    'id': 17527492091559,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Wyatt Peters',
    'address': '3291 Riley Run Suite 180\nPort Cameron, PA 54997',
    'text': 'Class moment same. Anything want any often role often conference hear.\nStand message sign blood. Entire travel black section present morning upon. Relate beyond business.',
    'email': 'dana38@example.com',
    'phone_number': '555-957-6081',
    'json': {
    'name': 'Michael Marks',
    'address': 'USS Spears\nFPO AP 29336',
},
    'key38281': 'value82344',
    'key37984': 'value94220',
    'key32653': 'value24652',
    'key80173': 'value18295',
    'key61534': 'value74149',
    'key47661': 'value56213',
    'key58704': 'value54436',
    'key26440': 'value26576',
},
    {
    'id': 17527492091568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Thomas Potts',
    'address': '8099 Salas Place\nMarthaland, NH 41328',
    'text': 'Blood on we turn beat. Member spend example Congress mind.\nSpecial work enough ago military may. Stay store it spend mean successful type.\nArticle move give card way. Suddenly nation item level rule.',
    'email': 'anne99@example.org',
    'phone_number': '334.446.7993',
    'json': {
    'name': 'Michelle Jones',
    'address': '52505 Phillips Ranch\nAtkinsmouth, IL 65180',
},
    'key76204': 'value66418',
    'key51139': 'value94500',
    'key93690': 'value60908',
    'key57058': 'value56928',
    'key73081': 'value86114',
    'key86433': 'value45464',
    'key63026': 'value71026',
    'key20652': 'value57848',
    'key78128': 'value15169',
},
    {
    'id': 17527492091579,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Ariana Hodges',
    'address': '18656 Hall Tunnel\nLake Anne, AS 61444',
    'text': 'Receive nature could job every. Able finish close score care him side school. Parent test indeed population loss business threat.',
    'email': 'arthur04@example.net',
    'phone_number': '001-313-563-0332x5442',
    'json': {
    'name': 'David Dominguez',
    'address': '8785 Cindy Station Suite 606\nJeremystad, KS 88906',
},
    'key29483': 'value93302',
    'key60572': 'value97327',
    'key70183': 'value3295',
},
    {
    'id': 17527492091589,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Zachary Sanders',
    'address': '80536 Steven Overpass\nFinleymouth, HI 15539',
    'text': 'Whose new fact make truth. Our baby plan plan hold defense near radio.\nWhole accept center push quality. Population career heart choice drive eat. Defense true method door choice game what so.',
    'email': 'sharoncollins@example.net',
    'phone_number': '001-770-921-0864',
    'json': {
    'name': 'Susan Scott',
    'address': '541 Joseph Garden\nJohnshire, WV 60947',
},
    'key54869': 'value97627',
    'key8507': 'value69517',
    'key87469': 'value85440',
    'key51324': 'value96141',
    'key17000': 'value4789',
    'key1024': 'value12140',
    'key60621': 'value59207',
    'key43379': 'value53849',
    'key89928': 'value7097',
},
    {
    'id': 17527492091600,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Michael Chapman PhD',
    'address': '88555 Michael Turnpike\nHoffmanton, OH 29390',
    'text': 'Your perform off agent process. Whether piece bank no history get generation everybody. Use or certainly simply someone sing.',
    'email': 'reynoldschristopher@example.org',
    'phone_number': '885.306.3924',
    'json': {
    'name': 'Dr. Michael Olson',
    'address': '38911 Lindsay Island\nValdezchester, CO 48386',
},
    'key96603': 'value50208',
    'key37408': 'value22126',
    'key35639': 'value69676',
    'key68541': 'value79102',
    'key1823': 'value83731',
    'key98728': 'value36408',
    'key49427': 'value94798',
},
    {
    'id': 17527492091612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Kimberly Reyes',
    'address': '86286 Dorsey Plain\nCourtneyhaven, MA 35406',
    'text': 'Later issue water surface child. Person easy everything.\nWoman difference during act west into. Nearly election unit well. Family summer ten determine above moment.',
    'email': 'gvilla@example.net',
    'phone_number': '+1-312-727-2684',
    'json': {
    'name': 'Jacqueline Daniels',
    'address': '648 Munoz Skyway\nSouth Andrestad, FL 85306',
},
    'key35235': 'value79842',
    'key63675': 'value53744',
    'key11292': 'value14624',
    'key2561': 'value75010',
},
    {
    'id': 17527492091623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Karen Sawyer',
    'address': '92554 Matthew Forest\nWest Frank, PA 68265',
    'text': 'Day worker challenge peace bring. Your who sign risk run again resource. Expect begin talk attention worker nation would.\nCan experience difference situation. Exactly political office fall.',
    'email': 'szhang@example.org',
    'phone_number': '631.631.5402x4757',
    'json': {
    'name': 'Dalton Miller',
    'address': '545 Jacob Prairie Suite 998\nLewisport, ND 61932',
},
    'key70924': 'value69708',
    'key45690': 'value91877',
    'key78035': 'value86945',
    'key86872': 'value17645',
    'key85603': 'value96124',
    'key11400': 'value79770',
},
    {
    'id': 17527492091634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Amanda Norton',
    'address': '0962 Johnson Divide\nLoriland, VT 92443',
    'text': 'Scene put likely green. Wide protect run key I tonight wind. Main media argue cause.\nWho way new public road. By far strategy government east join. Off price accept visit hour market.',
    'email': 'randyanderson@example.net',
    'phone_number': '345.627.6627x82880',
    'json': {
    'name': 'Brenda Walker',
    'address': '948 Jennifer Shore Suite 850\nClarkeport, NM 11706',
},
    'key61411': 'value68572',
    'key38011': 'value3646',
    'key40727': 'value71044',
    'key62611': 'value82331',
    'key94149': 'value5982',
},
    {
    'id': 17527492091646,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Jimmy Evans',
    'address': '3447 Jason Mall Apt. 082\nNew Deniseton, MI 99474',
    'text': 'Inside professional career make similar consumer art. Foot vote choose writer option open. Report one child detail physical style. Task hair clearly reach cut interesting husband bring.',
    'email': 'mary74@example.org',
    'phone_number': '(825)969-0620',
    'json': {
    'name': 'Matthew Herman',
    'address': '74320 English Brook Suite 799\nPort Tracey, FM 31564',
},
    'key70285': 'value78241',
    'key11157': 'value17238',
    'key44468': 'value9780',
    'key3696': 'value77397',
    'key96957': 'value50276',
},
    {
    'id': 17527492091656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Cynthia Finley',
    'address': '15133 Jason Canyon Apt. 971\nLoriville, MA 36644',
    'text': 'Listen fine key score in. Number into ever raise. Film capital great either avoid painting hope. Doctor clear arm year.',
    'email': 'odonaldson@example.org',
    'phone_number': '001-669-630-9405',
    'json': {
    'name': 'Sarah Lawrence',
    'address': '189 Kara Village Apt. 462\nJensenfurt, NY 77593',
},
    'key53374': 'value89321',
    'key48666': 'value40801',
    'key49397': 'value82439',
    'key627': 'value21383',
    'key69223': 'value15116',
    'key8859': 'value21403',
    'key87442': 'value25940',
    'key11446': 'value23483',
    'key36673': 'value46070',
},
    {
    'id': 17527492091666,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Casey Clark',
    'address': '686 Collins Village\nJenningsstad, DC 10655',
    'text': 'Create deal light two nothing parent town production. Threat without loss production drop identify.',
    'email': 'xwatkins@example.org',
    'phone_number': '001-496-992-4360x51315',
    'json': {
    'name': 'Andrew Cruz',
    'address': '060 Anthony Overpass Suite 815\nNorth Daniel, DE 83234',
},
    'key10865': 'value77305',
    'key5062': 'value85197',
    'key16782': 'value42086',
    'key18337': 'value14886',
    'key3518': 'value72774',
    'key59005': 'value80730',
    'key62514': 'value3385',
    'key66366': 'value8027',
},
    {
    'id': 17527492091677,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Andrew Guzman',
    'address': '230 Ian Place\nWest Jean, MD 16887',
    'text': 'Rise speak should land somebody. Whether will recently edge. Great fly also over.\nMother future want wife nearly. Month have focus field. Data car onto.\nBring rule Republican.',
    'email': 'christina51@example.org',
    'phone_number': '001-931-647-5791x15902',
    'json': {
    'name': 'Samuel Alexander',
    'address': 'USS Pena\nFPO AE 00916',
},
    'key42047': 'value18253',
    'key6988': 'value35600',
},
    {
    'id': 17527492091686,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Amy Schmidt',
    'address': '8832 Mitchell Track\nKochbury, MP 40524',
    'text': 'Account try national voice once response. Interesting work grow although herself purpose compare. Effect room against impact argue shake.',
    'email': 'dorothyhenderson@example.net',
    'phone_number': '886.303.5703x0240',
    'json': {
    'name': 'Terri Mcbride',
    'address': 'USS Gregory\nFPO AE 71835',
},
    'key14068': 'value22072',
    'key99989': 'value66009',
    'key9465': 'value23524',
    'key7365': 'value52161',
    'key93899': 'value11639',
    'key22875': 'value70925',
    'key98436': 'value15914',
    'key48854': 'value25985',
    'key28944': 'value97936',
},
    {
    'id': 17527492091696,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Angela Allen',
    'address': '64369 Sherri Cliffs Apt. 586\nMichaelshire, WY 05015',
    'text': 'Number art tough according. Just discover buy score deep result.\nBack try would mission. Decide after late friend. Them among sport we than consider rock.',
    'email': 'jacob08@example.net',
    'phone_number': '971.329.1098',
    'json': {
    'name': 'Marilyn Francis',
    'address': '6561 Waters Cape\nWest Erica, MT 02129',
},
    'key10165': 'value6858',
    'key8094': 'value79756',
    'key76403': 'value45309',
    'key42742': 'value56762',
    'key6480': 'value35271',
    'key22011': 'value15510',
    'key33131': 'value62984',
    'key92329': 'value19485',
    'key24636': 'value37335',
},
    {
    'id': 17527492091707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Kimberly Leonard',
    'address': '290 Spears Neck Suite 323\nNorth Jasonshire, OK 46067',
    'text': 'Follow movement type drug before. Past when begin western. Party seat structure simple child follow now.',
    'email': 'dominicgill@example.net',
    'phone_number': '480.687.2920x27837',
    'json': {
    'name': 'Barbara Howard',
    'address': '28168 Lopez Underpass\nVirginiabury, IL 44802',
},
    'key98495': 'value96192',
},
    {
    'id': 17527492091718,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Elizabeth Scott',
    'address': '581 Marcus Island\nNorth Amy, FL 23647',
    'text': 'Civil exist land include reach new small quite. Center first notice since plant. Compare may practice fact nature help science.',
    'email': 'whitematthew@example.net',
    'phone_number': '+1-895-648-2008x613',
    'json': {
    'name': 'Christina Martinez',
    'address': '4061 Stone Heights Suite 732\nWest Paula, MI 31192',
},
    'key36838': 'value76543',
    'key85532': 'value52469',
    'key94993': 'value5380',
    'key38332': 'value1931',
    'key61623': 'value52518',
    'key85924': 'value65848',
    'key24094': 'value73091',
    'key54464': 'value45008',
    'key67303': 'value32226',
},
    {
    'id': 17527492091730,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Shelly Coleman',
    'address': '865 Simmons Rapids\nNorth Kimberly, PA 72263',
    'text': 'Morning month true threat life. Mother pick court always. Month every art note.\nThem opportunity make. Deep party suffer bill. Keep peace any partner source student own.',
    'email': 'vfarmer@example.net',
    'phone_number': '5186871660',
    'json': {
    'name': 'Eileen Beltran',
    'address': '925 Shannon Field\nKevinside, NH 48805',
},
    'key15456': 'value61602',
    'key34102': 'value68287',
    'key86767': 'value9047',
    'key51690': 'value99414',
    'key50228': 'value65578',
    'key90404': 'value50257',
    'key39158': 'value82386',
    'key22998': 'value2648',
    'key85058': 'value97469',
},
    {
    'id': 17527492091741,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Donna Richardson',
    'address': '9029 Nguyen Plaza Suite 308\nHallstad, TN 34454',
    'text': 'Anyone me specific place actually stand pull. Wind more style impact organization maybe. About garden anyone.\nPublic require final bag any. Check finish fly hope ask if sort food.',
    'email': 'hernandezmarcus@example.com',
    'phone_number': '(460)257-5367',
    'json': {
    'name': 'Sean Phillips',
    'address': 'Unit 5971 Box 4879\nDPO AA 65028',
},
    'key54321': 'value96376',
},
    {
    'id': 17527492091751,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Theresa Hickman',
    'address': '256 Mendoza Station\nGrahamfurt, NV 84515',
    'text': 'Player six line property.\nForeign analysis respond commercial support. Day herself bag success soldier. Structure region many road anything public.',
    'email': 'urocha@example.com',
    'phone_number': '648-302-0631x728',
    'json': {
    'name': 'Zachary Weaver',
    'address': 'PSC 5365, Box 1325\nAPO AP 28358',
},
    'key6211': 'value41822',
},
    {
    'id': 17527492091760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Paul Rush',
    'address': '9584 Toni Mountains Suite 420\nGonzalesview, MH 26169',
    'text': 'Yourself speech director crime first morning. Fire skill region. Recognize may ago back various pretty.',
    'email': 'davidmartin@example.org',
    'phone_number': '538.303.8023',
    'json': {
    'name': 'Laura Lewis',
    'address': '571 Marc Drives Apt. 024\nEast Alicia, ME 06131',
},
    'key13348': 'value866',
    'key8918': 'value97641',
},
    {
    'id': 17527492091770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Seth Williams',
    'address': '8907 Garcia Rest\nToddfurt, WV 87029',
    'text': 'Student general meet wide yes. Have usually blood share suggest agreement. Food participant reveal really yourself without.',
    'email': 'bbryant@example.org',
    'phone_number': '652.617.9577x9153',
    'json': {
    'name': 'Cameron Harris',
    'address': '4789 Holt Corner Apt. 650\nNew David, GU 80470',
},
    'key69469': 'value47577',
    'key20611': 'value51181',
    'key42021': 'value70702',
},
    {
    'id': 17527492091781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Rodney Austin',
    'address': '09268 Rogers Vista Apt. 666\nWest Diana, WI 21789',
    'text': 'Cover name talk home me white test. Manage discussion almost up middle various.\nList today performance administration free machine. You source light leave them.',
    'email': 'jennifer12@example.net',
    'phone_number': '+1-374-588-1310x8771',
    'json': {
    'name': 'Juan Bush',
    'address': '5462 Walters Motorway\nReyesberg, MO 57996',
},
    'key91682': 'value62759',
    'key72079': 'value18416',
    'key65669': 'value9113',
    'key47366': 'value37841',
    'key5905': 'value67046',
    'key28284': 'value91169',
    'key16835': 'value13044',
},
    {
    'id': 17527492091792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Michael Johns',
    'address': '21428 Smith Roads\nNew Christopherfort, PA 18754',
    'text': 'Create tax each service friend dinner current nice.\nHot news concern owner act old hard. Ask management week class look.',
    'email': 'andersonsarah@example.net',
    'phone_number': '+1-297-488-5514x1511',
    'json': {
    'name': 'Stephanie Garner',
    'address': '1196 William Ports Apt. 918\nOscarbury, NC 21157',
},
    'key47262': 'value17137',
    'key99446': 'value10587',
    'key7155': 'value92976',
    'key98756': 'value37047',
    'key8284': 'value45609',
    'key74469': 'value30019',
    'key65849': 'value36955',
    'key64173': 'value82614',
    'key14792': 'value95574',
},
    {
    'id': 17527492091804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Thomas Fleming',
    'address': '4757 Wright Burgs\nNorth James, OR 47746',
    'text': 'Responsibility watch executive sign. Partner test power history person meet care.',
    'email': 'patrick15@example.org',
    'phone_number': '+1-783-689-5899',
    'json': {
    'name': 'Carmen Murray',
    'address': '83369 Heather Extensions Apt. 917\nRobinsonhaven, AL 33531',
},
    'key2944': 'value22256',
},
    {
    'id': 17527492091814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Daniel Yang',
    'address': '46184 Timothy Corner Suite 016\nMcintoshport, AS 44712',
    'text': 'Window test wall visit class more. Some lay present information travel last.\nAmount stay enough.\nDifficult wonder generation. Item join woman.',
    'email': 'dmiranda@example.com',
    'phone_number': '9063683740',
    'json': {
    'name': 'Ryan Harris',
    'address': '213 Miller View\nJasonhaven, NJ 80717',
},
    'key79365': 'value94082',
    'key46388': 'value73743',
    'key91489': 'value88812',
    'key66877': 'value75565',
    'key41639': 'value17544',
},
    {
    'id': 17527492091825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Sarah Miller',
    'address': '93704 Calhoun Mission\nMelissachester, KY 60617',
    'text': 'Hold western necessary. Its responsibility decision blue. Glass once ahead list continue vote. Word education common surface.',
    'email': 'tfrederick@example.org',
    'phone_number': '741-669-5049',
    'json': {
    'name': 'Dr. John Hardy',
    'address': '0809 Rivera Rest Suite 037\nNorth Devinmouth, AK 18113',
},
    'key96723': 'value96739',
    'key69672': 'value7522',
    'key7570': 'value26874',
    'key98146': 'value76660',
    'key80281': 'value20511',
    'key63360': 'value13353',
    'key95825': 'value15950',
},
    {
    'id': 17527492091836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Bryan Butler',
    'address': '0394 Frank Spur\nJuliafurt, IA 18201',
    'text': 'Prevent we Democrat occur. Rise food someone down. Nation training table so near firm themselves.',
    'email': 'joseph31@example.net',
    'phone_number': '001-429-554-7919x28066',
    'json': {
    'name': 'Hector Wood',
    'address': '41677 Hicks Flat Apt. 710\nKatherinefurt, CT 57249',
},
    'key37882': 'value1653',
    'key50349': 'value31981',
    'key60654': 'value18492',
    'key23016': 'value49944',
    'key7841': 'value98998',
},
    {
    'id': 17527492091847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Stephanie Torres',
    'address': '86672 Susan Stravenue\nWilsonfurt, NH 12116',
    'text': 'Husband finally foot produce. In no first. But dog light draw trade school animal. Population response wide growth front line public.',
    'email': 'sullivanclaudia@example.com',
    'phone_number': '+1-731-852-6544x6658',
    'json': {
    'name': 'Justin Taylor',
    'address': '674 Rebekah Port\nWest Matthew, LA 69285',
},
    'key1518': 'value99733',
    'key57747': 'value5729',
},
    {
    'id': 17527492091858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Alexandria Anderson',
    'address': 'Unit 8708 Box 6709\nDPO AP 76988',
    'text': 'My summer early today friend case. Rock kitchen car computer know. Agreement campaign law begin.\nPersonal how often sign camera you media. Night democratic serve adult just artist.',
    'email': 'jacob12@example.net',
    'phone_number': '914-831-1206x995',
    'json': {
    'name': 'Valerie Collins',
    'address': '404 Stacy Knoll\nWalkerfort, NE 79140',
},
    'key46454': 'value1327',
    'key94347': 'value78252',
    'key3145': 'value93852',
    'key19184': 'value2580',
    'key19260': 'value83218',
    'key81087': 'value77555',
},
    {
    'id': 17527492091866,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Dr. Edward Howard',
    'address': '52959 Green Lakes Suite 629\nEast James, ID 67270',
    'text': 'His knowledge office night himself force. Coach front along moment. Person least civil three speech account.',
    'email': 'valeriesantos@example.org',
    'phone_number': '484-211-9948',
    'json': {
    'name': 'Dr. Renee White',
    'address': '0135 Christensen Ville Apt. 926\nEast Amberstad, PA 17771',
},
    'key52143': 'value35372',
    'key14621': 'value44367',
    'key16979': 'value10261',
    'key90782': 'value71289',
    'key12101': 'value28927',
    'key60124': 'value2104',
    'key88053': 'value32964',
},
    {
    'id': 17527492091878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Danielle Steele',
    'address': 'PSC 9658, Box 1238\nAPO AP 73952',
    'text': 'Young add various past important. Item shoulder himself. Like view every evening.',
    'email': 'robertahanna@example.com',
    'phone_number': '(265)765-5193x4519',
    'json': {
    'name': 'Jennifer Thompson',
    'address': 'PSC 9333, Box 7744\nAPO AP 38375',
},
    'key85903': 'value4473',
    'key57879': 'value84231',
    'key26292': 'value94369',
    'key64796': 'value87459',
    'key25264': 'value38152',
    'key51775': 'value30664',
    'key64989': 'value76993',
    'key57412': 'value43945',
},
    {
    'id': 17527492091886,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Luis Davidson',
    'address': '893 Taylor Parkway\nEast John, MP 68412',
    'text': 'Report within last program. Believe lot increase across.\nCharacter century end might later leave war. Key suffer community garden although.',
    'email': 'josejohnson@example.com',
    'phone_number': '(540)684-5403',
    'json': {
    'name': 'Amber Reynolds',
    'address': '53894 Alexander Cliffs\nSanchezberg, MT 67899',
},
    'key18252': 'value54596',
    'key21399': 'value85419',
    'key73180': 'value14872',
    'key41732': 'value63857',
    'key68816': 'value84129',
    'key34567': 'value29335',
    'key90000': 'value56816',
    'key1847': 'value83020',
    'key13584': 'value5837',
},
    {
    'id': 17527492091897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Kimberly Cooper',
    'address': '727 Mia Club Apt. 522\nNorth Melanieport, IN 03355',
    'text': 'Grow guess yourself drive expect worker. Protect physical avoid indeed. Bag language less list myself.\nSame thousand over. Trial fast practice glass. Whole debate foreign matter mind.',
    'email': 'lperez@example.net',
    'phone_number': '(248)715-2862x419',
    'json': {
    'name': 'Ronald Lee',
    'address': '351 Katherine Common\nLake Melissa, MD 07229',
},
    'key6937': 'value22893',
    'key31962': 'value62407',
},
    {
    'id': 17527492091908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Denise Mcdonald',
    'address': '63099 Nicholson Brooks\nWest Linda, PW 84605',
    'text': 'Bag age position stage happy give. Audience east kind exactly every college although article. Billion program term return environmental whatever PM difficult. Both reflect number wall.',
    'email': 'woodanna@example.net',
    'phone_number': '243-298-7725x87217',
    'json': {
    'name': 'Gabriel Jones',
    'address': '9343 Dean Forest Apt. 782\nCynthiafurt, WV 07739',
},
    'key85866': 'value26395',
    'key14219': 'value57941',
    'key61313': 'value46213',
    'key94789': 'value88906',
    'key88843': 'value30003',
    'key69793': 'value12527',
    'key70742': 'value92332',
    'key9464': 'value81264',
},
    {
    'id': 17527492091919,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Timothy Jackson',
    'address': '306 Adam Mission Apt. 935\nSouth Christinafort, ME 93631',
    'text': 'Great both beyond type. Either their able enough everyone west. One bill mean eat son woman side.\nHalf service wait Democrat. Power in company may pay trade. Which less follow inside him respond.',
    'email': 'wortiz@example.net',
    'phone_number': '001-573-525-2135x70873',
    'json': {
    'name': 'Carol Harris',
    'address': '26110 Ward Road Apt. 983\nPort Maria, MH 86751',
},
    'key70975': 'value94227',
},
    {
    'id': 17527492091930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Ronnie Simmons',
    'address': '934 Colleen Knoll\nSouth Christopherland, MP 38153',
    'text': 'Record good subject participant property. Effort interesting tough give top. Wide nor security class toward. Close study administration study their project.',
    'email': 'jillrivera@example.com',
    'phone_number': '355-684-1042x0066',
    'json': {
    'name': 'Connie Hart',
    'address': '15600 Andrea Trail\nWest Paul, AL 53055',
},
    'key17418': 'value24283',
    'key11248': 'value78347',
    'key62003': 'value9356',
    'key11473': 'value80443',
    'key3710': 'value40271',
    'key70437': 'value41178',
    'key98266': 'value50693',
    'key59427': 'value12952',
    'key45565': 'value28823',
},
    {
    'id': 17527492091942,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Karen Roberts',
    'address': '38360 Andre Forks\nLake Cindyland, HI 91198',
    'text': 'Ago instead support research. Should economic day make.\nHere accept blood edge study trade century. Official strong safe career lead size.\nSave tell movie. Myself everybody yet method.',
    'email': 'ojohnson@example.com',
    'phone_number': '931-656-9205x44108',
    'json': {
    'name': 'Bonnie Martin',
    'address': '30157 Munoz Cliffs\nEast Annaland, UT 53988',
},
    'key986': 'value62613',
    'key55173': 'value90622',
},
    {
    'id': 17527492091953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Jennifer Adams',
    'address': '002 Kristen Inlet Suite 724\nHeatherburgh, VA 27272',
    'text': 'Together market board scientist outside forward. Rather vote option fly. Evening trade section break office fact attention.\nOnto great why.',
    'email': 'rmartin@example.org',
    'phone_number': '(856)919-1445',
    'json': {
    'name': 'Tracy Young',
    'address': '163 Rhodes Roads\nJonesville, NJ 83330',
},
    'key58974': 'value74637',
    'key61452': 'value61086',
    'key92598': 'value94558',
    'key29272': 'value3691',
    'key39639': 'value27001',
    'key27558': 'value44296',
    'key98906': 'value91280',
    'key92370': 'value17580',
    'key8747': 'value28995',
    'key10843': 'value53087',
},
    {
    'id': 17527492091964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Charles Terrell',
    'address': '5571 Christopher Burg\nEast Tiffany, FM 48170',
    'text': 'Speak sometimes fund customer reality. By customer value specific go difference. Medical list remain early world against debate quickly.',
    'email': 'littlesusan@example.org',
    'phone_number': '+1-808-299-4186x92316',
    'json': {
    'name': 'Jade Beasley',
    'address': '21109 West Mountain Apt. 810\nPort Andrefort, NC 69874',
},
    'key53266': 'value36520',
    'key13281': 'value31644',
    'key94863': 'value51926',
    'key58832': 'value38646',
    'key37140': 'value64226',
    'key50172': 'value22367',
},
    {
    'id': 17527492091975,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Alexandria Baxter',
    'address': '354 Jackson Terrace Apt. 953\nPort Lancefort, GA 16020',
    'text': 'Successful history actually apply real. Ok else manager.\nNothing owner measure evidence report heavy hope. Minute cold issue. Feeling after find try training often.',
    'email': 'bryan74@example.net',
    'phone_number': '554.856.5043',
    'json': {
    'name': 'Crystal Larson',
    'address': '074 Stanley Gardens\nMurphyfurt, TX 18218',
},
    'key47186': 'value7661',
    'key49339': 'value98105',
    'key33131': 'value47714',
    'key63683': 'value70077',
    'key54171': 'value85113',
    'key18306': 'value70806',
    'key74529': 'value17084',
    'key67878': 'value68736',
    'key75871': 'value83429',
},
    {
    'id': 17527492091986,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Ronald Johnson',
    'address': '2805 Claudia Parkways Apt. 574\nSouth Reginastad, AZ 04871',
    'text': 'Weight gas treatment employee produce prove. Small factor bag environmental store.\nJob especially blue he interest need would. Hope decision Mr far front set.',
    'email': 'qvasquez@example.com',
    'phone_number': '(688)865-5894x23213',
    'json': {
    'name': 'Paula Scott',
    'address': '7704 Solis Plains Suite 552\nLake Kyle, NE 91651',
},
    'key12274': 'value69127',
    'key490': 'value71613',
    'key50284': 'value33913',
    'key74902': 'value2537',
    'key40831': 'value41854',
    'key9594': 'value22425',
    'key62290': 'value48566',
    'key12560': 'value46585',
    'key75144': 'value54462',
},
    {
    'id': 17527492091997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Michael Floyd',
    'address': '3575 Powell Parkway Suite 965\nSouth Anitaburgh, WA 75589',
    'text': 'Fight item process leave foreign while however. Money address ground until want.\nSpring seat ok. Check in bring fast. What political alone important into eat.',
    'email': 'michaelharvey@example.org',
    'phone_number': '(936)982-0144x08866',
    'json': {
    'name': 'Deborah Lopez',
    'address': '997 Andre Viaduct Apt. 076\nJuliefurt, DE 90985',
},
    'key426': 'value5666',
    'key58852': 'value39032',
    'key33371': 'value55717',
    'key32000': 'value98638',
},
    {
    'id': 17527492092009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Julian Oconnell',
    'address': '97079 Vaughan Roads\nPort Katelyn, FM 07627',
    'text': 'Law free national one suddenly fast store. Growth everybody particular writer per. Quite help determine.\nIdea part true consider least put sing. Doctor improve produce believe data language side.',
    'email': 'ellislaurie@example.org',
    'phone_number': '(925)712-1273',
    'json': {
    'name': 'Joshua Cross',
    'address': '07256 Mary Plains Apt. 252\nAngelatown, IN 98180',
},
    'key19269': 'value81184',
    'key80618': 'value76399',
    'key32790': 'value54198',
},
    {
    'id': 17527492092020,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Sierra Martin',
    'address': '692 Tracy Courts Apt. 151\nElliottside, IA 19032',
    'text': 'Morning than us various. Half society according meet. Anyone majority bank not cause.\nAccept beyond price page newspaper option church.',
    'email': 'ljames@example.org',
    'phone_number': '482-721-5537x7898',
    'json': {
    'name': 'Veronica Wise',
    'address': '42001 Kayla Motorway Apt. 697\nLake Amanda, CA 18876',
},
    'key80900': 'value30625',
},
    {
    'id': 17527492092031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Jack Valdez',
    'address': '0828 Martin Extensions Apt. 911\nSouth Sandra, TX 88424',
    'text': 'See lawyer decade. Term scene risk office series public inside. Concern station opportunity artist board start piece.\nLive will pattern often. Since respond style case opportunity.',
    'email': 'calvinsharp@example.net',
    'phone_number': '348.379.9751x97571',
    'json': {
    'name': 'Gregory Green MD',
    'address': '637 Miller Cliff\nBrittneyborough, NV 40922',
},
    'key66792': 'value76654',
    'key67358': 'value78730',
    'key37249': 'value88990',
},
    {
    'id': 17527492092043,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Travis Cabrera',
    'address': '398 Johnson Islands Suite 366\nWest Amberfort, IN 59270',
    'text': 'Unit surface the food imagine off. Street fund security nature work kid. Benefit or describe per ready determine. Pull floor job approach wait want effort.',
    'email': 'johnodonnell@example.com',
    'phone_number': '001-628-759-7255x099',
    'json': {
    'name': 'Kenneth Coleman',
    'address': '384 Rowe Manor Apt. 097\nWest Chad, DE 90451',
},
    'key16195': 'value29851',
    'key74502': 'value76106',
    'key52125': 'value95381',
},
    {
    'id': 17527492092054,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Emily Walters',
    'address': '0297 Denise Plains Apt. 645\nChristopherberg, CT 97682',
    'text': 'Whole service Congress student. Body your level event south.\nLittle age us current argue air. Who court teacher recently offer training.',
    'email': 'collinsamy@example.org',
    'phone_number': '+1-531-310-6007x7485',
    'json': {
    'name': 'Jason Fox',
    'address': '371 Neal Crest Suite 793\nSouth Mackenzie, UT 07102',
},
    'key54206': 'value53573',
    'key59999': 'value10648',
    'key20977': 'value56218',
    'key60754': 'value49535',
    'key92690': 'value26248',
    'key46255': 'value29338',
    'key18304': 'value83907',
},
    {
    'id': 17527492092066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michael Welch',
    'address': '393 Johnson Views Apt. 657\nLongburgh, MN 13291',
    'text': 'Interview once add history. Mother arrive defense. Be worker care often these.',
    'email': 'johnmcclain@example.net',
    'phone_number': '920.395.0541x66787',
    'json': {
    'name': 'Jessica Byrd',
    'address': '973 Alexis Overpass\nEast Nancyfurt, WY 11598',
},
    'key13930': 'value6415',
    'key58476': 'value20368',
    'key7740': 'value85193',
    'key86283': 'value1222',
    'key43909': 'value5263',
    'key84070': 'value60964',
    'key19186': 'value1109',
    'key54728': 'value36420',
    'key10': 'value35265',
    'key35193': 'value83971',
},
    {
    'id': 17527492092078,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Michael Lee',
    'address': '9566 Craig Summit Apt. 549\nBlackmouth, WA 56575',
    'text': 'Firm after memory quality. Move how one yourself. Hundred carry put father professional game.\nUnderstand near nothing want source with guess. Stay over full bad prevent.',
    'email': 'riverakimberly@example.net',
    'phone_number': '(224)547-8942x52180',
    'json': {
    'name': 'Melanie Harrison',
    'address': '015 Jenkins Loop Suite 356\nRushbury, MO 03014',
},
    'key52200': 'value69775',
    'key88063': 'value90543',
    'key81807': 'value58042',
    'key78136': 'value57788',
    'key74492': 'value39684',
    'key54386': 'value89991',
    'key12948': 'value11752',
},
    {
    'id': 17527492092090,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Deborah Ortiz DDS',
    'address': '55864 Shannon Mall\nNew Bryan, SD 99182',
    'text': 'Rise us on. Still family behind mother. Police current relationship role senior health certainly.',
    'email': 'andersonpatricia@example.com',
    'phone_number': '784.505.4765x7848',
    'json': {
    'name': 'Brian Adams',
    'address': '1911 Cook Lock Suite 598\nJamesport, SD 58948',
},
    'key28226': 'value403',
    'key74214': 'value51930',
    'key56530': 'value15418',
    'key89225': 'value36036',
    'key87022': 'value40674',
    'key51560': 'value73277',
    'key50168': 'value44476',
},
    {
    'id': 17527492092101,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Michael Rodgers',
    'address': 'Unit 6986 Box 4036\nDPO AA 06008',
    'text': 'Beat chance professor defense usually position of set. Movement radio without. Because Congress how involve notice program thousand. Sister material account chair.',
    'email': 'kroberts@example.net',
    'phone_number': '(773)309-0465',
    'json': {
    'name': 'Gregory Mcdonald Jr.',
    'address': '2693 Smith Stream\nNew Mitchellburgh, AS 24857',
},
    'key83166': 'value33223',
    'key74405': 'value98441',
    'key68806': 'value54133',
    'key13487': 'value87324',
    'key66576': 'value86348',
    'key3825': 'value4257',
},
    {
    'id': 17527492092110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Eric Guerrero',
    'address': '437 Wagner Pine Suite 873\nMosesborough, VA 95161',
    'text': 'Born simple stop strong. Four fine particularly call. Industry run such or test understand.\nConsumer boy what yard region. Choose note action Democrat policy.',
    'email': 'lwilliams@example.com',
    'phone_number': '+1-599-735-6451x7637',
    'json': {
    'name': 'Madison Valenzuela',
    'address': '057 Huffman Radial Suite 882\nNorth Vernonfort, WI 01102',
},
    'key50566': 'value43847',
    'key21258': 'value46959',
    'key25480': 'value10429',
    'key19774': 'value18444',
    'key3303': 'value8082',
    'key4735': 'value8992',
},
    {
    'id': 17527492092121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Wanda Mahoney',
    'address': '5464 Wayne Turnpike\nLake Thomasmouth, FL 09562',
    'text': 'Field sit hear life beat without degree million. Follow risk shoulder voice yes name audience special.\nInside water to Republican commercial some practice. Chance budget lay which end ok do.',
    'email': 'jenna08@example.org',
    'phone_number': '280.982.3266',
    'json': {
    'name': 'Sean Fields',
    'address': 'PSC 6812, Box 6193\nAPO AA 61694',
},
    'key24204': 'value31680',
    'key76390': 'value63606',
    'key39361': 'value96560',
    'key55751': 'value18004',
    'key48659': 'value19031',
},
    {
    'id': 17527492092130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Eric Yoder',
    'address': '601 David Shoals Apt. 098\nGranttown, GU 60366',
    'text': 'Vote student order rather level large final.\nPeople place thousand sometimes through. Bill clearly cold writer. World everybody back leader according reveal table.',
    'email': 'karenjohnson@example.com',
    'phone_number': '5203321137',
    'json': {
    'name': 'Hannah Harris',
    'address': '6271 Caroline Inlet\nScottborough, IL 77399',
},
    'key55113': 'value23154',
    'key2043': 'value71111',
    'key2712': 'value85486',
    'key99504': 'value5596',
    'key4476': 'value72497',
    'key55493': 'value81626',
},
    {
    'id': 17527492092141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Juan Duncan',
    'address': 'Unit 7840 Box 8286\nDPO AP 95137',
    'text': 'Hour different small. Yourself go forget simply memory home item theory.\nLikely provide television three.\nRemember home build mention college cover say science.',
    'email': 'campbellross@example.net',
    'phone_number': '(852)926-9908x394',
    'json': {
    'name': 'Damon Gonzalez',
    'address': '045 Sara Greens Apt. 091\nKellyborough, OR 98533',
},
    'key27704': 'value72481',
    'key2359': 'value33635',
    'key14105': 'value86572',
    'key45346': 'value99035',
    'key16423': 'value73242',
    'key46363': 'value35119',
    'key87064': 'value9239',
    'key59492': 'value7521',
},
    {
    'id': 17527492092151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Kimberly Harris',
    'address': '98924 Edwards Overpass Suite 809\nEast Alejandroshire, NY 86989',
    'text': 'Able subject chance song sign together least. Above and personal wait manager Democrat.\nMinute but network body raise yard southern. Loss he current serious believe.',
    'email': 'paulaporter@example.net',
    'phone_number': '9819570826',
    'json': {
    'name': 'Matthew Hunter',
    'address': '70413 Kevin Garden\nWest Stephenport, WI 11973',
},
    'key80299': 'value36408',
    'key41075': 'value12346',
    'key72020': 'value74724',
    'key20336': 'value47152',
    'key53743': 'value6576',
    'key94177': 'value71613',
},
    {
    'id': 17527492092162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Andrea Gonzalez',
    'address': '413 Kimberly Motorway\nEast Madisonmouth, NH 43679',
    'text': 'Husband police of act skill eight hair.\nTotal nation whether likely. Measure should those yes much. Financial education reach most detail yourself second.',
    'email': 'megan72@example.org',
    'phone_number': '(293)733-5068x43194',
    'json': {
    'name': 'Cassandra Rogers',
    'address': '10061 Jason Locks\nNorth Laurachester, PR 67214',
},
    'key8433': 'value68616',
},
    {
    'id': 17527492092171,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Nicholas Morris',
    'address': '8007 Smith Squares\nWoodsport, MH 15532',
    'text': 'Whole resource old edge. Enjoy second wall article.\nMention remember work. Success section live pay animal hope.\nEither threat situation magazine. Then pattern model else ask.',
    'email': 'joyhernandez@example.net',
    'phone_number': '503-527-2679x75689',
    'json': {
    'name': 'Susan Copeland',
    'address': '07651 Jacob Keys Suite 367\nKristahaven, NE 46056',
},
    'key99999': 'value20653',
    'key24406': 'value1300',
    'key59199': 'value39259',
    'key35226': 'value88912',
    'key43507': 'value23230',
    'key24485': 'value7363',
},
    {
    'id': 17527492092182,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Kelsey Bullock',
    'address': '09556 Espinoza Road\nWest Alexisville, GA 69029',
    'text': 'Across detail sort. Investment Mr stage television thing.\nCup type family chance. Study wall month education sound.',
    'email': 'brownjessica@example.com',
    'phone_number': '(726)826-2825',
    'json': {
    'name': 'William Nelson',
    'address': '530 William Road Suite 698\nRiveraberg, MA 27986',
},
    'key54602': 'value1833',
    'key89017': 'value67195',
    'key50945': 'value41911',
},
    {
    'id': 17527492092194,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Carol Peterson',
    'address': '95074 Joshua Walks Apt. 249\nJoseview, CO 95349',
    'text': 'Baby goal officer no quality. Question trial contain sea behind what. Bed or expect day if.\nFace wall play opportunity. Research begin community. Matter program tend everyone.',
    'email': 'snichols@example.com',
    'phone_number': '(408)585-0254',
    'json': {
    'name': 'Jon Bryant',
    'address': '74896 John Street\nPattersonport, NM 20722',
},
    'key48608': 'value32138',
    'key80661': 'value26626',
    'key61001': 'value21581',
    'key98247': 'value64688',
    'key7671': 'value68573',
    'key37269': 'value76898',
},
    {
    'id': 17527492092205,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Kenneth Valentine',
    'address': '55222 Daniel Route\nNew Tamarafort, ID 10104',
    'text': 'Know would be watch. Past next figure.\nMrs without site lead medical within. Physical explain remember. Heavy million attorney recently.',
    'email': 'mooregary@example.net',
    'phone_number': '815.421.8030x771',
    'json': {
    'name': 'Heather Briggs',
    'address': '689 Donna Islands\nWhiteshire, PW 65637',
},
    'key62254': 'value28667',
    'key15180': 'value27018',
    'key80494': 'value57180',
    'key22187': 'value6613',
    'key79018': 'value29703',
    'key9017': 'value39390',
},
    {
    'id': 17527492092217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Ryan Maxwell',
    'address': '0925 Jerry Unions\nHuntshire, NY 94429',
    'text': 'Why name conference institution hotel material town. Easy place such provide interview. Eat ready how between. Against society PM product.\nMaintain tonight sing table. Skin power good bill just.',
    'email': 'williamslauren@example.com',
    'phone_number': '(538)281-8582',
    'json': {
    'name': 'Ryan Ochoa',
    'address': '32170 Johnson Key\nNorth Ricky, CT 01559',
},
    'key51745': 'value99811',
    'key75867': 'value45228',
    'key40103': 'value86087',
    'key20879': 'value75999',
    'key27363': 'value25696',
    'key70250': 'value7785',
},
    {
    'id': 17527492092228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Jason Sanders',
    'address': '093 Tonya Loaf Suite 483\nLake Johnton, MH 94858',
    'text': 'Agency fast century. Even whole back new election. Star free road discussion four realize.\nEverybody TV young apply social edge. Sort team girl entire feeling.',
    'email': 'brian77@example.com',
    'phone_number': '001-688-871-9432x693',
    'json': {
    'name': 'Janice Hull',
    'address': '5579 Wilson Walk\nJustinton, KS 29572',
},
    'key67727': 'value56963',
    'key90082': 'value66291',
},
    {
    'id': 17527492092239,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Brent Morales',
    'address': '2371 Lori Square\nNorth Stephaniefort, ME 15463',
    'text': 'Carry behind get something choose. Late such the admit. Us technology tree.\nAgainst adult fund mind often fine force result. Form military with risk they.',
    'email': 'fred55@example.net',
    'phone_number': '949.871.2156x58003',
    'json': {
    'name': 'David Norris',
    'address': 'USS Watson\nFPO AE 17975',
},
    'key63673': 'value79276',
    'key20122': 'value58075',
    'key53125': 'value69438',
    'key4786': 'value85555',
},
    {
    'id': 17527492092248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Karen Blankenship',
    'address': '781 Nicole Underpass\nWest Sara, MS 04086',
    'text': 'Particular small turn board person several heavy. Husband message yes deep former. Low whose choice ground evidence.',
    'email': 'michellejordan@example.net',
    'phone_number': '757.646.4205x732',
    'json': {
    'name': 'Micheal Hogan',
    'address': 'PSC 2318, Box 3903\nAPO AE 28579',
},
    'key3762': 'value53746',
    'key36194': 'value18557',
    'key82268': 'value299',
    'key73987': 'value53306',
    'key13814': 'value18241',
    'key31612': 'value25903',
    'key7357': 'value81762',
    'key5014': 'value67917',
    'key47135': 'value58953',
},
    {
    'id': 17527492092257,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Charles Johnson',
    'address': '480 Steven Mountains\nSnyderland, LA 93501',
    'text': 'Contain magazine develop example believe follow usually. Not big although special case few. Then other old born radio relate or.\nI record class public. Five change economic make level full serve.',
    'email': 'lamblindsey@example.org',
    'phone_number': '(624)868-7222',
    'json': {
    'name': 'Trevor Bowman',
    'address': '63174 Elizabeth Park Suite 609\nAmberbury, VT 17825',
},
    'key40688': 'value7151',
},
    {
    'id': 17527492092268,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Casey Carter',
    'address': '32782 Frey Lodge Apt. 830\nBestside, VT 11224',
    'text': 'Her here must should which suffer. Perhaps letter still challenge relationship ever stage use.\nAttorney Republican movie baby know action. Former between then computer involve try.',
    'email': 'brianharris@example.net',
    'phone_number': '(350)597-5386',
    'json': {
    'name': 'Katherine Ewing',
    'address': '862 Natalie Village\nWest Zachary, PA 58412',
},
    'key36842': 'value70299',
    'key38924': 'value21120',
    'key36075': 'value53029',
    'key26105': 'value59415',
    'key22802': 'value26603',
    'key93048': 'value88696',
    'key16447': 'value97679',
    'key89485': 'value81',
    'key83239': 'value74001',
    'key11749': 'value55604',
},
    {
    'id': 17527492092280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Chelsea Mcdonald',
    'address': '601 Campbell Mountains Apt. 911\nBakerfurt, TX 39510',
    'text': 'Road deep father should tree. Father nation near top address. Inside none better discover run fly.',
    'email': 'kelly47@example.net',
    'phone_number': '001-712-838-0342',
    'json': {
    'name': 'Lauren Moses',
    'address': '5201 Horton Unions\nNew Juliaton, FL 01329',
},
    'key21641': 'value51824',
    'key76004': 'value14261',
    'key62957': 'value41225',
    'key71636': 'value18688',
    'key10309': 'value50616',
    'key20373': 'value43946',
    'key93241': 'value82903',
    'key91564': 'value64762',
},
    {
    'id': 17527492092291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Christine Roberts',
    'address': '1848 Michael Rapid\nEast Tamaratown, NC 92174',
    'text': 'Trouble follow federal answer civil. Call story ground three around.\nDiscussion American result call recognize strategy minute. Local fear painting.',
    'email': 'nelsonnicholas@example.com',
    'phone_number': '(424)952-8887x7287',
    'json': {
    'name': 'Cassandra Mills',
    'address': '3545 Ward Vista\nCooleyside, NV 52832',
},
    'key46889': 'value92745',
    'key69224': 'value11099',
    'key78606': 'value40866',
    'key44967': 'value70841',
},
    {
    'id': 17527492092303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'John Davis',
    'address': 'PSC 7291, Box 6465\nAPO AE 00538',
    'text': 'Sometimes natural old resource. Often court oil whom on try small. Sit interesting stock western open professor find.\nWhat girl ago. Out very edge final. Where money all third structure add.',
    'email': 'romerocourtney@example.com',
    'phone_number': '+1-987-874-2091',
    'json': {
    'name': 'Jennifer Haynes',
    'address': '1267 John Center Suite 056\nNew Nicholas, NC 86759',
},
    'key15993': 'value81203',
    'key2083': 'value86716',
    'key85515': 'value18046',
    'key30021': 'value59608',
    'key88940': 'value13024',
    'key81116': 'value82168',
    'key32447': 'value99895',
},
    {
    'id': 17527492092312,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Tina Rivera',
    'address': '7751 Scott Pass\nSouth Crystalside, IN 35925',
    'text': 'House listen thank industry line. Key include consumer if tend argue might.\nMoney force order hope everything rock. Indicate know action unit so close huge.',
    'email': 'zgonzales@example.net',
    'phone_number': '001-967-746-4068x89347',
    'json': {
    'name': 'Mark West',
    'address': '673 Derek Trace\nNorth Elizabeth, AK 85950',
},
    'key26524': 'value62211',
    'key27190': 'value40874',
    'key25691': 'value78427',
    'key70352': 'value35595',
    'key40369': 'value47909',
    'key33458': 'value35167',
    'key34516': 'value52725',
    'key91939': 'value19027',
},
    {
    'id': 17527492092322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'James Graham',
    'address': '19931 Pearson Crossroad\nJuliemouth, VA 13709',
    'text': 'Expect side look might. Mother find anything somebody support. Amount speech case man.\nTrue agency build foreign nation state clearly. Under particular across. Anyone worker maybe sort agent cup.',
    'email': 'rjackson@example.net',
    'phone_number': '+1-619-937-9729x404',
    'json': {
    'name': 'Valerie Robbins',
    'address': '665 Christopher Lakes\nAaronville, WI 52937',
},
    'key34117': 'value87053',
    'key85644': 'value76960',
    'key75642': 'value59120',
    'key70118': 'value88812',
    'key63526': 'value90661',
    'key64651': 'value70541',
    'key72621': 'value15604',
    'key4899': 'value84465',
    'key62144': 'value33213',
    'key17535': 'value68542',
},
    {
    'id': 17527492092333,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Lisa Stephens',
    'address': '718 Crystal Ville\nWest Debraport, FL 81610',
    'text': 'Voice collection happen test rich. Beat thousand also trouble.\nSouth they practice bill similar culture. Arrive system magazine money his.',
    'email': 'moorejohn@example.org',
    'phone_number': '956-463-3302x84686',
    'json': {
    'name': 'Marie Ward',
    'address': '3773 Thomas Street\nEast Brian, HI 20437',
},
    'key83705': 'value41706',
    'key43507': 'value26459',
    'key22691': 'value72903',
    'key31614': 'value1549',
    'key20778': 'value35567',
    'key41530': 'value42988',
    'key57336': 'value16273',
    'key15210': 'value35266',
    'key18156': 'value74853',
    'key33911': 'value23012',
},
    {
    'id': 17527492092344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Tanya Miller',
    'address': 'Unit 6732 Box 9132\nDPO AP 43202',
    'text': 'Whatever pass quality real sure involve. Attorney bad rich sport visit wonder. Operation others agreement process.',
    'email': 'mary28@example.com',
    'phone_number': '230.244.6372',
    'json': {
    'name': 'Michael Castro',
    'address': '40642 Thomas Trail Suite 691\nMarshallview, PA 55202',
},
    'key52742': 'value26672',
    'key62197': 'value23058',
    'key17861': 'value59251',
    'key71677': 'value89868',
    'key71010': 'value69448',
},
    {
    'id': 17527492092353,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Wesley Johnson',
    'address': '51386 Frazier Squares\nEast Sandra, AR 62168',
    'text': 'Piece indeed perhaps very he property heart decision. Father view crime travel. Natural camera sing model over tell benefit.',
    'email': 'wesley64@example.net',
    'phone_number': '001-880-864-9355x927',
    'json': {
    'name': 'Debra Hughes',
    'address': '880 Matthew Club Apt. 342\nHernandezville, SD 92856',
},
    'key47009': 'value96103',
    'key28540': 'value25466',
    'key5587': 'value45624',
},
    {
    'id': 17527492092363,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Anne Vaughan',
    'address': '923 Underwood Avenue\nPort Monicaport, FL 74789',
    'text': 'Large despite team speech whom spend. Meeting recent relationship drug. Feel employee affect reflect sell.',
    'email': 'wardjoshua@example.net',
    'phone_number': '287-927-2542',
    'json': {
    'name': 'Donna Thomas',
    'address': '343 Brown Shoals\nBarryhaven, NJ 71030',
},
    'key75419': 'value67929',
    'key50529': 'value11619',
    'key48121': 'value37393',
},
    {
    'id': 17527492092375,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Danielle Martin',
    'address': '0164 Jackson Spring Suite 993\nHilltown, FM 68058',
    'text': 'Board size or. Action talk act simply score. Run instead another of ask too lot until.\nSuch center ahead foreign pick floor. Film better trade by hear sure.',
    'email': 'hmelendez@example.com',
    'phone_number': '492.538.7510x22936',
    'json': {
    'name': 'Valerie Buck',
    'address': '0446 David Courts Suite 095\nLake Karentown, VI 49198',
},
    'key28887': 'value8130',
    'key54892': 'value91608',
},
    {
    'id': 17527492092386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Victoria Hernandez',
    'address': '95796 Daniel Lock Suite 751\nCunninghamview, MN 46360',
    'text': 'Sport born senior they. As author body reason late ok stock. Late record mean represent interesting official.',
    'email': 'pclark@example.org',
    'phone_number': '001-795-801-0289',
    'json': {
    'name': 'Jennifer Matthews',
    'address': '7870 Jennifer Hollow Apt. 439\nNorth Christiebury, FL 33779',
},
    'key66054': 'value39397',
    'key59180': 'value89812',
    'key36542': 'value91110',
},
    {
    'id': 17527492092397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Amy Martinez',
    'address': '2765 Hall Mission\nJennyland, LA 64095',
    'text': 'Energy paper professional theory focus nearly material. Seven beautiful star eat.\nHowever seem degree human call. Might control bring three. Plant really authority red yet per.',
    'email': 'jacqueline27@example.com',
    'phone_number': '8826049395',
    'json': {
    'name': 'Denise Robinson',
    'address': 'Unit 3114 Box 1856\nDPO AE 20358',
},
    'key13497': 'value34027',
    'key20485': 'value28960',
    'key37245': 'value12712',
    'key67557': 'value99472',
    'key48669': 'value95188',
    'key392': 'value90897',
    'key43111': 'value80245',
    'key69401': 'value62146',
    'key21761': 'value38271',
    'key57867': 'value64309',
},
    {
    'id': 17527492092406,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Melissa Glass',
    'address': '02780 Murray Views Apt. 612\nJessicatown, FL 04142',
    'text': 'Miss range rather beat billion. Product certainly trade. Result begin society top so.\nCareer language must gun would.\nChoice later world life off process. Sound have agree cause explain.',
    'email': 'charles33@example.org',
    'phone_number': '+1-980-464-3458x5991',
    'json': {
    'name': 'Kevin Colon',
    'address': '1988 Molly Lights\nBeverlytown, AL 78639',
},
    'key65886': 'value12522',
    'key36007': 'value31190',
    'key90562': 'value29564',
    'key17350': 'value13489',
    'key33003': 'value60711',
    'key40047': 'value8228',
    'key84176': 'value28631',
},
    {
    'id': 17527492092416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Ricardo Ayers',
    'address': '7158 Karen Trail\nNorth Mirandachester, NY 45967',
    'text': 'Avoid camera event ability draw later list.\nPerhaps per pretty stop hold. Cup again indeed lawyer doctor which. For treat message require plan fund throw.',
    'email': 'laurajones@example.org',
    'phone_number': '+1-477-995-0346x66737',
    'json': {
    'name': 'Fernando Davis',
    'address': '34611 Elizabeth Ferry\nSoniaborough, NC 04894',
},
    'key54343': 'value57889',
    'key72295': 'value36358',
    'key38869': 'value15623',
    'key99497': 'value52419',
    'key20892': 'value12945',
    'key18592': 'value52056',
},
    {
    'id': 17527492092427,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Daniel Wang',
    'address': 'USCGC James\nFPO AE 65641',
    'text': 'End price more describe want nice. Raise citizen body cultural full soon. Nothing past actually together subject cut.',
    'email': 'rebecca66@example.net',
    'phone_number': '001-740-884-0011x98983',
    'json': {
    'name': 'Heather Jordan',
    'address': '21322 Daniel Curve Apt. 914\nPort Zacharyview, NE 88705',
},
    'key94566': 'value65913',
},
    {
    'id': 17527492092436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Tasha Meyers',
    'address': '3557 Traci Forest\nNovakborough, KS 57575',
    'text': 'Go improve best behavior morning successful. Book son without program certainly. Argue turn lead important person.',
    'email': 'jessica69@example.org',
    'phone_number': '359.232.9525x8481',
    'json': {
    'name': 'Tonya Kramer',
    'address': '198 Jennifer Gateway\nErinport, ME 11679',
},
    'key77875': 'value86421',
    'key96107': 'value75529',
    'key11498': 'value66053',
    'key42734': 'value54506',
    'key5785': 'value37130',
    'key1574': 'value65881',
    'key42766': 'value54287',
    'key79222': 'value86074',
    'key73762': 'value74781',
},
    {
    'id': 17527492092446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Michael Woods',
    'address': '568 Calhoun Points\nHowardbury, DE 87570',
    'text': 'Speak computer participant join often.\nBusiness minute clear into player. Successful will evening history.\nMean point body state hotel. Fish TV unit minute my apply.',
    'email': 'norma07@example.net',
    'phone_number': '(204)985-2229',
    'json': {
    'name': 'Jeff Garcia',
    'address': '571 Cathy Green Suite 176\nWest Beth, DC 16923',
},
    'key92769': 'value44963',
    'key298': 'value43708',
    'key58426': 'value65162',
    'key45416': 'value60837',
    'key46189': 'value72454',
    'key85140': 'value13834',
    'key41136': 'value76473',
    'key26157': 'value71225',
    'key67459': 'value73816',
},
    {
    'id': 17527492092457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'David Fitzgerald',
    'address': '99958 Pearson Trafficway\nMartinezstad, NY 15282',
    'text': 'Wear drug drop account develop dream. Good number arrive.\nState item try ago law pay since. Hundred citizen direction defense successful final ever court. Shake everyone culture nice.',
    'email': 'barry87@example.com',
    'phone_number': '401.527.2698',
    'json': {
    'name': 'David Foster',
    'address': '0970 Parker Port Apt. 832\nNorth Holly, OR 01097',
},
    'key31390': 'value37569',
    'key3958': 'value46622',
    'key49291': 'value92264',
    'key9685': 'value41868',
    'key36656': 'value79156',
    'key77987': 'value6011',
},
    {
    'id': 17527492092468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Matthew Reyes',
    'address': '1852 Gina Rapid Suite 615\nJeffreyborough, PR 02377',
    'text': 'Consumer spring process environment medical citizen. Class few might else. National why measure particularly executive.',
    'email': 'wrightmatthew@example.com',
    'phone_number': '509.432.5014x135',
    'json': {
    'name': 'Karen Brooks',
    'address': '4351 Sanders Vista\nSouth Virginiabury, HI 08374',
},
    'key65699': 'value57560',
    'key33743': 'value98909',
    'key96954': 'value46456',
    'key65072': 'value24659',
    'key14495': 'value4915',
    'key83079': 'value24593',
    'key13318': 'value32955',
    'key39850': 'value73117',
},
    {
    'id': 17527492092479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Ryan Tucker',
    'address': '20194 Andrew Road Suite 746\nAustinmouth, WI 26139',
    'text': 'Newspaper according election director first raise.\nChair when somebody industry middle win company. Politics modern experience teach especially offer.',
    'email': 'heidigarner@example.com',
    'phone_number': '+1-277-919-0049x28309',
    'json': {
    'name': 'Sean Hall',
    'address': '3692 Andrew Terrace Apt. 323\nNorth Racheltown, TX 97318',
},
    'key43643': 'value40872',
    'key59520': 'value93540',
    'key70841': 'value35024',
    'key36421': 'value51739',
    'key92093': 'value7846',
    'key42653': 'value56504',
    'key56966': 'value13030',
    'key9835': 'value64503',
    'key57568': 'value81373',
    'key80728': 'value97846',
},
    {
    'id': 17527492092491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Catherine Flores',
    'address': '65492 Lee Junction Apt. 550\nLake Brittany, IN 24675',
    'text': 'Husband partner smile service series could. Town piece process possible. Significant technology by first wife draw.\nSix until push staff. Compare value scene onto professor.',
    'email': 'uclark@example.net',
    'phone_number': '(305)621-6618x789',
    'json': {
    'name': 'Bradley Romero',
    'address': '2589 Leslie Summit\nRussobury, DE 96990',
},
    'key15010': 'value66154',
    'key96666': 'value266',
    'key64464': 'value12212',
    'key92568': 'value71391',
    'key82743': 'value81566',
    'key75540': 'value12967',
    'key73655': 'value33267',
    'key88310': 'value2228',
    'key92936': 'value8048',
},
    {
    'id': 17527492092502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Walter Wilson',
    'address': '82727 Matthew Mills\nFryland, MP 68764',
    'text': 'Number inside factor evening eight. Through exist identify onto southern member new. Weight catch save brother wonder.',
    'email': 'hintonmarilyn@example.net',
    'phone_number': '579.658.0111',
    'json': {
    'name': 'Zachary Horn',
    'address': '801 Keller Port\nNorth Beth, AL 30190',
},
    'key33147': 'value58280',
    'key3240': 'value19653',
    'key29333': 'value2617',
    'key78194': 'value43594',
},
    {
    'id': 17527492092513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Leslie Vega',
    'address': '2227 Johnson Gateway\nChangfurt, CA 51454',
    'text': 'Property easy quite team hold building. Fund consider close we and back management character.',
    'email': 'sonya58@example.org',
    'phone_number': '749-496-3029x02225',
    'json': {
    'name': 'Larry Boyd',
    'address': '358 Brandon Club Apt. 967\nEast Connie, CT 68974',
},
    'key67255': 'value68851',
    'key40195': 'value84354',
    'key86131': 'value30639',
    'key1424': 'value58608',
    'key65317': 'value74588',
    'key26644': 'value9585',
    'key67119': 'value93331',
    'key13929': 'value4435',
    'key90918': 'value51704',
    'key10588': 'value46324',
},
    {
    'id': 17527492092524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'David Klein',
    'address': 'USCGC Morris\nFPO AA 07286',
    'text': 'Candidate table us magazine. Page show artist sign. Quite spring little newspaper traditional employee everything.\nEverybody draw simply plan.',
    'email': 'harrisscott@example.net',
    'phone_number': '926-438-3972',
    'json': {
    'name': 'Amy Stewart',
    'address': '17812 Adam Forest Suite 622\nGoodmantown, OR 25509',
},
    'key37148': 'value61021',
    'key43259': 'value84361',
    'key1552': 'value39645',
    'key16042': 'value33',
    'key92099': 'value57969',
    'key62845': 'value50272',
    'key49963': 'value12829',
},
    {
    'id': 17527492092535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Christine Miller',
    'address': '017 Matthews Park Apt. 879\nPort Williamberg, SC 85333',
    'text': 'Board product food national chair manager.\nSign attack worry pull population. None might guy discover explain. Feel prepare every together suggest even free.',
    'email': 'ginacollins@example.net',
    'phone_number': '001-830-977-9567x520',
    'json': {
    'name': 'Rachel Ortiz',
    'address': '2366 Lisa Path Apt. 161\nFlemingburgh, PW 75337',
},
    'key74131': 'value7256',
},
    {
    'id': 17527492092546,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Joseph Pacheco',
    'address': '5688 Linda Villages\nBradleyfurt, PW 15338',
    'text': 'Author spend step partner body. Perform according manager rest use. Republican democratic responsibility section collection hit. Speech two society watch law.',
    'email': 'sarahdavis@example.net',
    'phone_number': '657.498.1168x99102',
    'json': {
    'name': 'Jill Boone',
    'address': '3029 Richard Plain\nJenkinsstad, FL 04334',
},
    'key6555': 'value16852',
},
    {
    'id': 17527492092557,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Jennifer Espinoza',
    'address': '0022 Garrett Fields\nNorth Seth, DC 30526',
    'text': 'Concern ability ready almost home. Top become want know perform either program. Everything toward benefit after.',
    'email': 'gonzalesjacob@example.com',
    'phone_number': '001-429-628-2341',
    'json': {
    'name': 'Jessica Taylor',
    'address': '768 Victoria Crest Apt. 270\nNew Daniel, FM 09486',
},
    'key89666': 'value3748',
    'key10562': 'value9449',
    'key35341': 'value57874',
},
    {
    'id': 17527492092568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Anthony Shaw',
    'address': '1246 Wiggins Summit Suite 476\nJasonhaven, PR 84793',
    'text': 'Inside air year blue loss. Write time actually team real size. With light way out two either right.',
    'email': 'bthompson@example.org',
    'phone_number': '+1-749-729-4727x62890',
    'json': {
    'name': 'Donna Davis',
    'address': '18654 Christopher Streets\nNorth Gary, VT 40632',
},
    'key48189': 'value2113',
    'key91769': 'value88280',
    'key56789': 'value87300',
    'key17205': 'value99221',
},
    {
    'id': 17527492092579,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Eddie Owens',
    'address': '264 Bonilla Ports\nNorth Nicole, SC 26145',
    'text': 'It little break debate performance bring watch. Receive official interview trip suffer. Lead friend owner chance number. Black happen though social young.',
    'email': 'jbishop@example.com',
    'phone_number': '640-597-3389x82323',
    'json': {
    'name': 'Joyce Humphrey',
    'address': '398 Richardson Stravenue\nJameston, NM 74108',
},
    'key36178': 'value63124',
    'key42207': 'value98971',
    'key58752': 'value3685',
    'key2387': 'value42746',
    'key8987': 'value42498',
    'key57801': 'value28303',
},
    {
    'id': 17527492092590,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Thomas Miller',
    'address': '62087 Zachary Mountain\nLake Christianmouth, AZ 67360',
    'text': 'Blue finish thank laugh too evidence argue seek. Major you case happy record sister return although. Republican seem Republican hope begin suddenly.',
    'email': 'joshuawallace@example.org',
    'phone_number': '(879)460-7389',
    'json': {
    'name': 'David Rodriguez',
    'address': '473 Larsen Mountains\nWest Ryanmouth, CT 86919',
},
    'key45537': 'value13917',
    'key26091': 'value42433',
    'key30344': 'value98377',
    'key61334': 'value11051',
    'key57507': 'value24409',
    'key63542': 'value48677',
    'key86986': 'value42344',
    'key27637': 'value57937',
    'key6431': 'value73447',
},
    {
    'id': 17527492092602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Brandi Bush',
    'address': '611 Bentley Well\nCrossburgh, IA 76341',
    'text': 'Drop I center world huge to.\nMemory win particular. Tough ready something situation agent.',
    'email': 'kennethsmith@example.net',
    'phone_number': '001-500-810-3199',
    'json': {
    'name': 'Thomas Nunez',
    'address': '09018 Kayla Mills\nPaulfurt, CT 62099',
},
    'key98060': 'value92354',
    'key45947': 'value38002',
    'key94436': 'value17540',
    'key92975': 'value28955',
    'key18551': 'value74053',
    'key51550': 'value91676',
},
    {
    'id': 17527492092613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Tara Blair',
    'address': '88888 Darlene Locks Apt. 498\nStevensshire, KY 98114',
    'text': 'Perform executive else. Current too specific administration. Enough trial describe believe talk.\nGuess couple section reach sell. Mention community rather near with.',
    'email': 'jamescaitlin@example.org',
    'phone_number': '001-475-396-8440x0733',
    'json': {
    'name': 'Rebecca Goodman',
    'address': '263 Terry Shoals\nEmilyshire, TX 94160',
},
    'key58924': 'value73727',
    'key12453': 'value20680',
    'key28884': 'value13509',
    'key75419': 'value5674',
    'key44288': 'value87341',
},
    {
    'id': 17527492092625,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Michael Walters',
    'address': '506 Ramirez Brook\nCollinsburgh, UT 69960',
    'text': 'Series read individual cost great computer hard. For scientist behind forget. Argue almost exactly official together message.',
    'email': 'myersdawn@example.net',
    'phone_number': '266-344-5060x074',
    'json': {
    'name': 'Jonathan Leonard',
    'address': '4640 Richard Port Suite 677\nNorth Dianaview, NY 20864',
},
    'key56970': 'value71110',
    'key24393': 'value24789',
    'key31638': 'value30382',
    'key32335': 'value63055',
},
    {
    'id': 17527492092636,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Carrie Morrison',
    'address': '62457 White Shoal\nStefaniefort, UT 39176',
    'text': 'Tax protect final table visit decade call. Reduce last pick fall attack your spend. Return third senior avoid pressure until choose.',
    'email': 'donnarice@example.com',
    'phone_number': '872-266-1151x13061',
    'json': {
    'name': 'Michael Norris',
    'address': 'USS Rivera\nFPO AP 79732',
},
    'key20627': 'value95062',
    'key26024': 'value24463',
    'key25823': 'value47043',
    'key14954': 'value95256',
    'key52349': 'value79629',
},
    {
    'id': 17527492092647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Emily Turner',
    'address': '01252 Troy Light Apt. 443\nMorganfort, TN 74857',
    'text': 'Interesting cover issue since research. Your interesting current check.\nChance different increase skill attention. Life trade official conference week could.',
    'email': 'perryabigail@example.org',
    'phone_number': '507.735.4313x22598',
    'json': {
    'name': 'Kyle Kerr',
    'address': 'Unit 4341 Box 6871\nDPO AP 12203',
},
    'key69761': 'value95929',
    'key79972': 'value97780',
},
    {
    'id': 17527492092656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Michael Frost',
    'address': '908 Jackson Place\nKathleenfurt, OR 88855',
    'text': 'Reach position within especially staff point over position. High but player.\nUs particular blue truth your approach company. Prove heavy box another law. Arm teacher surface free.',
    'email': 'matthew48@example.com',
    'phone_number': '480.766.7315',
    'json': {
    'name': 'Cynthia Bridges',
    'address': '26300 Clark Knolls Suite 598\nPort Paige, CT 05990',
},
    'key61306': 'value249',
    'key57357': 'value39340',
    'key60230': 'value88119',
    'key33870': 'value4659',
    'key87547': 'value49027',
    'key99172': 'value50076',
},
    {
    'id': 17527492092667,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Tracy Wilcox',
    'address': '1911 Herring Meadow\nPort Anthony, TN 75192',
    'text': 'Measure yet plan should. Drug cold mother subject military may someone. Charge team common recognize require.\nIdea whole get. Of thought college. Book more win view.',
    'email': 'hallcorey@example.com',
    'phone_number': '001-822-355-2263x216',
    'json': {
    'name': 'Lauren Mills',
    'address': '5871 Rivera Road Suite 462\nLake Michaelhaven, IN 36249',
},
    'key46465': 'value67573',
    'key92741': 'value76668',
    'key20062': 'value87002',
    'key65215': 'value31178',
    'key14594': 'value82192',
    'key85251': 'value26966',
    'key44423': 'value46525',
    'key80914': 'value87853',
    'key20333': 'value91017',
    'key18749': 'value23821',
},
    {
    'id': 17527492092678,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Joseph Henry',
    'address': '9162 Maria Point Apt. 018\nLake Barbaraside, ID 67311',
    'text': 'Someone sea possible their provide huge. Support become weight test see. Smile could process.',
    'email': 'ngill@example.org',
    'phone_number': '(470)482-1648',
    'json': {
    'name': 'Joshua Gonzalez',
    'address': '44742 Andrew Vista Suite 558\nTylermouth, TN 00695',
},
    'key52250': 'value94949',
    'key30452': 'value73092',
    'key43344': 'value7203',
},
    {
    'id': 17527492092689,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Ruben Blackwell',
    'address': '7424 Melton Village\nNorth Anthonyton, MO 34722',
    'text': 'Improve story network movie argue new thought. Wish significant assume important. Congress drug one order billion play car participant.',
    'email': 'smayer@example.net',
    'phone_number': '001-755-299-1084',
    'json': {
    'name': 'Mark Keith',
    'address': '2380 Tran Pine\nJamesport, IL 86197',
},
    'key74687': 'value13777',
    'key40616': 'value24770',
    'key44295': 'value68099',
    'key48810': 'value38006',
    'key35710': 'value35404',
    'key50931': 'value8941',
    'key54844': 'value41408',
},
    {
    'id': 17527492092700,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Evan Edwards',
    'address': 'USNV Stephenson\nFPO AP 78557',
    'text': 'East law TV once difference player. Real main could law exactly its others high.',
    'email': 'jessicaschmidt@example.org',
    'phone_number': '224-999-3220x52833',
    'json': {
    'name': 'Michael Anderson',
    'address': '17583 Julie Mills\nWyattberg, NV 68575',
},
    'key58864': 'value91615',
},
    {
    'id': 17527492092710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'William Munoz',
    'address': 'PSC 1864, Box 0600\nAPO AP 31105',
    'text': 'World want blue camera decide. Five animal population son whom read. Magazine may according to blood.',
    'email': 'justinsimpson@example.com',
    'phone_number': '+1-551-846-9955x30098',
    'json': {
    'name': 'Garrett Key',
    'address': '9954 Carol Village\nPaulshire, SD 40869',
},
    'key96822': 'value57305',
    'key86612': 'value59420',
    'key14513': 'value14176',
    'key33898': 'value40333',
    'key44025': 'value97459',
    'key39589': 'value63718',
},
    {
    'id': 17527492092720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Shari Matthews',
    'address': '983 Taylor Groves Apt. 826\nMackchester, TN 07376',
    'text': 'Pattern chair trial form. You range claim property education adult indeed. Outside sell deep other message protect decision.',
    'email': 'tammymcintyre@example.com',
    'phone_number': '8918696648',
    'json': {
    'name': 'William Maxwell',
    'address': 'Unit 9629 Box 8325\nDPO AA 78077',
},
    'key16756': 'value14662',
    'key38246': 'value23868',
    'key39648': 'value70493',
    'key54236': 'value62328',
    'key21613': 'value38501',
    'key99363': 'value85187',
    'key23385': 'value98566',
},
    {
    'id': 17527492092729,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Mr. Steven Brown',
    'address': 'PSC 1072, Box 2764\nAPO AP 53721',
    'text': 'Free available offer defense whole southern machine. Specific right little along market month fine.',
    'email': 'kathy07@example.net',
    'phone_number': '9274810671',
    'json': {
    'name': 'Madison Green',
    'address': '335 Rodriguez Row\nReginaldhaven, OR 30212',
},
    'key72784': 'value74468',
    'key53460': 'value20884',
},
    {
    'id': 17527492092738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'April Gamble',
    'address': '6904 Ricky Extension Suite 895\nJodimouth, AR 24972',
    'text': 'Entire return particularly talk professional. Card soldier level station. Itself majority president leader.',
    'email': 'bentleyrebecca@example.com',
    'phone_number': '735.265.9642x707',
    'json': {
    'name': 'Elizabeth Wang',
    'address': '22116 Jonathon Parks\nEvansborough, AK 97841',
},
    'key29287': 'value9474',
    'key62409': 'value21770',
    'key37693': 'value79299',
    'key82280': 'value24428',
    'key87503': 'value44373',
    'key25711': 'value66646',
    'key94403': 'value33674',
    'key90987': 'value28029',
    'key33202': 'value16742',
    'key37140': 'value94947',
},
    {
    'id': 17527492092749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'James Thomas',
    'address': '0595 Ellison Via\nKennethstad, AZ 09158',
    'text': 'Choose college statement material recently put. Explain other before scene dark clearly cover.\nMajority Democrat doctor. Until other sell service tonight. Team simply hotel.',
    'email': 'campbellerica@example.net',
    'phone_number': '001-578-877-1580x587',
    'json': {
    'name': 'Jennifer Lopez',
    'address': '21133 Andersen Garden Suite 729\nLake Steven, UT 13827',
},
    'key9626': 'value47752',
    'key472': 'value25101',
},
    {
    'id': 17527492092760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Belinda Phillips',
    'address': '409 Douglas Point\nLake David, KY 20360',
    'text': 'Bring back program her.\nElse such charge minute break thought. Simply hold though begin easy born throw. Opportunity Mr citizen everyone my later prepare.',
    'email': 'ghill@example.net',
    'phone_number': '(513)964-6814x131',
    'json': {
    'name': 'Kimberly Ryan',
    'address': '8714 Perry Ramp\nWest Daniel, VA 37347',
},
    'key39968': 'value40657',
    'key24849': 'value75736',
    'key12036': 'value97078',
    'key20727': 'value47176',
    'key82242': 'value13556',
},
    {
    'id': 17527492092771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Mikayla Carter',
    'address': '40497 Albert Underpass\nDownsfort, LA 56090',
    'text': 'Similar really training need people. Professional bit these option strategy style place smile. Smile pressure civil early left.\nSomething know as outside surface place.',
    'email': 'rdavis@example.org',
    'phone_number': '+1-568-831-0244x086',
    'json': {
    'name': 'Ms. Debra Smith MD',
    'address': '674 Robert Spurs\nNorth Tylerstad, NV 74330',
},
    'key86552': 'value20262',
    'key8136': 'value10220',
    'key79682': 'value20353',
},
    {
    'id': 17527492092782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'David Trujillo',
    'address': '57482 Lisa Isle\nJenniferview, MT 21191',
    'text': 'Smile must Democrat wife community miss way. Better instead significant.\nTechnology to strong accept deep food. Left seven keep public front dog current per. Wish threat yourself life reduce do.',
    'email': 'rbennett@example.com',
    'phone_number': '6888041677',
    'json': {
    'name': 'Katie Miller',
    'address': '4273 Emily Loaf\nFostertown, IA 71194',
},
    'key7788': 'value50846',
    'key73603': 'value10393',
    'key30271': 'value74750',
    'key57343': 'value56134',
    'key96210': 'value60095',
    'key61774': 'value83761',
    'key50673': 'value76688',
},
    {
    'id': 17527492092793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Andrew Williams',
    'address': '695 Smith Keys\nNew Nancy, ID 80994',
    'text': 'Fire what back significant five. Market born seven generation report area green exactly. Money per food decade service these.',
    'email': 'cindy37@example.com',
    'phone_number': '+1-547-383-7389',
    'json': {
    'name': 'Charles Torres',
    'address': '233 Weeks Coves Suite 147\nChavezview, ID 73937',
},
    'key37900': 'value84982',
    'key88147': 'value98159',
},
    {
    'id': 17527492092804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Suzanne Walls',
    'address': '4479 Boyd Court\nShermanchester, CO 35016',
    'text': 'Research fire them role after true.\nPretty level no plan. Around sound notice Mr performance be paper.',
    'email': 'john31@example.com',
    'phone_number': '001-948-363-7348x7610',
    'json': {
    'name': 'Matthew Ford',
    'address': '196 Larry Corners Apt. 762\nNorth Christopherland, MH 34736',
},
    'key47602': 'value20102',
    'key91051': 'value66622',
    'key13097': 'value86458',
    'key3356': 'value97769',
},
    {
    'id': 17527492092817,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Michelle Martin',
    'address': '37134 Castillo Spurs\nSeanburgh, CT 07163',
    'text': 'Investment play knowledge sense street. Eye each church tend road. Teach page military mouth dog.',
    'email': 'christophernewman@example.net',
    'phone_number': '557.728.8086',
    'json': {
    'name': 'Daniel Gonzalez',
    'address': '480 Jones Turnpike\nSouth Carlburgh, MO 01803',
},
    'key27986': 'value30885',
    'key10613': 'value49456',
},
    {
    'id': 17527492092831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Henry Davis',
    'address': 'USNV Griffin\nFPO AE 43227',
    'text': 'Explain hold house article health for second. Detail sign evidence exist bed.\nLaugh drop animal approach partner should peace foot. Doctor ready decide.\nCongress cell well. Kind marriage management.',
    'email': 'qmartinez@example.org',
    'phone_number': '8846118954',
    'json': {
    'name': 'Rachel Johnston',
    'address': '5744 Hardy Mills\nPort Laura, SC 45014',
},
    'key64212': 'value82256',
    'key32352': 'value40758',
    'key79393': 'value57970',
    'key71673': 'value89965',
    'key13120': 'value17170',
    'key52697': 'value41633',
    'key77293': 'value43206',
    'key87834': 'value70761',
    'key12392': 'value5450',
},
    {
    'id': 17527492092842,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Robert Dawson',
    'address': '9048 Victoria Ranch Suite 082\nMichaelmouth, NJ 92271',
    'text': 'Citizen put letter reach.\nAge almost yet. Ground through age where include thought son upon.',
    'email': 'melissa22@example.net',
    'phone_number': '280.592.9448',
    'json': {
    'name': 'Mary Cochran',
    'address': '0315 Velasquez Crossing\nSouth Roberttown, GU 02030',
},
    'key39115': 'value76773',
    'key35777': 'value99703',
    'key30798': 'value57010',
    'key78505': 'value49887',
    'key38732': 'value47649',
    'key94837': 'value2562',
},
    {
    'id': 17527492092854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Samuel Gordon',
    'address': '295 Lawrence Hills Apt. 345\nJohnsonport, WA 27838',
    'text': 'Would generation at point. Fact company information.\nBlood quite commercial. Leg law human move.\nDespite not decade certainly find movement. Economy ten phone town.',
    'email': 'mccormickjill@example.net',
    'phone_number': '502.894.0473',
    'json': {
    'name': 'Jerome Howard',
    'address': '0915 Bruce Overpass Suite 334\nPort Reneemouth, TX 08857',
},
    'key97321': 'value81492',
    'key31569': 'value62015',
    'key59298': 'value24802',
    'key86472': 'value72235',
    'key16527': 'value39129',
    'key92756': 'value58361',
    'key43620': 'value43514',
    'key52156': 'value54840',
    'key3155': 'value42383',
},
    {
    'id': 17527492092867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Victoria Barnes',
    'address': '962 Claire Ramp Suite 828\nMicheleville, UT 33312',
    'text': 'Executive government reason ever strategy eight off. Popular someone write institution these.',
    'email': 'spencegregory@example.com',
    'phone_number': '441-682-5322x66917',
    'json': {
    'name': 'Deanna Young',
    'address': '475 Erika Parkway Apt. 658\nSouth Lynnburgh, KS 86604',
},
    'key4435': 'value30176',
    'key53935': 'value66900',
    'key36405': 'value50852',
    'key91067': 'value65332',
    'key79253': 'value19890',
    'key52220': 'value71563',
    'key58809': 'value83830',
    'key20460': 'value39489',
    'key44838': 'value42677',
    'key90836': 'value99346',
},
    {
    'id': 17527492092879,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Caroline Sanders',
    'address': '0576 Garcia Circle\nSouth Danachester, KY 53622',
    'text': 'Line room minute interview minute majority gun. Over help everyone. Part bed join agent executive.',
    'email': 'skrause@example.org',
    'phone_number': '209.338.7360',
    'json': {
    'name': 'Wendy Andrews',
    'address': 'PSC 0778, Box 6377\nAPO AP 76178',
},
    'key59542': 'value52328',
},
    {
    'id': 17527492092889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Amber Graham',
    'address': '582 Cody Mall Suite 109\nKaitlynton, WV 47205',
    'text': 'Into herself hear friend. Case raise move guy out painting various west.\nNeed garden respond forget. Imagine around nothing wear attention question.',
    'email': 'acevedokaren@example.net',
    'phone_number': '540-338-5905x42370',
    'json': {
    'name': 'Jason Tucker',
    'address': '664 Beck Extensions Suite 855\nWest Williamhaven, KY 61810',
},
    'key48748': 'value95217',
    'key28569': 'value43099',
    'key1015': 'value46260',
    'key61429': 'value11349',
    'key2738': 'value59371',
    'key55652': 'value53938',
    'key25745': 'value30462',
},
    {
    'id': 17527492092901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Matthew Gutierrez',
    'address': '04259 Jacobson Parkway\nYoungburgh, PR 06102',
    'text': 'Themselves our us parent feel several method. Contain price economy minute positive open half. Full young discover gas participant sure be. Treatment instead exist ago if owner memory.',
    'email': 'keithjones@example.net',
    'phone_number': '001-442-744-9401',
    'json': {
    'name': 'Jared Gates',
    'address': '7389 Burke Garden\nWest Crystal, FL 35126',
},
    'key48435': 'value27759',
    'key76783': 'value64901',
},
    {
    'id': 17527492092912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Nathan Smith',
    'address': '20277 Elizabeth Manors Suite 664\nEast Shaun, CA 99691',
    'text': 'To person land possible nothing site present. Business data affect fire fund. Hope manager product clear.',
    'email': 'haley01@example.org',
    'phone_number': '(799)835-5642x623',
    'json': {
    'name': 'Mark Conner',
    'address': '21062 Tanya Flat Apt. 001\nPort Gilbert, IA 99673',
},
    'key92763': 'value93396',
    'key65368': 'value42831',
    'key85695': 'value9542',
},
    {
    'id': 17527492092922,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Jackie Martin',
    'address': '8959 Desiree Stravenue Suite 370\nWhiteport, MP 70782',
    'text': 'Kind time sing spring now.\nChance pass officer. Daughter project forget near indicate. Ground treat nation see.\nEnergy everything type before.',
    'email': 'jason40@example.org',
    'phone_number': '(235)914-2463x239',
    'json': {
    'name': 'Sarah Castillo',
    'address': '52398 Myers Loaf\nEast Johnmouth, NE 67118',
},
    'key69495': 'value65082',
    'key33432': 'value44516',
    'key74283': 'value93205',
    'key60234': 'value17169',
},
    {
    'id': 17527492092933,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'William Skinner',
    'address': 'USNS Ramos\nFPO AE 29068',
    'text': 'Lose series majority such term call bad.\nDoor human short their girl common. Far provide compare opportunity body.\nOfficer house who really professor. Cover effort doctor event stuff goal everything.',
    'email': 'allison50@example.com',
    'phone_number': '781-752-7666x580',
    'json': {
    'name': 'Leslie Shea',
    'address': '9322 Santiago Key Apt. 267\nElizabethberg, NV 85880',
},
    'key49888': 'value16730',
    'key93945': 'value94525',
    'key88270': 'value38825',
    'key34190': 'value43212',
    'key76750': 'value29438',
    'key32933': 'value19773',
    'key86399': 'value5435',
    'key84641': 'value59406',
    'key16900': 'value68646',
},
    {
    'id': 17527492092943,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Kelly Glenn',
    'address': '91501 Parker Freeway\nSteeleview, SC 53060',
    'text': 'Capital church social others. Quickly bit value job modern case name.',
    'email': 'carla31@example.com',
    'phone_number': '+1-844-704-7355x85039',
    'json': {
    'name': 'Frank Smith',
    'address': '3851 Phillip Station\nLake Alicefort, MA 69172',
},
    'key14408': 'value37961',
},
    {
    'id': 17527492092953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Emily Espinoza',
    'address': '8251 Wilson Hollow Apt. 370\nArianaborough, AZ 97475',
    'text': 'Economic decide structure everyone thing. No class early agent lawyer training.\nFinancial such seat. Exactly glass term up then across mention.\nMorning common education region magazine training read.',
    'email': 'johnlyons@example.org',
    'phone_number': '001-461-687-0490',
    'json': {
    'name': 'Shannon Lee',
    'address': 'PSC 1822, Box 8050\nAPO AA 48798',
},
    'key41370': 'value6894',
    'key82145': 'value53187',
    'key71442': 'value37887',
    'key77269': 'value33520',
    'key41191': 'value4006',
    'key11773': 'value58863',
    'key8763': 'value78522',
    'key61720': 'value834',
    'key80864': 'value61372',
    'key91334': 'value44275',
},
    {
    'id': 17527492092963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Pamela Stewart',
    'address': '48137 Melissa Greens\nMillerchester, CT 95555',
    'text': 'Describe southern myself serious. Data tax north across sport man fall. Wish subject suffer several property.',
    'email': 'christopherjohnson@example.org',
    'phone_number': '(201)509-8504',
    'json': {
    'name': 'Thomas Peterson',
    'address': '4820 Samantha Tunnel Suite 449\nNorth Kyleburgh, WY 09608',
},
    'key6882': 'value9794',
},
    {
    'id': 17527492092974,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Anne Hernandez',
    'address': '392 Kevin Port\nNorth Teresatown, NJ 37484',
    'text': 'Season might miss everyone. Southern stock save move best. Size add of white through series bit.\nHeavy lay present bad bar now. Yes huge case. Pick lose factor election majority worker establish.',
    'email': 'burkemichael@example.org',
    'phone_number': '839-574-1209x414',
    'json': {
    'name': 'Bryan Oliver',
    'address': '639 Tammy Canyon Apt. 715\nStewartmouth, MS 37336',
},
    'key29743': 'value72599',
},
    {
    'id': 17527492092985,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Sabrina Cantrell',
    'address': '679 Charles Village\nPort Kristenmouth, NC 69871',
    'text': 'Address establish reduce always in. Exactly very ten PM effect effect. Military data stay money.\nSame tell environment plant. Order history contain company represent.',
    'email': 'fergusontanya@example.org',
    'phone_number': '+1-348-797-0888x95312',
    'json': {
    'name': 'Jill Fowler',
    'address': '124 Cole Summit\nMillsland, SC 61316',
},
    'key49907': 'value54525',
    'key56507': 'value88596',
    'key98342': 'value79308',
},
    {
    'id': 17527492092997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Juan Norton DDS',
    'address': '8692 Henry Lakes\nJohnsonborough, WA 86474',
    'text': 'Blood anything under sister end later which. Build discover authority. Network model individual player.',
    'email': 'jonesrhonda@example.net',
    'phone_number': '666.246.3433',
    'json': {
    'name': 'Paige Mendez',
    'address': '748 Williams Forks\nWilliamsstad, PW 57881',
},
    'key9353': 'value58416',
    'key94494': 'value29935',
    'key25746': 'value96569',
    'key24509': 'value33709',
},
    {
    'id': 17527492093009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Wesley Adams',
    'address': '94440 Garcia Terrace Apt. 212\nLake Nicholas, MH 21817',
    'text': 'Training choose cup beyond coach as. Wind even audience why everybody gun.\nAlthough cover plan focus song. Figure him each who find certain teacher. System glass own likely build.',
    'email': 'amccarthy@example.com',
    'phone_number': '833.367.2180x6585',
    'json': {
    'name': 'Danielle Hunter',
    'address': 'USNV Pearson\nFPO AE 83014',
},
    'key63811': 'value27222',
    'key24197': 'value22581',
    'key96170': 'value40232',
    'key8764': 'value50092',
},
    {
    'id': 17527492093018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Michael Kirby',
    'address': '7745 Christine Lodge Apt. 521\nRomanland, PW 99504',
    'text': 'Report include instead machine. Claim window from paper baby example anyone.\nPurpose break character Democrat quite decade. Upon section kind door speak.',
    'email': 'logan53@example.com',
    'phone_number': '(855)656-2130x04000',
    'json': {
    'name': 'Anthony Johnson',
    'address': '209 Tracy Groves Suite 192\nNew Elizabeth, ID 31153',
},
    'key53635': 'value15671',
    'key99727': 'value47958',
    'key2353': 'value91210',
    'key39292': 'value80150',
},
    {
    'id': 17527492093028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Megan Vazquez',
    'address': '89474 Powell Parks\nNew Cynthiachester, OH 72345',
    'text': 'Charge discuss despite art claim. Painting capital matter practice month easy day.\nRecent without care mean television heart type. Democratic possible per set particular already first.',
    'email': 'lydiasutton@example.com',
    'phone_number': '(675)911-0694x99097',
    'json': {
    'name': 'Ernest Diaz',
    'address': '8208 Farmer Gateway\nShepherdhaven, OR 10272',
},
    'key72874': 'value58578',
    'key89767': 'value62831',
    'key7019': 'value49409',
    'key64642': 'value22580',
    'key4686': 'value63822',
    'key51945': 'value26693',
},
    {
    'id': 17527492093040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Susan Watkins',
    'address': '55681 Larry Fields Suite 156\nLake Ryan, AS 86318',
    'text': 'Get lose spend sea under same office. People third recently should sometimes effort.',
    'email': 'joshua61@example.net',
    'phone_number': '001-571-802-2601',
    'json': {
    'name': 'Gina Wilson',
    'address': '7788 Joshua Ways Suite 540\nSmithfurt, DC 94958',
},
    'key59991': 'value16439',
    'key33879': 'value92207',
    'key15540': 'value75846',
    'key71838': 'value24569',
    'key55856': 'value18482',
    'key11846': 'value88282',
    'key78301': 'value98944',
    'key74981': 'value98395',
    'key88613': 'value4779',
},
    {
    'id': 17527492093051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Travis Daniels',
    'address': '878 Laura Falls Suite 180\nKennethland, AK 48656',
    'text': 'Environmental probably third theory. Loss visit medical government magazine still.',
    'email': 'yjones@example.net',
    'phone_number': '(497)755-3441',
    'json': {
    'name': 'Traci Holland',
    'address': '36935 Scott Grove Apt. 518\nNorth Sandraburgh, AS 44162',
},
    'key72617': 'value17672',
    'key80996': 'value34188',
},
    {
    'id': 17527492093061,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Morgan Mccoy',
    'address': '86456 Charles Summit\nSouth Carlamouth, AZ 48073',
    'text': 'Sell wait present goal total exactly five charge. Compare husband state president government. Begin Congress whom series spring.',
    'email': 'petersondustin@example.com',
    'phone_number': '(763)320-6692',
    'json': {
    'name': 'Dustin Morris',
    'address': '4635 Weiss Prairie Suite 456\nWest Jessica, HI 54139',
},
    'key78531': 'value75184',
    'key81360': 'value30917',
    'key89163': 'value77816',
    'key26569': 'value48306',
    'key24417': 'value32050',
    'key2996': 'value72402',
},
    {
    'id': 17527492093072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Sean Horton',
    'address': '982 Jessica Cove Suite 505\nLake Katie, MH 24824',
    'text': 'Hit grow almost choose process. Tend bar relate admit near project.\nStart increase herself want here receive main. Big popular focus director woman. Develop free not raise. Spring tend back.',
    'email': 'zbaker@example.org',
    'phone_number': '+1-420-963-2948x19016',
    'json': {
    'name': 'Joseph Johnson',
    'address': '4214 Smith Inlet\nPiercefort, MO 35326',
},
    'key18998': 'value30578',
    'key34012': 'value88802',
    'key92079': 'value74034',
    'key38752': 'value82597',
    'key98609': 'value72367',
    'key17538': 'value84165',
    'key32604': 'value4654',
    'key16006': 'value2663',
    'key12811': 'value85014',
},
    {
    'id': 17527492093084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Kimberly Walker',
    'address': '1482 Allison Shoal\nEast Austin, IA 32614',
    'text': 'Quickly television add head. Plan respond talk toward record. Ball difficult movement sing.',
    'email': 'joseph02@example.com',
    'phone_number': '247.919.5519',
    'json': {
    'name': 'Mark Torres',
    'address': '493 Lauren Rue\nRyanfurt, LA 23632',
},
    'key87938': 'value86110',
    'key2430': 'value91634',
},
    {
    'id': 17527492093093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Brittany Pace',
    'address': 'Unit 4216 Box 0664\nDPO AA 19330',
    'text': 'Upon general nothing sing when design student. Similar board with ago. Edge young responsibility instead recent.',
    'email': 'kwilson@example.com',
    'phone_number': '+1-520-813-8914x652',
    'json': {
    'name': 'Stacey Garrett',
    'address': '88656 Potter Glen\nLauriehaven, IA 37148',
},
    'key34283': 'value83034',
    'key48192': 'value91427',
    'key39584': 'value73220',
    'key34067': 'value82155',
},
    {
    'id': 17527492093102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Jessica Conway',
    'address': '440 Jasmine Fords\nPort Michaelberg, MP 63062',
    'text': 'Author never conference experience entire. Would environment chance realize safe.\nImage small society alone high look clearly. Out poor smile reason security matter scene.',
    'email': 'mitchelltara@example.com',
    'phone_number': '3193569158',
    'json': {
    'name': 'Sergio Thomas',
    'address': '925 Leon Lodge Apt. 859\nSouth Shannon, NE 81453',
},
    'key32543': 'value77149',
},
    {
    'id': 17527492093113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Angela Davis',
    'address': '0129 Davis Mall\nDerekview, AS 63910',
    'text': 'Respond reduce nice natural very. Century development character former black wrong radio. Stop learn late parent seat rest offer. Learn consumer organization figure nation human.',
    'email': 'nancy88@example.org',
    'phone_number': '972-209-8502x60076',
    'json': {
    'name': 'Christopher King',
    'address': '2060 Bruce Inlet Suite 772\nSouth Scott, AK 95449',
},
    'key42354': 'value54749',
    'key41440': 'value16351',
    'key49337': 'value92034',
    'key52818': 'value48170',
    'key68859': 'value83913',
    'key61891': 'value89341',
    'key81550': 'value81943',
    'key46261': 'value22442',
},
    {
    'id': 17527492093124,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Kevin Rowe',
    'address': '2058 Hunter Track Suite 519\nNorth Anthonyton, WV 29566',
    'text': 'Several treat phone street growth according.\nIf ready determine much join each. Three car here official bad.\nMilitary reality then test common. Couple experience son financial allow.',
    'email': 'hannahbecker@example.org',
    'phone_number': '772-391-8106',
    'json': {
    'name': 'Michael Huynh',
    'address': '595 Tina Village\nKimfurt, TX 14628',
},
    'key25264': 'value74928',
    'key92822': 'value37499',
    'key92424': 'value73611',
    'key44510': 'value75600',
    'key40880': 'value58278',
    'key85496': 'value84174',
    'key27383': 'value75773',
    'key74850': 'value28812',
    'key16589': 'value89583',
},
    {
    'id': 17527492093136,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Brandon Johnson',
    'address': '286 Megan Bypass Apt. 137\nJohnsonhaven, GU 84000',
    'text': 'No live keep customer. Cultural explain push half card above late. Trip hard air son upon like. Question tax recent.',
    'email': 'sbradley@example.net',
    'phone_number': '(380)265-6527x397',
    'json': {
    'name': 'Richard Barrett',
    'address': '781 Jeanne Mission\nSouth Bianca, CO 01735',
},
    'key40555': 'value47075',
    'key58293': 'value85138',
    'key71695': 'value91631',
    'key46841': 'value55218',
    'key62428': 'value35325',
    'key83390': 'value59874',
    'key82457': 'value74180',
    'key3279': 'value21767',
},
    {
    'id': 17527492093151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Kristin Jackson',
    'address': '205 Martinez Manor Suite 775\nLake Pamelahaven, CA 32794',
    'text': 'Prove everything some team rest opportunity pass politics. Fine near indicate position. Half high human.',
    'email': 'danielsricardo@example.com',
    'phone_number': '882-395-6642x84832',
    'json': {
    'name': 'Sara Williams',
    'address': '0063 Elizabeth Field Apt. 485\nPort Victoria, UT 70970',
},
    'key84088': 'value12527',
    'key13361': 'value3620',
    'key18354': 'value1965',
    'key56878': 'value32381',
    'key67061': 'value75197',
    'key23711': 'value16774',
    'key25575': 'value42822',
},
    {
    'id': 17527492093163,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Joseph Good',
    'address': '4570 Alexis Harbor Suite 892\nMichaelbury, NV 10392',
    'text': 'Eight professional list worker and buy talk. Kid unit field establish half create yard. Down town condition charge relationship maybe. Entire herself because order meet run design.',
    'email': 'figueroaalfred@example.org',
    'phone_number': '511-250-6914x57707',
    'json': {
    'name': 'Alexander Nicholson',
    'address': '820 Evan Ways\nNew Thomas, KS 90046',
},
    'key68930': 'value54701',
    'key80988': 'value28013',
    'key37601': 'value87989',
    'key43283': 'value3184',
},
    {
    'id': 17527492093174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Stephanie Bradford',
    'address': '472 Kristen Trafficway Suite 216\nSouth Elizabeth, WY 43323',
    'text': 'Worry what stand very reach decision where. Natural high see few serious.\nName agreement series. Real growth ahead alone simply remain despite. End detail structure newspaper.',
    'email': 'xcampbell@example.org',
    'phone_number': '+1-671-665-3062x1473',
    'json': {
    'name': 'Donna Garcia',
    'address': '816 Mcgee Lakes\nWest Sheriberg, MD 49148',
},
    'key50213': 'value47066',
    'key79448': 'value62474',
    'key38211': 'value58704',
    'key8916': 'value28688',
    'key24668': 'value51253',
    'key21132': 'value52813',
    'key74414': 'value31449',
    'key67389': 'value15161',
    'key32856': 'value7058',
},
    {
    'id': 17527492093185,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Jason Gallagher',
    'address': '1061 Bender Heights Apt. 339\nColeton, OK 91465',
    'text': 'Management ability certain lay meeting five popular. Ahead safe win.\nVote though prove first east pay. According college stuff series. Carry threat bar first cup for.',
    'email': 'barrettvictoria@example.net',
    'phone_number': '816-807-8837x7261',
    'json': {
    'name': 'Mark Martinez',
    'address': 'Unit 5234 Box 6532\nDPO AE 03511',
},
    'key82695': 'value4885',
    'key4567': 'value32361',
    'key6531': 'value43604',
    'key73244': 'value12608',
    'key42297': 'value85975',
    'key92573': 'value55065',
    'key45290': 'value22045',
    'key63097': 'value71666',
    'key96440': 'value95123',
},
    {
    'id': 17527492093196,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Melvin Wright',
    'address': '877 Melvin Knolls\nPort Reneeberg, VA 44866',
    'text': 'Him or themselves idea yes want base past. Then recognize white toward mean.\nEconomy sure air front why.\nPoint in leave teach notice easy. Bit professor admit candidate natural various.',
    'email': 'etaylor@example.org',
    'phone_number': '001-518-553-3482',
    'json': {
    'name': 'Julie Crawford',
    'address': '5415 William Park\nJamesside, KS 13205',
},
    'key86138': 'value64463',
    'key35034': 'value45312',
    'key91489': 'value10434',
    'key56112': 'value28955',
    'key2934': 'value68036',
    'key43789': 'value89412',
    'key28373': 'value73446',
    'key84222': 'value7456',
    'key73910': 'value38450',
},
    {
    'id': 17527492093206,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Devin Miller',
    'address': '258 Johnston Harbor Apt. 767\nRobertburgh, ND 76805',
    'text': 'Age wrong same get world. Teach treatment energy ask performance whom news. Network ok style very. North half project.',
    'email': 'imartinez@example.org',
    'phone_number': '883.672.2100',
    'json': {
    'name': 'April Fisher',
    'address': '81409 Steven Point Apt. 001\nLake Jessica, ID 20666',
},
    'key89799': 'value89407',
    'key5727': 'value35284',
    'key22892': 'value25753',
    'key30135': 'value20054',
    'key24536': 'value5920',
    'key37267': 'value60651',
    'key11405': 'value35748',
    'key96121': 'value43206',
    'key82153': 'value9998',
},
    {
    'id': 17527492093217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Andrew Daniels',
    'address': '969 Mcconnell Stream\nWest Tony, WY 47207',
    'text': 'People member sister partner. Happy party song difficult stop take force.\nOil unit half put memory heart about. Body benefit heavy. Exist above goal family.',
    'email': 'howelldavid@example.org',
    'phone_number': '246.727.6927',
    'json': {
    'name': 'Tanya Miller',
    'address': '29703 Madison Estate\nLake Keith, PR 65302',
},
    'key16782': 'value87640',
    'key51203': 'value6159',
    'key85034': 'value85655',
    'key70462': 'value76239',
    'key90376': 'value62211',
    'key97263': 'value91505',
    'key74801': 'value74540',
    'key7291': 'value72844',
},
    {
    'id': 17527492093229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Jose Mora',
    'address': '4535 Mills Coves Suite 683\nEast Nicholasstad, CA 38312',
    'text': 'Around send course per that seat door. Director suddenly worry like population society protect. Care citizen computer sure.',
    'email': 'anita39@example.com',
    'phone_number': '001-693-713-6779x3620',
    'json': {
    'name': 'Suzanne Becker',
    'address': '9792 Holly Rue\nLake Loriport, FL 92014',
},
    'key92830': 'value79590',
    'key21534': 'value17251',
    'key47744': 'value90611',
    'key31757': 'value64718',
},
    {
    'id': 17527492093239,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Victoria Harmon',
    'address': '45377 Ayala Groves\nWest Theresa, ME 52653',
    'text': 'Represent can nor win like two. Call ask others policy tell gas. Arm cut before fine on think.',
    'email': 'traci95@example.net',
    'phone_number': '001-944-883-7086x46352',
    'json': {
    'name': 'Anthony Gonzalez',
    'address': '37358 Molina Harbors\nAshleyfort, ND 72722',
},
    'key36372': 'value6157',
    'key19453': 'value53786',
    'key24838': 'value41827',
    'key6703': 'value82415',
    'key42022': 'value30767',
    'key25191': 'value38888',
    'key36675': 'value12363',
    'key56689': 'value56549',
},
    {
    'id': 17527492093250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Lisa Dawson',
    'address': 'PSC 8335, Box 8677\nAPO AP 90990',
    'text': 'Catch guy body term position provide listen. Fine region state near stuff.\nPm fine child physical air against affect. Foreign generation evening trouble.',
    'email': 'dgordon@example.com',
    'phone_number': '986.798.3975',
    'json': {
    'name': 'Marcus Hansen',
    'address': '823 Coleman Ranch\nLake Daniel, IA 76276',
},
    'key17981': 'value2993',
    'key4844': 'value14383',
},
    {
    'id': 17527492093259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Isabella Johnson',
    'address': '84453 Howard Vista Apt. 309\nSmithville, MP 81609',
    'text': 'Bag once especially. Age police score art describe heavy beautiful.\nHer from daughter expert practice. Behavior only matter recognize us. Deep interview thus view.',
    'email': 'oferguson@example.net',
    'phone_number': '(456)833-1119',
    'json': {
    'name': 'John Martinez',
    'address': '08197 Rebecca Lights Apt. 703\nNew Mark, GU 74260',
},
    'key7472': 'value32824',
    'key52946': 'value46479',
    'key7930': 'value89730',
},
    {
    'id': 17527492093270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Jennifer Carson',
    'address': 'Unit 9612 Box 4741\nDPO AP 08240',
    'text': 'She third industry machine everyone beyond. Phone scene break rather member. Memory senior adult image score.\nMillion available himself threat course.',
    'email': 'huangjennifer@example.net',
    'phone_number': '001-851-789-7189x54825',
    'json': {
    'name': 'Katelyn Wilson',
    'address': '4046 Barnett Knolls\nEast Karenbury, UT 93432',
},
    'key77368': 'value23528',
    'key56035': 'value2664',
    'key38252': 'value53361',
    'key77033': 'value62765',
    'key12791': 'value84199',
    'key1843': 'value69481',
    'key72634': 'value92308',
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
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'address',
    'uid',
    'email',
    'vector',
    'json',
],
    'filter': 'uid in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199]',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/delete"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/delete")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/delete'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
    'filter': 'id in [17527492091102, 17527492091117, 17527492091130, 17527492091141, 17527492091151, 17527492091161, 17527492091172, 17527492091184, 17527492091195, 17527492091207, 17527492091216, 17527492091227, 17527492091238, 17527492091249, 17527492091260, 17527492091271, 17527492091283, 17527492091293, 17527492091305, 17527492091317, 17527492091327, 17527492091337, 17527492091349, 17527492091361, 17527492091372, 17527492091384, 17527492091395, 17527492091406, 17527492091415, 17527492091426, 17527492091437, 17527492091448, 17527492091458, 17527492091468, 17527492091479, 17527492091490, 17527492091501, 17527492091513, 17527492091524, 17527492091535, 17527492091547, 17527492091559, 17527492091568, 17527492091579, 17527492091589, 17527492091600, 17527492091612, 17527492091623, 17527492091634, 17527492091646, 17527492091656, 17527492091666, 17527492091677, 17527492091686, 17527492091696, 17527492091707, 17527492091718, 17527492091730, 17527492091741, 17527492091751, 17527492091760, 17527492091770, 17527492091781, 17527492091792, 17527492091804, 17527492091814, 17527492091825, 17527492091836, 17527492091847, 17527492091858, 17527492091866, 17527492091878, 17527492091886, 17527492091897, 17527492091908, 17527492091919, 17527492091930, 17527492091942, 17527492091953, 17527492091964, 17527492091975, 17527492091986, 17527492091997, 17527492092009, 17527492092020, 17527492092031, 17527492092043, 17527492092054, 17527492092066, 17527492092078, 17527492092090, 17527492092101, 17527492092110, 17527492092121, 17527492092130, 17527492092141, 17527492092151, 17527492092162, 17527492092171, 17527492092182]',
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
    'filter': 'id in [17527492091102, 17527492091117, 17527492091130, 17527492091141, 17527492091151, 17527492091161, 17527492091172, 17527492091184, 17527492091195, 17527492091207, 17527492091216, 17527492091227, 17527492091238, 17527492091249, 17527492091260, 17527492091271, 17527492091283, 17527492091293, 17527492091305, 17527492091317, 17527492091327, 17527492091337, 17527492091349, 17527492091361, 17527492091372, 17527492091384, 17527492091395, 17527492091406, 17527492091415, 17527492091426, 17527492091437, 17527492091448, 17527492091458, 17527492091468, 17527492091479, 17527492091490, 17527492091501, 17527492091513, 17527492091524, 17527492091535, 17527492091547, 17527492091559, 17527492091568, 17527492091579, 17527492091589, 17527492091600, 17527492091612, 17527492091623, 17527492091634, 17527492091646, 17527492091656, 17527492091666, 17527492091677, 17527492091686, 17527492091696, 17527492091707, 17527492091718, 17527492091730, 17527492091741, 17527492091751, 17527492091760, 17527492091770, 17527492091781, 17527492091792, 17527492091804, 17527492091814, 17527492091825, 17527492091836, 17527492091847, 17527492091858, 17527492091866, 17527492091878, 17527492091886, 17527492091897, 17527492091908, 17527492091919, 17527492091930, 17527492091942, 17527492091953, 17527492091964, 17527492091975, 17527492091986, 17527492091997, 17527492092009, 17527492092020, 17527492092031, 17527492092043, 17527492092054, 17527492092066, 17527492092078, 17527492092090, 17527492092101, 17527492092110, 17527492092121, 17527492092130, 17527492092141, 17527492092151, 17527492092162, 17527492092171, 17527492092182]',
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
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
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



    def test_request_7(self):
        """测试请求 7 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
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



    def test_request_8(self):
        """测试请求 8 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
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



    def test_request_9(self):
        """测试请求 9 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '53cca3f0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_46_43_076016izoTLAAn',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[list]_1752749225.json')
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
    test = AllmilvusLogtestdeletevectorTestDeleteVectorByFilterPkFieldList1752749225Json()
    test.run_tests()
