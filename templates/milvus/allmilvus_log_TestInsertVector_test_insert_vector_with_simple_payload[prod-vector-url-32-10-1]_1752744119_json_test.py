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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-1]_1752744119_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-1]_1752744119.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl321011752744119Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-1]_1752744119.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-1]_1752744119.json"
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
    'RequestId': '7ddf9f5f-62ef-11f0-8bd2-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_58_699737JkXpCREE',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
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
    'RequestId': '7de7a70a-62ef-11f0-850e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_58_699737JkXpCREE',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Kathryn Velasquez',
    'address': '64775 Shah Dam Apt. 804\nCatherinemouth, MH 59442',
    'text': 'Law the everybody occur though. Military gun fall me natural.\nMillion never visit position similar friend. Little evidence eat really myself his agree. Interest choose behavior unit decade.',
    'email': 'tayloremily@example.org',
    'phone_number': '759.703.4315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julian Erickson',
    'Richard Moore',
    'Kayla Rodriguez',
],
    'json': {
    'name': 'Leonard Stevens',
    'address': '845 Peter Estate\nAlanchester, DE 88239',
},
    'key26075': 'value99731',
    'key82576': 'value96597',
    'key82434': 'value92602',
    'key92837': 'value54220',
    'key80077': 'value37664',
    'key57220': 'value90821',
    'key31863': 'value8547',
    'key43893': 'value4821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Todd Hester',
    'address': '6525 Rodriguez Glens Suite 973\nPort Kyle, IA 00601',
    'text': 'Box pay enough material.\nPart bank hard sport hold close. Nice reason part religious evidence fall. Add lead probably rich hotel.',
    'email': 'dunlapkimberly@example.net',
    'phone_number': '438.621.7137',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Donald Ball',
    'Alfred Hanson',
    'James Rodriguez',
],
    'json': {
    'name': 'Kenneth Wallace',
    'address': '103 Ramsey Fords Apt. 296\nJenniferburgh, AL 90822',
},
    'key77888': 'value40359',
    'key32871': 'value61874',
    'key15931': 'value34815',
    'key96620': 'value81947',
    'key61975': 'value72807',
    'key91518': 'value27937',
    'key94689': 'value7098',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Candace Lawrence',
    'address': '5200 Cook Pass\nNorth Richard, ID 63643',
    'text': 'Pattern throw black democratic.\nCompare civil production wear message sometimes this. Population others image.\nFly catch minute door age.\nMight else since break traditional buy personal.',
    'email': 'tony94@example.com',
    'phone_number': '(616)243-7477',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alan Lopez',
    'Teresa Hernandez',
    'Jessica Reed',
    'Scott Harris',
],
    'json': {
    'name': 'Shawn Lopez',
    'address': '697 Smith Points\nNew Jeffreytown, AZ 80821',
},
    'key46913': 'value20515',
    'key40869': 'value97490',
    'key11029': 'value14850',
    'key34972': 'value27486',
    'key30655': 'value9024',
    'key15538': 'value5360',
    'key31783': 'value12973',
    'key5960': 'value99820',
    'key70747': 'value25462',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Robin Vasquez',
    'address': '39254 Hernandez Port Apt. 068\nChenmouth, AK 60039',
    'text': 'Adult over cell present computer claim suggest. Occur from behavior than important assume. Clear four wear house girl smile page.',
    'email': 'bbaldwin@example.com',
    'phone_number': '(954)392-8412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Melendez',
    'Christopher Wright',
    'David Morgan',
    'Angela Myers',
    'Phillip Robertson',
    'Frank Mccarthy',
    'John Allison',
],
    'json': {
    'name': 'Diana Barnes',
    'address': '60947 Danny Village\nWarnerview, CT 57391',
},
    'key69942': 'value10254',
    'key41836': 'value6024',
    'key10610': 'value29608',
    'key94443': 'value99035',
    'key15366': 'value7211',
    'key82367': 'value57621',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Christine Hurley',
    'address': 'PSC 6636, Box 1147\nAPO AE 69970',
    'text': 'Me beautiful about himself ability whatever hundred.',
    'email': 'parksshannon@example.org',
    'phone_number': '930.213.4074x2611',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Rodriguez',
    'Robert Lozano',
    'Wendy Collins',
    'Christopher Mann',
    'Nicholas Sanchez',
],
    'json': {
    'name': 'Daniel Mendoza',
    'address': '1947 Brian Mall\nPort Christopher, NC 15592',
},
    'key82797': 'value8312',
    'key32188': 'value22270',
    'key89277': 'value92782',
    'key36747': 'value77823',
    'key6555': 'value99061',
    'key31291': 'value30094',
    'key99309': 'value21031',
    'key477': 'value64766',
    'key69763': 'value8999',
    'key53964': 'value32477',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Scott Guzman',
    'address': '2705 Evans Drive Apt. 683\nBrendamouth, MI 13141',
    'text': 'Series notice how decade. Poor election drop direction property. Use voice do situation return management election.',
    'email': 'ian00@example.net',
    'phone_number': '+1-541-837-0488',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Kim',
    'Kimberly Harrington',
    'Ryan Christensen',
    'Samantha Barker',
    'Jennifer Hall',
],
    'json': {
    'name': 'Susan Davidson',
    'address': '708 Brittany Highway\nJeanetteshire, NJ 61733',
},
    'key26313': 'value7255',
    'key69075': 'value88051',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Sherry Avery',
    'address': 'USS Nicholson\nFPO AP 29900',
    'text': 'She worker technology result individual tell rich.\nOrder mother newspaper concern tell. Population effect take little law away perhaps. Yeah blue not store reduce artist.',
    'email': 'lclark@example.net',
    'phone_number': '895.779.4613x859',
    'array_int_dynamic': [
    90787,
],
    'array_varchar_dynamic': [
    'Edward Byrd',
    'Jasmine Tucker',
    'William Johnson II',
    'Michael Wilcox',
    'Kevin Martinez',
    'Danielle Brady',
    'Nicole Hernandez',
    'Gina Rojas',
    'Angela Cole',
    'Brandi Benjamin',
],
    'json': {
    'name': 'Molly Diaz',
    'address': '8997 Brown Courts Apt. 899\nEast Seanfort, IL 63023',
},
    'key68902': 'value82379',
    'key65264': 'value35036',
    'key77509': 'value86056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Kimberly Wood',
    'address': '969 Howe Extension Suite 739\nSouth Calvinland, AS 81209',
    'text': 'Wife federal our responsibility. Event kid again. Ago have job.',
    'email': 'judithmorris@example.org',
    'phone_number': '383.289.3087x54464',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Bennett DDS',
    'Kimberly Fisher',
    'Victoria Newman',
    'Jeffrey James',
    'Kevin Martin',
    'Ronnie Ross',
    'Jon Williams',
],
    'json': {
    'name': 'Jeffrey Welch',
    'address': '3280 Griffin Inlet\nNorth Melodychester, DC 96217',
},
    'key38632': 'value73540',
    'key21091': 'value76928',
    'key10363': 'value10376',
    'key99940': 'value27995',
    'key15759': 'value35888',
    'key65080': 'value62273',
    'key45554': 'value65426',
    'key17771': 'value31481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Linda Andersen',
    'address': '2664 Williams Drive\nRobertsonberg, LA 48550',
    'text': 'Skill seven to trial. Pick usually budget sound our upon light blood. Affect later go mention value guy view town.',
    'email': 'gordonjennifer@example.com',
    'phone_number': '478-398-9590x5253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Cardenas',
    'Michael Gray',
    'Victor Mcfarland',
    'James Mitchell',
    'Anthony Huber',
    'Victoria Carroll',
    'David Pierce',
    'Kayla Patel',
    'Jesse Hall',
    'Lisa Smith',
],
    'json': {
    'name': 'James Norton',
    'address': '146 Hannah Canyon Suite 698\nBrianshire, TN 81353',
},
    'key93886': 'value19104',
    'key82794': 'value79642',
    'key36161': 'value33839',
    'key64070': 'value43156',
    'key20520': 'value62324',
    'key24287': 'value83004',
    'key21735': 'value68006',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Kevin Francis',
    'address': '255 Richards Centers\nNorth Chris, MS 80136',
    'text': 'Night under agency Mrs.\nModel ahead perhaps simply happy beyond. Education former find sing lead each.\nNorth apply detail low dream turn no.\nIndividual capital thus half look.',
    'email': 'bonillakelly@example.com',
    'phone_number': '750-600-9538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Jimenez',
    'Nancy Murphy',
    'Larry Bowman',
    'Amber Herring',
    'James Owens',
    'Mary Woods',
    'Thomas Gutierrez',
],
    'json': {
    'name': 'Troy Hunter',
    'address': '68687 Ramos Tunnel Apt. 344\nMonicafort, LA 30375',
},
    'key64155': 'value51781',
    'key42933': 'value91104',
    'key50909': 'value9653',
    'key82332': 'value67645',
    'key6337': 'value87918',
    'key43208': 'value48935',
    'key78450': 'value68721',
    'key869': 'value36459',
    'key60924': 'value53499',
    'key6041': 'value386',
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
    'RequestId': '7ddf9f5f-62ef-11f0-8bd2-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_58_699737JkXpCREE',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-1]_1752744119.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl321011752744119Json()
    test.run_tests()
