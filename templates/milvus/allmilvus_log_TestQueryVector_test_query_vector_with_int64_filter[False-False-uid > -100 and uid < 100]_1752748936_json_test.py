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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752748936_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752748936.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid100AndUid1001752748936Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752748936.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752748936.json"
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
    'RequestId': 'adb7c4d6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_04_437902UXXoXUeR',
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
    'RequestId': 'adb7c4d6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_04_437902UXXoXUeR',
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
    'RequestId': 'adb7c4d6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_04_437902UXXoXUeR',
    'data': [
    {
    'id': 17527489304747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Susan Hughes',
    'address': '94074 Wu Fords\nNorth Jessica, AS 00659',
    'text': 'Analysis past million travel. Involve hand present behind less care old. Should small seat candidate clear source beat similar.\nBetter major leg sometimes environment eat low.',
    'email': 'campbellmichael@example.com',
    'phone_number': '810.859.1227x7379',
    'json': {
    'name': 'David Taylor',
    'address': '390 Ryan Road\nDanielland, IA 92714',
},
    'key83047': 'value6584',
},
    {
    'id': 17527489304765,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Daniel Anderson',
    'address': '1203 John Points\nJonesmouth, NM 69371',
    'text': 'Agreement draw later result pass sign.\nLarge another president student candidate face. Ok guess to. Contain early her pull small happen group.\nImportant when respond such.',
    'email': 'crossthomas@example.net',
    'phone_number': '5787178577',
    'json': {
    'name': 'Steve Martinez',
    'address': '834 Shaw Park Apt. 810\nHendersonland, DC 25509',
},
    'key56979': 'value48902',
    'key99987': 'value21401',
},
    {
    'id': 17527489304781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Troy Stone',
    'address': '1213 Mullins Place Apt. 730\nWest Kristinachester, ME 21945',
    'text': 'Take senior those admit. Child outside guess can.\nDebate act choose themselves degree human girl. Upon son better message.\nAssume those form perform cell. End bag safe different arm usually.',
    'email': 'elizabethmarshall@example.com',
    'phone_number': '7674779861',
    'json': {
    'name': 'John Smith',
    'address': '37659 Smith Route Apt. 162\nNew Colin, TN 18081',
},
    'key87467': 'value76880',
},
    {
    'id': 17527489304796,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Brittany Robinson',
    'address': '0403 Janet Fall\nPort Tiffanychester, RI 18012',
    'text': 'Amount see person born star really. Street scene sign rule our. Among collection majority they state blood particular Congress.',
    'email': 'diane57@example.net',
    'phone_number': '431.891.9563x003',
    'json': {
    'name': 'Robert Kennedy',
    'address': '4131 Kelly Springs Apt. 279\nAndersenfurt, MO 33229',
},
    'key78550': 'value4144',
    'key70957': 'value3246',
    'key43208': 'value5623',
    'key11858': 'value54355',
    'key40829': 'value64200',
    'key63541': 'value23814',
    'key59427': 'value40062',
    'key39119': 'value19099',
    'key16629': 'value57339',
},
    {
    'id': 17527489304809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Mary Garner',
    'address': '4965 Gray Mission Apt. 831\nWest Ronniefurt, NV 98223',
    'text': 'Others his admit. Grow herself speech above happen lay perhaps. Until leg teach fly environmental.\nIt true chair station now cell.\nAir hold chance fine. Change director technology Republican.',
    'email': 'pbrown@example.org',
    'phone_number': '(300)566-0728',
    'json': {
    'name': 'Robert Watson',
    'address': 'PSC 2576, Box 7489\nAPO AP 44809',
},
    'key43201': 'value86034',
    'key66123': 'value23535',
    'key97045': 'value87757',
    'key73417': 'value90704',
    'key60557': 'value44734',
    'key83605': 'value14391',
},
    {
    'id': 17527489304820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'James Friedman',
    'address': '3895 Daniel Greens\nHahnstad, TX 93454',
    'text': 'Trip alone might radio. Something officer thousand sea agree. Out social true economy sea.',
    'email': 'shannon26@example.org',
    'phone_number': '001-728-649-1041x27857',
    'json': {
    'name': 'Lauren Lamb',
    'address': '16319 Laura Crescent Suite 511\nHernandezview, AS 81030',
},
    'key78481': 'value92246',
    'key5108': 'value9221',
    'key55452': 'value68762',
    'key64585': 'value29224',
    'key46500': 'value16746',
    'key69025': 'value74397',
    'key6012': 'value63517',
    'key2620': 'value41215',
    'key83696': 'value26769',
},
    {
    'id': 17527489304834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Heather Myers',
    'address': '53144 Porter View Apt. 250\nRaymondfurt, OH 21799',
    'text': 'School site figure strategy anything drop produce audience. Education experience her no push.',
    'email': 'vegamitchell@example.com',
    'phone_number': '260.779.8427',
    'json': {
    'name': 'Susan Fuller',
    'address': '095 Brian Springs\nNew Brandyton, WV 56670',
},
    'key75761': 'value98872',
    'key49145': 'value54252',
    'key34691': 'value19234',
    'key91581': 'value75067',
    'key73148': 'value46375',
    'key26683': 'value36742',
    'key89702': 'value82077',
    'key35496': 'value87548',
    'key21830': 'value19961',
},
    {
    'id': 17527489304847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jeanette Snyder',
    'address': '696 Matthew Extension\nSchaeferside, FM 12307',
    'text': 'Bar now very specific wait three. Measure image poor maybe sit nor store. Heavy tree according use could physical although.',
    'email': 'traceygonzales@example.com',
    'phone_number': '510.525.6058x462',
    'json': {
    'name': 'Cynthia Marks',
    'address': '62272 Campbell Square\nMadisontown, TX 06544',
},
    'key7899': 'value59759',
    'key91436': 'value84641',
    'key14538': 'value24055',
},
    {
    'id': 17527489304859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jonathan Scott',
    'address': 'PSC 6487, Box 7907\nAPO AE 70917',
    'text': 'Your charge near sense.\nBusiness strong space himself defense camera pretty conference. Issue culture area decade kitchen Congress our authority. Season they guess speak.',
    'email': 'thomaseric@example.com',
    'phone_number': '(439)285-2809x9970',
    'json': {
    'name': 'Sarah Hart',
    'address': '58232 Pamela Tunnel\nClinefort, IL 84008',
},
    'key77552': 'value93342',
    'key32938': 'value98093',
    'key6713': 'value21078',
    'key65689': 'value15284',
    'key63169': 'value59226',
    'key86854': 'value29995',
    'key65802': 'value20922',
    'key44246': 'value87245',
},
    {
    'id': 17527489304869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Lisa Adams',
    'address': '6887 Lisa Manor\nPort Karaview, HI 33248',
    'text': 'Realize every accept. Town along early available memory there join. Rather apply various.\nThree full role game fast. Only effect special cultural book fact top.',
    'email': 'turnerjamie@example.com',
    'phone_number': '680-902-3615x410',
    'json': {
    'name': 'Stephen Bush',
    'address': '73577 Michael Squares\nWilliamport, IA 47328',
},
    'key8084': 'value29948',
    'key23278': 'value14309',
},
    {
    'id': 17527489304880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Benjamin Montgomery',
    'address': '00175 Smith Underpass\nDillonhaven, CO 35873',
    'text': 'Leader although gun off foreign very back. Meet take could under. Spring lot media determine know student.\nStand often possible. Member customer way.',
    'email': 'griffinshane@example.net',
    'phone_number': '904.991.9041x023',
    'json': {
    'name': 'James Shelton',
    'address': '9116 Wallace Fort Suite 804\nNorth Alicia, WA 99390',
},
    'key78562': 'value94458',
    'key99992': 'value50883',
    'key52208': 'value34823',
    'key50243': 'value13147',
    'key17298': 'value863',
    'key27088': 'value75803',
    'key3785': 'value24110',
},
    {
    'id': 17527489304892,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Brandon West',
    'address': '2921 Derrick Lakes Apt. 808\nWest Ronnieshire, CO 97607',
    'text': 'Same style fear gun popular character. Call budget look one. Past of build television cup safe.\nLand individual central policy. Music list somebody. A season concern company conference hour someone.',
    'email': 'iwalls@example.net',
    'phone_number': '7757813934',
    'json': {
    'name': 'Kyle Smith',
    'address': '17798 Jeffrey Shoal\nLake Sean, WY 53091',
},
    'key7800': 'value49588',
    'key5490': 'value1373',
    'key32890': 'value52289',
    'key7920': 'value50450',
    'key40001': 'value26321',
    'key44055': 'value99840',
    'key63969': 'value89724',
},
    {
    'id': 17527489304903,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Penny Chambers',
    'address': '661 Nicole Forges Apt. 023\nJohnsonfurt, PA 78757',
    'text': 'Behavior sing cultural area. Evening history though be executive both. Industry ready analysis fast.',
    'email': 'nancybarnes@example.com',
    'phone_number': '3765132609',
    'json': {
    'name': 'Jonathan Cook',
    'address': '89645 Ware River\nSouth Shawn, OH 14663',
},
    'key3606': 'value83256',
    'key46668': 'value39861',
    'key44716': 'value50974',
    'key63322': 'value34438',
},
    {
    'id': 17527489304914,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jessica Ortiz',
    'address': '9860 Hickman Knolls\nShannonton, CA 49828',
    'text': 'Explain husband sign buy. By employee enough financial chair.\nLaw mission bank sit fight.\nFast gun top true. Adult walk possible maintain high save let.',
    'email': 'vlam@example.org',
    'phone_number': '(754)220-9215',
    'json': {
    'name': 'Andrew Miller',
    'address': '84616 Christopher Courts\nPort Michael, UT 62451',
},
    'key72060': 'value54249',
    'key44978': 'value38212',
    'key27425': 'value21100',
    'key1108': 'value11222',
    'key10667': 'value48830',
    'key24601': 'value59845',
    'key93875': 'value45092',
    'key94': 'value93255',
    'key73385': 'value51462',
},
    {
    'id': 17527489304925,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Hannah Figueroa',
    'address': '03974 Hicks Forges\nMelissamouth, PA 44875',
    'text': 'Surface up however rest north. Seat debate today improve past end three. I from item return chance.\nInclude box television this. Financial indeed sign.\nRemember oil husband city.',
    'email': 'kristenwiggins@example.com',
    'phone_number': '001-486-829-4706x523',
    'json': {
    'name': 'Natasha Lyons',
    'address': '226 Joseph Spurs\nPort Ronnie, PR 87449',
},
    'key52591': 'value64119',
    'key16199': 'value26643',
    'key4755': 'value8689',
    'key62182': 'value53764',
    'key43290': 'value72213',
},
    {
    'id': 17527489304937,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Paul Juarez',
    'address': '352 Justin Wall\nNorth Valerie, IL 89448',
    'text': 'Concern act toward size crime. During computer radio art despite born understand. Late moment animal reason necessary identify service eye.',
    'email': 'bakerjoshua@example.org',
    'phone_number': '960-279-2894x859',
    'json': {
    'name': 'Juan Vaughan',
    'address': '3509 Stephen Burgs\nHaneyfort, PW 53801',
},
    'key3621': 'value32732',
    'key93375': 'value90416',
    'key1996': 'value62419',
    'key39580': 'value16916',
    'key7619': 'value66451',
    'key24085': 'value64132',
    'key61375': 'value95063',
    'key85552': 'value45169',
    'key63303': 'value17262',
},
    {
    'id': 17527489304948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Douglas Ross',
    'address': '174 Graham Plaza\nLake Angelicamouth, VA 72551',
    'text': 'Oil training around.\nRecord budget for about task nation. Through amount tree guess.',
    'email': 'wreed@example.com',
    'phone_number': '208.441.5317x2435',
    'json': {
    'name': 'Elizabeth Lucas',
    'address': '54492 Ashley Trail\nRobersonbury, KS 83675',
},
    'key65817': 'value18143',
    'key36136': 'value91827',
    'key7198': 'value82620',
    'key42232': 'value63851',
    'key78747': 'value97985',
    'key86092': 'value55003',
    'key76892': 'value61958',
    'key42670': 'value16204',
    'key88680': 'value88688',
    'key83650': 'value5541',
},
    {
    'id': 17527489304959,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'David Ellis',
    'address': '99203 Hicks Harbor\nMarissahaven, MA 38378',
    'text': 'Approach thought happy several allow risk. Possible bar beyond benefit experience.\nOrganization open born Congress. Career type into tax author.',
    'email': 'manuel01@example.org',
    'phone_number': '(456)562-8008',
    'json': {
    'name': 'Stephen Hansen',
    'address': '883 Haas Causeway Apt. 737\nLake Erinview, GA 30063',
},
    'key83020': 'value32298',
    'key21275': 'value34760',
},
    {
    'id': 17527489304970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Stephanie Hebert',
    'address': '9522 Heather Wells\nGillberg, MH 85501',
    'text': 'Collection sound so southern close left idea cell. Price cold fish represent produce paper ask decade.\nMusic child control bag member name. Financial leader red fund prove.',
    'email': 'christopher25@example.org',
    'phone_number': '001-665-471-0539x68942',
    'json': {
    'name': 'Timothy Boyle',
    'address': '577 Regina Mount Suite 590\nShawnshire, MI 72469',
},
    'key83794': 'value16041',
    'key54525': 'value74576',
    'key82704': 'value23833',
},
    {
    'id': 17527489304980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Ashley Contreras',
    'address': '700 Glenda Villages Suite 668\nLauraport, HI 55677',
    'text': 'Improve smile report production fly employee.\nStaff yeah real hotel. Item cover week relate plan soon time health. Suggest option window fear.',
    'email': 'montoyasarah@example.com',
    'phone_number': '204.383.3749x469',
    'json': {
    'name': 'Jason Roberts',
    'address': 'USNS Contreras\nFPO AA 29200',
},
    'key368': 'value1516',
    'key5191': 'value36987',
    'key79130': 'value10456',
    'key66220': 'value55986',
    'key49752': 'value64287',
    'key91276': 'value70327',
    'key72210': 'value69618',
    'key76037': 'value37296',
    'key45893': 'value12501',
    'key83261': 'value30575',
},
    {
    'id': 17527489304991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Sandra Fields',
    'address': '340 Kyle Loop\nPaulfort, MA 00510',
    'text': 'One parent but trouble instead note. Team pay American me fall air strategy. Old crime capital line wait already long.',
    'email': 'nataliemendoza@example.net',
    'phone_number': '793-501-9237',
    'json': {
    'name': 'Victor Calhoun',
    'address': '129 Dawn Meadow\nWoodsfurt, KS 60527',
},
    'key55086': 'value86238',
    'key82038': 'value22688',
    'key29897': 'value98078',
    'key78230': 'value28363',
    'key82657': 'value97154',
    'key59213': 'value92824',
    'key7224': 'value17748',
},
    {
    'id': 17527489305002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jordan Gordon',
    'address': '880 Williams Ports Suite 547\nRandyfort, IA 36044',
    'text': 'Education myself situation old near. Land enter product put study human national us.',
    'email': 'jesusjohnson@example.org',
    'phone_number': '303-493-4918',
    'json': {
    'name': 'Cory Adams',
    'address': '748 Russell Courts\nEast Donaldstad, SC 20447',
},
    'key2524': 'value34743',
    'key7047': 'value55021',
    'key37255': 'value15735',
},
    {
    'id': 17527489305015,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jessica May',
    'address': '5366 Rodney Crossing Suite 531\nEmmaville, TX 19780',
    'text': 'Participant have leader industry success whom. State middle production debate able.\nValue focus down name want owner hand. Already dog reach industry word. Look defense here develop.',
    'email': 'williamrodriguez@example.org',
    'phone_number': '(829)474-2714x250',
    'json': {
    'name': 'Christine Mitchell',
    'address': '88548 Hayden Extensions Suite 124\nEast Kristenburgh, IL 03216',
},
    'key47272': 'value84416',
    'key43692': 'value61077',
    'key14722': 'value85466',
    'key92115': 'value78194',
    'key90496': 'value66375',
    'key18031': 'value14462',
    'key72809': 'value7818',
    'key62219': 'value19082',
    'key99970': 'value7011',
    'key96216': 'value80420',
},
    {
    'id': 17527489305027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Randy Hopkins',
    'address': '44208 Regina Lakes Suite 146\nGabrielfurt, PW 42290',
    'text': 'Woman care indeed world total. Station risk seat bad lay with about special. Hear or both.\nList write after young. Agency responsibility throw fund why.',
    'email': 'mitchellbrandi@example.org',
    'phone_number': '566-545-1189x4154',
    'json': {
    'name': 'Donna Thomas',
    'address': '48255 Gina Falls Suite 742\nNew Johnport, DC 96705',
},
    'key75796': 'value57533',
    'key9321': 'value45188',
    'key50156': 'value61329',
    'key51968': 'value37376',
    'key43278': 'value12518',
    'key62780': 'value39500',
    'key19864': 'value91519',
    'key54222': 'value66053',
},
    {
    'id': 17527489305039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Crystal Curry',
    'address': '8576 Earl Cove\nCopelandland, TX 17816',
    'text': 'Nice image left the none owner. Federal wife note skill.\nLetter account military author five weight reality. Plant book something.',
    'email': 'williamsmichael@example.net',
    'phone_number': '7048309099',
    'json': {
    'name': 'Derek Bell',
    'address': 'Unit 6506 Box 4296\nDPO AP 09060',
},
    'key92786': 'value58915',
},
    {
    'id': 17527489305048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Derrick Bradford',
    'address': '979 Ward Tunnel Apt. 561\nRebeccafurt, TN 63229',
    'text': 'Adult cup plant medical. National people popular nature. Area law employee.\nEffort wife particularly just old relationship bring. Election fine apply. Similar night article thousand human.',
    'email': 'nlee@example.net',
    'phone_number': '379-843-2571',
    'json': {
    'name': 'Ashley Willis',
    'address': '7758 Joseph Branch\nJustinside, MS 28650',
},
    'key26653': 'value25126',
    'key73217': 'value2868',
    'key63121': 'value43858',
    'key85230': 'value11662',
    'key4084': 'value42100',
    'key28035': 'value81804',
    'key60005': 'value6431',
    'key58950': 'value25493',
    'key49913': 'value80105',
    'key85866': 'value95689',
},
    {
    'id': 17527489305059,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jerry Ellis',
    'address': '10172 Robert Corner Apt. 947\nPerrystad, GU 58693',
    'text': 'No think receive music view back write someone. Inside once financial.\nBit feel do down. Position wear today in. Rise certain our simple morning.',
    'email': 'lewisjonathan@example.net',
    'phone_number': '(308)318-8627',
    'json': {
    'name': 'Karen Perkins',
    'address': '5737 James Glens Suite 047\nNew Richardborough, IL 87435',
},
    'key44116': 'value24496',
    'key58364': 'value73329',
    'key62588': 'value9924',
    'key68914': 'value87695',
    'key7691': 'value16220',
    'key41796': 'value85896',
    'key37338': 'value90676',
    'key1049': 'value58733',
    'key61383': 'value25662',
    'key58278': 'value18527',
},
    {
    'id': 17527489305071,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Casey Galvan',
    'address': '1180 Brian Lodge\nWest Michaelberg, GU 09436',
    'text': 'Feeling yourself head high never fish feel. Generation group politics foreign partner.\nTax help wonder between activity concern. Simple friend start memory listen.',
    'email': 'james37@example.org',
    'phone_number': '786.653.7108x2694',
    'json': {
    'name': 'Gabriel Lewis',
    'address': '9537 Teresa Creek Suite 023\nWest Sydney, FM 35066',
},
    'key44224': 'value44850',
    'key48442': 'value88721',
},
    {
    'id': 17527489305081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Gabriel Velasquez',
    'address': '391 Martinez Lodge\nLake Jonathanland, HI 09866',
    'text': 'Show camera boy think run set hit. You sure change claim of. Scientist house school answer.\nResponsibility season garden fly. Kid happen him soon under present.',
    'email': 'wendy82@example.net',
    'phone_number': '(601)491-8385x8461',
    'json': {
    'name': 'Renee Huang',
    'address': 'PSC 7833, Box 8264\nAPO AE 44822',
},
    'key43814': 'value65593',
    'key72017': 'value88518',
},
    {
    'id': 17527489305090,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Richard Rivera',
    'address': '9009 James Ville Suite 846\nPort Angelaside, MO 93656',
    'text': 'Agency thing add leave. Lay near memory whose theory. Child talk quality into piece security.',
    'email': 'garydunn@example.com',
    'phone_number': '+1-207-994-3147x8771',
    'json': {
    'name': 'Claire Brooks',
    'address': '73455 Peggy Village Apt. 237\nSteventown, PW 76711',
},
    'key30006': 'value28674',
    'key82546': 'value47456',
    'key8054': 'value41683',
    'key49612': 'value47971',
    'key67220': 'value9213',
    'key46057': 'value79988',
    'key91333': 'value88602',
    'key78974': 'value61734',
},
    {
    'id': 17527489305102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Bryan Oneill',
    'address': '28637 Michael Highway\nSuttonland, GU 45437',
    'text': 'Enjoy above seem list. Some window easy call term. Fall form hot somebody impact impact point.\nGovernment ago rule produce detail feel. Often court only decide experience daughter person service.',
    'email': 'scott45@example.com',
    'phone_number': '3936994285',
    'json': {
    'name': 'Ryan Moore',
    'address': '17614 James Center\nHernandezfurt, AZ 77778',
},
    'key13601': 'value39210',
},
    {
    'id': 17527489305112,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Krista Lopez',
    'address': '6006 Hayes Mission\nAlexisside, NM 19749',
    'text': 'Yeah ago food relate market. Collection newspaper let.\nFish visit agent. Model camera rest pass difference best message.',
    'email': 'jennifer30@example.org',
    'phone_number': '(369)634-2174x349',
    'json': {
    'name': 'Melinda Foster',
    'address': 'USNS Wallace\nFPO AE 92229',
},
    'key12231': 'value1221',
    'key36328': 'value54530',
    'key88306': 'value88650',
    'key39434': 'value6066',
    'key44027': 'value90268',
    'key97455': 'value94123',
    'key52542': 'value85644',
    'key13352': 'value2737',
    'key91383': 'value99493',
    'key28942': 'value43823',
},
    {
    'id': 17527489305122,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Gary Wiggins',
    'address': '574 Donna Lock Apt. 608\nMunozside, KS 29500',
    'text': 'Mission watch man agree. Magazine left religious rest also action. Win soldier western activity enter house response.\nCase every receive feel range center TV. Plant go study kind value three season.',
    'email': 'nramirez@example.net',
    'phone_number': '(279)458-8983x228',
    'json': {
    'name': 'Heather Baker',
    'address': '09208 Willie Harbor Suite 230\nSharonfort, PR 95499',
},
    'key96334': 'value33304',
    'key66276': 'value27800',
    'key60837': 'value97127',
    'key10548': 'value77675',
    'key90550': 'value86187',
    'key42479': 'value36247',
    'key93002': 'value92452',
    'key73791': 'value70362',
    'key74836': 'value58621',
    'key80360': 'value93263',
},
    {
    'id': 17527489305133,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michael Jones',
    'address': '7981 Christina Port Suite 328\nEast Sabrinaborough, PA 24163',
    'text': 'But weight or require. Sing figure evening wall watch another song.\nWalk south put. Service drive language need begin. Become knowledge best game bag region good.',
    'email': 'fvalentine@example.net',
    'phone_number': '6392342934',
    'json': {
    'name': 'Eric Knox',
    'address': '189 Wilkins Locks\nLake Carlaton, MD 42703',
},
    'key74739': 'value40749',
    'key19675': 'value82587',
    'key38283': 'value48007',
},
    {
    'id': 17527489305143,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Dylan Nichols',
    'address': '067 Miller Ferry Suite 153\nGonzalezhaven, NV 86923',
    'text': 'Our level do ready expect discover young. Painting lot finally could art north. Industry magazine professor force benefit you plant.',
    'email': 'myersdana@example.org',
    'phone_number': '204-378-0825',
    'json': {
    'name': 'Kylie Smith',
    'address': '25999 Perkins Expressway Apt. 951\nPort Terribury, NV 65455',
},
    'key32797': 'value6884',
    'key71317': 'value50244',
    'key1307': 'value93666',
    'key8369': 'value10890',
    'key14446': 'value7319',
},
    {
    'id': 17527489305155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Tyler Cook MD',
    'address': '31947 Roberts Spurs\nJoseside, IA 59764',
    'text': 'Likely good interest develop factor statement usually fear. Car east half let establish add he.\nGive sound international camera. Phone much carry manager.',
    'email': 'erika59@example.net',
    'phone_number': '9934481489',
    'json': {
    'name': 'Adam Holland PhD',
    'address': '44983 Thompson Crossroad\nHeatherview, WA 58157',
},
    'key1788': 'value5605',
    'key48715': 'value12476',
},
    {
    'id': 17527489305166,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Susan Reyes',
    'address': '79710 Patrick Roads Apt. 879\nPort Samanthafort, LA 78878',
    'text': 'Approach including ability ask.\nNewspaper raise tax management town. Shoulder factor skin minute such someone interest. Whose language herself catch.',
    'email': 'lisa72@example.com',
    'phone_number': '499-545-3822x124',
    'json': {
    'name': 'Edwin Russell',
    'address': '922 Timothy Plaza Suite 745\nEast Karenport, PW 37206',
},
    'key65430': 'value33204',
    'key24622': 'value37084',
    'key64192': 'value72995',
    'key38699': 'value7894',
    'key46920': 'value48254',
    'key93685': 'value56348',
    'key74972': 'value82562',
    'key35021': 'value47928',
    'key11517': 'value82625',
    'key53278': 'value55280',
},
    {
    'id': 17527489305177,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Nicole Johnson',
    'address': '223 Robert Rest\nSouth Amanda, DC 57939',
    'text': 'Represent moment once yet part star peace. Win their president land use. East clearly middle rich win. Team event guess participant network.',
    'email': 'derekanderson@example.org',
    'phone_number': '001-808-659-3387',
    'json': {
    'name': 'John Brown',
    'address': '66956 Franco Stravenue Suite 385\nPort Makaylaborough, PW 79396',
},
    'key50952': 'value78234',
    'key75526': 'value28137',
    'key80453': 'value61943',
    'key56379': 'value32866',
    'key2866': 'value10641',
    'key60670': 'value14613',
    'key51694': 'value88002',
    'key62653': 'value2278',
    'key17507': 'value76792',
    'key18824': 'value4551',
},
    {
    'id': 17527489305188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Stephanie Gibson',
    'address': '9871 Fitzgerald Shores Apt. 684\nSouth Sandra, MA 05469',
    'text': 'Seven production responsibility act without sport only. Candidate science two difficult catch artist nice. Place approach PM against nice catch.',
    'email': 'whitneydelgado@example.org',
    'phone_number': '861-429-0849x8574',
    'json': {
    'name': 'Jessica Benson',
    'address': '5475 Williams Turnpike Apt. 600\nSouth Amanda, NY 92025',
},
    'key27602': 'value19206',
},
    {
    'id': 17527489305200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Michael Murphy',
    'address': '68447 Amy Wells\nDavisland, FM 24821',
    'text': 'Operation instead ten price whether yeah from. Position gun his yard.',
    'email': 'bridget25@example.net',
    'phone_number': '382.241.0384',
    'json': {
    'name': 'Misty Smith',
    'address': '997 Marquez Ferry\nMorganstad, NJ 95651',
},
    'key6727': 'value38181',
    'key2693': 'value73142',
    'key89379': 'value79847',
    'key93611': 'value27252',
    'key4257': 'value59127',
    'key63444': 'value9768',
    'key95715': 'value93828',
    'key58747': 'value82553',
    'key15455': 'value64423',
    'key39988': 'value92369',
},
    {
    'id': 17527489305210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Margaret Ford',
    'address': '20358 Hill Ports Suite 928\nLopezton, HI 44971',
    'text': 'Best somebody president personal member above recognize. Fear indicate represent nor PM. Trip best animal note nice scene artist.\nIndeed remember hospital agency act.',
    'email': 'crystal67@example.com',
    'phone_number': '001-751-229-3387x27968',
    'json': {
    'name': 'Sandra Davis',
    'address': '28349 Gail Haven Suite 894\nLeeport, VI 19257',
},
    'key44703': 'value59947',
    'key87499': 'value98394',
    'key99817': 'value1585',
    'key38587': 'value44793',
    'key20543': 'value75241',
    'key74989': 'value10090',
    'key65408': 'value7181',
    'key36268': 'value23211',
},
    {
    'id': 17527489305221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Paul Mcfarland',
    'address': '312 Thompson Road\nNorth Natasha, NH 50745',
    'text': 'Strategy someone laugh possible language can. Half collection food cover least I lawyer.\nWind material collection apply. Imagine question sell resource.',
    'email': 'sullivanteresa@example.net',
    'phone_number': '7204044588',
    'json': {
    'name': 'John Collins',
    'address': '79212 Barker Terrace\nEast Amber, IL 92138',
},
    'key21760': 'value35122',
    'key17408': 'value53910',
    'key91794': 'value72699',
},
    {
    'id': 17527489305233,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Julie Wells',
    'address': '59519 Cheryl Island Suite 005\nBakerland, PW 76581',
    'text': 'Boy behavior age short today piece parent interview. Region two town. Clearly large pull go. Reach manage international event parent face.',
    'email': 'bgrant@example.net',
    'phone_number': '970.554.1864x19374',
    'json': {
    'name': 'Gregory Schmitt',
    'address': 'PSC 9955, Box 2874\nAPO AE 48528',
},
    'key54848': 'value96710',
    'key18691': 'value98824',
    'key61935': 'value70885',
    'key80942': 'value46884',
    'key155': 'value5732',
    'key26628': 'value25857',
    'key62338': 'value71101',
    'key31849': 'value4971',
    'key38112': 'value83127',
    'key99104': 'value38535',
},
    {
    'id': 17527489305243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Laura George',
    'address': '48233 Christopher Mall\nPort Jessicaton, MT 04963',
    'text': 'Seek step able but view less. Deep official account very allow. May difference describe base result wait.\nLevel quite available account. Onto before someone blue growth year law.',
    'email': 'kenneth76@example.net',
    'phone_number': '+1-226-302-2192',
    'json': {
    'name': 'Hector Kane',
    'address': '489 Dennis Fords Suite 636\nJohnstad, VT 01784',
},
    'key60173': 'value28584',
    'key45228': 'value54398',
    'key53338': 'value97637',
    'key12833': 'value10493',
    'key3032': 'value45297',
    'key28864': 'value2407',
    'key87677': 'value49724',
    'key39212': 'value36399',
    'key39082': 'value16948',
},
    {
    'id': 17527489305254,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Robert Hart',
    'address': '8139 Walker Wells Suite 852\nWest Abigailview, OK 29100',
    'text': 'Meet college chance.\nSure camera attack threat half teacher. Example since war ahead close seek. Few appear paper save cell.\nLeave bill only machine enter network later. Moment half strategy seat.',
    'email': 'qbrown@example.net',
    'phone_number': '970.746.2591x42517',
    'json': {
    'name': 'Johnathan Ray',
    'address': '1298 Gregory Center\nThompsonshire, WI 80738',
},
    'key27096': 'value71710',
    'key78129': 'value34892',
    'key57734': 'value71492',
    'key65236': 'value96224',
    'key23164': 'value26645',
    'key68048': 'value35206',
    'key63798': 'value43052',
    'key94951': 'value26967',
    'key88088': 'value89132',
    'key21080': 'value29798',
},
    {
    'id': 17527489305266,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Linda Hickman',
    'address': '94708 Adams Knolls\nNorth Tamara, WY 84188',
    'text': 'Standard style image anything art. Mind out such represent while job with. Budget always dog investment.',
    'email': 'ganderson@example.net',
    'phone_number': '475.558.7322',
    'json': {
    'name': 'Joseph Smith',
    'address': '8026 Kristina Field Suite 837\nHunterton, CA 33133',
},
    'key67292': 'value64232',
    'key14533': 'value89392',
    'key72592': 'value50014',
    'key21586': 'value43025',
    'key77920': 'value44348',
    'key66725': 'value51582',
},
    {
    'id': 17527489305278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Susan Brown',
    'address': '2077 Clark Stravenue\nSouth Zacharyside, AL 86262',
    'text': 'Reach spring conference pressure open task ago. Least five type entire fill glass education. Born among money eight. Class class magazine writer.',
    'email': 'phillipsjoseph@example.net',
    'phone_number': '(242)426-7251x19327',
    'json': {
    'name': 'Tyler Kelley',
    'address': '921 Johnson River Suite 774\nNew Andrewborough, KS 47786',
},
    'key15912': 'value74113',
    'key683': 'value20395',
    'key59127': 'value2421',
    'key6854': 'value68784',
},
    {
    'id': 17527489305291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Renee Sherman',
    'address': '18802 Moore Ridges Apt. 344\nSouth Jonathan, OK 10467',
    'text': 'Direction country reveal television bring how Mrs. Key bank while benefit still watch cup meet.',
    'email': 'edwardstimothy@example.net',
    'phone_number': '(716)470-1878',
    'json': {
    'name': 'Vickie Cobb DDS',
    'address': '756 Brittany Springs\nPort Michaelmouth, VT 73132',
},
    'key47681': 'value98207',
    'key61909': 'value72437',
    'key69671': 'value46700',
},
    {
    'id': 17527489305303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Michelle Barron',
    'address': '042 Courtney Mountains Suite 218\nJacksonbury, WA 09882',
    'text': 'Fund every wide personal friend. College book sign learn. Know them push you focus guess.\nIdentify PM animal trade score share. South rule office never face worker customer official.',
    'email': 'hendersonerica@example.com',
    'phone_number': '(681)985-8853x90207',
    'json': {
    'name': 'Sabrina Smith',
    'address': '9163 Jennings Row Apt. 199\nHarrisside, KS 50981',
},
    'key64730': 'value38884',
    'key75874': 'value5529',
    'key86879': 'value82551',
    'key33475': 'value36355',
    'key87091': 'value72513',
},
    {
    'id': 17527489305315,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Robert Ballard',
    'address': '198 Lewis Prairie Apt. 675\nNorth Jeremyhaven, DE 37367',
    'text': 'His turn social center power cold why. Almost true several series up model yeah.\nDebate send participant well shake. Voice student smile so. Front modern current Mr sometimes common wide choose.',
    'email': 'rfigueroa@example.org',
    'phone_number': '9775024572',
    'json': {
    'name': 'Roger Kelley',
    'address': '8452 Terry Ranch Apt. 418\nSouth Justinland, LA 76800',
},
    'key50601': 'value93738',
    'key98077': 'value83811',
    'key51695': 'value71312',
    'key78625': 'value40963',
    'key86508': 'value12982',
    'key53328': 'value8583',
    'key8196': 'value58886',
    'key3863': 'value95693',
},
    {
    'id': 17527489305326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Lauren Lowe',
    'address': '392 Erica Corner\nLake Angelahaven, NM 98033',
    'text': 'Present kind magazine list education scientist. Yard need national personal agreement drive church.',
    'email': 'vanessa84@example.net',
    'phone_number': '+1-912-404-1810x625',
    'json': {
    'name': 'Linda Rivera',
    'address': 'Unit 0666 Box 7726\nDPO AA 73314',
},
    'key71264': 'value30138',
    'key8980': 'value16023',
    'key56208': 'value40708',
    'key93486': 'value63028',
    'key47986': 'value98695',
},
    {
    'id': 17527489305334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'John Ramirez',
    'address': '53139 Perez Haven\nMelissaport, VI 84212',
    'text': 'Structure oil high probably.\nOfficial crime minute practice degree. Every worker build garden even. Site before region force too idea final.\nChoice figure everyone officer. Various word better else.',
    'email': 'hansonandrea@example.com',
    'phone_number': '(328)734-5532x5308',
    'json': {
    'name': 'Colleen Solis',
    'address': '19614 Judy Village\nEdwardschester, CO 55567',
},
    'key14381': 'value5126',
    'key74995': 'value79984',
    'key83127': 'value11357',
    'key7614': 'value60840',
    'key52756': 'value19917',
},
    {
    'id': 17527489305345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Peter Martinez',
    'address': '63738 Powers Village\nEast Leeview, FM 68590',
    'text': 'Rich game question still. Media serious pick course hand candidate. Environment own protect marriage hand.',
    'email': 'dickersonmonica@example.com',
    'phone_number': '001-911-364-3952x76074',
    'json': {
    'name': 'Deanna Smith',
    'address': 'Unit 5816 Box 5873\nDPO AE 16804',
},
    'key3747': 'value39808',
},
    {
    'id': 17527489305355,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'James Mcgee',
    'address': '61473 Kimberly Glen\nAlvarezhaven, ID 84198',
    'text': 'Rule administration to bad exist establish. After they Republican whole stop wait huge.\nHotel computer book course thousand until identify reality.',
    'email': 'melissa45@example.com',
    'phone_number': '582.268.2659',
    'json': {
    'name': 'Kim Garcia',
    'address': '916 Garcia Island Suite 828\nBerryside, MO 80447',
},
    'key25494': 'value87583',
    'key55152': 'value22716',
    'key99626': 'value51450',
},
    {
    'id': 17527489305365,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Ashley Cunningham',
    'address': '20709 Ann Lake\nLake Jennifer, GA 03587',
    'text': 'Something others all ever theory. Ability parent evening.\nTeach final father event. Time talk cut certain you.\nStand memory trial learn be without. Almost throughout design.',
    'email': 'lynchmichael@example.com',
    'phone_number': '001-986-408-0831x20104',
    'json': {
    'name': 'Judith Aguilar',
    'address': '872 Anne Row Suite 952\nBrookeview, ID 19478',
},
    'key29378': 'value27749',
    'key40450': 'value78459',
    'key15683': 'value45113',
    'key36694': 'value8336',
    'key4642': 'value69923',
},
    {
    'id': 17527489305377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Sophia Adams',
    'address': '2212 Bonnie Alley\nEast Preston, MA 90998',
    'text': 'Spend painting party describe with. Rest rise event large sell then hear.\nRest officer radio child garden. Magazine bit go view fight government. Control star car television.',
    'email': 'roseadam@example.net',
    'phone_number': '585.356.5794',
    'json': {
    'name': 'Nancy Bell',
    'address': 'PSC 8040, Box 9501\nAPO AE 09681',
},
    'key97100': 'value57552',
    'key57335': 'value87303',
    'key85261': 'value70863',
    'key3497': 'value57638',
    'key90180': 'value77551',
    'key73173': 'value71543',
    'key1214': 'value19732',
    'key15007': 'value92302',
    'key3789': 'value77674',
    'key42817': 'value293',
},
    {
    'id': 17527489305386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Aaron Rollins',
    'address': '05913 Leslie Parkways Suite 939\nSouth Moniqueport, TX 41376',
    'text': 'Tv gun hold forward.\nMention employee middle. Memory allow early item line.\nGo threat even article themselves option. Here make security who.\nEach person somebody individual.',
    'email': 'belljustin@example.org',
    'phone_number': '918-506-9089',
    'json': {
    'name': 'Nicole Hughes',
    'address': '426 Jarvis River\nDonnaville, MI 15562',
},
    'key82760': 'value27336',
    'key44124': 'value22938',
},
    {
    'id': 17527489305397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jeremy Ryan',
    'address': 'PSC 5557, Box 0981\nAPO AE 01763',
    'text': 'Cause just avoid main. Store color bit bar with. See over author lose. State only nothing letter expert share laugh great.',
    'email': 'mollymcmahon@example.com',
    'phone_number': '976.366.1721x298',
    'json': {
    'name': 'Latoya Carr',
    'address': '10129 Fisher Mount Suite 897\nMatthewborough, VA 01859',
},
    'key21197': 'value81137',
    'key14813': 'value38317',
    'key759': 'value2372',
    'key70471': 'value16648',
    'key8774': 'value83003',
    'key95200': 'value72558',
    'key29759': 'value82258',
    'key42605': 'value77308',
    'key71396': 'value37552',
},
    {
    'id': 17527489305407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Anthony Mclean',
    'address': '278 Green Harbors\nKingchester, UT 27384',
    'text': 'Church tough nice whole white.\nCar maybe against individual onto power cell. Interview case two.\nGood expert go next care form school. Several your stock environmental.',
    'email': 'lholmes@example.org',
    'phone_number': '001-471-996-0253x91175',
    'json': {
    'name': 'Melissa Blackburn',
    'address': 'PSC 4662, Box 7034\nAPO AE 59122',
},
    'key45848': 'value13348',
    'key5548': 'value50335',
    'key11870': 'value53442',
    'key46211': 'value39715',
},
    {
    'id': 17527489305416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'John Ho',
    'address': '7174 Montgomery Wall Suite 631\nEast David, LA 18440',
    'text': 'Light color recognize page. Off enough happen adult. Mrs nation campaign remember senior.\nCommercial particularly whatever chair. Last find play ground.',
    'email': 'nataliereid@example.com',
    'phone_number': '+1-253-375-7990x94502',
    'json': {
    'name': 'Gabrielle Odonnell',
    'address': '065 Walker Junctions\nZavalatown, CA 85420',
},
    'key87557': 'value92265',
    'key68126': 'value79910',
    'key5807': 'value93196',
},
    {
    'id': 17527489305428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Adam Smith',
    'address': '37946 Oneal Ranch Apt. 817\nWest Robert, MH 50188',
    'text': 'Whole thousand record wear. A detail guy woman. Color foot choose ready day such director.\nRock everyone individual issue no may yourself. Already receive war church weight skill.',
    'email': 'thomas15@example.org',
    'phone_number': '+1-308-874-8215x7856',
    'json': {
    'name': 'Melissa Baxter',
    'address': '24611 Williams Manors\nRobertmouth, ME 13054',
},
    'key90543': 'value68295',
    'key93616': 'value61545',
},
    {
    'id': 17527489305438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Charles Golden',
    'address': '49494 Bruce Extensions\nEast Kyle, OH 03489',
    'text': 'Employee figure spend question sell young.\nAttention already threat training letter partner. Everybody understand star.',
    'email': 'calhounolivia@example.org',
    'phone_number': '467-351-6987x204',
    'json': {
    'name': 'Billy Ortiz DDS',
    'address': '275 Thompson Highway\nEast Susanbury, SC 83703',
},
    'key99426': 'value1272',
    'key55333': 'value62298',
    'key50932': 'value99364',
    'key5098': 'value5498',
    'key8460': 'value79708',
    'key73242': 'value39171',
    'key66614': 'value48357',
},
    {
    'id': 17527489305450,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Jerry Kennedy',
    'address': '892 Diana Streets\nNorth Shane, MH 76301',
    'text': 'Education born give operation dark. Concern something summer.\nWoman because major of. Ready far than challenge.\nBusiness shake part civil note. During garden police phone history attorney new enjoy.',
    'email': 'wpeck@example.net',
    'phone_number': '001-585-600-2313x06004',
    'json': {
    'name': 'Sandra Mitchell',
    'address': '7256 Robert Gardens Suite 229\nHeatherberg, DE 61507',
},
    'key89654': 'value79043',
},
    {
    'id': 17527489305461,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mary Dunn',
    'address': '570 Solis Place Apt. 352\nTeresamouth, NY 30054',
    'text': 'Measure entire natural activity follow rock back.\nIdentify west approach. Small watch sometimes not.',
    'email': 'craig48@example.net',
    'phone_number': '643.877.6539x39308',
    'json': {
    'name': 'Ryan Spears',
    'address': '4304 Cindy Circles\nNorth Wendyville, KS 83241',
},
    'key14709': 'value19979',
    'key90177': 'value73139',
},
    {
    'id': 17527489305471,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Shannon Martinez',
    'address': '37288 Micheal Gardens\nEatonshire, IN 54655',
    'text': 'Baby guess we property no man determine writer. Score agent moment cover.',
    'email': 'jenniferhiggins@example.net',
    'phone_number': '(265)418-8754x2114',
    'json': {
    'name': 'Tamara Smith',
    'address': '741 Linda Wells Apt. 796\nJenniferport, VT 25734',
},
    'key41400': 'value23060',
    'key53864': 'value87184',
    'key14624': 'value54172',
    'key87046': 'value42203',
    'key25561': 'value26609',
    'key83214': 'value74173',
    'key76972': 'value60666',
    'key14450': 'value55466',
    'key50915': 'value70099',
},
    {
    'id': 17527489305483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Zachary Watson',
    'address': '6770 Hogan View\nWest Patriciamouth, IN 86992',
    'text': 'Water article clear father. Each interview coach article.\nAlong could entire. Song economic country level few smile. Reduce nor list according job such toward.',
    'email': 'baileymichael@example.net',
    'phone_number': '(658)563-6356x2465',
    'json': {
    'name': 'Amy Tucker',
    'address': '941 Benson Highway Apt. 189\nPort Joannmouth, MP 08933',
},
    'key65963': 'value44423',
    'key66193': 'value48191',
    'key71102': 'value55500',
    'key84335': 'value36162',
    'key79827': 'value26881',
    'key44825': 'value42109',
    'key10713': 'value26622',
    'key31010': 'value52451',
    'key53901': 'value71937',
},
    {
    'id': 17527489305494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Richard Adams',
    'address': '667 Weber Meadow\nGraymouth, GA 43001',
    'text': 'Series data remain cause tough move.\nHand country fear know result force detail chance. Clearly easy sign manage seem wear mother. Speak stuff laugh laugh especially.',
    'email': 'collinjohnson@example.org',
    'phone_number': '950.274.1201x1171',
    'json': {
    'name': 'Carolyn Riggs',
    'address': '447 Samuel Union\nPort Jennifer, CT 50018',
},
    'key98121': 'value16806',
    'key30950': 'value49249',
    'key657': 'value44680',
    'key69446': 'value15372',
    'key35284': 'value56201',
    'key79277': 'value76707',
    'key85697': 'value5923',
},
    {
    'id': 17527489305506,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Cheryl Figueroa',
    'address': '9421 Castro Locks\nAlanport, WI 64941',
    'text': 'Consumer either far hear technology should. Anyone day develop forget. Different vote item serious structure pull.\nFind girl Mr.',
    'email': 'julian41@example.org',
    'phone_number': '001-371-722-3539x976',
    'json': {
    'name': 'Melissa Moore',
    'address': '46009 Kayla Valley Apt. 959\nCarrstad, MA 72634',
},
    'key26451': 'value40228',
    'key59638': 'value21974',
    'key19861': 'value19130',
    'key33378': 'value56074',
    'key49664': 'value96943',
    'key46790': 'value44391',
    'key79428': 'value19749',
    'key87857': 'value80298',
    'key35970': 'value34625',
    'key19513': 'value59704',
},
    {
    'id': 17527489305517,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Michael Sherman',
    'address': '562 Vaughn Burg Suite 644\nRogersstad, NH 41544',
    'text': 'Citizen maintain together. Consumer message whom better expect direction debate give. Statement space actually oil all public natural school. Much mention everything her development.',
    'email': 'iortiz@example.com',
    'phone_number': '001-453-525-2478x30989',
    'json': {
    'name': 'Ronald Conner',
    'address': '6887 White Parks Suite 456\nWest Ronald, MS 21638',
},
    'key32951': 'value18045',
    'key95821': 'value79453',
    'key46949': 'value51377',
    'key38562': 'value1245',
    'key56972': 'value93332',
    'key24792': 'value45891',
    'key65548': 'value7726',
    'key87280': 'value55708',
    'key24162': 'value36575',
},
    {
    'id': 17527489305529,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Courtney Hayes',
    'address': 'USS Little\nFPO AE 04734',
    'text': 'Resource carry quite interesting apply senior. Firm performance military fire commercial one attack eat. Share off expect young.',
    'email': 'samuelwatson@example.org',
    'phone_number': '001-725-325-6870x781',
    'json': {
    'name': 'Victor Velazquez',
    'address': '1231 Gregory Corners\nWrightmouth, MA 97656',
},
    'key50217': 'value4391',
    'key13780': 'value83101',
    'key74675': 'value13233',
    'key71584': 'value83925',
    'key66279': 'value20605',
    'key66883': 'value7442',
    'key72926': 'value36107',
},
    {
    'id': 17527489305539,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Scott Boyd',
    'address': '22583 Autumn Islands\nAdamview, MH 71355',
    'text': 'Truth standard it white cold. Cultural available truth east hour hard.\nFact nearly recent market often. Talk institution democratic. Still friend kitchen purpose focus performance.',
    'email': 'blackwesley@example.com',
    'phone_number': '(800)266-7114x2824',
    'json': {
    'name': 'Brian Stevens',
    'address': '37060 John Cliffs Apt. 645\nEast Christian, MN 71163',
},
    'key39954': 'value19232',
    'key67568': 'value90904',
},
    {
    'id': 17527489305550,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'John Hicks',
    'address': '581 Robertson Pass\nNew Caleb, AS 27911',
    'text': 'Rest school baby investment event. Group much whom including imagine. Seat use doctor record staff.\nDo part whose. Again necessary enough defense and.',
    'email': 'tracyjones@example.org',
    'phone_number': '(964)809-5769x974',
    'json': {
    'name': 'Kimberly Freeman',
    'address': '31348 Thomas Cliffs Suite 663\nNew Jamesport, MS 33040',
},
    'key47300': 'value49019',
    'key14859': 'value74214',
    'key9417': 'value65469',
    'key5859': 'value54111',
    'key25337': 'value4672',
    'key10080': 'value27405',
    'key46783': 'value14651',
    'key75593': 'value2903',
    'key92654': 'value17943',
},
    {
    'id': 17527489305562,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jackson Thomas',
    'address': '4603 Long Island Apt. 421\nEast Ronald, TX 19689',
    'text': 'Require book dinner series behavior agency town. Direction religious book possible. Explain side necessary break.\nYou trial soldier. Husband middle argue face community. Face want teach soldier.',
    'email': 'robin82@example.org',
    'phone_number': '+1-465-858-6448x9131',
    'json': {
    'name': 'Theresa Davidson',
    'address': '573 Stanley Stravenue\nLeeville, MO 04947',
},
    'key22129': 'value6652',
    'key72849': 'value85586',
    'key99282': 'value62618',
    'key3501': 'value87751',
    'key90881': 'value54412',
    'key68440': 'value67543',
    'key34941': 'value35211',
    'key41632': 'value89499',
    'key84567': 'value20556',
    'key58262': 'value1500',
},
    {
    'id': 17527489305573,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Cynthia Johnson',
    'address': '600 Paula Rest Suite 468\nWest Jeffery, PA 70782',
    'text': 'Accept wide student. Inside fact finish boy seven into quite important. Anyone parent plant development miss serve forward.\nBoy nice right no. Short finish painting amount. Speech break medical.',
    'email': 'hillmichael@example.com',
    'phone_number': '666-308-1292x5174',
    'json': {
    'name': 'Teresa Wagner',
    'address': 'USNS Cabrera\nFPO AA 57447',
},
    'key39727': 'value39209',
},
    {
    'id': 17527489305583,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jessica Allen',
    'address': '86350 Kim Ford\nSouth Aaronport, NH 40960',
    'text': 'Travel charge civil measure. National reduce house exist style environmental keep sport. Movie produce another financial yet window.',
    'email': 'lori49@example.net',
    'phone_number': '(395)510-1461',
    'json': {
    'name': 'Charles Peterson',
    'address': '307 Brian Corner Suite 768\nKellyfort, MT 50778',
},
    'key4661': 'value89084',
    'key36554': 'value13451',
},
    {
    'id': 17527489305594,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Brandon Gonzales',
    'address': '805 Yolanda Spurs Suite 442\nEast Catherinemouth, VI 53453',
    'text': 'Serve go organization dog. Cup rise across community technology board drop blue. Charge table owner if economy.',
    'email': 'cblack@example.com',
    'phone_number': '(770)479-2292',
    'json': {
    'name': 'Amber Johnson',
    'address': 'PSC 4962, Box 3985\nAPO AE 55833',
},
    'key53860': 'value16046',
    'key64884': 'value80528',
    'key27977': 'value17131',
    'key28791': 'value54081',
    'key88684': 'value18873',
    'key69111': 'value28151',
    'key51483': 'value40649',
    'key75306': 'value65452',
},
    {
    'id': 17527489305603,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Duane Jones DDS',
    'address': '67577 Andrea Prairie\nKellyland, NH 07716',
    'text': 'Foreign majority interview recently. Around capital eight fight lay international member. Only picture total require although listen stand.\nTogether operation carry just.',
    'email': 'lrose@example.net',
    'phone_number': '844-301-3641',
    'json': {
    'name': 'James Lopez',
    'address': '9730 Harris Station\nWest Erika, IN 80816',
},
    'key65796': 'value72855',
    'key55938': 'value18858',
    'key89699': 'value14537',
    'key30483': 'value22988',
    'key16913': 'value47732',
},
    {
    'id': 17527489305613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Melissa Mueller',
    'address': '54991 Jones Spur\nRodrigueztown, UT 51086',
    'text': 'Very if left former light become. Dark many business pretty store method direction.\nHere media public boy. Near member nature audience season market guess.',
    'email': 'chad86@example.net',
    'phone_number': '3714511111',
    'json': {
    'name': 'Laura Hill',
    'address': '2150 Connor Fort Apt. 614\nPort Robertmouth, AL 13071',
},
    'key88019': 'value62902',
    'key3354': 'value26240',
    'key13547': 'value61886',
    'key93744': 'value68589',
    'key71996': 'value6345',
    'key25992': 'value2596',
    'key99177': 'value67170',
    'key5044': 'value53687',
    'key45801': 'value72857',
},
    {
    'id': 17527489305624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Linda Powell',
    'address': '34749 Davis Freeway Apt. 985\nWiseport, DC 88194',
    'text': 'Lot example treat wish stop compare. Sort act model land son.\nIndustry range stock system sit sign ground. On responsibility recently. Marriage agent company wife successful executive.',
    'email': 'ryangibson@example.org',
    'phone_number': '415-555-0616x340',
    'json': {
    'name': 'Ruben Greene',
    'address': 'PSC 3657, Box 0924\nAPO AP 68336',
},
    'key34977': 'value14252',
    'key14014': 'value95709',
    'key7777': 'value93688',
    'key49065': 'value10205',
    'key636': 'value41133',
    'key75120': 'value450',
},
    {
    'id': 17527489305634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Zachary Gordon',
    'address': '2650 Nicole Streets Apt. 736\nNew Nathan, GA 35554',
    'text': 'Whatever sure family seven thank second. Color majority apply clear blue blue very.\nProgram pattern ready plant daughter. Bit task trouble majority black. Care chance good any view edge popular.',
    'email': 'johnsonkimberly@example.org',
    'phone_number': '430.414.1644',
    'json': {
    'name': 'Misty Maxwell',
    'address': '91872 Bell Meadows\nWest Preston, VT 49665',
},
    'key70283': 'value29748',
    'key92764': 'value45297',
    'key6702': 'value21646',
    'key76795': 'value65578',
    'key693': 'value90158',
    'key43476': 'value17255',
    'key30846': 'value13693',
    'key91368': 'value83403',
    'key28714': 'value29435',
    'key9985': 'value49016',
},
    {
    'id': 17527489305646,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Sandra Robertson',
    'address': '6976 Nichols Spring Apt. 447\nBartonton, CT 62111',
    'text': 'Myself treatment campaign protect arrive.\nModel task decade everyone health owner. Fish close watch box cup follow call.',
    'email': 'robertsmith@example.com',
    'phone_number': '+1-424-695-5877x90225',
    'json': {
    'name': 'Sarah Ward',
    'address': '27919 John Cape Suite 235\nBlakemouth, LA 05237',
},
    'key53167': 'value91863',
    'key20551': 'value37869',
},
    {
    'id': 17527489305657,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Stephanie Robbins',
    'address': '4181 Justin Cape Apt. 485\nEast Jessica, KY 71544',
    'text': 'Paper also moment affect interesting once loss election.\nCommercial all full military thank. Travel late surface note former alone. Woman because house seem south.',
    'email': 'kimberly87@example.com',
    'phone_number': '001-769-889-1100x164',
    'json': {
    'name': 'Jennifer Savage',
    'address': '338 Fritz Mountains Suite 659\nPort Ryan, OH 64094',
},
    'key53893': 'value77416',
    'key46088': 'value62900',
    'key54078': 'value98986',
    'key22392': 'value14559',
    'key9959': 'value80204',
    'key56128': 'value6919',
},
    {
    'id': 17527489305668,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Kevin Gay',
    'address': 'PSC 3853, Box 5244\nAPO AP 57692',
    'text': 'Business think want item result whole including performance.\nHeart officer he region. Factor rather go adult show bag. Claim knowledge response positive.',
    'email': 'danielrivera@example.com',
    'phone_number': '001-694-522-1486x9735',
    'json': {
    'name': 'Matthew Vazquez',
    'address': '6115 Montoya Junctions Suite 893\nPaulborough, WI 89048',
},
    'key22492': 'value33624',
    'key11899': 'value58696',
    'key99821': 'value89231',
    'key27561': 'value5863',
    'key17814': 'value11041',
    'key89609': 'value31227',
    'key61527': 'value99198',
    'key92832': 'value47561',
},
    {
    'id': 17527489305677,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Gabriel Collins',
    'address': '772 Zimmerman Passage Suite 195\nNew Sean, DE 75674',
    'text': 'Door us go lot change best sport. Window arm pretty smile important now. Work per reason too food. Child like trouble affect pay race.',
    'email': 'evansmatthew@example.com',
    'phone_number': '861-729-3196',
    'json': {
    'name': 'Amanda Hernandez',
    'address': '630 Rhonda Parkways Apt. 159\nScottland, VT 80227',
},
    'key85184': 'value58809',
    'key58111': 'value76801',
    'key15104': 'value12892',
    'key484': 'value34003',
},
    {
    'id': 17527489305688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jennifer Lucero',
    'address': '55319 Jill Ferry\nJoannehaven, OR 37040',
    'text': 'Move go country step seem entire child. Could course challenge would though.\nAlso turn hear deal. Authority put hour chair by.\nImagine film specific health performance which.',
    'email': 'virginiarice@example.net',
    'phone_number': '001-280-313-9137',
    'json': {
    'name': 'Briana Davis',
    'address': '665 Velasquez Unions\nDavisstad, PW 39141',
},
    'key85131': 'value47781',
    'key57965': 'value71066',
    'key11908': 'value26172',
},
    {
    'id': 17527489305700,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'John Allen',
    'address': '0395 Barr Neck Apt. 307\nCandiceland, MP 46726',
    'text': 'Material court role while early. Officer give speech available finish off a effort. Meet act work score sea.\nFinancial benefit plant join. Western whether way and expert.',
    'email': 'neil32@example.org',
    'phone_number': '785-489-7269',
    'json': {
    'name': 'Mark Roberts',
    'address': '66804 Christine Inlet Suite 433\nGraveshaven, MO 70140',
},
    'key99943': 'value69931',
    'key67608': 'value78755',
    'key29953': 'value58073',
    'key70261': 'value35835',
    'key4877': 'value52527',
    'key66812': 'value51291',
    'key12314': 'value62923',
    'key99522': 'value43044',
    'key97722': 'value24561',
},
    {
    'id': 17527489305711,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Joshua Pena',
    'address': '8440 Timothy Shoals Apt. 297\nNew Isaiah, MN 84585',
    'text': 'Bring listen when claim answer wonder ago suggest. Note keep talk medical. Write should land measure remain respond more.',
    'email': 'dbrown@example.com',
    'phone_number': '991-812-9447x949',
    'json': {
    'name': 'Marvin Brown',
    'address': '67341 Charles Center\nJeremyton, IA 34826',
},
    'key20281': 'value71667',
    'key80442': 'value42497',
    'key71631': 'value20873',
    'key45806': 'value79326',
    'key597': 'value41887',
    'key90344': 'value71343',
    'key27216': 'value80389',
    'key72433': 'value9493',
},
    {
    'id': 17527489305722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Holly Wolfe',
    'address': '45246 Leah Terrace Apt. 188\nMoorestad, MT 14079',
    'text': 'Bring lot paper community. Break beyond pay couple middle.\nRequire debate the understand especially identify. Hundred several still themselves myself explain travel officer.',
    'email': 'jamesdalton@example.net',
    'phone_number': '001-686-935-7227',
    'json': {
    'name': 'Robert Joseph',
    'address': '1442 Allen Squares Apt. 969\nLake Dylanstad, SD 81174',
},
    'key74080': 'value64293',
},
    {
    'id': 17527489305733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Roger Holt',
    'address': '8081 Jones Mission Suite 295\nWest Robert, VT 19469',
    'text': 'Picture edge red another.\nThing consider heavy meet wrong able bar myself. Maintain source responsibility little. Describe send trouble young return second general.',
    'email': 'mcculloughdavid@example.com',
    'phone_number': '586-572-8641x982',
    'json': {
    'name': 'Richard Cooper',
    'address': '75401 Cannon Plain\nEast Randallshire, AZ 68943',
},
    'key26650': 'value17389',
},
    {
    'id': 17527489305745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Vincent Lewis',
    'address': '38883 Curry Loop Apt. 789\nRodriguezside, WA 99383',
    'text': 'Carry look and each machine go enough art. Visit college line seat. Role rule often office anyone what rate wife. Maybe news movement artist.',
    'email': 'xpeterson@example.com',
    'phone_number': '251.649.0396',
    'json': {
    'name': 'Trevor Holland',
    'address': 'USNV Williams\nFPO AE 81250',
},
    'key1904': 'value70211',
    'key49920': 'value43450',
    'key3443': 'value76572',
    'key50890': 'value68912',
    'key5482': 'value44481',
    'key55065': 'value10829',
    'key4726': 'value12497',
    'key10322': 'value33293',
},
    {
    'id': 17527489305755,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Sean Hart',
    'address': '3348 Brianna Lights\nEast Helenview, VI 88151',
    'text': 'Trade prepare color break Congress. Physical door audience fear remain.\nOffer cold however history democratic be administration buy.',
    'email': 'higginsamber@example.com',
    'phone_number': '485.362.1815',
    'json': {
    'name': 'Michael Johnson',
    'address': '9268 Huff Shore\nEast Angelafort, ID 85250',
},
    'key54882': 'value74855',
    'key99073': 'value97556',
    'key94189': 'value52257',
    'key41797': 'value91257',
    'key8782': 'value8760',
    'key74631': 'value21714',
    'key33900': 'value2839',
},
    {
    'id': 17527489305766,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Alicia Strong',
    'address': '59875 Melissa Brooks\nPort Joseph, MS 08107',
    'text': 'Assume effect former use important. Board how task clearly where.\nOthers against tend scientist wife. Section receive every every none.',
    'email': 'patriciapalmer@example.com',
    'phone_number': '001-221-609-0074x6671',
    'json': {
    'name': 'Kyle Lee MD',
    'address': '597 Johnston Squares Apt. 924\nNorth Christopher, MD 76926',
},
    'key98408': 'value59383',
    'key25501': 'value2647',
    'key94313': 'value26697',
    'key36747': 'value62347',
    'key29613': 'value14562',
    'key47828': 'value94005',
},
    {
    'id': 17527489305778,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Kevin Joseph',
    'address': '627 Deborah Road\nMuellerville, MI 06938',
    'text': 'For form local her. Though Congress a west fall maintain.\nBlue sort drug personal. Western meeting quickly partner east.',
    'email': 'urussell@example.com',
    'phone_number': '(323)609-4672x013',
    'json': {
    'name': 'Danielle Ball',
    'address': '5727 Rachel Fords Apt. 915\nRyanstad, NM 89456',
},
    'key6311': 'value37327',
    'key43837': 'value15134',
},
    {
    'id': 17527489305790,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Summer Fowler',
    'address': '81008 Shaw Summit\nFrankmouth, UT 49732',
    'text': 'Set box stock hundred focus option. Discussion realize author feel expect. International best environment expect.\nPage new board defense training. Film ok where fear.',
    'email': 'patricia13@example.com',
    'phone_number': '001-840-269-3349x6148',
    'json': {
    'name': 'Christopher Hill',
    'address': '4663 Duncan Parkway\nNorth Dustinhaven, WY 79301',
},
    'key84660': 'value29935',
    'key43373': 'value46128',
    'key1314': 'value45167',
    'key83323': 'value18521',
    'key89343': 'value90084',
    'key30254': 'value67036',
    'key24835': 'value21870',
},
    {
    'id': 17527489305801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jason Kelly',
    'address': '2819 Patel Vista\nEllisfurt, HI 00829',
    'text': 'Serious half in morning.\nEasy third sell begin physical national. Not matter goal admit hundred present fight. Shoulder build into action instead. Table crime another produce think offer through.',
    'email': 'victoriafarmer@example.net',
    'phone_number': '463-253-9145x098',
    'json': {
    'name': 'Jasmine Ward',
    'address': '448 Tricia Crossroad\nLake Bobbymouth, DE 37682',
},
    'key47438': 'value4001',
    'key63717': 'value64509',
    'key58646': 'value52004',
},
    {
    'id': 17527489305813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Rhonda Prince',
    'address': '02727 Davis Dam Apt. 160\nDavismouth, NY 71837',
    'text': 'Chair include traditional southern experience four. Land left method source message purpose. Owner finish cold truth sing benefit myself. Risk land because support build challenge car.',
    'email': 'xavier23@example.net',
    'phone_number': '808-368-6951x066',
    'json': {
    'name': 'Chelsea Walker',
    'address': '891 Michael Corners\nSouth Laurenmouth, SD 28868',
},
    'key10099': 'value31029',
    'key33967': 'value93820',
    'key48262': 'value15506',
},
    {
    'id': 17527489305823,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Sarah Jones DVM',
    'address': '921 French Parkway Apt. 522\nWolfeville, AS 47429',
    'text': 'How author head situation current. Would painting street color lot. To night beyond.\nPlace decision indeed car billion fight. Eight special easy return economy TV west.',
    'email': 'zwest@example.com',
    'phone_number': '(954)337-6133x303',
    'json': {
    'name': 'Crystal Stafford',
    'address': '3000 Espinoza Forges\nMarisashire, PW 65393',
},
    'key82984': 'value42108',
    'key23745': 'value4173',
    'key64050': 'value26068',
    'key42125': 'value3368',
    'key73028': 'value72732',
},
    {
    'id': 17527489305835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Dr. Rachel Waters',
    'address': '68091 James Centers Suite 546\nBrittanyview, OH 96794',
    'text': 'Million politics somebody perhaps off hair green statement.\nDiscuss quality detail present. What ever force positive last. Else pay just world third trip.',
    'email': 'dcollins@example.net',
    'phone_number': '342.492.2403',
    'json': {
    'name': 'Cameron Cabrera',
    'address': '011 Michael Glens Suite 487\nJoshuaburgh, NJ 42373',
},
    'key42090': 'value98726',
},
    {
    'id': 17527489305845,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Julie Spencer',
    'address': '7418 Travis Knoll Suite 792\nNew Eric, MT 23687',
    'text': 'Interview whole method red foot one. Send page everything rather population.\nItem message item recent face. Save center watch surface start most. Meeting no for local main detail crime.',
    'email': 'stonetrevor@example.com',
    'phone_number': '(516)211-2832x35289',
    'json': {
    'name': 'Jennifer Smith',
    'address': '774 Edwards Key Suite 980\nCatherineshire, MA 65390',
},
    'key69613': 'value840',
    'key6798': 'value25308',
    'key43775': 'value40403',
    'key15521': 'value24488',
    'key72273': 'value9156',
    'key29655': 'value43360',
    'key95017': 'value50008',
    'key80162': 'value11184',
},
    {
    'id': 17527489305857,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jeffrey Rodriguez',
    'address': '079 Samuel Extensions\nZacharyhaven, NE 78403',
    'text': 'Maintain college catch for. Prepare hard arrive growth however serve sit.\nTotal realize deal answer course.',
    'email': 'johnstonjennifer@example.net',
    'phone_number': '001-223-988-9174x4352',
    'json': {
    'name': 'Suzanne Carpenter',
    'address': '45910 Morris Trail\nNorth Ryan, RI 44911',
},
    'key89946': 'value54474',
    'key62527': 'value38080',
    'key56608': 'value87546',
    'key78276': 'value97367',
    'key14109': 'value53886',
    'key19553': 'value81741',
    'key58932': 'value84565',
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
    'RequestId': 'adb7c4d6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_04_437902UXXoXUeR',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'adb7c4d6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_04_437902UXXoXUeR',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752748936.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid100AndUid1001752748936Json()
    test.run_tests()
