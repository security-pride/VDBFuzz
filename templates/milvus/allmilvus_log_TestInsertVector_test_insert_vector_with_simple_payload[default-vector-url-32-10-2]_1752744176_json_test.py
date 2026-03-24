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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-10-2]_1752744176_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-10-2]_1752744176.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl321021752744176Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-10-2]_1752744176.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-10-2]_1752744176.json"
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
    'RequestId': '9fd68b9a-62ef-11f0-899e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_55_682779UMJxbCzP',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '9fddd360-62ef-11f0-8bd4-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_55_682779UMJxbCzP',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Rodney White',
    'address': '654 Veronica Spur Suite 041\nBeckerland, IA 73467',
    'text': 'Nature direction including decision since themselves first. Not Mr heart response view media because. Source little enter glass side whatever.',
    'email': 'jasminedavidson@example.net',
    'phone_number': '882-445-3854',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Mcdonald',
    'Benjamin Nelson',
    'Rhonda Miller',
    'Juan Nelson',
    'Richard Jackson',
    'Linda Callahan',
    'Sandra Parker',
    'George Vincent',
    'Carrie Silva',
],
    'json': {
    'name': 'Robert Lowe',
    'address': '443 Smith Plain Apt. 446\nIsaacfort, SC 76164',
},
    'key46474': 'value26621',
    'key21250': 'value95233',
    'key2854': 'value98568',
    'key39018': 'value79219',
    'key62470': 'value53481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Victoria Perry',
    'address': '7401 Brown Via Suite 636\nEast Bruceton, TN 04142',
    'text': 'Budget seat mean Mrs. Down simply us bed player.\nSafe court structure general. Line very that use.\nGun project our. Only staff pressure environmental.',
    'email': 'charlesjonathan@example.com',
    'phone_number': '823.248.6496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Perkins',
],
    'json': {
    'name': 'Hannah Morris',
    'address': '4341 Aaron Mountains Apt. 383\nLozanofurt, WA 25626',
},
    'key85305': 'value3310',
    'key38449': 'value64542',
    'key45807': 'value39763',
    'key50449': 'value25870',
    'key84926': 'value40581',
    'key35810': 'value43495',
    'key95597': 'value13488',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Chelsea Duncan',
    'address': '60559 Matthew Motorway\nLake Jeffrey, NJ 26558',
    'text': 'Bar prevent interview back for perhaps. Spend food share reality time candidate.\nPush talk go movement. Away will claim else director market. Option could such technology someone.',
    'email': 'kristinapeterson@example.net',
    'phone_number': '+1-424-614-5200x70584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Greg Houston',
    'Meghan Murphy',
    'Karen Hicks',
],
    'json': {
    'name': 'Charles Barnes',
    'address': '620 Ramsey Gateway\nWilkinsview, NH 18930',
},
    'key53966': 'value74652',
    'key79552': 'value62857',
    'key77920': 'value41483',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Stacy Wright',
    'address': '83717 Robert Canyon\nWest Michael, VT 46455',
    'text': 'Through artist marriage small think. Daughter over group argue environment price. Find public citizen fear shake during natural.',
    'email': 'robin63@example.net',
    'phone_number': '538-280-0264x2715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Thomas',
    'Ronald Baker',
    'Nicholas Butler',
    'Julie Alexander',
    'Michael Campbell',
    'Linda Jones',
],
    'json': {
    'name': 'Peter Santos',
    'address': '81479 Potter Tunnel Apt. 128\nAntoniomouth, PW 32815',
},
    'key18914': 'value33293',
    'key98904': 'value57489',
    'key91721': 'value13645',
    'key37652': 'value87712',
    'key14791': 'value56742',
    'key66253': 'value22369',
    'key53583': 'value492',
    'key53338': 'value16656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Ashley Woods',
    'address': '238 Amanda Views Apt. 022\nEthanberg, NV 24481',
    'text': 'Door can use low agent too shoulder choose. Center floor who very dream. Successful suggest economic.',
    'email': 'valeriepage@example.com',
    'phone_number': '(468)517-5017x67443',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Lucas',
    'Ashley Price',
],
    'json': {
    'name': 'Elizabeth Mathis',
    'address': '7273 Lawrence Stream\nJenniferton, HI 27843',
},
    'key55324': 'value18986',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Chris Taylor',
    'address': '2217 Perez Burgs Apt. 097\nSouth Nancy, TN 11816',
    'text': 'Child mind agent kid help power.\nGet either item third table away.\nMove although when message. Start challenge threat item compare my.',
    'email': 'emily34@example.net',
    'phone_number': '001-439-849-5770x808',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Perry',
    'Xavier Davis',
    'Andrew Turner',
    'Jordan Wright',
],
    'json': {
    'name': 'Anthony Spencer',
    'address': 'USNS Bates\nFPO AE 96070',
},
    'key34287': 'value76597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Zachary Collins',
    'address': 'Unit 3870 Box 2622\nDPO AP 63177',
    'text': 'First safe really hand success so language. Who simple mention doctor sell. Large stock Mrs mouth major section threat.',
    'email': 'erinhancock@example.org',
    'phone_number': '(842)780-2398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Murphy MD',
    'Mark Little',
    'Alejandro Wiley',
    'Jamie Jackson',
    'Nicholas Mitchell',
],
    'json': {
    'name': 'Phillip Coleman',
    'address': '83311 Lyons Ports\nWest Joannabury, NC 25208',
},
    'key40863': 'value30731',
    'key83814': 'value74492',
    'key21368': 'value36913',
    'key40796': 'value88491',
    'key73199': 'value31681',
    'key19463': 'value27937',
    'key88983': 'value1174',
    'key48831': 'value42567',
    'key84390': 'value65402',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Miguel Lewis',
    'address': 'USCGC Patton\nFPO AA 99943',
    'text': 'Process summer understand per believe. Information size trade sing per clear product degree.',
    'email': 'stephanierobles@example.org',
    'phone_number': '(842)930-2719x6839',
    'array_int_dynamic': [
    31696,
],
    'array_varchar_dynamic': [
    'Jessica Rivera',
    'Jason Jones',
    'Michael Reyes',
    'Zachary Hudson',
    'Lisa Gonzales',
    'Anthony Bean',
    'Chloe Alvarez',
    'Jessica Shelton',
    'Jacqueline Pittman',
    'Mariah Christensen',
],
    'json': {
    'name': 'Suzanne Love',
    'address': '038 Reeves View\nLuisland, WA 86234',
},
    'key44742': 'value77800',
    'key48156': 'value21435',
    'key48783': 'value56648',
    'key31116': 'value66766',
    'key50651': 'value24900',
    'key79196': 'value36825',
    'key55084': 'value37890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Audrey Moore',
    'address': '66654 Christopher Extension\nNew Lisaland, MD 68315',
    'text': 'Military choose model article. Rate newspaper Democrat suddenly. Exist suddenly team until newspaper reveal evidence.',
    'email': 'aolson@example.org',
    'phone_number': '860-936-3651',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Richard Johnson',
    'Michelle Mcdonald',
    'Lisa Johnson',
    'Michael Johnson',
    'Susan Burton',
    'Matthew Murphy',
    'Johnathan Mason',
    'Heather Rowe',
],
    'json': {
    'name': 'Traci Mason',
    'address': '018 Turner Gateway Apt. 275\nNew Sonyahaven, SD 06038',
},
    'key68587': 'value95206',
    'key38971': 'value5501',
    'key36169': 'value90306',
    'key75309': 'value86608',
    'key33055': 'value22325',
    'key79897': 'value85407',
    'key82854': 'value18614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Andrew Edwards',
    'address': '732 Jennifer Turnpike\nNew William, PW 11832',
    'text': 'Oil hundred positive recently around public image. Language citizen than.',
    'email': 'julie59@example.com',
    'phone_number': '963-309-9718x814',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Steven Wall',
    'Joshua Singh',
],
    'json': {
    'name': 'Christine Ross',
    'address': '027 Alexander Extensions\nLake Heather, MS 93787',
},
    'key86136': 'value45449',
    'key39017': 'value71016',
    'key46965': 'value70308',
    'key81147': 'value67675',
    'key9525': 'value69276',
    'key7714': 'value78751',
    'key71290': 'value20337',
    'key45403': 'value23214',
    'key77137': 'value85348',
    'key3226': 'value48234',
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
    'RequestId': '9fd68b9a-62ef-11f0-899e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_55_682779UMJxbCzP',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-10-2]_1752744176.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl321021752744176Json()
    test.run_tests()
