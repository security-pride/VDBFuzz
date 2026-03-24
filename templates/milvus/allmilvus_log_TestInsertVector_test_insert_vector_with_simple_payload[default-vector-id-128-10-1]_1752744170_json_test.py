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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-1]_1752744170_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-1]_1752744170.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId1281011752744170Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-1]_1752744170.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-1]_1752744170.json"
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
    'RequestId': '9c4a2eff-62ef-11f0-8d84-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_49_729737JQpsdlex',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
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
    'RequestId': '9c5125c1-62ef-11f0-9f7c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_49_729737JQpsdlex',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jason Gill',
    'address': '597 Matthew Hill\nWest Tara, VA 85569',
    'text': 'Consider information draw check task. Arrive enter recently discover computer time sign. Surface gas check accept.',
    'email': 'smithheather@example.org',
    'phone_number': '001-217-894-6199x55010',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Chris Johnson',
    'Erica Mitchell',
    'Sara Mcneil',
    'Kim Roberts',
],
    'json': {
    'name': 'Hunter Campbell',
    'address': '028 Diana Fields\nDorothybury, IA 17080',
},
    'key5856': 'value74067',
    'key38815': 'value5800',
    'key29899': 'value51224',
    'key36616': 'value73577',
    'key57618': 'value14839',
    'key70966': 'value38280',
    'key80010': 'value15035',
    'key51112': 'value66128',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Andrew Herring',
    'address': '710 Cannon Gardens\nSmithmouth, MO 56449',
    'text': 'Network expect feel peace material authority skin. Task organization ago stock region. Someone thought animal wish.',
    'email': 'kimberlyguerra@example.org',
    'phone_number': '(229)500-1281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Adam Joseph',
    'Scott Anderson',
    'Casey Vaughn',
    'Michelle Cohen',
    'Amber Sheppard',
    'Matthew Greene',
],
    'json': {
    'name': 'Sarah Kaiser',
    'address': 'Unit 8993 Box 7409\nDPO AP 94687',
},
    'key88669': 'value49727',
    'key61368': 'value39881',
    'key59614': 'value3393',
    'key78994': 'value19690',
    'key91027': 'value97963',
    'key17417': 'value90547',
    'key89662': 'value36690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Thomas Scott',
    'address': '050 Michelle Trail\nNorth Robert, VI 32812',
    'text': 'Yard service media memory save similar phone put. Each debate fall young of how doctor.',
    'email': 'sheryl52@example.net',
    'phone_number': '(466)451-2365x58966',
    'array_int_dynamic': [
    49508,
],
    'array_varchar_dynamic': [
    'Teresa Allen',
    'Brendan Beasley',
    'Margaret Bell',
    'Jenna Wyatt',
    'Nicholas Miller',
    'Seth Myers',
    'Jason Potter',
    'Jason Johnson',
    'Terri Mitchell',
    'Holly Phillips',
],
    'json': {
    'name': 'Lori Rosales',
    'address': '937 Berry Mountain Suite 063\nPort Kristinberg, TX 16698',
},
    'key95362': 'value73074',
    'key56253': 'value42281',
    'key66519': 'value12179',
    'key85419': 'value39836',
    'key37318': 'value4002',
    'key79469': 'value47379',
    'key3256': 'value22254',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Robert Duarte',
    'address': 'PSC 3104, Box 5151\nAPO AA 30656',
    'text': 'Everything product case college the then. Often well ever short number range add. Course democratic sing may in ahead. Win report politics focus.',
    'email': 'sanchezvincent@example.org',
    'phone_number': '674.403.2362x88014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Palmer',
    'Christopher Ellis',
    'Hector Torres',
    'William Pruitt',
    'Jennifer Wilson',
],
    'json': {
    'name': 'Tara Hernandez',
    'address': 'PSC 1205, Box 7952\nAPO AE 19705',
},
    'key42157': 'value10935',
    'key77243': 'value12798',
    'key43029': 'value37757',
    'key11923': 'value8416',
    'key15010': 'value7894',
    'key34999': 'value91227',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Diana Davis',
    'address': '11715 Javier Forest Apt. 663\nNew Bradleystad, GU 28141',
    'text': 'Save toward energy both while scientist effect could. Goal director carry store scientist movement.\nFirst ability defense me. Compare large character dinner.',
    'email': 'camposerin@example.net',
    'phone_number': '+1-442-293-6314x473',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Monica Hicks',
    'William Chen',
    'Daniel Hull',
],
    'json': {
    'name': 'Timothy Preston',
    'address': '205 Christensen Walk\nEast Paul, WI 31308',
},
    'key27624': 'value35377',
    'key60940': 'value8281',
    'key30': 'value41962',
    'key62720': 'value54503',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Nancy Larson',
    'address': '987 Tracy Common\nEast Ricky, VI 65624',
    'text': 'Mean indicate knowledge situation there company. Science collection group myself sign mention. Game foreign door scientist industry.',
    'email': 'blackalyssa@example.org',
    'phone_number': '(857)868-7914x676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Ross',
    'Elizabeth Flowers',
    'Matthew White',
],
    'json': {
    'name': 'Matthew Fleming',
    'address': '903 Kevin Parks\nJonesburgh, MI 96998',
},
    'key14990': 'value18874',
    'key96278': 'value14264',
    'key50496': 'value77193',
    'key67799': 'value72851',
    'key91434': 'value71149',
    'key7091': 'value1433',
    'key87948': 'value59831',
    'key13101': 'value94025',
    'key85713': 'value78688',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Paul House',
    'address': '090 Burton Trafficway\nEvansberg, MS 48919',
    'text': 'Operation someone evening worry agency tough ten. Best establish east move bag.\nThis where wait laugh. Interview election left. Lose environmental show relationship several wish indicate.',
    'email': 'jacob60@example.net',
    'phone_number': '(631)534-7985',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'John Costa',
    'Teresa Estrada',
    'Alexander White',
    'Aaron Novak',
    'Martin Maldonado',
    'Ellen Andersen',
    'Timothy Munoz',
    'Leslie Mckinney',
    'Sarah Coleman',
    'Kayla Ewing',
],
    'json': {
    'name': 'Kim Martinez',
    'address': '33212 Lee Branch Suite 035\nAnthonyview, NC 34895',
},
    'key16989': 'value68012',
    'key24733': 'value11436',
    'key59024': 'value1238',
    'key48835': 'value87232',
    'key34107': 'value14443',
    'key96162': 'value29018',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Todd Miller',
    'address': '874 Gutierrez Hills Apt. 324\nMichaelchester, OK 47732',
    'text': 'Increase couple join approach away boy region huge. Themselves candidate sit course.\nMan modern join but next lose risk. Hit visit write sometimes determine town under.',
    'email': 'natasha21@example.org',
    'phone_number': '(972)408-7792',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Gilbert',
    'John Medina',
    'Matthew Kim',
    'Jennifer Bailey',
    'Jennifer Shaw',
    'Crystal Richardson',
    'Angela Jackson',
    'Rodney Hernandez',
    'Jeremy Cooper',
    'Ian Pena',
],
    'json': {
    'name': 'Shawn Wilson',
    'address': '797 Dennis Lane\nLeemouth, FM 84875',
},
    'key29133': 'value47798',
    'key93926': 'value94949',
    'key83206': 'value51133',
    'key39916': 'value14408',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Madison Wilson',
    'address': '12156 Jorge Key\nEast Danielport, WI 45051',
    'text': 'One while suggest begin community. Situation usually factor. Project soldier late keep institution.\nWhy student worker foot language. Face more before different he song crime.',
    'email': 'sarahvalencia@example.com',
    'phone_number': '+1-319-473-4708x79028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Walker',
    'Colin Glover',
    'Mr. Michael Li',
    'Jacob Whitaker',
],
    'json': {
    'name': 'Kenneth Acosta',
    'address': '909 Mary Brooks\nJohnstad, NY 11743',
},
    'key71127': 'value59989',
    'key71544': 'value6598',
    'key3957': 'value15173',
    'key10211': 'value73284',
    'key67254': 'value41253',
    'key38376': 'value83761',
    'key61239': 'value12112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jason Rivera',
    'address': '8039 Johnson Key\nCortezfurt, WA 77428',
    'text': 'Into thank big every if. Rate eight dog concern meet condition card drive. Gas traditional minute future cold research real grow.',
    'email': 'ydavis@example.com',
    'phone_number': '(325)357-4311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Brown',
    'Melissa Velez',
    'Donald Liu',
    'Rachel Ibarra',
    'Michael Griffin',
    'Jenny Torres',
    'Amy Thompson',
    'Cynthia Montgomery',
    'Sarah Pierce',
],
    'json': {
    'name': 'Amber Bishop',
    'address': '848 Norman Plaza\nHeathermouth, VI 65309',
},
    'key36996': 'value31194',
    'key48930': 'value83687',
    'key55336': 'value42209',
    'key39000': 'value36001',
},
],
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



    def test_request_2(self):
        """测试请求 2 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '9c4a2eff-62ef-11f0-8d84-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_49_729737JQpsdlex',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-1]_1752744170.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId1281011752744170Json()
    test.run_tests()
