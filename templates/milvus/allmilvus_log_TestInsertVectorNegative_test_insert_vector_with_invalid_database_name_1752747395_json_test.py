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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752747395_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752747395.json"
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



class AllmilvusLogtestinsertvectornegativeTestInsertVectorWithInvalidDatabaseName1752747395Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752747395.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752747395.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '1dc392b8-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_16_34_432460ASEuQlPu',
    'dimension': 128,
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
    'RequestId': '1dc392b8-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_16_34_432460ASEuQlPu',
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
    'RequestId': '1dc392b8-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_16_34_432460ASEuQlPu',
    'data': [
    {
    'id': 17527473954725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Lynn Johnson',
    'address': '53876 Joshua Pike\nCherylport, KS 64749',
    'text': 'Local pass of now go concern. Bag material say. Four capital skill dream maybe.\nRoad bar hand Mr father.\nCup way brother next make he focus. Term close quite help suggest but.',
    'email': 'vdunlap@example.org',
    'phone_number': '449-588-3320x71912',
    'json': {
    'name': 'Mary Edwards',
    'address': '5712 Ramirez Mission Apt. 085\nTiffanymouth, PA 93542',
},
    'key18304': 'value98857',
    'key54350': 'value20038',
    'key91236': 'value34679',
    'key70258': 'value89522',
    'key63974': 'value67492',
},
    {
    'id': 17527473954742,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Aaron Ryan',
    'address': '26873 Morrison Route Apt. 275\nWest Kimberlychester, ND 24755',
    'text': 'Local most bring least number order order foot.\nLine at very reach face read model increase. Month toward pull call price.\nProvide seven ready car. Why any hotel southern chair event.',
    'email': 'reyesmelvin@example.net',
    'phone_number': '(464)270-9926x55139',
    'json': {
    'name': 'Robert Bruce',
    'address': '06604 Crystal Orchard\nKarenland, PR 70456',
},
    'key61573': 'value28626',
    'key77966': 'value63995',
    'key70961': 'value5898',
    'key64017': 'value61558',
    'key6105': 'value24117',
},
    {
    'id': 17527473954758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Anthony Dunlap',
    'address': 'USCGC Wilkerson\nFPO AP 99607',
    'text': 'Middle there night safe finally election. Decision policy west human.\nQuite final page career economic. Draw huge throw key social way value.',
    'email': 'oholland@example.net',
    'phone_number': '(340)294-9853',
    'json': {
    'name': 'Nancy Clark',
    'address': '279 Clayton Plaza Apt. 390\nKimmouth, IN 55513',
},
    'key38721': 'value2966',
    'key50273': 'value76069',
    'key28933': 'value87898',
    'key6855': 'value63026',
    'key49205': 'value23072',
    'key51606': 'value46913',
    'key34410': 'value91686',
    'key73075': 'value78211',
},
    {
    'id': 17527473954770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Kristen Bass',
    'address': '70386 James Radial\nNew Albert, OR 15491',
    'text': 'One analysis language road. Conference happy section space. Break assume thought affect.\nTable reveal in call mention adult. Listen family relate on cut.',
    'email': 'richardmurray@example.com',
    'phone_number': '001-403-590-4021x7746',
    'json': {
    'name': 'Amber Anderson',
    'address': 'PSC 3139, Box 2047\nAPO AA 24458',
},
    'key87559': 'value53872',
    'key24616': 'value54928',
    'key86966': 'value38015',
    'key19541': 'value91616',
    'key35677': 'value95028',
    'key3962': 'value8649',
    'key35082': 'value39335',
    'key76479': 'value13836',
},
    {
    'id': 17527473954782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Phillip Brewer',
    'address': '71474 Anderson Keys\nLake Lori, RI 15797',
    'text': 'Democrat major generation movement. Close rather population trial leave. Condition car kid us if. Language challenge stand raise off.',
    'email': 'harrisonmichelle@example.net',
    'phone_number': '+1-974-734-5103x43129',
    'json': {
    'name': 'Angela Mathis',
    'address': '52971 Matthew Trail\nJoelborough, AS 64685',
},
    'key668': 'value73645',
    'key93641': 'value74285',
    'key55141': 'value40960',
    'key17894': 'value79862',
},
    {
    'id': 17527473954796,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Michael Decker',
    'address': '502 Wood Garden Apt. 773\nAdamland, FL 07591',
    'text': 'Probably along son. Old shoulder police appear then nor. Hundred however even successful market hard floor.\nAvoid major similar. Daughter store official produce form. Wide to term bill.',
    'email': 'morenocassandra@example.org',
    'phone_number': '849.268.9898',
    'json': {
    'name': 'Patricia Cook',
    'address': '519 Phillips Prairie Apt. 729\nRothfort, MH 46703',
},
    'key54480': 'value23476',
    'key91265': 'value69869',
    'key64040': 'value39373',
    'key72011': 'value40466',
    'key71799': 'value38615',
},
    {
    'id': 17527473954811,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Julie Nash',
    'address': '04518 Laura Station Apt. 739\nJohnstad, MD 91676',
    'text': 'One many likely hotel wife even music. Stay cup tree.\nAgree always walk us five yet. Full main such current exactly model like beat.',
    'email': 'philiplee@example.org',
    'phone_number': '880.877.5471x286',
    'json': {
    'name': 'Justin Nash',
    'address': '93539 Chad Lock Apt. 402\nSouth Alishamouth, HI 10767',
},
    'key78748': 'value75645',
    'key31778': 'value40387',
},
    {
    'id': 17527473954824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Ryan Owens',
    'address': '4677 Cynthia Orchard Apt. 646\nLake Jocelyn, VT 74991',
    'text': 'Our now than participant happy. Affect west structure water.\nOwn television politics sing represent true rise. Once low term story. Prevent shake how hotel certainly special test.',
    'email': 'mcintyrekayla@example.net',
    'phone_number': '7003417317',
    'json': {
    'name': 'Melissa Evans',
    'address': '429 Michelle Plaza Apt. 395\nPort Dawnside, CO 91060',
},
    'key77193': 'value61931',
    'key13951': 'value46658',
    'key79178': 'value80989',
    'key48278': 'value901',
    'key36822': 'value18354',
    'key8737': 'value73475',
    'key62487': 'value81907',
    'key63210': 'value4622',
    'key61667': 'value8863',
},
    {
    'id': 17527473954836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jeffrey Robinson',
    'address': '57132 Pamela Radial Apt. 558\nAnnechester, GA 21737',
    'text': 'Heart trade true worker oil. Whatever economic rock culture not drug onto.',
    'email': 'bradley88@example.org',
    'phone_number': '536-998-4811x95063',
    'json': {
    'name': 'Patrick Graham',
    'address': '0464 Cook Ville\nLake Michellefurt, AL 45445',
},
    'key29471': 'value64729',
    'key56598': 'value83019',
    'key23938': 'value70620',
    'key9590': 'value32706',
    'key31534': 'value762',
    'key56809': 'value79694',
    'key71292': 'value74757',
},
    {
    'id': 17527473954848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Grant Herrera',
    'address': '69817 Brown Road\nLake Allen, RI 33520',
    'text': 'Blue maintain way interest yourself. Role right top entire generation. From black enter green site.\nDirector however think article air. Plant option recent scene nation.',
    'email': 'julie90@example.com',
    'phone_number': '+1-867-595-4479',
    'json': {
    'name': 'Kevin Allen',
    'address': '65541 Richardson Station Apt. 624\nCooperburgh, CO 44088',
},
    'key52370': 'value47444',
    'key45049': 'value43126',
    'key32750': 'value54639',
    'key62198': 'value80506',
    'key97508': 'value5043',
    'key35204': 'value78404',
},
],
    'dbName': 'invalid_database',
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '1dc392b8-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_16_34_432460ASEuQlPu',
    'dimension': 128,
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752747395.json')
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
    test = AllmilvusLogtestinsertvectornegativeTestInsertVectorWithInvalidDatabaseName1752747395Json()
    test.run_tests()
