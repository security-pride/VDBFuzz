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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 0_1]_1752745087_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 0_1]_1752745087.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid011752745087Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 0_1]_1752745087.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 0_1]_1752745087.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b7c2b33a-62f1-11f0-a980-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_54_811495ZyAgXkNO',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
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
    'RequestId': 'bae1dc1e-62f1-11f0-8b27-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_54_811495ZyAgXkNO',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Ricky Nguyen',
    'address': '8775 Miller Shoal Suite 278\nLake Jessica, IA 58378',
    'text': 'Season military factor commercial. Approach bed tree difference.\nDefense book show. Knowledge on wrong tend.\nAmerican large specific evening. Happen record perform sister program.',
    'email': 'davisyolanda@example.org',
    'phone_number': '001-907-590-6520x1747',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Maria Fisher',
    'George Guerrero',
],
    'json': {
    'name': 'Lori Miller',
    'address': '0478 Danielle Roads\nPort Kristinmouth, IN 81315',
},
    'key29626': 'value18745',
    'key3': 'value12437',
    'key35351': 'value96995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Brittney Kelly',
    'address': '00820 Sanders Mews\nDeniseborough, AR 16882',
    'text': 'Page ok rate couple enjoy. New remember work college tough may. Her line defense beyond current.',
    'email': 'bjohnson@example.org',
    'phone_number': '+1-621-801-2594x1006',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Susan Young',
    'Nancy Mercer',
    'Anthony Landry',
    'Collin Martinez',
    'Laura Richmond',
    'Katie Brown',
    'Victoria Potts',
],
    'json': {
    'name': 'Tracy Berry',
    'address': 'Unit 2164 Box 3940\nDPO AE 08118',
},
    'key86074': 'value89892',
    'key3317': 'value65472',
    'key1903': 'value79333',
    'key34970': 'value72919',
    'key80611': 'value69313',
    'key68341': 'value16980',
    'key76759': 'value55648',
    'key94136': 'value19953',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Michael Parsons',
    'address': '81377 Jennifer Ford Suite 600\nJanemouth, AZ 69196',
    'text': 'Various night hospital box. Wall section somebody.\nAssume book between national. Guy sometimes serve hard actually.\nTonight letter four federal allow south. Because share herself yet.',
    'email': 'martinezraymond@example.net',
    'phone_number': '555-732-9092',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tommy Pittman',
    'Emily Davis',
    'Elizabeth Lee',
    'Ashley Mccarty',
    'Lisa Patel',
],
    'json': {
    'name': 'Dana Miller',
    'address': '3514 Spence Gardens Suite 493\nBarrettborough, MS 52582',
},
    'key25529': 'value30038',
    'key50753': 'value4239',
    'key98320': 'value19561',
    'key8673': 'value32801',
    'key87794': 'value40341',
    'key89064': 'value30634',
    'key53249': 'value11797',
    'key59259': 'value35511',
    'key70026': 'value18023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'George Gonzalez',
    'address': '43927 Wood Plaza Suite 104\nMelissahaven, GU 16311',
    'text': 'Ask one line paper sing your edge. Cause soon hit more yeah market.\nWithin item represent wish within full manage thus. Approach major month picture such place less. House occur race save.',
    'email': 'suzanne28@example.com',
    'phone_number': '001-815-233-1211',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Porter',
    'Kimberly Anderson',
],
    'json': {
    'name': 'Susan Fisher',
    'address': '9677 Thompson Loop\nPort Michael, CO 47842',
},
    'key74030': 'value44349',
    'key35932': 'value78017',
    'key55811': 'value1284',
    'key28486': 'value50969',
    'key84732': 'value22562',
    'key36592': 'value87658',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Luke Castro',
    'address': '6009 John Plaza Suite 317\nDonaldland, VA 82422',
    'text': 'Hard discover TV east item. Positive management cup wind will task seven clear.\nSoon answer language agreement provide. Seven feeling camera cup Republican economic.',
    'email': 'michael34@example.org',
    'phone_number': '001-819-296-0880x122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Clark',
],
    'json': {
    'name': 'Dustin Wheeler',
    'address': '91577 David Parks Suite 227\nHintontown, TX 99503',
},
    'key82459': 'value13722',
    'key83970': 'value38124',
    'key16417': 'value49416',
    'key24784': 'value55498',
    'key26203': 'value50509',
    'key97317': 'value25281',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Sarah Carlson',
    'address': '392 Kelly Mountain\nBuckfort, AS 05471',
    'text': 'Hold modern partner deal much wait space. Wall store artist fast. Investment beat miss threat hit there organization.',
    'email': 'slopez@example.net',
    'phone_number': '+1-743-489-8096',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Mccarthy',
    'Eric Lyons',
    'Marcus King',
    'Jennifer Sanchez',
    'Cynthia Smith',
    'Jason Proctor',
    'Andrew Alvarez',
    'Jasmine Moran',
    'Leah Jackson',
    'Cassandra Herrera',
],
    'json': {
    'name': 'Joseph Castillo',
    'address': '338 Dudley Gardens\nLake Megantown, PW 47745',
},
    'key60002': 'value15781',
    'key67801': 'value65493',
    'key47493': 'value42056',
    'key58330': 'value8322',
    'key46594': 'value49589',
    'key32730': 'value92298',
    'key22961': 'value2200',
    'key2431': 'value1897',
    'key61890': 'value57947',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kimberly Young',
    'address': '120 Jones Loop\nKaylamouth, FL 30562',
    'text': 'Court imagine natural role tend. Trade employee look wife well week. Leg eight interesting way seem range wonder gas. Color be whose center century staff her.',
    'email': 'smorris@example.net',
    'phone_number': '411.963.7317x33912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Schmidt',
    'Taylor Moreno',
    'Kelsey Mclaughlin',
],
    'json': {
    'name': 'Lucas Clements',
    'address': '806 Keller Square\nNew Jesse, LA 58150',
},
    'key50896': 'value91433',
    'key39098': 'value54139',
    'key96797': 'value30247',
    'key18507': 'value982',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Linda Graham',
    'address': '08186 Hill Manor\nLake Danielleville, MA 47265',
    'text': 'Hand always similar meet.\nTry so edge need loss yet. Gas different person beyond. Throw city choice hour can he.',
    'email': 'curtisrebecca@example.net',
    'phone_number': '593-801-1857x2249',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Sullivan',
    'Eric Alvarez',
    'Jessica Hartman MD',
    'Gordon Garcia',
    'Crystal Sanders',
    'Stephen Shaw',
],
    'json': {
    'name': 'Joseph Aguilar',
    'address': '5490 Wilson Overpass Suite 307\nPort Duane, NE 41519',
},
    'key55566': 'value1058',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Michael Allen',
    'address': '53347 Greene Springs Suite 450\nWest Lee, NE 78325',
    'text': 'Our well foot energy her. Popular one rise defense others realize newspaper mission. People note fly spend move everybody.\nDesign able surface economy. Happen from more her thus person.',
    'email': 'vwhite@example.com',
    'phone_number': '001-578-206-5788x798',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Morris',
    'Jennifer Kent',
    'Mitchell Powers',
    'George Graves',
    'Sylvia Briggs',
    'Joseph Nguyen',
    'Brittany Jenkins',
],
    'json': {
    'name': 'Heather Mitchell',
    'address': '473 Kyle Fields\nSinghside, AR 61258',
},
    'key30375': 'value98686',
    'key76707': 'value90385',
    'key81318': 'value78573',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Michael Wade',
    'address': '646 Gregory Wall Apt. 530\nWest Nicoletown, NJ 22949',
    'text': 'Also natural various from effect indeed. Address item drop recently news water. After good wonder oil. Put especially important century along majority.',
    'email': 'johnbeltran@example.com',
    'phone_number': '(325)458-4523x2693',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Charles Vaughan',
    'Mary Hernandez',
    'Katie Carey',
    'Heather Sanchez',
    'Gabriella Harvey',
    'Micheal Austin',
    'Paul Miller',
    'Timothy Kennedy',
    'William Perez',
],
    'json': {
    'name': 'Katrina Hurst',
    'address': '98441 Reyes Ranch\nPatriciaburgh, GU 35200',
},
    'key95560': 'value78960',
    'key87767': 'value73641',
    'key93416': 'value7456',
    'key35895': 'value44935',
    'key32905': 'value73153',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Melissa Wilkerson',
    'address': '77444 Steven Corners Suite 448\nNorth Timothyside, PA 64906',
    'text': 'Himself fear meeting. Once firm visit always all foot nation.\nInteresting put apply lay make computer agree. Ground on sister spend. Wind specific behind now Democrat change create.',
    'email': 'jonathan67@example.net',
    'phone_number': '769.230.5239x0851',
    'array_int_dynamic': [
    28888,
],
    'array_varchar_dynamic': [
    'Julia Ryan',
    'Craig Francis',
    'Virginia Gonzales',
    'Paul Ryan',
    'Barbara Duncan',
    'Henry Burnett',
    'Ryan Johnston',
    'Kristin Keller',
    'Monica Wood',
    'Hunter Riley',
],
    'json': {
    'name': 'Kelli Taylor',
    'address': '692 Wallace Ranch\nRachelmouth, AL 65515',
},
    'key35154': 'value48080',
    'key7253': 'value90822',
    'key49183': 'value79346',
    'key83738': 'value94045',
    'key40856': 'value80641',
    'key31418': 'value16886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Paul Rios',
    'address': '17021 Brown Spur\nNew Marissastad, VA 08579',
    'text': 'Traditional our part establish material strong often Mr. Weight floor them need stage all sit. Your everybody situation involve.',
    'email': 'isabellataylor@example.org',
    'phone_number': '001-438-771-3243x98896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Martin',
    'Jason Vasquez',
    'Katrina Velasquez',
    'Frank Castillo',
    'April Hubbard DDS',
    'Douglas Parker',
    'Cassandra Donovan',
    'Wendy Cuevas',
    'Jessica Rasmussen',
],
    'json': {
    'name': 'Mrs. Crystal Smith DDS',
    'address': '139 Matthew Field\nKatherinehaven, VI 81036',
},
    'key80414': 'value99236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Sydney Perez',
    'address': '4701 Perkins Port\nLake Yvette, MH 79511',
    'text': 'Skin we real bill war.\nBecome same entire oil would. Movement onto very activity man the.\nPretty once professor thing hotel ahead society. Particularly travel spend focus assume.',
    'email': 'tonyabryant@example.org',
    'phone_number': '590-674-9452x523',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Austin Barnett',
    'Michelle Wang',
    'Madison Hall',
    'Cindy Page',
],
    'json': {
    'name': 'Garrett Moore Jr.',
    'address': '6124 Foster Manor\nSouth Troyfurt, MH 81753',
},
    'key34794': 'value38791',
    'key92948': 'value23172',
    'key39476': 'value42628',
    'key80931': 'value15345',
    'key86180': 'value18470',
    'key62828': 'value10183',
    'key24273': 'value17744',
    'key53113': 'value53163',
    'key76460': 'value70961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Shawna Hicks',
    'address': '46254 Duncan Pike\nHuntfurt, IL 36806',
    'text': 'Us bad official. Everyone have and south late why attack nearly. Hope hospital good drug enjoy difficult.\nPresident others member phone cut prepare mention.',
    'email': 'ckelley@example.com',
    'phone_number': '001-715-595-3157x49540',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Beck',
    'Francisco Durham',
    'Anthony Perez',
    'Tina Patton',
    'Michael Wilson MD',
    'Paul Rivera',
    'Kimberly Mueller',
    'Jane Hooper',
],
    'json': {
    'name': 'Wendy Valdez',
    'address': '416 Wheeler Grove\nSouth Caitlinmouth, ND 47086',
},
    'key25366': 'value17577',
    'key8653': 'value92986',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Alexander Brown',
    'address': '26256 Todd Trace\nSouth Valerie, TX 68579',
    'text': 'Issue side defense.\nLetter others sea positive official once explain.',
    'email': 'xjennings@example.net',
    'phone_number': '220-805-2945x0815',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jill Buck',
],
    'json': {
    'name': 'Justin Floyd',
    'address': '671 Barnes Plaza\nJohnstad, UT 08807',
},
    'key80375': 'value18234',
    'key98168': 'value39995',
    'key51017': 'value58226',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Christine Jenkins',
    'address': '1486 Matthew Spring\nKarenport, NM 07664',
    'text': 'Huge table us indeed green personal before. Social expect partner pretty. North fish investment decade situation respond.',
    'email': 'narnold@example.com',
    'phone_number': '285.354.4170x2185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Figueroa',
    'Lauren Greer',
    'David Beck',
    'Chris Brandt',
],
    'json': {
    'name': 'Mrs. Jacqueline Jenkins MD',
    'address': '932 Carlos Village\nMosleymouth, MT 10137',
},
    'key20991': 'value51612',
    'key88215': 'value77918',
    'key47964': 'value48378',
    'key9088': 'value98910',
    'key20987': 'value7874',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Andre Beasley',
    'address': '56821 Luis Plaza Suite 971\nOsbornebury, MP 62208',
    'text': 'Cost heart least whatever wind. Attention perhaps energy. Of after training million relate center.\nGood begin baby none.\nTown hundred church really truth night present.',
    'email': 'payneamanda@example.net',
    'phone_number': '6848512919',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Danny Schmitt',
    'Dr. Nancy Anderson DDS',
    'Victoria Butler',
],
    'json': {
    'name': 'Paul Anderson DDS',
    'address': '41616 Mclaughlin Canyon Suite 294\nMillerberg, MO 29494',
},
    'key34168': 'value31383',
    'key54343': 'value17073',
    'key73900': 'value85320',
    'key47396': 'value80244',
    'key15869': 'value23589',
    'key48191': 'value9878',
    'key23080': 'value51815',
    'key20908': 'value73914',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Darius King',
    'address': '370 Brian Mountains\nLake Laura, MH 29799',
    'text': 'Economy you every him degree. Hard late relate summer spend family. Sport those girl nation.\nConsumer yeah right debate. Mind city pattern concern. Make try threat join tonight behind.',
    'email': 'gonzalezmegan@example.net',
    'phone_number': '468.325.4069x175',
    'array_int_dynamic': [
    81920,
],
    'array_varchar_dynamic': [
    'Rachel Cannon',
    'Cynthia Lucas',
    'Nathaniel Vang',
],
    'json': {
    'name': 'Denise Lang',
    'address': '9592 Whitney Drive\nLake Devon, IA 42441',
},
    'key75392': 'value29290',
    'key14827': 'value14200',
    'key86845': 'value7246',
    'key71719': 'value56978',
    'key96032': 'value20412',
    'key1207': 'value85478',
    'key93174': 'value92172',
    'key10415': 'value44257',
    'key27827': 'value12490',
    'key25928': 'value96373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Tammy Crawford',
    'address': '67555 Sonya Cliffs\nLake Michaelport, TN 03369',
    'text': 'It task threat natural record start. To within individual week past among house. Room course on morning.\nWatch board role land plan. System news culture information.',
    'email': 'evansjeffrey@example.org',
    'phone_number': '(993)201-9394x7549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Pearson',
    'Ross Oliver',
    'Sarah Hoffman',
    'Martin Moon',
    'Leslie West',
    'Stacey Cox',
    'Roberto Dean',
    'Michael Perry',
],
    'json': {
    'name': 'Kristy Brooks',
    'address': '1710 Douglas Path\nLake Spencerside, DE 64436',
},
    'key1103': 'value56049',
    'key32786': 'value56465',
    'key8650': 'value1837',
    'key51705': 'value10298',
    'key14551': 'value2558',
    'key5938': 'value99157',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Julia Mitchell',
    'address': '9668 Samuel Haven Suite 631\nNorth Adambury, SC 27586',
    'text': 'Itself record decision race fly. Run effort become industry citizen. Past fast management capital value. Often practice economic off bit professor service.',
    'email': 'sawyersheila@example.org',
    'phone_number': '(412)224-4110x096',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Hernandez',
    'Melissa Thompson',
    'Robert Roman',
    'Renee Ortiz',
    'Teresa Green',
    'Nicole Peters',
    'Richard May',
    'Mr. Brandon Peterson',
    'Andrea Johnson',
    'Theresa Quinn',
],
    'json': {
    'name': 'Anthony Collier',
    'address': '2335 Gonzalez Gateway Suite 415\nWest Jenniferfort, MI 46871',
},
    'key28735': 'value89010',
    'key79555': 'value64853',
    'key84467': 'value34423',
    'key62607': 'value34425',
    'key20958': 'value87216',
    'key2082': 'value32730',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Kathleen Prince',
    'address': '3702 Crystal Hills Suite 113\nDeborahview, PA 07727',
    'text': 'True indeed choose enough generation door figure. Company television rate media.\nOnce his figure policy trip. Wear half nearly forget civil.',
    'email': 'aaron32@example.com',
    'phone_number': '(935)666-1210x95921',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Sanchez',
    'Jennifer Robinson',
    'Connie Miller',
    'Tyler Ballard',
    'Johnathan Clark',
    'Francis Ramirez',
    'David Miller',
    'Dominic Garcia',
],
    'json': {
    'name': 'Lee Carter',
    'address': '2406 Gregory Haven Suite 066\nDavidborough, NV 48032',
},
    'key99020': 'value40983',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Timothy Church',
    'address': '85750 Kerr Centers\nSouth Johnmouth, PW 40167',
    'text': 'Forward minute station kind. Tend career kind expect necessary. History well member kind idea.\nHear over pass baby. Scientist economy within institution green. War successful suddenly government.',
    'email': 'state@example.org',
    'phone_number': '579.702.1224x104',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Calderon',
    'Marissa Brown',
    'Ms. Patricia Simmons',
    'Veronica Campbell',
    'Ms. Dawn Welch',
    'Gary Johnson',
    'William Myers',
    'Matthew Neal',
],
    'json': {
    'name': 'Suzanne Mclaughlin',
    'address': '39319 Farley Mountains Suite 330\nEast Loriborough, DC 58572',
},
    'key82864': 'value38994',
    'key59221': 'value19666',
    'key99550': 'value42207',
    'key85105': 'value37511',
    'key47960': 'value47398',
    'key37030': 'value42730',
    'key73354': 'value94157',
    'key78295': 'value82135',
    'key41318': 'value86654',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'William Rogers',
    'address': '1559 Warren Mill Suite 953\nCynthiaview, IL 22416',
    'text': 'Authority simple page. Piece number positive suddenly.\nPartner tax hotel act smile us street ten. Paper program about audience. It world audience eight right great themselves station.',
    'email': 'cartertimothy@example.net',
    'phone_number': '483.841.2481x291',
    'array_int_dynamic': [
    96453,
],
    'array_varchar_dynamic': [
    'Dominique Brooks',
    'Sarah Morales',
    'Steven Mitchell',
    'Gregory Morris',
    'David Evans',
],
    'json': {
    'name': 'Mr. Jacob Gutierrez',
    'address': '78561 Campbell Shores\nLake Regina, CA 64018',
},
    'key62109': 'value66231',
    'key59936': 'value73608',
    'key99962': 'value28953',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Kristie Price',
    'address': '5768 Bell Turnpike Suite 449\nNew Tinaview, WI 03956',
    'text': 'Material quality move law. Congress skin sound he site understand.\nEvening many improve address anyone campaign drop. Debate lot medical peace professional street.',
    'email': 'kararosales@example.com',
    'phone_number': '001-766-512-1541x18581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Contreras',
    'Michael James',
    'Katherine Austin',
    'Sabrina Anderson',
    'Douglas Phelps',
    'Melanie Mclaughlin',
    'Charles Dean',
],
    'json': {
    'name': 'Katelyn Mays',
    'address': '5420 Vasquez Lodge\nNorth Karenfort, ND 28560',
},
    'key4287': 'value75078',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Sharon Davis',
    'address': '3912 Ford Street\nEast Emily, MD 90143',
    'text': 'Teacher light rate with. Yard leg always skill likely cause food. Ok star deal easy.\nMy enjoy tree reflect would loss show. Feeling break very.',
    'email': 'chanerika@example.net',
    'phone_number': '2196598034',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Torres',
    'Debra Mcdonald',
    'Benjamin Payne',
],
    'json': {
    'name': 'Tonya Mendez',
    'address': '08460 Thomas Manor Apt. 717\nNorth Melinda, NM 09267',
},
    'key83653': 'value75497',
    'key22803': 'value74803',
    'key68433': 'value70992',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Kristin Bowers',
    'address': '367 Andrew Roads Apt. 665\nLunahaven, AK 08768',
    'text': 'Hold group large production boy affect leader much. Reality surface two change piece put year.\nLawyer will seek hit change fight. Collection soldier against at there leg.',
    'email': 'jeffrey72@example.org',
    'phone_number': '(349)930-8173x12727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Wilson',
    'William Taylor',
    'Brad Peterson',
    'Brian Wilson',
    'Joseph Kim',
    'John Davis',
    'David Carpenter',
    'Charles Lawrence',
],
    'json': {
    'name': 'Kevin Stewart',
    'address': '149 Virginia Divide Apt. 294\nTriciashire, IL 42948',
},
    'key31705': 'value30563',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Timothy Phillips',
    'address': '4288 Olsen Centers Suite 550\nMercadofort, DE 06186',
    'text': 'At civil also pass maybe father person. Beyond true who camera. Wish pressure four each tend.',
    'email': 'yjohnson@example.com',
    'phone_number': '(376)298-9801',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Cook',
    'Jacob Davis',
    'Jacqueline Wright',
    'Lisa Scott',
    'William Larsen',
],
    'json': {
    'name': 'Joshua Peterson',
    'address': 'Unit 0083 Box 1543\nDPO AA 77049',
},
    'key64099': 'value91811',
    'key97607': 'value72753',
    'key85498': 'value7374',
    'key79488': 'value11285',
    'key87816': 'value65880',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Lisa Graves',
    'address': '970 Shah Run\nVillanuevaville, KS 03590',
    'text': 'Seat assume raise Mrs. Authority especially can. Phone special green fast stop.',
    'email': 'morenomichael@example.net',
    'phone_number': '001-915-340-5000',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Anne Miller',
    'Dalton Morgan',
    'Anna Brown DVM',
    'Jordan Rodriguez',
    'Robert Patterson',
    'Scott Marks',
],
    'json': {
    'name': 'Jesus Phelps',
    'address': '93809 Jeffery Club\nJacksonshire, OH 40839',
},
    'key48687': 'value21596',
    'key34532': 'value47958',
    'key27312': 'value98219',
    'key83865': 'value40183',
    'key93009': 'value61570',
    'key53830': 'value17657',
    'key47272': 'value98580',
    'key99243': 'value81319',
    'key85778': 'value24360',
    'key25866': 'value6500',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Julie Allen',
    'address': '12719 Ramsey Isle\nEast Scottshire, IA 11785',
    'text': 'Month pull design official. Sing support picture baby performance.\nThemselves present else senior spend back fall. Run relate read use someone use. Out provide let science. Hot home action.',
    'email': 'rochaisaac@example.com',
    'phone_number': '894-367-4755',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tanner Miller',
    'Kayla Hull',
    'Robert Garcia',
    'Kyle Key',
],
    'json': {
    'name': 'Steve Cross',
    'address': '02887 Lee Crescent Apt. 991\nEast Kellyville, WI 03123',
},
    'key13171': 'value17583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Katrina Stein',
    'address': '387 Crystal Ramp\nJonathanchester, MT 89937',
    'text': 'Gun rather together value religious. Figure follow design my small themselves sell.',
    'email': 'evansjennifer@example.org',
    'phone_number': '430-476-9842x67025',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Knight',
    'Matthew Spencer',
    'Michael Rodriguez',
    'Joseph Guerrero',
],
    'json': {
    'name': 'Alyssa Cook',
    'address': '80489 Moody Island Suite 513\nSouth Christopher, OH 29417',
},
    'key71826': 'value33964',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Mark West',
    'address': 'Unit 2008 Box 9272\nDPO AA 67516',
    'text': 'Successful month professional challenge draw somebody sound. View the analysis drive popular daughter.\nRemain picture especially through talk. Stock feeling natural allow.',
    'email': 'zcalderon@example.com',
    'phone_number': '5455229989',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Paul Jones',
    'Bobby Sanford',
    'Lucas Norman',
    'Lance Weber',
    'Madison Rodriguez',
    'Katherine Everett',
    'Dana Harris',
    'Christine Mason',
    'Jacob Mendez PhD',
],
    'json': {
    'name': 'Helen Cox',
    'address': '80329 Oliver Ports Apt. 806\nEast Susanshire, WY 50270',
},
    'key75243': 'value69317',
    'key51187': 'value30472',
    'key26149': 'value11967',
    'key56362': 'value65584',
    'key24653': 'value14419',
    'key63686': 'value28648',
    'key59224': 'value18634',
    'key56973': 'value7475',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Natalie Brown',
    'address': '534 Dennis Vista Apt. 188\nWardport, HI 92375',
    'text': 'Home rock form else piece course. Because task government read enter remain. Travel yeah institution you area international.',
    'email': 'kkline@example.org',
    'phone_number': '+1-423-344-1223x3138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Patton',
    'Eddie Munoz',
    'Diane Green',
    'Dawn Johnson',
    'Debra Velez',
    'Jill Anthony',
    'Wanda Baird',
],
    'json': {
    'name': 'Jaime Pena',
    'address': '376 Nichole Mount\nPachecofurt, VT 88028',
},
    'key86261': 'value22621',
    'key3307': 'value82147',
    'key28435': 'value63889',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Haley Cook',
    'address': '22208 Smith Prairie Suite 168\nSparksfurt, LA 51226',
    'text': 'Situation star spring. Join tree once condition budget. Your view spend wide.',
    'email': 'hodgeroy@example.com',
    'phone_number': '(260)247-7426',
    'array_int_dynamic': [
    56051,
],
    'array_varchar_dynamic': [
    'Cory Alexander',
    'Brandy Webb',
    'Jodi Hart',
    'Melanie Singleton',
    'Adam Osborn',
],
    'json': {
    'name': 'Matthew Davis',
    'address': '69196 Brown Station Apt. 743\nAshleyburgh, AZ 12626',
},
    'key21096': 'value8161',
    'key23425': 'value22297',
    'key78789': 'value3285',
    'key7624': 'value44263',
    'key64966': 'value10970',
    'key44408': 'value33800',
    'key55904': 'value46588',
    'key72950': 'value56232',
    'key46200': 'value17528',
    'key53698': 'value42028',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Charlene Phillips',
    'address': '890 Adams Roads Suite 736\nPort Richardside, VI 57113',
    'text': 'Your degree table choose guy draw call. Modern foot computer above candidate recent community. General discover film fall long enjoy him.',
    'email': 'elliottjorge@example.org',
    'phone_number': '001-562-426-7486x846',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Angela Smith',
    'Kristin Haynes',
],
    'json': {
    'name': 'Sarah Rodriguez',
    'address': '635 Laura Park Suite 114\nHinesmouth, MH 41390',
},
    'key79819': 'value54290',
    'key57186': 'value60354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Miguel Pittman',
    'address': '8898 Andres Hills Apt. 670\nPort Jamesland, AZ 10140',
    'text': 'Dog raise thing area every box. Woman recently general a.\nBuy speak career center general. Single begin pull television any. Kind let blood.',
    'email': 'paustin@example.com',
    'phone_number': '931.445.3176',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Roy Hart',
    'Steve Ramos',
],
    'json': {
    'name': 'Sean Bennett',
    'address': '622 Andrew Bypass\nSkinnerfurt, AR 33598',
},
    'key64647': 'value65465',
    'key33290': 'value84951',
    'key40077': 'value83881',
    'key67319': 'value53373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jamie Powell',
    'address': '00437 William Orchard\nWest Joy, MP 37173',
    'text': 'Ok quite bar last. Middle above various one finally friend check. Letter film successful certainly option return fear building. Group leader suddenly oil increase defense.\nEvery high fish.',
    'email': 'davisdarryl@example.net',
    'phone_number': '722-267-4859x223',
    'array_int_dynamic': [
    52589,
],
    'array_varchar_dynamic': [
    'Laura Henry',
    'Roger Rodriguez',
    'Virginia Thompson',
    'Thomas Nolan',
    'Bonnie Watson',
    'Chad Baker',
    'Tyler Perez',
    'Christopher Obrien',
    'Gary Rich',
],
    'json': {
    'name': 'Collin Thomas',
    'address': '3561 Dana River\nCarlosville, OR 42083',
},
    'key50759': 'value45702',
    'key98359': 'value22443',
    'key10131': 'value65564',
    'key40351': 'value7064',
    'key85230': 'value94691',
    'key45476': 'value47844',
    'key28445': 'value58786',
    'key79023': 'value46315',
    'key41269': 'value23807',
    'key69566': 'value32608',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Sheila Singh',
    'address': '9083 Yates Center Suite 375\nSmithfort, UT 78465',
    'text': 'Use these north option local focus.\nTechnology phone on offer move major. Increase scene sing.',
    'email': 'cassandraschmitt@example.com',
    'phone_number': '001-918-206-5265x8044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Todd Molina',
],
    'json': {
    'name': 'Adam Abbott',
    'address': '6436 Sheppard View Suite 327\nWolfehaven, SC 89079',
},
    'key90459': 'value34431',
    'key81580': 'value23650',
    'key41737': 'value69799',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Javier Rodriguez',
    'address': '683 Shannon Village Suite 557\nLarryville, ND 05067',
    'text': 'Six economic gun. By attorney bag role subject likely individual.\nSimple assume record. Education some see expect upon nothing stay.',
    'email': 'blakeclark@example.com',
    'phone_number': '001-557-468-3662x76670',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Ward',
    'Joseph Johnson',
    'Andrea White',
    'Kimberly Jones',
    'Austin Torres',
],
    'json': {
    'name': 'Christina Thomas',
    'address': '123 Samantha Loaf Apt. 212\nSouth Lisabury, MA 90116',
},
    'key57055': 'value62467',
    'key46958': 'value25867',
    'key10500': 'value67208',
    'key8769': 'value65203',
    'key96083': 'value37663',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Joshua Brock',
    'address': '59779 Mark Ford Apt. 035\nLake Brian, MD 94748',
    'text': 'Notice her also. Wide total south else voice.\nDetail million city thousand. Her make off poor start. Environment somebody mouth summer finish station.',
    'email': 'leah56@example.com',
    'phone_number': '273.274.1907',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Emily Jones',
    'Lori Manning',
],
    'json': {
    'name': 'Raymond Harding',
    'address': '10369 Rhonda Mountains Suite 813\nNew Calvin, SD 81764',
},
    'key70878': 'value54351',
    'key87682': 'value61079',
    'key14320': 'value84709',
    'key73867': 'value75942',
    'key41464': 'value13968',
    'key77871': 'value21377',
    'key55041': 'value77136',
    'key83152': 'value49828',
    'key66709': 'value45939',
    'key48775': 'value56675',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Cassidy Miller',
    'address': '67945 Katrina Burgs Apt. 615\nLake Brittany, HI 99059',
    'text': 'Some lot street statement. Before yeah team ground where director. Nation issue science common center heavy. Rise few physical speak hundred.',
    'email': 'edwinwells@example.org',
    'phone_number': '214-412-1113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ellen Horne',
    'Tracy Russo',
    'Ann Brown',
    'Xavier Yang',
    'Dr. Lisa Morgan',
    'Randy Bryant',
    'Monica Mendez',
    'Victor Lucas',
    'Eric Cox',
],
    'json': {
    'name': 'Brian Osborne',
    'address': 'Unit 1061 Box 3091\nDPO AA 66906',
},
    'key11829': 'value92235',
    'key33068': 'value53462',
    'key92775': 'value90442',
    'key95931': 'value39858',
    'key37146': 'value8755',
    'key41295': 'value91635',
    'key4074': 'value55755',
    'key83573': 'value26532',
    'key8076': 'value93201',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Kaitlyn Davidson',
    'address': '174 James Bridge\nNorth Jenniferchester, SD 49786',
    'text': 'Long official significant remain. Produce various large truth build. My customer study protect off perhaps. Sing arrive more feeling these product.',
    'email': 'xwallace@example.org',
    'phone_number': '001-263-785-4992',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Steve Lewis',
    'Ashley Johnson',
    'Jennifer Rowland',
    'John Moran',
    'Robert Myers',
],
    'json': {
    'name': 'Diane Thomas',
    'address': '395 Ronald Village Suite 180\nPort Sarah, RI 11528',
},
    'key3513': 'value92319',
    'key45945': 'value46275',
    'key8488': 'value51301',
    'key93548': 'value98822',
    'key35788': 'value52165',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jeffery Bryan',
    'address': '6501 Brandt Road\nNew Markstad, RI 89772',
    'text': 'Bank especially question find. Money away reduce tend each catch.\nClose only commercial daughter activity child home much. Whatever reach hit test relationship always side.',
    'email': 'ustevens@example.org',
    'phone_number': '001-435-759-0492',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Howard',
    'Mike Huber',
    'Carolyn Hendricks',
    'Allison Hunt',
],
    'json': {
    'name': 'Cody Ford',
    'address': '3870 Hughes Locks Suite 432\nFowlershire, CT 93350',
},
    'key25532': 'value56014',
    'key58306': 'value31330',
    'key81451': 'value44166',
    'key14125': 'value42471',
    'key1364': 'value51377',
    'key26499': 'value13591',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Veronica Moore',
    'address': '354 Robinson Canyon Suite 408\nWest Lorimouth, VA 62603',
    'text': 'Somebody agent marriage interesting now still. Whose reach realize. And reality unit possible music. Wall whole beautiful central person.',
    'email': 'jennifer47@example.com',
    'phone_number': '6129953366',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Travis Miller',
    'Jade Espinoza',
],
    'json': {
    'name': 'Phillip Turner',
    'address': '5770 Pamela Parkway Apt. 665\nLake Ryan, WY 43777',
},
    'key9186': 'value94531',
    'key48897': 'value79536',
    'key30275': 'value36308',
    'key49114': 'value26206',
    'key40964': 'value23652',
    'key50903': 'value15718',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kimberly Obrien',
    'address': '68686 Powell Prairie\nWeisston, MO 19114',
    'text': 'Recognize all movement real rate. Run else whom start. Company door yes send long.\nMessage operation white mention difficult these. Begin head late for industry somebody.',
    'email': 'jason37@example.org',
    'phone_number': '001-285-923-8475',
    'array_int_dynamic': [
    77069,
],
    'array_varchar_dynamic': [
    'David Fernandez',
    'Kimberly Bradley',
    'Joseph Wallace',
    'Christina Campbell',
    'Justin Mason',
    'Wayne Finley',
    'Donald Williams',
    'Mark Sandoval',
    'Jack Walker',
    'Alexandria Huber',
],
    'json': {
    'name': 'Katherine Garrett',
    'address': '47344 Russell Gardens\nRobertmouth, PR 60720',
},
    'key30790': 'value6909',
    'key30626': 'value63799',
    'key10776': 'value54336',
    'key6526': 'value32349',
    'key92837': 'value28384',
    'key55963': 'value56370',
    'key18472': 'value55789',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Kimberly Reyes',
    'address': '135 Jeffrey Overpass\nNorth Darrenmouth, AS 01219',
    'text': 'Difficult rate culture social I.\nColor economic commercial share dog. News owner term politics approach discuss.',
    'email': 'whitetiffany@example.org',
    'phone_number': '(359)469-4573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Norman',
    'Jennifer Meza',
],
    'json': {
    'name': 'Dawn Williams',
    'address': '99466 Wayne Mission\nLake Anthony, LA 40902',
},
    'key59318': 'value40190',
    'key47578': 'value73925',
    'key9753': 'value50771',
    'key53420': 'value32727',
    'key81894': 'value90803',
    'key45315': 'value40337',
    'key87967': 'value42382',
    'key48484': 'value81751',
    'key98729': 'value5320',
    'key68703': 'value88391',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Angelica Valdez',
    'address': '0663 Erik Lane\nMorrisport, FL 09026',
    'text': 'Bit however behind blood consumer employee that. Arm thing before true science. Realize nice gas carry.',
    'email': 'biancaperez@example.com',
    'phone_number': '001-330-996-8316x0881',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Monique Aguirre',
    'Craig Martinez',
    'Randall Mitchell',
    'Mary Crawford',
    'Margaret Cooper',
    'Rebecca Kim',
    'Kimberly Johnson',
],
    'json': {
    'name': 'Gregory Haney',
    'address': '9921 Anthony Flats Suite 130\nWest Mary, MA 10079',
},
    'key55240': 'value5837',
    'key17745': 'value73559',
    'key33922': 'value44411',
    'key73139': 'value89001',
    'key43209': 'value32916',
    'key50732': 'value73479',
    'key88160': 'value12482',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Amy Stout',
    'address': '064 Brown Neck\nNew Glennburgh, NJ 42534',
    'text': 'Person family instead machine student voice parent. Never could buy every. Be five security doctor situation outside.',
    'email': 'kellihoover@example.org',
    'phone_number': '+1-504-969-1151x210',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Beth Lowery',
    'Alicia Vargas',
    'Samantha Jackson',
    'Allison Keller',
    'April Sutton',
    'Alexis Boyd',
    'Kathleen Ewing',
    'Dustin Simon',
    'Lauren Nguyen',
],
    'json': {
    'name': 'Kendra Thomas',
    'address': '682 Julie Center\nKennethton, WA 37398',
},
    'key85029': 'value7641',
    'key86344': 'value47389',
    'key37169': 'value11406',
    'key25902': 'value26009',
    'key56290': 'value11323',
    'key99157': 'value78579',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Daniel Phillips',
    'address': 'USNV Coleman\nFPO AE 28422',
    'text': 'Indicate until late sport end research will thus.\nProve want consumer majority perform boy. Traditional voice Democrat. Measure already outside husband certain house.',
    'email': 'johnnygarcia@example.net',
    'phone_number': '338-652-7907',
    'array_int_dynamic': [
    58153,
],
    'array_varchar_dynamic': [
    'Steven Walsh',
    'Kerri Randolph',
    'Nancy Kelly',
    'Ashley Wilson',
    'Jaime Fox',
    'Amy Montoya',
    'Richard Thompson',
    'Kristen Thomas',
    'Alicia Lewis',
],
    'json': {
    'name': 'Lori Vega',
    'address': '17287 Wilson Shoals\nEast Courtneyborough, NY 54784',
},
    'key16003': 'value83363',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Matthew Marshall',
    'address': '7581 Jason Corner Suite 502\nEast Angela, MO 23700',
    'text': 'West method history foot read vote store.\nHistory realize break TV which list. Item find get thank tax doctor century again. Enjoy prove top marriage. Nice commercial main think rate also speak.',
    'email': 'afigueroa@example.net',
    'phone_number': '878.545.6949x003',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angel Patton',
],
    'json': {
    'name': 'John Pham',
    'address': '6182 Buckley Groves Apt. 297\nCharlenestad, NM 54469',
},
    'key86625': 'value92185',
    'key7593': 'value23392',
    'key993': 'value21635',
    'key4767': 'value65414',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'David Scott',
    'address': 'PSC 7911, Box 1259\nAPO AE 63662',
    'text': 'Partner occur evening include cup arrive. Position out drop notice establish old child. Street happen military dog. Sport life tend.',
    'email': 'jeffreyjackson@example.com',
    'phone_number': '345.269.0409',
    'array_int_dynamic': [
    64712,
],
    'array_varchar_dynamic': [
    'Mitchell White',
    'Brittany Walker',
    'Curtis Gilmore',
],
    'json': {
    'name': 'Patricia Estrada',
    'address': 'USS Miller\nFPO AP 89228',
},
    'key18685': 'value26704',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Logan Hardin',
    'address': '019 Villegas Islands Suite 819\nRobertview, MH 90491',
    'text': 'Maintain policy front after population top work. Across store support such. Shake gas answer service risk.',
    'email': 'salazaranthony@example.com',
    'phone_number': '001-803-465-5584x7747',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Collier',
    'Mary Arroyo',
    'Joshua Vincent',
    'Michelle Marks',
    'Mitchell Alvarez',
    'Shawn Wilkinson',
],
    'json': {
    'name': 'Mr. Justin Brown',
    'address': '607 Lopez Burgs\nSouth James, SC 19531',
},
    'key15820': 'value55976',
    'key79453': 'value96281',
    'key49145': 'value77189',
    'key33974': 'value94682',
    'key49645': 'value36062',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Crystal Holmes',
    'address': '7230 Eugene Spring Suite 121\nPort Nicole, CO 74950',
    'text': 'Leader impact feeling always culture. It court country group party. Quality wonder soon source job apply take. Where shoulder sort mention special.',
    'email': 'williamsontara@example.com',
    'phone_number': '+1-446-783-2621x9340',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Dodson',
    'David Smith',
    'Matthew Dean',
    'Kimberly Williams',
    'Sarah Murphy',
    'Jeremiah Allen',
    'Tanya Hays',
],
    'json': {
    'name': 'Derek Reid',
    'address': '6113 Harris Courts Apt. 706\nKeithchester, DC 82328',
},
    'key99289': 'value11032',
    'key71081': 'value8766',
    'key20889': 'value9711',
    'key82916': 'value15334',
    'key96079': 'value17288',
    'key21231': 'value39923',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'David Flores',
    'address': '8154 Hoover Streets Suite 514\nKevinton, DC 60410',
    'text': 'Community in international. Democratic least send law meeting view.\nRelationship represent two hope. American between network and behavior law likely. Expect offer strong Democrat experience.',
    'email': 'danielleharrell@example.net',
    'phone_number': '001-497-332-7513x884',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Wong',
    'Alejandro Davis',
    'Whitney Morgan',
    'Michelle Ryan',
    'Anthony Martin',
    'Debbie Zimmerman',
    'Franklin Rhodes',
    'Joseph Clarke',
    'Steven Lewis',
],
    'json': {
    'name': 'Latasha Martin',
    'address': '025 Thomas Gardens\nManninghaven, VT 42432',
},
    'key55563': 'value17453',
    'key33463': 'value63024',
    'key80119': 'value93183',
    'key8151': 'value62629',
    'key89412': 'value71465',
    'key23515': 'value35542',
    'key25276': 'value40910',
    'key70005': 'value60295',
    'key71871': 'value80062',
    'key66834': 'value56717',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Clayton Hines',
    'address': '1865 Richard Plaza Suite 558\nNorth Brittanyborough, ID 66168',
    'text': 'Five financial because. Single professional us.\nInternational computer much meet. Edge street sing leave box give standard late.\nTake how structure deep tax first. Ten receive go.',
    'email': 'julie24@example.com',
    'phone_number': '(716)287-8683x81079',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Thomas',
],
    'json': {
    'name': 'Veronica Thomas',
    'address': '67717 Pena Squares\nMariaberg, MP 25686',
},
    'key61111': 'value91924',
    'key47740': 'value91416',
    'key10738': 'value89002',
    'key21034': 'value80288',
    'key43432': 'value25462',
    'key335': 'value18663',
    'key25517': 'value51539',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Melissa Fischer',
    'address': '19921 Williams Hills\nHeatherland, WI 55836',
    'text': 'Ok town road support enough thought.\nThreat foot meeting card. Seek someone focus chance from song trial when. But night standard degree soon respond woman. Them for late language technology second.',
    'email': 'griffinpatricia@example.net',
    'phone_number': '001-745-845-2102x787',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Hall',
    'Tina Buckley',
    'Brandon Garcia',
    'Sylvia Lopez',
    'Brittany Warner',
    'Joseph Rodriguez',
    'Kenneth Pena',
    'Jamie Moore',
    'Joanna Kennedy',
    'James Gonzalez',
],
    'json': {
    'name': 'Jesse Stephens',
    'address': '599 Pacheco Lodge\nAnitamouth, KY 72167',
},
    'key95783': 'value28200',
    'key28790': 'value57435',
    'key71395': 'value40957',
    'key51901': 'value68751',
    'key3278': 'value74293',
    'key85454': 'value96880',
    'key14163': 'value8273',
    'key15263': 'value55535',
    'key98404': 'value5598',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Kristi Grant',
    'address': '4424 Bryan Via\nLake Samantha, HI 52985',
    'text': 'Around no war head international candidate. Behind also knowledge pressure discover could international. Own hundred white degree dog. Detail reality service.',
    'email': 'bateslisa@example.org',
    'phone_number': '+1-955-291-5120',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Eric Summers',
    'Jeffrey Ferguson',
    'Robert Parsons',
    'Sean Vargas',
    'Jeffery Todd',
],
    'json': {
    'name': 'Angela Smith',
    'address': '78438 Valdez Fords Suite 024\nEmmastad, SD 65189',
},
    'key36807': 'value94503',
    'key14287': 'value49302',
    'key89891': 'value1780',
    'key74971': 'value35079',
    'key51871': 'value38136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Stephanie Simmons',
    'address': '570 Jose Highway\nJillianborough, MI 55766',
    'text': 'History with rock have member room. Outside thing why population less street war.\nFeel boy unit strong. Land fast discuss detail. Few state few raise himself.',
    'email': 'ronaldblair@example.com',
    'phone_number': '+1-894-620-8799x44230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christina Goodwin',
    'Mary Tate',
    'Cindy Robinson',
    'Debra Williams',
    'Edward Mendez',
    'Danielle Clay',
    'Isabel Hansen',
],
    'json': {
    'name': 'Doris Perkins',
    'address': '426 Perry Vista Apt. 031\nKevinberg, MS 57105',
},
    'key24689': 'value98291',
    'key5594': 'value97302',
    'key36759': 'value75188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jennifer Rodriguez',
    'address': '52571 Robert Forks Apt. 613\nWest Jonathan, DE 06033',
    'text': 'Box may crime tonight more step major.\nEverybody remain movie common. North describe day next.\nCould environmental single direction. Owner several style east.',
    'email': 'malikking@example.net',
    'phone_number': '(329)387-9144',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kim Kelly',
    'Patricia Sherman',
    'Lisa Ryan',
],
    'json': {
    'name': 'Willie Pierce',
    'address': '3919 Shelley Overpass\nPort Chad, AR 06120',
},
    'key20802': 'value39627',
    'key43755': 'value41295',
    'key31959': 'value97426',
    'key35': 'value61974',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jane Daniel',
    'address': '04660 Matthew Terrace\nDrakeshire, NC 15789',
    'text': 'Industry air another suffer level win without. Pick water base cover television. Fine significant history address laugh stuff.',
    'email': 'cfarrell@example.com',
    'phone_number': '217-202-6746',
    'array_int_dynamic': [
    86681,
],
    'array_varchar_dynamic': [
    'Marcus Osborn',
    'Sydney Henderson',
    'Margaret Braun',
    'Jessica Oneal',
    'Cory Sloan',
    'Kristin Gutierrez',
    'Rebecca Stephens',
    'Samuel Mckinney',
],
    'json': {
    'name': 'Amanda Holt',
    'address': '56887 Alexis Crescent\nGibsonville, ME 37710',
},
    'key67564': 'value45475',
    'key33043': 'value51807',
    'key80178': 'value42317',
    'key78152': 'value46987',
    'key18825': 'value65522',
    'key7837': 'value9837',
    'key51023': 'value33325',
    'key53503': 'value12394',
    'key96093': 'value94504',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Martha Miles',
    'address': '6863 Mary Trail\nSouth Collin, DE 72962',
    'text': 'Day inside debate within. Charge carry easy head series hear soon put. Instead ok oil may including manager.',
    'email': 'gsmith@example.org',
    'phone_number': '(338)699-6525x0199',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Duffy MD',
    'Dylan Bowen',
    'Barbara Choi',
    'Mary Flores',
    'Alyssa Norman',
    'Rachel Anthony',
    'Kyle Hayes',
    'Peter Lewis',
    'Francis Hull',
],
    'json': {
    'name': 'Lisa Burch',
    'address': '06390 Chen Green\nStephensontown, NM 01110',
},
    'key26915': 'value77947',
    'key36810': 'value50546',
    'key69050': 'value72820',
    'key66727': 'value57818',
    'key6395': 'value16695',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Shawn Ramirez',
    'address': '6052 William Vista\nNorth Ericbury, MN 55710',
    'text': 'Fast strategy ever card. Because your fall.\nFish conference teacher and foot something often occur. Plan outside food receive your less four. Eight certain early case soldier.',
    'email': 'stephaniemiller@example.org',
    'phone_number': '445-533-6098x276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Taylor',
    'Melinda Cruz',
    'John Solis',
    'Timothy Ramirez',
    'Heather Murphy',
    'Shannon Allen',
    'Matthew Newman',
    'Andrew Gomez',
    'Amber Dean',
],
    'json': {
    'name': 'Dorothy Chapman',
    'address': '91601 Diana Road Suite 749\nMillerport, MI 53694',
},
    'key33459': 'value92688',
    'key85421': 'value45559',
    'key52337': 'value69107',
    'key33400': 'value87733',
    'key90463': 'value67365',
    'key52780': 'value51375',
    'key49629': 'value13413',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Connor Cameron',
    'address': '77304 Michelle Village Suite 883\nPort Samuelmouth, IA 28593',
    'text': 'Leader lose him experience president. Next staff sort best around.',
    'email': 'cameronjulia@example.org',
    'phone_number': '001-479-878-4918',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Wanda Cruz',
    'Jacob Henderson',
    'Jane Sanchez',
    'Damon King PhD',
    'Jason Alexander',
],
    'json': {
    'name': 'Amanda Nelson',
    'address': '0582 Jones Drives Suite 981\nSouth Robertmouth, OR 67932',
},
    'key37158': 'value73619',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Zachary Vazquez',
    'address': '88200 Elizabeth Viaduct\nHuntside, NJ 46768',
    'text': 'Argue necessary accept development we kid. Catch hand know baby nor especially simply. Audience put resource firm picture choice half.',
    'email': 'andreawatson@example.org',
    'phone_number': '590.551.1395',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Pittman',
],
    'json': {
    'name': 'Henry Smith',
    'address': 'Unit 6729 Box 0888\nDPO AP 30015',
},
    'key57397': 'value35454',
    'key7015': 'value20805',
    'key39455': 'value21248',
    'key42902': 'value84156',
    'key45855': 'value76741',
    'key29270': 'value17374',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Dr. Matthew Garcia MD',
    'address': '23916 David Wells\nDoughertyton, MN 31722',
    'text': 'Knowledge writer ever door wear plant must. History nation hot animal again example put say. Here race help commercial garden before modern.',
    'email': 'zhayes@example.com',
    'phone_number': '5702905067',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Emily Reyes',
    'Leslie Smith',
],
    'json': {
    'name': 'Hannah Ross',
    'address': '291 Philip Stravenue Apt. 054\nJustinbury, GU 61857',
},
    'key75365': 'value28813',
    'key75789': 'value59375',
    'key77612': 'value8089',
    'key3185': 'value34708',
    'key11266': 'value7367',
    'key13056': 'value86102',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Natalie Carter',
    'address': 'PSC 2596, Box 2354\nAPO AA 33602',
    'text': 'Consumer take professor look. Everyone base owner drug account.\nFill mean sound way draw accept. Artist affect read service. Player owner the any writer.',
    'email': 'baileyfelicia@example.com',
    'phone_number': '942.320.7759',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Moon',
    'Tammy Elliott',
    'Casey Moran',
    'Aaron Wood',
    'Darryl Houston',
    'Robert Thompson',
    'Charles Collins',
    'David Owens',
],
    'json': {
    'name': 'Maria Phelps',
    'address': '2394 Katherine Knolls\nEast Joanna, CA 96306',
},
    'key76810': 'value45939',
    'key80156': 'value84117',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Tiffany Stone',
    'address': '38181 Riley Locks Apt. 160\nLozanobury, PW 28904',
    'text': 'Challenge could main. Senior provide example card. Bed consider consumer.\nEnter ten explain others. Range gun hospital. Everyone recently even store later.',
    'email': 'acaldwell@example.net',
    'phone_number': '(461)623-1109',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Shelby Fischer',
],
    'json': {
    'name': 'Jeremy Garrett',
    'address': '34635 Michael Lodge\nCharlesport, MA 29014',
},
    'key29873': 'value39734',
    'key51865': 'value1824',
    'key72492': 'value92035',
    'key34382': 'value39615',
    'key64395': 'value60201',
    'key30835': 'value71239',
    'key39648': 'value64583',
    'key52198': 'value66811',
    'key8896': 'value17442',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jason Rush',
    'address': '34639 Richards Stream Suite 582\nPort Aaronchester, OH 88563',
    'text': 'Professor himself the. Yeah quickly budget.\nArrive story whole guess eat to. Situation scientist few appear wish.\nConference recognize majority industry. Claim dinner itself ready.',
    'email': 'jennifer75@example.com',
    'phone_number': '2846437079',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Jackson',
    'Caleb Santana',
    'Kathleen Bernard',
    'Jonathan Rhodes',
    'Kevin Smith',
    'Jennifer Nguyen',
    'Dustin Barton',
    'Karen Walker',
],
    'json': {
    'name': 'Katrina Douglas',
    'address': '35878 Palmer Loop Apt. 521\nNew Emily, AK 58804',
},
    'key86895': 'value28829',
    'key64174': 'value21631',
    'key96911': 'value6892',
    'key31286': 'value39217',
    'key83970': 'value50811',
    'key15991': 'value38800',
    'key90519': 'value11426',
    'key17094': 'value64956',
    'key64336': 'value69864',
    'key16971': 'value85337',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Michael Wyatt',
    'address': '1198 Kimberly Glen\nBartonshire, IN 16195',
    'text': 'Close ten despite report series set. Democrat year cultural music south data beat. Nation right election ground school tonight structure.',
    'email': 'hmartinez@example.net',
    'phone_number': '207-951-6688',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Johnston',
    'Susan Reyes',
    'Robert Ford',
    'Andre Cline',
],
    'json': {
    'name': 'John Coleman',
    'address': '104 Alexander Garden\nKimberlyview, FM 08474',
},
    'key53196': 'value44101',
    'key57698': 'value76333',
    'key3600': 'value11652',
    'key59486': 'value60207',
    'key67713': 'value98361',
    'key26780': 'value9741',
    'key21476': 'value76712',
    'key55723': 'value55252',
    'key61265': 'value92162',
    'key68064': 'value6682',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Troy Gilbert',
    'address': '97394 Sheri Shoals Suite 523\nNew Lori, VA 32653',
    'text': 'Street middle oil book contain attention. Southern so beautiful why. Clearly bar medical ability quickly personal. Data identify free new full.',
    'email': 'caitlin57@example.net',
    'phone_number': '(459)207-2847',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Pratt',
    'William Martinez',
    'Mitchell Perez',
    'Daniel Adams',
    'Cory Rodriguez',
    'Wesley Thomas',
    'Vincent Dean Jr.',
    'James Joyce',
    'Lawrence Cameron',
    'Sean Rubio',
],
    'json': {
    'name': 'Kimberly Mcdonald',
    'address': 'Unit 0130 Box 5954\nDPO AE 33332',
},
    'key70392': 'value63581',
    'key70712': 'value83514',
    'key51758': 'value60462',
    'key68144': 'value74270',
    'key95017': 'value65143',
    'key41894': 'value95366',
    'key16035': 'value8969',
    'key16982': 'value27867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Terry Shaw',
    'address': '78571 Miller Courts\nNew Nicholasberg, WV 13546',
    'text': 'Produce newspaper feeling wait assume close activity than. Bill cover Republican position share career. Break others end phone worry most. Rest cold oil learn recent continue best.',
    'email': 'olsonallen@example.net',
    'phone_number': '243.622.5501x2295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Justin White',
    'Mark Luna',
    'John Snyder',
    'Grace Anderson',
    'Matthew Huffman',
    'Joseph Chavez',
    'Amanda Rodriguez',
    'Michael Morris',
],
    'json': {
    'name': 'Ariana Neal',
    'address': '71789 Catherine Greens Suite 580\nSouth Daniellemouth, ND 78368',
},
    'key28016': 'value28774',
    'key39555': 'value66551',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Denise Lee',
    'address': 'Unit 9233 Box 0997\nDPO AE 60689',
    'text': 'Listen military north these by mind fear bit. Activity space democratic position however hundred newspaper. Color father scientist. West not table.',
    'email': 'gabrielsmith@example.com',
    'phone_number': '(683)459-3238x45807',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Lee',
    'Jerry Mccann',
    'Melissa Johnson',
    'Pamela Landry',
    'Theresa Carpenter',
    'Darryl Lloyd',
    'Laura White',
    'Vanessa Ellis',
    'Jasmine White',
],
    'json': {
    'name': 'Brandon Nunez',
    'address': '5830 Washington Parks\nEast Adrianville, NV 85174',
},
    'key40292': 'value48834',
    'key35894': 'value17345',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jason Ferguson',
    'address': 'USCGC White\nFPO AP 82671',
    'text': 'Else goal same successful share final. Office ground range always fish set. Beat person day door week.\nJust picture remain listen artist woman. Rate stage throughout common decision.',
    'email': 'jacob66@example.net',
    'phone_number': '2893690825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Oliver',
    'William George',
    'Joseph Atkinson',
    'Susan Johnson',
    'Ashley Jordan',
    'Vickie Ray',
],
    'json': {
    'name': 'Sara Lowe',
    'address': '1379 Carla Springs\nNew Angela, NV 24114',
},
    'key85915': 'value16573',
    'key91820': 'value88516',
    'key35790': 'value46318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'John Bailey',
    'address': '265 Amanda Square\nWest Richard, KY 74555',
    'text': 'Check word financial goal. Quickly left foot campaign specific beyond.\nGeneration together find range together art.',
    'email': 'zhernandez@example.com',
    'phone_number': '+1-219-309-6199x267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Carrie Riley',
],
    'json': {
    'name': 'Jennifer Huffman',
    'address': 'PSC 5123, Box 9309\nAPO AE 59122',
},
    'key17154': 'value53446',
    'key98685': 'value76201',
    'key45170': 'value95496',
    'key5232': 'value8118',
    'key92157': 'value51238',
    'key43095': 'value64165',
    'key38430': 'value7765',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Elizabeth Hill',
    'address': '4870 Jessica Gateway\nNew David, WY 19000',
    'text': 'Hit reduce finish next to at. Son his student work spring father institution. American enter care red.\nFire world develop key. Bank can western mean.',
    'email': 'jon04@example.org',
    'phone_number': '(444)324-2605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Glenn',
    'Miss Sarah Guzman',
    'Thomas Gray',
    'Lisa Jacobs',
],
    'json': {
    'name': 'Charles Hunt',
    'address': '6954 Mckinney Station Apt. 981\nThompsonbury, CT 88277',
},
    'key40205': 'value40503',
    'key65113': 'value73064',
    'key79685': 'value2488',
    'key65421': 'value45074',
    'key51541': 'value60919',
    'key57513': 'value54006',
    'key43581': 'value82787',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Sean Wilson',
    'address': '34527 Amy Manor Apt. 007\nNorth Jeffrey, VA 68325',
    'text': 'Follow program job even to successful. Pretty market admit try product hit.\nOnly dinner husband there. State themselves fact week.\nPeople attack possible year agent relationship model market.',
    'email': 'jacobhobbs@example.com',
    'phone_number': '(902)438-4956',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gary Leonard',
    'Valerie Green',
    'Matthew Williams',
],
    'json': {
    'name': 'Joseph White',
    'address': '850 Karen Parkway Suite 771\nEricside, NM 95492',
},
    'key77358': 'value45155',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Gail Carter',
    'address': '951 James Squares Suite 927\nPort Tyler, WV 16458',
    'text': 'Mouth author campaign evidence. Many moment tell consider get become. President develop good about from. Cost station partner we hot design forget type.\nSort light tonight.',
    'email': 'henrylaura@example.org',
    'phone_number': '001-666-254-6178x5764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Barnes',
    'Sara Ramsey',
    'Timothy Torres',
],
    'json': {
    'name': 'Stanley Bell',
    'address': 'PSC 2870, Box 7222\nAPO AP 56794',
},
    'key56707': 'value37365',
    'key71124': 'value96369',
    'key43670': 'value13503',
    'key24187': 'value22128',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Paul Oconnell',
    'address': 'PSC 8234, Box 1448\nAPO AP 87698',
    'text': 'Early man cell avoid.\nFace act adult pick talk. Trip today case series check.\nBetter everybody compare tree as theory.',
    'email': 'bsmith@example.org',
    'phone_number': '793-552-0223x191',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Carl Salazar',
    'Catherine Aguilar',
    'Christopher Burgess',
    'Bethany Moss',
],
    'json': {
    'name': 'Robert Horton',
    'address': '5273 Montoya Valley\nEast Melissa, KS 42429',
},
    'key5326': 'value64059',
    'key50215': 'value30658',
    'key5718': 'value7737',
    'key64376': 'value87025',
    'key76352': 'value55146',
    'key89326': 'value11898',
    'key89569': 'value69250',
    'key48782': 'value33815',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Ana Delgado',
    'address': '1656 Garcia Creek\nRaymondmouth, MO 12179',
    'text': 'Less reach employee often add central story. Green live report trouble. Media agreement none not nation.\nMost consider to go stock play.',
    'email': 'christinemartin@example.com',
    'phone_number': '3325931784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marisa Alexander',
    'Erika Dixon',
    'Caroline Rosario',
    'Matthew Powers',
    'Andrea Cooper',
    'Breanna Patton',
    'Mckenzie Baldwin',
    'Mrs. Miranda Hansen',
    'Steve Wright',
],
    'json': {
    'name': 'Tiffany Hull',
    'address': '85531 Thomas Extensions Apt. 187\nFrankstad, CA 29743',
},
    'key6760': 'value17020',
    'key97307': 'value6104',
    'key83118': 'value66160',
    'key2266': 'value52817',
    'key81378': 'value11673',
    'key67068': 'value29037',
    'key36308': 'value22602',
    'key98959': 'value2637',
    'key78340': 'value407',
    'key41376': 'value94728',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Victor Ramirez',
    'address': '341 Henry Forge Suite 930\nWayneburgh, SC 66591',
    'text': 'Now level many key. Behind really amount life approach picture manage statement. All itself whether whether.\nVisit safe if police. Mother blue hit down avoid way politics assume.',
    'email': 'rubiomichael@example.org',
    'phone_number': '+1-727-559-4352x53461',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Suzanne Hall',
    'Joseph Wheeler',
    'Jesus Walker',
    'Mark Cruz',
    'Samantha Mejia',
    'Tanya Nash',
    'Misty Hill',
    'Michelle Blackwell',
    'Richard Nichols',
    'Claudia King',
],
    'json': {
    'name': 'Lisa Robinson',
    'address': '485 Jenkins Center Apt. 192\nWest Jacobfort, WY 13733',
},
    'key54988': 'value35951',
    'key10468': 'value73550',
    'key14814': 'value32813',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Kathleen Thomas PhD',
    'address': '666 Laurie Mall Suite 422\nLake Bobbystad, TX 45346',
    'text': 'With happen culture test. Stay table hit able say. Place she camera majority join choose national change.',
    'email': 'waltontracy@example.com',
    'phone_number': '939.674.8189x195',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Collins',
    'Michael Anderson',
],
    'json': {
    'name': 'Robert Evans',
    'address': '89039 Tristan Landing\nLake Lindsey, VI 79856',
},
    'key74156': 'value58188',
    'key88307': 'value39711',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Tanya Harper',
    'address': '513 Derek Dale Suite 172\nBryantborough, GU 72951',
    'text': 'Help sell science design instead outside. Might spring describe hope over.\nOccur treatment night head buy. Issue consider especially body group my tree.',
    'email': 'helen40@example.com',
    'phone_number': '537-642-8654x477',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Donald Pierce',
    'Ashley Watkins',
    'Taylor Coleman',
    'Douglas Norton II',
    'Kathryn Valencia',
],
    'json': {
    'name': 'Leslie Hall DDS',
    'address': '711 Powers Roads Suite 452\nEast Roger, PR 78534',
},
    'key15110': 'value67704',
    'key46083': 'value23331',
    'key75293': 'value31158',
    'key65567': 'value35526',
    'key2872': 'value68736',
    'key48517': 'value87675',
    'key50002': 'value85762',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Joseph Roberts',
    'address': '9079 Gutierrez Ville Apt. 121\nSouth Matthewmouth, OK 01493',
    'text': 'Team economy collection education receive team administration. Available left now born result employee education.\nActivity by recent pass. Hard compare million protect.',
    'email': 'sparker@example.com',
    'phone_number': '001-979-548-4243x8343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laurie Kelley',
    'Holly Gonzales',
    'Christopher Bradley',
    'Mario Newman',
    'Timothy Clark',
    'Jeffrey Holmes',
    'Regina Solomon',
],
    'json': {
    'name': 'Bonnie Bell DDS',
    'address': '527 Rodriguez Squares Apt. 497\nSmithtown, MD 58362',
},
    'key31864': 'value46716',
    'key13357': 'value28748',
    'key40833': 'value70798',
    'key18648': 'value38427',
    'key51934': 'value58000',
    'key21896': 'value55702',
    'key95412': 'value97351',
    'key11047': 'value62592',
    'key47502': 'value1995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Mark Mayo',
    'address': '546 Hill Valley\nNorth Kennethfurt, AL 11636',
    'text': 'Community education sport attack her dream opportunity citizen. Perform stuff glass process avoid.',
    'email': 'jacobspatricia@example.net',
    'phone_number': '345.969.0751x8978',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amy Vasquez',
    'Molly Foster',
    'Karen Nelson',
],
    'json': {
    'name': 'Sara Figueroa',
    'address': '719 Fowler Tunnel\nNew Alexachester, UT 50576',
},
    'key26303': 'value79557',
    'key20491': 'value93543',
    'key12282': 'value66489',
    'key15089': 'value68150',
    'key38552': 'value89969',
    'key39714': 'value97549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Bianca Vega',
    'address': 'USCGC Figueroa\nFPO AA 23584',
    'text': 'Right once speak wall which specific president. Instead per amount artist religious worker meeting. Teach let discuss week off.',
    'email': 'bradwilliams@example.net',
    'phone_number': '001-735-618-4665x70858',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Durham',
    'Maria Williams',
    'Sharon King',
    'Brian Huynh',
    'Jennifer Villegas',
    'Michelle Hale',
    'Stephanie Roberts',
    'Rachel Jacobson',
],
    'json': {
    'name': 'Bridget Tran',
    'address': '6817 Benjamin Passage Suite 438\nMitchellton, RI 42014',
},
    'key20909': 'value12370',
    'key26977': 'value97192',
    'key89781': 'value58767',
    'key77169': 'value24970',
    'key56045': 'value8625',
    'key52109': 'value23854',
    'key72514': 'value39148',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Phyllis Dominguez',
    'address': '91784 Rodriguez Branch\nRodriguezview, GA 14271',
    'text': 'Good play require bring ahead. Check former help discuss. Professor for again. Fund chair dog art nor little laugh.\nRepresent cold drop star newspaper. Significant another five program.',
    'email': 'bakerjeanette@example.net',
    'phone_number': '(750)715-1599x0206',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Thompson',
    'Andrew Martinez',
    'Peter Anderson',
    'Jamie Thomas',
],
    'json': {
    'name': 'Jennifer Jones',
    'address': '413 Joy Meadow\nRojasland, DE 33864',
},
    'key17031': 'value82186',
    'key65379': 'value6534',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Pamela Finley MD',
    'address': '31603 Donald Passage Suite 167\nSharonmouth, LA 49540',
    'text': 'Can even suggest cost follow. Season simple send deal. Inside yeah mean nor together word hour opportunity. Oil third economy age.\nHere movie yard trouble will. Interest source open indeed personal.',
    'email': 'rachelroth@example.org',
    'phone_number': '236.291.1300',
    'array_int_dynamic': [
    11692,
],
    'array_varchar_dynamic': [
    'Bobby Perkins',
    'James Martinez',
    'Christopher Jarvis',
    'Tanya Lucas',
],
    'json': {
    'name': 'Erika Walker',
    'address': '8061 Day Field\nAyersside, IL 98865',
},
    'key67420': 'value66648',
    'key80554': 'value77470',
    'key34681': 'value63462',
    'key1414': 'value57072',
    'key45442': 'value57957',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Karen Alvarado',
    'address': '35196 Dawson Prairie\nNorth Amyport, SD 22163',
    'text': 'Travel fly challenge. Heavy she provide authority enter. Power yourself oil evening number feeling painting score.\nSet within safe employee majority. Any dinner short skill capital training.',
    'email': 'angelamontoya@example.org',
    'phone_number': '(271)720-7913',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Dennis',
    'Edgar Ruiz',
    'Nathan Daniels',
    'Mrs. Marie Jenkins',
    'Ruth Mcconnell',
    'Kari Calderon',
],
    'json': {
    'name': 'Debbie Gonzalez',
    'address': '8404 Miller Rue Apt. 436\nLake Joseph, FM 22180',
},
    'key10361': 'value48181',
    'key56946': 'value96970',
    'key57526': 'value6455',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Kevin Hill',
    'address': '402 Evans Ford\nPeterfort, PA 46117',
    'text': 'Suggest brother election option. Fire table attorney who fly number new seem. Country stay agreement while.\nAlmost pretty behind authority. My affect side return century act probably answer.',
    'email': 'omoore@example.net',
    'phone_number': '420.583.5648x79856',
    'array_int_dynamic': [
    23754,
],
    'array_varchar_dynamic': [
    'Jacqueline Johnson',
    'Lisa Giles',
    'Craig Schroeder',
    'Heidi Stanton',
    'Jacob Mcmillan',
    'Riley Brown',
    'Alexis Cooper',
],
    'json': {
    'name': 'Brittney Lee',
    'address': '3573 Travis Squares\nNew Tylerview, AK 99199',
},
    'key77242': 'value10552',
    'key339': 'value22814',
    'key30081': 'value163',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Alexa Joyce',
    'address': '0689 Ray Mills\nWest Kenneth, ID 12637',
    'text': 'A white their job. Little vote heart police. Indicate over think heart like left development turn.',
    'email': 'jorgehowell@example.com',
    'phone_number': '+1-367-975-2045x997',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Adams',
    'Nicholas Green',
    'Lisa Moore',
    'Theodore Leonard',
    'Frank Fields',
    'Nicole Rogers MD',
],
    'json': {
    'name': 'Mark Campbell',
    'address': '1889 Lara Villages\nWilliamton, AR 48540',
},
    'key83320': 'value10736',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Tony Brown',
    'address': '26957 Kimberly Estates\nMalonehaven, NJ 81658',
    'text': 'Break become growth party campaign protect human movie. Manager many maintain speak happy. Movie forget great air exist.',
    'email': 'chadlevine@example.com',
    'phone_number': '404.955.3092x23609',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Steven Moore',
],
    'json': {
    'name': 'Kyle Mathis',
    'address': 'PSC 5887, Box 4700\nAPO AA 63641',
},
    'key25711': 'value32925',
    'key15911': 'value97776',
    'key15821': 'value79355',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Gregory Prince',
    'address': '3170 Mccormick Motorway Suite 995\nWest Ryanstad, TN 17330',
    'text': 'After act suddenly might. Consider bring college as indicate ask.\nEnjoy him say require require increase customer. Story fund person class lot they father.',
    'email': 'charlesmiller@example.net',
    'phone_number': '548.255.6465x14264',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Wolfe',
    'Miss Mallory Dennis',
    'Christopher Hess',
    'Richard Weaver MD',
    'Barbara Hahn',
    'Alyssa Davis',
    'Tyler Lee',
],
    'json': {
    'name': 'Dalton Blake',
    'address': '4277 Donna Loaf Apt. 200\nCrossfort, SC 15023',
},
    'key99801': 'value51744',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Eric Webb',
    'address': '4724 Johnson Lock Suite 274\nEast Ruben, ND 85816',
    'text': 'Wonder artist yet discuss institution several if world. Else reduce thing night. Experience deep subject put station way.\nWall page new. Education anything situation campaign.',
    'email': 'kimberlybrooks@example.com',
    'phone_number': '(798)215-1235x8195',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Whitney Erickson',
    'Jennifer Ali',
    'Kelly Garrett',
    'Larry Benson',
    'Reginald Martinez',
    'Paul Aguilar',
    'William Fisher',
],
    'json': {
    'name': 'John Griffin',
    'address': '17584 Cassandra Circles\nStanleymouth, UT 02420',
},
    'key47911': 'value6554',
    'key93522': 'value39790',
    'key87470': 'value3252',
    'key76306': 'value86068',
    'key92522': 'value94702',
    'key97038': 'value2649',
    'key50462': 'value35608',
    'key81917': 'value60829',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Charles Brennan',
    'address': '97341 Matthew Dale Suite 642\nSouth Sandra, FM 06648',
    'text': 'Expert move tend particularly half. Consider past body do leg.',
    'email': 'joseph24@example.net',
    'phone_number': '773-650-1479x168',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joel Rodriguez',
    'Brandon Hogan',
    'Miss Patricia Bennett',
    'John Jordan',
    'Lisa Edwards',
    'Anthony Miller',
    'Ashley Williams',
    'Tanya James',
],
    'json': {
    'name': 'William Rogers',
    'address': 'USS Norton\nFPO AE 18932',
},
    'key77239': 'value24496',
    'key5261': 'value96280',
    'key66967': 'value37690',
    'key64538': 'value1929',
    'key10744': 'value93165',
    'key94539': 'value42056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'David Sanchez',
    'address': '075 Little Village Apt. 145\nScottfort, ND 14606',
    'text': 'Will view fire here any third stop. Myself recognize little where rule.\nMove even at understand wide. Dinner talk attention again.',
    'email': 'ujohnson@example.com',
    'phone_number': '717.956.8077x64514',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Garrison',
],
    'json': {
    'name': 'Drew Gaines',
    'address': '25005 Olsen Cove\nPort Carolland, FL 96533',
},
    'key20252': 'value63423',
    'key39044': 'value40800',
    'key11006': 'value27868',
    'key48692': 'value9670',
    'key10948': 'value37811',
    'key23449': 'value39202',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Rhonda Jones',
    'address': '930 Steven Spurs Apt. 394\nLake Crystal, TN 14927',
    'text': 'See teach across word kitchen. Participant audience realize teacher our need happy.\nGuy form within item. Table attorney worry light.',
    'email': 'emma33@example.org',
    'phone_number': '574-879-4035x25531',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Frank Davis',
    'Deanna Quinn',
    'Miss Sarah Williams',
    'Amy Stewart',
    'Steven Rice',
],
    'json': {
    'name': 'Angel Wilson',
    'address': '8366 Hoffman Loop\nNew Annmouth, MD 87353',
},
    'key39360': 'value58416',
    'key57256': 'value27772',
    'key66507': 'value57915',
    'key54517': 'value46415',
    'key67153': 'value34013',
    'key61018': 'value55662',
    'key97258': 'value43767',
    'key23012': 'value45003',
    'key45491': 'value20030',
    'key31463': 'value99060',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Nicholas Macdonald',
    'address': '57122 Gonzalez Parks\nEast Marissa, IA 47713',
    'text': 'Second we risk entire need already recognize shoulder.\nHimself sell player edge pattern son already various. Seat media large list project memory student drop.\nQuickly past product recognize laugh.',
    'email': 'armstrongelizabeth@example.org',
    'phone_number': '(792)911-2039x130',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Moses',
    'Kathleen Anderson',
    'Jordan Vasquez',
    'Evan Nixon',
    'Rebecca Dunlap',
    'Joseph Fox',
    'Michelle Massey',
],
    'json': {
    'name': 'George Sanchez',
    'address': '4743 Crystal Overpass\nEast Cherylfurt, MO 58515',
},
    'key84425': 'value83921',
    'key20959': 'value28851',
    'key83737': 'value50968',
    'key86815': 'value91923',
    'key82546': 'value95155',
    'key64229': 'value14042',
    'key91995': 'value64122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Dr. James Murray',
    'address': '702 Ashley Valleys\nRickeymouth, DE 88975',
    'text': 'Food find image light job place. Debate ball assume rise. Where visit recognize bed.',
    'email': 'larry49@example.net',
    'phone_number': '(747)470-6009x698',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Kaiser',
    'Courtney Harrison',
    'Joseph Medina',
    'Derrick Lloyd',
    'Maurice Sanchez',
    'William Beck',
    'Shannon Johnson',
],
    'json': {
    'name': 'Jaime Gutierrez',
    'address': '2906 Zhang Flats Apt. 883\nEdwardstown, GU 63642',
},
    'key59208': 'value94955',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Claudia Ramsey',
    'address': '2190 Hunter Circles\nWaltonberg, PR 46144',
    'text': 'Husband serve speech poor dinner list benefit. Position American eat gun.\nCountry development author talk national tax. Month owner may here blood. Drive our could one top.',
    'email': 'smithdanny@example.org',
    'phone_number': '(489)406-6708',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Gordon',
    'Collin Baker',
    'Gary Mitchell',
    'Jennifer Russo',
    'James Kelly',
    'Russell Taylor',
],
    'json': {
    'name': 'Joe Kemp',
    'address': '11243 Savannah Brook\nWest Ruth, WY 07034',
},
    'key68339': 'value57758',
    'key58160': 'value68829',
    'key82979': 'value38340',
    'key59225': 'value63409',
    'key63504': 'value51233',
    'key34739': 'value48883',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Brandon Hardy',
    'address': '342 Logan Estate\nAaronfurt, OR 86038',
    'text': 'Determine subject quickly more. Politics response account child. Value either make may grow free require community.',
    'email': 'sanderscourtney@example.org',
    'phone_number': '307.266.7776x3594',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Mendoza',
    'Timothy Ewing',
    'Matthew Gray',
    'Melissa Morris MD',
],
    'json': {
    'name': 'Jason Miller',
    'address': '29315 Turner Green Suite 282\nRileyland, RI 15504',
},
    'key57779': 'value40208',
    'key91401': 'value78638',
    'key41533': 'value56759',
    'key6256': 'value41994',
    'key18247': 'value83098',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Billy Mcgee',
    'address': '55673 John Corner Apt. 425\nSouth Lisa, HI 46351',
    'text': 'Late staff same enough both up seem. Trade bag approach check. Film artist after help arrive mind true leader.\nEconomic not recent wall just. Him sport politics during talk.',
    'email': 'anthonynunez@example.org',
    'phone_number': '463.380.3994',
    'array_int_dynamic': [
    40276,
],
    'array_varchar_dynamic': [
    'Rachel Sanchez',
    'Heather Rowe',
    'Katelyn Webster',
    'William Sanchez',
    'Tammy Newman',
    'Yvonne Anderson',
    'Alexander Harding',
    'Isaac Green',
    'Veronica Daniel',
],
    'json': {
    'name': 'Courtney Friedman',
    'address': '005 John Common\nMyersshire, KY 01079',
},
    'key14461': 'value69837',
},
],
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
        """测试请求 2 - POST http://172.17.0.5:23210/v1/vector/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'be7b67fb-62f1-11f0-91f8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_54_811495ZyAgXkNO',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b7c2b33a-62f1-11f0-a980-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_54_811495ZyAgXkNO',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 0_1]_1752745087.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid011752745087Json()
    test.run_tests()
