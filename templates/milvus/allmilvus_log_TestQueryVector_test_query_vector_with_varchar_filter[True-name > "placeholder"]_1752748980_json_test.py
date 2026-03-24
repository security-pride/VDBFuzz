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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_varchar_filter[True-name > "placeholder"]_1752748980_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name > "placeholder"]_1752748980.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithVarcharFilterTrueNamePlaceholder1752748980Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name > "placeholder"]_1752748980.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name > "placeholder"]_1752748980.json"
        self.test_count = 8  # 测试方法数量
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
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
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
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
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
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
    'data': [
    {
    'id': 17527489765306,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Dr. Jennifer Jones',
    'address': '0033 Sandra Canyon\nSouth Nancyberg, IL 98724',
    'text': 'Let million music daughter pay military factor. Show business sing. Quite great stop not since office address.',
    'email': 'rodneyreid@example.net',
    'phone_number': '001-493-537-5370',
    'json': {
    'name': 'Sara Jackson',
    'address': '287 Matthew Expressway Suite 099\nKingport, AK 34431',
},
    'key34530': 'value77333',
    'key19005': 'value25079',
    'key61277': 'value80643',
},
    {
    'id': 17527489765330,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Timothy Rodriguez',
    'address': '16246 Rebecca Port Suite 976\nEast Brittany, VT 43090',
    'text': 'Various set table campaign west defense finally. Once response return site second artist what. Somebody wall exist difference concern.',
    'email': 'nhaynes@example.com',
    'phone_number': '(593)912-5488',
    'json': {
    'name': 'Mr. Derek Wade',
    'address': '63082 Young Haven Suite 172\nNorth Mirandachester, NJ 48135',
},
    'key58545': 'value39381',
    'key86182': 'value46567',
    'key33533': 'value34174',
},
    {
    'id': 17527489765343,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Tamara Zamora',
    'address': 'PSC 4885, Box 1369\nAPO AE 05600',
    'text': 'Year performance worker natural. Him PM consumer PM perform number style call. Many than ready sister voice treatment question. Technology pull record.',
    'email': 'hesteremily@example.net',
    'phone_number': '(907)394-0034x71425',
    'json': {
    'name': 'David Velez',
    'address': '7598 Anderson Street Suite 811\nLangfurt, MP 43376',
},
    'key46529': 'value85608',
    'key18179': 'value43982',
    'key30059': 'value43087',
    'key88391': 'value16681',
    'key57546': 'value743',
    'key81318': 'value32643',
    'key23188': 'value10433',
},
    {
    'id': 17527489765354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Donna Sanchez',
    'address': '6485 Melinda Port Apt. 741\nWilsonburgh, AK 19687',
    'text': 'Form education focus meet beyond sing everything. Meeting beat dark out turn fill sing.\nMight put agency soon consider. Now entire listen school structure.',
    'email': 'stephen11@example.org',
    'phone_number': '(256)314-5260x4360',
    'json': {
    'name': 'Joseph Brown',
    'address': '2131 Mary Pass\nPort Joshua, WV 81469',
},
    'key89268': 'value79775',
    'key14171': 'value34660',
    'key10019': 'value81495',
    'key5549': 'value54805',
    'key37899': 'value99641',
},
    {
    'id': 17527489765366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Ryan Decker',
    'address': '82190 Stephanie Burg Suite 557\nVickieside, MD 09039',
    'text': 'Center author budget sometimes store letter very artist. Start form network explain large whether hundred. Very want ever meet family help.',
    'email': 'amber92@example.com',
    'phone_number': '365-814-5509',
    'json': {
    'name': 'Eddie Johnson',
    'address': '1105 Moore Village Suite 230\nAnthonytown, AK 70269',
},
    'key88473': 'value76136',
    'key67947': 'value89652',
    'key48736': 'value85116',
},
    {
    'id': 17527489765377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Zachary Ware',
    'address': '109 Harper Skyway Apt. 865\nCaseyport, ND 45293',
    'text': 'Personal expect seem. Start positive wall. Eight media successful market or too.',
    'email': 'rmcdonald@example.com',
    'phone_number': '332-731-8934x37074',
    'json': {
    'name': 'Frank Lee',
    'address': '02661 Shannon Valley\nWest Joseph, TN 96961',
},
    'key1579': 'value47580',
    'key16768': 'value86643',
    'key47580': 'value70863',
    'key85081': 'value29920',
    'key1598': 'value6297',
},
    {
    'id': 17527489765389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Melissa Moore',
    'address': '3451 Gill Unions\nBellburgh, MP 44155',
    'text': 'Sound process month strong show next response meeting. State glass paper put surface.\nSouthern two woman and. Major face traditional moment chance here make.',
    'email': 'emilyspencer@example.org',
    'phone_number': '784-840-8660',
    'json': {
    'name': 'Tami Sanchez',
    'address': '87294 Brian Lock Suite 760\nNorth Jeffreyview, PW 16552',
},
    'key3907': 'value67078',
    'key77279': 'value75762',
    'key97801': 'value54090',
},
    {
    'id': 17527489765402,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Larry Anderson',
    'address': '944 Valerie Ranch\nTuckertown, VI 56869',
    'text': 'Style final be task. West age market western foreign free program.\nMy raise type gun offer water. Name sport half hear. Produce arm sense themselves rule education focus.',
    'email': 'marywright@example.com',
    'phone_number': '(661)895-4797',
    'json': {
    'name': 'Bryan Taylor',
    'address': '6082 Lewis Brook\nNew Kathy, MT 00811',
},
    'key96511': 'value9256',
},
    {
    'id': 17527489765414,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kevin Hatfield',
    'address': '736 Morales Ville Suite 758\nMonicatown, NV 95371',
    'text': 'Standard upon plan world floor by. Husband any understand such huge ask key for. Security national week home real southern continue. Building fly white.',
    'email': 'tallen@example.net',
    'phone_number': '001-343-548-4586',
    'json': {
    'name': 'Heather Butler',
    'address': 'PSC 1399, Box 0698\nAPO AA 05969',
},
    'key32224': 'value96909',
    'key49575': 'value31424',
    'key46194': 'value19682',
    'key52994': 'value51870',
    'key78768': 'value87532',
    'key6056': 'value5068',
    'key16542': 'value96688',
},
    {
    'id': 17527489765423,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Michele Daugherty',
    'address': '115 Barbara Extension Apt. 810\nWest Veronicaside, MA 55884',
    'text': 'Sell agency white three offer project. Child song author respond social capital. Religious paper receive describe plant nor page.',
    'email': 'adam13@example.com',
    'phone_number': '001-573-878-8597',
    'json': {
    'name': 'Jennifer Reed',
    'address': '00592 Caitlin Skyway Apt. 268\nPeterhaven, KY 08251',
},
    'key20070': 'value68983',
    'key78291': 'value9947',
    'key8385': 'value28019',
    'key56340': 'value92797',
    'key82545': 'value42618',
    'key4098': 'value64367',
    'key93251': 'value35549',
    'key31343': 'value86189',
    'key74730': 'value73821',
    'key13432': 'value72542',
},
    {
    'id': 17527489765434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Selena Baldwin',
    'address': '198 Tamara Knoll Apt. 050\nWest Lauren, DE 09035',
    'text': 'Anything mission so author. Forget wear administration identify red help official. Argue throw pick.\nPull song state best human. Product factor remain item reduce long last.',
    'email': 'dorothymendez@example.com',
    'phone_number': '+1-871-884-3740',
    'json': {
    'name': 'John Young',
    'address': '141 Atkins Land Suite 752\nWest Nicole, KS 61705',
},
    'key62955': 'value19832',
    'key28711': 'value60809',
    'key86170': 'value38573',
    'key60451': 'value65673',
},
    {
    'id': 17527489765445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Mrs. Lisa Newman',
    'address': '1969 Mcclain Shoal\nJonesfurt, KS 69355',
    'text': 'Church bit seat both. Around kind poor professor. Information agency hold someone. Upon body off fill camera Democrat thousand.',
    'email': 'ojohnson@example.org',
    'phone_number': '+1-495-554-1221',
    'json': {
    'name': 'Edward Bell',
    'address': '36146 Sandra Isle Apt. 596\nNorth Joseph, ID 56882',
},
    'key8921': 'value79608',
    'key46163': 'value84034',
},
    {
    'id': 17527489765456,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Denise Hubbard',
    'address': '16569 Davis Unions Suite 522\nGallagherborough, MP 26685',
    'text': 'Old your effort indeed heart. Both a second game.\nStrong family reality only which pattern west. Ahead foreign traditional.\nParty hotel air model image term.',
    'email': 'gaybrian@example.net',
    'phone_number': '+1-243-392-7525',
    'json': {
    'name': 'Zachary Cox',
    'address': 'Unit 0142 Box 7589\nDPO AP 53036',
},
    'key8544': 'value5801',
    'key94531': 'value58528',
    'key74732': 'value86490',
    'key69914': 'value17690',
},
    {
    'id': 17527489765466,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Sean Lindsey',
    'address': '1737 Pittman Mountains\nNew James, CT 38961',
    'text': 'Guy then down middle. Sure better human measure three.\nDespite executive environmental find matter whose live go. Key reflect how civil. College small along he school suffer.',
    'email': 'johnfowler@example.org',
    'phone_number': '557-490-8039',
    'json': {
    'name': 'Erin Mcintyre',
    'address': '6694 Smith Course\nLake Jonathanmouth, MN 35486',
},
    'key10613': 'value44109',
},
    {
    'id': 17527489765478,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Benjamin Rodriguez',
    'address': '953 Trevor View\nAndrewmouth, FM 14020',
    'text': 'Course fund ever truth forget what. Deal thing both hit. Laugh be land course page.',
    'email': 'gjohnson@example.com',
    'phone_number': '+1-679-594-8857',
    'json': {
    'name': 'William Hernandez',
    'address': '0155 David Extensions Suite 422\nValenciaberg, NM 81796',
},
    'key65653': 'value18914',
    'key78601': 'value87802',
    'key756': 'value39111',
    'key21242': 'value33550',
    'key65660': 'value55506',
    'key24796': 'value99026',
    'key5430': 'value37443',
    'key91331': 'value61230',
    'key62963': 'value81097',
},
    {
    'id': 17527489765488,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Miranda Berger',
    'address': '9767 Fleming Run\nMillerburgh, NC 33709',
    'text': 'Character your medical its what light type. Pm off rise open son no station. Land wonder mouth avoid.',
    'email': 'ghunt@example.org',
    'phone_number': '(695)200-8273',
    'json': {
    'name': 'Lauren Giles',
    'address': '51523 Anita Squares Apt. 772\nBrownton, MI 84602',
},
    'key53714': 'value87194',
    'key85955': 'value25040',
    'key27601': 'value90063',
    'key52875': 'value19117',
},
    {
    'id': 17527489765499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Tanner Mason',
    'address': '945 Diana Heights Suite 337\nPort Brettborough, SD 05974',
    'text': 'Increase such trouble. Power worker think without husband value everyone. By short whether feel.\nOur front market police their old continue might. Fund within score end without.',
    'email': 'julieray@example.net',
    'phone_number': '808.789.4720x010',
    'json': {
    'name': 'Timothy Morgan',
    'address': '5019 Cory Brooks Apt. 088\nMorrisville, MS 95176',
},
    'key89633': 'value22529',
    'key54225': 'value25772',
    'key78395': 'value36099',
},
    {
    'id': 17527489765511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Nancy Weaver',
    'address': '00168 Carrie Roads\nLisastad, PA 69002',
    'text': 'Sound good garden artist true every. Majority modern model radio house.\nEvening father staff senior.\nProgram owner class. Air whatever official world. Right today everybody small.',
    'email': 'garciajames@example.org',
    'phone_number': '+1-542-307-1756x346',
    'json': {
    'name': 'Jessica Wright',
    'address': '46783 Harris Forges\nSamuelville, NE 44407',
},
    'key31850': 'value61409',
    'key51703': 'value47834',
},
    {
    'id': 17527489765523,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Julie Mills',
    'address': '4378 Lee Walks\nSouth Staceyville, FL 52978',
    'text': 'Interesting culture themselves in inside. Guy treatment take recently center couple increase.',
    'email': 'sarahmyers@example.net',
    'phone_number': '214.869.7420',
    'json': {
    'name': 'Jeffrey Wilson',
    'address': '791 Taylor Burg\nSouth Stephanie, ME 88969',
},
    'key82001': 'value30787',
    'key10796': 'value57093',
    'key16349': 'value89002',
    'key30260': 'value2547',
    'key9628': 'value53315',
    'key52564': 'value85577',
    'key46978': 'value99885',
},
    {
    'id': 17527489765534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Madison Foster',
    'address': '30042 Smith Squares\nShawshire, WA 57385',
    'text': 'Least military story medical single. Soldier modern beat perhaps tell feeling machine degree. Key option city coach treat five who.',
    'email': 'morrowchristopher@example.org',
    'phone_number': '763.493.7518',
    'json': {
    'name': 'Deborah Garcia',
    'address': '74316 Julia Burgs\nNorth Nicholas, RI 80568',
},
    'key73819': 'value69421',
    'key49024': 'value4185',
    'key31239': 'value9714',
    'key27302': 'value55760',
    'key69859': 'value76747',
    'key46354': 'value99253',
},
    {
    'id': 17527489765546,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Erin Cervantes',
    'address': '802 Ware Turnpike\nNorth Destiny, MA 99880',
    'text': 'Mrs trade they probably for item yes. Strong summer meet thought lead player help share.\nWould sound push term keep tough radio. Wide design capital.',
    'email': 'gschwartz@example.com',
    'phone_number': '416.581.5774',
    'json': {
    'name': 'Laura Ramos',
    'address': '508 Stefanie Union Suite 180\nEast Mike, AZ 64088',
},
    'key2815': 'value9442',
    'key10817': 'value70950',
    'key68841': 'value33632',
    'key96196': 'value20951',
    'key62637': 'value5102',
    'key40699': 'value62735',
    'key64616': 'value79337',
    'key58578': 'value49802',
    'key95713': 'value75129',
},
    {
    'id': 17527489765556,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Virginia Hardy',
    'address': '271 Jones Gateway Suite 032\nPort Seanfort, GU 58889',
    'text': 'Week stand defense perhaps call somebody. Use just push example.',
    'email': 'randallpitts@example.net',
    'phone_number': '773.538.4266',
    'json': {
    'name': 'Julie Zavala',
    'address': '6147 Marilyn Vista Apt. 911\nDavidside, AK 43390',
},
    'key20292': 'value94151',
    'key75474': 'value17866',
    'key82859': 'value26099',
},
    {
    'id': 17527489765568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Rachel Taylor',
    'address': '04956 Jeremy Plain\nJustinhaven, NM 09587',
    'text': 'Mrs card fact class hold blue might same.\nMain free particular quickly add. The site sea debate scene identify ahead.\nParent town mission. Personal hold other school sea again product.',
    'email': 'riverabrenda@example.com',
    'phone_number': '456.205.8688x3534',
    'json': {
    'name': 'Emily Clark',
    'address': '88019 Wayne Port Apt. 672\nMichaeltown, SD 20143',
},
    'key37721': 'value62984',
},
    {
    'id': 17527489765579,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Gabrielle Phillips',
    'address': '675 Wanda Union\nBarrhaven, KY 52027',
    'text': 'Even nearly similar nature who. Challenge activity audience short.\nAgain treatment western film and as. Address natural seat paper ahead including safe. Hand treat left discover development.',
    'email': 'janet01@example.com',
    'phone_number': '8003393803',
    'json': {
    'name': 'Christine Webb',
    'address': '8411 Melissa Square Apt. 833\nHowardchester, ME 78717',
},
    'key93954': 'value397',
    'key27161': 'value93283',
    'key81445': 'value43024',
    'key31742': 'value88293',
    'key66164': 'value72970',
    'key97913': 'value68104',
    'key62562': 'value14065',
    'key17480': 'value96702',
    'key38882': 'value25389',
},
    {
    'id': 17527489765590,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Scott Diaz',
    'address': '10817 Travis Curve\nLake Barbara, PR 22481',
    'text': 'Health federal class after kind fact. Ago open special structure. Six rather race eat population go wrong.',
    'email': 'stanleyheather@example.net',
    'phone_number': '649-731-5013',
    'json': {
    'name': 'Samantha Davis',
    'address': '83928 Rice Parks Apt. 870\nNew Shannon, MO 26508',
},
    'key68210': 'value35726',
    'key88149': 'value51000',
    'key48903': 'value90294',
    'key19450': 'value53594',
    'key39772': 'value36313',
    'key35780': 'value94688',
    'key12951': 'value80732',
    'key76820': 'value49762',
},
    {
    'id': 17527489765602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Marie Monroe',
    'address': '472 James Stravenue\nPort Sandra, CA 05525',
    'text': 'We offer list policy Republican ahead traditional. Full attack responsibility stay light. Break much cause whole.',
    'email': 'timothydixon@example.org',
    'phone_number': '789.300.9514x7590',
    'json': {
    'name': 'Aaron Hernandez',
    'address': '20732 Jennifer Estate Suite 724\nChristophertown, AL 45383',
},
    'key82880': 'value95427',
    'key41018': 'value55579',
    'key51486': 'value96341',
    'key71799': 'value29590',
    'key73965': 'value86631',
},
    {
    'id': 17527489765613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Karen Jones',
    'address': '44197 Melissa Corners\nEast Christine, SD 88454',
    'text': 'Writer hundred property kind green nothing. Reflect believe themselves present popular. Pick away peace research after human carry.',
    'email': 'tina09@example.com',
    'phone_number': '526-464-5758',
    'json': {
    'name': 'Victor Vance',
    'address': '92274 Brian View\nWrightburgh, ID 35733',
},
    'key65965': 'value59499',
    'key18337': 'value92063',
    'key67357': 'value38439',
    'key2673': 'value60473',
    'key43425': 'value24933',
    'key80279': 'value38763',
    'key70984': 'value44272',
    'key24852': 'value82019',
    'key96686': 'value81708',
},
    {
    'id': 17527489765623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Wendy Clark',
    'address': '56904 Hurst Route\nWendychester, IL 73897',
    'text': 'Job democratic view sea. Send away face matter put much.\nCareer finally sort enough bit government. Particularly expect owner system catch beyond any. North charge husband defense national.',
    'email': 'fadams@example.org',
    'phone_number': '723.307.8565x755',
    'json': {
    'name': 'Victoria Chapman',
    'address': 'USNV Oliver\nFPO AA 38895',
},
    'key93547': 'value22133',
    'key2247': 'value5984',
    'key87318': 'value25145',
    'key15402': 'value92374',
    'key87843': 'value58266',
    'key56670': 'value14239',
    'key10880': 'value24021',
    'key97175': 'value6840',
},
    {
    'id': 17527489765633,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Elizabeth Krause',
    'address': 'PSC 8959, Box 7496\nAPO AA 67035',
    'text': 'International accept change though. Human reality break.\nTen weight produce throw join discover. Share shoulder so science pressure its.',
    'email': 'owenseric@example.net',
    'phone_number': '(417)649-5526x573',
    'json': {
    'name': 'Jill Weber',
    'address': '51626 Pamela Expressway Apt. 698\nMichaelborough, VA 45634',
},
    'key99641': 'value88623',
},
    {
    'id': 17527489765643,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Richard Diaz',
    'address': '9491 Lamb Loaf Apt. 834\nPort Justinfurt, DC 99165',
    'text': 'Nice pick apply production. Event image in amount. Individual computer off.\nSuccess moment stop sing nothing participant necessary help. Argue war bit charge teacher civil player.',
    'email': 'vbrown@example.com',
    'phone_number': '(936)288-6167',
    'json': {
    'name': 'Terry Cox',
    'address': '966 Smith Viaduct\nNorth Hunter, KY 24515',
},
    'key7464': 'value28754',
    'key90231': 'value90568',
    'key34865': 'value80869',
    'key65284': 'value72809',
    'key79635': 'value68042',
    'key98832': 'value24208',
},
    {
    'id': 17527489765654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Karen Stewart',
    'address': '5409 Melissa Views Apt. 275\nSouth Steven, SC 46572',
    'text': 'Fly politics charge activity. Adult training night scientist better table eight. Answer back account money challenge call. Give item why difference issue gas.',
    'email': 'jasonarroyo@example.org',
    'phone_number': '(731)945-8413',
    'json': {
    'name': 'Rebekah Myers',
    'address': '936 Aguirre Extension Apt. 137\nWilliamsberg, MA 33583',
},
    'key37022': 'value16288',
    'key29611': 'value75259',
    'key62710': 'value12882',
    'key26752': 'value88536',
},
    {
    'id': 17527489765665,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Todd Smith',
    'address': '639 Tammy Freeway Apt. 002\nWrightbury, HI 17900',
    'text': 'Idea quality task second perform hand together. Two like enter might room manager eight enter.\nHour throw run stay. Possible well yeah over citizen evening business. Firm for analysis meet.',
    'email': 'rebecca06@example.org',
    'phone_number': '001-393-675-6202x9249',
    'json': {
    'name': 'Timothy Mcgee',
    'address': '481 Johnathan Fields Apt. 850\nStevensview, NM 01817',
},
    'key5934': 'value11335',
},
    {
    'id': 17527489765676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Amber Garcia',
    'address': '482 Jeffrey Hill Suite 994\nNorth Valerie, NV 26926',
    'text': 'Trouble remain generation. Cost major whether outside.\nBank say minute marriage. Every event bed happen every minute box. Decide thought thought how.',
    'email': 'dustincarlson@example.com',
    'phone_number': '+1-977-696-5613',
    'json': {
    'name': 'Nicole Mckay',
    'address': '4695 Carlos Port Apt. 969\nKatiefort, IN 20874',
},
    'key71132': 'value16772',
    'key16507': 'value16480',
    'key43648': 'value15797',
},
    {
    'id': 17527489765688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Tracey Hoffman',
    'address': '0887 Michelle Path Apt. 186\nBellchester, SD 80254',
    'text': 'Kid pick town theory hotel. Officer billion point quite. Develop beat glass. Green raise impact as film least.',
    'email': 'wellsevan@example.net',
    'phone_number': '393-624-9366x9894',
    'json': {
    'name': 'Dr. Anne Montgomery',
    'address': '652 David Union\nEast Johnland, ME 54595',
},
    'key21282': 'value59903',
},
    {
    'id': 17527489765699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Katelyn Jackson',
    'address': '0391 Elizabeth Grove Apt. 780\nStephensview, WI 28117',
    'text': 'Fine state well tough seven scene protect town. Hear determine because there food specific.\nModel leave loss party. Pm plan should station tonight describe. Father sound oil now watch heart.',
    'email': 'suzannedavis@example.net',
    'phone_number': '547-323-1137x490',
    'json': {
    'name': 'Michelle Bates',
    'address': '9095 Pamela Inlet Apt. 266\nWrightstad, WI 86710',
},
    'key14943': 'value95972',
    'key41253': 'value43031',
    'key73421': 'value2191',
    'key26444': 'value60573',
    'key5298': 'value2457',
    'key13833': 'value87946',
    'key6515': 'value89096',
    'key28724': 'value770',
    'key43760': 'value68002',
    'key56834': 'value9885',
},
    {
    'id': 17527489765711,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Brenda Barker',
    'address': '605 Thompson Passage\nFletchertown, AS 83775',
    'text': 'Center training worry system public. Table item throw reduce game generation.\nType will pull. Citizen drop individual PM heavy nor. Listen citizen mind computer particularly window.',
    'email': 'jward@example.org',
    'phone_number': '(893)879-9903',
    'json': {
    'name': 'William Norton',
    'address': '891 Mathis Fords\nEast Brianna, DE 50775',
},
    'key49897': 'value26224',
    'key53970': 'value43876',
    'key5819': 'value21286',
    'key52631': 'value8989',
    'key23587': 'value92231',
    'key49982': 'value25332',
},
    {
    'id': 17527489765723,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Anthony Mills',
    'address': '0637 Simpson Forge\nPort Jason, UT 29104',
    'text': 'Pressure soldier into team performance. Southern wife expect reality since western. Upon sea significant range into daughter phone stop.\nToward just walk. Natural us range former rate young yourself.',
    'email': 'epratt@example.net',
    'phone_number': '990-949-6547x060',
    'json': {
    'name': 'Aaron Alvarado',
    'address': '1421 Andrew Station Apt. 609\nStephanieport, CO 01648',
},
    'key78872': 'value64944',
},
    {
    'id': 17527489765733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Aaron Jones',
    'address': '246 Barajas Pine\nEast Bradley, KY 45227',
    'text': 'Word from front war. Human enough nation family.\nHelp cover term run wall a hear. White owner listen short.\nFigure detail leader throw create else probably. Store sister there car.',
    'email': 'nashsean@example.org',
    'phone_number': '511.269.1113x545',
    'json': {
    'name': 'James Collins',
    'address': '1511 Beth Village\nSouth Cameronside, MN 22930',
},
    'key11924': 'value74862',
    'key49579': 'value70384',
    'key82970': 'value31465',
    'key86053': 'value51650',
    'key62493': 'value77225',
    'key52473': 'value28120',
    'key20424': 'value57058',
    'key97681': 'value66594',
    'key62047': 'value10260',
},
    {
    'id': 17527489765745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Steven Mckenzie',
    'address': '13056 William Ville Suite 709\nLake James, FL 82431',
    'text': 'According national surface dream heart environmental. Beat should get public you with. Reveal paper right me deal try.\nRadio miss another more home clearly. Something ahead realize score.',
    'email': 'jamesclark@example.com',
    'phone_number': '209-792-5378',
    'json': {
    'name': 'Scott Page',
    'address': '30064 Daniel Mount\nSouth Brianshire, NC 83625',
},
    'key76641': 'value42173',
    'key15731': 'value62956',
    'key82448': 'value63854',
},
    {
    'id': 17527489765756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'David Dixon',
    'address': 'PSC 4201, Box 2957\nAPO AA 78868',
    'text': 'Writer law attention herself here. Tax maintain newspaper total him member project.',
    'email': 'meganwatkins@example.com',
    'phone_number': '(644)464-0053x25684',
    'json': {
    'name': 'Daniel Williams',
    'address': '568 Rivera Wall\nRobertborough, NV 33192',
},
    'key59629': 'value35343',
},
    {
    'id': 17527489765765,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Dustin Buchanan',
    'address': 'USCGC Alvarez\nFPO AA 34793',
    'text': 'Other worry laugh popular that. Discover international hot head city.\nAdult student ready around recently available us if. Center relate wall room detail.',
    'email': 'mcmahonbonnie@example.net',
    'phone_number': '839-813-0322x950',
    'json': {
    'name': 'Kimberly Rasmussen',
    'address': '686 Matthew Cliffs\nJoseshire, CA 20178',
},
    'key42942': 'value76996',
},
    {
    'id': 17527489765775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Michelle Gray',
    'address': '19458 Michael Mountain\nLake Theresa, AL 95715',
    'text': 'And relationship garden. Foot trip car tree parent order machine. Movement skill plant put.\nOccur health window our else reality. Growth build site others set. Individual after pressure.',
    'email': 'nicole57@example.org',
    'phone_number': '626.446.7111',
    'json': {
    'name': 'Rebecca Hurst',
    'address': '914 Eugene Loop\nPort John, RI 75265',
},
    'key15106': 'value36892',
    'key73291': 'value31324',
},
    {
    'id': 17527489765785,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Lynn Frazier',
    'address': 'PSC 1988, Box 5618\nAPO AP 56843',
    'text': 'Pay walk instead prepare. Mother serious analysis interesting against able. Card information new present.\nTwo rate green. Bar decide him sure school attack five.',
    'email': 'audrey88@example.com',
    'phone_number': '834.361.4375',
    'json': {
    'name': 'David Hoffman',
    'address': 'Unit 2151 Box 4487\nDPO AE 95697',
},
    'key59469': 'value60220',
    'key31990': 'value4397',
},
    {
    'id': 17527489765791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Charles Campbell',
    'address': '3606 Sandra Overpass Suite 657\nSouth Matthew, AL 85371',
    'text': 'Realize wife ago direction rather. Agreement music across life situation.\nCivil nothing speech detail five which. Lay prevent seven candidate defense news.',
    'email': 'lisaleon@example.net',
    'phone_number': '8405693691',
    'json': {
    'name': 'Roger Duke',
    'address': '386 Stokes River Suite 274\nSouth Reneefurt, MO 10711',
},
    'key86001': 'value54236',
    'key90457': 'value21703',
    'key14381': 'value33026',
    'key30942': 'value70784',
    'key31102': 'value60648',
    'key25965': 'value54442',
},
    {
    'id': 17527489765803,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Rachel Walker',
    'address': '40811 Moss Views Suite 350\nLake Edwardstad, NJ 64975',
    'text': 'Kind note while generation trade suffer recent. Might speech this Republican.\nWish popular religious tonight good. No bag skin.',
    'email': 'qwalker@example.com',
    'phone_number': '246-238-8947',
    'json': {
    'name': 'Mrs. Jill Neal',
    'address': '4508 Christopher Fork Apt. 395\nVictorialand, AS 49571',
},
    'key51517': 'value11389',
    'key67273': 'value64039',
    'key70372': 'value47378',
},
    {
    'id': 17527489765814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Kenneth Stewart',
    'address': '973 Holland Field Apt. 179\nPowellville, ND 72230',
    'text': 'Service worry thing realize available group five. Over upon official often reduce different exactly. Growth Congress agent level later save finish.',
    'email': 'perry70@example.org',
    'phone_number': '001-507-657-6979x67462',
    'json': {
    'name': 'Danielle George',
    'address': '88507 Michael Unions\nJamesfurt, FM 16459',
},
    'key45609': 'value87879',
    'key75900': 'value90205',
    'key8401': 'value76203',
},
    {
    'id': 17527489765824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Eric Summers',
    'address': 'Unit 9031 Box 1447\nDPO AE 19805',
    'text': 'Market parent each character style degree since. Shoulder case receive. Cause person and old economic land unit. Station concern enter federal member attack television.',
    'email': 'erin64@example.org',
    'phone_number': '(813)524-5493x297',
    'json': {
    'name': 'David Smith',
    'address': '36796 Garcia Loaf Suite 571\nSouth Crystal, TN 20654',
},
    'key89632': 'value23839',
    'key38090': 'value75555',
    'key53324': 'value31037',
    'key43486': 'value8261',
},
    {
    'id': 17527489765833,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Tamara Wang',
    'address': '96744 Dixon Glens Apt. 313\nAmyside, MS 28416',
    'text': 'Require carry artist first line nice similar. Growth option town north attack dream century. Care song want station work radio produce style.',
    'email': 'wwarner@example.net',
    'phone_number': '001-582-766-5549x499',
    'json': {
    'name': 'Douglas Berry',
    'address': '70964 Shepard Well Apt. 418\nJohnville, MP 52526',
},
    'key53808': 'value38363',
    'key21073': 'value67342',
    'key75490': 'value83595',
    'key35372': 'value67418',
    'key42734': 'value18539',
    'key32024': 'value15275',
    'key15133': 'value67188',
    'key77398': 'value61241',
    'key82055': 'value23613',
    'key21723': 'value53426',
},
    {
    'id': 17527489765844,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Michelle Gomez',
    'address': 'Unit 9616 Box 3468\nDPO AP 41863',
    'text': 'Science break respond letter wide executive type technology. Follow program blood reason side happy. Example lot throw drive production. Watch specific blue owner.',
    'email': 'hgarcia@example.com',
    'phone_number': '001-349-677-4342x906',
    'json': {
    'name': 'Kelly Wells',
    'address': '9874 Jones Run\nCatherineborough, WA 20568',
},
    'key28370': 'value52194',
},
    {
    'id': 17527489765853,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Brittney Rivera',
    'address': '80394 Laurie Lane\nMadelinechester, NY 02909',
    'text': 'Again sense spend. This speech computer do. Help development pretty issue door capital also.\nPush side either political anyone. Their improve action name whatever difference drop.',
    'email': 'brittanydudley@example.net',
    'phone_number': '(966)466-0077x264',
    'json': {
    'name': 'Scott Thomas',
    'address': '039 Rivera Shore\nWest Shannonstad, ID 53103',
},
    'key2064': 'value73983',
    'key20947': 'value462',
    'key18076': 'value51229',
    'key31111': 'value74033',
    'key48744': 'value32182',
    'key53499': 'value30705',
},
    {
    'id': 17527489765863,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Sara Roach',
    'address': '996 Philip Common Apt. 139\nNew Rachel, TX 17007',
    'text': 'Stock in yet save. Nearly every population project kind. Because task process space.\nThing interview form detail first town front see. Staff oil leader easy indicate.',
    'email': 'dorothy42@example.org',
    'phone_number': '+1-209-605-1398x25973',
    'json': {
    'name': 'Robert Vazquez',
    'address': '92580 Reynolds Lights Suite 233\nKochburgh, GU 93725',
},
    'key25869': 'value89504',
    'key45839': 'value79270',
    'key92996': 'value87795',
    'key62344': 'value32539',
    'key1406': 'value47202',
    'key42137': 'value31273',
    'key60371': 'value53492',
    'key70772': 'value60638',
},
    {
    'id': 17527489765874,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Amanda Evans',
    'address': '53233 Bond Walk\nGregoryland, MP 71135',
    'text': 'Tree feeling buy central fast medical. Today ability music seat among occur tough.\nClearly show decide individual argue lot. Others manage over early rich prepare. Price eight reason various.',
    'email': 'savagejason@example.org',
    'phone_number': '234.332.9108x36494',
    'json': {
    'name': 'Travis Sanchez',
    'address': '7133 Stephens Land\nRichardshire, WV 71307',
},
    'key35187': 'value76284',
    'key27596': 'value79302',
    'key54582': 'value61631',
},
    {
    'id': 17527489765886,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Kyle Becker',
    'address': '8682 Frank Mountains\nLake Lorichester, OR 71506',
    'text': 'Set push worry wait natural. Instead newspaper billion. Of fight yet list land.\nProvide federal realize foot resource hold science. Form feeling same heavy impact.',
    'email': 'john88@example.net',
    'phone_number': '001-252-479-1397x7326',
    'json': {
    'name': 'Ashley Sherman',
    'address': '3710 Rhodes Valleys\nBakermouth, CT 46150',
},
    'key86544': 'value18831',
    'key71699': 'value13773',
},
    {
    'id': 17527489765897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Richard Moses',
    'address': '99765 Miller Groves\nNorth Natalie, ME 86187',
    'text': 'Majority time dinner within maybe ever hour. Million study tough produce majority high lead many. Determine choose again.',
    'email': 'sburns@example.org',
    'phone_number': '787-679-8822',
    'json': {
    'name': 'Jasmine Edwards',
    'address': '19348 Nichols Plain Apt. 620\nConniemouth, FL 53765',
},
    'key96611': 'value18106',
},
    {
    'id': 17527489765907,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Nicholas Martinez',
    'address': '238 Luna Ports\nPort Jameschester, AR 08746',
    'text': 'Reveal shoulder three not age audience. Purpose rule market stage raise. Point charge knowledge see level.',
    'email': 'rjackson@example.org',
    'phone_number': '(962)430-0795',
    'json': {
    'name': 'Kelsey Smith',
    'address': '14219 Scott Extension Apt. 520\nSouth Mary, NY 01439',
},
    'key1001': 'value11544',
},
    {
    'id': 17527489765918,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Sonya Stephens',
    'address': '6127 Miller Bypass\nMurphymouth, RI 57463',
    'text': 'Perhaps center property turn friend art.\nCollege day news hospital.\nDeal music camera enjoy. Imagine magazine series friend.',
    'email': 'taylordavid@example.org',
    'phone_number': '(858)920-1711x2736',
    'json': {
    'name': 'Becky Young',
    'address': '8122 James Loaf Apt. 136\nPort Matthewport, TX 52677',
},
    'key68616': 'value49673',
    'key90036': 'value74059',
    'key79890': 'value70149',
    'key22116': 'value78929',
},
    {
    'id': 17527489765930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mark Ellis',
    'address': '830 Derrick Hill\nEast Gina, NV 02182',
    'text': 'Agreement whose fact light allow decade. Money apply beautiful listen though thought oil.\nLaw operation personal building thank. Material reveal art health religious political.',
    'email': 'hancockjohn@example.org',
    'phone_number': '530.478.3068x488',
    'json': {
    'name': 'Penny Anderson',
    'address': '2186 Stephanie Valley\nRobertland, RI 12750',
},
    'key18747': 'value91179',
    'key68385': 'value7479',
    'key94799': 'value94599',
    'key36989': 'value21545',
    'key26634': 'value94728',
    'key60766': 'value53073',
    'key54188': 'value91881',
    'key25263': 'value39013',
    'key30447': 'value92792',
},
    {
    'id': 17527489765941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Ruben Bryant',
    'address': '2530 David Garden Suite 056\nBellport, PW 45696',
    'text': 'Million health though rather it sure. Including loss popular Congress push ten baby. Artist finally than eat wife reality.',
    'email': 'adam84@example.net',
    'phone_number': '(204)407-9999x141',
    'json': {
    'name': 'Ronnie Rivera',
    'address': '7522 Sutton Meadow\nPort Teresa, VI 68671',
},
    'key98190': 'value81888',
    'key25980': 'value15900',
    'key37546': 'value437',
    'key936': 'value99836',
},
    {
    'id': 17527489765951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Shelly Hernandez',
    'address': '923 Acosta Tunnel Apt. 858\nEmilytown, LA 31773',
    'text': 'Yet wait especially bar. Arrive start upon bar practice drive whatever.\nRoom sit economy hour technology have move now. Reveal story man. Home hold choice expect them suggest back.',
    'email': 'gonzalezsean@example.com',
    'phone_number': '(433)620-3354x14679',
    'json': {
    'name': 'Nicholas Morales',
    'address': '987 Hall Road Suite 187\nDavilaville, MN 60213',
},
    'key42201': 'value83508',
    'key93428': 'value35586',
    'key85112': 'value93344',
    'key66309': 'value97800',
    'key60351': 'value68140',
    'key71980': 'value72645',
    'key49995': 'value35311',
    'key76483': 'value96552',
    'key85805': 'value2471',
    'key90766': 'value29563',
},
    {
    'id': 17527489765964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Michael Herrera',
    'address': 'PSC 2628, Box 1718\nAPO AA 22751',
    'text': 'Record meet nor stuff. Her better look sport account dark. Strong artist lot clearly.\nEconomic spring bag.',
    'email': 'nathanbrown@example.net',
    'phone_number': '(356)309-7465x57837',
    'json': {
    'name': 'Christopher Diaz',
    'address': '8601 Blackwell Junctions Apt. 930\nLaraview, WY 47487',
},
    'key90856': 'value84146',
    'key5137': 'value96757',
    'key49176': 'value92822',
    'key53493': 'value53182',
    'key25834': 'value85106',
    'key2952': 'value85258',
    'key85982': 'value11757',
    'key15609': 'value99646',
    'key41939': 'value78616',
},
    {
    'id': 17527489765974,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Joseph Alvarez',
    'address': '9831 Foster Spurs\nWest John, SC 17789',
    'text': 'High range wear world early natural whether. Language response consider. Together focus spring machine.',
    'email': 'juliesanchez@example.com',
    'phone_number': '001-548-733-3745x912',
    'json': {
    'name': 'Matthew Francis',
    'address': '26813 Robert Burg Apt. 116\nPort Marvin, VA 90844',
},
    'key36095': 'value2032',
    'key35081': 'value61261',
    'key29925': 'value81596',
    'key72261': 'value65891',
    'key73335': 'value90713',
    'key68110': 'value41777',
},
    {
    'id': 17527489765985,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Sara Hernandez',
    'address': '3919 Perez Squares Apt. 882\nAnthonymouth, VT 66892',
    'text': 'Suddenly guy education significant drug population.\nInterview with relationship collection material participant. Order or must lose. Help can mean stop point.',
    'email': 'tracey43@example.com',
    'phone_number': '001-613-627-3229',
    'json': {
    'name': 'William Harrison',
    'address': '3366 Alexander Throughway Suite 861\nSouth Brenda, WA 39042',
},
    'key45436': 'value55507',
    'key15082': 'value10313',
    'key48128': 'value12778',
    'key43749': 'value89988',
    'key67838': 'value74618',
    'key7255': 'value43872',
    'key78440': 'value70539',
    'key45979': 'value9688',
    'key27297': 'value34875',
    'key64295': 'value2102',
},
    {
    'id': 17527489765996,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Sara Collins',
    'address': '367 Lance Throughway Apt. 778\nNorth Nicoleville, VT 71531',
    'text': 'Live someone tell. Soldier discussion claim sense about. Charge single beautiful kind.',
    'email': 'rogerstanner@example.net',
    'phone_number': '(949)545-0280x2228',
    'json': {
    'name': 'Erin Anderson',
    'address': '67112 Davis Corners\nSouth Michaelmouth, NM 49327',
},
    'key64341': 'value35090',
    'key96514': 'value35483',
    'key36767': 'value47336',
    'key99483': 'value50759',
    'key43652': 'value19273',
    'key14487': 'value59257',
},
    {
    'id': 17527489766007,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Maria Davis',
    'address': '9329 Monica Valleys Suite 860\nWolfchester, VT 66270',
    'text': 'Modern large subject everyone add identify. Story student majority up. Cover machine natural head. Down successful wife amount.',
    'email': 'ramosdaniel@example.net',
    'phone_number': '+1-895-451-0870x63868',
    'json': {
    'name': 'Jamie Taylor',
    'address': '96411 Sutton Turnpike Apt. 523\nNew Scott, MI 43192',
},
    'key68909': 'value99480',
    'key50986': 'value9849',
    'key49053': 'value59629',
    'key43692': 'value71851',
    'key57446': 'value97639',
    'key91390': 'value34082',
    'key96986': 'value47685',
    'key80011': 'value91042',
    'key69513': 'value82326',
    'key29028': 'value56338',
},
    {
    'id': 17527489766019,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Dylan Delgado',
    'address': '9171 Caleb Ranch\nEast Elizabeth, VT 29535',
    'text': 'Animal against case coach organization never set. North role church enter may attention notice area. Beat moment easy part.',
    'email': 'paulwilliams@example.org',
    'phone_number': '870.752.3064',
    'json': {
    'name': 'Andrea Brown',
    'address': 'PSC 9651, Box 4818\nAPO AA 78112',
},
    'key22717': 'value76221',
    'key60623': 'value56599',
    'key72587': 'value26382',
    'key14036': 'value90123',
    'key87388': 'value33801',
    'key30157': 'value47421',
    'key13176': 'value89779',
    'key19188': 'value48971',
    'key24849': 'value60800',
},
    {
    'id': 17527489766028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Bryan Marshall',
    'address': '45057 Ray Fords Apt. 650\nWest Sandra, MI 59493',
    'text': 'After go follow rock town. Teach guy act report modern major high.\nPolitical executive bank street. Quickly laugh leave note professor receive quality type.',
    'email': 'rhodeseric@example.com',
    'phone_number': '+1-354-767-3391',
    'json': {
    'name': 'Eric Simon',
    'address': '763 Wong Drives\nTylerport, IA 98723',
},
    'key78905': 'value60517',
},
    {
    'id': 17527489766039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Adam Gardner',
    'address': '4854 Nicole Underpass\nDeborahborough, AS 50914',
    'text': 'Form mean maybe them opportunity. Author everything southern leader father.\nThough sense book assume raise far. Never at college necessary.\nMy floor soldier. Huge break guess plant.',
    'email': 'cadkins@example.org',
    'phone_number': '561.736.3818',
    'json': {
    'name': 'Christopher Smith',
    'address': '4957 Mccormick Drive\nEricland, NC 38446',
},
    'key7539': 'value92673',
    'key74294': 'value9800',
    'key85524': 'value72051',
    'key69832': 'value68728',
    'key53873': 'value83082',
},
    {
    'id': 17527489766050,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Evelyn Garza',
    'address': '20112 Brock Forges Apt. 319\nNorth Michael, TX 07866',
    'text': 'Similar manage avoid dream game suddenly many.\nPosition watch what model. Hope whether really that each develop factor. Performance firm outside building.',
    'email': 'delgadoamanda@example.net',
    'phone_number': '369.423.4225x3968',
    'json': {
    'name': 'Dylan Schaefer',
    'address': '1869 Sherri Spring Apt. 711\nCrystalshire, WI 19191',
},
    'key70730': 'value43495',
    'key11183': 'value28688',
    'key25876': 'value5081',
    'key88570': 'value18763',
    'key99656': 'value36249',
    'key77699': 'value86461',
    'key93442': 'value41356',
    'key74982': 'value37338',
    'key9471': 'value18397',
},
    {
    'id': 17527489766062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Zachary Peters PhD',
    'address': '3085 Morgan Expressway\nRodriguezstad, WV 97975',
    'text': 'Buy spring American as almost there American. Church tough form bank. Young all despite process college including a media.',
    'email': 'laura69@example.org',
    'phone_number': '630-478-7118',
    'json': {
    'name': 'James Garner',
    'address': '60010 Robert Club\nEast Mary, NY 61317',
},
    'key59167': 'value99488',
    'key63694': 'value22340',
    'key92593': 'value87193',
    'key18331': 'value28878',
    'key12917': 'value11873',
    'key5518': 'value48125',
    'key44726': 'value49410',
},
    {
    'id': 17527489766071,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Brad Conway',
    'address': '896 Cheryl Wall\nNew Vanessaville, MD 01769',
    'text': 'Space occur deal third main author. Candidate Mr choose child mouth can investment.\nMeeting join adult truth fish. Deal energy need peace certain. On nation sister past pressure.',
    'email': 'mark89@example.org',
    'phone_number': '001-687-294-8528',
    'json': {
    'name': 'Sierra Ramsey',
    'address': '723 Franco Cape Suite 533\nPriscillatown, PR 38848',
},
    'key52800': 'value22156',
    'key88106': 'value65069',
    'key67156': 'value54536',
    'key25965': 'value9137',
    'key12309': 'value94932',
    'key76787': 'value19086',
    'key70067': 'value3539',
    'key67658': 'value80',
    'key4150': 'value4549',
},
    {
    'id': 17527489766081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Austin Jackson',
    'address': '30168 Deborah Dam\nPort Rogerberg, OH 58769',
    'text': 'Study top star degree. Often big also system surface difficult dream. Stop society activity data listen here minute.',
    'email': 'victoria10@example.com',
    'phone_number': '5228578663',
    'json': {
    'name': 'Jacqueline Ferguson',
    'address': '5455 Cordova Shoal Suite 226\nLake Erin, DE 35667',
},
    'key32131': 'value58168',
    'key88934': 'value14406',
    'key86276': 'value41060',
    'key7402': 'value6536',
    'key23800': 'value30878',
    'key97279': 'value75366',
    'key72779': 'value76142',
},
    {
    'id': 17527489766091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Samantha Howe',
    'address': '254 Christopher Field\nNorth Justinberg, MN 29923',
    'text': 'Catch something send represent truth. Determine provide order area ground.\nToday seem relationship. Painting you hit act cost. Pay manage add check.',
    'email': 'uhunter@example.com',
    'phone_number': '291.803.7474',
    'json': {
    'name': 'Bonnie Molina',
    'address': '891 Jones Lake Suite 057\nSouth Richardhaven, MI 10654',
},
    'key62127': 'value69765',
    'key48553': 'value31352',
    'key39003': 'value25264',
    'key65176': 'value79004',
    'key8155': 'value32451',
    'key36563': 'value74335',
    'key86063': 'value25069',
    'key35350': 'value76467',
    'key40810': 'value4982',
    'key16468': 'value68327',
},
    {
    'id': 17527489766102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Erin Lopez',
    'address': '726 Anderson Pike\nMartinfort, NC 99113',
    'text': 'Pm concern pattern agency according series maybe into. Factor development effect analysis its interest. Price admit able control throughout idea trade discover.',
    'email': 'valerie87@example.org',
    'phone_number': '858-270-2170',
    'json': {
    'name': 'Brian Carpenter',
    'address': '88148 Stanley Lake Suite 399\nWest Christinabury, SD 90677',
},
    'key82397': 'value94124',
    'key96398': 'value82299',
    'key55061': 'value71453',
    'key66715': 'value80154',
    'key49563': 'value78427',
    'key29511': 'value62557',
},
    {
    'id': 17527489766113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Janet Parker',
    'address': 'Unit 1280 Box 7593\nDPO AP 55947',
    'text': 'Usually war majority drug defense yourself effect. Radio conference nor industry poor moment step management. Black TV part recognize single decision statement.',
    'email': 'zhall@example.net',
    'phone_number': '001-385-411-5905x313',
    'json': {
    'name': 'Natalie Hernandez',
    'address': '4537 Thompson Via\nWest Devinshire, GU 25802',
},
    'key98619': 'value74435',
    'key24261': 'value51279',
    'key37874': 'value91589',
    'key86221': 'value65936',
    'key64919': 'value34471',
},
    {
    'id': 17527489766122,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Aaron Parker',
    'address': 'PSC 7457, Box 1380\nAPO AA 39491',
    'text': 'By stop song walk mind. Environment do often easy chair natural oil. Accept bad movie lay everything according live.',
    'email': 'cbaker@example.com',
    'phone_number': '(680)638-0947',
    'json': {
    'name': 'James Jackson',
    'address': '4202 Olson Manor\nLake Jessechester, KY 87475',
},
    'key22958': 'value84928',
    'key38868': 'value1959',
    'key81274': 'value67062',
    'key37064': 'value54561',
},
    {
    'id': 17527489766130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Kelli Oconnor',
    'address': '44107 King Fork\nBrentmouth, PR 70037',
    'text': 'Develop white next individual feeling pass relationship. Cup product media wall agree quality. Side long hold total.\nGarden so hotel far wide. Situation keep inside onto break case.',
    'email': 'julie62@example.com',
    'phone_number': '(687)810-5788x90031',
    'json': {
    'name': 'Michael Gross',
    'address': '2804 Williams Wells Apt. 888\nPort Brianside, LA 57831',
},
    'key5453': 'value48728',
},
    {
    'id': 17527489766141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Roger Sanders',
    'address': '985 Harper Rapids Apt. 274\nPort Katherinetown, CA 93001',
    'text': 'Never beyond family range recently to. City any arrive use instead idea certainly. Best suggest nature spend.\nRun truth executive know which three. Have sing worry design several.',
    'email': 'eric16@example.net',
    'phone_number': '+1-952-684-2132x8226',
    'json': {
    'name': 'Felicia Avila',
    'address': '650 Thomas Flats\nSouth Michelleside, DE 59064',
},
    'key30559': 'value96801',
    'key95347': 'value94395',
},
    {
    'id': 17527489766152,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Elizabeth Parker',
    'address': '45859 Brandi Haven Apt. 178\nNew Michaelmouth, AS 61536',
    'text': 'Present much happen trouble certain. Piece important understand voice.\nForeign former language enjoy true. Herself ground admit upon serve bit collection.',
    'email': 'jack98@example.org',
    'phone_number': '(742)658-5100',
    'json': {
    'name': 'Patty Marsh',
    'address': '2390 Bradshaw Causeway\nAnthonyberg, AS 36334',
},
    'key32991': 'value65353',
    'key48': 'value5816',
    'key16655': 'value26658',
    'key19127': 'value42750',
    'key85385': 'value73097',
    'key90804': 'value78098',
    'key67073': 'value83999',
    'key65918': 'value47473',
    'key67566': 'value55248',
},
    {
    'id': 17527489766162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Veronica Bates',
    'address': '958 Anthony Overpass\nWeaverchester, AK 39412',
    'text': 'See above though who far loss book she. Official add scene stuff stuff. Campaign appear large life according local trade.',
    'email': 'joshuarobinson@example.net',
    'phone_number': '+1-938-877-8441x266',
    'json': {
    'name': 'Nicholas Price',
    'address': '486 Reynolds Mountain\nAimeeport, OH 74148',
},
    'key14636': 'value67698',
    'key67071': 'value26817',
    'key90606': 'value96796',
    'key3801': 'value74722',
    'key206': 'value3382',
    'key4302': 'value35614',
    'key82767': 'value84692',
    'key1148': 'value62166',
},
    {
    'id': 17527489766174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Sharon Drake',
    'address': '7703 Phillips Roads Apt. 731\nWest Nancy, CO 42137',
    'text': 'Know game health however very treatment. Manage certain important against major.\nProfessional floor direction gas. At director contain investment. Song play manage wind.',
    'email': 'eddiebaker@example.com',
    'phone_number': '5077272611',
    'json': {
    'name': 'Andrea Miles',
    'address': '65242 Nathaniel Circles\nSamanthahaven, IN 72707',
},
    'key82998': 'value84490',
    'key12382': 'value42168',
    'key36134': 'value33121',
    'key10694': 'value7387',
    'key4163': 'value76365',
    'key73262': 'value42679',
    'key82164': 'value80908',
    'key96091': 'value22989',
    'key50680': 'value33179',
    'key2962': 'value66168',
},
    {
    'id': 17527489766185,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'William Nguyen',
    'address': '73977 Jacob Common Suite 305\nMurrayfurt, ME 36986',
    'text': 'Power bar article yes. Second her answer. True leader so.\nSimilar weight might law truth its air. Individual especially be watch authority administration base. Data prove heart know.',
    'email': 'johnburns@example.com',
    'phone_number': '001-484-475-9850',
    'json': {
    'name': 'Anthony Moses',
    'address': '843 Amy Glens\nJillport, TN 58226',
},
    'key1210': 'value65906',
    'key7372': 'value10403',
    'key37909': 'value28804',
    'key24195': 'value7070',
    'key84134': 'value46907',
    'key51864': 'value23209',
    'key47100': 'value14272',
    'key82255': 'value75281',
    'key76881': 'value21010',
},
    {
    'id': 17527489766199,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Angel Robinson',
    'address': '784 Barbara Club Suite 285\nNorth Christophermouth, SD 42375',
    'text': 'Pay turn institution company. Fly who name cup want because section yeah. Do fund difference.',
    'email': 'ochoagabriel@example.com',
    'phone_number': '299.547.0403',
    'json': {
    'name': 'Malik Goodwin',
    'address': '623 Alyssa Manor\nWest Samanthamouth, CT 07871',
},
    'key1606': 'value34080',
    'key79568': 'value54381',
    'key69936': 'value50441',
    'key7049': 'value80458',
    'key68353': 'value24281',
    'key27253': 'value68884',
    'key43597': 'value8174',
    'key61385': 'value8434',
},
    {
    'id': 17527489766210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Ian Morrison',
    'address': '59012 Taylor Isle Apt. 398\nNorth Barrymouth, AR 68118',
    'text': 'Question difference certain politics.\nPicture tell model everything change quite claim.\nSure child main see wife their. Only give budget. Out begin baby drug owner.',
    'email': 'amanda40@example.com',
    'phone_number': '001-600-265-2701x57002',
    'json': {
    'name': 'Scott Giles',
    'address': '79847 Caitlin Rest\nWest Wendyfort, ME 29638',
},
    'key56842': 'value12644',
    'key67338': 'value13345',
    'key79061': 'value14913',
},
    {
    'id': 17527489766221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Melissa Price',
    'address': '642 Perkins Spring Apt. 044\nWest Robertland, MI 50145',
    'text': 'Cover American answer though save wait heart. Media star fast between land. Hold minute state important our.\nSeat hot kitchen market little. Seek few behavior author garden drive.',
    'email': 'thomasdavid@example.org',
    'phone_number': '(345)330-3432',
    'json': {
    'name': 'Joshua Smith',
    'address': '16586 Cline Way\nNew Michael, GA 97487',
},
    'key9650': 'value38694',
    'key68180': 'value66517',
    'key77570': 'value53315',
    'key84558': 'value22348',
},
    {
    'id': 17527489766232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Elizabeth Freeman',
    'address': '563 Tran Mall\nWest Dalefurt, HI 94048',
    'text': 'Shake student vote dark sort truth identify. Go evidence price third movement. Marriage know see building break of head toward.\nIf method improve sell claim.',
    'email': 'zrogers@example.net',
    'phone_number': '7616617748',
    'json': {
    'name': 'John Nguyen',
    'address': '79105 Webb Cape Apt. 108\nAtkinsonshire, OR 22606',
},
    'key65995': 'value23947',
    'key20529': 'value80390',
    'key67660': 'value47930',
},
    {
    'id': 17527489766243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Katie Kirk',
    'address': '9684 Natalie Stream\nSandovalville, GU 20265',
    'text': 'Town fund Congress dark. Deep role effect policy.\nExist family interest attack police today. Eight billion current quality.',
    'email': 'garciajoseph@example.com',
    'phone_number': '570.960.3305x70958',
    'json': {
    'name': 'David Henson',
    'address': '58708 Susan Drive Suite 437\nPort Amyfurt, MH 40146',
},
    'key81785': 'value3470',
    'key47188': 'value85899',
},
    {
    'id': 17527489766255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Michael Beck',
    'address': '4442 Sanchez Viaduct\nPort Derek, PR 46230',
    'text': 'Might step ago young man hit clearly. Art speech buy they try.\nKey future firm. Despite avoid early. Impact organization say real.',
    'email': 'ilynch@example.net',
    'phone_number': '001-328-536-5060x40614',
    'json': {
    'name': 'David Roberts',
    'address': '0643 Price Extensions\nJohnsontown, DC 79146',
},
    'key43756': 'value2474',
    'key40717': 'value26136',
    'key92205': 'value67895',
    'key67864': 'value89952',
    'key94672': 'value10440',
    'key77630': 'value93006',
    'key72611': 'value50161',
    'key54464': 'value17876',
},
    {
    'id': 17527489766266,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Mr. Tyler Moore II',
    'address': '02034 Jennifer Throughway Suite 815\nNorth Janiceside, SC 54910',
    'text': 'Guy everything response record. Tonight cultural way fast. President religious major ball cause.\nChance hundred benefit knowledge. Light better rise. Full owner class star.',
    'email': 'sjackson@example.net',
    'phone_number': '(557)264-6176',
    'json': {
    'name': 'Brooke Gonzales',
    'address': '284 Ashley Path\nJuliemouth, OR 30397',
},
    'key81779': 'value45702',
    'key93676': 'value43426',
    'key62124': 'value64274',
    'key73611': 'value22313',
    'key71656': 'value57125',
    'key35278': 'value760',
},
    {
    'id': 17527489766277,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michael Lyons',
    'address': 'Unit 9112 Box 0274\nDPO AA 90180',
    'text': 'Protect way lay morning wear scientist instead. Billion power successful avoid.',
    'email': 'johndiaz@example.org',
    'phone_number': '+1-697-648-8032x322',
    'json': {
    'name': 'Karen Mcbride',
    'address': '846 Daniel Squares\nLopezberg, OK 29617',
},
    'key4805': 'value44273',
    'key56083': 'value44344',
    'key36536': 'value13953',
    'key43051': 'value966',
},
    {
    'id': 17527489766286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Cesar Williams MD',
    'address': '97106 Michael Village Suite 511\nNew Sarahburgh, WV 42010',
    'text': 'Nice character once officer the final who one. Prove wish PM admit ok mention.\nBut rich free every manager practice will.',
    'email': 'amysuarez@example.net',
    'phone_number': '427.753.3019',
    'json': {
    'name': 'Dustin Cardenas',
    'address': '8259 Michael Creek\nHunterstad, MT 65795',
},
    'key16962': 'value8075',
},
    {
    'id': 17527489766297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Mark Martin',
    'address': '66963 Holt Lakes\nSouth Brentmouth, CA 54512',
    'text': 'News seem key process edge. Into affect suffer somebody read skill focus worker.\nTurn teach wind. Serve section leader under past language environment. Education weight feel.',
    'email': 'john62@example.org',
    'phone_number': '447-261-8933x99538',
    'json': {
    'name': 'Christian Davidson',
    'address': '1335 Williams Point\nBradleyburgh, CO 32647',
},
    'key55827': 'value97811',
    'key94231': 'value38460',
    'key10411': 'value35342',
    'key16922': 'value41648',
},
    {
    'id': 17527489766307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Philip Ford',
    'address': '23983 Dawn Burg Suite 042\nJeffreyland, DC 15185',
    'text': 'Sit business space resource would model. Same system alone company fly.\nOperation such become you. Size nation social dark. Study their old form PM you challenge.',
    'email': 'timothysmith@example.net',
    'phone_number': '(656)639-5222x54760',
    'json': {
    'name': 'Marie Mora',
    'address': '349 Jennifer Coves\nEast Timothymouth, MS 49568',
},
    'key11262': 'value47268',
    'key24837': 'value86022',
    'key37048': 'value77573',
    'key42957': 'value87148',
    'key70340': 'value78678',
},
    {
    'id': 17527489766320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Dr. Julie Spears MD',
    'address': '327 Danny Crossroad\nWest Justin, WV 26752',
    'text': 'Deep career letter to physical. Girl administration consumer few use. Talk close head whom design like military well.\nArt live everyone senior. Official save baby effect play area. Order create meet.',
    'email': 'pcasey@example.com',
    'phone_number': '001-928-762-4846x01813',
    'json': {
    'name': 'Tanya Stewart',
    'address': '01914 Robinson Shoals\nDavismouth, MT 69452',
},
    'key33182': 'value430',
    'key84965': 'value38602',
    'key13185': 'value65196',
    'key5667': 'value96029',
    'key25858': 'value31664',
    'key89527': 'value5114',
    'key27745': 'value7497',
    'key49052': 'value90304',
    'key38302': 'value58434',
    'key6306': 'value81331',
},
    {
    'id': 17527489766334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Christopher Velez MD',
    'address': '409 Larry Inlet Apt. 302\nFinleyhaven, KY 90896',
    'text': 'Focus draw modern senior you than deal agent. Culture rest none in.\nTheir weight social because skin development. Least me final situation.',
    'email': 'shane96@example.org',
    'phone_number': '241-913-2818x5841',
    'json': {
    'name': 'Marisa Wilson',
    'address': '093 John Grove Suite 151\nHudsonville, MS 31077',
},
    'key9729': 'value13911',
},
    {
    'id': 17527489766347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Sarah Coffey',
    'address': '2422 Black Islands\nLake Kathleenton, CT 47502',
    'text': 'Available glass little response former meet. Suddenly official group artist.',
    'email': 'micheal87@example.net',
    'phone_number': '9273499838',
    'json': {
    'name': 'Sabrina Copeland',
    'address': '498 Reyes Extension\nRamirezland, KY 94979',
},
    'key61810': 'value62514',
    'key39958': 'value63697',
    'key31534': 'value37012',
},
    {
    'id': 17527489766360,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Joseph Freeman',
    'address': '260 Samantha Oval Apt. 105\nLoriburgh, RI 25216',
    'text': 'Wife kitchen report film clearly. Region around note card goal relate.\nWear most mean police as seven. Develop serious attorney attack her role.',
    'email': 'deannaharrington@example.net',
    'phone_number': '(773)958-5662x698',
    'json': {
    'name': 'Larry Walker',
    'address': '296 Garrison Pass\nDanielleberg, PA 01875',
},
    'key36996': 'value10981',
    'key75705': 'value62479',
    'key98853': 'value31245',
    'key59328': 'value65914',
    'key66678': 'value1723',
    'key59223': 'value44050',
    'key51218': 'value14715',
    'key52733': 'value43105',
    'key98375': 'value61016',
    'key57165': 'value77449',
},
    {
    'id': 17527489766373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Teresa Little',
    'address': '474 Wells Villages Suite 780\nLake Mary, CA 20411',
    'text': 'Recently treatment test century not system head. Job nation ability everybody good throw debate.',
    'email': 'tiffany08@example.net',
    'phone_number': '+1-533-776-2902x040',
    'json': {
    'name': 'Cheryl Hamilton',
    'address': '43245 Garrison Wells Apt. 368\nLake Derrick, PW 20632',
},
    'key54429': 'value23907',
    'key2099': 'value66953',
    'key45013': 'value68258',
    'key45716': 'value75981',
    'key26194': 'value8479',
    'key87522': 'value56348',
},
    {
    'id': 17527489766386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Cynthia Smith',
    'address': '594 Jason Knolls Apt. 466\nWest Johnborough, OH 20288',
    'text': 'Let thing approach stuff notice here stage management. Hope certainly usually per memory husband tree country. Decide most minute call important join Mrs experience.',
    'email': 'shirleygraham@example.com',
    'phone_number': '+1-862-830-1045x8525',
    'json': {
    'name': 'Scott King',
    'address': '3176 Sonya Harbors\nPort Edwardland, AR 24025',
},
    'key54302': 'value16775',
    'key59805': 'value68139',
    'key97651': 'value73561',
    'key80917': 'value12182',
},
    {
    'id': 17527489766400,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jessica Gray',
    'address': '4531 Kathleen Stream Suite 766\nWest Maryborough, MP 82874',
    'text': 'Practice guess after us role. Cell team daughter customer new size.\nEnvironment member receive represent player common them protect. Road because four drop.',
    'email': 'lewisjames@example.net',
    'phone_number': '243-867-9443x2863',
    'json': {
    'name': 'David Coleman',
    'address': '8433 Jerry Loaf\nByrdport, ME 48652',
},
    'key20576': 'value81536',
    'key4373': 'value20376',
    'key42759': 'value12745',
},
    {
    'id': 17527489766412,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Shelly Landry',
    'address': '19461 Adam Landing\nElizabethview, KS 12205',
    'text': 'Manage policy together yes suffer message job. Power collection action into. Occur property nor.',
    'email': 'michael52@example.net',
    'phone_number': '001-358-436-4017x19241',
    'json': {
    'name': 'Joseph Villa',
    'address': 'Unit 6382 Box 6695\nDPO AE 84317',
},
    'key67739': 'value17721',
    'key62516': 'value93029',
    'key35004': 'value31019',
    'key70964': 'value89317',
    'key30609': 'value19504',
    'key98027': 'value18825',
    'key15574': 'value12861',
},
    {
    'id': 17527489766421,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Joseph Mccoy',
    'address': '00038 Carrie Views\nPort Lindahaven, PW 25395',
    'text': 'They such let already well. Sign call sound bank ten.\nApproach environmental them improve poor charge responsibility use. Natural free until capital.',
    'email': 'lisadecker@example.net',
    'phone_number': '217-372-8076',
    'json': {
    'name': 'Robert Lucero',
    'address': '5020 Mary Manors\nEast Deanhaven, TN 96788',
},
    'key6731': 'value55192',
    'key36501': 'value11055',
    'key93935': 'value72937',
},
    {
    'id': 17527489766431,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Teresa Fletcher',
    'address': '160 Sonya Orchard Apt. 866\nSmithhaven, GU 54562',
    'text': 'Different list season civil character couple. Among push rise discover.\nReal keep Mr picture. We huge mind wife. Whether still walk hit turn.',
    'email': 'mhill@example.org',
    'phone_number': '001-549-815-3663',
    'json': {
    'name': 'Richard Sanchez',
    'address': '81974 Evans Crescent Apt. 546\nMicheletown, IA 53413',
},
    'key75626': 'value62744',
},
    {
    'id': 17527489766442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Jade Wu',
    'address': '78764 Sara Estates\nNew Claireside, HI 50737',
    'text': 'Despite add fly physical. Military including care song speech difficult natural. Already carry explain only together beautiful knowledge.',
    'email': 'jtrujillo@example.org',
    'phone_number': '342-552-8258x663',
    'json': {
    'name': 'Lisa Henderson',
    'address': '78543 Johnson Mountains Apt. 418\nDouglasside, MO 34661',
},
    'key18769': 'value95119',
    'key21960': 'value786',
},
    {
    'id': 17527489766452,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Ronald Hernandez',
    'address': '00201 Robinson Highway\nNew Kenneth, MH 51768',
    'text': 'Should box road gas. Prove last wide. Senior current center necessary push service billion economy.\nBetween theory top total. Provide mouth all score.',
    'email': 'susan96@example.org',
    'phone_number': '+1-526-997-1408x15533',
    'json': {
    'name': 'Julia Moore',
    'address': '98851 Samantha Ways\nNorth Johnchester, VT 78572',
},
    'key69197': 'value84108',
    'key86948': 'value85020',
},
    {
    'id': 17527489766462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Michael Spencer',
    'address': '4114 Sandra Park Apt. 932\nWest Suefort, NE 59862',
    'text': 'Later instead kitchen win occur. Because call sort represent draw interesting describe draw.',
    'email': 'ggonzalez@example.net',
    'phone_number': '625.939.5141',
    'json': {
    'name': 'Mary Williams',
    'address': '45290 Pamela Loaf Apt. 422\nEast Elizabeth, KS 86741',
},
    'key68696': 'value46328',
    'key48925': 'value30137',
    'key59181': 'value2740',
    'key23613': 'value36914',
    'key41951': 'value34191',
    'key23044': 'value58947',
},
    {
    'id': 17527489766472,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Christopher Roach',
    'address': '28010 Martinez Freeway Apt. 841\nLake Amy, VI 88402',
    'text': 'Young movie fact sign speak a. Sense type full mission.\nCouple picture cut defense. General adult network oil thousand. Skill purpose ground we him let view still.',
    'email': 'droberts@example.net',
    'phone_number': '552.859.6267x56190',
    'json': {
    'name': 'Denise Hunter',
    'address': '1277 Travis Prairie\nJohnsonborough, MN 76094',
},
    'key72297': 'value67806',
    'key75271': 'value35082',
    'key77794': 'value61794',
},
    {
    'id': 17527489766483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Danielle Lewis',
    'address': '575 Goodwin Mills\nKlineville, MA 26171',
    'text': 'Day themselves thought. Station argue involve.',
    'email': 'ohicks@example.com',
    'phone_number': '761.576.0603x3753',
    'json': {
    'name': 'Lisa Montgomery',
    'address': '4873 Bernard Wells Apt. 484\nJimenezmouth, NH 71327',
},
    'key24798': 'value67162',
    'key65387': 'value64185',
    'key1012': 'value14148',
    'key60585': 'value58782',
    'key31226': 'value7848',
    'key64199': 'value82273',
    'key56062': 'value43634',
    'key85885': 'value9063',
    'key14687': 'value68571',
    'key98513': 'value2698',
},
    {
    'id': 17527489766494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Danny Lin',
    'address': '18675 Christian Bridge\nNorth Donna, IA 35037',
    'text': 'Agree test response. Gun mother decision measure word. That including record safe. With low factor anything sort gas market.\nOn break through surface charge charge. Heart return land here.',
    'email': 'alisha23@example.net',
    'phone_number': '(504)893-9896',
    'json': {
    'name': 'Dominique Wolf',
    'address': '654 King Squares\nBenjaminbury, MI 30541',
},
    'key67440': 'value610',
    'key34563': 'value14079',
    'key60477': 'value90257',
    'key13943': 'value40934',
    'key73655': 'value21116',
},
    {
    'id': 17527489766504,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Alice Heath',
    'address': '2664 Ramirez Passage\nGillespieshire, GA 14992',
    'text': 'Since mention gun seat girl task there. While mouth stuff Mrs different professor develop.\nAudience rich state tend idea join. Age career way mission wide down. Wish sea structure.',
    'email': 'chavezbeverly@example.net',
    'phone_number': '(702)430-2324x986',
    'json': {
    'name': 'Christine Jones',
    'address': '306 Zachary Skyway Apt. 938\nEast Jennifer, IL 92861',
},
    'key19409': 'value82858',
    'key40677': 'value11725',
    'key78915': 'value99709',
    'key47016': 'value26124',
    'key65909': 'value76367',
    'key52980': 'value85305',
},
    {
    'id': 17527489766515,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Nichole Smith',
    'address': '9969 Simpson Radial\nEast Laurenhaven, HI 06632',
    'text': 'Behavior sign theory opportunity sure blue character defense. Whose standard series. Half machine until almost next get difficult.\nThose recently action different. Collection I civil choose.',
    'email': 'garciadeborah@example.org',
    'phone_number': '(891)494-0998x583',
    'json': {
    'name': 'Edward Doyle',
    'address': '089 Mcknight Burgs\nLake Christopher, CT 62222',
},
    'key25149': 'value69507',
    'key42977': 'value73198',
    'key28192': 'value41260',
    'key95976': 'value40542',
    'key56682': 'value72355',
},
    {
    'id': 17527489766527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Susan Hernandez',
    'address': '56253 Kelly Stream Suite 332\nPort Kelly, SC 71310',
    'text': 'She story reflect American else. Low last generation miss stay call.\nPush direction attention still. Under reach us section pattern crime.',
    'email': 'sloancheryl@example.org',
    'phone_number': '759.540.3342',
    'json': {
    'name': 'Ryan Chambers',
    'address': '150 Lynn Throughway\nLake Randymouth, CO 66605',
},
    'key58559': 'value69938',
},
    {
    'id': 17527489766538,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Mikayla Fernandez',
    'address': '740 Jodi Expressway Apt. 316\nSouth Randybury, VA 21887',
    'text': 'West expert drive exist seat. Election traditional job old show soldier see responsibility. Movie six admit management job case whose response.',
    'email': 'ewatson@example.com',
    'phone_number': '708-984-0339x422',
    'json': {
    'name': 'Kristopher Reed',
    'address': '42983 Wood Oval Suite 551\nSouth Kyle, MT 32262',
},
    'key62700': 'value42705',
    'key4907': 'value26590',
    'key25699': 'value35733',
    'key15703': 'value12895',
    'key17270': 'value58305',
    'key2482': 'value69921',
    'key96662': 'value61065',
    'key38914': 'value78787',
    'key23397': 'value17493',
    'key75737': 'value24203',
},
    {
    'id': 17527489766549,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Melody Irwin',
    'address': 'USS Maldonado\nFPO AA 98226',
    'text': 'Cold meeting response player past you. Character two part political old call base. Argue although sport up table while.',
    'email': 'mhill@example.org',
    'phone_number': '(596)256-1351',
    'json': {
    'name': 'Thomas Watts',
    'address': 'Unit 7155 Box 4261\nDPO AA 05941',
},
    'key89122': 'value52191',
    'key61775': 'value98263',
},
    {
    'id': 17527489766556,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Andrea Kelley',
    'address': '63281 Shaw Path Suite 994\nKennedyfort, SD 77661',
    'text': 'Opportunity similar structure within. Watch let early Mr school enjoy teach. Artist involve new finish peace call what happy.\nFact effect share represent put short.',
    'email': 'petersongregory@example.net',
    'phone_number': '503.367.1259x304',
    'json': {
    'name': 'Casey Watkins',
    'address': '501 Howard Station Apt. 393\nNew Amandatown, OK 19775',
},
    'key93956': 'value81003',
    'key73952': 'value87050',
    'key27619': 'value41865',
    'key42338': 'value7955',
    'key64969': 'value53251',
    'key83222': 'value37104',
    'key19067': 'value7447',
    'key70308': 'value70686',
    'key13469': 'value22679',
},
    {
    'id': 17527489766568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Jenny Velasquez',
    'address': '47109 Silva Junction\nTaylorview, MH 19745',
    'text': 'Fish nice heavy take never play include. Course always near lot writer apply they.\nChallenge tell yard suggest sit. Listen film reflect build particular we own. Need no true material reason.',
    'email': 'john54@example.com',
    'phone_number': '7833785554',
    'json': {
    'name': 'William Hernandez',
    'address': '159 Smith Burgs Apt. 561\nHendersonstad, GU 02982',
},
    'key52246': 'value89383',
    'key17562': 'value9087',
    'key4491': 'value4822',
    'key52702': 'value47108',
    'key46470': 'value97164',
    'key67868': 'value72960',
    'key48713': 'value99708',
    'key57128': 'value99756',
    'key21573': 'value3394',
},
    {
    'id': 17527489766579,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Cynthia King',
    'address': '63472 Payne Stravenue Apt. 526\nEast Mary, MH 73195',
    'text': 'Draw land how environmental. Color yourself activity wish money.\nNext help guess relationship soon. Sometimes long usually cause against point.',
    'email': 'hursttravis@example.org',
    'phone_number': '(751)870-7361x56712',
    'json': {
    'name': 'Logan Barnes',
    'address': '8543 Wright Well\nAllenport, NM 74955',
},
    'key68911': 'value3147',
},
    {
    'id': 17527489766591,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Jeffrey Johnson',
    'address': '108 Jennifer Way\nDeanview, LA 27479',
    'text': 'Space direction attack tonight. Knowledge tax western second instead poor read. Away summer east leg partner.\nJust memory certain would free. Owner science last service adult.',
    'email': 'mwallace@example.net',
    'phone_number': '656.470.7328x313',
    'json': {
    'name': 'Joseph Williams',
    'address': '9505 Patricia Way\nPort Traviston, LA 05186',
},
    'key59695': 'value6688',
},
    {
    'id': 17527489766602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Brad Vang',
    'address': '48111 Lawrence Ranch\nNorth Dale, NY 71377',
    'text': 'Listen well community start. Movement fill remain anyone either seek authority. Amount much mind whether student. Make ahead relationship analysis garden box.\nClass get language stuff.',
    'email': 'cathydavis@example.org',
    'phone_number': '(713)984-2253',
    'json': {
    'name': 'Mrs. Chelsea James',
    'address': '300 Robertson Green\nWest Cathy, GA 67407',
},
    'key38455': 'value23783',
    'key51885': 'value44533',
    'key92869': 'value73446',
    'key82762': 'value93313',
    'key31012': 'value77625',
    'key49834': 'value62949',
    'key85328': 'value70687',
    'key43345': 'value52666',
},
    {
    'id': 17527489766613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Wendy Brewer',
    'address': '9399 Christina Turnpike Apt. 612\nNorth Michael, MA 11533',
    'text': 'Wait sometimes lead place. Property agreement expect model system remember area. Movie person whole customer in. General law hot likely increase measure ask collection.',
    'email': 'cthomas@example.net',
    'phone_number': '567-538-9248',
    'json': {
    'name': 'James Campbell',
    'address': '37826 David Brook Apt. 763\nWest Daniel, PR 45022',
},
    'key5125': 'value59861',
    'key14428': 'value77473',
    'key81737': 'value2748',
    'key75835': 'value98125',
    'key80854': 'value30849',
},
    {
    'id': 17527489766624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Troy Cantrell',
    'address': '17879 Gonzales Manors\nBernardton, TX 03481',
    'text': 'Treatment moment consumer company. Right leader job ball business deal. Remember today floor able whom whatever.\nReach likely include resource. Teach space travel hope.',
    'email': 'nfields@example.org',
    'phone_number': '494.739.3997',
    'json': {
    'name': 'Adam Carter',
    'address': '1190 King Branch Suite 278\nNew Mia, PA 33042',
},
    'key95997': 'value73825',
    'key6126': 'value57911',
    'key48975': 'value58983',
    'key11585': 'value45055',
    'key86271': 'value56506',
    'key17159': 'value4371',
},
    {
    'id': 17527489766635,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Ronald Medina',
    'address': '6012 Green Overpass\nWest Alexis, MA 38723',
    'text': 'Science character about hospital. Long pattern picture stop standard.\nLast avoid newspaper exist rather. Play ability civil marriage drive per.\nPerform once teacher born agency include.',
    'email': 'lorihammond@example.net',
    'phone_number': '(825)402-6335',
    'json': {
    'name': 'Zachary Nichols',
    'address': '53448 Timothy Stravenue Suite 852\nPort Jonathanport, DC 78125',
},
    'key88568': 'value97554',
    'key60099': 'value85548',
    'key9176': 'value78422',
    'key35932': 'value1806',
    'key80309': 'value95167',
},
    {
    'id': 17527489766646,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Emily Ramirez',
    'address': '44168 Gibson Islands\nBuchananland, TN 36317',
    'text': 'Sister recently probably evening. Loss president eat community.',
    'email': 'martinezjill@example.org',
    'phone_number': '855.467.6666x8281',
    'json': {
    'name': 'Duane Spencer',
    'address': 'PSC 1947, Box 4865\nAPO AP 47645',
},
    'key55571': 'value94076',
    'key32360': 'value40709',
    'key34192': 'value52310',
    'key3078': 'value76463',
    'key41167': 'value95378',
    'key40658': 'value79052',
},
    {
    'id': 17527489766656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Ronald Jones',
    'address': '086 Dale Mills\nNew Geoffreyton, UT 33685',
    'text': 'Story answer tend seat sort. Should win information country able page. Fly prove five town not that.',
    'email': 'kathryn17@example.com',
    'phone_number': '+1-864-475-5096x448',
    'json': {
    'name': 'Christopher Hunt',
    'address': '540 Watkins Locks Suite 441\nNorth Geneport, FM 29273',
},
    'key64299': 'value85984',
    'key59245': 'value26272',
    'key40392': 'value78763',
    'key46957': 'value3959',
    'key90681': 'value18639',
    'key9272': 'value1501',
    'key93860': 'value70621',
},
    {
    'id': 17527489766666,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Paul Ruiz',
    'address': '21438 Molina Ridges\nPort Andrewton, AZ 68231',
    'text': 'None area bag check they. Quickly hour mind because include heart report travel. Various majority audience bag.\nSoldier near either education. Check sign sound remain meeting.',
    'email': 'fstrickland@example.org',
    'phone_number': '315-325-5297x86768',
    'json': {
    'name': 'Alexander Perez',
    'address': '1513 Howard Divide Apt. 208\nBoydmouth, CT 56394',
},
    'key29282': 'value34752',
    'key83713': 'value69850',
    'key63646': 'value49397',
    'key29342': 'value68170',
    'key46180': 'value88368',
    'key42565': 'value9479',
    'key11414': 'value76022',
    'key3705': 'value57510',
    'key76446': 'value49246',
},
    {
    'id': 17527489766677,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Matthew Mccoy',
    'address': '8847 Romero Haven Apt. 510\nEast Lorimouth, NH 19741',
    'text': 'Pretty local enter letter. Or among group always people difference.\nThreat bad past quite. Another miss science total candidate.\nOthers once floor public cell here. Hour talk expert loss.',
    'email': 'zcummings@example.com',
    'phone_number': '+1-847-879-9275x35090',
    'json': {
    'name': 'Francis Herrera',
    'address': 'PSC 5532, Box 5119\nAPO AP 69655',
},
    'key94082': 'value59953',
    'key25658': 'value91100',
    'key60163': 'value21129',
},
    {
    'id': 17527489766687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Joel Lopez',
    'address': '5439 Gregory Haven\nBellshire, KY 38020',
    'text': 'House subject oil answer success best during place. Kind look benefit admit major senior government. Floor change none seem building discover.',
    'email': 'molly56@example.org',
    'phone_number': '379.894.2156x5183',
    'json': {
    'name': 'Linda Ramirez',
    'address': 'PSC 2357, Box 5215\nAPO AA 98288',
},
    'key53159': 'value46244',
    'key685': 'value18919',
    'key54719': 'value34278',
    'key88771': 'value79133',
    'key92892': 'value28879',
    'key47388': 'value64939',
},
    {
    'id': 17527489766695,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Christy Lawson',
    'address': '3077 Frank Corner\nThomasmouth, TX 01678',
    'text': 'Member any purpose everything seek. Finish until thank can role.\nCertainly fact fact act time.\nUnder if building care young. Run success lot beat machine environmental read.',
    'email': 'oashley@example.org',
    'phone_number': '652-720-9593',
    'json': {
    'name': 'Jessica Smith',
    'address': 'PSC 0998, Box 9299\nAPO AP 85319',
},
    'key38819': 'value30865',
    'key69762': 'value11169',
    'key90045': 'value11097',
    'key19012': 'value29252',
    'key16072': 'value78504',
    'key3401': 'value2240',
    'key95129': 'value73353',
    'key60660': 'value62086',
},
    {
    'id': 17527489766704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Joseph Miller',
    'address': '25268 Farrell Ports\nSouth Anthonymouth, NH 12259',
    'text': 'Information act inside reach. Car stand then.\nDrug about any. Thank mission nice newspaper class.',
    'email': 'megan42@example.net',
    'phone_number': '685-835-6676x2730',
    'json': {
    'name': 'Kayla Wright',
    'address': '8551 Daniels Vista\nPort Jonathan, AR 37448',
},
    'key3165': 'value47499',
    'key30113': 'value71830',
    'key481': 'value65982',
    'key46312': 'value38945',
    'key91638': 'value87772',
    'key8329': 'value56113',
},
    {
    'id': 17527489766714,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Katelyn Garrett',
    'address': '86883 Robyn Coves\nNew Shannon, ND 53282',
    'text': 'Her rich market interest yeah more. First form after eight on.',
    'email': 'haynesgregg@example.com',
    'phone_number': '833-338-9287',
    'json': {
    'name': 'Christine Garcia',
    'address': '6922 Williams Route\nWilliamfort, DE 95180',
},
    'key95064': 'value88476',
    'key26154': 'value40440',
    'key21860': 'value78333',
    'key33851': 'value94140',
    'key16498': 'value29837',
    'key30391': 'value42995',
    'key94421': 'value75676',
    'key16274': 'value33461',
    'key71155': 'value43760',
    'key77948': 'value44316',
},
    {
    'id': 17527489766725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Katherine Jones',
    'address': '22683 Flores Burg Apt. 592\nSouth Johnview, IA 56037',
    'text': 'Assume bank bad difference western. House material teach ago out amount. Remain act page reveal deep.\nMarriage almost first herself. Operation too already tax so if.',
    'email': 'caitlin88@example.org',
    'phone_number': '+1-545-931-2006x2286',
    'json': {
    'name': 'Danny Mullins',
    'address': '66681 Randolph Mall Suite 122\nEast Donna, NE 52858',
},
    'key60270': 'value18459',
    'key66927': 'value72508',
    'key35225': 'value69225',
},
    {
    'id': 17527489766736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Charles Day',
    'address': '43428 Smith Creek\nNorth Robert, NE 13959',
    'text': 'Main last of system certainly magazine book. Guy growth stay matter movie country. Make way student machine follow. Order maybe suddenly security continue class at theory.',
    'email': 'stephenbuchanan@example.net',
    'phone_number': '436.326.3576x478',
    'json': {
    'name': 'Lauren Mack',
    'address': '45535 Nelson Overpass\nDonaldview, KS 12827',
},
    'key19230': 'value5288',
    'key71732': 'value11433',
    'key9466': 'value92463',
    'key60729': 'value95242',
},
    {
    'id': 17527489766748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Victoria Clements',
    'address': '605 Brittany Glens\nChristinatown, MN 11669',
    'text': 'Center region school. Side success remain prevent national structure agency market. Life cultural television total position father.\nUse whether town carry word practice. Clear financial civil loss.',
    'email': 'barnold@example.com',
    'phone_number': '758.822.3775x85226',
    'json': {
    'name': 'Sierra Wall',
    'address': '9951 Lambert Harbor Suite 556\nLake Katherine, ND 83198',
},
    'key89947': 'value43275',
    'key40932': 'value74239',
    'key77971': 'value20059',
    'key34041': 'value18114',
},
    {
    'id': 17527489766758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'John Bowman',
    'address': '606 Alexis Harbor Apt. 494\nLake Cody, AK 33805',
    'text': 'Level point foot fight outside. Thus lot fear commercial measure good voice arm.',
    'email': 'snyderanthony@example.org',
    'phone_number': '(434)466-8743x16217',
    'json': {
    'name': 'Alexander Kaiser',
    'address': '85596 Chavez Summit Suite 484\nPowellmouth, OR 25449',
},
    'key15035': 'value65590',
},
    {
    'id': 17527489766769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Cassandra Mooney',
    'address': '1873 Collins Forges\nLake Melissa, MA 41095',
    'text': 'Me note senior country. Avoid back you majority base hand.',
    'email': 'robert46@example.org',
    'phone_number': '856.298.0465',
    'json': {
    'name': 'Courtney Walker',
    'address': 'PSC 6939, Box 1273\nAPO AE 30099',
},
    'key18755': 'value53280',
    'key42964': 'value87181',
    'key46008': 'value48421',
},
    {
    'id': 17527489766778,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Joseph Brown',
    'address': 'Unit 6996 Box 1186\nDPO AA 75983',
    'text': 'With be hard decade movement.\nFather man citizen today six. Notice back guess doctor tonight explain where.',
    'email': 'evan75@example.com',
    'phone_number': '(566)977-8087x2337',
    'json': {
    'name': 'Danielle Stevens',
    'address': '876 Barbara Club\nEast Nicholas, NH 66767',
},
    'key58696': 'value65588',
    'key63264': 'value14836',
    'key26948': 'value97557',
    'key84322': 'value52698',
    'key1376': 'value48585',
    'key70675': 'value24747',
},
    {
    'id': 17527489766786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Corey Clements',
    'address': '62495 Bennett Courts Apt. 309\nSouth Catherinefurt, FM 23077',
    'text': 'Shake protect relationship special card room. Exactly main father dark traditional. Us bank support lead very chance find.\nExample forget court into great big relate. Agency hit they your.',
    'email': 'simmonscraig@example.net',
    'phone_number': '001-760-814-5637',
    'json': {
    'name': 'Ashley Blake',
    'address': '29399 Michael Coves\nPort Stephenstad, NY 47489',
},
    'key82581': 'value12565',
    'key92785': 'value54949',
    'key79226': 'value72426',
    'key55611': 'value34353',
    'key76897': 'value63886',
    'key24161': 'value51273',
},
    {
    'id': 17527489766797,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Ashley Hill',
    'address': '24485 Bailey Mountain Apt. 439\nMirandaborough, PR 23873',
    'text': 'Growth husband capital technology reflect certainly. Food relate treatment later down oil over watch. Remain various who outside. Under appear of develop choice decade I pull.',
    'email': 'brownlauren@example.org',
    'phone_number': '001-564-992-0938x671',
    'json': {
    'name': 'Alexander Day',
    'address': '9132 Virginia Camp Apt. 348\nLake Mark, VI 04634',
},
    'key33855': 'value60618',
    'key35929': 'value44158',
    'key59543': 'value55393',
},
    {
    'id': 17527489766809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Terry Lucero',
    'address': '81681 Adam Ranch\nMatthewhaven, NC 30208',
    'text': 'Everything success would practice. Focus live born fall out control many two. Indeed against painting.',
    'email': 'bethdecker@example.org',
    'phone_number': '2875465288',
    'json': {
    'name': 'Robin Thomas',
    'address': '9741 Matthew Village\nJamieberg, GU 38896',
},
    'key36533': 'value76887',
    'key3785': 'value9506',
},
    {
    'id': 17527489766820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Eric Smith',
    'address': '54668 Grant Shoals\nNorth Sydneyburgh, RI 30152',
    'text': 'Case low different view want seat floor impact. Opportunity agent table these sense. Available describe Mr challenge.',
    'email': 'zachary23@example.net',
    'phone_number': '001-766-580-3501',
    'json': {
    'name': 'John Young',
    'address': '19232 Small Extension Suite 028\nLake Michael, PW 39614',
},
    'key19795': 'value63369',
    'key61249': 'value98794',
},
    {
    'id': 17527489766832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Theresa Arnold',
    'address': '82863 Caitlin Courts\nEast Donaldland, VI 34000',
    'text': 'Teach art method themselves. Nor fill increase hot condition economy meeting adult.',
    'email': 'tburgess@example.com',
    'phone_number': '3889597821',
    'json': {
    'name': 'Kathleen Dillon',
    'address': '4013 Powell Canyon Suite 130\nHaleport, KS 62496',
},
    'key26651': 'value744',
    'key15362': 'value926',
    'key12994': 'value76749',
    'key51563': 'value71395',
},
    {
    'id': 17527489766843,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Robert Conner',
    'address': '013 Clark Forks\nHoodshire, KS 75984',
    'text': 'Charge talk east product according unit. Base behind information race thank. Forget business look data provide interest both.',
    'email': 'drogers@example.com',
    'phone_number': '(246)831-2494x6891',
    'json': {
    'name': 'Jason Rodriguez',
    'address': '6186 Renee Fork Apt. 655\nWest John, MS 28127',
},
    'key33206': 'value10815',
    'key68738': 'value60099',
    'key466': 'value35019',
    'key57146': 'value42168',
},
    {
    'id': 17527489766855,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Rachel Thomas',
    'address': '58087 David Stravenue\nNorth Patricia, NM 31370',
    'text': 'Move recently local. Place bank entire item couple laugh. Reveal management body entire ground white power. Then deep because month single head Congress project.',
    'email': 'ehart@example.net',
    'phone_number': '690.942.9566x7540',
    'json': {
    'name': 'Melanie Owens',
    'address': '175 Katherine Rue\nNorth Veronica, MH 41799',
},
    'key84680': 'value46133',
    'key41210': 'value9771',
    'key60639': 'value40481',
    'key80749': 'value4426',
    'key62752': 'value21564',
    'key83678': 'value29722',
    'key98818': 'value52273',
    'key52223': 'value77934',
},
    {
    'id': 17527489766867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Wayne Swanson',
    'address': '1492 Hardy Rapid\nLake Joseborough, NJ 84917',
    'text': 'Feel threat charge opportunity. Mean theory left team between.\nVisit especially already democratic mention song work. Read likely unit while him image reality.',
    'email': 'angela08@example.org',
    'phone_number': '+1-810-697-4987x94366',
    'json': {
    'name': 'Lisa Price',
    'address': '762 Steven Crest\nNorth Lynnhaven, LA 06097',
},
    'key46026': 'value62850',
    'key68996': 'value8512',
    'key48980': 'value10348',
    'key26311': 'value90959',
    'key81982': 'value60291',
    'key79012': 'value21539',
    'key46713': 'value71865',
},
    {
    'id': 17527489766878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Mrs. Tracy Matthews MD',
    'address': '205 Jones Prairie Apt. 223\nPort Brianmouth, NM 91976',
    'text': 'Test allow table. Market level behind whose law. Black film project nor sing research. Live choose others area push security.\nTreat deal discuss. Employee reduce admit add environment.',
    'email': 'laurencook@example.com',
    'phone_number': '(211)270-8780x58943',
    'json': {
    'name': 'Lauren Tucker',
    'address': 'Unit 6670 Box 4198\nDPO AE 49783',
},
    'key4821': 'value51898',
    'key30627': 'value38727',
    'key1210': 'value61295',
    'key77598': 'value28056',
    'key3994': 'value99263',
    'key4930': 'value57874',
},
    {
    'id': 17527489766889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Walter Horn',
    'address': '3601 Little Viaduct\nDonaldshire, SD 81159',
    'text': 'Show hotel require scientist. Read resource why prepare much book. Amount work on possible least upon.',
    'email': 'ibanks@example.net',
    'phone_number': '(278)978-0167x4152',
    'json': {
    'name': 'Jason Rush',
    'address': '9900 Kevin Brook\nBethview, VA 93916',
},
    'key31735': 'value3103',
    'key60521': 'value80640',
    'key25749': 'value64459',
    'key53675': 'value79466',
    'key83671': 'value12341',
    'key887': 'value93817',
    'key94368': 'value94469',
    'key56981': 'value12599',
    'key23876': 'value86904',
},
    {
    'id': 17527489766900,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Christina Moreno',
    'address': '028 Natalie Ranch\nVaughnmouth, SC 35329',
    'text': 'Once provide challenge star seem. Me know pattern full bag hit. Nature maybe quickly machine practice her.',
    'email': 'hamiltonchristopher@example.net',
    'phone_number': '(861)787-6596',
    'json': {
    'name': 'Judy Lewis',
    'address': '90982 Dorsey Overpass Suite 730\nSouth Sharon, OR 42518',
},
    'key16909': 'value90858',
    'key3351': 'value66791',
    'key49508': 'value39275',
    'key89710': 'value9469',
    'key46241': 'value29837',
    'key80344': 'value5498',
    'key19688': 'value79316',
},
    {
    'id': 17527489766912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Robert Garrison',
    'address': '49991 Keith Curve\nWilliamschester, ID 40483',
    'text': 'Finish professor safe recent. Government foreign too standard.\nWithout night admit wrong institution head. Factor deep around during mean. Executive ground tell event strong tell.',
    'email': 'johnthomas@example.com',
    'phone_number': '5136475209',
    'json': {
    'name': 'Claudia Cain',
    'address': '07542 Mary Greens\nEast Victoriatown, VT 03628',
},
    'key32469': 'value45483',
    'key44642': 'value25796',
    'key46288': 'value3862',
    'key16442': 'value34009',
    'key87217': 'value80044',
    'key74367': 'value38650',
    'key58446': 'value96506',
    'key20786': 'value35610',
    'key79636': 'value61726',
},
    {
    'id': 17527489766923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Tony Ramos',
    'address': 'Unit 4161 Box 8647\nDPO AP 19144',
    'text': 'Career without learn lot produce next. Arm budget require budget small American herself use. Police partner machine place may discussion significant.',
    'email': 'lharris@example.org',
    'phone_number': '(345)688-2227x64962',
    'json': {
    'name': 'Amanda Martinez',
    'address': '10001 Roberts Brook\nWest James, CT 14595',
},
    'key14946': 'value55564',
    'key92983': 'value97178',
    'key22767': 'value73437',
    'key30298': 'value13925',
    'key16406': 'value93664',
    'key48370': 'value62271',
    'key22351': 'value92574',
    'key79803': 'value37974',
    'key67300': 'value54266',
},
    {
    'id': 17527489766932,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Shane Taylor',
    'address': '0278 Tucker Parkways\nWest Kaitlyn, SD 80160',
    'text': 'Land individual little part success future. Mr want claim remain.\nWestern wide western agreement fear high. Threat mother mind provide show live. Serious movement lose watch.',
    'email': 'gregorygallegos@example.com',
    'phone_number': '(772)240-6085',
    'json': {
    'name': 'Jon Walker',
    'address': 'Unit 1693 Box 6932\nDPO AA 19438',
},
    'key1813': 'value93643',
    'key8943': 'value71189',
    'key39101': 'value99911',
    'key43573': 'value58150',
    'key69114': 'value15817',
    'key29348': 'value97005',
    'key96598': 'value95452',
    'key69045': 'value34603',
},
    {
    'id': 17527489766941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Monica Roach',
    'address': '808 Logan Field Apt. 553\nLorichester, SD 68357',
    'text': 'Every thing character.\nKey water national recognize above. Away glass worker myself page myself.',
    'email': 'christensendaniel@example.org',
    'phone_number': '207-293-5508',
    'json': {
    'name': 'Rebecca Berg',
    'address': '11885 Crystal Crescent Suite 982\nGardnerburgh, WY 20866',
},
    'key94586': 'value43323',
    'key60141': 'value27286',
    'key75767': 'value28072',
    'key39420': 'value48519',
},
    {
    'id': 17527489766953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Robert Mitchell',
    'address': '4177 Wolfe Knolls\nEast Timothyton, OK 02212',
    'text': 'Treat will professional provide seven myself assume. Memory product always friend. Wrong ten trip show policy.',
    'email': 'juan11@example.org',
    'phone_number': '+1-425-856-4965x503',
    'json': {
    'name': 'Jessica Ramirez',
    'address': '261 Linda Creek Apt. 329\nNorth Vincenttown, SD 76313',
},
    'key43171': 'value37392',
    'key32733': 'value89501',
    'key25747': 'value97239',
    'key45011': 'value4998',
    'key82634': 'value26572',
    'key65418': 'value72066',
    'key55594': 'value707',
    'key94684': 'value97452',
},
    {
    'id': 17527489766963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Deborah Ramos',
    'address': '98227 Bryan Fall Suite 776\nWilsonbury, AR 27503',
    'text': 'Low toward right treatment describe light national staff. Trip security language time beat able.',
    'email': 'zjohnson@example.net',
    'phone_number': '261.321.3748x8106',
    'json': {
    'name': 'Vanessa Gray',
    'address': '211 Joyce Glen Suite 252\nEast Oliviamouth, LA 88343',
},
    'key71023': 'value44229',
},
    {
    'id': 17527489766973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Sean Gomez',
    'address': '208 Cassandra Park Apt. 372\nNorth Juliechester, NM 74286',
    'text': 'Adult clearly fall because several teacher serve. Believe report we product. Rise least bag thus response bring challenge. Hit arm carry someone others ten.',
    'email': 'sbarber@example.org',
    'phone_number': '+1-299-948-9928',
    'json': {
    'name': 'Tiffany Daniel',
    'address': '5138 Ann Creek Apt. 404\nFowlerborough, FM 05939',
},
    'key95633': 'value58773',
    'key101': 'value40467',
    'key71086': 'value65762',
    'key26667': 'value47892',
    'key78450': 'value32550',
    'key93427': 'value67953',
    'key3146': 'value39560',
    'key56139': 'value3595',
    'key88911': 'value22309',
},
    {
    'id': 17527489766984,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Luis Schmitt',
    'address': '73895 Lindsey Via\nGregoryshire, GU 57472',
    'text': 'Republican skin to grow know provide rich. Government last day. Win very room art him participant.',
    'email': 'bailey40@example.com',
    'phone_number': '+1-453-743-1841',
    'json': {
    'name': 'Molly Ferguson',
    'address': '526 Luna Fork\nSouth Anthonyberg, NM 17209',
},
    'key4014': 'value42100',
    'key63232': 'value67076',
    'key97711': 'value29399',
    'key33596': 'value18811',
    'key13494': 'value46393',
    'key36518': 'value4257',
    'key19748': 'value22816',
    'key10927': 'value15995',
    'key20491': 'value81256',
},
    {
    'id': 17527489766994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Rachael Martinez',
    'address': '431 Brian Mountains\nNorth Chloe, GU 04993',
    'text': 'Enter lay treatment consider key. Degree arm within common father evidence. Want large successful woman. A why international talk night eat.',
    'email': 'drocha@example.org',
    'phone_number': '370.534.7277x2639',
    'json': {
    'name': 'Alexandria Todd',
    'address': '378 Adam Path Apt. 968\nSouth Tina, MD 88963',
},
    'key39279': 'value76580',
    'key52591': 'value65033',
    'key93692': 'value5664',
    'key83217': 'value52345',
    'key83939': 'value68193',
    'key23583': 'value71871',
    'key85386': 'value20889',
    'key78963': 'value45939',
    'key6346': 'value8360',
},
    {
    'id': 17527489767004,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Mr. Willie Levine',
    'address': '51204 Daniel Underpass\nEast Thomasland, VI 01043',
    'text': 'Heart carry meet social agree everybody. Yeah picture ten. Front now so visit arrive tree.\nAgency area challenge event fund bill what. Teacher change north point around myself.',
    'email': 'cwells@example.net',
    'phone_number': '(642)312-1433',
    'json': {
    'name': 'Maria Bryant',
    'address': '737 Cameron Glens\nContrerasfort, AZ 54194',
},
    'key86835': 'value8663',
    'key33141': 'value9347',
    'key79322': 'value83309',
    'key2758': 'value85401',
},
    {
    'id': 17527489767015,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Dominic Clark',
    'address': 'USS Soto\nFPO AE 69075',
    'text': 'Describe too budget us finish base action.\nProduct raise bank morning skin. Ten choose black event game. Each fight discussion allow best.',
    'email': 'vbaker@example.net',
    'phone_number': '+1-206-419-5159x3044',
    'json': {
    'name': 'Kevin Vincent',
    'address': '6173 Amy Lake\nSarafort, NM 07051',
},
    'key26103': 'value32075',
    'key54064': 'value79204',
    'key95490': 'value481',
},
    {
    'id': 17527489767024,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Anthony Davenport',
    'address': 'Unit 2085 Box 0490\nDPO AE 83888',
    'text': 'Question could rule collection deal for. Food let show wear free place. Cause authority memory full enough.',
    'email': 'lindseyfry@example.net',
    'phone_number': '+1-716-348-9659x07130',
    'json': {
    'name': 'Kenneth Cook',
    'address': '2083 Chavez Mall Apt. 062\nJohnville, AZ 53943',
},
    'key43843': 'value84220',
    'key30912': 'value88309',
    'key14286': 'value82568',
    'key57612': 'value78024',
    'key83393': 'value17294',
    'key77871': 'value85250',
    'key77339': 'value71425',
    'key10195': 'value30863',
    'key60780': 'value29327',
    'key62885': 'value49891',
},
    {
    'id': 17527489767033,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Courtney Munoz',
    'address': '25015 Berger Vista\nBakerhaven, AK 71213',
    'text': 'Nor quite company local election figure.\nDiscuss important determine budget rock full relationship. Lawyer relationship rather because marriage recognize.',
    'email': 'phillipwhite@example.com',
    'phone_number': '+1-424-240-2325x56296',
    'json': {
    'name': 'Ronald Mccoy',
    'address': '945 Serrano Terrace\nNew Keith, IA 66405',
},
    'key11651': 'value40100',
    'key25607': 'value17226',
    'key30496': 'value60249',
    'key74657': 'value88656',
    'key82005': 'value2984',
    'key2509': 'value36494',
    'key19105': 'value59829',
    'key31273': 'value18193',
    'key957': 'value19979',
    'key41554': 'value60907',
},
    {
    'id': 17527489767045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Sharon Newman',
    'address': '8657 Diane Skyway\nLeeside, PA 87790',
    'text': 'Either traditional his why if one. Present try use town job instead spend.\nWin wish miss camera sell talk. Determine already least long amount commercial.',
    'email': 'angela53@example.net',
    'phone_number': '236-933-9535x581',
    'json': {
    'name': 'Kim Phillips',
    'address': '907 Le Knolls Suite 952\nNorth Matthewport, PA 92852',
},
    'key63809': 'value83628',
    'key78581': 'value23132',
    'key11653': 'value69955',
    'key89481': 'value62169',
    'key60109': 'value17116',
    'key85392': 'value22125',
    'key6506': 'value33096',
    'key97236': 'value98896',
    'key81307': 'value8400',
    'key1350': 'value1596',
},
    {
    'id': 17527489767057,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Derek Patel',
    'address': '984 Jones Manors\nLeahfort, NC 77474',
    'text': 'Record technology network between leave feeling along. Magazine enough live size throughout class. Forward everyone perform with term manager.',
    'email': 'jacquelinetran@example.org',
    'phone_number': '(361)745-1927x66718',
    'json': {
    'name': 'Emily Copeland',
    'address': '6708 Smith Neck Apt. 743\nMelissashire, SC 85552',
},
    'key8968': 'value1867',
    'key97721': 'value33186',
    'key48065': 'value58781',
    'key35651': 'value74156',
    'key66643': 'value6984',
},
    {
    'id': 17527489767068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Jennifer Sullivan',
    'address': '616 Julie Estate\nJacquelinemouth, AS 38428',
    'text': 'Land able gas risk official candidate late. Less medical night high decide point coach. As mind production manager she including knowledge agree.',
    'email': 'thomassolis@example.com',
    'phone_number': '+1-307-859-7488x244',
    'json': {
    'name': 'Ashley Phillips',
    'address': 'Unit 4839 Box 5333\nDPO AE 23710',
},
    'key54952': 'value38983',
    'key2875': 'value3778',
    'key44698': 'value65618',
},
    {
    'id': 17527489767077,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Jennifer Reynolds',
    'address': '819 Woodard Vista\nEast Joshua, MN 81972',
    'text': 'Bar best high eight raise. Sort per forward nice wish center. Pattern old increase instead.',
    'email': 'shanesoto@example.org',
    'phone_number': '(545)656-0578x6176',
    'json': {
    'name': 'Christopher Wilson',
    'address': '021 Walton Green Apt. 751\nLake Valerie, MN 70719',
},
    'key23361': 'value43602',
    'key7467': 'value5204',
    'key35611': 'value85908',
    'key79290': 'value16679',
    'key46346': 'value2090',
    'key40028': 'value53592',
},
    {
    'id': 17527489767088,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Steven Nguyen',
    'address': '713 Robert Cape Apt. 352\nSwansonbury, TX 61473',
    'text': 'Mission office who specific still.\nEffect deal magazine while catch.\nMr indicate rise risk vote. Born grow cultural campaign different happy evidence approach. Hot person hot consumer.',
    'email': 'lynnjessica@example.net',
    'phone_number': '(399)956-3955x8790',
    'json': {
    'name': 'Michele Yang',
    'address': '4111 Ortega Bridge\nMeganbury, MH 02622',
},
    'key74814': 'value36059',
    'key92901': 'value35730',
    'key51350': 'value16432',
    'key73539': 'value49463',
    'key68667': 'value29819',
},
    {
    'id': 17527489767100,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Cheryl Zimmerman',
    'address': '4279 Gabriel Path Apt. 035\nPort Kristinstad, OH 85203',
    'text': 'Try benefit prevent PM. Last physical difficult range their.\nRecent fight daughter we. Night middle physical lay natural interesting.',
    'email': 'badkins@example.org',
    'phone_number': '+1-948-557-8064x9152',
    'json': {
    'name': 'David Barrett',
    'address': '0524 Munoz Ridges\nSouth Robertmouth, MH 14304',
},
    'key70193': 'value96978',
},
    {
    'id': 17527489767110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Paul Carey',
    'address': '34848 Gomez Island Suite 112\nMontgomeryhaven, NV 41993',
    'text': 'Exist learn late similar common both now. Read I week especially their card try.\nNote adult how black share old. Art war home investment. Where allow tree future democratic especially.',
    'email': 'stephaniefisher@example.org',
    'phone_number': '230-949-1370x2324',
    'json': {
    'name': 'Katherine Hunt',
    'address': 'Unit 8414 Box 5933\nDPO AE 65037',
},
    'key88825': 'value24690',
    'key96174': 'value43526',
    'key4775': 'value74249',
    'key42232': 'value4301',
    'key4952': 'value27088',
    'key17314': 'value22836',
},
    {
    'id': 17527489767121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Andre Campbell',
    'address': '30736 Rodriguez Crossing\nNew Virginiafurt, NY 32544',
    'text': 'Very experience while. Present author couple who history water. Every baby kind trip begin interest.\nNature dream close write. Natural condition world city soldier full.\nArrive help perform.',
    'email': 'ldavis@example.org',
    'phone_number': '824-790-8799x475',
    'json': {
    'name': 'Alyssa Frederick',
    'address': 'Unit 0271 Box 0023\nDPO AA 82706',
},
    'key83196': 'value55223',
    'key31194': 'value35012',
    'key94952': 'value87495',
    'key45434': 'value7781',
    'key26442': 'value78680',
    'key60214': 'value58665',
    'key76601': 'value31870',
    'key71202': 'value74432',
    'key561': 'value32034',
    'key80564': 'value55463',
},
    {
    'id': 17527489767130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Alejandro Mitchell',
    'address': '700 Elizabeth Ridge\nRoweport, AK 32181',
    'text': 'Contain cold student certainly large throw. Performance writer one eight billion join.\nGuy such religious true defense discussion political. Amount reach your ago different.',
    'email': 'elizabeth81@example.com',
    'phone_number': '+1-723-657-7200x07941',
    'json': {
    'name': 'Frederick Jones',
    'address': '73748 Melanie Estates\nWest Rita, OK 77339',
},
    'key81223': 'value34601',
    'key64984': 'value43475',
    'key69075': 'value43749',
    'key58895': 'value33241',
    'key92244': 'value83634',
    'key39595': 'value97658',
    'key61171': 'value58296',
    'key85914': 'value74798',
    'key98277': 'value28836',
},
    {
    'id': 17527489767139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Ronald Chan',
    'address': '7996 Melinda Springs\nPort Jacob, CT 38857',
    'text': 'Choice explain it politics. Three language begin agency seat Congress present.\nBudget contain crime research.',
    'email': 'parkernicholas@example.net',
    'phone_number': '+1-539-217-9989',
    'json': {
    'name': 'Angela Cline',
    'address': '0213 Salas Street\nLake Cynthia, OH 00789',
},
    'key96363': 'value23873',
    'key53940': 'value10646',
    'key64401': 'value78527',
    'key33591': 'value30643',
    'key47564': 'value4141',
},
    {
    'id': 17527489767150,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Sarah Landry',
    'address': '4209 Regina Locks\nJessicamouth, TX 61294',
    'text': 'Grow one wear could. Everybody rather program rest simple. Certain free risk one government professor power.\nMorning dinner rest. Site happen hard continue morning bit.',
    'email': 'scottphillips@example.com',
    'phone_number': '001-781-298-1312x177',
    'json': {
    'name': 'Joseph Wall',
    'address': '05618 Aguirre Burg\nLake Jeffreytown, KS 71812',
},
    'key54737': 'value79122',
    'key98175': 'value6603',
    'key23701': 'value85828',
    'key3597': 'value27756',
    'key81735': 'value12849',
    'key18961': 'value32930',
    'key2699': 'value58490',
    'key13071': 'value91279',
    'key22275': 'value55745',
    'key70870': 'value20468',
},
    {
    'id': 17527489767162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Julie Poole',
    'address': '9074 Garcia Stream Apt. 168\nNorth Keithville, HI 43026',
    'text': 'Technology eight help down with economy question. Cup vote good near character easy.\nFirst sort election opportunity for drive.',
    'email': 'elizabeth89@example.net',
    'phone_number': '202-544-5825x154',
    'json': {
    'name': 'Nicholas Love MD',
    'address': '803 Jennifer Mountain Apt. 843\nEast William, OR 90136',
},
    'key31596': 'value45166',
    'key47693': 'value29087',
    'key51847': 'value87269',
    'key36029': 'value65469',
    'key77819': 'value56885',
    'key46733': 'value65964',
    'key57085': 'value32429',
    'key68036': 'value86969',
    'key3311': 'value73551',
    'key46785': 'value6292',
},
    {
    'id': 17527489767172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Thomas Sawyer',
    'address': '271 Gibson Place Apt. 711\nHartside, AS 96066',
    'text': 'Perhaps individual ask after. Item bad loss affect.\nOnto character what ok discover its resource. You baby shoulder theory. Rich great plant news our.',
    'email': 'kirkhenry@example.net',
    'phone_number': '(554)211-5304x85257',
    'json': {
    'name': 'Tina Ortiz',
    'address': '011 Justin Groves Apt. 151\nAnthonyside, TX 79326',
},
    'key49599': 'value16162',
    'key24093': 'value17446',
    'key30178': 'value44119',
},
    {
    'id': 17527489767184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Mark Rose',
    'address': '8549 Holland Heights Apt. 895\nWest Robertport, KY 22852',
    'text': 'Campaign yard room man floor. Name true admit federal price effect.\nOut heart live sing before help. Provide at she decade at agent can.',
    'email': 'florespaula@example.org',
    'phone_number': '667.996.0876x688',
    'json': {
    'name': 'Elizabeth Atkins',
    'address': 'PSC 6709, Box 9234\nAPO AE 96400',
},
    'key25565': 'value76742',
},
    {
    'id': 17527489767194,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Jill Larson',
    'address': '5346 Bruce Gateway\nWest Georgefurt, MD 46595',
    'text': 'My good second. Together mind certain light put. Exactly easy expert.\nPicture how their bit during finish notice. Strong into evening prevent young. Question common across. Task identify test.',
    'email': 'josephmccormick@example.org',
    'phone_number': '(254)299-8973x5293',
    'json': {
    'name': 'Morgan Tucker',
    'address': '69771 Reynolds Views\nWest Tyler, NE 81963',
},
    'key73511': 'value90309',
    'key29241': 'value77118',
    'key92770': 'value85867',
    'key12537': 'value16704',
    'key90201': 'value28311',
    'key9970': 'value66436',
    'key1130': 'value596',
    'key85304': 'value87538',
    'key98071': 'value54525',
},
    {
    'id': 17527489767205,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Randall Mitchell',
    'address': 'USCGC Acosta\nFPO AE 29966',
    'text': 'Throw long than ago investment stand computer approach. Entire sound hair include fast.\nHer involve six choose color. Order agent course might theory yeah few.',
    'email': 'cdeleon@example.org',
    'phone_number': '612-309-1143x90885',
    'json': {
    'name': 'Joseph Sherman',
    'address': '5655 Kelly Turnpike\nNorth Karenmouth, PA 96109',
},
    'key85453': 'value11891',
    'key7884': 'value32560',
    'key33230': 'value91292',
    'key1811': 'value4015',
    'key85876': 'value59227',
    'key64453': 'value61423',
    'key62580': 'value109',
    'key33601': 'value96526',
},
    {
    'id': 17527489767214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Ann Bailey',
    'address': 'Unit 7148 Box 4418\nDPO AP 61561',
    'text': 'Human drop their property quite. Remember play short lead. Wife later current but.\nWay growth allow lay responsibility cause discuss. Eat officer surface science time.',
    'email': 'kayla98@example.com',
    'phone_number': '001-633-712-7362x989',
    'json': {
    'name': 'Briana Nguyen',
    'address': '60736 Tanya Way Apt. 307\nScottport, KY 28291',
},
    'key18212': 'value80295',
    'key15360': 'value26379',
},
    {
    'id': 17527489767223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Jay Walker',
    'address': '38942 John Fork\nJessicaview, MH 67425',
    'text': 'Million campaign personal discuss. Yes measure three instead drug family. Through against me middle customer. Employee his information prevent sort his tonight.',
    'email': 'julie81@example.net',
    'phone_number': '815.219.5122x268',
    'json': {
    'name': 'Kyle Cummings',
    'address': 'USCGC King\nFPO AP 92581',
},
    'key73541': 'value17479',
    'key16663': 'value86795',
},
    {
    'id': 17527489767232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Keith Anderson',
    'address': '452 Marcus Shoals\nJonesport, TN 70669',
    'text': 'If ahead hospital charge but well thought. Beat business lose interest. Rule name mention season more.',
    'email': 'justinanderson@example.org',
    'phone_number': '765-708-9999x9186',
    'json': {
    'name': 'John Howell',
    'address': '59185 Antonio Springs Apt. 067\nCruzchester, IL 06050',
},
    'key61324': 'value23038',
    'key22466': 'value68488',
    'key39569': 'value41157',
    'key59153': 'value88177',
    'key43819': 'value19443',
    'key49205': 'value24895',
    'key55552': 'value60601',
    'key51959': 'value60632',
},
    {
    'id': 17527489767243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Richard Lopez',
    'address': '5379 Joshua Rue\nWest Johnborough, DE 74163',
    'text': 'People poor role let foreign. Time item three dream yard small.\nSpring break compare like strong country. Require cultural next. Interest family capital scientist six body many. Run possible long.',
    'email': 'michelle39@example.com',
    'phone_number': '(585)740-7827x486',
    'json': {
    'name': 'Denise Bennett',
    'address': '93270 Berg Walks\nNorth Cindy, MA 38347',
},
    'key29518': 'value25207',
},
    {
    'id': 17527489767253,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Jeffrey Olson',
    'address': '77388 Swanson Junction Suite 401\nEast Kevinberg, OH 86162',
    'text': 'Trouble close argue factor why space movie. Policy box idea.\nWhole head during close. Industry Republican boy what green only. Such baby left for responsibility very look.',
    'email': 'moorejack@example.net',
    'phone_number': '226.385.6075x7064',
    'json': {
    'name': 'Stacy Ward',
    'address': '4384 Crystal Motorway\nChristopherhaven, SD 54146',
},
    'key7324': 'value31783',
    'key3511': 'value14581',
},
    {
    'id': 17527489767265,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Tina Andrews',
    'address': '4671 Bush Court Apt. 448\nPort Reginald, MT 21892',
    'text': 'Hotel now difference able outside. Real than candidate front population like where town.\nMe reflect may health. Life response traditional attack door later.',
    'email': 'kyledavis@example.com',
    'phone_number': '(575)991-3769x310',
    'json': {
    'name': 'Lisa Reid',
    'address': '2401 Hill Fall Suite 540\nWilcoxfurt, NM 64177',
},
    'key85541': 'value2378',
    'key39480': 'value51679',
    'key65820': 'value69424',
    'key58263': 'value31566',
    'key97114': 'value28402',
    'key37638': 'value21560',
    'key39933': 'value39106',
},
    {
    'id': 17527489767277,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Lisa Cole',
    'address': '71650 Esparza Expressway Apt. 431\nBrownmouth, AK 72655',
    'text': 'Deep American must realize parent. Difficult relationship admit game type.\nMemory eat stage until spring. Style age article ever development high. Already crime compare wear most indeed.',
    'email': 'phudson@example.com',
    'phone_number': '001-948-691-5976x66527',
    'json': {
    'name': 'Misty Mendoza',
    'address': '708 Jessica Valleys\nRiverabury, MT 18738',
},
    'key57026': 'value40893',
    'key61743': 'value32961',
    'key1255': 'value86618',
},
    {
    'id': 17527489767288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Jeffery Moore',
    'address': '8519 Sara Haven Suite 474\nMichaelville, CT 30639',
    'text': 'Particularly seek head seek represent inside. Force girl no contain manager across reveal. Station film explain population someone moment call here.',
    'email': 'chanjesus@example.com',
    'phone_number': '001-752-291-9247x38022',
    'json': {
    'name': 'Robert Duncan',
    'address': '670 Michael Forest Suite 403\nMadisonmouth, VI 90786',
},
    'key52697': 'value91792',
    'key67002': 'value1559',
    'key1626': 'value51136',
    'key41796': 'value95484',
},
    {
    'id': 17527489767299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Chelsea Nash',
    'address': '6503 Jones Port\nEast Lauratown, MT 84256',
    'text': 'Prove none fish message. Out speech reveal girl. Morning change than think table box pay.',
    'email': 'kclements@example.com',
    'phone_number': '+1-549-370-3166',
    'json': {
    'name': 'Dana Gutierrez',
    'address': '91210 Tiffany Hills Suite 758\nMelissamouth, TN 04054',
},
    'key45427': 'value13752',
    'key48063': 'value41053',
    'key39569': 'value25493',
    'key57210': 'value41334',
    'key6935': 'value25151',
    'key92574': 'value95049',
    'key93547': 'value37255',
    'key56091': 'value9039',
    'key52186': 'value21709',
    'key90213': 'value39694',
},
    {
    'id': 17527489767310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Carl Herrera',
    'address': '576 Rebecca Rapids\nWest Anthonymouth, VI 41234',
    'text': 'She teacher often effect purpose left. Fly reduce politics. Language necessary enjoy item.\nTravel while activity action. Drop no night respond give. Those become front.',
    'email': 'garciarussell@example.com',
    'phone_number': '+1-590-362-7777x8943',
    'json': {
    'name': 'Brenda Thompson',
    'address': '842 Pham Spurs Suite 788\nWest Dale, WV 67215',
},
    'key45901': 'value21177',
    'key38303': 'value52597',
    'key44616': 'value74407',
    'key30267': 'value69133',
    'key57219': 'value28937',
    'key8520': 'value91066',
    'key55063': 'value18761',
},
    {
    'id': 17527489767322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Amanda Sanders',
    'address': 'USNV Chambers\nFPO AE 00887',
    'text': 'Hot authority medical idea. Food form care century medical body.\nParty foreign put do from finally hot. May rather peace indicate machine.',
    'email': 'ashleyhays@example.net',
    'phone_number': '001-977-368-2387x57072',
    'json': {
    'name': 'Cindy Gonzalez',
    'address': '0804 Christopher Springs Suite 209\nEarltown, IL 39110',
},
    'key81931': 'value50338',
},
    {
    'id': 17527489767331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Ralph Hodge',
    'address': '996 Parks Loop\nRodriguezborough, FL 87961',
    'text': 'Add bag range among. Beautiful decade on short its suffer know compare. Start sing hit Democrat drop run often. Visit red part so they cost amount.\nNational top value seem.',
    'email': 'ivilla@example.org',
    'phone_number': '+1-412-955-0483x91703',
    'json': {
    'name': 'Melissa Love',
    'address': 'USCGC Gray\nFPO AE 03975',
},
    'key7052': 'value32438',
    'key28453': 'value319',
    'key72443': 'value21816',
    'key47208': 'value2934',
    'key84125': 'value44103',
    'key29986': 'value74543',
    'key34533': 'value97084',
    'key11474': 'value28190',
},
    {
    'id': 17527489767345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Christopher Smith',
    'address': '939 Jennifer Bridge Suite 868\nPort John, TN 69009',
    'text': 'Character smile positive itself act. Church special kitchen possible out challenge face. Laugh raise trip image cost new throw.',
    'email': 'williamsjohn@example.com',
    'phone_number': '001-245-223-5584x6336',
    'json': {
    'name': 'Christie Torres',
    'address': '90445 Wilson River\nHarrisville, AK 52271',
},
    'key78205': 'value23861',
    'key25600': 'value23986',
    'key66884': 'value91904',
},
    {
    'id': 17527489767356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Allison Garcia',
    'address': 'Unit 8941 Box 7842\nDPO AE 64745',
    'text': 'Feeling situation method standard among generation. Difficult thing within guess boy long off analysis. Seat animal oil support upon price land effort.',
    'email': 'jeremy57@example.com',
    'phone_number': '001-942-817-2406x3876',
    'json': {
    'name': 'Ruth Walker',
    'address': '2821 Michael Knoll\nNew Nicholaston, MN 44535',
},
    'key74724': 'value35489',
},
    {
    'id': 17527489767364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Andres Phillips',
    'address': '1066 Amy Isle\nCindymouth, NC 76554',
    'text': 'Race almost author candidate direction. Tonight concern movement.\nVoice during somebody leave figure face. Market summer local state. Account sign parent position.',
    'email': 'mitchellalexis@example.com',
    'phone_number': '(355)787-9327x321',
    'json': {
    'name': 'Shannon Dennis',
    'address': '99372 Toni Valleys\nWest Katherine, MI 15642',
},
    'key10563': 'value11226',
    'key82551': 'value68976',
},
    {
    'id': 17527489767375,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Chad Kim',
    'address': '09891 Williams Cliffs\nMaldonadomouth, TN 63049',
    'text': 'Establish mother management interest cell training. Girl very those amount laugh.\nActivity number against focus produce analysis turn. Never important claim fund help prove.',
    'email': 'taylorjoseph@example.com',
    'phone_number': '469.977.1548',
    'json': {
    'name': 'Amy Smith',
    'address': 'USNV Dodson\nFPO AP 00731',
},
    'key75389': 'value7041',
    'key10919': 'value59799',
    'key38708': 'value16671',
},
    {
    'id': 17527489767385,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Daniel Rodriguez',
    'address': '432 Nunez Shoals Suite 947\nCordovaborough, IN 14146',
    'text': 'We coach go no floor. Together social mention important performance fast think. Sort value very role water charge.\nFew floor today relationship.',
    'email': 'christopher86@example.com',
    'phone_number': '+1-684-267-8157',
    'json': {
    'name': 'Kimberly Gardner',
    'address': '018 Lara Gateway\nAaronhaven, WI 61129',
},
    'key21801': 'value43981',
    'key36536': 'value38196',
    'key89255': 'value83601',
    'key29809': 'value75741',
},
    {
    'id': 17527489767396,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Sara Soto',
    'address': '234 Chelsea Inlet Apt. 904\nNorth Davidshire, ND 65149',
    'text': 'Agency million prepare.\nDescribe near well common. Alone season land wrong turn among. Argue our poor industry significant pretty.',
    'email': 'sandrabruce@example.net',
    'phone_number': '3976341821',
    'json': {
    'name': 'Martha Lamb',
    'address': '7367 Henderson Park Apt. 406\nPort Alyssafurt, AZ 62353',
},
    'key66249': 'value53238',
    'key36697': 'value13270',
    'key71128': 'value60918',
    'key67891': 'value43769',
    'key73647': 'value33439',
},
    {
    'id': 17527489767408,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Regina Robinson',
    'address': 'USCGC Walker\nFPO AE 55824',
    'text': 'Chair quickly whom son present prevent. Throw really mission office public. Style than day manage drop.\nEye its voice level father. Million left author interest tree agreement national available.',
    'email': 'abigail75@example.org',
    'phone_number': '(543)663-5494',
    'json': {
    'name': 'Barbara Burke',
    'address': '17998 Charles Spur\nLindseyside, PR 99785',
},
    'key44168': 'value9659',
    'key6064': 'value6321',
    'key48783': 'value39547',
    'key4299': 'value47822',
    'key40203': 'value42895',
    'key51101': 'value63729',
    'key33248': 'value93363',
},
    {
    'id': 17527489767417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Sharon Gutierrez',
    'address': '8589 Cynthia Cove\nLake Kelly, DC 71227',
    'text': 'Forget half show. Wide lose indeed too ready.\nMight organization trouble glass. Property amount drug ground first Democrat like real. Enough training subject nor. Party guess bank over leave local.',
    'email': 'morenowillie@example.org',
    'phone_number': '(203)213-0010',
    'json': {
    'name': 'Christine Stanley',
    'address': '91367 Price Drives\nEast Thomasville, ID 60322',
},
    'key90712': 'value71111',
    'key83253': 'value33679',
    'key33238': 'value64214',
    'key68095': 'value78104',
    'key86424': 'value45352',
    'key39691': 'value21500',
    'key70803': 'value83663',
},
    {
    'id': 17527489767428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Russell Smith',
    'address': '454 Nicole Divide Apt. 012\nAnthonymouth, DC 87614',
    'text': 'If leader arm several team alone street career.\nNews perhaps attention season realize. Plan or single school early get.\nDream cut boy parent close few. Size major assume then in.\nLocal head wear.',
    'email': 'charles66@example.com',
    'phone_number': '441-936-1588',
    'json': {
    'name': 'Jason Marshall',
    'address': '130 Barker Rapids\nWest Mario, SC 66462',
},
    'key89474': 'value168',
    'key30812': 'value70769',
},
    {
    'id': 17527489767439,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Vanessa Gutierrez',
    'address': '6265 Romero Locks Apt. 013\nPort Briana, MN 41237',
    'text': 'Wear capital moment mission. Leader season summer choose Democrat.\nLeader test teacher better. May affect trouble relate I. Able discover she.',
    'email': 'martinezalex@example.org',
    'phone_number': '+1-521-988-7177x19482',
    'json': {
    'name': 'John Meza',
    'address': '23378 Foster Place\nWest Dominique, ME 00603',
},
    'key95173': 'value66347',
    'key5183': 'value90869',
    'key18481': 'value38833',
    'key55653': 'value87077',
    'key18675': 'value88320',
    'key50610': 'value36485',
    'key71669': 'value9402',
    'key14750': 'value10737',
    'key716': 'value59894',
    'key5962': 'value32413',
},
    {
    'id': 17527489767450,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Lauren Murray',
    'address': '78058 Clark Centers Apt. 437\nGriffithchester, AZ 41931',
    'text': 'Show history skin everyone. Use baby guess drive.\nEven stuff administration major. Recognize window huge possible natural book. Compare real throw.',
    'email': 'erikblake@example.com',
    'phone_number': '831-751-3806x9531',
    'json': {
    'name': 'Jesse Perry',
    'address': '76909 Caleb Neck Suite 146\nSouth Josephside, CO 68856',
},
    'key26567': 'value55435',
    'key95724': 'value53342',
    'key67970': 'value1643',
    'key82220': 'value97850',
    'key11544': 'value6248',
},
    {
    'id': 17527489767462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Calvin Smith',
    'address': '012 Kelsey Street Suite 648\nWest Jessicaport, TN 20210',
    'text': 'So course education nor. Add point listen maintain teach. Key significant policy support.',
    'email': 'jenniferarcher@example.net',
    'phone_number': '(459)256-8493',
    'json': {
    'name': 'Sarah Martinez',
    'address': 'PSC 8677, Box 7055\nAPO AE 73555',
},
    'key48412': 'value7465',
    'key40041': 'value77236',
    'key20049': 'value86385',
    'key13451': 'value10193',
    'key23812': 'value69450',
},
    {
    'id': 17527489767471,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Roberto Wilson',
    'address': '916 Monica Squares\nNorth Tina, LA 99822',
    'text': 'And soldier way movement study six life yourself. After newspaper run product gun.\nReveal produce church each clear kid. Still lead save dog high radio other friend.',
    'email': 'vbentley@example.net',
    'phone_number': '605-202-0762x83445',
    'json': {
    'name': 'Robert Wilson',
    'address': 'Unit 3398 Box 7038\nDPO AA 14554',
},
    'key49066': 'value20675',
    'key94029': 'value56064',
    'key33283': 'value82556',
    'key79129': 'value66762',
    'key13478': 'value97480',
    'key71934': 'value85333',
    'key85845': 'value15345',
    'key1075': 'value11682',
    'key74535': 'value10645',
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'address',
    'uid',
    'email',
    'vector',
    'json',
],
    'filter': 'name > \'Lu\'',
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



    def test_request_4(self):
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = 'null'
        
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
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



    def test_request_7(self):
        """测试请求 7 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'c92af8dc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_42_50_492970nqFxdZHk',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name > "placeholder"]_1752748980.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithVarcharFilterTrueNamePlaceholder1752748980Json()
    test.run_tests()
