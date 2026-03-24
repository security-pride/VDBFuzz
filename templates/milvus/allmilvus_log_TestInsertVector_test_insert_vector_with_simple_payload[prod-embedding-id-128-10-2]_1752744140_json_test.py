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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-2]_1752744140_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-2]_1752744140.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId1281021752744140Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-2]_1752744140.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-2]_1752744140.json"
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
    'RequestId': '8a0a2bc0-62ef-11f0-9555-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_19_111245mJVEvkqF',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'embedding',
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
    'RequestId': '8a11b4cc-62ef-11f0-bade-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_19_111245mJVEvkqF',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Anthony Baker',
    'address': '95440 Howard Groves Suite 288\nLake Elizabethchester, NJ 17444',
    'text': 'Suggest something decide natural country. Their difference trouble case message throw. Result production happen late senior.',
    'email': 'taylor46@example.net',
    'phone_number': '506-710-9178x8542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dana Romero',
    'Jamie Peters',
    'Angela Foster PhD',
],
    'json': {
    'name': 'Stephanie Rivas',
    'address': 'Unit 3371 Box 4271\nDPO AA 52117',
},
    'key33578': 'value64907',
    'key58790': 'value27180',
    'key46598': 'value30410',
    'key26408': 'value26593',
    'key48945': 'value96414',
    'key17169': 'value43514',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Nicole Peterson',
    'address': '85488 Miller Pass Suite 446\nPort Laura, GU 68763',
    'text': 'Suggest two here maybe such serious moment base. Your process best over read decision successful remember.',
    'email': 'doylejohn@example.net',
    'phone_number': '937-970-5825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lance Lawson',
    'Wendy Johnson',
    'Monica Greene',
    'Jerome Greene',
],
    'json': {
    'name': 'Joseph Cummings',
    'address': '512 Logan Ramp Apt. 866\nWrightton, CA 95950',
},
    'key24265': 'value32100',
    'key21429': 'value46410',
    'key86355': 'value97050',
    'key18997': 'value70043',
    'key9212': 'value94339',
    'key23566': 'value53295',
    'key64249': 'value92215',
    'key60841': 'value38210',
    'key8607': 'value48678',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Mitchell Sanchez',
    'address': '94011 Molina Wall Apt. 279\nWest Kenneth, MP 13674',
    'text': 'Radio son oil garden public box entire lose. Sense mean off soldier. Herself back partner however between foot carry.',
    'email': 'lopezcody@example.net',
    'phone_number': '+1-295-776-6506x837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Valdez',
],
    'json': {
    'name': 'Jose Rogers',
    'address': '1521 Jay Valley\nSouth Frederick, MD 71370',
},
    'key93329': 'value5412',
    'key75350': 'value19530',
    'key35630': 'value40674',
    'key85981': 'value33524',
    'key47387': 'value70121',
    'key36495': 'value46002',
    'key74552': 'value43503',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Mark Johnson',
    'address': '94962 Lance Forks\nPort Thomaschester, ND 01469',
    'text': 'Lose team during throughout music.\nSeveral enter conference find method box. Answer even say three lead whether chair site.',
    'email': 'carol75@example.net',
    'phone_number': '451.867.0960x689',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Carter',
    'Christina Davis',
    'Nicholas Turner',
],
    'json': {
    'name': 'Laurie Hayes',
    'address': '5914 Powers Brooks Suite 061\nChristineland, RI 75322',
},
    'key63788': 'value21403',
    'key30344': 'value40733',
    'key88575': 'value55800',
    'key48571': 'value10967',
    'key321': 'value45934',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Jimmy Torres',
    'address': '4383 Morgan Views Apt. 728\nNew Emily, CA 86313',
    'text': 'Others kind low coach not like college scene. Third church can painting.\nAgent property including field fish small pattern. Turn myself dream health his.\nProduction star grow choice.',
    'email': 'johnsonholly@example.com',
    'phone_number': '(391)989-8511x639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Hansen',
],
    'json': {
    'name': 'Marc Porter',
    'address': '7180 Foster Flats Apt. 509\nRiveraside, NC 01851',
},
    'key23535': 'value36491',
    'key18509': 'value99941',
    'key1951': 'value77341',
    'key14856': 'value77235',
    'key31631': 'value57311',
    'key65570': 'value58056',
    'key13415': 'value87063',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Cindy Lozano',
    'address': '95804 Myers Mountain Apt. 206\nCastrotown, VI 87280',
    'text': 'Whose occur add avoid still available meeting past. Approach ready million soldier. Behind for short. Expect management station just.',
    'email': 'mwong@example.net',
    'phone_number': '(772)409-1656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Jones',
    'Robert Harris',
    'Kelly Brewer',
    'Renee Williams',
],
    'json': {
    'name': 'Julie Martinez',
    'address': '12491 Anthony Center\nEast Leslie, MO 21720',
},
    'key46584': 'value2552',
    'key36769': 'value56869',
    'key191': 'value49172',
    'key53722': 'value80995',
    'key12': 'value78372',
    'key83835': 'value26769',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Nathan Lee',
    'address': 'PSC 9769, Box 6865\nAPO AP 81487',
    'text': 'Enough relate opportunity air cultural agree whole. Rock administration because police arrive. Media eye real rock financial sing interest.\nCompare under marriage until. Win section behavior tax.',
    'email': 'haleykim@example.net',
    'phone_number': '(713)422-5914x21038',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amy Nguyen',
    'Steven Simpson',
    'Jessica Le',
    'Sophia Guzman',
    'Mark Holder',
    'Jodi Rose',
    'Raymond Hamilton',
    'Jimmy Andersen',
    'Brian Andrews',
],
    'json': {
    'name': 'Daniel Dunn',
    'address': '825 Walker Street Apt. 249\nLake Michaelshire, HI 99612',
},
    'key32344': 'value38108',
    'key43541': 'value8201',
    'key9472': 'value14038',
    'key1622': 'value17462',
    'key73477': 'value77697',
    'key97786': 'value45326',
    'key87084': 'value21989',
    'key49369': 'value48717',
    'key96633': 'value56405',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Kelly Short',
    'address': '768 Jackson Stravenue\nWhiteport, WA 44533',
    'text': 'Season guess official agree we near. Magazine any both.\nBuild opportunity front case trip move. Carry notice indicate dinner view tell.',
    'email': 'ovasquez@example.org',
    'phone_number': '8455757064',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Price',
    'Victoria Diaz',
    'Amy Collins',
    'Daniel Coleman',
    'Alexandra Saunders',
    'Christine Salas',
    'David Cole',
],
    'json': {
    'name': 'Thomas Foley',
    'address': '878 Heather River\nSouth Cameronport, WA 82867',
},
    'key78333': 'value63746',
    'key97889': 'value81108',
    'key23087': 'value17005',
    'key26520': 'value77487',
    'key66072': 'value65509',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'James Lopez',
    'address': '12771 Rachel Via\nLake Kevin, IA 02728',
    'text': 'Financial other where onto will close stand. Information more billion represent against stand. Protect space term whether bank choice lead.',
    'email': 'mgarrison@example.com',
    'phone_number': '+1-429-834-4226x5760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Ferguson',
    'Jamie Mcdonald',
    'Patrick Gutierrez',
    'Anthony Cox',
    'James Booker',
    'Christine Gonzalez',
],
    'json': {
    'name': 'Dawn Richardson',
    'address': '9844 Kennedy Corners Suite 216\nWilliammouth, MH 43494',
},
    'key20174': 'value5885',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Matthew Munoz',
    'address': '275 Stacy Ridges\nLake Williamfurt, WI 87551',
    'text': 'Lot give mouth street relationship goal. Old get newspaper suddenly space no. Medical gas suddenly black.\nPopulation and strategy play provide affect. Police compare order attack nation enjoy.',
    'email': 'lisagonzalez@example.org',
    'phone_number': '584-662-6104x12906',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Duke',
],
    'json': {
    'name': 'Alicia Wells',
    'address': '581 Jim Course\nSouth Corey, MD 95039',
},
    'key55612': 'value66356',
    'key94387': 'value16619',
    'key82800': 'value35039',
    'key84064': 'value62056',
    'key87480': 'value66196',
    'key871': 'value89503',
    'key23847': 'value85563',
    'key32692': 'value38914',
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
    'RequestId': '8a0a2bc0-62ef-11f0-9555-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_19_111245mJVEvkqF',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-2]_1752744140.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId1281021752744140Json()
    test.run_tests()
