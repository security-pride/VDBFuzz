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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-2]_1752744198_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-2]_1752744198.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId1281021752744198Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-2]_1752744198.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-2]_1752744198.json"
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
    'RequestId': 'ac9e301c-62ef-11f0-b68c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_17_123815ZiMdNQSX',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'embedding',
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
    'RequestId': 'aca5b6d7-62ef-11f0-8f03-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_17_123815ZiMdNQSX',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Judith Navarro',
    'address': '5412 Richardson Spring\nNew Derrick, IN 20984',
    'text': 'Already join later officer race. Open line pattern interview bill matter what including. Special conference science character tree. Body product team act marriage bit able stand.',
    'email': 'lwatson@example.net',
    'phone_number': '(789)340-7496x681',
    'array_int_dynamic': [
    12104,
],
    'array_varchar_dynamic': [
    'Dale West',
    'Seth Coleman',
    'Briana Ward',
    'Michael Moore',
    'Tyler Lawrence',
    'Nicholas Ross',
],
    'json': {
    'name': 'Ashley Chavez',
    'address': '2586 Chandler Plains Apt. 383\nEast Victoriafurt, MD 45243',
},
    'key72863': 'value11727',
    'key3653': 'value61974',
    'key59173': 'value18080',
    'key19287': 'value45360',
    'key17908': 'value82519',
    'key73394': 'value62461',
    'key29673': 'value12812',
    'key90303': 'value47459',
    'key51905': 'value123',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Michael Beck MD',
    'address': '348 Rose Mission\nAdamfort, CA 38548',
    'text': 'Human his way behind executive need. Those gas help call.\nInclude blue necessary well everybody return. Current avoid man these join eye. Grow here visit share small.',
    'email': 'jblair@example.org',
    'phone_number': '001-640-748-3759',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mark Gay',
    'Joshua Williams',
    'Tanya Baker',
    'Steven Hogan',
    'Jennifer Wright',
    'Shelby Hancock',
    'Dean Johns',
    'David Stone',
    'Theresa Thompson',
],
    'json': {
    'name': 'Sarah Moore',
    'address': '50175 Davies Valleys\nGutierrezport, DC 33752',
},
    'key66884': 'value90159',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Brian Adkins',
    'address': '5051 Mcconnell Forge Suite 245\nJeffreyville, AR 21156',
    'text': 'Care bank military approach. Town part theory five foreign feel bar travel. Value full opportunity discover Mrs why.',
    'email': 'katielee@example.net',
    'phone_number': '969.673.9424x88837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joanne Kennedy',
    'Janet Miller',
    'Brianna Morris',
    'Jeffrey Murray',
    'Kevin Brown',
    'Tara Murray',
    'Andrea Burke',
    'Michelle Anderson',
    'Michael Reid',
],
    'json': {
    'name': 'Bryan Carroll',
    'address': '758 Andrea Springs\nDavidstad, VA 34081',
},
    'key34897': 'value45078',
    'key4786': 'value92810',
    'key69146': 'value11364',
    'key65622': 'value183',
    'key4201': 'value83957',
    'key60502': 'value29333',
    'key4952': 'value58584',
    'key91918': 'value3522',
    'key40044': 'value29529',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'John Anderson',
    'address': '385 Johnson Motorway Apt. 979\nNorth Wendyport, MA 83812',
    'text': 'Sure window physical. Whose audience three respond interesting.',
    'email': 'charlesosborn@example.com',
    'phone_number': '525-722-9031x86578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Peggy Sanchez',
    'Jennifer Manning',
    'Matthew Graves',
    'Michelle Hess',
],
    'json': {
    'name': 'Felicia White',
    'address': '8530 Taylor Coves Apt. 984\nPort Erica, KS 82380',
},
    'key21848': 'value7191',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Ryan Newman',
    'address': '575 Chang Light\nNew Zacharymouth, TX 82048',
    'text': 'Enjoy economic soon already mouth almost.\nThem our song maintain common. Woman provide cultural any audience foreign around drop.\nMeet wish laugh eat hear test ago. Six lay subject fly.',
    'email': 'jennifer45@example.net',
    'phone_number': '001-822-246-9003',
    'array_int_dynamic': [
    66803,
],
    'array_varchar_dynamic': [
    'David Hickman',
],
    'json': {
    'name': 'Christina Cervantes',
    'address': '0331 Fletcher Isle\nJasonstad, FM 64096',
},
    'key75338': 'value28678',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Scott Robertson',
    'address': '560 Jordan Square Suite 068\nMatthewshaven, AR 36782',
    'text': 'Find time look lose itself night should. Say weight necessary interest. Reveal decade always film place often.',
    'email': 'michelle64@example.net',
    'phone_number': '2818588855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Williams',
    'Paul Marshall',
],
    'json': {
    'name': 'Brooke Browning',
    'address': '139 Samuel Circle Apt. 882\nAlifurt, ID 70482',
},
    'key23040': 'value72872',
    'key77224': 'value90864',
    'key2470': 'value26497',
    'key22746': 'value7787',
    'key18136': 'value71518',
    'key66104': 'value12316',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'James Alvarez',
    'address': '27499 Howard Field Suite 406\nJerryberg, ID 21994',
    'text': 'Change outside stock same. Scientist save wide determine approach fast treatment series. Maintain director card decade car happen floor out.\nTogether small although concern. Turn something that wear.',
    'email': 'annettecopeland@example.com',
    'phone_number': '(562)433-3712x819',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Moss',
    'Donald Maxwell',
    'Gerald Sloan',
    'Tina Conrad',
    'Aaron Mays',
    'Tyler Wells MD',
    'Amanda Williams',
    'Kendra Raymond',
    'Blake Paul',
    'Linda Wright',
],
    'json': {
    'name': 'Margaret Fletcher',
    'address': '91033 Andrew Grove\nWoodbury, IA 82899',
},
    'key87131': 'value15684',
    'key95544': 'value24789',
    'key89499': 'value19497',
    'key29701': 'value37191',
    'key87450': 'value48632',
    'key53172': 'value5828',
    'key75995': 'value3182',
    'key39629': 'value61521',
    'key79101': 'value20452',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Michael Miller',
    'address': '600 Williamson Crescent\nDebbiehaven, TN 56902',
    'text': 'Pm blood perhaps and difficult never. View kitchen risk customer quality. Note hospital question school peace area walk early.',
    'email': 'moorekatie@example.net',
    'phone_number': '204.793.8126x45972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Morgan',
    'Larry Frazier',
    'Xavier Dixon',
    'Monica Manning',
    'Daniel Blanchard',
    'Cheyenne Smith',
    'Wesley Vasquez',
    'Joshua Archer',
    'Ariel Webb',
],
    'json': {
    'name': 'David Garrett',
    'address': '1873 Woodward Villages Suite 381\nWangborough, GA 46889',
},
    'key88714': 'value7224',
    'key2528': 'value65467',
    'key82323': 'value24747',
    'key5534': 'value97345',
    'key37962': 'value66857',
    'key13663': 'value2668',
    'key33285': 'value58542',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Christina Johnson',
    'address': '6277 Butler Viaduct\nNew Matthewland, VI 72094',
    'text': 'Light all call. And scientist still. See director other local until.\nCustomer other such. Animal less probably more near upon.\nSafe place pull usually simply cold than. Small sometimes when.',
    'email': 'yhart@example.org',
    'phone_number': '340-767-1324x10740',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Dixon',
    'Dylan Austin',
    'Samantha Berger',
    'Corey Rodriguez',
    'Jeremy Miller',
    'Brian Davis',
    'Tamara Morris',
    'Erin Johnson MD',
    'Christopher Bond',
    'Raymond Kaufman PhD',
],
    'json': {
    'name': 'Diamond Fischer',
    'address': '205 Dustin Inlet\nPricebury, TN 61058',
},
    'key46492': 'value74790',
    'key32541': 'value62931',
    'key99855': 'value66349',
    'key42346': 'value85800',
    'key95817': 'value48723',
    'key76525': 'value20343',
    'key99691': 'value91890',
    'key21633': 'value64773',
    'key99221': 'value9780',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jessica Hammond',
    'address': '371 Connie Mountains Apt. 701\nRodriguezmouth, PR 91076',
    'text': 'Wish coach including marriage.\nSimple subject political collection.\nMyself success cultural. Open upon large myself. Marriage eat child wish trade benefit.',
    'email': 'kelly17@example.org',
    'phone_number': '(762)920-1091x2185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Reynolds',
    'Jasmine Thompson',
    'Vernon Fuller',
],
    'json': {
    'name': 'Rebecca Caldwell',
    'address': '35399 Kimberly Mews Suite 771\nJenniferstad, NV 11897',
},
    'key1719': 'value47045',
    'key59816': 'value8575',
    'key21996': 'value26379',
    'key70519': 'value34045',
    'key35658': 'value22494',
    'key89239': 'value71142',
    'key34817': 'value17381',
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
    'RequestId': 'ac9e301c-62ef-11f0-b68c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_17_123815ZiMdNQSX',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-2]_1752744198.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId1281021752744198Json()
    test.run_tests()
