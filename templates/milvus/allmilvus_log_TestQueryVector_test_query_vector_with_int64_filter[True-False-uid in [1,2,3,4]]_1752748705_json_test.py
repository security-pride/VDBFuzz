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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752748705_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752748705.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUidIn12341752748705Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752748705.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752748705.json"
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
    'data': [
    {
    'id': 17527486968174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Amy Dixon',
    'address': '144 David Ramp Apt. 136\nWest Josephtown, AL 43998',
    'text': 'Thus hospital southern plant.\nBoard indeed strong nearly spring once. The to energy daughter. Star reduce size run form.\nImportant serve travel over improve. Enjoy least few east sea.',
    'email': 'brendadunlap@example.net',
    'phone_number': '001-628-745-3710x62715',
    'json': {
    'name': 'Terry Reed',
    'address': '59351 Allison Court Suite 191\nSouth Adam, AS 26803',
},
    'key56255': 'value38206',
    'key16852': 'value26635',
    'key93763': 'value19274',
    'key74868': 'value24908',
    'key42028': 'value86635',
},
    {
    'id': 17527486968198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Kenneth Duncan',
    'address': 'USNS Lucas\nFPO AP 37369',
    'text': 'Include individual present skin east remember.\nCouple hair professional bar throughout someone goal. Would population recently task.',
    'email': 'jadams@example.org',
    'phone_number': '283.775.3994x1192',
    'json': {
    'name': 'Sarah Gross',
    'address': '09164 Brown Corner\nWest Barbarashire, PW 54712',
},
    'key34508': 'value19109',
    'key76480': 'value59602',
    'key43322': 'value22892',
    'key80024': 'value44174',
    'key57116': 'value13640',
    'key34625': 'value15773',
    'key3532': 'value73941',
},
    {
    'id': 17527486968209,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Brandon Spence',
    'address': '4472 John Place Suite 897\nNorth Deborah, TN 81092',
    'text': 'Skill avoid down job offer miss part there. Almost book its go for. Development fine play believe continue example level.',
    'email': 'jmartinez@example.com',
    'phone_number': '001-581-574-9402',
    'json': {
    'name': 'Lee Dixon',
    'address': '560 Hansen Views\nWadeton, MO 80025',
},
    'key5389': 'value76167',
    'key3171': 'value33219',
    'key77509': 'value73021',
    'key11256': 'value67210',
    'key24493': 'value80446',
},
    {
    'id': 17527486968221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Robert White',
    'address': '86884 Rachel Dale\nNew Tracy, CT 58050',
    'text': 'Hospital job draw add enjoy hotel him. Difficult wrong prevent debate light give good. Option forward none machine.',
    'email': 'rodney20@example.com',
    'phone_number': '(821)522-3026x43615',
    'json': {
    'name': 'Seth Gillespie',
    'address': '241 Donna Fort Apt. 803\nWoodsfurt, NH 64774',
},
    'key40087': 'value3276',
    'key27400': 'value3295',
    'key54647': 'value38380',
    'key10526': 'value75472',
    'key68199': 'value13334',
    'key79412': 'value57560',
    'key95579': 'value25856',
    'key5687': 'value30192',
},
    {
    'id': 17527486968232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Wendy Miller',
    'address': 'USCGC Richard\nFPO AP 96443',
    'text': 'Father there career rule require sing public country. Choice happen positive stage.\nPositive season recognize little garden prepare any conference. Laugh high fire indicate.',
    'email': 'katelyn57@example.org',
    'phone_number': '(635)393-2209x107',
    'json': {
    'name': 'Samuel Rodgers',
    'address': '990 Casey Harbor Suite 395\nMaloneburgh, MH 89449',
},
    'key53769': 'value68613',
    'key47222': 'value90563',
    'key65997': 'value33882',
    'key75831': 'value22326',
},
    {
    'id': 17527486968242,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jessica Larsen',
    'address': '85227 Jenkins Inlet\nBerryborough, VI 27226',
    'text': 'Dog themselves admit knowledge themselves owner newspaper amount. Approach will the maybe. Tough floor wall community true.',
    'email': 'tuckercheryl@example.org',
    'phone_number': '+1-654-234-6249',
    'json': {
    'name': 'Veronica Anderson',
    'address': '504 Wood Corner\nAllenton, MA 12352',
},
    'key64710': 'value79407',
    'key77659': 'value3108',
    'key4092': 'value55270',
    'key65823': 'value65864',
},
    {
    'id': 17527486968255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Patrick Ruiz',
    'address': 'PSC 0955, Box 4594\nAPO AE 44177',
    'text': 'Spend hair product detail buy different she. Church condition see lay.\nTime coach film at inside when. After week hope dinner view seat section away. Across eight city fill so.',
    'email': 'stonemark@example.com',
    'phone_number': '808.292.7497x0786',
    'json': {
    'name': 'Jessica Coffey',
    'address': '243 Cassandra Land\nNew Paulberg, MT 87513',
},
    'key56297': 'value36688',
    'key62544': 'value90783',
    'key50097': 'value18496',
},
    {
    'id': 17527486968264,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Paul Thomas',
    'address': '0622 Moore Park Suite 210\nNew Nicole, RI 70479',
    'text': 'Back town contain talk goal theory center ability. Fish similar surface board amount four. Upon condition financial blue military at owner wall. Source read sea resource.',
    'email': 'benjamin21@example.net',
    'phone_number': '001-334-537-6826x8781',
    'json': {
    'name': 'Pamela Keith',
    'address': '185 Kim Road\nClementsberg, AK 17174',
},
    'key84389': 'value53977',
    'key12017': 'value63240',
    'key13411': 'value45975',
    'key33499': 'value93838',
    'key36743': 'value80033',
    'key64845': 'value3701',
    'key65301': 'value55575',
},
    {
    'id': 17527486968275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'James Webb',
    'address': '3426 Nicole Mews\nNew Danaborough, CA 10048',
    'text': 'Body force morning feeling language guess movement challenge. Character seat major yard fear address subject.\nFirm drive appear. Or take try drop speech save rule.',
    'email': 'amandasalas@example.net',
    'phone_number': '+1-765-627-1696x833',
    'json': {
    'name': 'Robert Jones',
    'address': '51026 Luis Union\nJohnchester, WA 21197',
},
    'key56623': 'value4945',
    'key43866': 'value96997',
},
    {
    'id': 17527486968286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Caitlin Green',
    'address': '173 Smith Orchard\nJameshaven, AZ 13498',
    'text': 'Soldier environment thus area. Rich myself source language theory read. Occur reduce room.',
    'email': 'elee@example.org',
    'phone_number': '304.385.7071',
    'json': {
    'name': 'Laura Anderson',
    'address': '0793 Perez Ramp Suite 149\nCharlesfurt, MO 21223',
},
    'key30526': 'value96093',
    'key93690': 'value79545',
    'key84559': 'value23520',
    'key45397': 'value71455',
    'key84745': 'value32506',
},
    {
    'id': 17527486968297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Joseph Rogers',
    'address': 'USS Willis\nFPO AP 51511',
    'text': 'Throughout plant respond put two long then manager. Late soon story partner low save fast.',
    'email': 'matthewgonzalez@example.com',
    'phone_number': '+1-788-396-5347x5475',
    'json': {
    'name': 'Lori Brock',
    'address': '066 West Shoals Apt. 868\nBryanland, NE 29242',
},
    'key86716': 'value97475',
    'key73044': 'value60910',
    'key12051': 'value44653',
    'key13849': 'value63617',
    'key48249': 'value73697',
},
    {
    'id': 17527486968308,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Anne Nunez',
    'address': '3224 Frank Ramp\nBernardfurt, VA 72573',
    'text': 'Wear Mr under yard. Room nation development become today entire radio large.\nSummer south our environment hospital support. Ground brother save field. Game without sense task. Other ready white.',
    'email': 'hgeorge@example.org',
    'phone_number': '+1-747-937-7857x85020',
    'json': {
    'name': 'Thomas Brown',
    'address': '1132 Charles Crest\nWest Jasonland, OK 82611',
},
    'key93152': 'value76446',
    'key96440': 'value82960',
    'key40381': 'value58468',
    'key73662': 'value20060',
    'key87078': 'value84753',
    'key6572': 'value26505',
    'key31912': 'value32550',
    'key34871': 'value93595',
},
    {
    'id': 17527486968320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Theresa Gregory',
    'address': '383 Reeves Tunnel\nNorth Travis, RI 84874',
    'text': 'Entire kind threat rest include mind. Current name market likely true occur. Watch remain or sure bring. Then establish rich.',
    'email': 'tmack@example.org',
    'phone_number': '001-638-296-5958x91653',
    'json': {
    'name': 'Andre Smith',
    'address': '0824 Williamson Centers Suite 417\nMoorestad, RI 11135',
},
    'key9308': 'value16224',
    'key7358': 'value24176',
    'key31469': 'value65681',
    'key75210': 'value90741',
    'key50455': 'value23127',
    'key99181': 'value43795',
    'key56834': 'value80605',
    'key30519': 'value67478',
},
    {
    'id': 17527486968331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Tara Miller',
    'address': '048 Mark Vista Suite 287\nWest Shannonbury, AS 46893',
    'text': 'Learn expert benefit operation technology they. Data another baby list radio. Within rule conference nor.',
    'email': 'johnsonautumn@example.com',
    'phone_number': '491.922.6446x77175',
    'json': {
    'name': 'Jennifer Pittman',
    'address': '356 Nicole Underpass\nOwensport, NM 25794',
},
    'key15232': 'value58911',
    'key18901': 'value5064',
    'key958': 'value65849',
    'key5864': 'value80058',
},
    {
    'id': 17527486968343,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Nathan Maxwell',
    'address': '4600 Dylan Walks\nWest Lindseymouth, GU 10882',
    'text': 'That rich onto. Process none site see among tonight middle Republican. Action lead way camera put recognize those.\nHundred reason day indicate. Grow move late second everybody wear.',
    'email': 'kjoseph@example.com',
    'phone_number': '001-294-438-3965x3662',
    'json': {
    'name': 'Jonathan Jones',
    'address': '166 Robert Neck Suite 705\nMcgeeland, IA 62437',
},
    'key61698': 'value9718',
    'key811': 'value23323',
    'key97669': 'value32294',
    'key27228': 'value25675',
    'key51895': 'value7991',
    'key2410': 'value68944',
    'key11428': 'value65807',
    'key60428': 'value6934',
},
    {
    'id': 17527486968354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Brittany Evans',
    'address': '70493 Derrick Forks\nLake Bruceside, MN 38901',
    'text': 'Before human live entire outside drug performance. Summer work feel style bar may. Finish clear total politics instead.\nDifficult central garden ground mind.',
    'email': 'greenjanet@example.org',
    'phone_number': '393.515.6068x103',
    'json': {
    'name': 'James Hatfield',
    'address': '245 David Trafficway Apt. 751\nEatonmouth, NH 99064',
},
    'key55423': 'value79468',
    'key97713': 'value54423',
    'key2007': 'value5229',
    'key73563': 'value19433',
    'key45157': 'value8545',
    'key67749': 'value13972',
    'key12163': 'value42034',
    'key71920': 'value36220',
    'key88088': 'value38523',
},
    {
    'id': 17527486968366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Wendy Brooks',
    'address': '784 Martinez Squares\nChadview, IL 71673',
    'text': 'Away daughter least first science song. One under yeah top material performance ago situation. Not in buy own successful year.',
    'email': 'michelle92@example.org',
    'phone_number': '384-488-4253x7582',
    'json': {
    'name': 'Kathy Buckley',
    'address': '746 Daniel Via Apt. 974\nNew Richardton, MI 02586',
},
    'key51856': 'value71695',
    'key95466': 'value51218',
    'key63631': 'value76393',
},
    {
    'id': 17527486968376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Erin Fischer',
    'address': '0863 Yu Estates Apt. 381\nMurrayton, CO 82462',
    'text': 'Smile price most. Toward treatment guy character. Almost without light start go range government article.',
    'email': 'dominguezbrandon@example.com',
    'phone_number': '243-278-3630',
    'json': {
    'name': 'Ronald Horton',
    'address': '0825 Rebecca Plains\nNew Sarah, LA 54025',
},
    'key74664': 'value66120',
    'key18751': 'value72142',
    'key1118': 'value55913',
    'key76837': 'value37717',
    'key44570': 'value4261',
    'key9556': 'value90132',
    'key76239': 'value84868',
    'key3426': 'value27435',
    'key90333': 'value85844',
},
    {
    'id': 17527486968388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Meagan Perez',
    'address': '1461 James Pike Apt. 608\nKylestad, KY 09042',
    'text': 'Window black remain new. Eight pretty knowledge bring.\nDiscussion wrong majority personal be window. Church since finally near carry movie model.',
    'email': 'sue82@example.net',
    'phone_number': '(836)275-6118x65232',
    'json': {
    'name': 'Patricia Madden',
    'address': '475 Pamela Place\nEast Daisyfurt, NE 73009',
},
    'key6793': 'value87253',
    'key1184': 'value99734',
    'key3875': 'value70801',
},
    {
    'id': 17527486968399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Pamela Wiggins',
    'address': '94152 Webb Light\nSouth Joshualand, PA 83996',
    'text': 'Really site west husband sit word might. Against kitchen way time stuff each science model.\nNational spend lot soon political. Reach left church international your. West wear food.',
    'email': 'destiny72@example.com',
    'phone_number': '+1-496-530-7611x79006',
    'json': {
    'name': 'David Gutierrez',
    'address': '073 Collier Crescent\nPort Robin, IN 64787',
},
    'key61861': 'value3909',
    'key86647': 'value72220',
    'key35541': 'value65240',
    'key13128': 'value44336',
    'key54219': 'value55640',
    'key64666': 'value72257',
    'key93191': 'value31826',
    'key29751': 'value24175',
    'key56111': 'value75471',
},
    {
    'id': 17527486968410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'George Henderson',
    'address': '838 Michael Tunnel Apt. 772\nPort Laura, TN 95808',
    'text': 'Box building should girl sing. Say camera city must ago cold. Exist too become until.\nThreat environmental help sit. Provide later for interview.',
    'email': 'briannacallahan@example.org',
    'phone_number': '339.875.1704',
    'json': {
    'name': 'Paul Austin',
    'address': '0906 Patterson Highway Suite 817\nEast Johnmouth, KS 43724',
},
    'key29939': 'value83408',
    'key67689': 'value78474',
    'key62332': 'value3406',
    'key92556': 'value78193',
    'key38674': 'value86174',
},
    {
    'id': 17527486968422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jeff Mcdonald',
    'address': '71115 Ashley Ferry Apt. 720\nRachelmouth, AZ 01566',
    'text': 'Magazine recently prepare democratic ok worry. Large short believe as stage debate.\nBase art yourself network machine during safe. Up whatever anyone thank hospital.',
    'email': 'edwardsmitchell@example.net',
    'phone_number': '493.226.7833',
    'json': {
    'name': 'Tiffany Gonzalez',
    'address': '6905 Le Shoal Apt. 891\nCharlesfort, WA 33555',
},
    'key4543': 'value42353',
    'key60183': 'value95719',
    'key27220': 'value35856',
    'key66553': 'value45321',
},
    {
    'id': 17527486968434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Mrs. Lisa Brewer',
    'address': '8250 Kim Plaza\nEast Kelly, AL 33861',
    'text': 'Kitchen quality public view billion magazine business. Store yet yeah author first. Group though seat professional land early mention former.',
    'email': 'bonnieprice@example.com',
    'phone_number': '+1-685-407-4559',
    'json': {
    'name': 'David Hayes',
    'address': '2902 Lee Crescent Suite 293\nFigueroafort, WY 11777',
},
    'key1309': 'value13903',
    'key94156': 'value68576',
},
    {
    'id': 17527486968448,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Bruce Larsen',
    'address': '6152 Pierce Junction Apt. 797\nSouth Austin, IN 37305',
    'text': 'White billion through through safe debate. Though seven off his point policy hit.\nDemocratic before attack already. Sing indeed wall front yard simple. Adult what plan ground.\nCould than party among.',
    'email': 'ereyes@example.com',
    'phone_number': '001-518-317-3078x897',
    'json': {
    'name': 'Ryan Dennis',
    'address': '7479 David Isle Suite 926\nWhitneyshire, CA 42615',
},
    'key4653': 'value72845',
    'key47169': 'value89655',
    'key56553': 'value91086',
    'key60877': 'value18965',
    'key17741': 'value43227',
    'key85507': 'value30908',
    'key45840': 'value13222',
},
    {
    'id': 17527486968462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Eddie Cooper',
    'address': '804 Kirby Prairie Apt. 032\nLake Danielchester, NH 48870',
    'text': 'Loss reality word attention less far always. Color listen full small. Change operation our option.\nHimself election course teacher. Ability city cost television.',
    'email': 'meganhart@example.com',
    'phone_number': '001-376-586-7871x88732',
    'json': {
    'name': 'Nicole Ellis',
    'address': '7577 Taylor Loaf\nLeeview, KS 64654',
},
    'key32512': 'value88775',
    'key10631': 'value42085',
    'key92766': 'value61060',
    'key7583': 'value85367',
    'key1442': 'value80624',
    'key98022': 'value39995',
    'key33810': 'value4792',
    'key10668': 'value72557',
    'key3228': 'value30507',
},
    {
    'id': 17527486968474,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Kimberly Romero',
    'address': '25063 Marissa Spurs Apt. 012\nWest Stacyborough, VT 80341',
    'text': 'Where total development price make us past discuss. Newspaper force person difference ready year even. Thus rest indeed however eight state probably.',
    'email': 'jacobsonraymond@example.org',
    'phone_number': '290-834-2759x824',
    'json': {
    'name': 'Natalie Harrell',
    'address': '013 Gibson Lake\nLake Cody, WA 20097',
},
    'key58370': 'value95646',
    'key15085': 'value78814',
    'key98077': 'value63427',
},
    {
    'id': 17527486968486,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Stephanie Jones',
    'address': '3134 Madison Squares Suite 122\nPotterport, NM 07380',
    'text': 'Opportunity down film eight size Mrs together. Boy fish plan these.\nSituation activity collection beat anything off individual. Analysis upon quite smile.',
    'email': 'jmolina@example.org',
    'phone_number': '881.373.7659',
    'json': {
    'name': 'Jason Mendez',
    'address': '510 Daniel Camp Apt. 409\nWest Timothy, IN 14374',
},
    'key181': 'value65640',
    'key90500': 'value34189',
    'key5078': 'value95436',
    'key39149': 'value63332',
    'key27030': 'value26001',
    'key75332': 'value90432',
},
    {
    'id': 17527486968497,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Elizabeth Jennings',
    'address': '51178 Stephen Mews Apt. 356\nFosterberg, AS 82474',
    'text': 'Send happen house discussion affect. More ago so many mention. Pattern measure even.\nCarry those air site third always. Paper expert doctor my focus. Sound partner father this company of.',
    'email': 'leerobinson@example.com',
    'phone_number': '9736743641',
    'json': {
    'name': 'Holly Giles',
    'address': '7515 Kevin Cliffs Suite 467\nPort Joseph, AK 65351',
},
    'key83047': 'value58928',
    'key41302': 'value69498',
    'key90246': 'value68237',
    'key23498': 'value13303',
    'key34176': 'value14428',
    'key7027': 'value38898',
    'key75745': 'value32261',
    'key33800': 'value796',
    'key97215': 'value75769',
    'key62193': 'value4521',
},
    {
    'id': 17527486968509,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Katherine Valenzuela',
    'address': '55938 Lawrence Keys Suite 792\nWufurt, SD 84183',
    'text': 'Second protect finish recently on individual. Red nature crime example end.\nSuch cover entire seat candidate thousand. International kitchen tell explain role hair.',
    'email': 'melissa76@example.com',
    'phone_number': '2747585408',
    'json': {
    'name': 'Bethany Cole',
    'address': '7056 Jim Gardens Apt. 280\nWest Nicholas, MS 46729',
},
    'key30179': 'value26101',
    'key704': 'value47508',
    'key29143': 'value4462',
},
    {
    'id': 17527486968520,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Sarah Vega',
    'address': '9092 Michael Walk\nSouth Ralphton, OK 96987',
    'text': 'Personal throughout include push. Film station tell accept rise less.\nSkin send remember day opportunity project character on. Out name out drive.',
    'email': 'kingbrian@example.net',
    'phone_number': '918-413-2619x6338',
    'json': {
    'name': 'Adrian Ferrell',
    'address': '999 Richard Plaza Suite 210\nKirbymouth, GU 53935',
},
    'key34646': 'value40302',
    'key25025': 'value47553',
    'key7285': 'value63188',
    'key71869': 'value77528',
    'key644': 'value51010',
    'key96146': 'value38098',
    'key65476': 'value89035',
    'key294': 'value47732',
    'key10137': 'value33336',
    'key96030': 'value24230',
},
    {
    'id': 17527486968532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jacob Williams',
    'address': '28389 Jennifer Fork\nThompsonside, NJ 94708',
    'text': 'Explain clearly military participant together computer join. As within force across north form activity. Director add push garden pass.',
    'email': 'eduke@example.net',
    'phone_number': '(822)374-8877',
    'json': {
    'name': 'Alisha Roberts',
    'address': '2616 Christopher Via\nNorth Scottfort, MH 73322',
},
    'key93832': 'value6256',
    'key79789': 'value28318',
    'key89438': 'value89193',
    'key33883': 'value92238',
    'key51973': 'value4756',
    'key5134': 'value29782',
    'key36583': 'value54579',
    'key99978': 'value71732',
    'key97906': 'value7066',
},
    {
    'id': 17527486968543,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Kevin Hampton',
    'address': '78002 Stevenson Squares\nShortmouth, MD 63662',
    'text': 'Economic education despite. Likely million church shake exist. Drive respond instead together design specific.\nPainting late upon exist.',
    'email': 'morrisonlisa@example.com',
    'phone_number': '(267)641-3425x345',
    'json': {
    'name': 'Kim Harris',
    'address': '103 Wagner Squares Suite 541\nNorth Pamelaburgh, MD 03060',
},
    'key85768': 'value11120',
    'key43982': 'value34157',
    'key61918': 'value21301',
    'key60909': 'value47490',
    'key82756': 'value28514',
    'key29241': 'value40092',
    'key61842': 'value79806',
    'key3557': 'value28300',
    'key26053': 'value97632',
},
    {
    'id': 17527486968555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'William Shaffer',
    'address': '2763 Underwood Valleys\nErichaven, KS 67918',
    'text': 'Soon tell air growth close beyond. Loss sell million best four. Only town home role.\nForeign poor heart fast popular security your.',
    'email': 'wbell@example.org',
    'phone_number': '+1-729-519-7218',
    'json': {
    'name': 'Alex Montgomery',
    'address': '97104 Eaton Drive Apt. 732\nEast Brandon, MI 74207',
},
    'key4825': 'value36489',
    'key87227': 'value23982',
    'key68559': 'value71120',
    'key8412': 'value20652',
    'key8402': 'value82719',
    'key56482': 'value85131',
    'key34624': 'value74898',
    'key22332': 'value70706',
    'key94451': 'value61722',
},
    {
    'id': 17527486968566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Austin Snyder',
    'address': 'Unit 3601 Box 8442\nDPO AP 34347',
    'text': 'Computer agent quite while culture professor. Article or hand idea still. Me look today foot contain medical change. Dark public worker language.\nTrip door past.',
    'email': 'berryrichard@example.net',
    'phone_number': '+1-705-702-0136',
    'json': {
    'name': 'Michael Bauer',
    'address': '572 Jones Plain\nCarlsonstad, MH 31862',
},
    'key13104': 'value13118',
    'key36585': 'value92983',
    'key60542': 'value26974',
    'key70218': 'value80105',
    'key10063': 'value76405',
    'key97678': 'value56778',
    'key85219': 'value27376',
    'key92009': 'value37159',
    'key22916': 'value92860',
    'key15797': 'value10564',
},
    {
    'id': 17527486968576,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Jonathan Austin',
    'address': '9306 Timothy Via\nEast Juan, NV 14735',
    'text': 'Management Republican both future. Can long interesting end future. Many common way black point hundred economic.',
    'email': 'michelle69@example.org',
    'phone_number': '+1-594-310-9927',
    'json': {
    'name': 'Elizabeth Carpenter',
    'address': '13612 Scott Rapids Apt. 667\nLake Wayne, CO 25166',
},
    'key237': 'value22375',
    'key74599': 'value1670',
    'key24058': 'value12615',
    'key16119': 'value88728',
    'key80619': 'value79129',
    'key40423': 'value85848',
    'key17140': 'value5724',
    'key98272': 'value4841',
    'key87186': 'value70231',
    'key83782': 'value16403',
},
    {
    'id': 17527486968586,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Samantha Galloway',
    'address': 'USS Morgan\nFPO AP 15864',
    'text': 'Determine be nation they begin increase. According consumer energy even free also. Whether lead buy act.\nSchool none indicate. Half ability open value daughter explain.',
    'email': 'wayne65@example.net',
    'phone_number': '(481)280-2800x37843',
    'json': {
    'name': 'Jason Hughes',
    'address': '599 Lisa Isle\nSouth Carol, FM 22484',
},
    'key17455': 'value97530',
    'key44911': 'value81396',
    'key53452': 'value53644',
},
    {
    'id': 17527486968595,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Michael Fisher',
    'address': '20764 Kelly Ranch\nEast Katelynborough, CA 08272',
    'text': 'Carry nature population. Onto growth hit Mr environment. Available science product source mention town head.\nInstitution find goal game upon. Matter brother like.\nWay book same his size source stop.',
    'email': 'cvasquez@example.com',
    'phone_number': '6223584735',
    'json': {
    'name': 'Mary Lawson',
    'address': '29428 Becky Lakes Apt. 553\nBrittanychester, VI 76795',
},
    'key29138': 'value67308',
    'key87668': 'value77250',
    'key17931': 'value50464',
    'key39154': 'value8535',
    'key30722': 'value63504',
    'key34518': 'value87209',
    'key26998': 'value72888',
    'key14854': 'value33331',
    'key76181': 'value39629',
    'key53244': 'value94678',
},
    {
    'id': 17527486968606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Hannah Bryant',
    'address': '342 Owens Groves Suite 999\nEast Alexa, VA 41102',
    'text': 'Chair live prevent. Return worker painting significant eight. Whatever than serious defense section.',
    'email': 'ronald55@example.com',
    'phone_number': '200-877-5549',
    'json': {
    'name': 'Kaitlyn Buckley',
    'address': '320 Luis Roads Apt. 438\nJohnsonburgh, GA 53063',
},
    'key32691': 'value38425',
    'key10130': 'value87753',
    'key46077': 'value88524',
    'key72859': 'value30401',
    'key75480': 'value86267',
    'key42301': 'value7596',
    'key45035': 'value14411',
},
    {
    'id': 17527486968617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kenneth Taylor',
    'address': '072 Amanda Villages Suite 152\nLaurenfort, HI 75930',
    'text': 'Race place receive source safe. Left perhaps continue follow necessary. Group budget though few money that involve student.\nLess throughout several foreign human. Range civil assume anything.',
    'email': 'johnlewis@example.net',
    'phone_number': '4558358365',
    'json': {
    'name': 'Lindsey Tucker',
    'address': 'Unit 8989 Box 6376\nDPO AA 40272',
},
    'key5332': 'value24695',
    'key70470': 'value46779',
    'key11458': 'value38328',
    'key76700': 'value8778',
    'key90373': 'value65400',
    'key64880': 'value53415',
    'key72532': 'value21936',
},
    {
    'id': 17527486968626,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Kenneth Garcia',
    'address': '595 Kenneth Shores Apt. 860\nSouth Scottstad, CT 62273',
    'text': 'Require sea authority hard nature.\nCapital seat back human wish forget. Food face kind within democratic town. Themselves else event throughout.',
    'email': 'rossdenise@example.net',
    'phone_number': '+1-907-966-2864x55502',
    'json': {
    'name': 'Matthew Thomas',
    'address': '92231 Kim Parkway\nNew Stephanie, MT 66820',
},
    'key93324': 'value4263',
    'key27201': 'value48724',
    'key87131': 'value19690',
    'key84836': 'value57385',
    'key37031': 'value74742',
    'key32694': 'value28995',
    'key66915': 'value99846',
    'key27427': 'value35827',
},
    {
    'id': 17527486968637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Dylan Smith',
    'address': 'Unit 6106 Box 8677\nDPO AP 49471',
    'text': 'Study almost religious control. Picture yourself enter low owner. Just turn remember.',
    'email': 'cunninghamalyssa@example.com',
    'phone_number': '439.646.2601x566',
    'json': {
    'name': 'Andrew Chung',
    'address': '4082 Castaneda Village\nDavisside, MN 63426',
},
    'key17739': 'value62515',
    'key85202': 'value23044',
    'key43543': 'value30449',
    'key20366': 'value28911',
},
    {
    'id': 17527486968647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Tyler Murray',
    'address': '877 Carter Course\nNorth Harrymouth, SC 28560',
    'text': 'Trip nothing range central father whether decision.',
    'email': 'iwilliams@example.net',
    'phone_number': '(269)664-0299x607',
    'json': {
    'name': 'Samuel Torres',
    'address': '713 Coffey Harbor Suite 913\nJuliamouth, NC 44276',
},
    'key69955': 'value98093',
    'key30367': 'value15424',
    'key1999': 'value32926',
    'key10622': 'value73684',
    'key49076': 'value84864',
    'key73194': 'value82071',
    'key13701': 'value67848',
},
    {
    'id': 17527486968657,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Nina Cook',
    'address': '24126 Brandon View\nSouth Nicholas, DE 36611',
    'text': 'Interview success speech pattern evidence south commercial.\nImage sport election development everybody better stock. Surface religious under thus consider. Husband hot day goal available.',
    'email': 'vrodriguez@example.org',
    'phone_number': '+1-322-267-7653x61245',
    'json': {
    'name': 'Reginald Brewer',
    'address': '4953 Keith Plains\nWest Brandy, NV 48555',
},
    'key23268': 'value70593',
    'key31126': 'value83219',
    'key43099': 'value79119',
    'key76578': 'value39120',
    'key95242': 'value87446',
    'key33282': 'value58076',
    'key87069': 'value64995',
    'key43128': 'value41128',
},
    {
    'id': 17527486968668,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Samantha Rodriguez',
    'address': '8016 Steven Burgs\nGardnerburgh, FL 99389',
    'text': 'Fill me step town bit baby. But apply stuff. Recently about position positive yard difficult improve.',
    'email': 'brandon56@example.org',
    'phone_number': '542-800-6925',
    'json': {
    'name': 'Courtney Miller',
    'address': 'Unit 2084 Box 1255\nDPO AA 99915',
},
    'key82634': 'value34478',
    'key52356': 'value7506',
    'key96964': 'value48090',
},
    {
    'id': 17527486968676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Gregory Lloyd',
    'address': '64530 Maria Shoal\nPort Valeriestad, IL 28824',
    'text': 'Wear show south reality ago. Worker painting involve factor.\nCause per purpose moment call itself guess. Various thank policy win her create. Chance value help put successful.',
    'email': 'valeriehensley@example.org',
    'phone_number': '579.253.3049',
    'json': {
    'name': 'Kimberly Higgins',
    'address': '894 Phillip Terrace Apt. 678\nNorth Devinhaven, ME 26229',
},
    'key9847': 'value72146',
    'key58795': 'value97682',
    'key16227': 'value26995',
    'key39332': 'value23981',
    'key47046': 'value11891',
    'key66905': 'value46394',
    'key46580': 'value45955',
    'key1884': 'value28388',
},
    {
    'id': 17527486968687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Keith Flowers',
    'address': '70555 Timothy Coves Suite 317\nSouth Courtneybury, PW 78944',
    'text': 'Space owner card brother. Help as admit after help manager apply.\nReflect right skill single control another.',
    'email': 'andersonpatricia@example.net',
    'phone_number': '(273)581-9411',
    'json': {
    'name': 'Katherine Harrell',
    'address': '37261 Lisa Turnpike Apt. 631\nWendystad, MT 35757',
},
    'key73775': 'value65157',
    'key81442': 'value36279',
    'key14027': 'value93670',
    'key91564': 'value76500',
},
    {
    'id': 17527486968699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Kelly Paul Jr.',
    'address': '31208 Steven Lodge Suite 855\nMartinfurt, WV 60321',
    'text': 'Eye whole sound forget. Remain dinner stock cultural. Evidence bad population issue money drug special.\nOccur avoid day price message leave. Lose nice above move.',
    'email': 'courtney62@example.com',
    'phone_number': '564.436.2826',
    'json': {
    'name': 'Rebekah Davis',
    'address': '66745 Myers Squares\nAllisontown, OH 94356',
},
    'key5626': 'value71339',
    'key99788': 'value99216',
},
    {
    'id': 17527486968709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Nicholas Oneal',
    'address': '55001 Michelle Prairie\nHawkinsville, NV 18328',
    'text': 'Myself news peace child. See simply suffer general. Good environmental activity way let car card.',
    'email': 'pscott@example.org',
    'phone_number': '796-863-6262x7188',
    'json': {
    'name': 'Jennifer Irwin',
    'address': '4896 Raymond Rapids Apt. 198\nWilliamstad, MT 88637',
},
    'key52485': 'value37744',
    'key7317': 'value96157',
    'key95292': 'value19955',
    'key6958': 'value38738',
    'key80890': 'value53764',
    'key72566': 'value52126',
    'key11477': 'value90563',
    'key56596': 'value52674',
    'key77057': 'value91619',
},
    {
    'id': 17527486968720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christopher Hamilton',
    'address': '878 Peter Rapid Apt. 185\nLake Bryan, CA 87410',
    'text': 'Will gas television school have action story law. Could others former source water. Firm per stand measure.',
    'email': 'rachael81@example.com',
    'phone_number': '269.577.4336x89387',
    'json': {
    'name': 'Roger Bullock',
    'address': '3124 Sarah Dam\nWilliamstown, DE 91399',
},
    'key94152': 'value99354',
    'key70797': 'value93946',
    'key99064': 'value89143',
    'key37626': 'value13535',
    'key74081': 'value25203',
},
    {
    'id': 17527486968730,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Taylor Johnson',
    'address': '6254 Madison Ports\nMeganmouth, FM 28990',
    'text': 'Open tax subject mean. Best stuff share television share process approach listen. Experience customer hard clearly. Firm establish war parent near thank election official.',
    'email': 'kristin96@example.net',
    'phone_number': '(354)797-0138x995',
    'json': {
    'name': 'Nicholas Bell',
    'address': 'PSC 6833, Box 7127\nAPO AA 03313',
},
    'key65214': 'value52092',
    'key53153': 'value53719',
    'key68674': 'value38762',
    'key38729': 'value39805',
    'key15684': 'value94233',
    'key80736': 'value74182',
    'key72245': 'value12165',
    'key56925': 'value96394',
    'key90627': 'value63173',
},
    {
    'id': 17527486968739,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Jessica Anderson',
    'address': '23596 Davis Mission Suite 954\nCarlfort, AS 45155',
    'text': 'Civil senior necessary four shoulder crime.\nAppear low already fall yard. Kind together star these sign lawyer star.',
    'email': 'kimberlybowen@example.org',
    'phone_number': '647-811-5434',
    'json': {
    'name': 'Timothy Johnson',
    'address': '51512 Calvin Coves Apt. 896\nChristiantown, CT 14973',
},
    'key50030': 'value99102',
    'key78097': 'value77360',
    'key2653': 'value80885',
},
    {
    'id': 17527486968749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Chelsea Estrada',
    'address': 'PSC 6072, Box 9706\nAPO AE 66913',
    'text': 'Note response environment billion star action. Option sign method kid you lay message this. Attack writer section modern same manage practice source. Head head financial federal teach fear.',
    'email': 'lbarrett@example.net',
    'phone_number': '628-233-1294',
    'json': {
    'name': 'Monica Morris',
    'address': '889 Blake Mews\nEast Brenda, FM 76113',
},
    'key84957': 'value52538',
    'key3127': 'value94136',
    'key17508': 'value88297',
    'key88322': 'value84802',
    'key99386': 'value81910',
},
    {
    'id': 17527486968758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Miss Samantha Ryan MD',
    'address': '89844 David Points\nAshleyfurt, CO 87026',
    'text': 'Performance forget young. Forget Mr standard. Reflect expert these serious rate good even.\nAct fish business station like relate. Garden public fine chance too young fund.',
    'email': 'barkermark@example.org',
    'phone_number': '538.959.2620x33587',
    'json': {
    'name': 'John Rodriguez',
    'address': '23148 Ann Prairie\nWest Davidshire, MS 25201',
},
    'key13410': 'value41623',
    'key24627': 'value56167',
    'key97757': 'value83439',
    'key44463': 'value26157',
    'key37746': 'value43493',
    'key74035': 'value66283',
    'key7918': 'value36283',
    'key4202': 'value95406',
},
    {
    'id': 17527486968769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Troy Estrada',
    'address': '996 Beard Street Suite 478\nMariahaven, CT 99429',
    'text': 'Actually wall a buy discuss watch first. Rest floor decade produce wish.\nSpecial though sort bad. Read down Mr day debate son large. First stand message democratic discover low subject customer.',
    'email': 'nelsontamara@example.net',
    'phone_number': '801-670-9768',
    'json': {
    'name': 'Christopher Miller',
    'address': '17120 Atkinson Ranch\nEast Timothy, IA 94110',
},
    'key95002': 'value81349',
    'key48854': 'value51933',
    'key59830': 'value60091',
    'key23393': 'value47428',
    'key57817': 'value68239',
    'key56717': 'value66539',
    'key39022': 'value94606',
},
    {
    'id': 17527486968781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Alexander Allen DDS',
    'address': '943 Andrea Freeway Apt. 666\nSouth Melindaport, KY 52639',
    'text': 'Rich picture traditional majority against attention. Necessary after lose. Professional nothing against security.',
    'email': 'kmontgomery@example.com',
    'phone_number': '001-338-717-7360x3189',
    'json': {
    'name': 'Michael Lucas',
    'address': 'PSC 0196, Box 4701\nAPO AP 13746',
},
    'key5783': 'value22648',
    'key3669': 'value74798',
    'key8147': 'value20516',
    'key77586': 'value48350',
    'key55024': 'value49459',
    'key35840': 'value12388',
    'key87083': 'value4674',
    'key40438': 'value11251',
    'key94913': 'value63581',
},
    {
    'id': 17527486968790,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Maria Baker',
    'address': '0003 Tina Villages\nNorth Stephanieside, WA 78855',
    'text': 'First will wear fire actually bill save know.\nUse generation exactly speak. Democratic company camera each. Child citizen research start something ready suggest.',
    'email': 'wspence@example.org',
    'phone_number': '(326)938-4391x134',
    'json': {
    'name': 'Jason Meyers',
    'address': '067 Green Fall\nEast Shane, NJ 67683',
},
    'key56078': 'value89770',
    'key39206': 'value48787',
    'key79570': 'value57346',
    'key11887': 'value10215',
    'key84080': 'value18689',
    'key77898': 'value21787',
    'key52114': 'value45134',
    'key74044': 'value68471',
    'key48523': 'value65966',
},
    {
    'id': 17527486968801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kathy Quinn',
    'address': '3827 Juarez Overpass Apt. 094\nEricberg, NV 00815',
    'text': 'Network painting after body wind. Garden institution quickly another officer. Police certain carry itself religious.',
    'email': 'eterrell@example.com',
    'phone_number': '+1-536-997-1747x02621',
    'json': {
    'name': 'Ashley Nelson',
    'address': '52068 Chandler Lane Suite 520\nLake Kevinburgh, DC 56149',
},
    'key25542': 'value4713',
},
    {
    'id': 17527486968814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jennifer Wilkinson',
    'address': '1097 Davis Lake\nSouth Mary, CT 03003',
    'text': 'Cultural pull federal protect prove head. Fall time evening free. Information only above.\nReach majority building relate really cup late although. Edge view itself finally.',
    'email': 'owensjacob@example.net',
    'phone_number': '824-662-7817',
    'json': {
    'name': 'Julia Lowe',
    'address': 'USNS Crosby\nFPO AP 45610',
},
    'key77404': 'value27096',
},
    {
    'id': 17527486968825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'David Brown',
    'address': '936 Antonio Bridge Suite 489\nSouth Sophiamouth, GA 16792',
    'text': 'Deal western effect couple suffer physical wish. Any much hard sister goal main hope entire. Decision seven since inside magazine draw.',
    'email': 'vanessamccullough@example.org',
    'phone_number': '(755)489-6830x555',
    'json': {
    'name': 'Nicole Turner',
    'address': '302 James Dale Suite 673\nNorth Petermouth, NM 74547',
},
    'key18206': 'value47584',
    'key39245': 'value11384',
    'key75507': 'value31144',
    'key22870': 'value2676',
    'key41571': 'value38604',
    'key65344': 'value94182',
    'key67545': 'value8377',
    'key65916': 'value88764',
},
    {
    'id': 17527486968837,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Lisa Hawkins',
    'address': '5051 Peggy Pike\nLake Michaelchester, NJ 93860',
    'text': 'Practice fish option in. Before still seven against dream trip.\nMaybe write sport bar him enter every. Authority through begin wall form home girl. Player budget offer after garden say list.',
    'email': 'todd40@example.net',
    'phone_number': '001-201-420-3200x655',
    'json': {
    'name': 'Ryan Garcia',
    'address': '71573 Richardson Drive\nWrightchester, NH 29039',
},
    'key88930': 'value92896',
    'key30679': 'value27641',
    'key99989': 'value71495',
    'key27808': 'value55748',
    'key28398': 'value66936',
    'key92957': 'value89297',
},
    {
    'id': 17527486968849,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Paul Williams',
    'address': '894 Richards Keys\nWest Kim, CT 11079',
    'text': 'Hour feeling church what. Final heavy face magazine.\nSea education fear Mr member.',
    'email': 'tatenicole@example.net',
    'phone_number': '001-927-607-6090x44137',
    'json': {
    'name': 'Angela Gilbert',
    'address': '33664 Scott Lights Apt. 154\nLake Billychester, OR 42508',
},
    'key14152': 'value32190',
    'key37735': 'value56645',
    'key97070': 'value73783',
    'key96797': 'value28890',
    'key86459': 'value79740',
    'key69235': 'value29012',
    'key88878': 'value56179',
},
    {
    'id': 17527486968861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Karla Moore',
    'address': '2226 Timothy Path Apt. 727\nThomasberg, AZ 33736',
    'text': 'Road inside animal into development. Under college law my occur window amount for. This speech draw hair community time.',
    'email': 'orice@example.com',
    'phone_number': '(698)569-5255',
    'json': {
    'name': 'John Ward',
    'address': '1267 Roberta Expressway\nEast Terrimouth, TX 26733',
},
    'key38401': 'value20182',
    'key57286': 'value838',
    'key25776': 'value35732',
    'key840': 'value83211',
},
    {
    'id': 17527486968872,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Bonnie Cannon',
    'address': '643 Hull Summit Apt. 662\nWest Robertfurt, KS 99565',
    'text': 'Take need economic reason. Receive Congress check score nature. Not themselves argue call.\nBase almost place speak give. Popular quite bar part home.',
    'email': 'joy23@example.com',
    'phone_number': '882.735.0286',
    'json': {
    'name': 'Lisa Duarte',
    'address': '26336 Randolph Parkways\nBennettberg, PR 03091',
},
    'key94737': 'value90535',
    'key566': 'value3459',
},
    {
    'id': 17527486968884,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mr. Joshua Powell',
    'address': '0258 Karen Route Apt. 771\nNew Coreyview, DE 88828',
    'text': 'Often investment him. Lay trade certain common your. Only show news wide.',
    'email': 'fbarnett@example.net',
    'phone_number': '001-892-732-3885x42619',
    'json': {
    'name': 'Robert Murray',
    'address': '7379 Anthony Pass\nWrightborough, AL 08368',
},
    'key91238': 'value49612',
    'key12862': 'value82521',
    'key56913': 'value56112',
    'key58043': 'value46972',
    'key10568': 'value74127',
    'key37981': 'value56706',
    'key43341': 'value17877',
    'key76295': 'value93253',
    'key65851': 'value66721',
},
    {
    'id': 17527486968895,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Curtis Aguilar',
    'address': '15267 Parker Points\nRamirezbury, NJ 44073',
    'text': 'House suffer number learn film road eye.\nSee mention until enter old. Herself mention daughter pass yes themselves contain.',
    'email': 'teresawhite@example.org',
    'phone_number': '(314)260-5005x080',
    'json': {
    'name': 'Bryan Foster',
    'address': '4910 Watkins Knolls\nBrittanyberg, SC 80730',
},
    'key79885': 'value93292',
    'key35464': 'value52198',
},
    {
    'id': 17527486968906,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Susan Sullivan',
    'address': '0130 Smith Extension Apt. 836\nNew Jay, MT 03210',
    'text': 'Firm effect memory whether bit education price. Their operation dark draw. Care group worker huge prevent manager.\nFear serve raise at consumer mean. Its agree involve president play some move.',
    'email': 'williamlozano@example.net',
    'phone_number': '310-530-8058',
    'json': {
    'name': 'Nicole Schroeder',
    'address': '99345 Sherry Prairie Apt. 268\nNew Matthewberg, RI 62745',
},
    'key7708': 'value12043',
},
    {
    'id': 17527486968918,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Stephanie Powell',
    'address': 'Unit 8059 Box 0791\nDPO AA 00794',
    'text': 'Officer radio fine sign administration. At voice across daughter buy. News onto father if. Box five PM moment difference.\nSon story speak develop. Card beautiful then try figure something.',
    'email': 'lewisgabrielle@example.org',
    'phone_number': '618.400.4776x5647',
    'json': {
    'name': 'Kenneth Diaz',
    'address': '04337 Ronald Square\nLamberttown, OK 28291',
},
    'key40298': 'value58957',
    'key86110': 'value68532',
    'key43007': 'value84170',
    'key8675': 'value36665',
    'key73749': 'value81444',
    'key14570': 'value85515',
},
    {
    'id': 17527486968928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jessica Freeman',
    'address': '90045 Silva Light Suite 751\nJordanchester, OR 29877',
    'text': 'Member enough character section. Spring foreign many reality other protect. Able stage attack night shake maintain often.',
    'email': 'tranhayley@example.net',
    'phone_number': '741-758-8225',
    'json': {
    'name': 'Jesse Reyes',
    'address': '4686 Marquez Knolls Apt. 858\nNew Ann, KY 08300',
},
    'key99096': 'value10867',
    'key36382': 'value30979',
    'key44777': 'value67239',
    'key31367': 'value55859',
    'key74854': 'value94507',
},
    {
    'id': 17527486968939,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Melanie Arnold',
    'address': '00800 Atkins Avenue\nNorth Lauraville, MS 70877',
    'text': 'Where group doctor baby middle.\nOn sit yet look action hear first. Together address attention. Floor third those avoid.\nWith effort table take.',
    'email': 'otaylor@example.com',
    'phone_number': '694-951-7529',
    'json': {
    'name': 'Kristen Murray',
    'address': '2690 Juan Green Apt. 026\nEast Sheilafurt, PW 50255',
},
    'key17875': 'value11712',
    'key73552': 'value90065',
    'key98630': 'value75968',
    'key90735': 'value59661',
    'key13021': 'value29742',
    'key47244': 'value95671',
    'key63474': 'value44275',
},
    {
    'id': 17527486968950,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Scott Perez',
    'address': '957 Foster Lake\nChristopherborough, PA 88934',
    'text': 'Power lot church true. Send upon our everything lot pretty dog.\nStyle industry hand worry much treatment. Note executive you difficult will thing check.\nElection area because name.',
    'email': 'jeffrey39@example.org',
    'phone_number': '+1-656-874-0886x2708',
    'json': {
    'name': 'Michael Alexander',
    'address': 'Unit 7666 Box 4992\nDPO AA 95689',
},
    'key26162': 'value11474',
    'key84593': 'value35928',
    'key91445': 'value73446',
},
    {
    'id': 17527486968959,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Randy Howard',
    'address': '649 Smith Land\nSharonchester, UT 78046',
    'text': 'Probably walk religious yes dinner out summer.\nPolitical group skin case. Modern game painting partner hundred mind respond. History we clear.',
    'email': 'johnfrazier@example.com',
    'phone_number': '(874)246-8772',
    'json': {
    'name': 'Dorothy Skinner',
    'address': '35804 Frances Drive\nBradleytown, ID 50654',
},
    'key56816': 'value20530',
    'key54014': 'value44554',
    'key29813': 'value43907',
    'key80062': 'value8129',
    'key53574': 'value6897',
},
    {
    'id': 17527486968970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Wesley Montgomery',
    'address': '8857 Kellie Ferry\nMcclurebury, PR 99290',
    'text': 'Say eat that. Matter since third step east thank sign stand.\nQuickly out father between plant. Knowledge all project early clear.\nYourself say food material. Continue appear true next plant two.',
    'email': 'kinglaurie@example.net',
    'phone_number': '439.831.7723',
    'json': {
    'name': 'Dana Suarez',
    'address': '65566 James Drive\nEast Karen, WY 12034',
},
    'key58671': 'value68195',
    'key69445': 'value71812',
    'key31928': 'value29911',
    'key33502': 'value92015',
},
    {
    'id': 17527486968981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Christian Hodges',
    'address': '58729 Armstrong Mountains\nWest Vanessa, MH 65444',
    'text': 'Sure practice would middle mind. Born interesting customer add. Month task defense focus.\nReflect magazine among court would employee arm.',
    'email': 'hoodmargaret@example.com',
    'phone_number': '+1-256-491-7519x665',
    'json': {
    'name': 'Robert Marquez',
    'address': '12259 Rhonda Mount Suite 505\nEast Meredithberg, CT 17199',
},
    'key25533': 'value35196',
    'key16733': 'value40417',
    'key13261': 'value71710',
    'key78809': 'value52713',
},
    {
    'id': 17527486968993,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Austin Edwards',
    'address': 'USNV Singleton\nFPO AE 69352',
    'text': 'Key common action drug nation. Young executive reality suffer.\nNot spend base perform seat me. Sell late team building exist entire way. Create type machine behind very go difference.',
    'email': 'charlessampson@example.com',
    'phone_number': '2733908297',
    'json': {
    'name': 'Darryl Brown',
    'address': 'Unit 2106 Box 6922\nDPO AP 06464',
},
    'key40595': 'value1389',
    'key19699': 'value90843',
    'key20014': 'value80539',
    'key73301': 'value9602',
    'key90892': 'value18391',
},
    {
    'id': 17527486969001,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Brenda Brown',
    'address': '17574 Troy Row Apt. 621\nLake Jeffreyborough, MT 92374',
    'text': 'City personal record prove car have. Bed democratic right.\nStaff film hold less discuss rest conference. Look clearly fear.',
    'email': 'mccarthyangela@example.net',
    'phone_number': '+1-696-391-2816x40351',
    'json': {
    'name': 'Carolyn Hall',
    'address': '286 Tyler Squares Apt. 622\nCoxmouth, AR 98646',
},
    'key53506': 'value97418',
},
    {
    'id': 17527486969012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Sonya Miller',
    'address': '621 Callahan Extension\nNew Steven, OK 16021',
    'text': 'Tree especially main million central structure. Course item my. Dog with perform either organization house next. Country green give final.',
    'email': 'jamesmcpherson@example.net',
    'phone_number': '2967876320',
    'json': {
    'name': 'Christopher Finley',
    'address': 'PSC 3173, Box 2844\nAPO AE 40352',
},
    'key52673': 'value10718',
    'key31547': 'value87732',
    'key42385': 'value86177',
    'key42887': 'value96990',
    'key63941': 'value64038',
    'key21741': 'value64769',
    'key98619': 'value22904',
},
    {
    'id': 17527486969021,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Cathy Williams',
    'address': '4330 Amanda Center\nNew Randall, GA 37501',
    'text': 'Window identify cup put policy better. Personal mission from over. The building some four indicate.\nWith candidate member memory person fall common. Soon standard several yard.',
    'email': 'hannahfuentes@example.net',
    'phone_number': '791.926.9589',
    'json': {
    'name': 'Julie Greene',
    'address': '5862 Padilla Stream Suite 395\nNew Saraside, AK 58494',
},
    'key47134': 'value4212',
    'key67172': 'value4077',
    'key32215': 'value31593',
    'key33387': 'value10317',
    'key42015': 'value26031',
    'key20373': 'value98350',
    'key12651': 'value10252',
    'key4509': 'value62469',
},
    {
    'id': 17527486969033,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Stephen Graves',
    'address': '7427 King Forest Apt. 086\nPort Stacey, MT 51039',
    'text': 'Indeed attorney something card western professional experience. Type finally no work power quickly majority. One American my particularly say.',
    'email': 'freymichael@example.org',
    'phone_number': '354.753.7314x502',
    'json': {
    'name': 'Eugene Murphy',
    'address': '1635 Pamela Falls Suite 130\nEast Taylor, UT 01303',
},
    'key80442': 'value42077',
    'key31821': 'value798',
    'key2352': 'value41371',
    'key14695': 'value82904',
    'key94124': 'value53801',
},
    {
    'id': 17527486969044,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Caroline Watson',
    'address': '358 Johnson Corners\nMartinezbury, FM 90993',
    'text': 'Explain community finally past TV ever.\nFall line toward language north go step power.',
    'email': 'rebeccaaguilar@example.com',
    'phone_number': '001-912-970-1524',
    'json': {
    'name': 'Debbie Riddle',
    'address': 'USS Mora\nFPO AP 52259',
},
    'key7317': 'value94046',
    'key7446': 'value26142',
    'key84501': 'value34591',
    'key69021': 'value4489',
},
    {
    'id': 17527486969055,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Lauren Mitchell',
    'address': '109 Cook Cove\nNew Rebeccaborough, NM 96395',
    'text': 'Number father food run many race. Message better court your travel.\nPlace into south. Art game meet campaign only recognize age. Himself upon foot need almost beyond charge.',
    'email': 'laura37@example.org',
    'phone_number': '7446067317',
    'json': {
    'name': 'Donald Fields',
    'address': '171 Sims Glens Apt. 405\nFrankview, KS 03259',
},
    'key65189': 'value32687',
    'key44795': 'value31090',
    'key10471': 'value74722',
    'key31837': 'value39579',
    'key43087': 'value50788',
    'key59992': 'value46983',
    'key43275': 'value26567',
    'key94223': 'value85747',
    'key64899': 'value859',
},
    {
    'id': 17527486969066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Karen Adams',
    'address': '39944 Anthony Green\nLake Seanshire, MH 44249',
    'text': 'Store now attention field. Say against administration receive see necessary.\nMillion number six community drug push. Produce policy course number act kind their.',
    'email': 'dcameron@example.com',
    'phone_number': '001-667-227-2876x856',
    'json': {
    'name': 'Douglas Johnson',
    'address': '2524 Brenda Turnpike Suite 610\nWoodland, WY 58640',
},
    'key99720': 'value99214',
    'key27992': 'value58517',
    'key66110': 'value12474',
    'key53906': 'value46323',
    'key47944': 'value41740',
    'key65111': 'value73749',
},
    {
    'id': 17527486969076,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'George Rodriguez',
    'address': '848 Zachary Summit Suite 091\nSouth Michael, VA 53238',
    'text': 'Firm yard main attack hand add smile. Provide specific role major.',
    'email': 'christycross@example.com',
    'phone_number': '+1-212-273-9858x503',
    'json': {
    'name': 'Robert Vega',
    'address': '16434 Kathryn Brook\nWest Jennifertown, GU 71773',
},
    'key46312': 'value43060',
},
    {
    'id': 17527486969087,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Thomas Smith',
    'address': '686 Ian Alley\nPatriciachester, LA 61429',
    'text': 'Note detail force tonight threat argue. Success catch several out appear.\nSource miss blue heart their. Sit nearly American federal must rule.',
    'email': 'mbrown@example.com',
    'phone_number': '(433)781-1186',
    'json': {
    'name': 'Richard Daniels',
    'address': '675 Amy Neck\nLake Taylor, KY 52541',
},
    'key66959': 'value34959',
    'key62609': 'value28348',
    'key54941': 'value80649',
},
    {
    'id': 17527486969097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Miguel Johnson',
    'address': '1058 Pamela Parkway\nEast Michael, AS 89168',
    'text': 'Measure able style close too sister ever. Factor resource continue admit.\nMinute sure weight however glass section successful late. Only throw natural old. Bill ball room way lose tough Democrat.',
    'email': 'herreramatthew@example.com',
    'phone_number': '001-312-559-9597',
    'json': {
    'name': 'Amy Bennett',
    'address': '45434 Summers Ranch Suite 524\nJohnsonfort, FL 36869',
},
    'key21047': 'value20937',
    'key30572': 'value36793',
    'key35968': 'value85844',
    'key38933': 'value98886',
    'key11070': 'value28088',
    'key6918': 'value3716',
    'key89953': 'value91571',
    'key99339': 'value71807',
    'key88814': 'value13201',
},
    {
    'id': 17527486969108,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jesse Sheppard',
    'address': '94382 Richard Locks Apt. 015\nLake Rebeccaside, IN 75685',
    'text': 'Most television capital ground. Camera fine modern space sister soon hospital. Store effect movie.',
    'email': 'amanda85@example.org',
    'phone_number': '+1-453-348-6186x72881',
    'json': {
    'name': 'Robert Russell',
    'address': '9219 Acosta Spring Apt. 576\nNorth Robertbury, ME 60824',
},
    'key11540': 'value29026',
    'key37963': 'value42634',
    'key16843': 'value99432',
    'key45551': 'value76571',
    'key57474': 'value97602',
    'key55218': 'value3524',
    'key14411': 'value52924',
    'key20907': 'value6866',
    'key54111': 'value49422',
},
    {
    'id': 17527486969119,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Leah Blevins',
    'address': '199 Pacheco Forks Apt. 064\nTaylorside, ID 52170',
    'text': 'Hour run tax case turn. Road foot dog mouth. Beautiful race sing whose season much card.',
    'email': 'stephanieharris@example.net',
    'phone_number': '422-735-5997',
    'json': {
    'name': 'Jennifer Nelson',
    'address': '253 Laura Shores Apt. 932\nPort Arianashire, VA 19830',
},
    'key31051': 'value77014',
    'key31894': 'value26637',
},
    {
    'id': 17527486969130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Dustin Ramirez',
    'address': '69659 Cindy Ways\nNorth Jamesside, AL 58813',
    'text': 'Charge catch environment how few structure hold. Scientist policy bring machine same light.',
    'email': 'markmartin@example.com',
    'phone_number': '(889)925-9809',
    'json': {
    'name': 'Eric Richardson',
    'address': '893 Judy Lights Apt. 280\nNew Jennifer, WY 70067',
},
    'key87388': 'value84847',
    'key21225': 'value54353',
},
    {
    'id': 17527486969141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Brandy Roberts',
    'address': '17239 Clark Fields\nNew Cindymouth, CT 29951',
    'text': 'Cultural fast trade civil same. Later mouth able tell throw professional scientist world.',
    'email': 'kyle54@example.net',
    'phone_number': '427.608.8956x5728',
    'json': {
    'name': 'Kimberly Grant',
    'address': '215 Laura Hills Suite 168\nEast Sarah, VT 90420',
},
    'key52991': 'value44437',
    'key41469': 'value89031',
    'key78252': 'value29378',
    'key63723': 'value69535',
    'key49754': 'value3539',
    'key21312': 'value40710',
},
    {
    'id': 17527486969152,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michelle Vazquez',
    'address': 'Unit 9752 Box 8522\nDPO AP 48470',
    'text': 'Anyone fight when card authority air strong. Month deal onto when mission. Pattern industry many especially doctor.\nNo write court can find. Girl son expert government until world.',
    'email': 'jennifercampbell@example.net',
    'phone_number': '907-553-4161x9702',
    'json': {
    'name': 'Robin Perez',
    'address': '271 Madison Shoals\nAndrewbury, OR 50706',
},
    'key96097': 'value9245',
    'key35066': 'value90515',
    'key76538': 'value99252',
    'key64403': 'value12558',
    'key28302': 'value97659',
    'key49797': 'value72006',
},
    {
    'id': 17527486969161,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Sarah Kent',
    'address': '53239 Dixon Groves Apt. 556\nChungport, MP 40077',
    'text': 'Police various phone able. Political born relate someone glass.',
    'email': 'vlarsen@example.net',
    'phone_number': '001-618-669-9555x483',
    'json': {
    'name': 'Jaime Lopez',
    'address': '0324 Casey Vista\nNorth Ryan, SD 81057',
},
    'key34760': 'value79839',
    'key19195': 'value40149',
    'key89512': 'value7419',
    'key53221': 'value51023',
    'key20422': 'value78207',
    'key85164': 'value46178',
    'key65776': 'value12718',
    'key35547': 'value78946',
},
    {
    'id': 17527486969172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Anne White',
    'address': '33151 Sanchez Point\nKellybury, CT 87122',
    'text': 'The fight fight article special represent. Mind close position poor.\nWe kid it challenge way. Rock value less.',
    'email': 'lopezjennifer@example.net',
    'phone_number': '+1-302-253-2462',
    'json': {
    'name': 'Timothy Dickson',
    'address': 'Unit 3738 Box 4770\nDPO AA 41249',
},
    'key20379': 'value60528',
    'key82796': 'value26609',
    'key21253': 'value79752',
    'key4728': 'value94361',
    'key39996': 'value37686',
    'key14910': 'value46180',
    'key18591': 'value4727',
    'key64240': 'value6243',
},
    {
    'id': 17527486969181,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Marilyn Atkins',
    'address': 'PSC 6187, Box 0126\nAPO AE 09479',
    'text': 'Special single firm art arrive theory recognize. Test machine analysis. A listen season follow best.\nAlmost fear physical among everybody financial law. Stuff medical strategy center can.',
    'email': 'ymeyers@example.org',
    'phone_number': '778.524.6380x57327',
    'json': {
    'name': 'Brett Chandler',
    'address': '00768 Wright Overpass\nWest Jesus, MN 03882',
},
    'key32201': 'value55198',
    'key11663': 'value50364',
    'key43239': 'value54281',
    'key54038': 'value96116',
    'key3321': 'value39396',
    'key57493': 'value29522',
    'key30742': 'value16887',
    'key76501': 'value37226',
    'key42699': 'value28498',
},
    {
    'id': 17527486969190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'William Hood',
    'address': '6892 Michelle Branch\nWest Sean, VI 02938',
    'text': 'Account responsibility owner nothing establish indeed response. Hear spring degree nearly recently improve.',
    'email': 'laustin@example.org',
    'phone_number': '621.548.7141',
    'json': {
    'name': 'April Jones',
    'address': '4646 Patrick Trail\nWest Laura, MT 11799',
},
    'key87735': 'value43038',
    'key58794': 'value92230',
    'key41836': 'value52810',
    'key35308': 'value98307',
    'key46380': 'value52307',
    'key89042': 'value68087',
    'key43585': 'value23756',
    'key97856': 'value67382',
    'key69074': 'value67973',
},
    {
    'id': 17527486969200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Lindsey Moody',
    'address': '2860 Stewart Estates Suite 130\nKimland, MS 25308',
    'text': 'Lay speak plant. Watch poor send simply. Low dark claim science air evidence send second. Follow sport base town affect.',
    'email': 'buchananmatthew@example.org',
    'phone_number': '001-872-288-3263x48802',
    'json': {
    'name': 'Morgan Brown',
    'address': 'Unit 7461 Box 6752\nDPO AE 35041',
},
    'key14723': 'value99644',
    'key67448': 'value26912',
    'key76138': 'value29933',
    'key51458': 'value22931',
    'key5047': 'value68976',
},
    {
    'id': 17527486969210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jorge Rodriguez',
    'address': '2679 Christina Plains Suite 558\nSmithmouth, WY 14748',
    'text': 'Still service instead security. We anything learn character.\nSite peace old sell floor news. Our either direction easy over through range.',
    'email': 'zespinoza@example.net',
    'phone_number': '480-871-1585',
    'json': {
    'name': 'Willie Johnson',
    'address': 'Unit 6763 Box 0434\nDPO AE 39794',
},
    'key74078': 'value34021',
    'key10205': 'value7713',
    'key33880': 'value3649',
    'key46130': 'value40406',
    'key27786': 'value86335',
},
    {
    'id': 17527486969219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Samuel Lopez',
    'address': '3370 Humphrey Branch Apt. 375\nEast Ericahaven, IA 45777',
    'text': 'Rise south girl seem. Section range why man thought camera design. Edge institution mother especially woman performance money.\nHere outside kid station hundred want maintain provide.',
    'email': 'ccraig@example.com',
    'phone_number': '410.695.3279x52468',
    'json': {
    'name': 'Denise Tanner',
    'address': '5251 Johnson Isle\nLake Carriebury, MT 54089',
},
    'key71663': 'value67024',
    'key38686': 'value71970',
    'key35958': 'value96515',
    'key60615': 'value95855',
    'key42381': 'value14061',
    'key46772': 'value76734',
},
    {
    'id': 17527486969230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Lance Cunningham',
    'address': '69365 Donald Manors Suite 706\nWest Phillip, AZ 90317',
    'text': 'Defense government cup true list. Question care everyone control. Success here focus page threat many sometimes.',
    'email': 'henryrobert@example.net',
    'phone_number': '+1-955-731-7003x756',
    'json': {
    'name': 'Courtney White',
    'address': '863 Leslie Harbor\nBlackwellfurt, HI 94234',
},
    'key21837': 'value16325',
    'key69193': 'value50747',
    'key10675': 'value77403',
    'key32762': 'value92878',
    'key28539': 'value34630',
    'key17491': 'value79287',
    'key2671': 'value59029',
    'key1537': 'value21588',
    'key81511': 'value18926',
    'key86734': 'value30341',
},
    {
    'id': 17527486969242,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Brian Griffin',
    'address': '198 King Way\nSouth Melanieburgh, AS 48029',
    'text': 'Eat especially large bar century. Ready culture too building thank professional time writer. Exactly audience yeah.\nCheck human charge rock center. Leg walk also remain option treat nearly.',
    'email': 'patellisa@example.org',
    'phone_number': '(359)468-7552x5487',
    'json': {
    'name': 'William Coleman',
    'address': '5705 Bailey Rest Suite 081\nAnnefort, ME 24386',
},
    'key41161': 'value16091',
    'key75944': 'value1201',
    'key43733': 'value24627',
    'key1626': 'value6623',
    'key84555': 'value61730',
    'key7736': 'value49138',
    'key12600': 'value43945',
    'key38125': 'value82332',
    'key43317': 'value13649',
},
    {
    'id': 17527486969254,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Stacy Hill',
    'address': '872 Allison Glen Suite 441\nJoshuamouth, OK 66300',
    'text': 'Growth finish box technology she. Responsibility staff we play way air join.\nEmployee return pick situation name late especially. Change indeed over chance.',
    'email': 'amanda06@example.org',
    'phone_number': '238.894.4370x3359',
    'json': {
    'name': 'Paul Wood',
    'address': '912 Pope Place\nNew Jasminehaven, MO 48440',
},
    'key63473': 'value3298',
    'key87472': 'value41978',
    'key703': 'value82966',
    'key49788': 'value76207',
    'key9869': 'value92601',
    'key74861': 'value4737',
    'key51680': 'value39555',
    'key87668': 'value13735',
    'key49583': 'value78807',
    'key41612': 'value36882',
},
    {
    'id': 17527486969264,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Rachel Williams',
    'address': '47147 Clayton Circles Suite 066\nJordanmouth, WI 92917',
    'text': 'Threat sport no day. Source trial require program physical.\nMyself teacher certainly perhaps. Ball tonight remember community authority defense give home. Debate market most these.',
    'email': 'yolanda86@example.org',
    'phone_number': '+1-754-221-8032x18763',
    'json': {
    'name': 'Susan Dickerson',
    'address': '92943 John Groves\nWattsstad, TX 88613',
},
    'key35856': 'value63083',
    'key51431': 'value74177',
    'key10510': 'value28864',
    'key66007': 'value6356',
    'key3586': 'value11184',
    'key62516': 'value41903',
    'key44731': 'value44840',
    'key53702': 'value58639',
    'key66638': 'value22009',
    'key81344': 'value93438',
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
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
    'RequestId': '22728f78-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_10_782678uznDzZfK',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752748705.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUidIn12341752748705Json()
    test.run_tests()
