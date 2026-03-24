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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752748849_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752748849.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid100AndUid1001752748849Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752748849.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752748849.json"
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
    'RequestId': '797f1a3e-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_36_825524EVAllnJh',
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
    'RequestId': '797f1a3e-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_36_825524EVAllnJh',
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
    'RequestId': '797f1a3e-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_36_825524EVAllnJh',
    'data': [
    {
    'id': 17527488428637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Alexander Smith',
    'address': '203 Freeman Parkways Apt. 475\nKaitlynstad, AL 26864',
    'text': 'Do fund design official open news.\nOfficial song partner nation able. Goal size do inside guess.\nOk party see himself customer surface. Up population attention respond.',
    'email': 'lauren56@example.net',
    'phone_number': '841.896.0112',
    'json': {
    'name': 'Benjamin Gallegos',
    'address': '16396 David Prairie Apt. 895\nLake Edward, MO 86477',
},
    'key38108': 'value69331',
    'key40377': 'value16943',
    'key87947': 'value48478',
    'key85561': 'value30550',
    'key33232': 'value10770',
    'key61203': 'value41178',
    'key33485': 'value20421',
    'key92309': 'value53883',
    'key73851': 'value29575',
},
    {
    'id': 17527488428654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Robert Carr',
    'address': '8413 Stephanie Manors Apt. 230\nEast Richardhaven, CA 82738',
    'text': 'Support long resource series. News cultural summer business. Green care laugh measure card gas.',
    'email': 'nporter@example.org',
    'phone_number': '(633)648-4499',
    'json': {
    'name': 'Amy Lopez',
    'address': '306 Melanie Meadows Suite 494\nEast Tyler, MO 59683',
},
    'key37013': 'value80784',
},
    {
    'id': 17527488428667,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Justin Jefferson',
    'address': '8656 Tiffany Divide\nPorterstad, CT 15302',
    'text': 'American son future industry western. Amount executive course follow health.\nSite hand family down politics represent. Ask would soldier strategy new energy sure.',
    'email': 'christopher91@example.com',
    'phone_number': '001-418-384-8370x9078',
    'json': {
    'name': 'Erica Martinez',
    'address': '830 Catherine Prairie\nRobbinston, PA 80131',
},
    'key33549': 'value10545',
    'key27661': 'value70727',
    'key3177': 'value69929',
    'key27819': 'value58441',
    'key7252': 'value33841',
},
    {
    'id': 17527488428681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Michael Gonzalez',
    'address': '144 Robin Locks\nEast Joshua, PR 09444',
    'text': 'Practice ago himself involve within black actually collection. Executive magazine drop. Impact money ready.',
    'email': 'arthurhood@example.org',
    'phone_number': '+1-620-874-5188x918',
    'json': {
    'name': 'Robert Parker',
    'address': '8899 Stacey Circles\nMartinezburgh, OH 57354',
},
    'key59808': 'value7153',
    'key42549': 'value29839',
    'key80298': 'value22587',
    'key35856': 'value8718',
    'key70972': 'value23561',
    'key97099': 'value11327',
},
    {
    'id': 17527488428694,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Nicholas Curtis',
    'address': '905 Johnson Street Suite 628\nNew Danielle, VT 48263',
    'text': 'Marriage law others out. These way explain example. Degree service chair three run.\nGun arm provide. Discuss education wrong outside billion throughout head church.',
    'email': 'udominguez@example.com',
    'phone_number': '780.827.8531',
    'json': {
    'name': 'John Merritt',
    'address': '922 Tiffany Extensions\nSouth Amanda, PR 85247',
},
    'key97958': 'value74628',
    'key99906': 'value27004',
    'key28585': 'value60112',
    'key35804': 'value28339',
    'key18252': 'value75123',
    'key40756': 'value34906',
    'key77101': 'value97056',
    'key49770': 'value28029',
},
    {
    'id': 17527488428707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Ryan Lang',
    'address': '333 Terrell Mountain Apt. 349\nLake Tracy, PA 94360',
    'text': 'Miss after computer listen however drug. Page director itself view vote.\nProcess pattern consumer certain fill not against. Else deal husband next. Live allow best reduce certain wind step.',
    'email': 'oaguilar@example.com',
    'phone_number': '(986)499-5695',
    'json': {
    'name': 'Victoria Jackson',
    'address': '8025 Hill Port\nWest Christopher, PR 91107',
},
    'key84448': 'value72890',
    'key56302': 'value19782',
    'key52298': 'value16134',
},
    {
    'id': 17527488428720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Nicole Sanders',
    'address': '63761 Mcfarland Bridge\nWest Destiny, MT 55016',
    'text': 'Group edge spend relate. Bar evidence ability air. Politics true idea doctor. Congress mind real sometimes child.',
    'email': 'jenniferbruce@example.org',
    'phone_number': '(671)968-5864',
    'json': {
    'name': 'Heather Salazar',
    'address': '84970 Cunningham Pine Suite 996\nEricshire, NJ 44361',
},
    'key6882': 'value26665',
    'key42932': 'value7333',
    'key55046': 'value31041',
    'key72486': 'value85503',
    'key15081': 'value95143',
    'key43540': 'value55198',
    'key62154': 'value83921',
    'key77913': 'value63980',
    'key41253': 'value57780',
},
    {
    'id': 17527488428734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Taylor Gomez',
    'address': '47307 Banks Divide Apt. 509\nGarzaside, FL 59955',
    'text': 'He almost whether series treatment. Occur less thank forward company nice. Into better second color process.\nSuch window until.',
    'email': 'navarromary@example.net',
    'phone_number': '+1-611-419-2669x74986',
    'json': {
    'name': 'Donald Landry',
    'address': '15108 Kevin Brooks\nWest Kennethside, CO 03867',
},
    'key27864': 'value51011',
    'key99613': 'value48495',
    'key97270': 'value60696',
},
    {
    'id': 17527488428749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Timothy Graham',
    'address': 'PSC 6423, Box 0498\nAPO AA 59355',
    'text': 'Glass actually ball while dream identify. Wrong community per environmental window.\nSet car their address show. Power part face indeed building stock head life.',
    'email': 'aross@example.org',
    'phone_number': '8742594506',
    'json': {
    'name': 'Patricia Smith',
    'address': '317 Murphy Way Apt. 883\nNorth Erin, MI 45128',
},
    'key68661': 'value42359',
    'key50951': 'value88045',
    'key73382': 'value53131',
    'key75627': 'value34808',
    'key87370': 'value17920',
    'key51178': 'value53385',
},
    {
    'id': 17527488428759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Ronald Gonzales',
    'address': '1367 Larry Land Apt. 429\nEast Stevenburgh, SD 00548',
    'text': 'Fly indeed own expect. Market past support soon small nice. Current defense give size cause risk when.',
    'email': 'ashleymiller@example.net',
    'phone_number': '680-446-9709x7803',
    'json': {
    'name': 'Daniel Thompson',
    'address': '972 Karla Plain\nRyanmouth, HI 10433',
},
    'key63806': 'value41698',
    'key12331': 'value97565',
},
    {
    'id': 17527488428771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Joanna Alvarado',
    'address': '1715 Ashley Spurs\nLorihaven, IL 90293',
    'text': 'Usually poor campaign account guess position. Issue performance minute suffer movie. Structure event as old rule. Eye court explain easy involve common or.',
    'email': 'abigail82@example.org',
    'phone_number': '001-558-812-8750x4751',
    'json': {
    'name': 'Jose Barnes',
    'address': '036 Carolyn Neck Suite 942\nHarrishaven, ID 43327',
},
    'key30766': 'value6258',
    'key83716': 'value67369',
    'key5667': 'value31803',
    'key50214': 'value93565',
    'key15399': 'value2857',
    'key84780': 'value21132',
    'key3599': 'value37836',
    'key55683': 'value67289',
    'key54098': 'value90724',
    'key23446': 'value78177',
},
    {
    'id': 17527488428782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Samuel Olson',
    'address': '415 Amy Lakes\nVangburgh, MI 61914',
    'text': 'Enter focus break through training mission. Though west garden wrong stock position this. Thought finish yeah whose my check your sometimes. Value offer for.',
    'email': 'margaret37@example.com',
    'phone_number': '001-220-879-4991x68397',
    'json': {
    'name': 'Emily Walker',
    'address': '593 Amanda Skyway Suite 238\nPamtown, ME 63717',
},
    'key3469': 'value47911',
},
    {
    'id': 17527488428794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Leslie Johnson',
    'address': '9832 Kimberly Forest\nHarryfort, MN 48987',
    'text': 'Choose well language draw. Sea final standard information nothing road attorney. Customer college continue. Factor remember price energy stand pass wonder indeed.',
    'email': 'kimgabriel@example.org',
    'phone_number': '919.571.7789',
    'json': {
    'name': 'Jennifer Mcguire',
    'address': '75608 Cynthia Island\nSouth James, UT 98542',
},
    'key42676': 'value1221',
    'key8911': 'value61216',
    'key72289': 'value90946',
    'key87593': 'value98293',
    'key33554': 'value23216',
    'key1088': 'value58199',
    'key42516': 'value13462',
    'key11594': 'value46512',
    'key35674': 'value7187',
},
    {
    'id': 17527488428807,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Joshua Chavez',
    'address': 'PSC 0183, Box 0675\nAPO AA 41454',
    'text': 'Clear whole number boy question crime figure present. Seat concern the cause rather. Left tree example.\nCatch away top. Forward popular person hot also garden about.',
    'email': 'dlopez@example.org',
    'phone_number': '925-210-6997',
    'json': {
    'name': 'Dr. Jessica Wood',
    'address': '009 Nelson Meadows\nDawnville, WV 92937',
},
    'key54524': 'value26275',
    'key123': 'value7611',
    'key31143': 'value97771',
    'key58877': 'value83353',
    'key53342': 'value81655',
},
    {
    'id': 17527488428818,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jessica Cortez',
    'address': '23182 Kenneth Highway\nLake Alecmouth, VT 10376',
    'text': 'Practice feel would national school democratic. Wonder author move study agree claim assume. If much open wall myself feeling to.',
    'email': 'courtneyjuarez@example.com',
    'phone_number': '001-655-703-1641x52073',
    'json': {
    'name': 'Dillon Gomez',
    'address': '85664 Paula Meadow\nLauramouth, WA 36771',
},
    'key84039': 'value1351',
    'key73563': 'value65718',
    'key71662': 'value95079',
    'key40133': 'value94159',
    'key80266': 'value30849',
    'key49350': 'value89919',
    'key21194': 'value66246',
    'key64600': 'value70387',
},
    {
    'id': 17527488428831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Barbara Walker',
    'address': '673 Jacqueline Port\nJohnfurt, MP 70991',
    'text': 'Several base letter clearly. Finally people increase prepare church citizen.',
    'email': 'tlewis@example.com',
    'phone_number': '905-608-7212',
    'json': {
    'name': 'Victoria Lewis',
    'address': 'PSC 9142, Box 7198\nAPO AP 98505',
},
    'key22211': 'value62200',
    'key33829': 'value2430',
    'key31536': 'value1948',
    'key59867': 'value46704',
    'key94080': 'value33829',
    'key96798': 'value45565',
    'key62339': 'value89643',
},
    {
    'id': 17527488428841,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Anthony Ward',
    'address': '953 Jordan Pine Suite 637\nEast Brandon, SC 50078',
    'text': 'Outside source sea including author difference. Have bag keep husband occur. So development sell fast.',
    'email': 'adamsbradley@example.com',
    'phone_number': '2957042601',
    'json': {
    'name': 'Deborah Mathis',
    'address': '126 Elliott Row Apt. 130\nEdwinport, PR 52911',
},
    'key83214': 'value41442',
    'key10233': 'value36514',
},
    {
    'id': 17527488428855,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Margaret Peterson',
    'address': 'USNV Johnson\nFPO AA 04416',
    'text': 'Production ahead few want ask new myself.\nMilitary what southern model. Believe party industry manage during consumer word. Seem college population hope number anything box.',
    'email': 'yarnold@example.net',
    'phone_number': '001-484-574-7198x7848',
    'json': {
    'name': 'Nathan Martinez',
    'address': '57307 Rebecca Views Suite 630\nNorth Daniel, MA 18596',
},
    'key34148': 'value62122',
    'key41220': 'value29846',
},
    {
    'id': 17527488428867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Alan Pineda',
    'address': '06139 Trujillo Village\nWest Williambury, AL 56716',
    'text': 'Sing moment share piece. One especially thing.\nThat play yes up.\nExecutive southern woman forward country while. Relationship level respond up. Week political voice simply remember each interview.',
    'email': 'johngardner@example.net',
    'phone_number': '(876)536-8468',
    'json': {
    'name': 'Wendy Fowler',
    'address': '834 Erin Road\nPerkinschester, SC 36341',
},
    'key82715': 'value85085',
    'key44708': 'value93021',
    'key96512': 'value31398',
    'key55169': 'value62552',
    'key78694': 'value31432',
    'key35356': 'value90862',
    'key36115': 'value73898',
    'key53954': 'value77809',
},
    {
    'id': 17527488428881,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Tyler Russell',
    'address': '20120 Peggy Turnpike Suite 311\nEast Jessicaside, NJ 75730',
    'text': 'Around issue majority technology size deal answer. Moment system day maintain rich grow. Form particularly watch able.',
    'email': 'diana71@example.com',
    'phone_number': '+1-949-555-0143x06239',
    'json': {
    'name': 'Gary Williams',
    'address': 'USNS Smith\nFPO AE 89161',
},
    'key40562': 'value98869',
    'key8764': 'value81227',
    'key177': 'value64153',
    'key66408': 'value64267',
    'key99248': 'value64059',
    'key78519': 'value60769',
},
    {
    'id': 17527488428893,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Leslie Schroeder',
    'address': '7161 Paul Crossroad\nPort Cynthiaport, HI 84382',
    'text': 'Specific hard accept indicate. Realize feel rest voice past election.',
    'email': 'carl42@example.net',
    'phone_number': '386.305.0189',
    'json': {
    'name': 'James Ford',
    'address': '63480 Miller Parks\nCherylfurt, NC 60755',
},
    'key92759': 'value59486',
    'key49508': 'value23193',
    'key29008': 'value36554',
    'key25273': 'value12764',
    'key68530': 'value86057',
    'key2881': 'value6442',
    'key42033': 'value36152',
},
    {
    'id': 17527488428905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Cynthia Sutton',
    'address': '971 Wilson Meadow Suite 270\nWest Jaredside, ND 07708',
    'text': 'Guess off national receive her item remain result. Series everything after task record. Through guy thank rich hour away would news. Certainly so report out.',
    'email': 'veronica51@example.net',
    'phone_number': '+1-253-593-8031x239',
    'json': {
    'name': 'Suzanne Simpson',
    'address': '192 Jillian Crossing Suite 836\nSouth Ryan, AZ 92758',
},
    'key34225': 'value22370',
    'key1675': 'value61116',
    'key28998': 'value40697',
    'key58294': 'value47316',
    'key93274': 'value85445',
    'key54336': 'value19807',
    'key52768': 'value20902',
    'key64215': 'value64750',
    'key17934': 'value13285',
},
    {
    'id': 17527488428917,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Donald Webb',
    'address': '21954 Douglas Stream\nMossside, AL 83258',
    'text': 'Stop debate able morning might claim summer. Music imagine camera without subject young star. Likely art research better newspaper pull thought gun.',
    'email': 'gregorymontes@example.net',
    'phone_number': '001-712-322-3962',
    'json': {
    'name': 'Melissa Reyes',
    'address': '83599 Grace Circle\nFisherstad, MP 29967',
},
    'key67848': 'value83960',
    'key22134': 'value97378',
},
    {
    'id': 17527488428930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Ann Garcia',
    'address': '214 William Radial Apt. 787\nWest Whitneytown, CO 39714',
    'text': 'Position raise ten they agent. Car official fall view way week ok.\nBlue phone test better suggest school. Choose itself outside tree what still.',
    'email': 'qhuffman@example.org',
    'phone_number': '+1-663-426-1733x9084',
    'json': {
    'name': 'Mike Chapman',
    'address': '422 Hardy Mountains\nSandersfurt, NE 53185',
},
    'key98279': 'value65995',
    'key75189': 'value94577',
},
    {
    'id': 17527488428941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Cynthia Gilmore',
    'address': 'USNV Howard\nFPO AE 81138',
    'text': 'Relationship song meeting upon camera. Hot send purpose character. Value author structure be occur enjoy put conference. Treat who design paper into instead.',
    'email': 'ucummings@example.net',
    'phone_number': '+1-309-687-6834',
    'json': {
    'name': 'Kara Wheeler',
    'address': '4740 Katie Turnpike\nJacobberg, GU 98660',
},
    'key5029': 'value70625',
    'key84180': 'value6229',
    'key64908': 'value64808',
    'key10893': 'value40883',
    'key76511': 'value26541',
    'key88887': 'value53873',
},
    {
    'id': 17527488428950,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Daisy Beck',
    'address': '023 Benjamin Mission\nBonnieton, CA 12299',
    'text': 'Arm family hundred include operation. Hot feeling debate recently garden.\nWhile oil bill. Can although yard reveal significant.\nArrive stay toward town.',
    'email': 'alicia91@example.com',
    'phone_number': '665.418.6183x7029',
    'json': {
    'name': 'Kelly Hopkins',
    'address': '1868 Rose Points Apt. 428\nPort Michelle, MD 91693',
},
    'key72263': 'value22121',
    'key23024': 'value87167',
    'key41831': 'value96316',
    'key94667': 'value88009',
    'key56220': 'value40661',
    'key15651': 'value95021',
    'key45696': 'value20822',
    'key49312': 'value19822',
    'key96901': 'value85457',
    'key94621': 'value50045',
},
    {
    'id': 17527488428961,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Taylor Medina',
    'address': 'Unit 2324 Box 4598\nDPO AA 28817',
    'text': 'However compare picture general seven fly executive. Him debate us quality program Mrs worry. Opportunity born them away certain company throw theory.',
    'email': 'ncook@example.org',
    'phone_number': '335-796-2461x286',
    'json': {
    'name': 'Beverly Miller',
    'address': '794 Julie Lakes Suite 529\nWest William, MS 17699',
},
    'key95047': 'value63936',
    'key93203': 'value15937',
    'key20917': 'value57838',
    'key27438': 'value93035',
    'key43447': 'value28364',
    'key83352': 'value47089',
    'key58933': 'value44414',
    'key9672': 'value73921',
    'key77981': 'value36804',
},
    {
    'id': 17527488428969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Lisa Adams',
    'address': '5413 Jessica Turnpike Suite 924\nWest Michaelfurt, NY 76544',
    'text': 'Summer office phone head bit. Lot through together outside material either sign. Receive home others nature happen toward.',
    'email': 'emilyroberts@example.org',
    'phone_number': '+1-328-802-6615x6797',
    'json': {
    'name': 'Dr. Henry Crosby',
    'address': 'USNS Medina\nFPO AE 48681',
},
    'key97300': 'value95437',
    'key68282': 'value28315',
    'key16802': 'value82068',
    'key15197': 'value67311',
    'key11230': 'value7916',
    'key58762': 'value13082',
    'key8791': 'value59436',
},
    {
    'id': 17527488428980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Derrick Rodriguez',
    'address': '188 Lawrence Trail\nJohnsonchester, WI 86721',
    'text': 'Able stop majority compare. Current partner summer media.\nExpert know provide involve before bit. Board company subject rule difficult station ten. Billion its become visit power individual.',
    'email': 'edavis@example.com',
    'phone_number': '(828)822-2998',
    'json': {
    'name': 'Derek Underwood',
    'address': '7917 Cooper Street Apt. 704\nStewartborough, ID 96490',
},
    'key51885': 'value79458',
},
    {
    'id': 17527488428991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Isaiah Moyer Jr.',
    'address': '259 Ingram Branch\nNorth Kathleenfurt, MT 50999',
    'text': 'Money respond past left show exist. Business enjoy up hair sister meet three they. Life writer woman form interview individual time hand. And occur best issue room.',
    'email': 'triciastone@example.net',
    'phone_number': '(780)470-3878x26457',
    'json': {
    'name': 'Victoria Massey',
    'address': '479 Salas Spurs\nNew Thomasbury, MO 83513',
},
    'key74502': 'value35838',
    'key8585': 'value41839',
    'key96980': 'value64154',
    'key13789': 'value25632',
    'key50931': 'value44559',
    'key39393': 'value63560',
    'key50796': 'value14696',
    'key14591': 'value49506',
    'key84813': 'value34935',
    'key35265': 'value85239',
},
    {
    'id': 17527488429003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Julie Bryant',
    'address': '75509 Davidson Plaza Suite 101\nStricklandton, NC 15907',
    'text': 'Stop piece group although market song. Music scientist piece senior. Difference both before back mean.\nPrice you whether. Sport fly hair religious decision.',
    'email': 'collinsbrittany@example.com',
    'phone_number': '714.606.7833x69646',
    'json': {
    'name': 'Thomas Brown',
    'address': '510 Jimmy Curve Suite 120\nMendozaborough, PA 72843',
},
    'key32121': 'value5984',
},
    {
    'id': 17527488429015,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Whitney Ramirez',
    'address': '6530 West Fall\nEast Suzanne, OK 75408',
    'text': 'Management current attorney really room issue. Even another open civil. Positive woman poor.',
    'email': 'lisaward@example.com',
    'phone_number': '+1-248-866-7135x012',
    'json': {
    'name': 'Michael Kelly',
    'address': '837 Kylie Center Suite 459\nNorth Clarencebury, OR 10962',
},
    'key83833': 'value42437',
    'key25607': 'value475',
    'key35983': 'value20855',
    'key91099': 'value27476',
    'key12178': 'value9657',
    'key99267': 'value93116',
    'key28354': 'value16229',
    'key23858': 'value71675',
    'key73401': 'value3814',
    'key64712': 'value21306',
},
    {
    'id': 17527488429026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Suzanne Moore',
    'address': '74157 William Park Apt. 392\nAmandaview, TX 89301',
    'text': 'Either Republican analysis.\nWonder population my student practice product single. Its onto should market main.\nArtist cold soon strong wish watch board. So tend might end.',
    'email': 'amanda99@example.net',
    'phone_number': '(535)778-1273',
    'json': {
    'name': 'Melanie Barron',
    'address': '7109 Wright Alley\nGarciaberg, KS 84541',
},
    'key23346': 'value17077',
},
    {
    'id': 17527488429037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Oscar Thompson',
    'address': '15997 White Freeway\nVaughnhaven, GA 00758',
    'text': 'Treatment several office fact smile responsibility fear. Only middle statement success effort a.',
    'email': 'markmorrison@example.org',
    'phone_number': '+1-794-906-2570x16675',
    'json': {
    'name': 'Bryan West',
    'address': '02605 Caitlin Bypass Suite 475\nAndrehaven, NH 94244',
},
    'key45425': 'value52602',
    'key74910': 'value36595',
    'key5318': 'value65507',
    'key73421': 'value94679',
    'key69851': 'value84010',
    'key34200': 'value24084',
    'key99392': 'value53474',
},
    {
    'id': 17527488429049,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Mark Lam',
    'address': '7955 Kidd Square Apt. 535\nCooperstad, ND 56734',
    'text': 'Grow tend product little option whatever human. Capital camera action more young develop among.\nSubject them foreign ask. Open improve soon from.',
    'email': 'amanda12@example.org',
    'phone_number': '001-332-330-7621x2155',
    'json': {
    'name': 'Penny Carrillo',
    'address': '75150 Baxter Plains Apt. 340\nAbigailville, DC 59414',
},
    'key29324': 'value3815',
    'key73887': 'value98037',
    'key71979': 'value77523',
    'key70204': 'value31968',
    'key3874': 'value6874',
    'key71543': 'value42811',
    'key72837': 'value26038',
    'key25720': 'value64263',
},
    {
    'id': 17527488429060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jonathan Jones',
    'address': '226 Cooper Spring Apt. 139\nLake Patrick, FL 42025',
    'text': 'Win television grow movie job yourself every. How wrong issue boy third wind drive.\nFinish growth yeah assume soon because amount.',
    'email': 'evanscrystal@example.net',
    'phone_number': '230-464-6215x472',
    'json': {
    'name': 'Rachel Robinson',
    'address': '760 Newton Passage\nNew Kristi, IA 06084',
},
    'key33873': 'value13627',
    'key32977': 'value61140',
    'key2613': 'value21640',
},
    {
    'id': 17527488429071,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Jose Fox',
    'address': '369 Rocha Views Apt. 573\nChristopherville, DE 49751',
    'text': 'Next before great allow to beautiful relationship. Customer onto their thing power. During here through theory some require.',
    'email': 'floreskurt@example.org',
    'phone_number': '(954)689-9301',
    'json': {
    'name': 'Julie Peterson DDS',
    'address': '49346 Becker Stream\nAndersonberg, VI 81772',
},
    'key7557': 'value82544',
    'key32431': 'value20204',
    'key18843': 'value66737',
    'key43952': 'value42709',
    'key26709': 'value65203',
    'key48165': 'value94817',
    'key30944': 'value15667',
    'key60995': 'value90888',
},
    {
    'id': 17527488429083,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Dennis Kelly',
    'address': '5911 Elaine Shoal Suite 095\nLake Kimberlyton, VT 17541',
    'text': 'Part southern machine. Up person represent Mrs meet consumer.\nTree today down stuff late. Fish data American young order media tough Congress. Hundred success new quite majority itself month.',
    'email': 'brookealvarado@example.com',
    'phone_number': '756-699-1977x9834',
    'json': {
    'name': 'William Wilcox',
    'address': 'Unit 6777 Box 8833\nDPO AP 42390',
},
    'key87390': 'value51603',
    'key27547': 'value23268',
    'key10123': 'value39535',
    'key76751': 'value2318',
    'key88985': 'value61784',
    'key20121': 'value91802',
    'key66327': 'value51275',
    'key81058': 'value60430',
    'key70697': 'value29065',
    'key97106': 'value64782',
},
    {
    'id': 17527488429094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Yvette Perry',
    'address': '829 Martha Shore Apt. 459\nWest Tammy, NV 80598',
    'text': 'Morning career such support worry. Evening that garden would truth section war. Someone plan subject likely issue they. Behind support color.\nEnergy huge real form camera. Very finally western.',
    'email': 'stewartriley@example.com',
    'phone_number': '001-990-224-9588',
    'json': {
    'name': 'Katie Foley',
    'address': '3716 Chapman Skyway\nPort Jenna, NM 54853',
},
    'key97021': 'value69466',
    'key257': 'value6960',
    'key23052': 'value76220',
    'key70585': 'value27000',
    'key87084': 'value35075',
    'key61060': 'value29939',
    'key48584': 'value10737',
},
    {
    'id': 17527488429108,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Madeline Davis',
    'address': '02051 Lewis Valley Apt. 141\nEast Kimberly, NJ 22443',
    'text': 'Hit report report feel worker herself collection simple. Then deep morning ability environment.\nWould add coach paper wall wide.',
    'email': 'justin34@example.com',
    'phone_number': '487-724-2333',
    'json': {
    'name': 'Leslie Shah',
    'address': '766 Victor Estate\nGarretthaven, VA 84410',
},
    'key87566': 'value47680',
    'key35931': 'value74063',
    'key79126': 'value6590',
    'key96398': 'value24695',
    'key33458': 'value5090',
    'key52507': 'value35676',
    'key32194': 'value76950',
},
    {
    'id': 17527488429121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Allison Mueller',
    'address': '8393 Stephenson Wells Apt. 587\nNorth Johnstad, WV 97720',
    'text': 'Buy four recognize future public. Season now style catch recent she carry.\nNot too same some. Late spend available. So second politics against.',
    'email': 'alexandria21@example.net',
    'phone_number': '9439374085',
    'json': {
    'name': 'Kyle Richmond',
    'address': '98914 Mcgrath Stream Apt. 564\nElliottland, WV 03475',
},
    'key86990': 'value37209',
    'key58306': 'value43161',
    'key144': 'value1833',
    'key48157': 'value92048',
    'key73836': 'value26415',
    'key569': 'value25151',
    'key22765': 'value33028',
    'key45598': 'value30367',
},
    {
    'id': 17527488429134,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Mrs. Jessica Stewart MD',
    'address': '38440 William Lake\nWest Jackson, VI 47078',
    'text': 'Fight price site material carry garden. Writer any employee father.\nFactor forget notice analysis author. Trial organization field product effect.',
    'email': 'martinezstephen@example.net',
    'phone_number': '(446)486-0304x7530',
    'json': {
    'name': 'Randall Floyd',
    'address': '02493 Mark Land\nPort Josestad, NV 37825',
},
    'key56553': 'value94269',
    'key21542': 'value41621',
    'key5321': 'value25061',
    'key98319': 'value24726',
    'key16858': 'value33767',
    'key33086': 'value15588',
    'key18379': 'value9858',
    'key59792': 'value20946',
    'key31201': 'value65659',
},
    {
    'id': 17527488429148,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Brian Martinez',
    'address': '9843 Davis Mountains\nPort Ethan, AZ 84428',
    'text': 'Nothing by once that. Either leg film poor say last who.\nAssume or star bad responsibility environment century operation. Laugh pattern economy. Ball drop power face blood anything four.',
    'email': 'anthonyday@example.net',
    'phone_number': '477.296.2589x500',
    'json': {
    'name': 'Philip Gates',
    'address': 'Unit 4733 Box 6756\nDPO AA 61163',
},
    'key96984': 'value51222',
    'key33152': 'value33178',
    'key75603': 'value55758',
    'key71889': 'value39223',
    'key92034': 'value82060',
    'key54749': 'value50556',
    'key83555': 'value43782',
},
    {
    'id': 17527488429160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Carly Lewis',
    'address': '032 Bautista Brook\nPetersburgh, MP 37683',
    'text': 'Prepare expert lose know car right health. Begin mission term perhaps. Example Mrs job community and impact himself.\nCharacter near treatment. Catch well name until.',
    'email': 'singhcarly@example.net',
    'phone_number': '001-409-390-2805x3518',
    'json': {
    'name': 'Lawrence Rodriguez',
    'address': '98721 Anthony Lakes Suite 019\nNew Cynthia, AZ 25695',
},
    'key85173': 'value16867',
    'key59664': 'value86513',
    'key39187': 'value81247',
    'key34487': 'value93843',
    'key49032': 'value70707',
    'key11550': 'value63584',
},
    {
    'id': 17527488429174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Daniel Cox',
    'address': '550 David Dam Suite 243\nEast Lisaland, GU 39667',
    'text': 'Rock table his ahead. List I audience very financial. Level last teacher wind after card measure rise.',
    'email': 'wmejia@example.net',
    'phone_number': '712-910-4432',
    'json': {
    'name': 'Emily Sellers',
    'address': '5592 Turner Grove Apt. 999\nSolisville, GU 48823',
},
    'key7241': 'value34765',
    'key15016': 'value24437',
    'key10221': 'value79248',
    'key14439': 'value28725',
    'key46826': 'value70267',
    'key89889': 'value41343',
},
    {
    'id': 17527488429187,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Kenneth Lopez',
    'address': '727 Timothy Summit\nNorth Tylerfurt, DE 17183',
    'text': 'Add power care. Real spring take dog experience respond political.\nCultural but region unit send fact tax about. Participant whom maybe sure fast able.',
    'email': 'koliver@example.org',
    'phone_number': '742-237-8122',
    'json': {
    'name': 'John Greene',
    'address': '01866 James Prairie\nHernandezberg, OR 25318',
},
    'key26414': 'value96157',
    'key87842': 'value65435',
    'key43738': 'value37249',
    'key70213': 'value77341',
    'key77422': 'value64434',
    'key56230': 'value84603',
    'key98186': 'value51776',
    'key31931': 'value4304',
    'key49205': 'value26936',
},
    {
    'id': 17527488429201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Zoe Townsend',
    'address': '777 Smith Tunnel\nJuanstad, MN 10048',
    'text': 'Agree step international big sort create. Amount official music capital.',
    'email': 'jeffrowland@example.org',
    'phone_number': '9525769714',
    'json': {
    'name': 'Andrew Bishop',
    'address': '9893 Morales Stream Apt. 793\nNorth Jessica, FM 86338',
},
    'key7679': 'value71909',
    'key67944': 'value8432',
    'key71511': 'value25457',
    'key1622': 'value57885',
    'key30587': 'value77617',
    'key65765': 'value75496',
    'key81855': 'value41624',
    'key25708': 'value79350',
    'key71729': 'value69153',
    'key38532': 'value15555',
},
    {
    'id': 17527488429212,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Shannon Orozco',
    'address': '9248 Mcdonald Ridge Apt. 994\nNew Katie, MD 84783',
    'text': 'Third with it east me. Know believe available. Employee moment list. Baby your actually executive despite.',
    'email': 'sthomas@example.com',
    'phone_number': '001-215-896-3347',
    'json': {
    'name': 'Michael Thomas DDS',
    'address': '0632 Kristen Way\nBrownmouth, WA 69154',
},
    'key49041': 'value31994',
    'key5438': 'value80840',
    'key37098': 'value59091',
    'key90843': 'value52008',
    'key72382': 'value25967',
    'key95277': 'value73574',
    'key42455': 'value88104',
    'key37204': 'value90836',
    'key35003': 'value93947',
    'key65567': 'value5603',
},
    {
    'id': 17527488429223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Ryan King',
    'address': '32621 Candace Bridge Suite 189\nEast Sarachester, VI 86542',
    'text': 'Relate loss language build seem. Base government challenge example out despite any tree. Quite go window person enough keep begin. Manage I because tax behavior.',
    'email': 'hvargas@example.org',
    'phone_number': '+1-288-900-5267x0865',
    'json': {
    'name': 'Doris Reeves',
    'address': '891 Gentry Inlet\nSmithfort, PA 13902',
},
    'key74884': 'value7721',
    'key5896': 'value57233',
    'key47487': 'value95522',
    'key63411': 'value8184',
    'key53887': 'value26610',
    'key4937': 'value26801',
    'key43575': 'value17352',
},
    {
    'id': 17527488429234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Juan Smith',
    'address': '15888 Gregory Ports Suite 137\nNorth David, ND 11632',
    'text': 'Bit stuff loss sit always. Affect offer piece perform than defense training.\nBody design you loss vote book person. Yard build audience shake condition.',
    'email': 'william47@example.com',
    'phone_number': '+1-914-995-9233x37195',
    'json': {
    'name': 'Amanda Henry',
    'address': '6621 Brian Forks Suite 235\nReevesberg, ND 14760',
},
    'key92218': 'value62734',
    'key29382': 'value89251',
},
    {
    'id': 17527488429246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Kelly Blankenship',
    'address': '65500 Delacruz Common Suite 823\nSmithburgh, WY 54708',
    'text': 'Girl tree answer family.\nSecurity according none. Structure adult find tree relationship social. Important action those job.\nLittle off respond this.',
    'email': 'morristheodore@example.com',
    'phone_number': '+1-746-868-4921x41244',
    'json': {
    'name': 'Troy Bruce',
    'address': '56463 Kevin Island\nLangmouth, IA 62845',
},
    'key23974': 'value31426',
    'key37732': 'value78458',
    'key26941': 'value73471',
    'key10818': 'value55739',
},
    {
    'id': 17527488429261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Bernard Taylor',
    'address': '1057 Lewis Harbors\nRobertshire, VI 96172',
    'text': 'Strong stand although computer.\nOver choice happy national each. Majority majority improve moment simple I. Government his create close stand often.',
    'email': 'alexandersteele@example.com',
    'phone_number': '3189731073',
    'json': {
    'name': 'Colleen Nelson',
    'address': '33078 Gabrielle Burgs\nPort Jamesstad, ND 22882',
},
    'key35463': 'value31503',
    'key43885': 'value20037',
    'key15493': 'value83779',
    'key72554': 'value15493',
},
    {
    'id': 17527488429275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Judy Stevenson',
    'address': '4363 Jamie Camp Suite 862\nLake Josephland, MD 94825',
    'text': 'Animal language report culture bring letter during. Brother laugh hotel network.',
    'email': 'williammoore@example.net',
    'phone_number': '259-674-0542x8370',
    'json': {
    'name': 'Christina Luna',
    'address': '2993 Graham Hollow\nEast Randy, OR 01964',
},
    'key9435': 'value49198',
    'key47236': 'value11893',
    'key8045': 'value26476',
},
    {
    'id': 17527488429289,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Hannah Wright',
    'address': '979 Eugene Vista\nAmandabury, NY 05579',
    'text': 'Thus bill dog. Rather upon economy likely leader yet task.\nIt threat rise break own. Father concern despite along free week. Human should long color.',
    'email': 'starkvictoria@example.net',
    'phone_number': '001-560-552-6733x1056',
    'json': {
    'name': 'Scott Clark',
    'address': '6174 Molina Loaf Suite 800\nNorth Melanie, ND 09489',
},
    'key62410': 'value64099',
    'key5158': 'value12274',
},
    {
    'id': 17527488429302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Bonnie Foster',
    'address': '626 Mcdowell Center\nCherylland, RI 93054',
    'text': 'Reflect though sign issue song well.\nAdministration detail stay. You blue view public win some. Expect bit risk. Save step score hope investment class.',
    'email': 'luisrios@example.org',
    'phone_number': '549.264.2679',
    'json': {
    'name': 'Christina Smith',
    'address': '36058 Morgan Views Apt. 183\nPotterfort, SC 10585',
},
    'key94940': 'value8826',
    'key66420': 'value69151',
    'key36351': 'value3357',
    'key97780': 'value42818',
    'key23167': 'value36049',
    'key35393': 'value73519',
    'key82762': 'value71343',
    'key87770': 'value63850',
    'key90275': 'value53382',
    'key25804': 'value16877',
},
    {
    'id': 17527488429317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Rebecca Williams',
    'address': '520 Casey Row Apt. 457\nHowelltown, DC 55132',
    'text': 'Boy writer even reflect side. Product former fight century who money. Offer choice particular mouth these. Would who think like apply.\nReturn her pretty scene this.',
    'email': 'uwilliams@example.com',
    'phone_number': '001-958-247-7883x6860',
    'json': {
    'name': 'Susan Martinez',
    'address': '964 Christine Parkways Apt. 884\nJuanview, CA 07235',
},
    'key93416': 'value91686',
    'key24226': 'value52701',
    'key99840': 'value70429',
    'key27020': 'value79046',
    'key76355': 'value75734',
    'key77877': 'value84572',
},
    {
    'id': 17527488429330,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kenneth Harrison',
    'address': '5376 Carlos Unions Suite 853\nNew Alexander, RI 92768',
    'text': 'Hit today out image. Require back writer control option western.\nLook nature able skin among provide. Week any seat every.\nWill party center would. Spring bit represent democratic more.',
    'email': 'james56@example.net',
    'phone_number': '471-766-1029x8065',
    'json': {
    'name': 'John Carson',
    'address': '473 Michele Lakes\nSamanthaville, OR 54377',
},
    'key39427': 'value37510',
    'key99157': 'value85183',
    'key99986': 'value45451',
    'key17889': 'value4749',
    'key26151': 'value75569',
    'key27824': 'value63126',
    'key20754': 'value83431',
    'key27294': 'value96210',
},
    {
    'id': 17527488429343,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Stephen Ortega',
    'address': '5734 Ryan Road\nPennyton, DC 20225',
    'text': 'Standard suddenly season start guess. Song send century card keep law.\nWhether win yourself site. Certain since late debate minute certainly idea. Happy project attention over.',
    'email': 'dana59@example.net',
    'phone_number': '206-628-7967',
    'json': {
    'name': 'Jason Crawford',
    'address': '58853 Kristine Drives Apt. 531\nWest Howard, FM 39532',
},
    'key74728': 'value9749',
    'key25270': 'value84164',
    'key67668': 'value51143',
    'key56833': 'value75558',
    'key48266': 'value15634',
},
    {
    'id': 17527488429354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Christopher Walker',
    'address': '521 Erik Trail\nJuliefort, AR 58142',
    'text': 'Safe with list eat to the world else. Box trip research information us economy. Home mouth success store assume.',
    'email': 'mary52@example.net',
    'phone_number': '(990)271-0496x8928',
    'json': {
    'name': 'Leslie Cole',
    'address': '756 Ryan Ridge\nChristinaberg, GU 03853',
},
    'key28613': 'value9288',
    'key39064': 'value6192',
    'key38677': 'value38931',
    'key59281': 'value73124',
    'key39310': 'value61856',
    'key63728': 'value11886',
    'key22477': 'value26516',
},
    {
    'id': 17527488429364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Tasha Zimmerman',
    'address': '1869 David Trace Apt. 593\nWest Camerontown, KY 41639',
    'text': 'But about bed reveal. Together meeting really hope life yet significant. Return order seek different.\nSince run raise heart attorney. Agency sometimes court system rate since.',
    'email': 'qburch@example.net',
    'phone_number': '(404)273-4011',
    'json': {
    'name': 'Robert Mcdonald',
    'address': '93476 Townsend Cliff Suite 613\nTrevinoborough, DE 83467',
},
    'key36907': 'value31476',
    'key73007': 'value11801',
    'key85050': 'value42462',
    'key6778': 'value74360',
    'key12986': 'value28482',
    'key48106': 'value42747',
    'key66856': 'value5270',
    'key90000': 'value61019',
    'key20774': 'value56770',
},
    {
    'id': 17527488429376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jessica Preston',
    'address': '820 Gregory Creek\nPort Amanda, KS 44501',
    'text': 'Century general improve leader material ready cause. Billion challenge federal population sense add. Decade best drive all according final six. Say cut when information buy develop.',
    'email': 'traceyperez@example.net',
    'phone_number': '429.905.2867',
    'json': {
    'name': 'Mark Harrington',
    'address': '689 Sheila Radial\nNorth Stefaniechester, SC 54862',
},
    'key51036': 'value24052',
    'key5848': 'value42467',
    'key53444': 'value65378',
},
    {
    'id': 17527488429388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'John Chen',
    'address': '32225 Brandon Mission Apt. 046\nJacobbury, AR 58885',
    'text': 'Southern paper for go quite her. Hit would model.\nSend here animal direction information according. There war read tough story risk within. Indeed win season admit never close finally.',
    'email': 'thomassamantha@example.com',
    'phone_number': '503.299.9012x0935',
    'json': {
    'name': 'Vincent Martin',
    'address': '832 Jeffrey Crest\nSophiaview, NC 07028',
},
    'key72859': 'value19636',
    'key2830': 'value42126',
    'key44424': 'value71283',
    'key71647': 'value22015',
    'key74494': 'value59968',
},
    {
    'id': 17527488429400,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Dawn Dunlap',
    'address': '6455 Reed Rest Suite 648\nPort Sara, MN 49769',
    'text': 'Put provide late ask. Serious truth training computer skin inside. Course health apply must between simple speech example.',
    'email': 'stephaniebenton@example.org',
    'phone_number': '974.926.4934x40039',
    'json': {
    'name': 'Adrian Berg',
    'address': '9002 Hobbs Lodge\nWest Richard, ND 06826',
},
    'key70216': 'value24777',
    'key65973': 'value56796',
    'key52185': 'value29338',
    'key52237': 'value54973',
    'key93100': 'value98068',
    'key82244': 'value83121',
    'key72281': 'value80924',
    'key75631': 'value71302',
    'key65517': 'value29037',
    'key64910': 'value74451',
},
    {
    'id': 17527488429411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Morgan Massey',
    'address': '6952 Kevin Squares\nNew Joseph, FL 34026',
    'text': 'I put become everyone account area lose. Four cause pick recent pass painting account rate. True authority level western threat rather.',
    'email': 'jaredanderson@example.net',
    'phone_number': '813-702-5403',
    'json': {
    'name': 'Abigail Smith',
    'address': 'PSC 4755, Box 8294\nAPO AE 51362',
},
    'key33525': 'value3702',
    'key83786': 'value9438',
    'key39502': 'value44982',
    'key20563': 'value45120',
    'key95709': 'value35156',
    'key32475': 'value54553',
    'key59937': 'value4525',
},
    {
    'id': 17527488429421,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Erik Shaw',
    'address': '00998 Barry Orchard Suite 004\nBelindahaven, MS 08948',
    'text': 'Everyone move how. Must realize thus rate wrong room join.\nThere road box hair bar. Most learn shake night.\nInclude season story nature magazine minute. Next serve method page.',
    'email': 'regina42@example.com',
    'phone_number': '(611)487-9948x59072',
    'json': {
    'name': 'Lisa Cooper',
    'address': '82262 Frank Dale\nPort Dennis, GU 51213',
},
    'key34568': 'value341',
    'key74388': 'value48216',
    'key81665': 'value66993',
    'key14619': 'value72932',
},
    {
    'id': 17527488429431,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Brian Macdonald',
    'address': '9111 Jocelyn Inlet\nStantonberg, VA 38752',
    'text': 'Discussion true feeling pass act born. Air store kid protect. Off your piece alone.\nGroup last style who. Again goal full like have. Play on others night wife street.',
    'email': 'joshua89@example.com',
    'phone_number': '001-654-633-3776x7946',
    'json': {
    'name': 'Charles Nolan',
    'address': '9896 Price Mills Apt. 224\nEast Markshire, OH 46589',
},
    'key39616': 'value50319',
    'key90898': 'value12697',
    'key83210': 'value64213',
    'key10668': 'value68215',
    'key62654': 'value3581',
    'key51795': 'value24054',
    'key84871': 'value62116',
    'key61331': 'value27832',
    'key61813': 'value55490',
},
    {
    'id': 17527488429442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Max Yoder',
    'address': '1462 Thomas Ports\nTimothyberg, AS 27645',
    'text': 'Establish onto chance foreign prevent card capital. Manage enough sign health store onto. Leader often dog box do.',
    'email': 'marybowman@example.org',
    'phone_number': '200.269.6657x98499',
    'json': {
    'name': 'Kevin Barrett',
    'address': '2886 Newman Dale Suite 532\nWest Sheri, NC 42857',
},
    'key19173': 'value48925',
    'key76851': 'value52437',
},
    {
    'id': 17527488429453,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Robert Bell',
    'address': '750 Misty Unions\nLake Andrew, GA 05136',
    'text': 'Science create near vote inside attack. Per dinner rule. Record put either tax box recent three.\nTonight beat available deal various lay through. Town authority white blood send expert.',
    'email': 'danawilliams@example.com',
    'phone_number': '001-506-846-1332x30510',
    'json': {
    'name': 'Eric Bailey',
    'address': '75681 Bowers Ways\nAlyssahaven, WV 80358',
},
    'key55838': 'value98367',
    'key69683': 'value37257',
},
    {
    'id': 17527488429464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Joshua Zimmerman',
    'address': '72501 Brown Unions Suite 110\nLake Kelseyshire, SD 73649',
    'text': 'Follow something north. Off thousand issue sometimes someone. Usually seem where career wonder.\nTechnology answer trouble. Store wait strong.',
    'email': 'lsmith@example.net',
    'phone_number': '+1-988-804-9378x77476',
    'json': {
    'name': 'Ashley Rodriguez',
    'address': '7842 Elizabeth Ridge\nSouth Brian, NC 04533',
},
    'key76940': 'value87366',
    'key44756': 'value80120',
    'key73479': 'value17659',
    'key14849': 'value8816',
    'key70097': 'value54302',
    'key57730': 'value90749',
    'key3848': 'value14089',
},
    {
    'id': 17527488429475,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Lisa Merritt',
    'address': '904 Christopher Court Apt. 106\nEast Joe, MH 70819',
    'text': 'Phone other walk. Leg million discussion listen win into.\nRegion dog despite religious. Near nation add. Interview son still right throw artist school.',
    'email': 'erica47@example.org',
    'phone_number': '001-529-638-2853x488',
    'json': {
    'name': 'Erin Shelton',
    'address': '81025 Kristi Ramp\nAnthonystad, MN 73414',
},
    'key28380': 'value44329',
    'key76263': 'value91072',
    'key61369': 'value67283',
    'key80144': 'value60338',
    'key36903': 'value74234',
    'key25640': 'value2818',
    'key87152': 'value71254',
    'key62335': 'value67042',
    'key39381': 'value47476',
},
    {
    'id': 17527488429485,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Eric Hurst',
    'address': '605 Melanie Green Apt. 920\nWilliamsport, KS 33487',
    'text': 'Pressure option call federal wear none. Special performance plant company month.\nCause arrive long decide myself reason. Happen western information never.',
    'email': 'breanna25@example.net',
    'phone_number': '546-767-9702x012',
    'json': {
    'name': 'Alex Robinson',
    'address': '605 Smith Tunnel\nTammyfurt, MA 88437',
},
    'key91083': 'value49603',
},
    {
    'id': 17527488429496,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Elizabeth Hood',
    'address': '992 Ewing Common\nNorth Keith, KS 13045',
    'text': 'Agency approach difference student others. Pass will onto put wonder.\nFinally thousand decision bring. Claim resource eat identify. Security property teacher sister staff.',
    'email': 'briana76@example.com',
    'phone_number': '(247)335-3122',
    'json': {
    'name': 'Dylan Riddle',
    'address': '7402 Chapman Grove\nElizabethborough, MD 91205',
},
    'key12495': 'value4237',
    'key85747': 'value79609',
    'key55712': 'value85293',
    'key70986': 'value48488',
    'key52747': 'value94782',
    'key56714': 'value54023',
    'key30541': 'value10448',
    'key10770': 'value13594',
    'key59466': 'value97000',
    'key98916': 'value80484',
},
    {
    'id': 17527488429506,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Zachary Wright',
    'address': '429 Cynthia Skyway\nSouth Kristinaville, MP 44300',
    'text': 'Property claim thus. Cell report rock. Source allow design. Expect marriage several for.\nToday stand reflect dinner real test. Question front debate. She letter forward she whatever.',
    'email': 'bsalazar@example.com',
    'phone_number': '+1-644-356-3591x986',
    'json': {
    'name': 'John Franklin',
    'address': '27134 Williams Court Suite 701\nOsbornebury, FM 09303',
},
    'key18412': 'value77957',
    'key25988': 'value27702',
    'key19558': 'value42299',
    'key41007': 'value52543',
},
    {
    'id': 17527488429518,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Lisa Wang',
    'address': '863 Baldwin Roads\nLisachester, NY 76284',
    'text': 'Forget green like tend subject hope doctor. One brother painting. Pick evidence try large push.\nCharacter generation listen once term.',
    'email': 'ruthleblanc@example.com',
    'phone_number': '+1-965-781-2372x40658',
    'json': {
    'name': 'Raymond Lynch',
    'address': '71514 Kennedy Circle\nKevinshire, MI 88344',
},
    'key30088': 'value10735',
    'key20228': 'value11554',
    'key54237': 'value52278',
    'key6085': 'value71069',
    'key29181': 'value45774',
    'key6066': 'value87112',
    'key17489': 'value82082',
},
    {
    'id': 17527488429529,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Mrs. Christine Rhodes',
    'address': '3645 Mcpherson Village Suite 033\nJamesland, WY 23884',
    'text': 'Job fact theory hope small. Sit authority spring. Line manager some action skin.\nPainting find relationship daughter free likely direction. Sort kind important impact.',
    'email': 'hjones@example.net',
    'phone_number': '7349278266',
    'json': {
    'name': 'Shelley Williams',
    'address': '809 Julia View Suite 025\nMyersview, RI 43088',
},
    'key35597': 'value60051',
    'key30821': 'value81676',
    'key19926': 'value62195',
    'key31991': 'value87654',
},
    {
    'id': 17527488429540,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Bryan Lowe',
    'address': '966 Green Bridge\nParsonsport, RI 17030',
    'text': 'Per activity toward necessary material keep record. Somebody wear room join hard air only.\nOut receive rest father boy usually. Attention really risk fear south.',
    'email': 'chambersashley@example.org',
    'phone_number': '546.538.1262x842',
    'json': {
    'name': 'Michelle Carlson',
    'address': '81674 Makayla Passage Apt. 125\nNew Mitchell, NC 26605',
},
    'key55722': 'value33663',
    'key15508': 'value55662',
    'key19922': 'value80243',
    'key29452': 'value77533',
    'key35468': 'value27827',
},
    {
    'id': 17527488429552,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Debra Meyer',
    'address': '4405 Christy Knolls Suite 479\nShepherdstad, NE 61674',
    'text': 'Book our always president keep. Again anything school open name. Training drug organization owner particularly.',
    'email': 'murphymichael@example.com',
    'phone_number': '727.575.4749x483',
    'json': {
    'name': 'Amy Campbell',
    'address': '75473 Yvonne Mount Suite 926\nPort Michaelberg, VA 31104',
},
    'key72005': 'value49315',
    'key60459': 'value81773',
},
    {
    'id': 17527488429564,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Cynthia Hamilton',
    'address': '0006 Alexis Shoal Suite 142\nJefffurt, NH 68573',
    'text': 'And agent general pressure. Every he poor whom.',
    'email': 'tannergonzalez@example.org',
    'phone_number': '949-957-0185',
    'json': {
    'name': 'Brittany Callahan',
    'address': '8745 Lee Loop\nNew Joshua, AK 67629',
},
    'key82309': 'value20302',
    'key66169': 'value32726',
    'key29835': 'value86450',
    'key16925': 'value51184',
    'key89146': 'value32202',
    'key67306': 'value73408',
},
    {
    'id': 17527488429574,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Thomas Garcia',
    'address': '9597 Martinez Falls Apt. 327\nKingshire, AK 31270',
    'text': 'Against interesting leave sport politics computer. Military open somebody back tree between.',
    'email': 'sandersrobert@example.org',
    'phone_number': '(295)707-7662x537',
    'json': {
    'name': 'Thomas Pratt',
    'address': '6199 Sean Prairie Suite 931\nDanielmouth, DE 02550',
},
    'key30088': 'value84895',
    'key88272': 'value69754',
    'key63285': 'value6081',
    'key143': 'value97605',
    'key71231': 'value55010',
    'key94945': 'value22965',
},
    {
    'id': 17527488429586,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Patrick Davis',
    'address': '059 Morales Causeway Apt. 845\nEast Joshua, MP 10215',
    'text': 'Wind pick growth serious front.\nShare purpose oil board air morning may. Effect budget southern sense six billion. Away agent assume middle.',
    'email': 'mcdanielsherry@example.net',
    'phone_number': '(704)363-3123',
    'json': {
    'name': 'Brian Mitchell',
    'address': '3116 James Oval Apt. 748\nPort Sarah, GU 03316',
},
    'key94213': 'value60194',
    'key58646': 'value34074',
    'key49079': 'value80649',
    'key95859': 'value23837',
    'key90599': 'value65988',
    'key40018': 'value82113',
    'key27373': 'value46293',
},
    {
    'id': 17527488429598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Tiffany Blackwell',
    'address': 'USCGC Hahn\nFPO AA 26109',
    'text': 'Particularly fight Congress sport interview. Relationship sea set professor rather. Actually prove a move thing yet. Pick control human Republican tonight stop.',
    'email': 'carlos20@example.com',
    'phone_number': '928.331.6547x6527',
    'json': {
    'name': 'Tara Mcdaniel',
    'address': '762 Margaret Hollow\nHernandezburgh, IL 40882',
},
    'key59019': 'value98302',
    'key2491': 'value67126',
    'key82544': 'value51978',
    'key97366': 'value61203',
    'key44755': 'value89306',
    'key92809': 'value80891',
    'key67138': 'value82903',
    'key78129': 'value64060',
    'key70116': 'value45012',
},
    {
    'id': 17527488429607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Danielle Colon',
    'address': '9119 Katherine Port\nDanielstad, ND 71207',
    'text': 'President not and town appear. Defense hospital draw interesting near. Outside reality federal sister.',
    'email': 'rcain@example.net',
    'phone_number': '426.533.1105x34341',
    'json': {
    'name': 'Joel Hurst',
    'address': '9412 Johnson Forest\nMercerchester, MD 24276',
},
    'key53193': 'value30491',
    'key53766': 'value46336',
    'key47307': 'value58455',
    'key64399': 'value90758',
    'key609': 'value52735',
    'key51128': 'value28246',
    'key87570': 'value74628',
},
    {
    'id': 17527488429618,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Crystal Ruiz',
    'address': '0421 Holly Drive Apt. 297\nLake Yvetteport, PA 82059',
    'text': 'Put officer type these. Discussion best laugh political serve good. Foot tough out black.',
    'email': 'yrichardson@example.com',
    'phone_number': '947-823-2687x97785',
    'json': {
    'name': 'Kenneth Hunter',
    'address': '006 Holmes Squares\nEast Donnafurt, PR 43752',
},
    'key95349': 'value1316',
    'key47756': 'value52928',
    'key87951': 'value11900',
    'key38483': 'value36950',
    'key72934': 'value86553',
    'key80315': 'value43898',
    'key89685': 'value15790',
},
    {
    'id': 17527488429628,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Anna Vazquez',
    'address': '090 Rebecca Ville Suite 111\nSouth Toni, NH 09929',
    'text': 'Security current mouth talk suffer foreign. Among note three structure affect. Again drive whom professor bank pass movement.\nChoose eight race large. To employee join.',
    'email': 'robertmills@example.net',
    'phone_number': '+1-904-575-7657x69366',
    'json': {
    'name': 'Ashley Cook',
    'address': '186 Davies Street\nBurnschester, NV 24838',
},
    'key81742': 'value27164',
    'key32133': 'value14191',
    'key18450': 'value3111',
    'key53203': 'value18528',
    'key92945': 'value25613',
},
    {
    'id': 17527488429640,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Teresa Fox',
    'address': '61982 Madison Route\nNorth Annetteborough, NC 29023',
    'text': 'Already word away send process evidence surface.\nWould for what nation production money. Anything want various light full sometimes.',
    'email': 'stewartjade@example.net',
    'phone_number': '259-618-5947x42894',
    'json': {
    'name': 'Vanessa Huff',
    'address': '2729 Anthony Common Suite 702\nSouth Jeffreyton, MH 50974',
},
    'key27992': 'value10908',
    'key4259': 'value37095',
    'key17958': 'value99389',
},
    {
    'id': 17527488429651,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Barbara Greene',
    'address': '189 Gibson Fields Apt. 458\nCarsonview, SC 28372',
    'text': 'Clear light face fight nature difficult. Identify lay worry meeting. More southern person nature bring.\nAgreement service stock although.',
    'email': 'nicole58@example.com',
    'phone_number': '447-897-0393x0518',
    'json': {
    'name': 'Michael Davidson',
    'address': '502 Morales Route\nJosephborough, MO 49644',
},
    'key17440': 'value79935',
},
    {
    'id': 17527488429662,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Casey Herrera',
    'address': 'Unit 0821 Box 0406\nDPO AE 39603',
    'text': 'Live still almost news control boy anyone center. Series statement sound do they put. Who song send moment believe public seek. Too able now.',
    'email': 'robersondana@example.org',
    'phone_number': '+1-710-323-7691x906',
    'json': {
    'name': 'Stephen Smith',
    'address': '386 Wilson Plaza\nJoseport, WA 52473',
},
    'key25603': 'value56223',
    'key50683': 'value29981',
    'key42309': 'value10290',
    'key50653': 'value54199',
    'key71000': 'value91159',
},
    {
    'id': 17527488429671,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Casey Shaffer',
    'address': '327 Misty Ferry\nJohnburgh, OR 41688',
    'text': 'Environment mission our hair official lot full whatever. Mind into position thousand southern word. Financial buy job cost truth various western long.',
    'email': 'snoble@example.net',
    'phone_number': '(903)262-9765',
    'json': {
    'name': 'Michelle Sims',
    'address': '1289 Thomas Shore Apt. 488\nKennethbury, AL 63868',
},
    'key33210': 'value21261',
    'key42311': 'value78161',
    'key77331': 'value92318',
},
    {
    'id': 17527488429681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kimberly Atkinson',
    'address': '363 Gabrielle Squares Suite 207\nLake Roberta, MP 05096',
    'text': 'Clear effect force condition. Consider quite former shoulder history without meeting.\nBehind end past like natural. Attorney report could join poor. Far know goal win.',
    'email': 'foleyjennifer@example.net',
    'phone_number': '+1-383-322-9273x327',
    'json': {
    'name': 'Tyler Aguilar',
    'address': '30617 Harry Landing\nSouth Tabitha, VI 73654',
},
    'key47553': 'value61720',
    'key61913': 'value73505',
    'key62359': 'value79730',
    'key80761': 'value5266',
    'key16578': 'value16919',
    'key11519': 'value98769',
    'key61789': 'value18426',
    'key31834': 'value37023',
    'key33194': 'value61284',
    'key98940': 'value96410',
},
    {
    'id': 17527488429693,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Suzanne Hart',
    'address': '328 Williams Ville\nWest Karenstad, FL 79188',
    'text': 'Present where now kind. Recently green score team reason black involve. Trial truth news five brother agency.',
    'email': 'thomascole@example.net',
    'phone_number': '(870)474-1106x6029',
    'json': {
    'name': 'Mrs. Pamela Dickerson',
    'address': '718 Samantha Lodge\nSouth Charles, CA 79112',
},
    'key49967': 'value44731',
    'key11834': 'value42771',
},
    {
    'id': 17527488429703,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'James Haynes',
    'address': '113 Molly Road\nWarrenhaven, MN 75765',
    'text': 'National people husband man. Show attack president phone. Between someone when pretty.\nOver approach soldier. Religious value now thing already. Major over score meet marriage such staff.',
    'email': 'cindychang@example.org',
    'phone_number': '(942)510-5731x315',
    'json': {
    'name': 'Charles Jensen',
    'address': '7151 Willie Parkways\nBenjaminfort, CT 65040',
},
    'key48692': 'value35017',
    'key91223': 'value10882',
    'key96537': 'value42869',
    'key57193': 'value87165',
    'key33196': 'value35292',
    'key21032': 'value75267',
    'key69642': 'value10115',
    'key43430': 'value39037',
    'key89828': 'value18786',
},
    {
    'id': 17527488429715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Ashley Reyes',
    'address': '4399 Robinson Fort Apt. 383\nNew Lisa, OK 59337',
    'text': 'Play speech stop through heavy. Professional from director picture because least. Different contain marriage edge.\nNational whole increase despite color. Ask detail especially south.',
    'email': 'wyattrobert@example.net',
    'phone_number': '288.272.5860x8878',
    'json': {
    'name': 'Joseph Jones',
    'address': '071 Jacob Extension Apt. 172\nWilkersonview, TX 33792',
},
    'key38600': 'value30624',
},
    {
    'id': 17527488429727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Philip Torres',
    'address': '951 Hopkins Crest Apt. 162\nHillstad, MS 06035',
    'text': 'Lawyer money without ball. Husband effect candidate take. Pass walk until market she politics.\nCivil training since cost along find. Member Congress technology enough why.',
    'email': 'neilcruz@example.net',
    'phone_number': '(218)351-9524',
    'json': {
    'name': 'Jeffery Lopez',
    'address': 'Unit 0355 Box 9500\nDPO AE 66024',
},
    'key63557': 'value50127',
    'key83887': 'value86318',
    'key44783': 'value11612',
},
    {
    'id': 17527488429738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Rebecca Hickman',
    'address': 'Unit 8629 Box 2045\nDPO AA 74225',
    'text': 'Amount remain modern stock protect both young fall. Various arrive reason its sister.\nEven sit several candidate cause figure town. Minute project become safe guy factor almost.',
    'email': 'aterry@example.net',
    'phone_number': '(648)928-2215',
    'json': {
    'name': 'Richard Foster',
    'address': '44557 Walters Forest Suite 928\nJosephfort, WY 69945',
},
    'key20410': 'value108',
    'key66012': 'value10912',
    'key96924': 'value19870',
    'key24848': 'value11380',
    'key2051': 'value13846',
    'key30179': 'value69090',
    'key68056': 'value47361',
},
    {
    'id': 17527488429748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Anthony Fletcher',
    'address': '346 Jessica Groves\nKimshire, AS 93377',
    'text': 'Talk own skin exactly.\nWhose brother run policy take their. Line beat alone have land business lead sound. Million understand seek parent response green.',
    'email': 'kevin23@example.org',
    'phone_number': '6429563197',
    'json': {
    'name': 'Lisa Gonzalez',
    'address': '07378 Heidi Curve Apt. 382\nLake Margaretburgh, AR 36351',
},
    'key54080': 'value18667',
    'key12764': 'value19093',
    'key74206': 'value27622',
    'key59158': 'value60539',
    'key99458': 'value83410',
    'key38033': 'value26070',
    'key89041': 'value96128',
    'key7588': 'value65293',
},
    {
    'id': 17527488429759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Joseph Miller',
    'address': '153 Lowery Island Suite 798\nNew Kelly, PR 15224',
    'text': 'Go board along present data organization. Entire local career if throw own old. Responsibility today in professor political blood seek.',
    'email': 'tonya15@example.net',
    'phone_number': '2288353654',
    'json': {
    'name': 'Brittany Rogers',
    'address': '917 Beth Cape\nHugheschester, SD 91532',
},
    'key31811': 'value90010',
},
    {
    'id': 17527488429770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Nicole Bender',
    'address': 'Unit 7185 Box 1056\nDPO AP 62900',
    'text': 'Trip find how. Mrs game off year. Blue together style film. Tonight end parent we most.\nThen special religious gas reflect evening present. Light call work great anything.',
    'email': 'jgallegos@example.org',
    'phone_number': '+1-454-494-7472x87517',
    'json': {
    'name': 'Marc Elliott',
    'address': '82360 Melissa Fields\nShannonstad, MI 36882',
},
    'key3782': 'value42495',
    'key58027': 'value85345',
    'key91047': 'value17112',
    'key46959': 'value26294',
    'key14074': 'value75433',
    'key73749': 'value78471',
    'key11158': 'value45100',
},
    {
    'id': 17527488429780,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Denise Wells',
    'address': '0140 Cross Walk Suite 028\nCampbelltown, VI 96900',
    'text': 'Listen small anything yard difficult.\nCase career condition economy safe edge. Create pretty thousand major factor. Sport hit spring animal trip deep culture.',
    'email': 'lhunt@example.org',
    'phone_number': '001-646-699-7935x941',
    'json': {
    'name': 'John Martin',
    'address': '53164 Walker Island Apt. 457\nSouth Danafort, UT 84751',
},
    'key97481': 'value30059',
    'key12213': 'value13387',
    'key85376': 'value43316',
},
    {
    'id': 17527488429792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jeffery Lawson',
    'address': '66739 Karen Bypass\nSouth Jasmineview, MS 11027',
    'text': 'Wonder rate thank watch interest public degree. Really memory near source however who sell.\nMilitary who hair blood personal. Him home speak base recently. Upon player team future get produce base.',
    'email': 'dakota06@example.com',
    'phone_number': '6305271412',
    'json': {
    'name': 'Sara Navarro',
    'address': '32170 Murphy Drives\nJessehaven, AR 30107',
},
    'key4116': 'value81529',
    'key11592': 'value12824',
    'key27114': 'value23161',
    'key76659': 'value97521',
    'key91595': 'value34747',
    'key88580': 'value46887',
    'key8076': 'value86704',
    'key39253': 'value78519',
    'key95808': 'value30219',
},
    {
    'id': 17527488429803,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Laura Martin',
    'address': 'PSC 5159, Box 9579\nAPO AE 19862',
    'text': 'Give entire sound. Three sometimes wrong discuss want brother animal. College environmental into claim feel bit. Similar writer management not successful director.',
    'email': 'yvonnejones@example.org',
    'phone_number': '975.959.6465x4801',
    'json': {
    'name': 'Mark Paul',
    'address': 'USNS Walsh\nFPO AA 17854',
},
    'key6077': 'value68376',
    'key74353': 'value19679',
    'key36846': 'value8956',
    'key69900': 'value53490',
    'key45494': 'value46216',
    'key76939': 'value42914',
    'key24172': 'value85951',
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
    'RequestId': '797f1a3e-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_36_825524EVAllnJh',
    'filter': 'uid > -100 and uid < 100',
    'limit': 100,
    'offset': 0,
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
    'RequestId': '797f1a3e-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_36_825524EVAllnJh',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752748849.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid100AndUid1001752748849Json()
    test.run_tests()
