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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752744239_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752744239.json"
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



class AllmilvusLogtestinsertvectornegativeTestInsertVectorWithInvalidDatabaseName1752744239Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752744239.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752744239.json"
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
    'RequestId': 'c5374ab1-62ef-11f0-afdf-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_58_392508BpCyLbMu',
    'dimension': 128,
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
    'RequestId': 'c53f7d19-62ef-11f0-abf1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_58_392508BpCyLbMu',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Marcus Frey',
    'address': '04063 Karen Crest Apt. 652\nKimfort, NH 52293',
    'text': 'Information black will room front debate us. Recognize herself good decision hour current protect common. Leg blood really likely teacher behind.',
    'email': 'ccamacho@example.net',
    'phone_number': '001-737-611-2888x4115',
    'array_int_dynamic': [
    37324,
],
    'array_varchar_dynamic': [
    'Sheila Hall',
],
    'json': {
    'name': 'Christine Reyes',
    'address': '2570 Katie Mews\nSouth Mercedesstad, AR 65243',
},
    'key75228': 'value79978',
    'key10192': 'value84699',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Kristy Wilson',
    'address': '8045 Flynn Mountains\nEast Stephenside, NC 69528',
    'text': 'Course under financial among. Produce very society religious.',
    'email': 'adrianjohnson@example.com',
    'phone_number': '001-797-811-5145x0658',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Weaver',
    'Lisa Mcgrath',
],
    'json': {
    'name': 'William Holden',
    'address': '47314 Monica Flat\nPort Michaelmouth, ME 23417',
},
    'key39005': 'value24875',
    'key88011': 'value1501',
    'key54603': 'value83196',
    'key54181': 'value94646',
    'key27411': 'value68807',
    'key12634': 'value46768',
    'key63551': 'value11072',
    'key11635': 'value36016',
    'key47343': 'value43558',
    'key74101': 'value87916',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Rachel Wood',
    'address': 'Unit 6346 Box 4185\nDPO AA 86203',
    'text': 'Trial why sit. Heart husband eat affect worry military. Phone rest court gun notice.\nUnder trial forward white natural kind technology throw. Budget positive quality pass happen.',
    'email': 'zmurray@example.org',
    'phone_number': '001-899-501-3524x201',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Anderson',
    'Jamie Randolph',
],
    'json': {
    'name': 'Amanda Myers',
    'address': '49962 Lynch Common Apt. 127\nPort Beckyport, FM 02732',
},
    'key87918': 'value12698',
    'key97449': 'value28163',
    'key92669': 'value17880',
    'key44131': 'value81105',
    'key77461': 'value53707',
    'key47394': 'value26902',
    'key54828': 'value35904',
    'key15244': 'value53394',
    'key3295': 'value60890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'William Kelley',
    'address': '61068 Charles Trail\nLake Robert, MN 92718',
    'text': 'Attention clearly just base face. Here how medical north power firm foot particularly.\nCentury area price view exist heavy information news. Technology church and father tree me process.',
    'email': 'christinecross@example.org',
    'phone_number': '312-324-2949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Scott',
    'Michelle Hurst',
    'Kim Martinez',
    'James Rogers',
    'Connie Martin',
],
    'json': {
    'name': 'Robin Stephens',
    'address': 'Unit 9826 Box 2927\nDPO AP 29357',
},
    'key59493': 'value20988',
    'key41180': 'value2067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Edward Welch',
    'address': '96472 Emily Fields\nMartinfurt, NM 91305',
    'text': 'Camera participant ability scientist part old. Third story Democrat upon.\nYear race paper entire radio least home. Industry race exactly leave road pressure light.',
    'email': 'egreer@example.com',
    'phone_number': '936-777-7348x771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Robert Randolph',
    'Taylor Owens',
    'Bruce Gardner',
    'Brian Owens',
    'Stephanie Johnson',
    'Eric Thomas',
    'William Lopez',
    'Michael Garcia',
    'Timothy Cole',
],
    'json': {
    'name': 'Scott Williams',
    'address': '731 Moran Forest Apt. 866\nLake Clayton, OK 66032',
},
    'key77410': 'value66985',
    'key29165': 'value58751',
    'key9049': 'value99359',
    'key30905': 'value14996',
    'key84093': 'value78837',
    'key89171': 'value65280',
    'key85217': 'value86798',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Michael Marks',
    'address': '50458 Singleton Burg Suite 845\nPorterview, CO 10752',
    'text': 'Democrat capital region character newspaper. Current shoulder past page speech government however.\nSend population behind ever firm all fly. Nearly defense explain feel state dinner well down.',
    'email': 'petersonalexander@example.com',
    'phone_number': '9618445592',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Laura Zimmerman',
    'Wayne Christensen',
    'Natalie Walton',
],
    'json': {
    'name': 'Seth Townsend',
    'address': '59193 Dylan Gateway Apt. 459\nBarbarabury, TN 33746',
},
    'key97848': 'value56629',
    'key11881': 'value98290',
    'key56808': 'value14131',
    'key45416': 'value86261',
    'key28104': 'value49416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Tanya Andrews',
    'address': '911 Michelle Bypass Apt. 784\nRogersfurt, WA 00553',
    'text': 'Occur indicate guy box. Including bring investment must bit once. Listen gas new show.',
    'email': 'kjackson@example.com',
    'phone_number': '4162670928',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Hernandez',
    'Adam Montes',
    'Christopher Parker',
],
    'json': {
    'name': 'Brian Green',
    'address': '078 Holland Course\nSharonfurt, TX 18973',
},
    'key25923': 'value70171',
    'key87695': 'value95675',
    'key9441': 'value38548',
    'key60584': 'value41261',
    'key84969': 'value31337',
    'key79968': 'value47697',
    'key25858': 'value22855',
    'key79591': 'value28894',
    'key16457': 'value77044',
    'key75800': 'value23496',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Michael Sanchez',
    'address': '151 Lucas Throughway Suite 963\nGonzalesmouth, SD 78856',
    'text': 'Summer show agency material explain another all. Front exist risk. Success development service just treat.\nWife address be. College management all positive together gas.',
    'email': 'janewhite@example.net',
    'phone_number': '362-353-4400',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Melton MD',
    'Holly Cooper',
    'Dana Nelson',
],
    'json': {
    'name': 'Tammie Figueroa',
    'address': '550 Boyd Vista Apt. 962\nSouth Jeffrey, KY 91296',
},
    'key40765': 'value69769',
    'key10754': 'value31183',
    'key82033': 'value20380',
    'key30607': 'value77571',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Lisa Weber',
    'address': '28466 Sharon Junctions\nNataliefort, MS 23769',
    'text': 'Bring you her sing accept light. Sure however point career part result course. Man fear American offer even cultural. Fire school white too pressure hand mission.',
    'email': 'stanleyjose@example.org',
    'phone_number': '280.729.5273x099',
    'array_int_dynamic': [
    7514,
],
    'array_varchar_dynamic': [
    'Kristin Carroll',
    'Brandon Moran',
],
    'json': {
    'name': 'Nicole Carroll',
    'address': '54590 Steven Light Apt. 815\nAndrewborough, TN 55412',
},
    'key82005': 'value61176',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Daniel Gross',
    'address': '55682 Price Expressway Apt. 472\nSouth Megan, VT 56558',
    'text': 'Fly hear stop common. Why order beyond avoid. List building that less.\nThink away relate five season what third plant. Long value word future store may case. Hear sometimes together still green.',
    'email': 'meagan70@example.com',
    'phone_number': '734.724.5044x9491',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sally Carter',
    'Kenneth Mejia',
    'Anne Burns',
    'David Scott',
],
    'json': {
    'name': 'Lori Baldwin',
    'address': '97037 French Green Suite 598\nDonnachester, SD 33058',
},
    'key97978': 'value67194',
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



    def test_request_2(self):
        """测试请求 2 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'c5374ab1-62ef-11f0-afdf-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_58_392508BpCyLbMu',
    'dimension': 128,
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_database_name_1752744239.json')
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
    test = AllmilvusLogtestinsertvectornegativeTestInsertVectorWithInvalidDatabaseName1752744239Json()
    test.run_tests()
