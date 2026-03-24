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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 01]_1752748836_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 01]_1752748836.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid011752748836Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 01]_1752748836.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 01]_1752748836.json"
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
    'data': [
    {
    'id': 17527488282652,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Susan Barnes',
    'address': '947 Villanueva Underpass Apt. 655\nJoshuachester, NV 23289',
    'text': 'Write available hold fact fact spring on. Road environmental relate voice face I. Section lead show leader since add crime.',
    'email': 'nbrown@example.net',
    'phone_number': '278-501-0615',
    'json': {
    'name': 'John Reed DVM',
    'address': '9280 Maxwell Lodge\nEast Sallyfort, UT 92370',
},
    'key37212': 'value54518',
    'key29219': 'value99072',
    'key91996': 'value37716',
    'key11331': 'value55560',
},
    {
    'id': 17527488282669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sherry Phillips',
    'address': '010 Sheila Well Apt. 176\nNorth Frederickmouth, CA 72624',
    'text': 'Painting area real suggest.\nTry current recent push article fire realize. Think do fish. Picture couple enough week capital.',
    'email': 'amandasims@example.com',
    'phone_number': '(610)831-2362x50302',
    'json': {
    'name': 'Mr. Bobby Adams',
    'address': '3693 Mooney Way Apt. 694\nNorth Christopher, MH 49735',
},
    'key57892': 'value11088',
    'key89385': 'value34270',
},
    {
    'id': 17527488282682,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Gerald Alvarado',
    'address': '865 Dixon Wall\nPort Davidhaven, WY 24867',
    'text': 'Week most economy consumer popular direction perform. Usually fast collection system against.\nPrice create owner lose. Strategy go material vote building music.',
    'email': 'ymartinez@example.org',
    'phone_number': '001-924-752-9986x52737',
    'json': {
    'name': 'Michelle Hicks',
    'address': '679 Connie Burgs Suite 906\nKarenport, RI 01767',
},
    'key22412': 'value6991',
},
    {
    'id': 17527488282694,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jennifer Christian',
    'address': '4402 Jessica Road\nPort Tammyshire, MP 25845',
    'text': 'Director low form likely. Put fish area southern knowledge degree. Speak third scene modern appear summer.',
    'email': 'marie08@example.net',
    'phone_number': '285-395-7088x86841',
    'json': {
    'name': 'Ann Castillo',
    'address': '94625 Ellen Extensions\nNorth Jacobstad, SD 45874',
},
    'key67117': 'value32264',
    'key99107': 'value63780',
    'key33833': 'value84834',
    'key37916': 'value32364',
    'key36649': 'value2298',
    'key87048': 'value58186',
    'key41610': 'value7075',
    'key29100': 'value16188',
},
    {
    'id': 17527488282707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Mary Anderson',
    'address': '186 Rodriguez Rue\nSouth Lindsay, OH 88200',
    'text': 'Young whom instead recently according place hit avoid. Size add wish.\nAlso question society issue couple. Son hope whether good opportunity. Prove throw water wife order animal scene.',
    'email': 'theresahunter@example.org',
    'phone_number': '923-416-7223x0973',
    'json': {
    'name': 'Todd Smith',
    'address': '38259 Brian Inlet Apt. 441\nJamesmouth, NC 86326',
},
    'key96934': 'value51321',
    'key69067': 'value51560',
    'key78125': 'value95748',
    'key26750': 'value49017',
    'key111': 'value59367',
    'key10277': 'value95127',
    'key84796': 'value17339',
    'key65868': 'value54286',
    'key23223': 'value55138',
},
    {
    'id': 17527488282722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Rachel Rodriguez',
    'address': '46989 Waters Way Suite 951\nWest Penny, OK 70207',
    'text': 'Position simply society establish. Region physical physical before. Artist serve population.',
    'email': 'shawnhart@example.org',
    'phone_number': '001-950-726-1660',
    'json': {
    'name': 'Karen Brown',
    'address': '2955 Lopez View\nPort Jasonport, VT 23981',
},
    'key99845': 'value67589',
    'key99618': 'value82740',
    'key84396': 'value557',
    'key24041': 'value1042',
    'key25180': 'value93765',
    'key48675': 'value9847',
    'key33120': 'value71695',
    'key25584': 'value44212',
    'key45173': 'value21468',
},
    {
    'id': 17527488282736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Christian Miller',
    'address': '78559 Stevens Way\nWest Jamesbury, PW 84384',
    'text': 'What beyond appear general way finish entire.\nOffice main conference do account. Itself blood maintain our least. Produce book mind crime view.',
    'email': 'rodriguezmark@example.org',
    'phone_number': '456-443-1721',
    'json': {
    'name': 'Claudia Schmidt',
    'address': '3509 Joshua Ferry\nBaileyburgh, NM 39115',
},
    'key68932': 'value16271',
},
    {
    'id': 17527488282749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Nicole Mills',
    'address': '99670 Angelica Plains Apt. 141\nMichaelview, MA 88832',
    'text': 'Improve stand full past building address myself. Real election sea hotel improve.\nOf direction management open. Soon consumer its may. Increase herself receive strategy their such.',
    'email': 'smithsophia@example.com',
    'phone_number': '9495125937',
    'json': {
    'name': 'Eric Hall',
    'address': '76293 Miller Harbors\nLake Cesar, MD 75098',
},
    'key16707': 'value66568',
    'key26005': 'value32590',
    'key56572': 'value16118',
    'key14330': 'value52489',
    'key35815': 'value90828',
    'key61597': 'value74217',
    'key18124': 'value7467',
    'key76186': 'value34221',
    'key16813': 'value18109',
    'key97067': 'value2232',
},
    {
    'id': 17527488282761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Taylor Nelson',
    'address': '57524 Garcia Trail Suite 495\nEmilyborough, MD 36153',
    'text': 'Section shake perform summer worry sing sister. Pull tell already each interview best special. Particularly that for arm.\nLike me lot yes.',
    'email': 'lorifowler@example.com',
    'phone_number': '8584744962',
    'json': {
    'name': 'Juan Johnson',
    'address': '31962 William Ferry\nSmithmouth, OR 84851',
},
    'key38847': 'value8606',
    'key80128': 'value14215',
    'key17133': 'value80508',
    'key47358': 'value22827',
},
    {
    'id': 17527488282773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jade Potter',
    'address': '90638 Mcdonald Unions\nLake Shelly, CA 42375',
    'text': 'Thousand word near act contain guy. Laugh week news administration discover pass. Might firm computer suggest lose claim.',
    'email': 'rhodesjessica@example.org',
    'phone_number': '(305)496-8563',
    'json': {
    'name': 'Stephanie Rodriguez',
    'address': '71186 Stone Heights Apt. 455\nLake Tracyside, VT 24633',
},
    'key96571': 'value82763',
    'key64771': 'value31261',
    'key98217': 'value46647',
    'key32102': 'value77941',
    'key50974': 'value34712',
    'key69519': 'value83898',
    'key65427': 'value40272',
},
    {
    'id': 17527488282785,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Michelle Jefferson',
    'address': '834 Pamela Motorway\nAndersonchester, WI 08503',
    'text': 'Challenge field on take those strategy across cultural. Movement inside admit apply item into before accept. Contain painting while its set.',
    'email': 'ryan94@example.org',
    'phone_number': '531.351.5150',
    'json': {
    'name': 'Debra Collins',
    'address': '9379 Gates Fall\nPort Danielle, UT 79996',
},
    'key49261': 'value53629',
    'key20964': 'value42029',
    'key25586': 'value785',
},
    {
    'id': 17527488282799,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Jeffrey Ruiz',
    'address': 'USNS Griffin\nFPO AA 90646',
    'text': 'Hand floor and sort. Night analysis economy thus us woman. Agreement really third professor again why. First effort quite.',
    'email': 'gfoley@example.com',
    'phone_number': '5258782744',
    'json': {
    'name': 'Christopher Oneal',
    'address': '866 Fisher Divide Apt. 250\nWest Kellymouth, DC 46294',
},
    'key74469': 'value39148',
    'key38826': 'value29520',
    'key49551': 'value49417',
    'key56250': 'value39860',
    'key10457': 'value36603',
    'key62201': 'value36156',
    'key42479': 'value24281',
    'key35520': 'value65450',
},
    {
    'id': 17527488282812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Rita Proctor',
    'address': '728 Knapp Creek Suite 187\nRochaborough, LA 86091',
    'text': 'Large environmental end friend prove. Exist relate grow though help. Executive bring table onto agency.',
    'email': 'jeffreyhall@example.org',
    'phone_number': '(858)663-9455x4892',
    'json': {
    'name': 'Jennifer Hernandez',
    'address': '67537 Oconnell Brooks\nRebeccachester, AK 12493',
},
    'key14531': 'value49106',
    'key85326': 'value5277',
    'key64504': 'value16053',
    'key46397': 'value79680',
},
    {
    'id': 17527488282824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Natalie Donovan',
    'address': '6424 Bradford Brooks Apt. 391\nNorth Cynthiaberg, MO 56886',
    'text': 'Relate girl culture note sure. Throw son trip social or.\nReligious need room yeah religious agent film. American nearly season pretty company country. Pm a performance bag benefit toward still.',
    'email': 'rebecca00@example.com',
    'phone_number': '317-285-0576',
    'json': {
    'name': 'Charles Ortiz',
    'address': '7240 Daniel Place\nAllisonberg, VA 55541',
},
    'key45505': 'value400',
    'key71185': 'value48224',
    'key93084': 'value75524',
    'key9608': 'value35101',
    'key39538': 'value58971',
    'key25252': 'value38884',
    'key68210': 'value48653',
    'key10388': 'value62647',
    'key59510': 'value95094',
    'key53354': 'value42292',
},
    {
    'id': 17527488282835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Haley Walker',
    'address': '03416 Ashley Brook\nLake Marissastad, SC 45639',
    'text': 'Early arm mean experience. Threat goal blood best know lawyer go. Specific think chair tell wear direction television.',
    'email': 'stephaniekennedy@example.com',
    'phone_number': '(980)454-5299x2278',
    'json': {
    'name': 'Walter Gonzalez',
    'address': '2224 Anderson Ranch Suite 194\nChristinefort, TX 75158',
},
    'key48924': 'value28982',
    'key6063': 'value58316',
    'key93899': 'value58436',
    'key52561': 'value43522',
    'key60024': 'value2035',
},
    {
    'id': 17527488282847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jessica Mora',
    'address': '98481 Mcdaniel Mills\nGibsonfurt, VT 52299',
    'text': 'Fight off agent reach.\nBeautiful officer standard eight industry leg. Happen relationship poor environmental goal. Important fear prepare opportunity.',
    'email': 'william78@example.com',
    'phone_number': '001-201-893-6037x2305',
    'json': {
    'name': 'Stephen Baker',
    'address': '38259 Marcia Square\nEast David, NV 40463',
},
    'key8771': 'value10851',
    'key45352': 'value62227',
    'key95853': 'value15394',
    'key60086': 'value61552',
    'key83631': 'value61602',
    'key90944': 'value9348',
    'key68050': 'value30135',
    'key39627': 'value6312',
    'key83796': 'value25462',
},
    {
    'id': 17527488282858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'David Murphy',
    'address': '758 Torres Center\nWest Steven, LA 49515',
    'text': 'Take culture five body entire minute. Go pick education rise simple although.',
    'email': 'andrejenkins@example.org',
    'phone_number': '(763)405-0481',
    'json': {
    'name': 'Daniel Leonard',
    'address': '82345 Warren Views\nPort Jamesborough, MH 32469',
},
    'key63979': 'value30010',
    'key1949': 'value83599',
},
    {
    'id': 17527488282869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Glenn Willis',
    'address': '523 Matthew Glens\nCruzhaven, CO 31144',
    'text': 'Kind subject trial positive might. Little white there edge scene matter arrive. Night pick break discuss.',
    'email': 'jamesernest@example.net',
    'phone_number': '(361)657-9901x588',
    'json': {
    'name': 'Sarah Steele',
    'address': '94600 Willis Trail\nStantonberg, TN 43315',
},
    'key41771': 'value81893',
    'key84646': 'value54011',
    'key77812': 'value44209',
    'key90966': 'value85468',
    'key51876': 'value97617',
    'key72835': 'value99180',
    'key58151': 'value11283',
},
    {
    'id': 17527488282881,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Christopher Oconnor',
    'address': '1963 Tammie Wells\nSouth Sarah, AK 28899',
    'text': 'Until spring machine figure moment. Fast foreign fly pay grow reality. Be green position staff south establish travel be. Health goal remain thought these top the commercial.',
    'email': 'edwardsmike@example.org',
    'phone_number': '457.948.9547',
    'json': {
    'name': 'Nicholas Smith',
    'address': '39909 Collier Terrace\nHineschester, IL 08901',
},
    'key96838': 'value34581',
    'key70041': 'value48819',
    'key16729': 'value33107',
    'key17280': 'value36203',
    'key47953': 'value73426',
    'key79773': 'value66415',
},
    {
    'id': 17527488282892,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jonathan Williams',
    'address': '9382 Michael Forge\nTarastad, MA 48347',
    'text': 'Weight drop indicate. Agent cold focus measure direction evidence.\nReal peace enter nor position here down. Mind still race end.',
    'email': 'jamiewall@example.net',
    'phone_number': '(799)518-3614x713',
    'json': {
    'name': 'Elizabeth Morales',
    'address': '69003 Robert Plains Suite 874\nNew Christopher, PW 81353',
},
    'key97713': 'value23593',
    'key16874': 'value86709',
    'key71150': 'value30477',
    'key37602': 'value47651',
},
    {
    'id': 17527488282903,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Thomas James',
    'address': 'Unit 7418 Box 8429\nDPO AE 50125',
    'text': 'Share successful wall water. Much husband machine include offer score but.',
    'email': 'jennifernelson@example.net',
    'phone_number': '(761)784-7619x432',
    'json': {
    'name': 'Erika Warner',
    'address': '45290 Gay Springs Suite 433\nKimberlytown, AL 09040',
},
    'key23679': 'value77309',
    'key72150': 'value9611',
    'key52152': 'value3947',
    'key87120': 'value90365',
    'key61619': 'value36817',
    'key12007': 'value16469',
    'key13982': 'value28499',
    'key59938': 'value46912',
    'key23964': 'value99622',
    'key23491': 'value57253',
},
    {
    'id': 17527488282913,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Marvin Pitts',
    'address': '267 Kayla Springs\nFarrellland, NJ 16525',
    'text': 'Answer class stand cold final could coach. Blue realize front new hear provide arrive.\nEspecially personal study surface. Court worry wife.',
    'email': 'oneilltara@example.org',
    'phone_number': '001-956-604-3680x9257',
    'json': {
    'name': 'Corey Wilkerson',
    'address': '62543 Janice Parkways Apt. 275\nAngelaberg, IA 12766',
},
    'key36119': 'value43119',
    'key80951': 'value12531',
    'key74637': 'value25954',
    'key79453': 'value89432',
    'key6799': 'value81575',
    'key66813': 'value28422',
    'key54129': 'value82394',
},
    {
    'id': 17527488282925,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Raymond Mitchell',
    'address': '656 Cohen Corner Suite 407\nEast Brent, NJ 53892',
    'text': 'Rich benefit current day time. Sea newspaper about company its draw may contain.\nClass page none executive help less. Modern opportunity story be when.',
    'email': 'qcalderon@example.com',
    'phone_number': '(468)825-3586',
    'json': {
    'name': 'Christopher Hicks',
    'address': '064 Carter Expressway Suite 869\nSouth Patricia, MO 61373',
},
    'key88843': 'value4109',
},
    {
    'id': 17527488282936,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Crystal Hunter',
    'address': 'Unit 8288 Box 2117\nDPO AP 09761',
    'text': 'Result his single fly school. Southern very break some boy building character. Better continue manager away bad husband.\nEnjoy parent activity. Professional civil how. Three really much lot course.',
    'email': 'belljennifer@example.net',
    'phone_number': '923.683.1998x2781',
    'json': {
    'name': 'Cameron Kelley',
    'address': '494 David Freeway Suite 941\nJerryshire, NC 25239',
},
    'key35618': 'value1173',
    'key34153': 'value14735',
    'key51577': 'value69652',
    'key56378': 'value11447',
    'key90434': 'value87224',
    'key34898': 'value87246',
    'key60869': 'value84874',
    'key8232': 'value99808',
},
    {
    'id': 17527488282946,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Brandon Randolph',
    'address': '3726 Natasha Rapids Apt. 637\nNorth Jacob, DE 38100',
    'text': 'Camera order conference already budget. Happy computer election do. Writer clearly help.\nHistory movement degree tree analysis anything floor. Establish join state safe she.',
    'email': 'martinezlinda@example.org',
    'phone_number': '001-782-880-9646x709',
    'json': {
    'name': 'Tonya Cooper',
    'address': '41340 Williams Burg Apt. 994\nWardburgh, GA 09137',
},
    'key67106': 'value7766',
    'key23145': 'value47009',
    'key54852': 'value51378',
    'key37692': 'value25757',
    'key53102': 'value12128',
},
    {
    'id': 17527488282957,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Mr. Lee Jones',
    'address': '7317 Mcmillan Stream Apt. 027\nPratthaven, MI 43539',
    'text': 'Together green suffer four.\nReduce study open forward stand strategy. His in choose country.\nWind view three. Door speak increase her. Structure energy process traditional camera as.',
    'email': 'rachelbanks@example.net',
    'phone_number': '689.663.7095x496',
    'json': {
    'name': 'Michelle Morrow',
    'address': '180 Elizabeth Valley Apt. 185\nMorganhaven, MD 40606',
},
    'key97399': 'value11087',
    'key29434': 'value67403',
    'key93030': 'value61215',
    'key94465': 'value68098',
    'key47446': 'value40299',
    'key61898': 'value73799',
    'key18115': 'value8195',
    'key42095': 'value35234',
    'key55895': 'value62275',
},
    {
    'id': 17527488282970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Christopher Mitchell',
    'address': '513 Johnson Stravenue Suite 772\nKleinview, AS 77831',
    'text': 'Analysis still town plan including woman. Run without safe mean improve sure. Real offer green fall full anyone his painting.',
    'email': 'jack62@example.net',
    'phone_number': '(454)458-8746',
    'json': {
    'name': 'Sarah Gonzalez',
    'address': '3339 Tamara Terrace Apt. 943\nSouth Frank, SC 49764',
},
    'key3676': 'value72733',
    'key68561': 'value77742',
    'key77152': 'value4388',
    'key45955': 'value16816',
},
    {
    'id': 17527488282980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Katrina Simpson',
    'address': 'PSC 7379, Box 0685\nAPO AA 35017',
    'text': 'Win along control mean beat number. Finally no social space.\nThus daughter treatment big trouble everyone. Stuff appear race yeah threat space open.',
    'email': 'richardgardner@example.com',
    'phone_number': '929.405.2927',
    'json': {
    'name': 'James Young',
    'address': '86481 Owens Crest\nAshleyton, AL 50482',
},
    'key23908': 'value25422',
    'key66208': 'value90033',
    'key58511': 'value72603',
    'key26733': 'value54279',
},
    {
    'id': 17527488282990,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jason Davis',
    'address': '57377 Andrea Burg Suite 166\nLake Larrytown, IN 34468',
    'text': 'Tonight bag approach single.\nSeason cultural society despite dog. Might with commercial trade man glass. Indicate whose look claim prove like performance. Hand show follow treat simply last.',
    'email': 'vmitchell@example.com',
    'phone_number': '+1-993-937-5142x402',
    'json': {
    'name': 'Anthony Rodriguez',
    'address': '2407 Corey Island\nPort Kendraview, GA 02819',
},
    'key73277': 'value38058',
    'key78147': 'value69426',
    'key87617': 'value3075',
    'key48835': 'value46510',
    'key68203': 'value23604',
    'key54823': 'value98615',
    'key44955': 'value69778',
    'key37308': 'value17116',
    'key67237': 'value11244',
    'key22368': 'value84201',
},
    {
    'id': 17527488283000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Heidi Mills',
    'address': '23256 Harrison Inlet\nSaratown, MN 75688',
    'text': 'Social important campaign position part return group. Home those into wall assume degree recent.\nUp board note reveal seem action. Face better idea item firm.\nPattern girl source official throw.',
    'email': 'gibsonkelsey@example.net',
    'phone_number': '001-935-741-8794x807',
    'json': {
    'name': 'Julie Kennedy',
    'address': '95366 Hernandez Crossroad\nLisatown, OR 38570',
},
    'key18391': 'value60632',
    'key91388': 'value49260',
    'key92753': 'value7454',
    'key63381': 'value26555',
    'key83553': 'value78420',
    'key66222': 'value41641',
    'key67095': 'value16717',
    'key12243': 'value6828',
    'key66140': 'value42070',
    'key74454': 'value44394',
},
    {
    'id': 17527488283012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Tiffany Johnson',
    'address': 'Unit 3579 Box 4897\nDPO AA 59060',
    'text': 'Family structure situation challenge reality. Although think cold doctor compare hear agreement half. Available seat move drop whether.\nProduct local responsibility.',
    'email': 'garciacynthia@example.com',
    'phone_number': '833-864-7276x5251',
    'json': {
    'name': 'Kerry Wilson',
    'address': '67833 Rebecca Loaf\nNorth Christine, PR 83965',
},
    'key48872': 'value38179',
    'key88398': 'value5382',
    'key78426': 'value91992',
    'key89613': 'value5300',
    'key17185': 'value48281',
},
    {
    'id': 17527488283022,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Anna Carroll',
    'address': '92254 Christopher Crossroad\nNorth Luis, CO 34861',
    'text': 'Without age parent account outside whatever. Floor capital up treatment.\nWalk inside whom at pressure program program imagine. Force bring either travel particularly goal.',
    'email': 'huntlinda@example.com',
    'phone_number': '3979410296',
    'json': {
    'name': 'Cheryl Perez',
    'address': '10032 Erin Glens Suite 822\nRobertfurt, AR 40302',
},
    'key29620': 'value82313',
    'key23003': 'value33023',
    'key16991': 'value20035',
},
    {
    'id': 17527488283032,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Miranda Pham',
    'address': '6182 Raven Coves Suite 957\nNorth Bryanmouth, MP 32576',
    'text': 'Case general thing plan trouble concern note. Over civil wall less. Family recently dinner year success watch after.\nAdd toward find. Impact oil list.',
    'email': 'lopezchristopher@example.net',
    'phone_number': '(915)344-9723x8208',
    'json': {
    'name': 'Dylan Lynch',
    'address': '976 Richards Forges\nLake Richard, FM 20811',
},
    'key87668': 'value32092',
    'key69119': 'value52377',
    'key25337': 'value21565',
    'key21884': 'value63826',
    'key58817': 'value65276',
    'key20661': 'value18864',
},
    {
    'id': 17527488283046,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'David Shah',
    'address': '605 Toni Coves Suite 983\nJonesside, GA 56689',
    'text': 'Beat one decide week during nearly. Media stage might toward view effect.\nBase number arm speak that. Week ask south.',
    'email': 'desiree57@example.org',
    'phone_number': '780-627-1204x8397',
    'json': {
    'name': 'Nicole Lawson',
    'address': '120 James Summit\nHunterburgh, KS 83370',
},
    'key91438': 'value54749',
    'key4878': 'value13994',
    'key51285': 'value93576',
    'key59219': 'value23533',
    'key46230': 'value12984',
    'key41001': 'value22969',
    'key49572': 'value25065',
    'key205': 'value47528',
},
    {
    'id': 17527488283058,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'John Nelson',
    'address': '68521 Joseph Cove Apt. 991\nPort Lauraborough, WY 15057',
    'text': 'Choose edge worker entire current conference step. Type sport last mouth recently.\nDark response protect century entire. Idea keep education purpose although final he occur.',
    'email': 'kathleenhenson@example.org',
    'phone_number': '915-590-0584x7120',
    'json': {
    'name': 'Edward Hampton',
    'address': '7439 Dawson Estate Suite 525\nSouth Ashley, PA 72713',
},
    'key98534': 'value89390',
    'key49762': 'value62692',
    'key6615': 'value62656',
},
    {
    'id': 17527488283069,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Nicole Williams',
    'address': '082 Anderson Drives\nNew Robertside, MP 60300',
    'text': 'That area local painting. Relationship expert write any. Color financial day career guy radio else.\nKnowledge stop staff owner term leave present. Perform yes main general.',
    'email': 'aarongraham@example.com',
    'phone_number': '001-788-788-2306x73137',
    'json': {
    'name': 'Jorge Flores',
    'address': '3886 Deborah Fort\nLopezview, NJ 18691',
},
    'key35006': 'value51576',
    'key4290': 'value38137',
    'key32424': 'value21577',
    'key60374': 'value13179',
    'key15974': 'value73725',
    'key32022': 'value95337',
    'key27500': 'value2700',
    'key23781': 'value22201',
},
    {
    'id': 17527488283081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Calvin Marsh',
    'address': '67527 Patterson Plains\nJohnsonside, MD 93131',
    'text': 'Unit though real ground deal raise only.\nThere process military. Prevent service although likely. Sort mean organization more data leave stock.',
    'email': 'nicholssandra@example.net',
    'phone_number': '460-978-8636x8986',
    'json': {
    'name': 'Robert Hill',
    'address': '99297 Carson Mission\nSuzanneville, SC 30970',
},
    'key49646': 'value75094',
    'key93860': 'value49038',
    'key14855': 'value33628',
    'key12575': 'value52264',
    'key43541': 'value50099',
    'key72223': 'value13745',
    'key87146': 'value58057',
    'key87847': 'value17615',
    'key93666': 'value98583',
},
    {
    'id': 17527488283093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Brandon Pierce',
    'address': '6175 James Light Apt. 729\nCarolynside, AZ 12660',
    'text': 'Off be such keep memory back certain fast. Response white decade including.\nLeader rule end fish let will. Statement finally think believe front president. Little establish bill.',
    'email': 'erin23@example.net',
    'phone_number': '(406)437-2199x200',
    'json': {
    'name': 'Jessica Pope',
    'address': 'PSC 5227, Box 7438\nAPO AA 89835',
},
    'key74822': 'value42157',
    'key71653': 'value78446',
    'key19623': 'value16641',
    'key84392': 'value72179',
    'key10668': 'value53149',
    'key62282': 'value19876',
    'key64211': 'value38178',
    'key80109': 'value46339',
    'key39606': 'value75053',
    'key91171': 'value20110',
},
    {
    'id': 17527488283102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Michael Daugherty',
    'address': 'PSC 7050, Box 4926\nAPO AP 47108',
    'text': 'Cost book result resource thought. Share travel movement travel.',
    'email': 'andrew44@example.com',
    'phone_number': '278.561.1531x5810',
    'json': {
    'name': 'Sherri White',
    'address': '95582 Eric Extensions\nEast Lucaschester, WI 20293',
},
    'key9122': 'value11427',
    'key89489': 'value35680',
    'key54320': 'value5872',
    'key22605': 'value58608',
    'key53687': 'value76859',
    'key19821': 'value60986',
    'key68653': 'value66451',
    'key48306': 'value25582',
},
    {
    'id': 17527488283110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Mrs. Denise Sawyer',
    'address': 'PSC 6305, Box 3892\nAPO AE 57956',
    'text': 'Century area candidate dog time week. Deal walk while without. Nearly effect ahead hot writer board attorney. Hand go million thing.',
    'email': 'alexlee@example.net',
    'phone_number': '(767)697-1436x54232',
    'json': {
    'name': 'Eddie Hunt',
    'address': '3421 Sally Lakes\nSusanside, MS 95038',
},
    'key38801': 'value11973',
    'key36383': 'value52033',
    'key8910': 'value73924',
    'key1584': 'value49694',
    'key80523': 'value96625',
    'key22339': 'value82953',
},
    {
    'id': 17527488283120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Alejandro Rose',
    'address': '776 Miller Shoals Suite 133\nJudyfurt, FM 29630',
    'text': 'Position rock discover give remember next seem. Remember serious happen will job. Several wish pass where.\nStreet better father strong side final million. Car away seat at with behind.',
    'email': 'amanda39@example.org',
    'phone_number': '498-794-1569x587',
    'json': {
    'name': 'Jasmine Luna',
    'address': '5829 Taylor Knolls Apt. 472\nDouglasland, CO 12421',
},
    'key78823': 'value2616',
    'key20583': 'value5508',
    'key6252': 'value14381',
    'key80038': 'value28100',
    'key40205': 'value59113',
    'key8067': 'value2487',
    'key20141': 'value15687',
    'key73916': 'value96198',
},
    {
    'id': 17527488283130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Elizabeth Greene',
    'address': '94586 John Tunnel\nBeckerland, VA 77524',
    'text': 'Drive more drug true. Cover hair read sing star road government activity.',
    'email': 'kmason@example.org',
    'phone_number': '604.400.7582',
    'json': {
    'name': 'Jacob Herring',
    'address': '11995 Bailey Via\nEast Barbara, FL 26226',
},
    'key30432': 'value87857',
    'key19610': 'value87449',
    'key15644': 'value90409',
    'key29301': 'value57477',
    'key23544': 'value13562',
    'key48833': 'value46668',
},
    {
    'id': 17527488283141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Brittany Higgins',
    'address': '897 Miller Curve Suite 323\nSouth Carla, NC 90979',
    'text': 'Lawyer dark glass nation pick per. Environment those western power court always. Start site bed space.',
    'email': 'smithglen@example.com',
    'phone_number': '+1-351-650-3390x102',
    'json': {
    'name': 'Danielle Berry',
    'address': '208 Tammy Cliffs Suite 633\nWileybury, OK 75455',
},
    'key69189': 'value90606',
},
    {
    'id': 17527488283153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Donna Conley',
    'address': '05704 Mason Mills\nSouth Ryan, MO 96839',
    'text': 'Same may tonight star even seek thing. Party significant I worry offer cold scientist.\nExample station trip TV clearly resource organization. Newspaper wife prove cost apply expect analysis.',
    'email': 'schmidtscott@example.com',
    'phone_number': '713-959-6559x41599',
    'json': {
    'name': 'Mrs. Carolyn Gray MD',
    'address': '03746 Lin Stravenue\nWest Daniel, MH 80695',
},
    'key30669': 'value55937',
    'key39044': 'value47448',
},
    {
    'id': 17527488283164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Ashley Hoffman',
    'address': '457 Katie Groves\nSouth Michael, AK 41221',
    'text': 'Attorney time field such technology administration. Management behind require cause majority consider help.',
    'email': 'vanessa37@example.org',
    'phone_number': '887-741-6248',
    'json': {
    'name': 'Donna Bennett',
    'address': '3448 Brenda Field\nEast Matthew, NE 88455',
},
    'key26526': 'value32375',
    'key85567': 'value20349',
    'key88661': 'value77144',
    'key91655': 'value70083',
},
    {
    'id': 17527488283174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Andrea Jackson',
    'address': '50035 Chris Plaza\nNew April, OR 85750',
    'text': 'Cover everyone toward how must. Whose TV lawyer real. Join real five.\nPicture commercial lay person young interest. Administration order degree whom natural even.',
    'email': 'farmerjohn@example.org',
    'phone_number': '001-616-593-9091x0124',
    'json': {
    'name': 'Nichole Leblanc',
    'address': '2521 Peters Ridges\nWest Dawn, HI 53800',
},
    'key2085': 'value82337',
    'key59481': 'value29420',
    'key93223': 'value72922',
    'key83779': 'value92399',
    'key1825': 'value30747',
    'key27954': 'value20930',
},
    {
    'id': 17527488283185,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Joseph Davis',
    'address': '06303 Christina Trail\nNew Marioside, IA 39712',
    'text': 'Federal several cup less society sit. Pay security ask interview like work service century.',
    'email': 'hannah81@example.org',
    'phone_number': '944-814-7267x44296',
    'json': {
    'name': 'Margaret Lopez',
    'address': '062 Smith Valleys Apt. 895\nWest Douglasport, PA 10662',
},
    'key51284': 'value9440',
    'key39582': 'value11574',
    'key38359': 'value98264',
    'key95783': 'value87442',
    'key41550': 'value56640',
    'key20823': 'value27497',
},
    {
    'id': 17527488283196,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Makayla Parker',
    'address': '11753 Justin Cove\nJohnberg, OR 33511',
    'text': 'Structure trip player. Talk outside two suggest. Month happy see quickly important day hope. Character walk thought side stage born skin machine.',
    'email': 'natalie99@example.org',
    'phone_number': '001-911-825-6272x22841',
    'json': {
    'name': 'Tyler Meyer',
    'address': '61151 Samantha Isle\nJohnville, TN 17608',
},
    'key64360': 'value10092',
},
    {
    'id': 17527488283207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Stephanie Chan',
    'address': '846 Travis Spring Suite 495\nNorth Joshua, NH 73980',
    'text': 'Oil citizen fish future human. Today available main front bar relationship drug. Who get will hand what production organization agreement.',
    'email': 'qgordon@example.com',
    'phone_number': '856-363-0419x01151',
    'json': {
    'name': 'Terry Martinez',
    'address': '6409 Jeffery Wall\nNorth Reginaldview, PA 22244',
},
    'key70893': 'value76456',
    'key31945': 'value57955',
    'key26549': 'value60643',
    'key61726': 'value87949',
    'key17329': 'value7496',
    'key54005': 'value35908',
    'key72261': 'value69370',
    'key3753': 'value63185',
    'key84508': 'value75190',
},
    {
    'id': 17527488283218,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Stephen Lutz',
    'address': '032 Rodriguez Cliffs\nPort Kyleport, LA 28813',
    'text': 'Cost official street where address. Service evening same million inside available.\nVoice detail many life rather career contain. Suddenly bring generation boy. Leg moment note yard sure.',
    'email': 'gamblechristine@example.net',
    'phone_number': '+1-658-291-7810',
    'json': {
    'name': 'Daniel Lopez',
    'address': '46276 Timothy Union\nNew Priscillaburgh, DE 38794',
},
    'key49122': 'value3479',
    'key26141': 'value62343',
    'key67000': 'value21356',
    'key3495': 'value1641',
    'key99138': 'value61471',
    'key35350': 'value96311',
    'key46535': 'value50695',
    'key6806': 'value5517',
    'key30262': 'value98642',
},
    {
    'id': 17527488283230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Joshua Parker',
    'address': '56569 Danielle Skyway Apt. 244\nMartinport, KS 63404',
    'text': 'Growth save pass father than public.\nGirl mother general senior. How little best good. Teacher hair if media factor close.\nSide to table college. Require certainly prepare president.',
    'email': 'nhudson@example.com',
    'phone_number': '274.552.2647',
    'json': {
    'name': 'Lauren Cortez',
    'address': '663 Torres Lights Suite 493\nSouth Charlottestad, AS 50370',
},
    'key22231': 'value17086',
},
    {
    'id': 17527488283242,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Gregory Madden',
    'address': '0111 Shannon Stream\nStewartfurt, CT 21111',
    'text': 'Simple Congress whole painting artist. Again mother newspaper image foot matter.\nEdge body behavior feeling product. Officer business imagine.',
    'email': 'hjames@example.org',
    'phone_number': '+1-619-727-1498x36042',
    'json': {
    'name': 'Taylor Hensley',
    'address': '2768 Lopez Ports\nPort Jenniferfort, OH 81607',
},
    'key44804': 'value71160',
    'key53145': 'value87792',
    'key83605': 'value36609',
},
    {
    'id': 17527488283253,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Brandy King',
    'address': '197 Gonzalez Parkways\nPort Paulville, PA 70470',
    'text': 'Economic true success authority west maintain. Second capital turn add big likely off.\nThemselves believe dog. Face top religious program.',
    'email': 'julie61@example.org',
    'phone_number': '+1-599-862-7338',
    'json': {
    'name': 'Amy Roberts',
    'address': '8392 Cheryl Landing Suite 389\nLake Jason, IN 07564',
},
    'key29619': 'value88496',
    'key85301': 'value80277',
    'key28435': 'value61714',
    'key85229': 'value85973',
    'key82005': 'value36104',
},
    {
    'id': 17527488283263,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Marcia Richardson',
    'address': '91017 Brandon Centers Suite 565\nMartinezstad, RI 67519',
    'text': 'Cultural baby spend simply to project buy heart. Fall season impact investment population. Budget seat measure project scene yet operation new.',
    'email': 'ruthhopkins@example.net',
    'phone_number': '(947)278-7117x196',
    'json': {
    'name': 'Corey Henson',
    'address': '882 Rosales Dam Apt. 851\nJasonhaven, MP 33063',
},
    'key54879': 'value38971',
    'key74280': 'value3902',
    'key52125': 'value23712',
    'key9853': 'value52216',
    'key29798': 'value66041',
    'key60289': 'value74640',
    'key58857': 'value27844',
    'key94754': 'value90540',
    'key75650': 'value84138',
},
    {
    'id': 17527488283275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Debra Moore',
    'address': '30236 Bryan Unions Apt. 867\nAshleychester, MS 23914',
    'text': 'Particularly situation party hard. Model tonight several push according energy.\nPossible offer election these. Point artist never word source challenge image. Minute prove ago society.',
    'email': 'manuelburton@example.net',
    'phone_number': '594-408-8892',
    'json': {
    'name': 'Christopher Mcintosh',
    'address': '03604 Timothy Parks Suite 189\nBrianchester, NV 66094',
},
    'key83316': 'value96317',
    'key47908': 'value76020',
    'key47978': 'value56539',
    'key71373': 'value43880',
    'key6754': 'value75931',
    'key45082': 'value87056',
    'key35052': 'value74558',
    'key99135': 'value65832',
},
    {
    'id': 17527488283287,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Michaela Tanner',
    'address': '6086 Brock Orchard\nEast Kenneth, MO 29580',
    'text': 'Turn sea entire them walk authority daughter. Establish according enjoy our. True change box.',
    'email': 'kathryndickerson@example.net',
    'phone_number': '904-306-8736x78018',
    'json': {
    'name': 'Michael Mitchell',
    'address': '13176 Robert Ways\nCarterburgh, UT 10939',
},
    'key45154': 'value18131',
    'key44798': 'value89370',
    'key96665': 'value84798',
    'key19561': 'value6337',
},
    {
    'id': 17527488283299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Adam Medina',
    'address': 'PSC 6790, Box 3715\nAPO AA 01170',
    'text': 'Season cost project consumer. Executive magazine seat pretty.\nMinute chair truth cell. Few key win. For data occur spend shake.\nEnvironment attorney south study. Daughter month rate discuss.',
    'email': 'bobby99@example.net',
    'phone_number': '295.520.0168x18798',
    'json': {
    'name': 'Jon Patterson',
    'address': '295 Evan Stravenue\nSouth Preston, IN 79691',
},
    'key76943': 'value84758',
    'key67311': 'value5632',
    'key5728': 'value47260',
    'key25119': 'value20186',
    'key50503': 'value97554',
    'key42587': 'value66506',
},
    {
    'id': 17527488283307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Johnny Davis',
    'address': '4511 Michelle Fall\nBrianafort, CT 18446',
    'text': 'Interesting member reduce his up alone experience. Current common join second action material maintain assume. Manager pretty decide sing body pattern gas.',
    'email': 'bethanyalexander@example.com',
    'phone_number': '557.611.5590',
    'json': {
    'name': 'Pamela Cummings',
    'address': '8641 Aaron Inlet\nLake Scottchester, DC 89917',
},
    'key36360': 'value36498',
    'key30729': 'value73010',
    'key82647': 'value5280',
    'key90660': 'value62998',
    'key93304': 'value18194',
    'key98321': 'value49510',
},
    {
    'id': 17527488283318,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Marcus Garcia',
    'address': '98703 Natalie Glen\nEast Markmouth, WI 82065',
    'text': 'Determine whether kid him. Management return data allow of.\nCarry morning tell clear nothing medical return. Cup and able into situation almost. Plan TV foot PM.',
    'email': 'williampearson@example.com',
    'phone_number': '(640)858-1626',
    'json': {
    'name': 'Michelle Brown',
    'address': 'PSC 9037, Box 2222\nAPO AA 53407',
},
    'key58198': 'value6526',
    'key77254': 'value80407',
    'key57715': 'value86728',
    'key99669': 'value64267',
    'key25399': 'value29975',
    'key22677': 'value75657',
    'key78395': 'value26670',
    'key51196': 'value10236',
    'key92802': 'value38621',
},
    {
    'id': 17527488283328,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Jason Vazquez',
    'address': '9540 Christensen Parkway Suite 495\nEdwardtown, VT 91938',
    'text': 'Card middle age place source realize beyond. Manage yourself become pull first know. Market control important car gas letter floor only. Little success lot agent issue half example.',
    'email': 'douglas10@example.net',
    'phone_number': '285.895.3146x953',
    'json': {
    'name': 'Sara Neal',
    'address': '2466 Raymond Mills Apt. 849\nRangelberg, NE 70893',
},
    'key82482': 'value99283',
    'key71734': 'value48717',
    'key76625': 'value75290',
    'key35385': 'value116',
    'key36272': 'value82658',
    'key37239': 'value19757',
    'key53665': 'value99590',
    'key84071': 'value98727',
    'key87945': 'value15109',
},
    {
    'id': 17527488283338,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Victoria Escobar',
    'address': '2232 Cole Walk Suite 316\nMauricefurt, ME 82288',
    'text': 'Fast pretty physical want near among population young.\nBy family charge again. Third important bad blue election create.',
    'email': 'walkerdeborah@example.net',
    'phone_number': '001-749-480-4680x327',
    'json': {
    'name': 'Jessica Clarke',
    'address': '736 Grant Haven\nEileenton, SC 58580',
},
    'key16239': 'value95236',
    'key83030': 'value82447',
    'key46689': 'value89453',
    'key35219': 'value80386',
    'key19165': 'value77893',
    'key7820': 'value18344',
    'key42409': 'value66775',
    'key50960': 'value35119',
    'key81923': 'value60413',
    'key16726': 'value91629',
},
    {
    'id': 17527488283350,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Douglas Logan',
    'address': '55783 Sharon Crescent\nAndrewville, OH 82406',
    'text': 'Court decide commercial sit break cup. Tree peace everybody. Ever business experience knowledge arrive remember.',
    'email': 'jonesmichele@example.net',
    'phone_number': '+1-359-943-5985x59248',
    'json': {
    'name': 'Nathan Fox',
    'address': '05906 Neal Islands Suite 247\nCarrside, FM 85499',
},
    'key34260': 'value51521',
    'key61377': 'value35390',
    'key11008': 'value232',
    'key38796': 'value85777',
    'key80193': 'value88908',
    'key63591': 'value51553',
},
    {
    'id': 17527488283362,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Derek Cisneros',
    'address': '525 Martin Fall Apt. 667\nPort Krystal, AS 33094',
    'text': 'Need better finish tonight big operation. Subject people rate her go same. Create middle main ball population heart.\nAt return again history. Cut cost deep attorney police occur.',
    'email': 'garybridges@example.com',
    'phone_number': '(957)914-8759',
    'json': {
    'name': 'Linda Jackson',
    'address': '6081 Scott Meadow Suite 778\nLake Williamtown, ID 25411',
},
    'key57558': 'value69055',
    'key56631': 'value98614',
    'key67299': 'value64405',
    'key60104': 'value41539',
    'key85488': 'value5572',
    'key73546': 'value17881',
},
    {
    'id': 17527488283373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Patricia Ross',
    'address': 'USCGC Bullock\nFPO AE 90388',
    'text': 'Wind political us second enough data watch. Voice provide wind hot treat author lead.\nReason cut become west husband learn. Real land operation.',
    'email': 'umiller@example.net',
    'phone_number': '802.299.6860',
    'json': {
    'name': 'Christopher Simon',
    'address': '455 Krista Heights Suite 594\nCoxmouth, FM 50645',
},
    'key64144': 'value76033',
    'key60831': 'value63669',
    'key69955': 'value69570',
    'key61828': 'value42288',
    'key55008': 'value48032',
    'key64877': 'value53736',
    'key3176': 'value35430',
    'key99213': 'value26364',
},
    {
    'id': 17527488283383,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Heather Baldwin',
    'address': 'PSC 2165, Box 3422\nAPO AE 02079',
    'text': 'Character candidate throw out more dark. Build color pay break. Radio later fast plan election hundred no.',
    'email': 'reedvincent@example.org',
    'phone_number': '(857)469-5895x2717',
    'json': {
    'name': 'Anita Vang',
    'address': '667 Martin Pines Apt. 401\nBrendaview, KY 43566',
},
    'key66704': 'value51839',
    'key62658': 'value30972',
    'key98818': 'value54388',
    'key60410': 'value93066',
    'key6874': 'value47526',
},
    {
    'id': 17527488283393,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Angela Durham',
    'address': '35041 Lee Crest\nBarkerfurt, MN 60561',
    'text': 'Measure like free professional such work these piece. Toward trade network contain test. There air much until no during agreement along.',
    'email': 'yjones@example.org',
    'phone_number': '(629)621-4235x95706',
    'json': {
    'name': 'Brandon Austin',
    'address': '861 Hernandez Garden Suite 687\nJustinside, OR 80270',
},
    'key56144': 'value1297',
},
    {
    'id': 17527488283403,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Angela Knight',
    'address': '247 Eileen Crossroad\nSchwartzshire, NE 32935',
    'text': 'Catch about project country head.\nSing company concern little ask. Value space full fund act low feeling. Garden day manager sea appear through candidate.',
    'email': 'steven85@example.net',
    'phone_number': '601-673-9114x8446',
    'json': {
    'name': 'Michael Monroe',
    'address': '411 Rodriguez Turnpike\nHarrisshire, IL 12141',
},
    'key75206': 'value12612',
    'key19101': 'value81980',
    'key67': 'value36142',
    'key7747': 'value56148',
    'key16636': 'value12143',
    'key69492': 'value34396',
},
    {
    'id': 17527488283414,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Angelica Schroeder',
    'address': '908 Jennifer Skyway\nNorth Kimberly, ID 61879',
    'text': 'Central church bank few sense. Commercial American center.\nNature energy front billion here. Other mother forward car sea seven. Could student pay friend despite.\nYes toward for political.',
    'email': 'tbradley@example.com',
    'phone_number': '928-531-7353',
    'json': {
    'name': 'Ryan Frazier',
    'address': '002 Justin Shores\nSouth Johnnyside, WI 14245',
},
    'key79653': 'value42917',
    'key39864': 'value31848',
},
    {
    'id': 17527488283425,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Stephen Johnson',
    'address': 'PSC 8268, Box 3184\nAPO AE 26166',
    'text': 'Economic away event talk. Behind floor benefit. Hospital program while mouth customer Mrs decade.',
    'email': 'ftaylor@example.com',
    'phone_number': '001-392-365-4943',
    'json': {
    'name': 'Brittney Oneill',
    'address': '948 Marissa Vista Apt. 972\nKevinmouth, IL 39451',
},
    'key59143': 'value59318',
    'key20385': 'value62507',
    'key32144': 'value22665',
    'key47315': 'value78021',
    'key22481': 'value21938',
    'key36346': 'value6773',
    'key53524': 'value48598',
    'key1332': 'value79404',
    'key47634': 'value5398',
    'key85876': 'value6144',
},
    {
    'id': 17527488283434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Victoria Carter',
    'address': '89936 Kennedy Key\nNew Jesse, PR 05924',
    'text': 'Pattern since student realize lead stop black surface. Country opportunity think long attorney approach edge money.',
    'email': 'annadavid@example.net',
    'phone_number': '532-723-5851x260',
    'json': {
    'name': 'Gregory Garcia',
    'address': '26945 Williamson Junctions Apt. 109\nDennisland, LA 20230',
},
    'key96786': 'value88252',
    'key81842': 'value98691',
    'key20036': 'value58236',
    'key63755': 'value41228',
    'key70035': 'value4903',
    'key56532': 'value68849',
},
    {
    'id': 17527488283445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jennifer Wilson',
    'address': '77165 Williams Villages\nPort Michelleborough, ME 15549',
    'text': 'Store program policy who rise federal think may. Hit behind natural step allow message.\nTogether future home. Way garden control practice free reach usually.',
    'email': 'samantha19@example.net',
    'phone_number': '001-439-378-3272x9959',
    'json': {
    'name': 'Ms. Rebecca Roman',
    'address': '799 Adam Track Apt. 147\nNew Debra, OR 97463',
},
    'key93664': 'value43533',
    'key66680': 'value21988',
    'key83566': 'value40378',
    'key44751': 'value3855',
    'key23207': 'value50993',
    'key47676': 'value61738',
    'key85049': 'value78488',
    'key59704': 'value15913',
    'key42852': 'value41113',
    'key35393': 'value20638',
},
    {
    'id': 17527488283455,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Richard Bowman',
    'address': 'Unit 7871 Box 8300\nDPO AA 61520',
    'text': 'Over simply old agent technology. Probably easy now show.\nSubject because area left hundred those. Worker case entire skill than voice close prove. Dark other not.',
    'email': 'xtaylor@example.net',
    'phone_number': '001-648-749-1743x96184',
    'json': {
    'name': 'Misty Cobb',
    'address': 'PSC 2361, Box 5598\nAPO AE 12995',
},
    'key59721': 'value71225',
    'key20325': 'value87409',
    'key87034': 'value25625',
    'key44427': 'value74389',
    'key2348': 'value29521',
    'key95473': 'value7825',
},
    {
    'id': 17527488283463,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Theodore Beasley',
    'address': '455 Levine Lights Suite 369\nJoshuachester, GA 27883',
    'text': 'Recent security fight she. Top indeed quality claim involve. Do audience performance high. World we officer successful career goal.',
    'email': 'usweeney@example.org',
    'phone_number': '(468)612-3304',
    'json': {
    'name': 'Kelli Williams',
    'address': '5471 Mckinney Spring\nFitzgeraldmouth, ND 91744',
},
    'key52703': 'value18536',
    'key65711': 'value81424',
    'key16768': 'value83339',
    'key6082': 'value59821',
},
    {
    'id': 17527488283473,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Holly Thornton',
    'address': 'PSC 5396, Box 9666\nAPO AP 56622',
    'text': 'Which success somebody laugh. After task there huge firm PM piece.\nAlong industry artist actually reveal water. Industry discuss speak whole me.',
    'email': 'sherihernandez@example.org',
    'phone_number': '(547)733-9398x13597',
    'json': {
    'name': 'Natalie Jackson',
    'address': '65255 Pratt Creek Suite 650\nCraigland, AK 41982',
},
    'key59903': 'value75309',
},
    {
    'id': 17527488283483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Christopher Jimenez',
    'address': '1940 Stephanie Stravenue\nEast Tracybury, IL 32656',
    'text': 'Base let feel traditional research country sport. Entire argue report. Machine church well draw value very.',
    'email': 'huertastephen@example.net',
    'phone_number': '7744489379',
    'json': {
    'name': 'Jack Vaughan',
    'address': '698 Stephanie Estates Apt. 620\nPort Bonnie, WI 60595',
},
    'key94120': 'value22085',
    'key88844': 'value85364',
    'key13499': 'value34515',
    'key86313': 'value58347',
    'key12692': 'value22454',
    'key27353': 'value15131',
    'key77117': 'value92901',
    'key62647': 'value31307',
},
    {
    'id': 17527488283494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Susan Villegas',
    'address': '9069 Tammy Harbor Suite 308\nEast Margaretshire, PA 27141',
    'text': 'Visit safe community. Worker west really charge education capital project. Affect since after method Democrat.\nThought still recognize left. Message major type prevent less before.',
    'email': 'steven27@example.net',
    'phone_number': '354-329-0353',
    'json': {
    'name': 'Joel Peck',
    'address': '3034 Brown Islands Suite 342\nNorth Emma, NV 72317',
},
    'key94346': 'value19687',
    'key84235': 'value49125',
    'key20466': 'value69344',
    'key4138': 'value82741',
    'key34720': 'value80821',
    'key49244': 'value35434',
    'key14458': 'value71299',
    'key61389': 'value16221',
},
    {
    'id': 17527488283505,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Michael Santana',
    'address': '5105 Thompson View Apt. 079\nNew Christopher, TX 42449',
    'text': 'Particularly there war describe but political. Strong treat within check. Trip market everything whose decision.\nCharge quickly despite agency. Country fund author thought cold.',
    'email': 'robertsmith@example.net',
    'phone_number': '508-506-4207',
    'json': {
    'name': 'Chad Bennett',
    'address': '425 Sarah Light Suite 978\nNorth Patriciashire, KY 38026',
},
    'key23591': 'value71381',
    'key28836': 'value4099',
    'key37306': 'value94412',
    'key51359': 'value89356',
    'key75392': 'value33340',
},
    {
    'id': 17527488283516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Robert Foster',
    'address': '89073 Davis Knoll\nAlexandriastad, WA 99120',
    'text': 'Whom start southern sound start land. Heart fall out collection particularly sometimes rest.',
    'email': 'rrobinson@example.net',
    'phone_number': '615-683-4086x7363',
    'json': {
    'name': 'Donna Pitts',
    'address': '7097 Franklin Ville\nWest Sara, MP 49645',
},
    'key12500': 'value38092',
    'key97737': 'value62799',
    'key94240': 'value6347',
    'key28872': 'value4326',
},
    {
    'id': 17527488283527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Patricia Maxwell',
    'address': 'PSC 0579, Box 0819\nAPO AP 15636',
    'text': 'Sure thousand glass build. Individual we current unit. There cultural pretty major area difference subject though.',
    'email': 'eric58@example.com',
    'phone_number': '797.465.3828',
    'json': {
    'name': 'Zachary Arnold',
    'address': '4876 Nicholas Plains Apt. 806\nEast Stephenside, GA 40628',
},
    'key85553': 'value34673',
},
    {
    'id': 17527488283535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Zachary Williamson',
    'address': '936 Brown Parkways Apt. 411\nEast Michaelport, AR 84591',
    'text': 'Rest common admit third poor media. Sea if age improve head several. Raise toward partner least also PM certainly.\nWeight recently even single decade. Real read improve vote.',
    'email': 'rodgersjesse@example.com',
    'phone_number': '814-595-9248x5253',
    'json': {
    'name': 'Jeffrey Gilbert',
    'address': '361 Sheila Square Suite 460\nZacharyborough, MO 53120',
},
    'key81428': 'value73273',
    'key98272': 'value24048',
    'key51893': 'value81594',
    'key24327': 'value82451',
    'key23987': 'value66301',
    'key31233': 'value4618',
},
    {
    'id': 17527488283546,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Jason Vega',
    'address': 'Unit 1462 Box 7671\nDPO AA 29842',
    'text': 'Born central garden think direction partner. Seven billion tonight east hour always build. Employee worry we identify money.',
    'email': 'lisa04@example.com',
    'phone_number': '+1-293-751-5575',
    'json': {
    'name': 'Meghan Martin',
    'address': '099 Harrison Shore Suite 886\nReginaldport, NM 02815',
},
    'key67809': 'value73504',
    'key78822': 'value73201',
    'key10605': 'value96452',
    'key38517': 'value73754',
    'key3838': 'value70882',
    'key66191': 'value34450',
    'key9118': 'value66582',
    'key1517': 'value14115',
    'key18999': 'value26427',
    'key56220': 'value42665',
},
    {
    'id': 17527488283555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Steven Contreras',
    'address': '8541 Ruth Islands Suite 871\nGarciatown, MH 11795',
    'text': 'Blood owner better her training author Democrat we. Other wish buy career subject certainly hear nice.\nAnyone tell way join door street you. Service fall read. Computer per here poor world whole.',
    'email': 'kinglauren@example.com',
    'phone_number': '+1-609-224-8703x33727',
    'json': {
    'name': 'Roy Cruz',
    'address': '951 Walker Flats\nHodgefort, FM 33133',
},
    'key951': 'value14287',
    'key37358': 'value86331',
    'key85072': 'value83551',
    'key79903': 'value87889',
    'key68459': 'value58863',
    'key17024': 'value969',
    'key32759': 'value96615',
    'key62850': 'value59759',
    'key97079': 'value64846',
    'key96340': 'value72594',
},
    {
    'id': 17527488283567,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Stacey Gutierrez',
    'address': '912 Smith Pines Apt. 906\nSouth Johnborough, NC 69766',
    'text': 'Physical huge practice finally room stop. We family help this.\nClass nor civil hit. Way bar just health. Life serious walk generation cost resource book rich.',
    'email': 'olivia55@example.net',
    'phone_number': '687-983-7902x4560',
    'json': {
    'name': 'Bryan Roman',
    'address': '57838 Rogers Crescent Apt. 051\nJennifermouth, SC 30633',
},
    'key6653': 'value42169',
    'key76547': 'value51775',
},
    {
    'id': 17527488283577,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Becky Martinez',
    'address': '3664 Reed Crescent Apt. 723\nStacyport, MA 15111',
    'text': 'Marriage provide space product course. Cause much discussion. Listen listen word like.\nReason become long key. Training effect family particular.',
    'email': 'ramirezjason@example.org',
    'phone_number': '+1-414-856-0493x8981',
    'json': {
    'name': 'Tyler Briggs',
    'address': '7627 Myers Expressway Apt. 103\nLake Kristaburgh, SC 71665',
},
    'key45325': 'value17863',
    'key28522': 'value41464',
    'key1553': 'value78868',
    'key8942': 'value89044',
    'key79511': 'value80917',
},
    {
    'id': 17527488283589,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Valerie Griffith',
    'address': '98129 Patel Ville\nNorth Madison, NM 41950',
    'text': 'East charge good section tonight interview everything. Gas organization road million pick thus mean near. Half fund race current.',
    'email': 'shahn@example.net',
    'phone_number': '(280)655-1573x8652',
    'json': {
    'name': 'Ryan Pollard',
    'address': '271 Jerry Shoal Apt. 680\nEast Kelly, NV 21125',
},
    'key60707': 'value13364',
    'key63254': 'value40786',
    'key85940': 'value33979',
    'key62235': 'value79932',
    'key2886': 'value48400',
    'key9969': 'value42915',
},
    {
    'id': 17527488283600,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Dustin Steele',
    'address': '3722 Thomas Brooks\nEast Ashley, WV 57678',
    'text': 'Style top skin concern ground identify someone agency. Move since science. Group culture my prevent executive. Hot process feeling you agency.',
    'email': 'kevin22@example.net',
    'phone_number': '001-936-342-5687x650',
    'json': {
    'name': 'Kathy Hogan',
    'address': '622 Mann Ramp Suite 404\nAndrewstad, OK 20562',
},
    'key68420': 'value28040',
    'key70689': 'value6624',
    'key67024': 'value21019',
    'key68252': 'value61681',
    'key19430': 'value15366',
    'key67266': 'value33022',
    'key86203': 'value85275',
    'key52627': 'value47979',
    'key43961': 'value94297',
},
    {
    'id': 17527488283611,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Ronnie Myers',
    'address': 'PSC 9316, Box 0019\nAPO AA 45879',
    'text': 'Expect improve section form. Light sense onto ready run body.\nReally team song few. List door less design reflect inside. Main school soldier low Congress necessary.',
    'email': 'jenniferhayes@example.org',
    'phone_number': '249.453.7723x603',
    'json': {
    'name': 'Michael Kidd',
    'address': '2030 Williams Forge\nSouth Karenbury, HI 35811',
},
    'key11143': 'value14575',
    'key82094': 'value78380',
    'key49521': 'value23506',
    'key23719': 'value24013',
},
    {
    'id': 17527488283620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Deborah May',
    'address': '60535 Jessica Groves\nGarciamouth, WV 18091',
    'text': 'Evidence identify personal particularly one. Guy wife yard short most body away item. Commercial itself cell simple simple task. Set nor special true may.',
    'email': 'brandonsmith@example.net',
    'phone_number': '001-512-839-1997x833',
    'json': {
    'name': 'Michael Ramsey',
    'address': '07017 Debbie Corners\nPort Victoria, AL 70361',
},
    'key6785': 'value3953',
    'key22072': 'value58588',
    'key75299': 'value85711',
},
    {
    'id': 17527488283631,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Nicolas Wells',
    'address': '9997 Tammy Mission\nSnyderville, OR 06028',
    'text': 'Notice always nature serious section. Skill note her worker teacher affect per.',
    'email': 'richardcoleman@example.org',
    'phone_number': '(865)756-9175x313',
    'json': {
    'name': 'Joseph Bartlett',
    'address': '1544 Ramirez Drive\nLawsonmouth, CT 04607',
},
    'key17361': 'value78124',
    'key37634': 'value13429',
    'key47802': 'value67651',
    'key37088': 'value7510',
    'key25211': 'value71003',
    'key51405': 'value634',
    'key39377': 'value34221',
    'key20597': 'value34164',
    'key84909': 'value82721',
},
    {
    'id': 17527488283643,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Kelly Chandler',
    'address': '307 Hannah Springs Suite 009\nBrandonport, IL 47676',
    'text': 'Capital ready mention police popular.\nEverything traditional gas close American. Hundred leave operation. Describe amount line explain.',
    'email': 'amyphillips@example.net',
    'phone_number': '575-278-8212',
    'json': {
    'name': 'Angelica Bell',
    'address': '4249 Joseph Bridge\nSouth Nicholeville, WV 74481',
},
    'key96075': 'value34785',
    'key32284': 'value77281',
    'key53889': 'value93788',
    'key20947': 'value63217',
    'key18942': 'value50232',
},
    {
    'id': 17527488283654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Matthew Gibson',
    'address': '6185 Mark Mountains Suite 881\nSheilabury, RI 71862',
    'text': 'Few example receive. General similar take human recognize pressure. Left course author order hope.',
    'email': 'jared64@example.net',
    'phone_number': '304.718.6704x800',
    'json': {
    'name': 'Michael Brewer',
    'address': '939 Richard Mission Apt. 767\nSouth Chasetown, MO 98041',
},
    'key55250': 'value58063',
    'key88098': 'value51545',
    'key45053': 'value38676',
},
    {
    'id': 17527488283664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Robert Poole',
    'address': '013 Nathan Keys Suite 830\nNorth Thomastown, AR 71475',
    'text': 'Agree compare debate control recent way. International voice ready effort film. There away assume check summer front why.\nEasy southern partner mission. Senior animal other feeling economy.',
    'email': 'josephmoore@example.com',
    'phone_number': '857.649.7321x3126',
    'json': {
    'name': 'Tracy Payne MD',
    'address': '6636 Wright Center Suite 367\nJessicahaven, OR 92352',
},
    'key79365': 'value5609',
    'key88633': 'value97885',
    'key63978': 'value5859',
    'key64303': 'value62890',
    'key28201': 'value94478',
    'key15620': 'value36184',
    'key12289': 'value51416',
    'key35547': 'value28071',
    'key57774': 'value98645',
    'key85684': 'value23728',
},
    {
    'id': 17527488283676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Morgan Peck',
    'address': '21379 Lori Courts Apt. 606\nJohnstad, CA 39439',
    'text': 'Mrs according power management nature. Life spring join instead former produce. Grow beautiful bar new work community citizen college.\nIdentify affect that learn they office anything.',
    'email': 'jennifermoreno@example.com',
    'phone_number': '(844)988-8889',
    'json': {
    'name': 'Jessica Barnes',
    'address': '528 Patricia Run\nBrownport, TX 03858',
},
    'key78974': 'value33981',
    'key23147': 'value42851',
    'key26799': 'value57102',
    'key32314': 'value24903',
},
    {
    'id': 17527488283687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Shelley Garrett',
    'address': '349 James Glen\nHenryborough, KS 46193',
    'text': 'Common specific nothing there. Factor social program public be nice those.\nSea finish would fly modern.',
    'email': 'maycody@example.org',
    'phone_number': '+1-352-783-2657x805',
    'json': {
    'name': 'Sergio Duffy',
    'address': '3043 Smith Points Apt. 934\nWagnerville, HI 86901',
},
    'key15607': 'value78497',
    'key76505': 'value26790',
    'key17934': 'value29561',
    'key46111': 'value92034',
    'key33779': 'value55733',
    'key37840': 'value7529',
    'key47928': 'value83174',
    'key47551': 'value79013',
},
    {
    'id': 17527488283699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Wayne Ingram',
    'address': '0438 Phyllis Common\nTammymouth, SD 01157',
    'text': 'Development shoulder Democrat kid fine ever provide. Anyone cause recognize. Prove able spend sport left song gun produce.\nStill quickly success interest start.',
    'email': 'xfisher@example.net',
    'phone_number': '+1-646-521-9979x0244',
    'json': {
    'name': 'Yesenia Farmer',
    'address': '947 Herman Streets\nHickmanview, NY 61454',
},
    'key98502': 'value15626',
    'key96948': 'value85575',
    'key5230': 'value44163',
    'key56577': 'value30925',
},
    {
    'id': 17527488283710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Shawn Johnson',
    'address': '628 Phillips Branch Apt. 842\nEast Amandabury, WA 57844',
    'text': 'Relate somebody toward fund. Population professional resource.\nStudent deal put. Attorney another environmental nothing ago force. Attention better discover.',
    'email': 'gdoyle@example.net',
    'phone_number': '001-535-249-5714x0433',
    'json': {
    'name': 'Grant Weber',
    'address': '14538 Shea Avenue\nLake Patricia, ID 82115',
},
    'key10469': 'value35923',
    'key38809': 'value57979',
},
    {
    'id': 17527488283721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Carlos Gibbs',
    'address': '7667 Cynthia Turnpike Apt. 982\nMuellerhaven, NC 29822',
    'text': 'From focus drug knowledge something product carry. Director gun for bar respond development now.\nRealize write politics them child after family good. Group pull top word might attorney.',
    'email': 'colemandavid@example.net',
    'phone_number': '558-856-0016',
    'json': {
    'name': 'Cathy Hughes',
    'address': '1712 Kelley Cove\nHortonchester, KY 64915',
},
    'key51016': 'value38024',
    'key65905': 'value8002',
    'key2001': 'value57069',
    'key71858': 'value84498',
},
    {
    'id': 17527488283733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Kimberly Dickerson',
    'address': '556 Ayala Creek\nWilkinsmouth, MD 38482',
    'text': 'Tv them yeah light. Let nature about investment. Yard machine add seem sing participant campaign.',
    'email': 'dcarlson@example.org',
    'phone_number': '936-787-4119',
    'json': {
    'name': 'Stephanie Beck',
    'address': '385 Brown Fall Apt. 071\nGayfurt, MH 81392',
},
    'key15871': 'value70790',
    'key9939': 'value19132',
    'key29517': 'value65528',
    'key74256': 'value25422',
    'key80352': 'value31163',
    'key35050': 'value63172',
    'key89569': 'value15971',
    'key72738': 'value36947',
},
    {
    'id': 17527488283745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Joseph Barajas',
    'address': '170 Cruz Heights Apt. 136\nNorth Danielle, WI 02211',
    'text': 'Run us grow theory rise. Determine civil determine media go impact. Lawyer budget interesting management huge American event.',
    'email': 'hlyons@example.net',
    'phone_number': '+1-284-321-0171x2800',
    'json': {
    'name': 'Christopher Robbins',
    'address': 'PSC 5431, Box 8018\nAPO AE 22322',
},
    'key36361': 'value54974',
},
    {
    'id': 17527488283753,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Chris Delacruz DDS',
    'address': '4527 Olson Station\nSouth Alyssaburgh, IN 47491',
    'text': 'Arm value consider subject lead consumer. Write three turn sit offer him. Along reach here education.\nActually charge toward include.',
    'email': 'robert27@example.net',
    'phone_number': '(327)262-6916x367',
    'json': {
    'name': 'Brian Anderson',
    'address': '80242 Austin Radial Suite 341\nNorth Jeffreyton, VA 47559',
},
    'key2647': 'value21901',
    'key49108': 'value41495',
    'key77080': 'value74640',
    'key28866': 'value41952',
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
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
    'RequestId': '70cbe480-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_22_228547TciANzEu',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 01]_1752748836.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid011752748836Json()
    test.run_tests()
