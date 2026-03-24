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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752748878_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752748878.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUidIn12341752748878Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752748878.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752748878.json"
        self.test_count = 5  # 测试方法数量
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
    'RequestId': '8ae04a8c-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_05_982544SzUjqHHy',
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
    'RequestId': '8ae04a8c-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_05_982544SzUjqHHy',
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
    'RequestId': '8ae04a8c-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_05_982544SzUjqHHy',
    'data': [
    {
    'id': 17527488720181,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Thomas Lewis',
    'address': '804 Shirley Spring\nWalkerbury, FL 01780',
    'text': 'Society ready professional or anyone where try. Explain deep realize direction cup news. System value plan article surface agree including.',
    'email': 'oneillryan@example.org',
    'phone_number': '001-548-449-1401',
    'json': {
    'name': 'James Smith',
    'address': '66839 David Groves Apt. 722\nDanielton, SC 55009',
},
    'key66529': 'value19663',
    'key48626': 'value58803',
},
    {
    'id': 17527488720197,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Natasha Wallace',
    'address': '82752 Williams Locks Suite 702\nPort Christopherton, OH 76688',
    'text': 'Bed successful look choose show money. Garden director capital report various work. Something which agent speak.',
    'email': 'cathycurry@example.org',
    'phone_number': '(341)537-3652',
    'json': {
    'name': 'Troy Davis',
    'address': 'Unit 4695 Box 3328\nDPO AA 92708',
},
    'key38013': 'value71734',
    'key94013': 'value25084',
    'key44807': 'value25066',
    'key3980': 'value68761',
    'key90774': 'value27243',
},
    {
    'id': 17527488720208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Melissa Hays',
    'address': '2816 Jeffrey Forges Apt. 356\nLake Julie, VA 13483',
    'text': 'Reach shake bad special Mr center position. Enjoy boy also wrong she trouble.\nSeries leave receive resource evidence former. Half help carry painting behind. Wonder current happy.',
    'email': 'ihutchinson@example.org',
    'phone_number': '+1-505-442-5898x7419',
    'json': {
    'name': 'Mr. Jason Anderson',
    'address': '50746 Brown Rapid\nNorth Deborahchester, SC 93788',
},
    'key33073': 'value72871',
    'key31881': 'value20497',
    'key88270': 'value27603',
    'key51177': 'value10612',
    'key32037': 'value51762',
    'key80101': 'value92470',
    'key83457': 'value47378',
    'key58865': 'value60032',
    'key43887': 'value95611',
},
    {
    'id': 17527488720220,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'James Hoffman',
    'address': '57901 Cristina Burg\nWest Adam, WA 82823',
    'text': 'Responsibility foreign student reflect cut argue. Show dinner only soon her institution happy.\nPopulation trip develop crime again.',
    'email': 'matthewsmith@example.org',
    'phone_number': '+1-729-744-5296',
    'json': {
    'name': 'Molly Green',
    'address': 'PSC 4340, Box 6069\nAPO AP 72208',
},
    'key23613': 'value8122',
    'key58731': 'value63070',
    'key97957': 'value1401',
    'key42702': 'value80296',
    'key65959': 'value76197',
    'key18498': 'value89287',
    'key83960': 'value99194',
    'key35455': 'value97932',
    'key22706': 'value38725',
},
    {
    'id': 17527488720230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Elizabeth Hawkins',
    'address': '212 Ayers Hill Apt. 293\nAshleyland, MH 34548',
    'text': 'Talk adult vote success million cultural no. Figure sometimes up green win be commercial dog. Box feel service tend finally rock bag which.',
    'email': 'ndaniels@example.com',
    'phone_number': '+1-822-218-2066x4992',
    'json': {
    'name': 'Jennifer Garcia',
    'address': '30159 Anne Fort\nBurchstad, WY 14579',
},
    'key22937': 'value85773',
    'key99653': 'value97942',
    'key6636': 'value10351',
    'key52343': 'value3858',
    'key65883': 'value9516',
    'key90706': 'value55396',
},
    {
    'id': 17527488720243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Miguel Brennan',
    'address': 'Unit 9334 Box 1326\nDPO AE 26845',
    'text': 'Democrat local culture interview. Summer beautiful property note left help.\nListen stock best agree. Magazine class move today eight. Similar future not idea sort sort shoulder.',
    'email': 'nancywright@example.com',
    'phone_number': '492-637-7219x04234',
    'json': {
    'name': 'Miranda Nolan',
    'address': '9025 Cordova Point Apt. 911\nLisaville, MN 01742',
},
    'key17777': 'value32210',
    'key20452': 'value18032',
    'key19796': 'value42592',
    'key19078': 'value53321',
    'key14256': 'value8411',
    'key45214': 'value16492',
    'key18363': 'value60378',
},
    {
    'id': 17527488720253,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Regina Scott',
    'address': '87085 Duarte Manor Apt. 909\nJohnfort, IN 59165',
    'text': 'Member gun specific place develop we. Source television indeed anyone. Really leader board behind check institution let.',
    'email': 'jill57@example.org',
    'phone_number': '(348)276-6296x7498',
    'json': {
    'name': 'Anthony Frost',
    'address': '845 Johnson Roads Apt. 548\nAmandamouth, CA 48268',
},
    'key68186': 'value96004',
    'key84692': 'value91184',
    'key61176': 'value53589',
    'key84566': 'value93115',
    'key19707': 'value95132',
    'key36884': 'value93655',
},
    {
    'id': 17527488720265,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joe Brooks',
    'address': '327 Katie Knolls\nSotostad, VT 69256',
    'text': 'Then movement lawyer election trade.\nPlant say night.\nTen up follow important say soldier maintain information. Game action everyone bill thousand concern.',
    'email': 'walterskatherine@example.org',
    'phone_number': '587-824-0677x44716',
    'json': {
    'name': 'Troy Jackson',
    'address': '582 Osborne Ford\nSheilaside, MS 58526',
},
    'key66829': 'value55495',
    'key97900': 'value61463',
    'key17185': 'value6174',
},
    {
    'id': 17527488720277,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Amy Scott',
    'address': 'Unit 1298 Box 0025\nDPO AA 84607',
    'text': 'Phone behind page help ok grow together sit. Special third central story stuff.\nInvolve what administration.',
    'email': 'reedjuan@example.org',
    'phone_number': '001-322-863-2882',
    'json': {
    'name': 'Jessica Burke',
    'address': '1677 Michael Rapid\nLake Danielside, DE 82210',
},
    'key87010': 'value24704',
    'key97133': 'value42309',
    'key69266': 'value42498',
    'key86331': 'value66213',
    'key29283': 'value75437',
    'key21634': 'value35487',
    'key55668': 'value66751',
    'key74083': 'value75123',
    'key12149': 'value41897',
    'key13917': 'value98271',
},
    {
    'id': 17527488720286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Barbara Simmons',
    'address': '74977 Myers Plains Suite 483\nNorth Jeremy, AK 33080',
    'text': 'Wide stage board east task most. Through always dark change large hand action mouth.\nWin bar opportunity such. Television top star whether. Low receive wife movie owner.',
    'email': 'sheltondiana@example.net',
    'phone_number': '001-572-676-5051',
    'json': {
    'name': 'Melissa Holder',
    'address': '631 Gonzales Estates\nNathanton, CO 10908',
},
    'key93574': 'value78051',
    'key2565': 'value9607',
    'key26886': 'value1020',
    'key20584': 'value97831',
    'key24852': 'value39669',
    'key47459': 'value60413',
},
    {
    'id': 17527488720297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Linda Chen',
    'address': '3863 Mark Course Apt. 290\nMeyerville, GA 09313',
    'text': 'Throughout happy before spring space. Project few employee radio.\nRace lead manage project.\nGeneral role may second picture. Fly simply medical practice possible camera.',
    'email': 'amanda34@example.com',
    'phone_number': '+1-907-483-0646x2259',
    'json': {
    'name': 'Zachary Arnold',
    'address': '1602 Jonathan Roads\nEast John, KY 37640',
},
    'key71747': 'value50454',
},
    {
    'id': 17527488720308,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Holly Foley',
    'address': '034 Garcia Estate Suite 275\nLake Valerie, LA 39159',
    'text': 'Economic up send chair TV wrong. Religious mouth amount number. Start send factor subject scene light.\nHigh city reach hope beat join.\nLearn study church not respond. Father event history claim.',
    'email': 'dmyers@example.net',
    'phone_number': '001-581-497-1656x662',
    'json': {
    'name': 'Nicole Williams',
    'address': '5873 Ross Green\nEast Angela, MN 73642',
},
    'key52784': 'value5025',
    'key85935': 'value40160',
    'key3992': 'value98701',
    'key28734': 'value82853',
    'key16382': 'value91910',
    'key25185': 'value34140',
    'key66043': 'value21888',
    'key98524': 'value31504',
    'key65253': 'value98476',
},
    {
    'id': 17527488720319,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Joyce Dorsey',
    'address': '8324 Hancock Ranch Apt. 443\nReyesstad, FM 97508',
    'text': 'Future item election whom growth item. Almost enough at own recently stuff look artist. North return relationship media question hear.',
    'email': 'rebeccamiller@example.net',
    'phone_number': '361-620-4512',
    'json': {
    'name': 'Christopher Marshall',
    'address': '5808 Mark Glens Suite 889\nThomasborough, PR 49985',
},
    'key47143': 'value75583',
    'key12328': 'value45442',
    'key1835': 'value20944',
    'key39441': 'value7957',
    'key84662': 'value11026',
    'key58863': 'value97423',
},
    {
    'id': 17527488720331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Olivia Phillips',
    'address': '353 Alison Port\nPort Kyletown, KS 82738',
    'text': 'Build include increase wait this. Fall city beat house guy protect guess. Poor find age guess floor.\nCould national sister.',
    'email': 'xallen@example.com',
    'phone_number': '7013026576',
    'json': {
    'name': 'Emily Castillo',
    'address': '6593 Jacob Loop Apt. 296\nNorth Cheyennetown, WA 19860',
},
    'key21639': 'value16441',
},
    {
    'id': 17527488720342,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Sheila Franklin',
    'address': 'PSC 1523, Box 9888\nAPO AA 15013',
    'text': 'Administration natural into will. Young give four them top.\nChurch by fill.\nMust hour cover region else development bed. Know should poor debate wonder stay. Style either usually billion.',
    'email': 'patrickibarra@example.com',
    'phone_number': '262.374.0897',
    'json': {
    'name': 'Ronald Ramos',
    'address': '549 Thompson Manors\nJohnstonmouth, AL 16069',
},
    'key81504': 'value83827',
    'key53119': 'value13889',
    'key21218': 'value82813',
    'key55744': 'value91412',
    'key45367': 'value89142',
    'key16696': 'value19442',
    'key4702': 'value90145',
    'key70135': 'value15182',
    'key17667': 'value46159',
},
    {
    'id': 17527488720352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Michael Suarez',
    'address': '444 Antonio Estates Apt. 406\nKennethport, NV 86696',
    'text': 'Whom interesting memory use various remember. Upon fire young serve different. Mention social teach such somebody case charge.',
    'email': 'joannehayes@example.com',
    'phone_number': '+1-622-616-0785x989',
    'json': {
    'name': 'Rachel Arias',
    'address': '88671 Baker Plains Apt. 221\nPort Shawn, ND 86078',
},
    'key8509': 'value86653',
    'key47989': 'value58045',
    'key15477': 'value79931',
    'key7911': 'value95205',
    'key55954': 'value43264',
    'key88156': 'value64526',
    'key88765': 'value78793',
    'key75512': 'value59457',
    'key26350': 'value5499',
    'key39659': 'value72332',
},
    {
    'id': 17527488720363,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Rebecca Martinez',
    'address': '107 Gregory Lock Suite 303\nPort Daniel, CA 62782',
    'text': 'Feel produce family attorney clearly leave. Until form pick. Accept character reflect behind window since position.\nSort reach appear need national.',
    'email': 'williamdaniel@example.org',
    'phone_number': '+1-333-936-0860x81832',
    'json': {
    'name': 'Rachel Hernandez',
    'address': 'PSC 5157, Box 3547\nAPO AA 17721',
},
    'key51164': 'value82092',
    'key95648': 'value51783',
    'key26551': 'value61307',
    'key44261': 'value86367',
},
    {
    'id': 17527488720373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Jennifer Sanders',
    'address': '5341 Carla Estate Apt. 488\nAllenmouth, AL 82530',
    'text': 'Character card huge specific hundred live most. Into great song subject miss.\nMorning inside car. Check candidate sport hit energy those red.',
    'email': 'sjoseph@example.org',
    'phone_number': '3678314029',
    'json': {
    'name': 'Donald Johnson',
    'address': '1231 Smith Circle\nSouth Matthewmouth, OR 23754',
},
    'key67742': 'value5722',
    'key56625': 'value99060',
    'key48141': 'value30467',
    'key5625': 'value89413',
    'key66906': 'value75857',
    'key96914': 'value20005',
    'key12851': 'value64980',
    'key85626': 'value92361',
    'key69810': 'value31393',
},
    {
    'id': 17527488720383,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Steven Jones',
    'address': '1204 Hardy Mountains\nDukeville, AR 88853',
    'text': 'Exist ever relate main above wait. Old down lay property room.\nReturn miss individual simple respond they quickly. Radio issue everybody. Not although simply service seven claim rule three.',
    'email': 'rogercarney@example.org',
    'phone_number': '791.757.1963',
    'json': {
    'name': 'Brandi Smith',
    'address': '933 Thompson Springs\nDerekton, ID 91535',
},
    'key53566': 'value50350',
},
    {
    'id': 17527488720395,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jason Weiss',
    'address': '7338 Henderson Plains Suite 216\nChamberschester, FL 49581',
    'text': 'Government change husband actually police never. Network audience detail key matter current wide. Five base despite hotel open former writer. You surface police design tree window.',
    'email': 'ramosjulia@example.com',
    'phone_number': '(500)919-0284',
    'json': {
    'name': 'Marcus Frazier',
    'address': '93466 Amanda Mountain Apt. 168\nEast John, GU 32913',
},
    'key83804': 'value23117',
    'key37731': 'value54687',
    'key40112': 'value21861',
    'key27320': 'value82833',
    'key14373': 'value93400',
    'key78958': 'value24706',
    'key8240': 'value20082',
    'key28475': 'value68505',
    'key42134': 'value6308',
},
    {
    'id': 17527488720407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Gloria Vega',
    'address': '872 Daniel Green Suite 427\nLewismouth, FM 68207',
    'text': 'Know admit nearly believe contain size.\nCountry room event same ball mention staff plant. Nature law industry summer executive account.',
    'email': 'michelle91@example.net',
    'phone_number': '381.560.4590x2886',
    'json': {
    'name': 'James Miller',
    'address': '017 Hannah Wells Suite 700\nMarystad, NH 38547',
},
    'key64069': 'value5655',
    'key69134': 'value53964',
    'key67692': 'value63271',
    'key18769': 'value68846',
    'key85192': 'value34393',
},
    {
    'id': 17527488720417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'James Miller',
    'address': '337 Bryant Streets\nPort Dennis, OR 67091',
    'text': 'Seat Mrs natural some add scientist become. Strong above practice fast. Professor trial into address out community else.',
    'email': 'michaelbrittney@example.org',
    'phone_number': '764.653.5192x670',
    'json': {
    'name': 'Ashley Klein',
    'address': '679 Bolton Ways Suite 770\nSouth Lauren, AR 72567',
},
    'key57833': 'value54255',
    'key44335': 'value38795',
    'key45835': 'value53902',
    'key58901': 'value58254',
},
    {
    'id': 17527488720429,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Heather Calderon MD',
    'address': 'USNV Turner\nFPO AA 68545',
    'text': 'Administration situation write education water wait popular. Drive the their serve analysis central anything across. Per drive street partner race center sound.',
    'email': 'frederick47@example.org',
    'phone_number': '+1-829-423-1160x42288',
    'json': {
    'name': 'Timothy Fuentes',
    'address': '459 Ruth Green Apt. 858\nJohnbury, OR 43152',
},
    'key31836': 'value11971',
    'key51371': 'value8246',
},
    {
    'id': 17527488720438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Cassandra Miller',
    'address': '75322 Stephen Island\nElliottview, NV 34836',
    'text': 'Line or prepare also which. Look kind instead kid project. What check position add. Bag between by source employee.\nScene talk young in. Knowledge foot people upon.',
    'email': 'zwebb@example.com',
    'phone_number': '+1-350-306-2966x9835',
    'json': {
    'name': 'Matthew Phillips',
    'address': '29599 Denise Ferry Suite 211\nSouth Brandon, PA 26698',
},
    'key50559': 'value86231',
    'key97581': 'value69660',
    'key39023': 'value47051',
    'key95092': 'value74970',
    'key92764': 'value6588',
    'key16723': 'value170',
    'key98686': 'value39546',
    'key41869': 'value99792',
    'key33903': 'value88198',
    'key63181': 'value52352',
},
    {
    'id': 17527488720449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Kevin Edwards',
    'address': '323 Lewis Heights\nKennethshire, SD 16764',
    'text': 'Smile thing rock very agent. Type people three appear mean that.\nLand into clearly though. Blue both ever could. Community dog speech machine suggest site set.',
    'email': 'april96@example.org',
    'phone_number': '+1-434-801-9564x5368',
    'json': {
    'name': 'Tyler Huff',
    'address': '88499 Nguyen Trail\nPort Blake, NY 24630',
},
    'key13633': 'value89277',
    'key60494': 'value9159',
},
    {
    'id': 17527488720459,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'James Mathis',
    'address': '645 Gabrielle Drive\nNew Matthewmouth, WA 31485',
    'text': 'Discuss surface decision out store. Out Republican over condition modern believe.\nChair quality wish represent her. Board company similar man not this doctor.',
    'email': 'hjuarez@example.org',
    'phone_number': '+1-895-500-8289',
    'json': {
    'name': 'Julia Hobbs',
    'address': '43649 Anderson Mills Apt. 502\nNew Jessica, FM 35025',
},
    'key5030': 'value96631',
    'key51435': 'value27528',
    'key88133': 'value60273',
    'key73919': 'value14169',
    'key54971': 'value52309',
    'key84480': 'value46371',
},
    {
    'id': 17527488720470,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Eric Wall',
    'address': 'Unit 6939 Box 4527\nDPO AP 25287',
    'text': 'Member live manager increase. Eye possible call mention teacher. Rest big management admit especially house life.',
    'email': 'heather61@example.org',
    'phone_number': '+1-820-523-2366x3678',
    'json': {
    'name': 'Alexandra Smith',
    'address': 'PSC 6325, Box 4894\nAPO AE 92954',
},
    'key16745': 'value3224',
    'key95821': 'value77280',
    'key88333': 'value43837',
    'key36820': 'value47950',
    'key65110': 'value67953',
    'key57906': 'value39680',
    'key95500': 'value27548',
    'key65192': 'value82152',
    'key62682': 'value2479',
    'key32456': 'value7669',
},
    {
    'id': 17527488720477,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jason Velazquez',
    'address': '0331 Lamb Lake Apt. 591\nAmyborough, SD 75397',
    'text': 'After quite possible response though. Senior choose account within remain notice.\nDog party Democrat lead hospital possible. Hour rich tough year stop thing music garden.',
    'email': 'juliahill@example.org',
    'phone_number': '(419)655-3046',
    'json': {
    'name': 'Steven Summers',
    'address': '217 Dixon Forest\nAndreaburgh, DE 81127',
},
    'key49629': 'value28935',
    'key45687': 'value95263',
    'key48628': 'value60158',
},
    {
    'id': 17527488720489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Teresa Morgan',
    'address': '7265 Mcdaniel Avenue\nLaurashire, KY 52799',
    'text': 'Truth lawyer recognize. Have leg such film century.\nRelate old rule understand green response easy. Mrs wind election character region find. We enjoy news manager fire major.',
    'email': 'damon58@example.org',
    'phone_number': '001-651-971-5133x740',
    'json': {
    'name': 'Ms. Laura Mann',
    'address': '1357 Taylor Place Suite 037\nAustinborough, GU 07365',
},
    'key99358': 'value61853',
    'key13075': 'value25403',
    'key73704': 'value6150',
    'key25323': 'value52968',
    'key18926': 'value13993',
    'key81602': 'value69367',
    'key41276': 'value55584',
    'key62726': 'value12340',
},
    {
    'id': 17527488720500,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Ryan Contreras',
    'address': '46767 Tyler Fords Apt. 604\nNorth Andrewstad, UT 77471',
    'text': 'Another number read including head.\nGirl quite himself card increase like maintain. Machine away state city when better under.\nBeat but top. Pick memory above dark.',
    'email': 'torresthomas@example.com',
    'phone_number': '295.378.5241',
    'json': {
    'name': 'Melissa Stevenson',
    'address': '917 Dean Ridges\nEast Benjaminburgh, AS 28055',
},
    'key41600': 'value2128',
    'key3346': 'value83950',
    'key24406': 'value68824',
},
    {
    'id': 17527488720511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Kimberly Mcdaniel',
    'address': 'Unit 7816 Box 6778\nDPO AE 43792',
    'text': 'Safe force itself morning suggest. Deep also major travel scene nearly. Paper piece ok require them member particularly.',
    'email': 'nboone@example.com',
    'phone_number': '6273860705',
    'json': {
    'name': 'Derek Clark',
    'address': '93671 Perez Summit\nPort Teresa, AZ 02306',
},
    'key62531': 'value39934',
    'key41467': 'value77427',
    'key57511': 'value12147',
    'key2075': 'value82479',
    'key58437': 'value4867',
    'key41134': 'value61330',
    'key74704': 'value43238',
    'key29506': 'value53300',
    'key83305': 'value10012',
},
    {
    'id': 17527488720520,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Michelle Davis',
    'address': '05653 Benjamin Ports Apt. 519\nNew Craig, ID 89027',
    'text': 'Character pressure stand your election. Animal else big from necessary clearly. Care if themselves maybe hit hope.',
    'email': 'hensonmichael@example.net',
    'phone_number': '542-453-5786x351',
    'json': {
    'name': 'Taylor Villegas',
    'address': '3262 Perkins Ramp Suite 859\nTeresaberg, CT 48226',
},
    'key88331': 'value35341',
},
    {
    'id': 17527488720531,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'John Tyler',
    'address': '698 Kimberly Trail\nLeeside, MS 70151',
    'text': 'Challenge above school article key. Certain marriage season pass rule finish north.\nWide end price increase safe.',
    'email': 'paulnash@example.com',
    'phone_number': '+1-512-841-4454',
    'json': {
    'name': 'Kimberly Gordon',
    'address': '2703 Misty Manor\nSilvaville, IL 29616',
},
    'key76242': 'value72387',
    'key25792': 'value27471',
    'key5995': 'value73563',
    'key15429': 'value91262',
},
    {
    'id': 17527488720542,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Robin Tucker',
    'address': '2039 Garcia Trafficway\nSouth Brittany, UT 61426',
    'text': 'Feel sell member account successful how if appear. Little sit military figure several.\nElse arm blood goal visit sit attention. Herself few once positive. Black project maybe gun.',
    'email': 'michelle56@example.net',
    'phone_number': '+1-973-248-4005',
    'json': {
    'name': 'Lucas Mitchell',
    'address': '716 Kelly Spring Suite 197\nWilsonville, CA 56019',
},
    'key45508': 'value86717',
    'key98100': 'value70755',
    'key82532': 'value79411',
    'key11270': 'value47049',
    'key32066': 'value67580',
    'key33848': 'value6563',
    'key31269': 'value45497',
    'key77427': 'value12657',
    'key45004': 'value64923',
},
    {
    'id': 17527488720553,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Amber Bush',
    'address': '20767 Kyle Orchard\nEricastad, FM 37347',
    'text': 'Learn sport arrive. Office despite over majority evidence particular industry. Economy word travel argue open music.',
    'email': 'ekaufman@example.org',
    'phone_number': '557-447-7676x267',
    'json': {
    'name': 'Paula Cook',
    'address': '766 Stevens Land Suite 543\nNorth Aimee, MA 66196',
},
    'key92206': 'value38977',
    'key7710': 'value42723',
    'key62733': 'value36988',
},
    {
    'id': 17527488720564,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Aaron Thompson',
    'address': '610 Lopez Haven\nSouth Meganbury, KY 25682',
    'text': 'Beat throw protect later bar interview realize prove. Think cell claim.\nRead city store either song never affect. Assume particularly strong bag possible relationship son.',
    'email': 'ruizjoseph@example.com',
    'phone_number': '(344)598-1100x06697',
    'json': {
    'name': 'Jonathan Pollard',
    'address': '3166 Woods Camp\nMichaelport, AL 14251',
},
    'key52409': 'value96643',
    'key12821': 'value20706',
    'key80808': 'value6044',
    'key96268': 'value92694',
},
    {
    'id': 17527488720575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Kim Silva',
    'address': '9862 Ward Parks\nBradleyland, NE 95102',
    'text': 'Travel back process goal prove create organization. Material these then television probably. Director assume take what cup.',
    'email': 'jasonrusso@example.org',
    'phone_number': '001-669-806-5264x3077',
    'json': {
    'name': 'Joseph Acevedo',
    'address': 'PSC 3969, Box 3737\nAPO AE 70542',
},
    'key21191': 'value61137',
    'key19514': 'value27690',
    'key64720': 'value33918',
    'key49287': 'value63683',
    'key37423': 'value81486',
    'key53610': 'value84039',
    'key8281': 'value28200',
    'key93525': 'value81205',
},
    {
    'id': 17527488720585,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Dana Johnson',
    'address': 'Unit 4931 Box 5572\nDPO AP 61086',
    'text': 'Between ok wide will fight learn cost. Value reality left would.\nItem someone politics. Couple and describe system not.\nMovie blue yet take be. Board economic social design total upon energy.',
    'email': 'joneskeith@example.org',
    'phone_number': '679-324-1239',
    'json': {
    'name': 'Nicholas Knight',
    'address': '797 Shaw Mountains Apt. 469\nCindybury, TX 12827',
},
    'key19772': 'value39864',
    'key79474': 'value63249',
    'key80444': 'value50392',
    'key86585': 'value98383',
    'key69304': 'value2640',
    'key23923': 'value18215',
    'key40145': 'value57574',
    'key63621': 'value24661',
    'key26216': 'value28455',
    'key87565': 'value12838',
},
    {
    'id': 17527488720595,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Lynn Thompson',
    'address': '427 Ryan Crescent Apt. 739\nMartinberg, LA 61404',
    'text': 'Ever sound picture ok. Analysis future create accept discuss marriage.\nEverything method energy soldier three fill. Themselves way reach why section.',
    'email': 'matthewmoore@example.com',
    'phone_number': '428.664.2760x5142',
    'json': {
    'name': 'Diane Mccarthy',
    'address': '55921 Matthew Alley\nGravesberg, SC 53867',
},
    'key2820': 'value56387',
    'key91246': 'value19963',
    'key8492': 'value44254',
    'key64921': 'value68067',
    'key11717': 'value32223',
    'key31835': 'value78623',
    'key57461': 'value5376',
    'key48334': 'value32647',
    'key38213': 'value73498',
},
    {
    'id': 17527488720606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Andrea Russo',
    'address': '96058 Diane Falls\nAarontown, MD 09340',
    'text': 'Radio hot center contain various million. Gun toward generation painting guy conference.',
    'email': 'barberbryce@example.com',
    'phone_number': '+1-890-878-7714x0299',
    'json': {
    'name': 'Andrew Collins',
    'address': '22891 Diaz Club\nNorth Gregory, IA 14837',
},
    'key43796': 'value36192',
    'key63446': 'value99117',
    'key74254': 'value77243',
    'key60547': 'value72974',
},
    {
    'id': 17527488720617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Anthony Martinez',
    'address': '342 Brown Prairie\nKennethfurt, PW 94050',
    'text': 'Down although economy expect size kid. Truth event former year article class. Positive office floor country factor person. Agree radio teacher until share.',
    'email': 'ianderson@example.org',
    'phone_number': '634-323-6428',
    'json': {
    'name': 'Sean Li',
    'address': '76009 Mary Key\nEast Cynthia, DC 14322',
},
    'key51276': 'value19173',
    'key21289': 'value3198',
    'key45502': 'value37684',
    'key18728': 'value91930',
    'key9511': 'value93388',
    'key21126': 'value82116',
    'key57112': 'value44146',
},
    {
    'id': 17527488720628,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Hannah Lopez',
    'address': 'Unit 6194 Box 4462\nDPO AP 79950',
    'text': 'Should evidence professional discussion task him pull. System enough also cell attorney. Customer successful research take successful instead professional.',
    'email': 'luislopez@example.com',
    'phone_number': '885-511-2838x480',
    'json': {
    'name': 'Marie Brown',
    'address': '64837 Jonathan Parks\nNew Sarahfort, WV 29797',
},
    'key54683': 'value11851',
    'key94252': 'value68914',
    'key19599': 'value78757',
    'key23766': 'value30816',
    'key54733': 'value55341',
    'key31586': 'value54076',
    'key92934': 'value22927',
    'key11963': 'value51124',
    'key28178': 'value77925',
    'key90316': 'value9489',
},
    {
    'id': 17527488720637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Bryan Thompson',
    'address': '0813 Berry Village\nSouth Jacob, MN 98734',
    'text': 'Finish rate even defense particular decide. Themselves soon walk sea security important. Color bag to however can citizen north.',
    'email': 'henry15@example.net',
    'phone_number': '(453)881-8659x834',
    'json': {
    'name': 'Katrina Garza',
    'address': 'USNS Mckinney\nFPO AE 99684',
},
    'key38527': 'value8846',
},
    {
    'id': 17527488720646,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Nichole Cannon',
    'address': '51189 April Points Apt. 074\nLake Patriciahaven, OK 27793',
    'text': 'Defense practice up make. Financial painting lay reduce along would section. Something thank miss computer during scene involve.\nCulture how if from reduce really. Baby happen PM media foot firm.',
    'email': 'steven99@example.org',
    'phone_number': '649.503.1482',
    'json': {
    'name': 'Courtney Sims',
    'address': '5522 Lee Meadows Suite 648\nHensleyburgh, WY 01642',
},
    'key72822': 'value50266',
    'key73642': 'value46791',
    'key60031': 'value88464',
    'key57157': 'value32179',
    'key16760': 'value35994',
    'key6906': 'value79975',
    'key58919': 'value59272',
},
    {
    'id': 17527488720657,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Tara Wolfe',
    'address': '00384 Taylor Union\nKennethbury, MP 61440',
    'text': 'Them kid check daughter produce southern crime draw. Social capital meeting book.\nReach alone board my economy. Catch cost outside audience protect four. Three create dream others member may.',
    'email': 'vrogers@example.net',
    'phone_number': '+1-655-511-0418x820',
    'json': {
    'name': 'Candice Green',
    'address': '2634 Bryan Glen\nMurrayland, MO 58960',
},
    'key28833': 'value91647',
    'key44068': 'value50843',
    'key96829': 'value97683',
},
    {
    'id': 17527488720668,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Mark Donaldson',
    'address': '5493 Karen Pine Apt. 427\nNorth Holly, OR 51614',
    'text': 'Color early speech easy staff provide.\nScience person own special television agent. Recent although special window.\nOnto present scientist at heavy capital. Seem Democrat form room.',
    'email': 'csims@example.com',
    'phone_number': '(308)751-1473',
    'json': {
    'name': 'Larry Moody',
    'address': '71749 Victoria Manors Suite 760\nPort Ashleyville, MO 24189',
},
    'key36680': 'value29904',
    'key41968': 'value54134',
},
    {
    'id': 17527488720679,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Joe Price',
    'address': '80901 Jackson Expressway Apt. 563\nPort Mary, MS 91464',
    'text': 'Really just despite their.\nGrowth simple have bank. Culture your sell sense performance. Reason sit result site chance able true.',
    'email': 'sarahgonzales@example.net',
    'phone_number': '232.229.8337x152',
    'json': {
    'name': 'Sheila Gross',
    'address': '64090 Brittany Landing Apt. 884\nPort Jason, IL 45323',
},
    'key3116': 'value95151',
    'key38470': 'value93916',
},
    {
    'id': 17527488720690,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Sandra Alvarez',
    'address': '118 Escobar Forest\nSmithview, VT 16914',
    'text': 'Card reality important either. Successful hope argue he middle deal. Three group anyone concern case.\nRock painting goal company edge major tend film. Agree first law trouble bit if capital.',
    'email': 'harriswilliam@example.net',
    'phone_number': '001-343-334-3069x32688',
    'json': {
    'name': 'Antonio Russell',
    'address': '2445 Simpson Common Suite 764\nKimberlyfort, NH 51097',
},
    'key25804': 'value69105',
},
    {
    'id': 17527488720702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Eileen Ayala',
    'address': '7927 Jennifer Street Apt. 488\nNorth Yvetteland, GU 25468',
    'text': 'Attention response development. Cell thus manage attention central.\nWho nearly result evening everybody. Now kid goal often region.',
    'email': 'william68@example.org',
    'phone_number': '494-427-4017x874',
    'json': {
    'name': 'John King',
    'address': 'USNV Wilson\nFPO AP 13906',
},
    'key16504': 'value67035',
    'key96304': 'value63620',
    'key90859': 'value77042',
    'key30687': 'value10647',
},
    {
    'id': 17527488720712,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Sarah Wood',
    'address': '9444 Jeremy Vista\nNorth Pamela, MP 08918',
    'text': 'All marriage evening base. Eight check near herself wide thing. High sometimes near sure budget reduce would.',
    'email': 'rebecca41@example.com',
    'phone_number': '304.914.9588x6235',
    'json': {
    'name': 'Christian Johnson',
    'address': '8514 Christopher Well\nStewartview, MP 80958',
},
    'key40301': 'value21224',
    'key95898': 'value37824',
    'key28331': 'value84653',
    'key94407': 'value64324',
    'key41651': 'value65318',
    'key24985': 'value34401',
    'key30292': 'value30995',
    'key5591': 'value11926',
    'key69553': 'value66618',
},
    {
    'id': 17527488720722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Dawn Wilson',
    'address': '0302 Danielle Haven Suite 035\nWeekschester, AR 66460',
    'text': 'Guy fund whole draw product various.\nHeart line partner. Require great main many. Campaign attack spend take.\nLeg on seat person father. Across star learn such land continue. Threat season rest if.',
    'email': 'watsonbrandi@example.net',
    'phone_number': '001-680-295-8807x411',
    'json': {
    'name': 'Misty Franklin',
    'address': '78697 Leslie Forks\nNew Kendra, OK 21853',
},
    'key96119': 'value15642',
    'key8509': 'value37909',
    'key92319': 'value39474',
    'key99055': 'value73233',
    'key39746': 'value970',
    'key93876': 'value45073',
},
    {
    'id': 17527488720733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Shaun Hernandez II',
    'address': '7216 Moore Unions Apt. 491\nSouth Christopherhaven, GA 94063',
    'text': 'Capital close child rest smile. Show either indicate look senior. Lot economic scene skin church ability health player. Clearly international effect everyone media hospital.',
    'email': 'bullockderek@example.org',
    'phone_number': '+1-473-833-5195x541',
    'json': {
    'name': 'Kimberly Molina',
    'address': '06084 Kelsey Court Apt. 630\nNorth Jeffrey, VI 27553',
},
    'key87602': 'value53536',
    'key39944': 'value59781',
    'key91844': 'value46090',
    'key9464': 'value63838',
    'key21798': 'value77301',
    'key59152': 'value17900',
},
    {
    'id': 17527488720745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Daniel Strickland',
    'address': '41507 Kendra Meadow\nNew Jessicabury, WV 92487',
    'text': 'Himself week if lay star. Send difficult only east tend part company.\nControl role tell power detail. Girl ago have score southern.',
    'email': 'dayrachel@example.net',
    'phone_number': '+1-613-440-5313x7603',
    'json': {
    'name': 'Nicole Calderon',
    'address': '5544 Porter Summit Suite 780\nPort Carolyn, MS 98984',
},
    'key59418': 'value54399',
    'key44326': 'value10833',
    'key34355': 'value27537',
    'key8344': 'value35239',
    'key53800': 'value97504',
    'key50795': 'value90714',
},
    {
    'id': 17527488720757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Karen Jones',
    'address': '6128 Johnson Crossing\nChristophershire, AR 83532',
    'text': 'Address senior discuss story author eye term. Career pass none decision hospital knowledge situation. Actually miss write my.',
    'email': 'browndennis@example.org',
    'phone_number': '845.403.5417x908',
    'json': {
    'name': 'Tamara Mueller',
    'address': '2780 Rodriguez Lakes\nGoodwinshire, RI 30847',
},
    'key53242': 'value26464',
    'key59016': 'value79289',
    'key48713': 'value75807',
    'key14739': 'value9023',
},
    {
    'id': 17527488720768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Brian Williams',
    'address': '855 Paul Crest Apt. 420\nNew Eddie, MD 09866',
    'text': 'Large radio local coach community senior item accept. Politics specific skill protect high argue cultural result. Item also military if.',
    'email': 'shawn06@example.org',
    'phone_number': '+1-246-734-3993',
    'json': {
    'name': 'Brandon Jefferson',
    'address': 'Unit 8151 Box 7540\nDPO AP 17945',
},
    'key29841': 'value95435',
},
    {
    'id': 17527488720776,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Julia Hernandez',
    'address': '3562 Gates Meadow Apt. 874\nNorth Jennifer, HI 59102',
    'text': 'Fly charge until then hit protect door. Do dog campaign. Analysis customer risk seek deep project career.',
    'email': 'chad75@example.org',
    'phone_number': '315.595.8801x3029',
    'json': {
    'name': 'Trevor Foster',
    'address': '485 Juan Freeway Apt. 456\nNew Joel, NH 10742',
},
    'key31841': 'value23346',
    'key51007': 'value96236',
    'key79184': 'value78887',
    'key77395': 'value1146',
    'key12988': 'value26413',
    'key18396': 'value22794',
},
    {
    'id': 17527488720787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Angela Ramirez',
    'address': '2493 Tran Loaf\nSouth Linda, ND 96184',
    'text': 'Animal see care couple three culture. That whole will region measure. Poor who for change full yeah.',
    'email': 'michael33@example.com',
    'phone_number': '563.307.4311x8214',
    'json': {
    'name': 'Rachel Ponce',
    'address': '034 Michelle Stravenue Apt. 422\nEast Melissa, ND 13835',
},
    'key80376': 'value91029',
    'key71472': 'value71387',
    'key56977': 'value50886',
    'key79635': 'value21451',
    'key22124': 'value27200',
    'key16356': 'value92236',
    'key54812': 'value83227',
},
    {
    'id': 17527488720797,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Mallory Ellis',
    'address': '946 Elizabeth Extension Apt. 907\nPort Madisonport, TN 37841',
    'text': 'Never catch major race him respond.\nConference agency practice player interesting. Professional able local view former similar air.',
    'email': 'drichard@example.net',
    'phone_number': '+1-926-252-8637x1515',
    'json': {
    'name': 'Teresa Holmes',
    'address': '7226 Patricia Lake\nDonnatown, HI 82154',
},
    'key23271': 'value83618',
    'key60914': 'value72604',
    'key26905': 'value55567',
    'key24165': 'value54924',
    'key16381': 'value69402',
    'key51043': 'value4239',
    'key81124': 'value21804',
    'key29207': 'value17770',
},
    {
    'id': 17527488720809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Melinda Evans',
    'address': '9251 Todd Stream Suite 656\nMaryborough, NY 39742',
    'text': 'Herself until another case theory everybody. Might group center get goal office you. Manager professional purpose stage learn trouble alone.',
    'email': 'jordan64@example.org',
    'phone_number': '+1-265-845-0904x1321',
    'json': {
    'name': 'Susan Harper',
    'address': '657 Thomas Islands\nWest Christopherstad, AS 75038',
},
    'key42758': 'value18943',
    'key46200': 'value85858',
    'key44522': 'value93076',
    'key55774': 'value97670',
    'key56326': 'value28266',
    'key48973': 'value66610',
},
    {
    'id': 17527488720822,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'William Turner',
    'address': '05097 Dennis Corners\nLake Amy, PR 08577',
    'text': 'Positive population door easy share more lead one. Decade know friend quickly moment join.',
    'email': 'brewershelby@example.org',
    'phone_number': '3953913614',
    'json': {
    'name': 'Timothy Fritz',
    'address': '185 Dawn Fords Suite 919\nTonyaberg, AR 73799',
},
    'key61421': 'value30699',
    'key32464': 'value62906',
    'key53951': 'value60524',
    'key45978': 'value66278',
    'key68410': 'value74888',
    'key19067': 'value9083',
},
    {
    'id': 17527488720835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Susan Young',
    'address': '45524 Pace Mission\nEast Crystalstad, KS 80148',
    'text': 'Hope around hospital song eight democratic. Memory never religious. Move animal direction gun contain meeting.',
    'email': 'cwong@example.net',
    'phone_number': '5524905279',
    'json': {
    'name': 'Nancy Williams',
    'address': '518 Nguyen Circle\nLopezburgh, DE 42876',
},
    'key26639': 'value43688',
    'key12500': 'value53188',
},
    {
    'id': 17527488720848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Elizabeth Parsons',
    'address': '79948 Robert Rue Apt. 862\nSouth Steven, WV 76344',
    'text': 'Between tree ok speak month phone of decision. Whom reality level different. During school response during.',
    'email': 'katherine61@example.com',
    'phone_number': '567.227.1137x0221',
    'json': {
    'name': 'Lisa Mejia',
    'address': 'PSC 8339, Box 5339\nAPO AP 18133',
},
    'key53483': 'value54148',
    'key15766': 'value89610',
    'key97433': 'value42714',
    'key43149': 'value83431',
    'key36259': 'value99445',
    'key64378': 'value45865',
},
    {
    'id': 17527488720859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Dennis Walton',
    'address': '00941 Jennifer Motorway\nHartchester, MH 04502',
    'text': 'Room economy area radio. Consumer property western environment last fight white. Girl minute find find reveal.\nNear increase lead win local. Month every nice city at.\nIf often property feel.',
    'email': 'yvonnebrown@example.org',
    'phone_number': '714.987.7876',
    'json': {
    'name': 'Samuel Campbell DDS',
    'address': '97685 Stephen Landing\nDavidburgh, MA 48864',
},
    'key10193': 'value22133',
    'key49363': 'value91334',
    'key62883': 'value76313',
    'key12452': 'value478',
    'key38544': 'value62858',
    'key79089': 'value76246',
    'key49606': 'value27749',
    'key94464': 'value71893',
},
    {
    'id': 17527488720873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Don Ford',
    'address': '4313 Christina Camp Suite 491\nLake Brandymouth, KS 16918',
    'text': 'Stage beautiful wear above red player. Fact student culture thing understand health type. Material care catch study. Manager they might direction up.',
    'email': 'wcruz@example.com',
    'phone_number': '001-341-769-4113x07410',
    'json': {
    'name': 'Kathleen Lewis',
    'address': '161 Richard Ports\nEast Alexandra, LA 98334',
},
    'key60905': 'value54436',
    'key48999': 'value18300',
    'key81326': 'value82368',
    'key15933': 'value2571',
},
    {
    'id': 17527488720885,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Brittany Miller',
    'address': '11978 Shelly Mountain Suite 465\nSouth Anthony, VA 79751',
    'text': 'Create management help woman. Audience affect song.\nFeeling well four about interesting phone. Cut industry music light water watch. Although night manager base mother fact.\nTax nor yes others feel.',
    'email': 'rebeccawright@example.org',
    'phone_number': '(451)770-7678',
    'json': {
    'name': 'Francisco Anderson',
    'address': '404 Maria Lodge\nLeefort, IN 97362',
},
    'key70847': 'value65043',
    'key48748': 'value65832',
    'key62140': 'value9182',
    'key45469': 'value88195',
    'key15810': 'value6662',
    'key36186': 'value35882',
    'key96429': 'value15770',
},
    {
    'id': 17527488720897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Nicole Thompson',
    'address': '4897 Turner Greens\nSouth Christopher, CT 58279',
    'text': 'Spend create knowledge concern. Stage teacher sometimes plant state management cell require.\nAlong factor goal happy mouth. Nor already voice. President follow number firm majority again your.',
    'email': 'christopherramirez@example.org',
    'phone_number': '(235)970-9103',
    'json': {
    'name': 'Seth Thompson Jr.',
    'address': '833 Michael Spur\nJeffreymouth, CA 79313',
},
    'key56252': 'value65628',
},
    {
    'id': 17527488720908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kimberly Mcpherson',
    'address': '862 Sara Hills Suite 312\nSouth Kellyport, AK 69510',
    'text': 'Shoulder everyone gun picture more total note. Nor man speech poor figure near.\nPopulation individual street by often. Because evidence next can movement you.',
    'email': 'pacevirginia@example.org',
    'phone_number': '(601)381-7715',
    'json': {
    'name': 'Joseph Howard',
    'address': '65213 Barry Mission\nEdwardburgh, PR 60497',
},
    'key45083': 'value89110',
    'key15283': 'value15269',
    'key59309': 'value54730',
    'key3677': 'value74363',
    'key81393': 'value14527',
},
    {
    'id': 17527488720919,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'David Morgan',
    'address': '0818 Hill Tunnel Suite 826\nPort Jeanette, MN 36458',
    'text': 'Want direction stay husband. Degree person sport work. First environmental financial example design discuss debate arm.',
    'email': 'tthomas@example.org',
    'phone_number': '580.258.7872x05491',
    'json': {
    'name': 'Jason Martinez',
    'address': '5932 Jamie View Suite 202\nSouth Dillon, SC 56829',
},
    'key51926': 'value73483',
    'key64061': 'value53366',
},
    {
    'id': 17527488720930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Jose Baker',
    'address': '2147 Miller Motorway\nPaigeberg, MT 56503',
    'text': 'Idea create gun various. Grow half environmental present own radio dog. Peace will education ball talk chair late.',
    'email': 'trujillojulie@example.com',
    'phone_number': '+1-902-641-0391',
    'json': {
    'name': 'Jennifer Larson',
    'address': '39438 Lauren Ford\nStaceyland, SC 33431',
},
    'key22006': 'value56486',
    'key32642': 'value69164',
    'key14314': 'value9514',
    'key10330': 'value83843',
    'key67643': 'value97352',
    'key77326': 'value33624',
    'key32985': 'value14821',
},
    {
    'id': 17527488720941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Matthew Perkins',
    'address': '704 Moore Mountains Suite 794\nLake Rebeccaport, PA 54006',
    'text': 'Bed do enough scene research his decide.\nMovie public several follow number. But ago suggest key inside.\nMedia order never crime pay. Finish society fish since draw nation may summer.',
    'email': 'kristathomas@example.com',
    'phone_number': '726-418-7897',
    'json': {
    'name': 'Charles Waters',
    'address': '5518 Jasmine Spurs\nNew Carmenfort, LA 89877',
},
    'key23608': 'value1181',
    'key40099': 'value48701',
    'key72099': 'value21996',
    'key55697': 'value45853',
    'key76838': 'value61414',
},
    {
    'id': 17527488720952,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jennifer Church',
    'address': 'Unit 1896 Box 9138\nDPO AA 67356',
    'text': 'Art really customer someone process wish task include. Money major analysis within up physical. Character court because describe exactly tree since.\nSystem happy these key suddenly meeting down.',
    'email': 'crystal69@example.com',
    'phone_number': '(450)264-1752x966',
    'json': {
    'name': 'Dennis Adkins',
    'address': '865 Nathan Camp\nJosephside, AS 87240',
},
    'key91022': 'value46500',
    'key80355': 'value85885',
    'key19194': 'value19459',
    'key15108': 'value18008',
},
    {
    'id': 17527488720961,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Frederick Clarke',
    'address': '182 Summer Valley\nPaulmouth, CA 76868',
    'text': 'Very mention majority however about medical reach. Everybody fund impact week time son.',
    'email': 'josesimpson@example.com',
    'phone_number': '+1-563-828-8620x748',
    'json': {
    'name': 'Robert Ayers',
    'address': '277 Maddox Dale Apt. 293\nLake Mariaburgh, NY 85284',
},
    'key21897': 'value92369',
    'key78643': 'value99661',
    'key51714': 'value98877',
    'key46392': 'value90404',
},
    {
    'id': 17527488720971,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Judy Bonilla',
    'address': '3472 Hampton Plains Apt. 662\nSouth Lucas, ID 22999',
    'text': 'Form if at. Tax sure management it difference research drug. President ability catch street stock run. What between just off analysis specific relationship.',
    'email': 'kristajohnson@example.org',
    'phone_number': '+1-346-413-4485x005',
    'json': {
    'name': 'Ashley Shea',
    'address': '9435 Brian Parks Apt. 844\nGilbertborough, NC 38081',
},
    'key58648': 'value68990',
    'key25425': 'value93530',
    'key56971': 'value29728',
    'key99848': 'value60166',
    'key40980': 'value12200',
    'key70109': 'value12929',
    'key66727': 'value55133',
    'key90273': 'value33754',
    'key87476': 'value44117',
},
    {
    'id': 17527488720983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Stacy Chavez',
    'address': '17983 Ruiz Springs Suite 078\nJohnsonland, OR 82904',
    'text': 'Enough night painting should state business. Challenge population car.',
    'email': 'kelleywilliam@example.net',
    'phone_number': '(930)348-4639',
    'json': {
    'name': 'Christina Bird',
    'address': '4337 Gonzalez Ways Apt. 519\nLake Lisa, NE 12859',
},
    'key26519': 'value1236',
},
    {
    'id': 17527488720995,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Anna Matthews',
    'address': '03560 Wilson Coves\nLanestad, ND 45474',
    'text': 'Treat girl place computer ok control. Task represent response TV. Growth recent generation manage could. Action break majority name prove.',
    'email': 'tararichardson@example.net',
    'phone_number': '001-255-370-3586x13701',
    'json': {
    'name': 'Kayla Johnson',
    'address': '01844 Sweeney Heights\nPort Bradtown, CT 51426',
},
    'key57027': 'value93771',
    'key48736': 'value62814',
    'key52638': 'value44740',
    'key98726': 'value93779',
},
    {
    'id': 17527488721007,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Dr. Michael Taylor',
    'address': '84136 Ford Inlet Suite 609\nAmandatown, MT 85823',
    'text': 'Stock whole number. Eight kitchen it affect break audience.\nSimply want family early will seat. White word practice seek member capital American.',
    'email': 'xrobinson@example.com',
    'phone_number': '(697)469-4269',
    'json': {
    'name': 'Jeremiah Thomas',
    'address': '65406 Max Roads Apt. 593\nAguilarhaven, IN 26731',
},
    'key87461': 'value36563',
    'key60986': 'value78611',
    'key23484': 'value49089',
    'key98903': 'value94769',
    'key37328': 'value67039',
},
    {
    'id': 17527488721018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Larry Smith',
    'address': '39434 Kristina Court\nSouth Donald, IA 58184',
    'text': 'Wrong police forward story friend grow. Attack support president indeed not. Floor maintain loss.\nSon approach fund especially resource budget adult. Our feeling because sit career four.',
    'email': 'cordovajeremy@example.org',
    'phone_number': '+1-218-399-5266x57151',
    'json': {
    'name': 'Kenneth Reeves',
    'address': '0957 Miller Plaza\nWalkerview, CO 78451',
},
    'key23650': 'value26481',
    'key40107': 'value88246',
    'key53043': 'value15161',
},
    {
    'id': 17527488721030,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Jeremy Barron',
    'address': '86340 Michelle Meadows Apt. 269\nSouth Seanfurt, VT 24282',
    'text': 'Face current second than effort.\nAnd court short its speak indeed. New various record focus front specific. Spend western fire position history quality.',
    'email': 'susan05@example.com',
    'phone_number': '+1-948-827-1331x93158',
    'json': {
    'name': 'Crystal Williams',
    'address': '0433 Carter Motorway Suite 080\nCurtisburgh, PR 78281',
},
    'key53082': 'value50316',
},
    {
    'id': 17527488721041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Gina Quinn',
    'address': '1765 Tanya View\nWest Karen, MO 18283',
    'text': 'General look young majority. Traditional leader military body start. Floor professor few believe study indeed ok.\nNor maintain ten last. Prepare hair this property.',
    'email': 'anna58@example.com',
    'phone_number': '513-403-0592',
    'json': {
    'name': 'Jose Richards',
    'address': '546 Livingston Trail\nNew Jeanneview, SC 13217',
},
    'key46115': 'value40175',
    'key11231': 'value15290',
    'key88659': 'value66858',
    'key63048': 'value64541',
    'key23378': 'value40369',
    'key76094': 'value68482',
    'key24997': 'value11436',
    'key95864': 'value43581',
},
    {
    'id': 17527488721051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'John Sims Jr.',
    'address': '0838 Hayes Shore\nJosestad, TX 64507',
    'text': 'A more budget such red admit almost so. Similar during wrong trip. Whatever blue hand.\nEvidence than southern system room. Account fast west.',
    'email': 'carolyn66@example.org',
    'phone_number': '(600)762-3185x860',
    'json': {
    'name': 'Sandra Williams',
    'address': '28062 Brenda Ferry Apt. 508\nWest Reneeberg, WA 99129',
},
    'key89093': 'value92350',
    'key87759': 'value75063',
    'key97147': 'value22664',
    'key71835': 'value46111',
    'key58117': 'value9346',
    'key72477': 'value73825',
    'key77240': 'value32108',
    'key4730': 'value33667',
    'key66091': 'value56698',
},
    {
    'id': 17527488721062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Nina Thomas',
    'address': '810 Gordon Ranch Suite 942\nWest Ellen, IN 01027',
    'text': 'Young how drive success statement include happen. Democrat billion hit happen involve forget design but. Wrong remember yes simple candidate.',
    'email': 'rodriguezcaleb@example.com',
    'phone_number': '(517)765-4159x1656',
    'json': {
    'name': 'Kristi Brown',
    'address': '86627 Natalie Brooks\nLake Kevinview, HI 21863',
},
    'key23278': 'value14923',
    'key84456': 'value98044',
    'key90893': 'value70601',
    'key97416': 'value30120',
    'key57607': 'value61640',
    'key9441': 'value5894',
    'key24427': 'value13112',
    'key7226': 'value58332',
},
    {
    'id': 17527488721073,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Kenneth Bennett',
    'address': 'Unit 0582 Box 3575\nDPO AA 17194',
    'text': 'Evidence tough business leave enough Congress. Visit might sometimes second vote probably. But send score sign learn under.',
    'email': 'davisronald@example.net',
    'phone_number': '(984)542-2808',
    'json': {
    'name': 'Jacob Johnson',
    'address': '25223 Preston Manors Suite 944\nPort Christyberg, FL 72229',
},
    'key8578': 'value26708',
    'key99169': 'value88708',
    'key3363': 'value88604',
    'key1792': 'value97729',
    'key32795': 'value25032',
    'key40377': 'value12601',
    'key6817': 'value81285',
    'key11877': 'value58288',
    'key14434': 'value59807',
    'key59149': 'value32013',
},
    {
    'id': 17527488721083,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Barry Wall',
    'address': '3236 Brian Orchard\nPort Matthew, MS 52143',
    'text': 'Market single think democratic whom nature. Window moment personal argue task. Us but choose soon talk.',
    'email': 'cody94@example.net',
    'phone_number': '001-300-345-1669',
    'json': {
    'name': 'Alan Carson',
    'address': '091 Lee Pike Suite 474\nNorth Andrea, KY 67219',
},
    'key52477': 'value8898',
    'key42472': 'value38319',
    'key11344': 'value25038',
    'key30405': 'value75876',
},
    {
    'id': 17527488721093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Douglas Smith',
    'address': '423 Wilson Brook\nShawchester, AL 62543',
    'text': 'Performance region office doctor there. Movement drop style happy story score health back. Majority center some traditional.',
    'email': 'tristan07@example.org',
    'phone_number': '254-316-1748x6396',
    'json': {
    'name': 'Joel Weaver',
    'address': '290 Richards Mount\nEdwardsmouth, TN 26269',
},
    'key24901': 'value19020',
    'key76603': 'value7276',
    'key19643': 'value56730',
    'key49759': 'value20336',
    'key39240': 'value63618',
    'key34056': 'value80135',
},
    {
    'id': 17527488721104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Amy Stafford',
    'address': '5999 Kevin Grove Apt. 229\nDavidberg, GU 37899',
    'text': 'Both accept buy kid blood traditional education fall. Plant team where carry drive improve. Challenge close bit focus can modern remember floor.\nFather represent mission source you off.',
    'email': 'johnsonfaith@example.net',
    'phone_number': '591-291-2773x37812',
    'json': {
    'name': 'Daniel Lucas',
    'address': '9388 Brad Station Apt. 703\nNorth Christopher, HI 38453',
},
    'key76560': 'value6873',
    'key91023': 'value97357',
    'key79937': 'value86040',
    'key56168': 'value71317',
    'key81920': 'value92328',
    'key94976': 'value20319',
    'key4291': 'value55796',
},
    {
    'id': 17527488721115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Tiffany Cooper',
    'address': '36685 Lloyd Throughway Suite 932\nRalphburgh, UT 21322',
    'text': 'Common leader than Congress writer tell. As least finally glass within.',
    'email': 'meganward@example.com',
    'phone_number': '001-311-588-9224',
    'json': {
    'name': 'Robert Freeman',
    'address': '1487 Adams Crest\nDiazburgh, WI 11480',
},
    'key97841': 'value404',
    'key21520': 'value91660',
    'key37373': 'value65478',
    'key11679': 'value23633',
},
    {
    'id': 17527488721127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Jennifer Mckenzie',
    'address': '77173 Phillip Port\nPatrickmouth, VT 82990',
    'text': 'Company may all possible purpose record weight. Bank life dog rest. Around war since necessary statement family management.\nCommon western want agreement. Type night picture do.',
    'email': 'joshua39@example.org',
    'phone_number': '613-203-0177',
    'json': {
    'name': 'Sophia Lucas',
    'address': '17462 Julia Bypass\nPereztown, NM 23626',
},
    'key97448': 'value91867',
    'key76823': 'value72696',
    'key21575': 'value37884',
    'key70330': 'value69799',
    'key73476': 'value50327',
    'key20770': 'value72279',
},
    {
    'id': 17527488721137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Matthew Gonzalez',
    'address': '807 Wendy Field Apt. 715\nPort Tyroneborough, HI 39516',
    'text': 'Experience idea both turn green choice determine. Serious study whole through party very never.\nRed must before back left. At above forget group discuss sell.',
    'email': 'telliott@example.net',
    'phone_number': '+1-846-262-3455x5701',
    'json': {
    'name': 'David Oconnor',
    'address': '460 Michael Fields Apt. 758\nWest Stacy, ID 70462',
},
    'key29137': 'value82224',
    'key36100': 'value15630',
},
    {
    'id': 17527488721147,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Joe Jones',
    'address': '597 Sheila Turnpike Suite 546\nNorth Courtneystad, AS 57197',
    'text': 'Poor want discuss civil ever. Game ball coach feeling.\nWhole where especially discover economic scientist control campaign. No than Mrs use case husband in.',
    'email': 'justin69@example.com',
    'phone_number': '(890)627-6066x9733',
    'json': {
    'name': 'Meghan King',
    'address': '027 Martin Ramp\nLake Troyborough, HI 01805',
},
    'key95756': 'value63237',
    'key77286': 'value55126',
    'key20334': 'value5199',
    'key45381': 'value63517',
    'key51547': 'value83088',
    'key18710': 'value15940',
    'key96355': 'value6361',
},
    {
    'id': 17527488721157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Dr. Amanda Miller',
    'address': '7618 Kevin Spur Suite 855\nEast Travis, SD 99074',
    'text': 'Impact push return course leader both. Whether support power agent interesting lead suddenly almost. Much answer girl result same center.',
    'email': 'kevinolson@example.com',
    'phone_number': '801.294.3558',
    'json': {
    'name': 'Angel Mitchell',
    'address': '17749 Greene Lodge\nFraziermouth, ND 06417',
},
    'key45942': 'value32048',
    'key52479': 'value45364',
    'key31792': 'value56353',
    'key84810': 'value56339',
    'key94645': 'value70466',
    'key49830': 'value8381',
    'key61114': 'value27478',
    'key42871': 'value16520',
    'key13923': 'value64568',
    'key24355': 'value20865',
},
    {
    'id': 17527488721169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Donna Stone',
    'address': '6720 Melissa Common Suite 362\nCatherinefurt, IN 23359',
    'text': 'Weight sign direction according. Record would director believe term hope. Kind a affect realize door happy member. Magazine arm resource ground available.',
    'email': 'rlopez@example.org',
    'phone_number': '680.531.9638',
    'json': {
    'name': 'Shannon Walker',
    'address': '2861 Lawrence Road Apt. 298\nEast Bridget, FM 44055',
},
    'key27547': 'value11431',
    'key56475': 'value3816',
},
    {
    'id': 17527488721180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Howard Walker',
    'address': '85710 Cindy Rest Suite 060\nChadbury, KS 17692',
    'text': 'Road six laugh win. Better get service trade remember hand. Author affect fill.\nCar expert camera consider. Member order reach dark situation structure become.',
    'email': 'nrogers@example.com',
    'phone_number': '600.307.9125x404',
    'json': {
    'name': 'Jonathan Oneal',
    'address': '353 Corey Spring Suite 855\nWest Amandaburgh, CT 58763',
},
    'key56319': 'value55626',
    'key46581': 'value86022',
    'key98190': 'value8772',
    'key18558': 'value71672',
    'key27105': 'value94159',
    'key9798': 'value46230',
    'key49164': 'value652',
    'key37283': 'value6307',
    'key73481': 'value92697',
    'key24829': 'value71532',
},
    {
    'id': 17527488721190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Patrick Martinez',
    'address': '326 Caitlin Shoal Apt. 705\nJohnsonfort, AZ 28204',
    'text': 'Black computer guy trade fall here former. Animal tree always feel factor new claim.\nTown consider culture value per someone idea. Hot media product at able pay. Dark too nor pull.',
    'email': 'jamesgarrett@example.com',
    'phone_number': '3414020506',
    'json': {
    'name': 'Emily Oliver',
    'address': '3373 Amy Parkways\nGreenmouth, NV 27085',
},
    'key95494': 'value66542',
},
    {
    'id': 17527488721202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kimberly Weeks',
    'address': '210 Meza Club\nLake Anthonyton, OR 28179',
    'text': 'Individual value finish along town discussion collection. Upon not financial matter Republican.\nMuch actually argue herself cell gun fall. Board choose instead education possible.',
    'email': 'ogilbert@example.org',
    'phone_number': '897.603.6105',
    'json': {
    'name': 'Kevin Richmond',
    'address': '6327 Evelyn Inlet Apt. 674\nNew Matthewville, OK 23176',
},
    'key55884': 'value45877',
    'key81734': 'value91598',
    'key48774': 'value18263',
    'key58550': 'value25346',
    'key21748': 'value80121',
},
    {
    'id': 17527488721213,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'David Gonzales',
    'address': '9534 Carson Wells\nWest Robert, PR 44480',
    'text': 'Trade will technology difficult whole different. Space indeed father issue rest method account.\nSound individual impact. Force book city listen number design point.',
    'email': 'bradshawveronica@example.net',
    'phone_number': '(682)867-5146',
    'json': {
    'name': 'Jacob Santos',
    'address': '2799 Jaclyn Via\nDebbiestad, OH 73224',
},
    'key90105': 'value97496',
    'key1923': 'value41052',
    'key94739': 'value49184',
    'key4837': 'value97913',
    'key38045': 'value45059',
    'key16523': 'value6296',
    'key81372': 'value3663',
    'key45832': 'value58767',
    'key87059': 'value79458',
    'key52802': 'value29616',
},
    {
    'id': 17527488721224,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Luis Wade',
    'address': '313 Williamson Port Apt. 931\nMorenohaven, NM 81591',
    'text': 'Manage someone either follow wrong thus. Old rather camera everyone consumer.',
    'email': 'lisa91@example.com',
    'phone_number': '4319429884',
    'json': {
    'name': 'Sandra Miller',
    'address': '445 Johnson Forest\nShawnshire, CT 98360',
},
    'key63134': 'value23732',
    'key6372': 'value68311',
    'key62173': 'value93262',
    'key79316': 'value31335',
    'key53145': 'value36514',
    'key8202': 'value15198',
    'key95959': 'value80519',
    'key99422': 'value68773',
    'key61012': 'value956',
},
    {
    'id': 17527488721235,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Justin Bentley',
    'address': '8122 Garcia Turnpike\nJosephside, MN 27796',
    'text': 'Her increase number medical carry. Produce family grow heavy base for upon. Case debate ten simple scientist situation analysis before.\nForm teacher way traditional entire. Tend ok close.',
    'email': 'alyssa27@example.net',
    'phone_number': '893.879.9959x9892',
    'json': {
    'name': 'Natasha Baker',
    'address': '543 Walker Ramp\nMonicafort, OK 32216',
},
    'key51516': 'value72087',
    'key71868': 'value86525',
    'key29001': 'value20477',
},
    {
    'id': 17527488721246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Andrew Garza',
    'address': '8668 Danny Valleys\nNew Amymouth, MI 86131',
    'text': 'Civil be standard watch mention since hour.\nMy dinner section later arm join. Stay term public experience become seem field.',
    'email': 'feliciagarrett@example.com',
    'phone_number': '329-374-1264',
    'json': {
    'name': 'Andrew Shepherd DVM',
    'address': '514 David Mall\nHunterberg, AS 77368',
},
    'key87158': 'value48871',
    'key51249': 'value26982',
    'key23666': 'value2493',
    'key55818': 'value69462',
},
    {
    'id': 17527488721257,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Michael Barker',
    'address': '145 Julie Vista Suite 560\nGainesberg, PA 70812',
    'text': 'Crime region reveal. Help church people energy scene.\nPut mean his lay moment officer apply. Class investment very people. Need in try speak account. Real onto friend season father television.',
    'email': 'schmidtkimberly@example.com',
    'phone_number': '+1-624-664-9456x4846',
    'json': {
    'name': 'Carlos Robinson',
    'address': '75410 Thomas Vista\nEast Michaelland, OR 39751',
},
    'key68437': 'value43180',
    'key47556': 'value46634',
    'key22349': 'value38375',
    'key69188': 'value23246',
    'key58247': 'value94667',
},
    {
    'id': 17527488721269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'John Blackwell',
    'address': 'USNV Hansen\nFPO AE 53933',
    'text': 'He must free institution. Front ground water outside continue. No form generation face doctor support night. Beat girl hospital something skin.',
    'email': 'meganwashington@example.net',
    'phone_number': '662.703.5698x058',
    'json': {
    'name': 'Jose Cook',
    'address': '6878 Clay Row Apt. 055\nLake Davidhaven, SC 22598',
},
    'key45538': 'value86188',
    'key24541': 'value33621',
    'key32296': 'value48129',
    'key8619': 'value61851',
    'key67941': 'value89598',
    'key74615': 'value52541',
    'key34065': 'value42659',
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
    'RequestId': '8ae04a8c-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_05_982544SzUjqHHy',
    'filter': 'uid in [1,2,3,4]',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '8ae04a8c-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_05_982544SzUjqHHy',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid in [1,2,3,4]]_1752748878.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUidIn12341752748878Json()
    test.run_tests()
