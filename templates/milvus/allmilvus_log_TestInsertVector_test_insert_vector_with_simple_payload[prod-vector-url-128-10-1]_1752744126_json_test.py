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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-1]_1752744126_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-1]_1752744126.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl1281011752744126Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-1]_1752744126.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-1]_1752744126.json"
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
    'RequestId': '8223d1ef-62ef-11f0-a9da-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_05_857546TVrcFWwz',
    'dimension': 128,
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
    'RequestId': '822ba0c5-62ef-11f0-b76b-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_05_857546TVrcFWwz',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Miranda Wagner',
    'address': '1096 Duran Corners\nJohnsonstad, CA 53730',
    'text': 'Similar care though agree.\nFoot reason like even without. Course seem nearly civil. Audience really fear political mouth.',
    'email': 'zlong@example.com',
    'phone_number': '415-280-4036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Sara Craig',
    'William Harrison',
    'Lauren West',
    'Joseph Vazquez',
    'Karen Cardenas',
    'Donald Hood',
    'Denise Parker',
],
    'json': {
    'name': 'Jessica Jones',
    'address': 'USNV Long\nFPO AP 71034',
},
    'key2752': 'value92020',
    'key66867': 'value27692',
    'key58846': 'value35034',
    'key87037': 'value28082',
    'key715': 'value78545',
    'key6919': 'value7837',
    'key72354': 'value43391',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Andrew Blackburn DDS',
    'address': '17040 Ellis Pines\nDevonfurt, OR 88185',
    'text': 'Approach kitchen people center. Include class local over half organization. Official beyond wife imagine picture.',
    'email': 'leslie40@example.com',
    'phone_number': '986-728-8948',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joan Benton',
    'Troy Clarke',
    'Debra Castillo',
],
    'json': {
    'name': 'Melissa Todd',
    'address': '496 Richard Islands\nNorth Gary, CO 01094',
},
    'key82871': 'value67813',
    'key70051': 'value75915',
    'key34778': 'value26370',
    'key71975': 'value21080',
    'key99309': 'value30728',
    'key89105': 'value6076',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Kelly Reyes',
    'address': '88282 Garrett Drives Apt. 712\nHernandezberg, TX 38311',
    'text': 'Then program true. Girl year yeah weight season ten. Save process family certain foot red sense. Black science of despite.',
    'email': 'nnguyen@example.org',
    'phone_number': '616-563-8709x4026',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Beth Whitaker',
    'Paige Todd',
    'Robert Horton',
    'Robert Kerr',
    'Christine King',
    'Caleb Evans',
    'Robert Flowers',
    'Martin Daniels',
    'John Rush',
],
    'json': {
    'name': 'Melissa Gallagher',
    'address': '3847 Collins Knoll Apt. 641\nLisabury, TN 13532',
},
    'key66748': 'value75006',
    'key7937': 'value37990',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Mark Pineda',
    'address': '7347 King Ridges Suite 114\nRyanport, VT 01270',
    'text': 'Simple his rise pick movie democratic husband door. Full simply anyone. Within party provide.\nMaintain Democrat between raise help no accept.',
    'email': 'buckleyryan@example.org',
    'phone_number': '588-880-1988x72894',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Corey Ellison',
],
    'json': {
    'name': 'George House',
    'address': '24502 Alvarez Overpass\nEast Shannon, VI 27558',
},
    'key22452': 'value77261',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Meghan Peterson',
    'address': '362 James Drive\nCurtisberg, UT 31969',
    'text': 'Believe face research room ten try happy. Send recent role technology answer western building animal.',
    'email': 'bmontoya@example.com',
    'phone_number': '001-643-328-1267x040',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Cameron',
    'Lindsey Levy',
    'Elizabeth Garcia',
    'Glenn Sanchez',
    'Aaron Mosley',
],
    'json': {
    'name': 'Randy Hammond',
    'address': '300 Robert Point Apt. 170\nHernandezmouth, IA 22405',
},
    'key40333': 'value43865',
    'key2469': 'value56959',
    'key36905': 'value26750',
    'key77516': 'value91481',
    'key83547': 'value49271',
    'key39': 'value82769',
    'key786': 'value6005',
    'key80817': 'value66484',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Kenneth Mueller',
    'address': 'USNV Clark\nFPO AP 22166',
    'text': 'Tend have college compare. Wish do land describe.\nBoard partner action history list. Memory ok business commercial. Growth including style before story. Lay bring for in never decision.',
    'email': 'pamelasmith@example.org',
    'phone_number': '+1-944-834-6221x033',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Olsen',
    'Brittany Moore',
    'Brittney Mccarty',
    'Faith Johnson',
    'Nicholas Johnson',
    'Paula Glass',
    'Erin Barr',
    'Chelsea Harper',
    'Sandra Hutchinson',
    'Anthony Cohen',
],
    'json': {
    'name': 'Danielle Summers',
    'address': '256 Jared Neck Apt. 126\nLeeton, MH 87053',
},
    'key53254': 'value75872',
    'key33687': 'value87267',
    'key58198': 'value37875',
    'key90023': 'value251',
    'key43389': 'value23329',
    'key66568': 'value98163',
    'key83223': 'value9436',
    'key26122': 'value19487',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'David Farrell',
    'address': '96332 Sean Extension\nKeithside, NY 64176',
    'text': 'Part natural sign perform return western suffer. Red value cup like important they. Receive company source avoid.',
    'email': 'johnbaker@example.com',
    'phone_number': '(247)665-8268',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Avila',
    'Michelle Perkins',
    'Emily Oneal',
    'Tommy Johns',
    'Deborah Sweeney',
    'Jesse Perry',
    'Christopher House',
    'Robert Wagner',
    'Joshua Dean',
],
    'json': {
    'name': 'Xavier Jimenez',
    'address': '5424 Kathryn Springs Apt. 433\nCoreyborough, NM 80004',
},
    'key89038': 'value43891',
    'key44926': 'value60996',
    'key2116': 'value33654',
    'key82259': 'value18844',
    'key89284': 'value55381',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Sharon Fleming',
    'address': '3718 Wilson Village\nMillershire, WV 61626',
    'text': 'Half else although up clearly cover big section. Answer full way know item choice add. Top go little choose hospital serious from.',
    'email': 'egregory@example.net',
    'phone_number': '957-261-8507',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Julie Wiley',
    'Juan Stewart',
    'Karen Wallace',
    'Jacqueline Thomas',
    'Sandra Ramirez',
    'Brenda Grant',
    'Benjamin Coleman',
    'Scott Roberts',
],
    'json': {
    'name': 'Maria Manning',
    'address': '02902 Mitchell Plaza\nToddstad, MI 30475',
},
    'key20515': 'value95409',
    'key13861': 'value58610',
    'key41647': 'value84690',
    'key54341': 'value78468',
    'key45328': 'value8530',
    'key35253': 'value44852',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Cassandra Brooks',
    'address': '1185 Hunter Square Suite 315\nVictoriastad, FL 55816',
    'text': 'Plant do drive happy population assume easy. Mr until small a book.\nLoss color vote. Republican manager treat design green easy dog on.',
    'email': 'gilesmichelle@example.org',
    'phone_number': '(587)601-3212x380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Glenn Pena',
    'Alexander Jackson',
    'Kristin Williams',
    'Shelley Butler',
    'Summer Roach',
    'Thomas Ortega',
    'Christopher Austin',
],
    'json': {
    'name': 'Lawrence Wilson',
    'address': '179 Jordan Roads Apt. 203\nPort Annaborough, MP 09400',
},
    'key30312': 'value34806',
    'key43149': 'value89156',
    'key1927': 'value40545',
    'key4892': 'value91061',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Glenda Williams PhD',
    'address': '27694 Chen Dale Apt. 810\nPort Jimmy, AK 27053',
    'text': 'Work feeling risk political thought born perhaps. Event house significant.\nCareer walk president mouth. Poor candidate some feel agency purpose whom.',
    'email': 'shirleycompton@example.org',
    'phone_number': '+1-951-736-2739x4225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Belinda Crawford',
    'Edward Mcdonald',
    'Heather Olson',
    'Christina Scott',
    'Danielle Sloan',
    'Robert Flores',
    'Courtney Shelton',
],
    'json': {
    'name': 'John King',
    'address': '1401 April Shoal\nLake Amanda, CT 48384',
},
    'key29692': 'value17386',
    'key37021': 'value78277',
    'key64198': 'value52326',
    'key26500': 'value84872',
    'key89413': 'value80702',
    'key65186': 'value34613',
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
    'RequestId': '8223d1ef-62ef-11f0-a9da-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_05_857546TVrcFWwz',
    'dimension': 128,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-1]_1752744126.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl1281011752744126Json()
    test.run_tests()
