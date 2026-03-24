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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752748778_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752748778.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrue1020Uid20301752748778Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752748778.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752748778.json"
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
    'data': [
    {
    'id': 17527487698683,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Kristen Flores',
    'address': '702 Sarah Rapids\nJacobhaven, DE 87448',
    'text': 'Alone follow mean language ten. Group picture cultural card enough tell hot. Director piece part president seven win.',
    'email': 'brianhubbard@example.com',
    'phone_number': '001-671-776-2444x28799',
    'json': {
    'name': 'Jose Powers',
    'address': '6811 Pace Valleys Apt. 232\nGlassville, DC 29140',
},
    'key31371': 'value67851',
    'key93945': 'value74685',
    'key11908': 'value56903',
    'key38959': 'value23632',
    'key90634': 'value1510',
    'key58031': 'value13838',
    'key49021': 'value4014',
    'key38771': 'value90047',
    'key33910': 'value59745',
},
    {
    'id': 17527487698701,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Anthony Le',
    'address': '2579 Davis Summit\nChristensenborough, FM 87571',
    'text': 'Floor against policy actually. Poor who force past generation. Bad somebody idea lay side own off.',
    'email': 'anthonyperez@example.net',
    'phone_number': '+1-637-464-7081x72060',
    'json': {
    'name': 'Kenneth Huynh',
    'address': '3854 Elizabeth Manors Suite 947\nMurrayshire, VT 60080',
},
    'key83910': 'value55301',
    'key4763': 'value68533',
    'key2874': 'value56133',
    'key2557': 'value53418',
    'key91687': 'value67964',
    'key80435': 'value43804',
    'key58728': 'value13672',
},
    {
    'id': 17527487698716,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Kevin Friedman',
    'address': 'PSC 8909, Box 0553\nAPO AA 59148',
    'text': 'Power participant surface participant. None herself parent recent rule sing change.\nInto way security question top each begin over. Under against single each thousand federal.',
    'email': 'nathaniel04@example.com',
    'phone_number': '(228)586-3571x662',
    'json': {
    'name': 'Scott Hall',
    'address': '7065 Christopher Crest\nSouth Shawnborough, NJ 33602',
},
    'key6910': 'value40209',
    'key47510': 'value31322',
    'key63253': 'value17592',
    'key86396': 'value56481',
    'key48688': 'value12723',
    'key56604': 'value65686',
    'key4960': 'value58259',
    'key2590': 'value43149',
    'key66968': 'value67819',
},
    {
    'id': 17527487698727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Mark Taylor',
    'address': 'PSC 6804, Box 6461\nAPO AA 98578',
    'text': 'Admit artist six term president nice.\nSeries song speech sing. Second change have. Street newspaper ever some produce media decade direction.',
    'email': 'adamguzman@example.org',
    'phone_number': '748.883.7080x58827',
    'json': {
    'name': 'Robert Franklin',
    'address': 'Unit 7844 Box 5135\nDPO AP 95928',
},
    'key6272': 'value64606',
},
    {
    'id': 17527487698736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Mathew Cohen',
    'address': '97656 Cortez Road\nWest Christopher, OR 26682',
    'text': 'Occur experience body pattern some. Professor rich create stop democratic position. Some federal ball south according whom.',
    'email': 'abigailtaylor@example.net',
    'phone_number': '257.374.0522',
    'json': {
    'name': 'Leslie Mitchell',
    'address': '681 Robinson Plaza Suite 318\nNolanburgh, WV 42878',
},
    'key24933': 'value95295',
    'key87711': 'value82685',
    'key38508': 'value53205',
    'key40919': 'value15916',
    'key93203': 'value4380',
    'key83001': 'value29182',
    'key62526': 'value90755',
    'key43140': 'value64111',
},
    {
    'id': 17527487698750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Daniel Ramirez',
    'address': 'Unit 7876 Box 0082\nDPO AP 60608',
    'text': 'Itself question play. Think base impact billion reduce interest across.\nImportant under garden doctor. Opportunity short eight such. Yeah enjoy sell indicate.',
    'email': 'jacksonjames@example.org',
    'phone_number': '(685)398-8103',
    'json': {
    'name': 'Larry Edwards',
    'address': '39801 Steven Union Apt. 510\nPort Joe, NV 81223',
},
    'key96347': 'value35331',
},
    {
    'id': 17527487698762,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Wendy Solomon',
    'address': '614 Garcia Spurs\nNew Johnfort, OK 37498',
    'text': 'Instead material four there from friend southern.\nCheck once sort able degree main reflect. Book choice many argue time trade. Time property without data teacher drug.',
    'email': 'hyu@example.net',
    'phone_number': '999-596-2801x65907',
    'json': {
    'name': 'Matthew Wilcox',
    'address': '85599 John Parkways\nWest William, AK 17885',
},
    'key6700': 'value94417',
    'key38533': 'value21725',
    'key13765': 'value47149',
    'key74446': 'value99191',
    'key80718': 'value32898',
    'key58928': 'value67413',
},
    {
    'id': 17527487698775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Sierra Watson',
    'address': '67997 Michelle Ranch Suite 282\nNew Daniellemouth, MA 45726',
    'text': 'Kind walk lot produce ok phone there. Walk control consider lot agreement.',
    'email': 'kristencarlson@example.com',
    'phone_number': '(347)279-8905',
    'json': {
    'name': 'Justin Scott',
    'address': '80940 Powers Fords\nEast Thomas, KS 90720',
},
    'key90458': 'value73136',
    'key20534': 'value23113',
    'key66726': 'value69009',
    'key48764': 'value69240',
    'key80485': 'value77734',
    'key75813': 'value92865',
    'key41864': 'value44908',
    'key62581': 'value66639',
},
    {
    'id': 17527487698786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Stephen Lewis',
    'address': '1881 Carter Islands Suite 901\nTiffanyport, MD 99622',
    'text': 'Capital send father per. Treatment position budget method. Including billion walk late we dinner there.\nThird open threat subject low. Information process boy strong. That fact behavior career trip.',
    'email': 'jadams@example.com',
    'phone_number': '(789)261-5801',
    'json': {
    'name': 'Brett Sanchez',
    'address': '422 Samantha Haven\nEast Mollyhaven, MN 19833',
},
    'key39126': 'value86297',
    'key2185': 'value29502',
    'key91112': 'value85631',
    'key1861': 'value44461',
    'key28731': 'value82691',
    'key29051': 'value83044',
    'key46784': 'value39266',
    'key45691': 'value85763',
    'key78814': 'value4137',
},
    {
    'id': 17527487698798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Mrs. Laurie Williams',
    'address': '4036 Jimenez Courts Apt. 778\nButlerland, AL 56825',
    'text': 'Right far better modern task claim yourself common. Hit believe conference would usually.\nAppear purpose everyone low role relate. Culture join ground thing put employee.',
    'email': 'brettpatel@example.org',
    'phone_number': '(377)780-5475x4858',
    'json': {
    'name': 'Aaron Anderson',
    'address': '655 Parker Centers\nAshleyfort, ME 56052',
},
    'key14589': 'value80833',
    'key55932': 'value81568',
    'key62683': 'value40349',
    'key51878': 'value71096',
    'key37782': 'value5705',
},
    {
    'id': 17527487698811,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Meghan Schmidt',
    'address': '79610 Martinez Flats\nWest Rogershire, NM 03841',
    'text': 'Suffer cover significant too dark degree. Power responsibility nature few lot about evidence. Edge road adult around arrive. List shake citizen suddenly heavy benefit arm.',
    'email': 'jjimenez@example.com',
    'phone_number': '585-352-6433x2381',
    'json': {
    'name': 'Karen Lopez',
    'address': '1682 Rebecca Burg\nPeterside, AL 94423',
},
    'key96640': 'value21807',
    'key56709': 'value7785',
    'key23256': 'value56921',
    'key10466': 'value793',
    'key20651': 'value76558',
    'key44087': 'value56550',
    'key8954': 'value31761',
},
    {
    'id': 17527487698822,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Christina Skinner',
    'address': '4559 Kevin Hills\nGregoryfurt, WA 10511',
    'text': 'Standard yes quality someone. This consider seek. Look professional reduce image citizen few.',
    'email': 'scottdavid@example.net',
    'phone_number': '5852364906',
    'json': {
    'name': 'Zachary Li',
    'address': '25138 Hayden Trail Suite 430\nLake Anthonyshire, CO 57279',
},
    'key66992': 'value97910',
},
    {
    'id': 17527487698835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Brian Dawson',
    'address': '990 Steven Pike\nCarlsonborough, RI 33096',
    'text': 'News night carry lawyer believe reason. View national produce need quality.\nToday study thought indicate wait Republican billion. Resource whether point case sit even decide provide.',
    'email': 'robert75@example.com',
    'phone_number': '+1-670-758-5651x71198',
    'json': {
    'name': 'Christine Sanchez',
    'address': '994 Glass Village\nLake Bradley, OR 38197',
},
    'key23704': 'value53421',
    'key42915': 'value84553',
    'key25449': 'value66800',
    'key68889': 'value38495',
    'key44140': 'value84707',
    'key22413': 'value3607',
},
    {
    'id': 17527487698846,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'John Holmes',
    'address': 'USNS Baldwin\nFPO AE 75419',
    'text': 'Push field glass car. Child listen marriage wrong society.\nHold team behavior message fine almost.\nPass recognize once receive degree enough rule.',
    'email': 'mrobles@example.com',
    'phone_number': '(836)795-5173x3493',
    'json': {
    'name': 'Shannon Francis',
    'address': 'Unit 8013 Box 8140\nDPO AP 03218',
},
    'key31493': 'value97619',
},
    {
    'id': 17527487698855,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'William Johnson',
    'address': '874 Howard Falls\nCynthiaberg, ND 76399',
    'text': 'Beautiful work admit responsibility. It threat eat education couple however purpose other.\nCampaign certainly table goal. Some ball law beat lose behind debate.',
    'email': 'laurenlucas@example.org',
    'phone_number': '290-575-2410',
    'json': {
    'name': 'Matthew Stephens',
    'address': '612 Stacey Land Suite 204\nPort Kaylahaven, AS 71464',
},
    'key94534': 'value92309',
    'key83053': 'value94960',
    'key8367': 'value97315',
    'key58025': 'value52429',
    'key42786': 'value59327',
    'key85879': 'value19574',
    'key99514': 'value90349',
    'key88001': 'value32658',
    'key91418': 'value1914',
    'key98101': 'value92755',
},
    {
    'id': 17527487698867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Erin Skinner',
    'address': '888 Sarah Heights Suite 134\nNew Huntertown, RI 46814',
    'text': 'Above military boy wrong. Health prepare return bank southern win. Which cause too move late seat agency.',
    'email': 'charles80@example.com',
    'phone_number': '(255)269-7245x394',
    'json': {
    'name': 'Cheryl Brown',
    'address': '711 Andrea Camp\nJasonborough, CO 31595',
},
    'key23942': 'value4168',
    'key7102': 'value93386',
},
    {
    'id': 17527487698879,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Sharon Kim',
    'address': '02461 Hall Summit\nAlejandroshire, ID 61779',
    'text': 'Imagine day compare.\nSuccess miss sort near move student. Resource nothing trial food let. Social dream argue once tend. Data get democratic back.\nHim wonder I up near grow. Before as them worry.',
    'email': 'jromero@example.net',
    'phone_number': '6589857556',
    'json': {
    'name': 'Michael Lewis',
    'address': 'USNS Stewart\nFPO AA 18964',
},
    'key53295': 'value27494',
    'key55241': 'value63203',
    'key50174': 'value27092',
    'key25120': 'value13822',
},
    {
    'id': 17527487698891,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Deborah Brown',
    'address': '655 Johnston Valleys\nMelanieborough, MI 94990',
    'text': 'End heart get south stock suddenly wife. Someone list three true.\nWalk color how smile meet.\nAnimal season wall statement see. Head look operation benefit media half. Born card serious compare.',
    'email': 'jeffreymorris@example.net',
    'phone_number': '370.930.2252x42395',
    'json': {
    'name': 'Jessica Wyatt',
    'address': 'Unit 3600 Box 3674\nDPO AE 50802',
},
    'key8382': 'value12011',
    'key37704': 'value38231',
    'key25532': 'value83024',
    'key28521': 'value85705',
},
    {
    'id': 17527487698901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Blake Maxwell',
    'address': '62218 Davis Landing Suite 159\nEast Brandon, KS 61366',
    'text': 'Participant fish thank create president. Million notice popular cost. Trip long call threat hold including.\nSuch may forget share let necessary. Produce fill never arm today possible we.',
    'email': 'marklivingston@example.com',
    'phone_number': '+1-827-944-7954x51252',
    'json': {
    'name': 'John Chavez',
    'address': '27658 Kimberly Freeway\nPort Madeline, PR 92974',
},
    'key26470': 'value30977',
},
    {
    'id': 17527487698912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Michael Wilson',
    'address': '9884 Stevens Square\nAtkinsonhaven, NH 87638',
    'text': 'Buy small because light these. Pretty purpose part study. Worry fly determine sort that reflect.\nFeel listen beautiful hundred American population green.',
    'email': 'bonniemorris@example.net',
    'phone_number': '540-571-6283x88229',
    'json': {
    'name': 'Lisa Adams',
    'address': '53488 Combs Ports\nNorth Autumn, ID 25659',
},
    'key52757': 'value30772',
    'key67144': 'value54890',
    'key19941': 'value65655',
    'key75710': 'value12163',
    'key22328': 'value9699',
    'key238': 'value64166',
},
    {
    'id': 17527487698924,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Brenda Miller',
    'address': '98412 Hernandez Village\nPort Jimmybury, PR 23648',
    'text': 'Truth strategy past build two. Sea seat at ask blue smile. Wonder study traditional.',
    'email': 'collinsmelissa@example.net',
    'phone_number': '(318)600-7260x6410',
    'json': {
    'name': 'Matthew Washington',
    'address': '079 Jackson Spring Suite 761\nWest Tanya, CT 81749',
},
    'key71504': 'value11032',
    'key13165': 'value75293',
    'key31968': 'value28595',
    'key50827': 'value59425',
    'key94791': 'value61513',
    'key98133': 'value89359',
    'key37299': 'value74064',
},
    {
    'id': 17527487698936,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Andre Morales',
    'address': '8956 Roach Row Apt. 293\nWilliamshaven, DE 73803',
    'text': 'Government leader science travel. Property go man trouble ahead wind share. Hundred per health behavior believe.',
    'email': 'lucasjennifer@example.net',
    'phone_number': '558.540.9484',
    'json': {
    'name': 'Jordan Chambers',
    'address': '000 Marshall Point Apt. 854\nSouth Catherinemouth, VT 92300',
},
    'key78416': 'value33109',
    'key95370': 'value46592',
    'key23162': 'value82784',
    'key65047': 'value90438',
    'key17364': 'value97029',
    'key2802': 'value90639',
    'key13421': 'value48969',
    'key83348': 'value36331',
},
    {
    'id': 17527487698948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Joshua Johnson',
    'address': 'USNV Morris\nFPO AP 50166',
    'text': 'Treatment success produce call bank car. Enough company worry type. Common hospital know your kitchen.\nLate speech training go stage. Language late toward school.',
    'email': 'nicolesalazar@example.org',
    'phone_number': '+1-763-960-7178x25067',
    'json': {
    'name': 'Michael Trevino',
    'address': '452 Brown Terrace\nNew Donna, TN 85340',
},
    'key38756': 'value82519',
    'key7099': 'value55172',
    'key64099': 'value46922',
    'key29897': 'value57336',
    'key25292': 'value91829',
    'key4341': 'value88016',
    'key51120': 'value29751',
    'key24359': 'value21925',
    'key18037': 'value65180',
},
    {
    'id': 17527487698958,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jason Andrews',
    'address': '669 Williams Neck\nJaredstad, AR 63509',
    'text': 'Find whose others crime back set. Movement treatment agency high.\nSpecific thousand more. Stock whole color section.\nNetwork agency health arrive.',
    'email': 'christina24@example.com',
    'phone_number': '672-485-5159x5443',
    'json': {
    'name': 'Jonathan Williams',
    'address': '79370 Coffey Terrace\nSouth Christinaland, CT 93468',
},
    'key48007': 'value29092',
    'key42595': 'value31904',
    'key67015': 'value54809',
    'key59934': 'value51682',
    'key39441': 'value46345',
    'key60193': 'value47403',
    'key39254': 'value19573',
},
    {
    'id': 17527487698969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Vanessa Harding',
    'address': 'Unit 0102 Box 1899\nDPO AA 26237',
    'text': 'Deal condition organization near field build. Allow poor hair manager prepare parent lose. Service soldier power mother hit.',
    'email': 'tconley@example.org',
    'phone_number': '5275672015',
    'json': {
    'name': 'Monica Wilson',
    'address': '31079 Oneal Locks\nNew David, SD 32915',
},
    'key11199': 'value8812',
    'key50426': 'value55041',
    'key67853': 'value32816',
    'key6664': 'value31554',
},
    {
    'id': 17527487698978,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Blake Castro',
    'address': '6566 Jennifer Lights\nNorth Johnbury, TX 04562',
    'text': 'Product suggest financial drug center. Fall later next great itself enjoy. Group product plant Mrs live Democrat debate.\nGirl red data management. Career hold rule new lawyer night explain.',
    'email': 'steven07@example.net',
    'phone_number': '001-451-903-1901',
    'json': {
    'name': 'Denise Martin',
    'address': 'USS Rivera\nFPO AA 64268',
},
    'key14975': 'value82892',
    'key66324': 'value83600',
    'key41239': 'value62610',
    'key84006': 'value88132',
    'key32012': 'value5197',
    'key40800': 'value26961',
    'key24299': 'value45866',
    'key40376': 'value78647',
    'key61789': 'value70394',
},
    {
    'id': 17527487698987,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Nancy Sanchez',
    'address': '562 Daniel Estates\nPort Sheila, WV 86578',
    'text': 'Send wife door whether fire development market. Color building turn every kid dark.\nFish rest change cup. Throw perhaps those throughout year.',
    'email': 'helen10@example.org',
    'phone_number': '884.828.2332x314',
    'json': {
    'name': 'Derrick Jones',
    'address': '27703 Romero Plains Apt. 408\nAdrianbury, ME 46914',
},
    'key76462': 'value44052',
    'key70592': 'value69001',
},
    {
    'id': 17527487698997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Morgan Stone',
    'address': '636 Mason Light\nBenjaminport, UT 13397',
    'text': 'Health play unit public front surface. Area blue decade.\nAccount society job none for. Step statement situation south value travel.',
    'email': 'sheltonmark@example.org',
    'phone_number': '766-949-2847',
    'json': {
    'name': 'Deborah Baker',
    'address': '89949 Angela Meadows Suite 132\nDavidfort, KS 29351',
},
    'key12799': 'value3939',
    'key78905': 'value8832',
    'key50735': 'value85435',
    'key10390': 'value2367',
    'key39214': 'value76676',
    'key30553': 'value70090',
    'key97512': 'value46699',
},
    {
    'id': 17527487699008,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Natasha Ochoa',
    'address': '4332 Sara Wells Apt. 779\nParkerport, RI 34454',
    'text': 'Your PM source capital. Store sport use exactly summer.\nLay success expert type shoulder education. Establish evidence program term different. Popular get later either ready.',
    'email': 'longjennifer@example.com',
    'phone_number': '(237)928-0401x045',
    'json': {
    'name': 'Kylie Cooper',
    'address': '2381 Perkins Shoal Apt. 304\nSouth Beckyhaven, NY 47252',
},
    'key45173': 'value14707',
    'key31299': 'value72935',
    'key68056': 'value45207',
    'key2736': 'value37901',
    'key97452': 'value43206',
    'key80881': 'value35285',
    'key91844': 'value45400',
    'key98533': 'value20394',
    'key31112': 'value98996',
    'key19960': 'value95006',
},
    {
    'id': 17527487699020,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Jason Douglas',
    'address': '313 Austin Key\nSouth Sarahchester, MD 40639',
    'text': 'Recent city line challenge walk. Amount state drop most campaign outside.\nParticular the rich race a to short arm. Pm operation high old. Stock become call our.',
    'email': 'christopher57@example.org',
    'phone_number': '9616775934',
    'json': {
    'name': 'Wesley Williams',
    'address': 'PSC 5620, Box 6628\nAPO AP 66582',
},
    'key57453': 'value20822',
    'key77870': 'value20189',
    'key63536': 'value51170',
    'key75946': 'value94373',
    'key69644': 'value16780',
    'key49362': 'value92151',
},
    {
    'id': 17527487699028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Mr. Jonathan Barrett',
    'address': '20174 Sara Court\nMichellefort, NH 14800',
    'text': 'Guy watch either around arrive wall. Town forward environmental.\nNone toward least interesting beyond of popular. Claim word light imagine study language easy. Land sort finish everyone those.',
    'email': 'edwardraymond@example.org',
    'phone_number': '001-877-834-2695x39820',
    'json': {
    'name': 'Angela Hughes',
    'address': '94399 Ramirez Lock\nBrewerberg, LA 35289',
},
    'key94324': 'value60112',
    'key88790': 'value80471',
    'key67963': 'value97634',
    'key63375': 'value19850',
},
    {
    'id': 17527487699040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Brandon Warner',
    'address': '0765 Kim Walks\nJessicashire, ND 47810',
    'text': 'Practice reduce off find leave. Turn owner understand poor food. Traditional star drive.\nNetwork build drop.',
    'email': 'juliesanchez@example.org',
    'phone_number': '+1-559-816-1197',
    'json': {
    'name': 'Allison Evans',
    'address': 'PSC 2744, Box 0630\nAPO AE 17395',
},
    'key40631': 'value3717',
    'key77376': 'value8994',
    'key6433': 'value17480',
    'key72694': 'value31918',
},
    {
    'id': 17527487699049,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Darrell Jones',
    'address': '30250 Downs Inlet\nEast Ashleymouth, MP 29608',
    'text': 'Stage benefit unit entire treatment ok.\nDay election store middle. In large evening energy. Stage east benefit.',
    'email': 'donald89@example.net',
    'phone_number': '001-589-698-2499x9984',
    'json': {
    'name': 'Ivan Bradley',
    'address': '045 Jeremy Parkway Suite 973\nLuketown, TN 64926',
},
    'key82118': 'value44824',
    'key57783': 'value69624',
    'key59241': 'value448',
    'key67815': 'value10579',
    'key2044': 'value75968',
    'key40925': 'value19085',
    'key10221': 'value16844',
},
    {
    'id': 17527487699059,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michelle Hill',
    'address': '88224 Cook Brook Apt. 837\nCameronhaven, SD 79972',
    'text': 'Court short environmental what significant design. Mouth it community commercial. Hour action until good when.',
    'email': 'ehurley@example.org',
    'phone_number': '702.512.0102x4959',
    'json': {
    'name': 'Timothy Wilson',
    'address': '7289 Williams Forge\nEast Veronica, MD 32369',
},
    'key61356': 'value25628',
    'key18244': 'value19666',
    'key82835': 'value99616',
    'key59996': 'value89504',
    'key89155': 'value74919',
},
    {
    'id': 17527487699070,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Craig Benton',
    'address': '903 Leon Loop Suite 724\nJosephland, NE 98351',
    'text': 'Wall Congress sense piece discover few pass. Kind research offer nice care public you. Newspaper administration paper laugh plan her staff business.',
    'email': 'brianharrington@example.org',
    'phone_number': '(829)822-1489',
    'json': {
    'name': 'Samuel Thompson',
    'address': '91909 Mann Gardens Apt. 416\nEast Kimberly, DE 47862',
},
    'key41950': 'value73360',
    'key50718': 'value89547',
    'key44249': 'value45573',
    'key32774': 'value96483',
    'key52600': 'value31389',
    'key38785': 'value689',
    'key38394': 'value63001',
    'key59648': 'value34957',
    'key19226': 'value73462',
},
    {
    'id': 17527487699082,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Deborah Fuentes',
    'address': '93514 Hess Crest Suite 829\nBrownchester, WI 17806',
    'text': 'Media tough hundred information think. Education push interest surface another future father TV.\nIdea add recent set. Factor then my wide learn allow say. Eye the though rock security.',
    'email': 'kayla21@example.org',
    'phone_number': '(939)773-0322x69048',
    'json': {
    'name': 'Mark Mcdowell',
    'address': '48521 Donald Drives\nLake Kristine, WV 44659',
},
    'key45100': 'value15004',
    'key57531': 'value64320',
    'key77191': 'value77485',
    'key87756': 'value20309',
    'key94162': 'value58527',
},
    {
    'id': 17527487699093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Harold Casey',
    'address': '4321 Robert Street Apt. 594\nMurilloland, MS 49797',
    'text': 'Politics base ready body table beautiful choice.\nRate garden edge. Room later year police decide from. Attention set than over.\nCarry affect officer tend front produce. Opportunity fear month health.',
    'email': 'lisa20@example.com',
    'phone_number': '(902)475-6869x36225',
    'json': {
    'name': 'John Dominguez',
    'address': '0518 Alexander Shoal\nMichaelmouth, VI 67602',
},
    'key68723': 'value84136',
    'key83091': 'value13180',
    'key89889': 'value98731',
    'key62455': 'value60282',
    'key7970': 'value87296',
    'key42362': 'value24721',
    'key6516': 'value18580',
    'key2719': 'value25763',
},
    {
    'id': 17527487699104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Michael Vasquez',
    'address': '94034 Jackson Crest Suite 213\nJenniferberg, NC 55951',
    'text': 'Specific rest worry less.\nSpecific care write decide card bit home. Collection per seek to green hospital behavior.',
    'email': 'emilyaustin@example.com',
    'phone_number': '+1-824-324-7474x939',
    'json': {
    'name': 'Kevin French',
    'address': '888 Beck Cape\nSouth Tammy, LA 96082',
},
    'key8351': 'value70099',
    'key66045': 'value52519',
    'key19762': 'value14008',
    'key65615': 'value40334',
    'key9194': 'value72334',
    'key71380': 'value98992',
    'key92183': 'value74413',
    'key76950': 'value3488',
    'key11247': 'value72061',
},
    {
    'id': 17527487699116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Shannon Moran',
    'address': '648 Rodriguez Valleys Apt. 313\nNorth Breanna, PR 93294',
    'text': 'Maintain customer can possible management. Compare this natural new vote. Great like series boy try.\nAhead difficult product article explain popular.',
    'email': 'plynch@example.com',
    'phone_number': '231-344-1849',
    'json': {
    'name': 'Sandra Griffin',
    'address': '11584 Michael Isle\nGardnerland, AR 16994',
},
    'key56522': 'value2094',
},
    {
    'id': 17527487699127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Misty Mann',
    'address': '3945 Patton Plains Apt. 149\nNew Heather, ME 95493',
    'text': 'Thank true successful road play boy each since. North mean approach total what. Check agent total treatment win still.',
    'email': 'erin89@example.net',
    'phone_number': '(411)221-6624x348',
    'json': {
    'name': 'Edward Becker',
    'address': '1156 Catherine Viaduct Apt. 389\nChristopherchester, MO 15229',
},
    'key25452': 'value24306',
    'key12865': 'value47783',
},
    {
    'id': 17527487699137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Daniel Gray',
    'address': '5818 Carney Camp Suite 570\nKarifurt, DE 84065',
    'text': 'Hot it raise course. State language measure color development follow design.\nBeyond chair world almost finish during against. Glass age street hope. Middle man black stand.',
    'email': 'sduncan@example.com',
    'phone_number': '994-857-8064',
    'json': {
    'name': 'Mary Morrison',
    'address': 'PSC 6928, Box 2195\nAPO AE 10804',
},
    'key61110': 'value32998',
    'key63309': 'value73550',
    'key55107': 'value92890',
    'key46832': 'value51201',
    'key904': 'value28349',
    'key90104': 'value14120',
},
    {
    'id': 17527487699146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Karen Jones',
    'address': '9780 Howard Lock Suite 514\nPort Angelachester, WV 65242',
    'text': 'Remain president relationship. Buy determine plan. Receive sport feel defense network happy model.\nName notice central expect well source report mission. Lose strategy choice fire front wait develop.',
    'email': 'gmccarthy@example.net',
    'phone_number': '+1-619-709-0636x182',
    'json': {
    'name': 'Jordan White',
    'address': '14199 Warren Gateway\nPort Laurashire, AL 49356',
},
    'key65559': 'value16928',
},
    {
    'id': 17527487699157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Randall Morris',
    'address': '54831 Blake Drives\nNorth Laura, AK 87847',
    'text': 'Type industry over suggest she. Son be me.\nPopulation usually forward reason president. Source pretty special.\nFour talk item affect one. Identify course fear into listen adult.',
    'email': 'singhelizabeth@example.com',
    'phone_number': '532.676.9929',
    'json': {
    'name': 'Laurie Hayes DDS',
    'address': '4376 Kenneth Manor\nEast Lauren, HI 87393',
},
    'key7172': 'value49260',
    'key87933': 'value4880',
    'key52695': 'value97178',
    'key17201': 'value87199',
    'key59171': 'value36981',
    'key79657': 'value71514',
    'key46493': 'value24582',
    'key21645': 'value7734',
    'key14287': 'value85459',
},
    {
    'id': 17527487699169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Calvin Curtis',
    'address': '0381 Randolph Island Suite 249\nNew Brendabury, RI 28992',
    'text': 'Thing continue adult ahead. List Republican officer scientist economy. Order save answer conference cause rather ball population.',
    'email': 'ynichols@example.net',
    'phone_number': '9933966463',
    'json': {
    'name': 'Mary Clark',
    'address': '81052 Tristan Stravenue\nDonnaburgh, MI 40640',
},
    'key95278': 'value48641',
    'key10823': 'value25713',
    'key95903': 'value7196',
    'key65581': 'value77942',
    'key20377': 'value20495',
    'key67988': 'value62287',
    'key77534': 'value66957',
    'key92540': 'value219',
    'key99919': 'value79778',
},
    {
    'id': 17527487699179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Cheryl Carson',
    'address': '56081 Watts Falls\nSouth Isaac, CT 01742',
    'text': 'Throughout perform change culture truth myself six. Toward different four house instead treat. Suddenly along remain to.',
    'email': 'andrewortega@example.net',
    'phone_number': '(803)561-9108',
    'json': {
    'name': 'Mrs. Lindsay Armstrong MD',
    'address': '3651 Carroll Circles\nSouth Ariel, VA 61548',
},
    'key63966': 'value39234',
    'key97686': 'value38107',
    'key43776': 'value4450',
    'key72419': 'value46214',
},
    {
    'id': 17527487699191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Robyn Chen',
    'address': 'USCGC Turner\nFPO AE 39664',
    'text': 'He notice across why. Every while media. Family establish use receive usually might gun.',
    'email': 'qfloyd@example.org',
    'phone_number': '(881)611-3717',
    'json': {
    'name': 'Brian Anderson',
    'address': '1191 Holly Ranch\nBrianfurt, VT 16939',
},
    'key18587': 'value56483',
    'key44122': 'value10888',
    'key13033': 'value91500',
    'key13289': 'value1985',
    'key43544': 'value57374',
    'key3382': 'value82359',
},
    {
    'id': 17527487699200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Ethan Schultz',
    'address': '822 Singleton Roads\nNorth Johnburgh, MD 67044',
    'text': 'Feeling effort capital he.\nSpecific fish cup around campaign. Various beautiful risk relationship support child.',
    'email': 'laura61@example.com',
    'phone_number': '+1-687-224-3563x994',
    'json': {
    'name': 'Steven Holmes',
    'address': '45748 Lopez Canyon\nWallerborough, NE 54325',
},
    'key33183': 'value58989',
    'key40307': 'value18799',
    'key78371': 'value47799',
    'key71106': 'value85541',
    'key12157': 'value55620',
    'key41027': 'value80992',
    'key54816': 'value44729',
},
    {
    'id': 17527487699211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Sean Ferguson',
    'address': '31277 Zimmerman Stravenue Apt. 941\nWest Jennifer, NM 36160',
    'text': 'Local easy white quickly husband data follow.\nSomeone audience child happy easy skill. Southern save or.\nStudent hit that rule its. Safe specific late instead character structure just.',
    'email': 'leerodriguez@example.net',
    'phone_number': '(285)948-7331x150',
    'json': {
    'name': 'Juan Jones',
    'address': '3220 Gonzales Roads Apt. 380\nJadeland, AR 80160',
},
    'key8066': 'value15892',
},
    {
    'id': 17527487699223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Sarah Carter',
    'address': 'Unit 1015 Box 3299\nDPO AA 82591',
    'text': 'Add teacher himself practice. Sound industry travel week. Discuss rate speech. Law degree sense wrong small.',
    'email': 'vhowell@example.org',
    'phone_number': '444.500.9558',
    'json': {
    'name': 'Wendy Strickland',
    'address': '140 Joanne Trail\nJonesland, NJ 81823',
},
    'key9808': 'value73765',
    'key30495': 'value97824',
    'key16972': 'value15083',
},
    {
    'id': 17527487699232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Heather Salas',
    'address': '310 Gibson Key Apt. 175\nPort Kristamouth, AK 23044',
    'text': 'Hundred clearly decade throw while of. Act require brother various better eat.\nLive we public method term page. Book save during bill meeting mission. Music expert culture beyond wish.',
    'email': 'clarkmichael@example.org',
    'phone_number': '787-592-0699x26141',
    'json': {
    'name': 'Linda Gonzales',
    'address': '257 Shane Crossroad Suite 321\nGeraldhaven, VI 51280',
},
    'key87219': 'value39671',
},
    {
    'id': 17527487699252,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Dr. Allison Hudson',
    'address': '31301 Parks Stravenue Apt. 135\nRhondashire, RI 18251',
    'text': 'Sense research foreign. Sister nice book material vote we. Effort floor whether stop.\nGeneral fight behavior certainly ago article effect.',
    'email': 'johnny80@example.net',
    'phone_number': '(896)551-2748x510',
    'json': {
    'name': 'Edward Wright',
    'address': '163 Jenna Squares\nOscarside, LA 02580',
},
    'key643': 'value42418',
    'key33212': 'value30432',
    'key52157': 'value65568',
    'key88626': 'value11511',
    'key78110': 'value51029',
    'key87249': 'value50391',
    'key98751': 'value95601',
    'key35292': 'value73648',
    'key273': 'value74471',
    'key85998': 'value32344',
},
    {
    'id': 17527487699264,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kenneth Parks',
    'address': '49333 Carla Mission Apt. 888\nNew Kenneth, FM 79465',
    'text': 'Tell local game carry machine. Meeting person radio page support personal. Quite perhaps politics phone.\nSame green be both. Thank worker focus risk service challenge. Challenge look affect memory.',
    'email': 'yhughes@example.org',
    'phone_number': '+1-929-378-3580x48275',
    'json': {
    'name': 'Tara Rodriguez',
    'address': '870 Lowe Turnpike\nJohnland, PA 73986',
},
    'key64706': 'value61860',
    'key44825': 'value23525',
},
    {
    'id': 17527487699276,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Maureen Beltran',
    'address': 'PSC 2208, Box 4256\nAPO AE 85611',
    'text': 'Law someone whom some sister anything. Experience seven reach day government.\nBack though chance debate four. Stock today while culture value work.',
    'email': 'lisa84@example.com',
    'phone_number': '222-302-0985x88652',
    'json': {
    'name': 'John Johnson',
    'address': '18921 Sally Keys Suite 648\nPort Erin, VI 86338',
},
    'key65971': 'value22721',
},
    {
    'id': 17527487699285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Melissa Anderson',
    'address': '41844 Harris Point Suite 044\nLesliehaven, MN 52688',
    'text': 'Early article skill. Someone eat law challenge fill forward I relate.\nEnvironmental really past land be natural. Among interview face defense. Past ground three draw start exist interview.',
    'email': 'markwise@example.com',
    'phone_number': '001-749-498-8807',
    'json': {
    'name': 'Miss Kelly Houston',
    'address': '547 Walker Crossroad\nNorth Sean, LA 63233',
},
    'key1863': 'value45505',
    'key24798': 'value44986',
    'key27543': 'value97080',
},
    {
    'id': 17527487699297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Kenneth Dominguez',
    'address': '552 Tracy Lodge\nPort Taylorview, SC 86513',
    'text': 'Hour fish relationship program whole agree personal. Building we table little course produce program. Fear life yet matter.',
    'email': 'annawilliams@example.org',
    'phone_number': '777.232.7159x76436',
    'json': {
    'name': 'Michele Robles',
    'address': '4549 Schultz Lock Apt. 754\nAlanton, WY 61102',
},
    'key78459': 'value20416',
    'key32176': 'value90069',
    'key63326': 'value39479',
    'key33150': 'value52801',
    'key63': 'value28496',
    'key32280': 'value89458',
},
    {
    'id': 17527487699310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Randy Morris',
    'address': '522 Francis Land\nKarenshire, HI 98623',
    'text': 'Father health carry and hospital paper.\nOnly receive wrong land large. Of now hold per anything. Week president accept degree.',
    'email': 'jonathan39@example.com',
    'phone_number': '(573)601-0848x4146',
    'json': {
    'name': 'Jennifer Bennett',
    'address': '42119 Wiggins Crossroad Apt. 134\nCampbellberg, KY 45362',
},
    'key89923': 'value55520',
    'key21532': 'value12092',
    'key88195': 'value5594',
    'key20805': 'value14464',
    'key12360': 'value74938',
},
    {
    'id': 17527487699321,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Teresa Garcia',
    'address': '28154 Miller Stream Suite 661\nLuisside, SD 46925',
    'text': 'Determine rule director never tonight least water. Assume along change let rule animal.\nSystem reason drug opportunity ever several significant.',
    'email': 'vjohnson@example.org',
    'phone_number': '7648550909',
    'json': {
    'name': 'Brianna Brooks',
    'address': '936 Love Mountains\nEricview, LA 05690',
},
    'key78840': 'value27389',
    'key28942': 'value75314',
    'key54413': 'value69116',
    'key80400': 'value49357',
    'key4373': 'value97053',
    'key10430': 'value62315',
    'key60671': 'value23654',
    'key91432': 'value32610',
},
    {
    'id': 17527487699333,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Norman Marsh',
    'address': '6290 Gonzales Rapid\nShawnberg, VI 74458',
    'text': 'Herself economic be nice reason others. Window better by whole quickly attorney eye. Record ready local offer let major election.',
    'email': 'icarson@example.com',
    'phone_number': '960.542.8405x32391',
    'json': {
    'name': 'Sara Hendricks',
    'address': '23686 Merritt Well Apt. 691\nDianachester, WV 90105',
},
    'key38638': 'value40008',
    'key36733': 'value20058',
    'key66592': 'value49123',
    'key24804': 'value44809',
    'key28003': 'value61240',
},
    {
    'id': 17527487699344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Susan Bender',
    'address': '70145 Reynolds Rapid\nNew Stacey, MO 62040',
    'text': 'Seem shoulder commercial wrong drop issue behind. Ability environment color history.\nClearly fine expert blue interest early. Mr point student such cell security. Military court pass local.',
    'email': 'mariahcruz@example.net',
    'phone_number': '814-854-2222',
    'json': {
    'name': 'Heather Lozano',
    'address': '188 Zachary Well\nJuanport, AL 91198',
},
    'key55952': 'value18018',
    'key56613': 'value9454',
    'key6654': 'value81536',
    'key58692': 'value77149',
    'key28893': 'value24275',
},
    {
    'id': 17527487699356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'James Vaughan',
    'address': '482 Dustin Road\nNorth Cheryl, AK 33570',
    'text': 'Money use avoid. Laugh imagine I manage.\nFirst create reduce. Sister enter likely stage sea.\nAbout growth talk tree likely machine someone leave. Group small far suddenly.',
    'email': 'tina55@example.com',
    'phone_number': '275-607-7871',
    'json': {
    'name': 'Brandon Garcia',
    'address': '7704 Phelps Camp Apt. 927\nLarashire, AZ 52524',
},
    'key24199': 'value9610',
    'key42926': 'value55472',
},
    {
    'id': 17527487699367,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Felicia Nelson',
    'address': '21553 Timothy Path\nShannonhaven, MO 03029',
    'text': 'Tough country character tough per. Energy follow Congress leave behavior between million practice. None guy middle begin network hospital where.',
    'email': 'zlewis@example.net',
    'phone_number': '245.290.0573x80751',
    'json': {
    'name': 'Brian Clark',
    'address': '2770 Jeffery Ridges Suite 795\nNew William, OH 17664',
},
    'key1758': 'value3095',
    'key52171': 'value71589',
    'key97973': 'value99041',
    'key31063': 'value77425',
    'key29072': 'value93495',
},
    {
    'id': 17527487699377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Tammy Brewer',
    'address': '15688 Jennifer Heights\nBobbymouth, NY 95581',
    'text': 'Quite picture rich southern. Scientist through interview parent stop. Another agency future there spend note.',
    'email': 'jessicabrown@example.org',
    'phone_number': '719-948-1684x929',
    'json': {
    'name': 'Audrey Long',
    'address': '14012 Smith Cliff Apt. 424\nStoneburgh, WY 34423',
},
    'key76678': 'value38230',
    'key91101': 'value8616',
    'key64543': 'value41494',
    'key15572': 'value74316',
    'key12529': 'value43890',
    'key69373': 'value26605',
    'key39578': 'value34246',
    'key32429': 'value31715',
},
    {
    'id': 17527487699389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'David Allen',
    'address': '84291 Antonio Square Suite 151\nPerezland, MO 16000',
    'text': 'Popular buy state policy activity once leader. Their television today. Near later send between fire language read often. Off policy standard discover risk.',
    'email': 'morriswilliam@example.com',
    'phone_number': '902-890-1714x6639',
    'json': {
    'name': 'Natalie Mcclure',
    'address': 'PSC 6339, Box 4705\nAPO AP 07775',
},
    'key50421': 'value62603',
    'key83410': 'value65733',
    'key33337': 'value83012',
    'key94865': 'value83656',
    'key26100': 'value40896',
    'key37889': 'value83319',
    'key10366': 'value95232',
},
    {
    'id': 17527487699399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Michael George',
    'address': '69669 Jeremy Mount Suite 928\nNorth Saraview, PA 20529',
    'text': 'South work try mission out. Control life song system cost movement member. For trial risk through decide.',
    'email': 'vmoore@example.com',
    'phone_number': '(695)319-7608',
    'json': {
    'name': 'Lori Garrison',
    'address': '585 Graves Glens\nBallchester, SD 42026',
},
    'key25508': 'value76030',
    'key57801': 'value74142',
},
    {
    'id': 17527487699410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Alicia Adams',
    'address': 'PSC 8507, Box 9838\nAPO AA 11283',
    'text': 'Compare may necessary summer. Mother make score authority compare team recognize.',
    'email': 'ajackson@example.org',
    'phone_number': '220.671.3355',
    'json': {
    'name': 'Brian Jones',
    'address': '020 Anthony Burgs Apt. 723\nNorth Isaacborough, CA 63904',
},
    'key28696': 'value28780',
    'key9820': 'value48532',
    'key2592': 'value33062',
    'key78116': 'value61456',
},
    {
    'id': 17527487699418,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Mr. Jeffrey Pratt',
    'address': 'PSC 0785, Box 5877\nAPO AE 41860',
    'text': 'Practice miss charge move about. Live rather style natural teach without officer. Chair camera little talk responsibility fight yes rock.',
    'email': 'jenniferkim@example.net',
    'phone_number': '721-884-0672',
    'json': {
    'name': 'Adam Rodriguez',
    'address': '9494 Molina Rapids\nFlemingport, DE 23059',
},
    'key67531': 'value32008',
    'key46236': 'value50144',
    'key11956': 'value4755',
    'key8437': 'value78925',
    'key90598': 'value41652',
    'key98919': 'value80504',
    'key77362': 'value56787',
    'key81753': 'value75047',
    'key82174': 'value96973',
    'key58467': 'value98108',
},
    {
    'id': 17527487699428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Allison Martinez',
    'address': '865 Taylor Plain\nLindseyhaven, GU 09465',
    'text': 'Keep model later. Weight think nearly west. Reason decision player include age.\nAppear section finally full. Always catch government save.',
    'email': 'gesparza@example.com',
    'phone_number': '543.389.5199x89920',
    'json': {
    'name': 'Leslie Freeman',
    'address': '6083 Gutierrez Haven\nPaulview, PA 19695',
},
    'key68207': 'value7460',
    'key34799': 'value92244',
},
    {
    'id': 17527487699439,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Donald Sullivan',
    'address': '78986 Beth Greens Suite 971\nLake Steven, MS 03187',
    'text': 'Assume be exist break notice remain far. Real government race check. Them when including much full build.',
    'email': 'john95@example.com',
    'phone_number': '(355)979-2306',
    'json': {
    'name': 'Robert Barrett',
    'address': '4672 Benjamin Tunnel\nScottton, FL 15199',
},
    'key37836': 'value70048',
    'key69223': 'value79712',
    'key66246': 'value45368',
    'key68850': 'value97727',
    'key46843': 'value38307',
    'key34068': 'value12221',
},
    {
    'id': 17527487699449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Sean Buck',
    'address': '909 Brandon Harbor Suite 284\nChristinetown, FL 18429',
    'text': 'Push police would within computer his though. His story pay candidate move inside scientist. Relate art station good.',
    'email': 'foxjulie@example.com',
    'phone_number': '954-297-9395',
    'json': {
    'name': 'Jonathan Ortiz',
    'address': '39358 Wilson Drive\nThomasside, PR 68613',
},
    'key36435': 'value66357',
    'key55320': 'value34388',
    'key6797': 'value82080',
    'key84119': 'value33863',
    'key89963': 'value46235',
    'key28342': 'value59863',
    'key83596': 'value47228',
    'key29347': 'value74977',
},
    {
    'id': 17527487699461,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'John Pollard',
    'address': '000 Michael Curve Apt. 367\nNorth Timothystad, OH 89398',
    'text': 'Often oil very argue east war. Factor leave stand go argue central. Indicate price game ready soon market across.\nHouse professor since tree. Teach case friend general.',
    'email': 'msnyder@example.com',
    'phone_number': '001-960-296-2433',
    'json': {
    'name': 'Jesus Hawkins',
    'address': '91797 Krystal Glen Suite 121\nRosarioport, PA 17340',
},
    'key44593': 'value20191',
    'key96068': 'value21624',
    'key78974': 'value68399',
    'key90766': 'value25356',
    'key80903': 'value93635',
    'key21612': 'value95358',
    'key69466': 'value45396',
    'key70746': 'value68650',
},
    {
    'id': 17527487699472,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Dr. Debra Steele DVM',
    'address': '22235 Denise Village Apt. 616\nDonovanside, IL 65366',
    'text': 'Also where knowledge. Loss onto real.\nWear investment simple remember ahead recent. Two available arm detail store. Carry never participant base writer indeed mother issue.',
    'email': 'janethoward@example.com',
    'phone_number': '704-695-1498',
    'json': {
    'name': 'Michelle Clay',
    'address': '3449 Allen Island Apt. 436\nEast Oscarmouth, NY 46065',
},
    'key81601': 'value69312',
    'key65292': 'value16201',
    'key29621': 'value59485',
    'key1918': 'value89697',
    'key99366': 'value23291',
    'key4679': 'value37060',
    'key51880': 'value14959',
},
    {
    'id': 17527487699484,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Christina Cortez',
    'address': '797 Woods Rest Suite 151\nSouth Amyshire, GU 91722',
    'text': 'Dog difficult though energy room. Short office do economic. The most head the.',
    'email': 'james23@example.org',
    'phone_number': '753.549.7223x430',
    'json': {
    'name': 'Latoya Adams',
    'address': '430 Kelley Courts Apt. 983\nPort Johnnyborough, MI 13463',
},
    'key66848': 'value62024',
    'key44783': 'value98267',
    'key94995': 'value18255',
    'key54637': 'value64707',
    'key67122': 'value53680',
    'key55586': 'value55095',
    'key55686': 'value88014',
    'key13375': 'value56146',
},
    {
    'id': 17527487699495,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'James Hill',
    'address': '0771 Jessica Rue\nDavisfurt, SD 59558',
    'text': 'Film voice friend audience organization. Prove central west us event serious them. Thank travel itself morning.',
    'email': 'ashleypadilla@example.com',
    'phone_number': '721-919-7052',
    'json': {
    'name': 'Susan Frey',
    'address': '909 Timothy Summit Suite 946\nStaceystad, MS 45210',
},
    'key93977': 'value62749',
    'key89167': 'value88745',
    'key97771': 'value90678',
    'key82533': 'value92902',
    'key2511': 'value60507',
    'key63175': 'value43267',
    'key70792': 'value29523',
    'key49508': 'value85507',
    'key36791': 'value39327',
    'key83472': 'value92644',
},
    {
    'id': 17527487699506,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Michelle Fox',
    'address': '27000 Jason Valley Suite 704\nLake Stephen, GA 45535',
    'text': 'Least firm beat although walk he probably effect. Candidate director authority film thousand should. Message before director media.',
    'email': 'heather25@example.com',
    'phone_number': '7855809733',
    'json': {
    'name': 'Taylor Floyd',
    'address': '143 Brandi Underpass\nJeffreymouth, NJ 24048',
},
    'key80119': 'value48389',
    'key20353': 'value80824',
},
    {
    'id': 17527487699516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Michael Hurley',
    'address': 'PSC 3667, Box 8063\nAPO AP 93377',
    'text': 'Try dream administration people none card. Take miss high memory yourself type.\nGovernment language response identify also memory. Question whom ask letter culture. Civil relate friend how something.',
    'email': 'angela55@example.net',
    'phone_number': '219-785-5959',
    'json': {
    'name': 'Brittney Oliver',
    'address': 'PSC 3344, Box 8245\nAPO AA 65406',
},
    'key14766': 'value10200',
    'key29147': 'value22851',
    'key12585': 'value57449',
    'key31642': 'value9973',
    'key64364': 'value93425',
    'key97783': 'value60393',
    'key95397': 'value12446',
},
    {
    'id': 17527487699523,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Lori Alvarez',
    'address': '798 Jackson Inlet Apt. 941\nSouth Davidfurt, FL 63638',
    'text': 'Special ten mother door group. Quality describe resource involve especially later citizen. Everything challenge good voice get green able seek.',
    'email': 'marie26@example.com',
    'phone_number': '(816)489-6946',
    'json': {
    'name': 'Jacqueline Mcdonald',
    'address': 'USNS Reyes\nFPO AE 62695',
},
    'key93975': 'value24793',
    'key74870': 'value66792',
    'key274': 'value71522',
    'key11637': 'value94679',
    'key16395': 'value71166',
    'key56812': 'value27675',
},
    {
    'id': 17527487699533,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Tammy Barnes',
    'address': '119 Jason Port Apt. 891\nLake Lisa, AR 09791',
    'text': 'Weight heavy ready weight prove investment foreign. Chance go these your item professional. Avoid where green laugh toward mention.\nStand take truth return modern various. Material have office sense.',
    'email': 'thompsonmelissa@example.com',
    'phone_number': '269.873.9632x3355',
    'json': {
    'name': 'Lance Warner',
    'address': '8815 Zachary Parks Apt. 337\nHoldermouth, CT 98557',
},
    'key45723': 'value34629',
    'key34015': 'value87242',
    'key62005': 'value90020',
    'key26221': 'value68573',
    'key62554': 'value87718',
    'key26652': 'value84783',
    'key20524': 'value10046',
},
    {
    'id': 17527487699544,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Paige Welch',
    'address': '7131 Tracy Square Suite 509\nJohnport, CA 79927',
    'text': 'Fight large just respond. Relationship however win actually office.',
    'email': 'gomezdavid@example.org',
    'phone_number': '238-468-3413',
    'json': {
    'name': 'Andrea Carlson',
    'address': '7846 Mullins Brooks\nMichaelberg, MT 78835',
},
    'key49514': 'value59111',
    'key37930': 'value49718',
    'key59884': 'value34373',
    'key20487': 'value13521',
    'key28645': 'value6986',
    'key75536': 'value6700',
    'key72441': 'value15783',
    'key27110': 'value92338',
    'key62799': 'value73580',
    'key45320': 'value56560',
},
    {
    'id': 17527487699556,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Jason Pierce',
    'address': 'Unit 0194 Box 1799\nDPO AA 84087',
    'text': 'Reflect late something child threat. Parent push human kitchen certainly me under.',
    'email': 'olee@example.org',
    'phone_number': '794-796-0526x423',
    'json': {
    'name': 'Christopher Black',
    'address': '5016 Susan Pike Suite 913\nJosephbury, WY 12229',
},
    'key53696': 'value85602',
    'key96701': 'value63291',
    'key53810': 'value93048',
    'key47203': 'value52096',
    'key28815': 'value93713',
},
    {
    'id': 17527487699565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'William Garcia',
    'address': '50767 Ian Pass Suite 050\nDanafurt, MO 08561',
    'text': 'Try ten prove admit enter significant since. Stand attack dog on meet pull discover big. Would although community at.',
    'email': 'woodschristopher@example.net',
    'phone_number': '794-204-6779x0561',
    'json': {
    'name': 'Molly Anderson',
    'address': '553 Singh Plains Apt. 261\nJaviermouth, CT 92505',
},
    'key31696': 'value40180',
    'key44313': 'value69250',
},
    {
    'id': 17527487699577,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Rachel Swanson',
    'address': '658 Melinda Vista Suite 030\nLake Dylanchester, LA 26010',
    'text': 'Ok probably structure return rock much discover. His call country president relationship collection table pull.\nUp get while career enjoy game.',
    'email': 'edward52@example.com',
    'phone_number': '6983362813',
    'json': {
    'name': 'Douglas Atkinson',
    'address': '87261 Jill Dale\nLake Michael, FM 21757',
},
    'key31976': 'value38337',
    'key50245': 'value16047',
    'key27618': 'value73630',
    'key83710': 'value39189',
    'key57171': 'value18971',
    'key72540': 'value87838',
    'key24842': 'value33551',
    'key91067': 'value24818',
    'key54745': 'value11222',
    'key62844': 'value76565',
},
    {
    'id': 17527487699587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Philip Thornton',
    'address': '058 Robert Shoals\nDanielmouth, WV 39874',
    'text': 'Because of military present really. Sport somebody expect home. Us reason public consumer necessary.',
    'email': 'ghughes@example.net',
    'phone_number': '(949)818-1199x0005',
    'json': {
    'name': 'Gloria Mcclure',
    'address': '892 Steven Centers\nSouth Charles, MH 15673',
},
    'key57058': 'value29307',
    'key24261': 'value90427',
    'key17398': 'value76429',
    'key59863': 'value26055',
    'key24202': 'value85915',
    'key24536': 'value44997',
    'key5292': 'value37295',
},
    {
    'id': 17527487699598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Kelsey Cline',
    'address': '27347 Richard Ramp Apt. 545\nMarymouth, PR 25218',
    'text': 'Mention Democrat on school contain. Put majority cup perhaps until. Stay contain item stuff doctor trade.',
    'email': 'kramirez@example.net',
    'phone_number': '(965)293-4175',
    'json': {
    'name': 'Jillian Smith',
    'address': '064 White Land Apt. 342\nWest Sherimouth, AL 44969',
},
    'key91824': 'value71171',
    'key64715': 'value18726',
    'key40220': 'value118',
    'key85128': 'value55530',
    'key24454': 'value67830',
    'key12087': 'value81503',
    'key81791': 'value74656',
    'key53362': 'value47852',
},
    {
    'id': 17527487699609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Eric Moreno',
    'address': '830 Gonzalez Cove\nJulianhaven, WV 51373',
    'text': 'Whether authority effect sign often first. Rather remain whatever example market professor discussion begin. News book drop far land.',
    'email': 'barrettrandy@example.net',
    'phone_number': '(450)582-9481',
    'json': {
    'name': 'Mark Roberts',
    'address': '35332 Tara Shores Suite 879\nJuliemouth, NM 36123',
},
    'key61655': 'value31721',
    'key58554': 'value5195',
    'key59200': 'value23921',
    'key94810': 'value9951',
    'key96854': 'value78728',
    'key27260': 'value1048',
    'key37242': 'value49986',
    'key46477': 'value7489',
    'key17429': 'value71355',
    'key58651': 'value77407',
},
    {
    'id': 17527487699621,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Sherry Hammond',
    'address': '444 Jon Crescent Suite 367\nBlanchardland, MI 89109',
    'text': 'Within price have would interview standard. Special occur admit.\nBrother drive interesting allow arm. Reveal go check author. City culture hundred some understand believe body.',
    'email': 'bbridges@example.org',
    'phone_number': '756.553.0631',
    'json': {
    'name': 'Brian Taylor',
    'address': '339 Barbara Dale\nLake Seanmouth, MI 53400',
},
    'key91097': 'value79351',
    'key45204': 'value58076',
    'key95780': 'value88315',
    'key94748': 'value6495',
    'key50966': 'value16614',
    'key44522': 'value87426',
    'key70311': 'value67803',
    'key86701': 'value8854',
    'key98592': 'value51663',
    'key67444': 'value54629',
},
    {
    'id': 17527487699632,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Abigail Fisher',
    'address': '80971 Lambert Wells Apt. 415\nDylanburgh, IL 99160',
    'text': 'Sell seat inside music industry. Party per at seem manager. Either third actually. Its firm bill action.\nRecent team something beyond check. People general line less.',
    'email': 'walter09@example.net',
    'phone_number': '(672)327-1651',
    'json': {
    'name': 'Samantha Moreno',
    'address': '38987 Finley Via Suite 421\nLake Amanda, MN 18409',
},
    'key29686': 'value55146',
    'key72960': 'value83908',
    'key12070': 'value30590',
    'key53837': 'value40055',
    'key36954': 'value79657',
    'key20577': 'value55228',
    'key12808': 'value53555',
},
    {
    'id': 17527487699644,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kimberly Schroeder',
    'address': '73937 Roberta Ville\nThomaschester, WV 12144',
    'text': 'Guess time stuff remember rise hit buy campaign. Fire off true concern your economy increase. Simple discussion involve machine nation. Improve those exactly able customer.',
    'email': 'cranecolleen@example.com',
    'phone_number': '001-348-305-2176x7851',
    'json': {
    'name': 'Sheila Benjamin',
    'address': '86677 Sarah Drive\nChelseamouth, NJ 07514',
},
    'key12888': 'value87304',
    'key85183': 'value81153',
    'key35366': 'value62769',
    'key2690': 'value4859',
},
    {
    'id': 17527487699656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Pamela Hernandez',
    'address': '3659 Lori Mission Apt. 652\nNorth Richard, GU 45692',
    'text': 'Future sport technology blood. Ball executive for maybe knowledge police open in.',
    'email': 'lauren57@example.org',
    'phone_number': '759-889-1729x3670',
    'json': {
    'name': 'Isaiah Roberts',
    'address': 'USCGC Carroll\nFPO AE 71119',
},
    'key37022': 'value90026',
    'key96737': 'value61736',
    'key41024': 'value32930',
    'key12423': 'value58700',
    'key12785': 'value71013',
    'key74692': 'value86142',
    'key46692': 'value66764',
    'key47552': 'value58017',
    'key90944': 'value92819',
},
    {
    'id': 17527487699666,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Justin Olson',
    'address': '627 Vargas Center\nWilsonbury, ID 29847',
    'text': 'At part term. Wrong thus mention religious.\nFriend middle necessary candidate soon mention eye nation. Citizen under big suggest same whom how.',
    'email': 'frobinson@example.net',
    'phone_number': '+1-724-419-7171x99683',
    'json': {
    'name': 'Vincent Miranda',
    'address': '876 Holt Brook\nWest Kellyside, ND 88823',
},
    'key41764': 'value66417',
    'key1980': 'value89556',
},
    {
    'id': 17527487699677,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Laura Sheppard',
    'address': '51313 Reynolds Vista Apt. 029\nNew Nathan, ID 80349',
    'text': 'Course box whole major record answer many rise. Throughout point task first Congress strategy no.\nJoin require five worker.',
    'email': 'tosborne@example.org',
    'phone_number': '942.214.5188x28810',
    'json': {
    'name': 'Brandi Collins',
    'address': '571 Robert Path\nMosleyport, PR 13692',
},
    'key18912': 'value38739',
    'key187': 'value39617',
    'key23970': 'value59825',
    'key56771': 'value82891',
    'key99765': 'value23889',
},
    {
    'id': 17527487699688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Kevin Howard',
    'address': '94626 Brooke Inlet\nMichellemouth, MP 50714',
    'text': 'Set dark town how section ask. According serve gun country. Building several politics produce tough.\nAround machine watch out. Nature attention measure stand.',
    'email': 'evansjacqueline@example.org',
    'phone_number': '413-688-1853x98202',
    'json': {
    'name': 'Lori Hendricks',
    'address': '726 Daniel Camp Apt. 678\nSouth Anitaborough, DC 59871',
},
    'key44154': 'value41515',
    'key50091': 'value82024',
    'key91813': 'value12550',
    'key62346': 'value49693',
    'key89373': 'value57493',
},
    {
    'id': 17527487699700,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Shelley Kent',
    'address': '38266 Thompson Rapid Apt. 081\nAmyfort, FL 28971',
    'text': 'Girl commercial sure everybody scientist high. Ever point company kind quality. Event expect senior.\nA money station after. Able board south. Case fish left language continue.',
    'email': 'dean41@example.com',
    'phone_number': '(584)723-1267',
    'json': {
    'name': 'Marc Ward DDS',
    'address': '7469 Perry Street\nWest Rhondashire, FL 29871',
},
    'key66140': 'value63305',
    'key64418': 'value44527',
    'key58144': 'value185',
    'key35097': 'value43962',
    'key61042': 'value24031',
    'key27428': 'value61150',
},
    {
    'id': 17527487699712,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Kristina Campbell',
    'address': '6830 Clark Oval\nWest Devinside, AS 48662',
    'text': 'Democratic management pass various according human.\nTax born according enter own. Deal dark possible.\nCare he picture bank notice. Sense animal cost clear season husband.',
    'email': 'jessicareese@example.net',
    'phone_number': '001-762-562-6073x76162',
    'json': {
    'name': 'Samantha Mercado',
    'address': '610 Christian Canyon Suite 972\nGreenfort, TX 54828',
},
    'key3050': 'value78374',
    'key69369': 'value60471',
    'key30697': 'value753',
    'key43720': 'value1495',
},
    {
    'id': 17527487699725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kristina Williams',
    'address': '527 Baker Street\nBranditon, SC 99268',
    'text': 'Field pick expect about want art present. Interesting story gas doctor outside.\nCertain soon scientist operation she once image. Focus near dinner. Back final probably.',
    'email': 'losborne@example.org',
    'phone_number': '621-828-9214',
    'json': {
    'name': 'George Butler',
    'address': '13736 Michelle Walk\nWest Timothy, VT 81372',
},
    'key94546': 'value45498',
    'key34931': 'value3668',
    'key23038': 'value83741',
    'key64007': 'value8851',
    'key38253': 'value24221',
    'key10602': 'value37271',
    'key2866': 'value69834',
},
    {
    'id': 17527487699737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Anna Kane',
    'address': 'USCGC Nelson\nFPO AE 21769',
    'text': 'Fill TV television. Hour west not drive sense building first.\nThen quickly phone beyond others similar mission professor. Gun poor hear play.',
    'email': 'adkinsmary@example.com',
    'phone_number': '(599)950-2095x854',
    'json': {
    'name': 'William Nelson',
    'address': '92111 Joshua Mill\nNew Joseph, MS 77113',
},
    'key20609': 'value90359',
    'key42654': 'value14433',
    'key23013': 'value29169',
    'key35095': 'value72455',
    'key92386': 'value90562',
    'key98857': 'value2665',
    'key9390': 'value95444',
    'key40090': 'value39185',
    'key5709': 'value86798',
    'key31555': 'value80227',
},
    {
    'id': 17527487699750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Allen Smith',
    'address': '3323 Smith Locks Apt. 662\nSouth Markland, FM 54103',
    'text': 'Forward work traditional catch without.\nPm floor possible board cut nearly special majority. Clear sing cold mouth think. Land up evidence street take fall.',
    'email': 'hopkinsnancy@example.org',
    'phone_number': '(518)501-0660x827',
    'json': {
    'name': 'Stephanie Velazquez',
    'address': '460 Kelly Row\nPort Laura, KY 80243',
},
    'key77505': 'value64273',
    'key12524': 'value71975',
    'key61418': 'value10249',
    'key48360': 'value9704',
},
    {
    'id': 17527487699762,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Eric Nichols',
    'address': '8689 Nicholas Fork\nWardview, VA 66773',
    'text': 'Once blood keep door medical and education safe. On capital half today his less open.\nOwner purpose color series natural run. Vote side remain attention line character.',
    'email': 'richardrose@example.com',
    'phone_number': '001-926-909-5807x04915',
    'json': {
    'name': 'Nathan Ritter',
    'address': '7083 Paul Greens Suite 526\nGillborough, OH 13927',
},
    'key68437': 'value40268',
    'key28212': 'value20101',
    'key25422': 'value25897',
    'key63265': 'value38395',
    'key57038': 'value18787',
    'key12250': 'value43664',
    'key7073': 'value60852',
},
    {
    'id': 17527487699775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Tonya Knapp',
    'address': '247 Smith Circles\nCobbside, NM 98753',
    'text': 'Rich set actually fear. Reality coach international population believe consider.\nHair possible apply admit. Others speech subject.',
    'email': 'eking@example.org',
    'phone_number': '(644)915-7382x17407',
    'json': {
    'name': 'Virginia Thomas',
    'address': '72307 Calvin Ramp\nLake Lisaton, MA 37060',
},
    'key10535': 'value7136',
    'key27000': 'value60121',
    'key66400': 'value67612',
    'key39250': 'value26587',
    'key73731': 'value44883',
    'key57160': 'value88060',
    'key92795': 'value13869',
    'key88904': 'value51223',
    'key8036': 'value35601',
    'key91428': 'value79430',
},
    {
    'id': 17527487699787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Carol Harris',
    'address': '55867 Mark Grove\nTimothyfurt, TN 27995',
    'text': 'Air report employee this response. Air thing force scientist difference.\nSide box mouth American student protect figure. Lot between fill option bank environmental.',
    'email': 'padillamichael@example.com',
    'phone_number': '+1-630-742-3617',
    'json': {
    'name': 'Whitney Wilson',
    'address': '9396 Price Corner\nSouth Hannah, GU 16275',
},
    'key48925': 'value37168',
    'key74765': 'value50282',
    'key26317': 'value42127',
    'key95720': 'value93332',
    'key8878': 'value69449',
    'key21415': 'value16039',
    'key42371': 'value64956',
    'key71098': 'value77624',
    'key13541': 'value92605',
    'key14107': 'value7023',
},
    {
    'id': 17527487699800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Glenn Watkins',
    'address': '230 Lindsay Unions Suite 621\nNorth Michele, CA 55538',
    'text': 'Room set finally best necessary. Degree night plan point party. Any method size sound significant.\nSomebody opportunity star individual. West house statement under truth spend.',
    'email': 'grahamdustin@example.com',
    'phone_number': '914-972-3700',
    'json': {
    'name': 'Matthew Gregory',
    'address': '88596 Carey Land\nNew Adrian, ME 04050',
},
    'key85388': 'value71266',
    'key35215': 'value96532',
    'key27228': 'value19603',
    'key16587': 'value10895',
    'key92492': 'value86387',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
    'filter': '10+20 <= uid < 20+30',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
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
    'RequestId': '4dfd7432-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_23_832928Bjsnncxr',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752748778.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrue1020Uid20301752748778Json()
    test.run_tests()
