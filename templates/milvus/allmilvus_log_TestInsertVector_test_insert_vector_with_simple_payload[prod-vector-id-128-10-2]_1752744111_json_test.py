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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-2]_1752744111_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-2]_1752744111.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId1281021752744111Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-2]_1752744111.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-2]_1752744111.json"
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
    'RequestId': '78f4ab06-62ef-11f0-85dd-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_50_449041zEZEadzm',
    'dimension': 128,
    'primaryField': 'id',
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
    'RequestId': '78fb5320-62ef-11f0-a957-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_50_449041zEZEadzm',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Cynthia Murphy',
    'address': '629 Mitchell Mill\nNew Brittanyland, WA 41568',
    'text': 'Without site investment right fire. Reflect activity interesting worker above.\nLife find well professional try activity manager spring. Third few nor her suggest run.',
    'email': 'nicholasschmidt@example.net',
    'phone_number': '6172779546',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amy Carlson',
    'Raymond Reed',
    'Priscilla Wise',
    'Jacqueline Morales',
    'Jonathan Rios',
    'Miguel Ford',
],
    'json': {
    'name': 'Daniel Jackson',
    'address': 'USNV Shields\nFPO AP 25546',
},
    'key30949': 'value94449',
    'key55512': 'value89643',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Julie Myers',
    'address': '309 Gonzales Key Suite 327\nPort Alicia, MI 91992',
    'text': 'Standard knowledge break speak reflect one.\nWe assume against. Spend church those sell western pick interesting. Consider instead its.\nDark these good pick foot act evidence.',
    'email': 'clarkjoel@example.net',
    'phone_number': '9897115244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Harvey',
    'Samantha Sullivan',
],
    'json': {
    'name': 'Edward Petty',
    'address': '08421 Robert Fall\nCodytown, MP 67056',
},
    'key56546': 'value57815',
    'key5321': 'value869',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Felicia Mcdonald',
    'address': '084 Holly Lakes Suite 566\nJoshuamouth, FM 14573',
    'text': 'Still officer hope. Performance economy read sense strong.\nProve well fact bad nation ability total. North member suffer yeah her draw. Factor treat lot.',
    'email': 'ddoyle@example.net',
    'phone_number': '6515104529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Bolton',
    'Colleen Lambert',
    'Madison Bond',
    'Adam Miles',
    'Jamie May',
    'Mark Valdez',
    'Matthew Martinez',
],
    'json': {
    'name': 'Yvette Baker',
    'address': '6971 Rachel Mills Suite 243\nMelissaborough, SD 56832',
},
    'key18495': 'value33116',
    'key58446': 'value30146',
    'key95482': 'value9856',
    'key35881': 'value93195',
    'key8423': 'value92957',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jennifer Oliver',
    'address': '3812 Ann Trail\nLake Calvin, IN 80976',
    'text': 'Away officer interest keep throughout style. Team bill have sister travel practice prove. Wish member hour.\nApply plant join authority himself house girl. Fear sea popular start clear hour vote.',
    'email': 'justin72@example.com',
    'phone_number': '(276)820-7882x83899',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angel Murphy',
    'Catherine Rice',
    'Phillip Moses',
    'Amber Gross',
],
    'json': {
    'name': 'Angelica Watson',
    'address': '77989 Cox Underpass Apt. 082\nSchultzhaven, UT 36595',
},
    'key81629': 'value30104',
    'key95616': 'value23506',
    'key80481': 'value68917',
    'key80529': 'value55828',
    'key88872': 'value42098',
    'key65021': 'value37420',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Sean Snyder',
    'address': '92492 Jason Loaf\nNew Rebecca, AZ 37884',
    'text': 'Even necessary world control design. Always family ever town school. Enter agent or people participant country place writer. Too day my best.',
    'email': 'nkelley@example.net',
    'phone_number': '(813)552-2499x867',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Frank Dorsey',
    'Aaron Walsh',
    'Joseph Wheeler',
    'Valerie Cisneros',
    'Dylan Garza',
    'Nathan Woods',
],
    'json': {
    'name': 'David Foster',
    'address': '607 Thompson Fords Suite 786\nWagnerfurt, AS 64933',
},
    'key92563': 'value49273',
    'key50952': 'value98562',
    'key42297': 'value54534',
    'key86243': 'value57964',
    'key19227': 'value56839',
    'key82727': 'value92397',
    'key86382': 'value81308',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Linda Williams',
    'address': '034 Maldonado Street Suite 673\nSteelefort, MP 97287',
    'text': 'Natural water produce. South seem western everybody. Future party street turn skin defense Mr language.\nWill local than generation city. Relate participant child seem.',
    'email': 'debraroberts@example.org',
    'phone_number': '001-255-979-8052x9024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Paul Miller',
    'Kathryn Mcneil',
    'Karen Ellis',
    'Cynthia Johnson',
    'Jill French',
],
    'json': {
    'name': 'Traci Carter',
    'address': '17848 Li Road Apt. 765\nEast Darrell, CO 02853',
},
    'key63290': 'value64196',
    'key7019': 'value42827',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Lauren Taylor',
    'address': '6057 Michael Mountain Suite 512\nCummingsberg, LA 84244',
    'text': 'Many business us rest research. Agreement back hundred occur others defense.\nRecent huge will society PM me. Rather four evening. Alone style simply security ok.',
    'email': 'zstanley@example.org',
    'phone_number': '219-323-9129x035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Wilson',
],
    'json': {
    'name': 'Laura Evans',
    'address': '74387 Levi Burg Suite 491\nSouth Juliastad, TX 90269',
},
    'key63359': 'value61123',
    'key79584': 'value36021',
    'key65714': 'value95501',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joseph Moss',
    'address': '4311 Thomas Park\nWest Curtisfort, PW 42313',
    'text': 'Low cut budget may treat somebody gun. Picture skill result civil program name.',
    'email': 'victoria95@example.net',
    'phone_number': '633-727-5954x10515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Angie King',
],
    'json': {
    'name': 'Connie Mckay',
    'address': '46481 Daniel Viaduct\nPrestonton, NC 98355',
},
    'key91030': 'value4450',
    'key71646': 'value19496',
    'key16645': 'value31960',
    'key99059': 'value49938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jessica Mora',
    'address': '655 Bailey Burg Apt. 950\nKellytown, IA 13841',
    'text': 'After activity card field.\nBuild officer relationship after miss. Onto reach market tax. Help suffer different. Side care animal myself movie.',
    'email': 'eric51@example.net',
    'phone_number': '7804596449',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Moon',
],
    'json': {
    'name': 'Melody Hansen',
    'address': '46638 Carr Canyon\nWest Anthonyfurt, VA 28283',
},
    'key10503': 'value35365',
    'key17052': 'value17076',
    'key35859': 'value24151',
    'key14993': 'value37049',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Tyler Wong',
    'address': '232 Howell Pine Apt. 843\nSouth Kevin, CA 83378',
    'text': 'Idea natural us away conference imagine top. Live poor consider check perhaps represent.\nTo exactly organization night culture might. Matter cause can how general. Imagine guy treatment argue wrong.',
    'email': 'williamsthomas@example.net',
    'phone_number': '(687)621-7357x74537',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Adams',
    'Michael Woodard',
    'Megan Kent',
    'Sherry Rodriguez',
],
    'json': {
    'name': 'Keith Frank',
    'address': '9265 Jody Oval\nHoffmanmouth, GA 45046',
},
    'key74259': 'value82261',
    'key66972': 'value67472',
    'key14446': 'value42941',
    'key20488': 'value9783',
    'key24102': 'value72127',
    'key15854': 'value75401',
    'key37079': 'value42864',
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
    'RequestId': '78f4ab06-62ef-11f0-85dd-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_50_449041zEZEadzm',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-2]_1752744111.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId1281021752744111Json()
    test.run_tests()
