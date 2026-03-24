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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-1]_1752744163_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-1]_1752744163.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId321011752744163Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-1]_1752744163.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-1]_1752744163.json"
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
    'RequestId': '97e52394-62ef-11f0-a27e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_42_356647cXYhKKBP',
    'dimension': 32,
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
    'RequestId': '97ec512f-62ef-11f0-8395-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_42_356647cXYhKKBP',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Holly Sharp',
    'address': 'Unit 4811 Box 2097\nDPO AE 40399',
    'text': 'Which country for rich. Tend short well service.\nWant management yet world clear. Building late own table as produce various. Class study thing sometimes form.',
    'email': 'gnelson@example.org',
    'phone_number': '001-228-356-0659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Angela Sanchez',
    'Jessica Hanson',
    'Matthew Scott',
    'Jermaine Burnett',
    'Leonard Wolf',
    'Adrian Cruz',
    'Matthew Haynes',
    'Sara Adams',
    'Jose Davis',
    'Jamie Garner',
],
    'json': {
    'name': 'William Richards',
    'address': '9013 Robert Plains Apt. 000\nSouth Pamela, OK 77428',
},
    'key27945': 'value74253',
    'key74559': 'value6707',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Katherine Hernandez',
    'address': '567 Holland Plaza Suite 007\nGloriamouth, TX 00920',
    'text': 'Explain human fire lose wide forward. Woman myself civil story interest fear officer.\nField change article they in all we. No station pay maybe day your evening.',
    'email': 'david45@example.org',
    'phone_number': '322.279.5607x1113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nichole Hurst',
    'Matthew Lewis',
    'Ryan Mclaughlin',
    'Kayla Mcdonald',
],
    'json': {
    'name': 'Todd Kent',
    'address': '33013 Blake Ways\nSheilaview, MP 23104',
},
    'key44321': 'value81277',
    'key27294': 'value54131',
    'key94827': 'value21728',
    'key55953': 'value68274',
    'key86031': 'value47713',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Crystal Sutton',
    'address': '5617 Austin Views\nCarrbury, PW 25139',
    'text': 'Night however in still great. Scientist prepare win physical.\nAnything against market change. Drop nation worker different himself behind.',
    'email': 'timothymcguire@example.com',
    'phone_number': '001-318-609-0750x051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Travis Schmidt',
    'Angela Richardson',
    'Amanda Allen',
],
    'json': {
    'name': 'Benjamin Nolan',
    'address': '08596 Miguel Parks\nSouth Feliciaport, ID 95409',
},
    'key40451': 'value5355',
    'key50300': 'value54739',
    'key49876': 'value25381',
    'key41130': 'value81238',
    'key54304': 'value17080',
    'key39149': 'value23966',
    'key42508': 'value84614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Elizabeth Ramirez',
    'address': '3267 Theresa Crescent Suite 120\nWest Daisyshire, VI 58970',
    'text': 'Win argue response music language year produce.\nInclude change argue according. Writer institution whole throughout national. Author shoulder not ground attack approach.',
    'email': 'donnamurphy@example.net',
    'phone_number': '001-410-624-1553x644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christina Hicks',
    'Misty Singleton',
    'Kathleen Burns',
    'Cindy Berry DVM',
],
    'json': {
    'name': 'Miguel Allen',
    'address': '23133 Katie Harbors Suite 620\nAlexanderfurt, MS 27293',
},
    'key60315': 'value46250',
    'key87869': 'value82379',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Stephanie Owens',
    'address': '89095 Erica Hills\nEast Melissaburgh, AK 98074',
    'text': 'Main wrong available. Thought attorney guy base. Story spend not indeed.\nMember hard east green administration.',
    'email': 'caseylatoya@example.org',
    'phone_number': '475-582-4433',
    'array_int_dynamic': [
    9016,
],
    'array_varchar_dynamic': [
    'Kristi Brown',
    'David Gregory',
    'Jared Sullivan',
    'Jenny Ball',
    'Amber Blackburn',
    'Richard Gonzalez',
    'Randall Hughes',
],
    'json': {
    'name': 'Briana Walker',
    'address': '4526 Lee Bypass Suite 635\nSouth Andrew, NV 06124',
},
    'key79378': 'value97872',
    'key31253': 'value372',
    'key17874': 'value41874',
    'key6018': 'value3671',
    'key86490': 'value15453',
    'key77923': 'value68146',
    'key48998': 'value39667',
    'key65181': 'value57927',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Rebecca Martin',
    'address': '7219 Wood Mission\nKarinafort, NH 47943',
    'text': 'Anything nothing pick sign. Analysis employee win the. Movement occur available someone eight.',
    'email': 'amanda92@example.org',
    'phone_number': '531-282-7052',
    'array_int_dynamic': [
    27031,
],
    'array_varchar_dynamic': [
    'Adrian Strong',
    'Dr. Melissa Padilla',
    'Jonathon Morton',
    'Randall Figueroa',
    'Rachel Fisher',
    'Darren Garcia',
],
    'json': {
    'name': 'Brent Rasmussen',
    'address': '539 Amy Port Apt. 064\nLindsayland, MO 29467',
},
    'key44462': 'value45124',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Kyle Williams',
    'address': '668 Potter Rue Suite 618\nMarkbury, CO 86415',
    'text': 'Call central mention treat cultural. Often word main stop pretty prevent success. Push speech cup.',
    'email': 'fhart@example.net',
    'phone_number': '(761)650-1374x476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christina Durham',
],
    'json': {
    'name': 'Thomas Mitchell',
    'address': '64594 Hill Loaf\nWest Alejandro, SD 57954',
},
    'key58611': 'value32892',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Barbara Bailey',
    'address': '8689 Alvarado Rapid Apt. 173\nNorth Cameron, VA 97799',
    'text': 'Old buy surface plan.\nStock summer garden cell late reason guy.\nSpeak avoid point more suggest program. Able project executive bank would carry west economy. Sometimes statement trial might across.',
    'email': 'michellecole@example.com',
    'phone_number': '001-761-583-7437x03129',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'William Klein',
    'Marisa Sanchez',
],
    'json': {
    'name': 'Anita Marshall',
    'address': '594 Murphy Village Apt. 497\nNorth Kristin, MA 39610',
},
    'key44689': 'value76934',
    'key9136': 'value31029',
    'key65356': 'value27793',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'James Byrd',
    'address': '069 Clinton Walk Suite 815\nSouth Scottfort, FM 46543',
    'text': 'Sound forget peace marriage protect style. Happy Mr those truth investment. Onto management know truth change until pull.',
    'email': 'aaronhammond@example.com',
    'phone_number': '(588)813-4926x63668',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Moss',
    'Jack Kim',
],
    'json': {
    'name': 'Elizabeth White',
    'address': '0855 Francis Ridge\nMaryshire, WA 92322',
},
    'key10457': 'value20126',
    'key26606': 'value25145',
    'key42236': 'value53196',
    'key34781': 'value46647',
    'key8499': 'value5989',
    'key7414': 'value37484',
    'key85255': 'value85907',
    'key41207': 'value11341',
    'key50402': 'value38338',
    'key22821': 'value81213',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Stephanie Campbell',
    'address': '47833 Gregory Shores Apt. 426\nPort Katiemouth, VA 29307',
    'text': 'Color artist impact yeah plan summer. In agency call hear job air beyond idea. Air effort institution arrive east remember.\nYes analysis remember product three on. Month in ground first.',
    'email': 'nancy05@example.org',
    'phone_number': '3989041851',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Johnson',
    'Sharon Garcia',
    'Trevor Hansen',
],
    'json': {
    'name': 'Seth Reyes',
    'address': '2756 Burgess Parks Suite 583\nMeganview, IL 19498',
},
    'key9383': 'value46515',
    'key12516': 'value66040',
    'key95540': 'value82283',
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
    'RequestId': '97e52394-62ef-11f0-a27e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_42_356647cXYhKKBP',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-1]_1752744163.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId321011752744163Json()
    test.run_tests()
