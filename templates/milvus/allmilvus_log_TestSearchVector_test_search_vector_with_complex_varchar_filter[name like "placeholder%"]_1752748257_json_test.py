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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_complex_varchar_filter[name like "placeholder%"]_1752748257_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name like "placeholder%"]_1752748257.json"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithComplexVarcharFilterNameLikePlaceholder1752748257Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name like "placeholder%"]_1752748257.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name like "placeholder%"]_1752748257.json"
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
    'data': [
    {
    'id': 17527482540930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Paige Johnson',
    'address': '76801 Andrea Spur\nEast Justin, AZ 28516',
    'text': 'Cost thing interesting forget next. Agreement financial PM college soldier want. Enter action form reduce information.\nCover technology paper. Fact animal mother.',
    'email': 'iolson@example.org',
    'phone_number': '355-305-3083x44500',
    'json': {
    'name': 'Kelli Rodriguez',
    'address': '8841 Bishop Union\nWest Ashleyville, VT 77741',
},
    'key49575': 'value45459',
    'key46159': 'value10411',
    'key51108': 'value27460',
    'key60995': 'value86136',
},
    {
    'id': 17527482540948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Jeffrey Collins',
    'address': '3653 Williams Curve\nStephanieborough, MI 27891',
    'text': 'Kind various attack join child participant pattern. List ask above rock then show.\nDefense building these decade. Reduce nation still finish since history involve view.',
    'email': 'shanelopez@example.net',
    'phone_number': '397-395-7945x47214',
    'json': {
    'name': 'Elizabeth Holmes',
    'address': '6200 White Cliffs Apt. 734\nNorth Stephenport, AS 04159',
},
    'key74938': 'value88873',
    'key16903': 'value80730',
    'key87471': 'value7084',
    'key94842': 'value64050',
    'key19681': 'value33829',
    'key74058': 'value95812',
    'key37517': 'value6964',
},
    {
    'id': 17527482540963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Carolyn Hampton',
    'address': '07822 Powell Light Apt. 756\nStephensonfurt, DC 32860',
    'text': 'Let success commercial late. Design though source difficult soldier section. Action few able what sport election drug. Fly as author line but.',
    'email': 'kimberly47@example.org',
    'phone_number': '9709172986',
    'json': {
    'name': 'Jessica Alvarez',
    'address': '0269 Ross Street\nStephenhaven, MN 85724',
},
    'key90366': 'value1362',
},
    {
    'id': 17527482540976,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Chloe Miller',
    'address': 'USNV Massey\nFPO AE 33940',
    'text': 'Detail prevent yes run ever material. Great knowledge provide question experience another find.\nTrue value sound out stage modern speech. Success main keep. Positive everybody two.',
    'email': 'mark88@example.org',
    'phone_number': '001-988-932-2473',
    'json': {
    'name': 'Brian Palmer',
    'address': '801 Cole Roads Apt. 728\nPenaland, OK 42396',
},
    'key41804': 'value71029',
    'key15570': 'value80732',
    'key29213': 'value79610',
    'key2747': 'value4540',
    'key39164': 'value20424',
    'key6744': 'value47627',
    'key68045': 'value68917',
    'key72334': 'value72046',
    'key96044': 'value29130',
    'key94052': 'value95122',
},
    {
    'id': 17527482540989,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Jamie Rogers',
    'address': '6650 Taylor Dale\nKennedychester, CO 86772',
    'text': 'Account culture street senior. Never born million director president now protect. Relationship put move no series friend military.\nTough exactly heart consumer. Investment film near lay collection.',
    'email': 'elizabethlopez@example.com',
    'phone_number': '(751)783-7547x7513',
    'json': {
    'name': 'Michael Smith',
    'address': '447 Rachael Isle\nDominguezshire, HI 94182',
},
    'key73842': 'value68274',
    'key17379': 'value57220',
    'key8579': 'value10041',
    'key68756': 'value77010',
    'key81976': 'value73287',
    'key23887': 'value38503',
},
    {
    'id': 17527482541003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joy Warren',
    'address': '411 Brown Orchard\nMurphyton, NC 71451',
    'text': 'Nature agent indicate result its common. Determine peace theory let rock second. Fear without stop necessary generation again.',
    'email': 'david24@example.net',
    'phone_number': '627.325.8540',
    'json': {
    'name': 'Donna Bradley',
    'address': '431 Nielsen Wall\nNorth Mary, IN 22928',
},
    'key62703': 'value12787',
    'key68107': 'value67452',
    'key17655': 'value56736',
    'key71003': 'value9494',
    'key16633': 'value27864',
},
    {
    'id': 17527482541016,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Cathy Harris',
    'address': '4022 Natalie Plaza Apt. 082\nSouth Karenchester, NM 30829',
    'text': 'News interview attention expert. Study kid check executive return rather. Threat high foot.\nProduce area station team very son tell. Model painting food between sport.',
    'email': 'thomas91@example.net',
    'phone_number': '001-688-760-4123x6804',
    'json': {
    'name': 'Dana Ortega',
    'address': '870 Jennifer Dam\nNorth Ashlee, AZ 90564',
},
    'key34542': 'value62239',
    'key25815': 'value36551',
    'key12794': 'value52896',
    'key36069': 'value26624',
    'key87166': 'value23590',
    'key99093': 'value32485',
    'key20113': 'value46201',
    'key22395': 'value75619',
    'key34052': 'value60603',
},
    {
    'id': 17527482541028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Carly Cook',
    'address': '022 Johnson Falls\nLake Ronald, MI 86307',
    'text': 'Last scientist provide her. Sell response wonder. News view production cost myself lawyer administration.',
    'email': 'mccarthyrenee@example.net',
    'phone_number': '460.942.6029',
    'json': {
    'name': 'Kimberly Torres',
    'address': '2229 Wood Spur Apt. 853\nPort Dominiquemouth, TN 70486',
},
    'key71501': 'value5093',
    'key37136': 'value82084',
    'key32079': 'value17272',
    'key7155': 'value67245',
    'key13952': 'value92893',
    'key97525': 'value44467',
    'key54077': 'value65788',
},
    {
    'id': 17527482541040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Marc Stewart',
    'address': '94502 John Common Apt. 135\nNorth Joshua, NC 68650',
    'text': 'Game hand very month then sometimes sea themselves. Star simple issue consumer cold.\nRecord pick fill six. Book development forget would rock. Mean sort total hospital per well.',
    'email': 'jsims@example.com',
    'phone_number': '(928)447-5011x727',
    'json': {
    'name': 'Cathy Richard',
    'address': '574 Caitlyn Mews\nMortontown, WA 59173',
},
    'key24742': 'value80168',
    'key41981': 'value73182',
    'key277': 'value45032',
    'key4202': 'value24868',
    'key12303': 'value19114',
    'key4032': 'value74664',
},
    {
    'id': 17527482541052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Zachary Martin',
    'address': '931 James Plains Apt. 345\nStevenstad, NJ 27332',
    'text': 'Dinner end including national focus leave. Forget indeed school hour several. Fly yet beyond mouth compare back teach.',
    'email': 'edwardmartinez@example.net',
    'phone_number': '+1-586-371-5893x966',
    'json': {
    'name': 'David Howell',
    'address': '6770 Kevin Lakes Suite 746\nWilsonmouth, ND 08181',
},
    'key76206': 'value68444',
    'key11437': 'value26357',
    'key76685': 'value11040',
    'key83792': 'value40718',
    'key13615': 'value41728',
    'key20183': 'value74833',
    'key67372': 'value6793',
    'key51304': 'value77111',
    'key22886': 'value60187',
},
    {
    'id': 17527482541064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'James Bradley',
    'address': '88507 Miller Trail\nLake Valerieburgh, SC 27083',
    'text': 'Pretty question word story.\nFoot foot another vote. Station two ok consumer. Film at serve though everyone statement.',
    'email': 'jamesdavila@example.net',
    'phone_number': '305.573.3045x723',
    'json': {
    'name': 'Amber Harmon',
    'address': 'Unit 1083 Box 9686\nDPO AP 99320',
},
    'key55794': 'value10362',
    'key32797': 'value76178',
    'key12609': 'value98606',
    'key90965': 'value61379',
    'key83868': 'value42476',
    'key55148': 'value12589',
    'key36603': 'value68697',
    'key15177': 'value35608',
    'key58334': 'value68616',
},
    {
    'id': 17527482541074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Candice Castro',
    'address': '84840 Margaret Oval Apt. 747\nWallacestad, MI 93281',
    'text': 'Election amount best cover. Fire culture into south sister town.\nInstitution eye general. Always agreement build issue goal brother form. Smile pattern information act leg easy shake million.',
    'email': 'khoward@example.org',
    'phone_number': '(313)980-2114',
    'json': {
    'name': 'Greg Williams',
    'address': '002 Greg Skyway\nRebeccaborough, SC 51342',
},
    'key31200': 'value61298',
    'key49299': 'value62119',
    'key53834': 'value75562',
    'key45065': 'value46898',
    'key21805': 'value84328',
    'key83091': 'value81912',
    'key54696': 'value6112',
},
    {
    'id': 17527482541085,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Mitchell Baker',
    'address': '0620 Stokes Rue Suite 695\nGonzalesstad, ND 36249',
    'text': 'Central prove suffer become. Music pressure friend computer deep just. From side practice responsibility.',
    'email': 'omccormick@example.net',
    'phone_number': '(338)227-9652',
    'json': {
    'name': 'Connie Mcpherson',
    'address': '161 Crawford Way Apt. 473\nMelodyberg, VI 28177',
},
    'key47342': 'value67137',
    'key44614': 'value95097',
    'key2042': 'value55637',
    'key23501': 'value77017',
    'key78387': 'value51892',
},
    {
    'id': 17527482541096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Rebecca Barr',
    'address': '05560 Gonzalez Point\nNew Curtis, WY 30425',
    'text': 'Economic remain price whom. Maybe produce side plan different project.\nLeg such church walk blood. Down suggest event sit air attack available possible. Available magazine social finish.',
    'email': 'sandra42@example.net',
    'phone_number': '9655212916',
    'json': {
    'name': 'Christopher Williams',
    'address': '179 Martin Fords Suite 916\nChristinemouth, MS 26099',
},
    'key73405': 'value71152',
    'key9151': 'value11053',
    'key43619': 'value46793',
    'key73637': 'value98621',
},
    {
    'id': 17527482541107,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Daniel Collins',
    'address': '3465 Bailey Hollow\nNew Erica, FM 27682',
    'text': 'That language organization least expect language could. Thus seem large sort.\nYes quite medical office easy plan court.\nJob all often easy point keep. General state economy behavior.',
    'email': 'elong@example.net',
    'phone_number': '001-596-278-9000x53123',
    'json': {
    'name': 'Brian Gibson',
    'address': '4828 David Camp\nJonathantown, NH 45675',
},
    'key81684': 'value3427',
    'key40393': 'value34753',
    'key25710': 'value44571',
    'key60657': 'value30846',
    'key94527': 'value76109',
    'key97242': 'value30989',
},
    {
    'id': 17527482541118,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Susan Washington',
    'address': '051 Lin Divide\nRyanshire, MD 85023',
    'text': 'Per point later morning. Member until still I. Continue data draw religious apply live. Born fight him television reason body floor.',
    'email': 'xjensen@example.com',
    'phone_number': '845-315-1198x439',
    'json': {
    'name': 'Tracy Cook',
    'address': '06380 Ashley Track Apt. 032\nYangtown, NV 35013',
},
    'key66002': 'value46088',
    'key57813': 'value18956',
    'key77680': 'value79712',
    'key85944': 'value5018',
    'key75223': 'value75667',
},
    {
    'id': 17527482541130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Jesse Mccall',
    'address': '929 Delacruz Mews\nJulietown, NJ 23630',
    'text': 'Fine well step federal piece. Create read moment summer ok fear even.',
    'email': 'arobinson@example.com',
    'phone_number': '716-493-4345x622',
    'json': {
    'name': 'Dylan Burke',
    'address': '53056 Jessica Trafficway\nJessemouth, NJ 74989',
},
    'key85308': 'value49949',
    'key4124': 'value37943',
    'key17731': 'value11774',
    'key53032': 'value87798',
    'key20811': 'value95402',
},
    {
    'id': 17527482541140,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Alex Gillespie',
    'address': '31411 Bradford Green\nSouth Ricky, OR 15365',
    'text': 'As school performance arrive few picture. Law enjoy relate Mr.\nWithout fast member total day finally.',
    'email': 'michelle08@example.net',
    'phone_number': '703.779.3489',
    'json': {
    'name': 'Timothy Anderson',
    'address': '05026 Russell Ville Apt. 425\nTylermouth, NJ 44184',
},
    'key90517': 'value28181',
    'key46887': 'value36572',
    'key93176': 'value93568',
    'key70820': 'value58408',
    'key87964': 'value48594',
    'key19895': 'value3141',
},
    {
    'id': 17527482541150,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Steven Sweeney',
    'address': '835 Jefferson Passage Apt. 255\nNorth Leah, NC 13128',
    'text': 'Everybody month listen physical. Each even far adult.\nReflect personal dream stop seek perhaps. Thought poor peace moment fill successful. Money these adult less.',
    'email': 'martinrichard@example.net',
    'phone_number': '001-254-280-8088x4924',
    'json': {
    'name': 'Cheryl Walter',
    'address': '9412 Matthew Isle\nKelseychester, WV 90324',
},
    'key63258': 'value36879',
    'key30815': 'value93658',
    'key2160': 'value13971',
    'key87388': 'value35458',
    'key80741': 'value70642',
    'key92761': 'value33099',
    'key77600': 'value97228',
    'key26656': 'value21031',
    'key54170': 'value39718',
},
    {
    'id': 17527482541162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Mariah Scott',
    'address': '33724 Lisa Ports\nSouth Andrew, CT 32836',
    'text': 'Which worry life leg. Nearly common answer TV foot voice.\nBusiness message large appear friend.\nOn article manage century analysis trade.',
    'email': 'brandi16@example.net',
    'phone_number': '+1-878-867-4662x3058',
    'json': {
    'name': 'Brent Watkins DVM',
    'address': '08147 Alexander Lakes Apt. 950\nJefferyside, NH 16572',
},
    'key6229': 'value38269',
    'key4431': 'value41283',
    'key10564': 'value77876',
},
    {
    'id': 17527482541172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Carol Pope',
    'address': '24023 Michael Isle\nShannonmouth, NE 68235',
    'text': 'Catch say interview chance. Whether step life catch himself turn.\nSea soon community rich book get.\nGive many behavior current site case. World give when moment compare somebody rise.',
    'email': 'vjones@example.org',
    'phone_number': '001-466-793-4860x2969',
    'json': {
    'name': 'John Peters',
    'address': '68426 Robert Point Suite 544\nVargasborough, PA 35336',
},
    'key91207': 'value85264',
    'key62987': 'value25988',
    'key82938': 'value37812',
    'key79578': 'value54285',
    'key73551': 'value62050',
    'key44956': 'value69842',
    'key30904': 'value81886',
    'key33238': 'value95735',
},
    {
    'id': 17527482541183,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Cynthia Mckay',
    'address': '265 William Trace Apt. 569\nPort Eric, MP 84293',
    'text': 'Large push trip true capital section professional. Ever ago catch reason represent pass mother. Level question six ago visit develop.',
    'email': 'vkoch@example.net',
    'phone_number': '001-986-662-6622x1073',
    'json': {
    'name': 'Theresa Ruiz',
    'address': '04534 Eric Turnpike Apt. 362\nKyleshire, ID 20851',
},
    'key59135': 'value5478',
    'key57259': 'value29469',
    'key1545': 'value23166',
},
    {
    'id': 17527482541194,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Sarah Wilson',
    'address': '61431 Kenneth Vista Apt. 563\nNew Bethanyburgh, CT 02037',
    'text': 'Learn he make guy card majority yourself. Once painting clear total economy news other. Young store image art response four day. Describe business half pick stock collection.',
    'email': 'smiller@example.net',
    'phone_number': '7416882701',
    'json': {
    'name': 'Tiffany Kramer',
    'address': 'PSC 0916, Box 4964\nAPO AP 01291',
},
    'key85662': 'value38046',
    'key59485': 'value39417',
    'key27623': 'value53323',
    'key37434': 'value36981',
},
    {
    'id': 17527482541203,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Brian Downs',
    'address': '706 Jason Crossing Suite 223\nRobinsonchester, NM 96694',
    'text': 'Character young argue local. Oil buy yeah affect ability space. Their important happen good admit.\nSize trouble population teach discuss. Occur food fly employee natural.',
    'email': 'johnmeyer@example.net',
    'phone_number': '935.478.9270',
    'json': {
    'name': 'Robert Cohen',
    'address': '61011 Nicholas Gardens\nNew Lisaberg, IA 18107',
},
    'key20530': 'value6631',
    'key56863': 'value80495',
    'key70783': 'value53564',
    'key35341': 'value96967',
},
    {
    'id': 17527482541213,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Jessica Hernandez',
    'address': '441 Zuniga Tunnel\nNew Amanda, DC 21520',
    'text': 'Recognize truth mean can. Discuss piece time during whole throughout full. Window have need employee.',
    'email': 'imyers@example.org',
    'phone_number': '001-986-394-5676',
    'json': {
    'name': 'Patrick Phillips',
    'address': '48478 Mcdaniel River\nPort Brandonborough, CO 05132',
},
    'key2466': 'value10135',
    'key54341': 'value19197',
    'key28799': 'value48226',
    'key81113': 'value61329',
},
    {
    'id': 17527482541224,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Logan Reed',
    'address': '69764 Bowen Causeway Apt. 935\nWest Susantown, WV 84937',
    'text': 'Recognize live however exactly evening better similar word. Lose race group more. Few house nature answer agree treatment item small. Today down help.',
    'email': 'zjohnston@example.org',
    'phone_number': '+1-561-640-5406x01333',
    'json': {
    'name': 'John Barker',
    'address': '276 Rivera Island Apt. 641\nSouth Christinafort, DE 20032',
},
    'key45724': 'value34449',
},
    {
    'id': 17527482541235,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Christopher Saunders MD',
    'address': '030 Kevin Estates\nJohnsonburgh, UT 52053',
    'text': 'Method ok sound help police social common. Trial against you everybody. Have concern program big product across church nothing. Special develop black study sense.',
    'email': 'harriskirk@example.org',
    'phone_number': '285.805.4978x6075',
    'json': {
    'name': 'Brad Mendoza',
    'address': '861 Perry Via Apt. 959\nSpencerburgh, OR 63481',
},
    'key69043': 'value18225',
    'key80307': 'value68736',
    'key57218': 'value71769',
    'key11142': 'value89650',
    'key62914': 'value46164',
    'key34777': 'value98263',
},
    {
    'id': 17527482541247,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jeffrey Reynolds',
    'address': '2842 Becker Drive\nNew Jasonchester, CO 33776',
    'text': 'Small drug really miss suggest. Suffer you through cultural about radio. Media job fight. Day employee value through cut vote after.',
    'email': 'atkinsonryan@example.net',
    'phone_number': '001-415-954-5382x6860',
    'json': {
    'name': 'Carl Reed',
    'address': '26521 Donna Stream Apt. 829\nNorth Arthurview, IL 05509',
},
    'key8349': 'value14815',
    'key32773': 'value241',
},
    {
    'id': 17527482541259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Christopher Williams',
    'address': '1162 Long Neck\nMullinsfurt, GA 57494',
    'text': 'Condition stock behind. Police hand put so meet. Relate ready true hear while tell art carry. Apply president point everybody world would.',
    'email': 'theresahester@example.org',
    'phone_number': '781.532.9614',
    'json': {
    'name': 'Jon Moses',
    'address': '7357 Juarez Wells\nLake Dylan, HI 85781',
},
    'key48620': 'value67472',
    'key43856': 'value43879',
    'key16600': 'value67377',
    'key26908': 'value17750',
    'key41515': 'value70',
    'key44574': 'value45645',
    'key43750': 'value54758',
    'key68244': 'value77844',
},
    {
    'id': 17527482541270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Beverly Burton',
    'address': '538 Elliott Forges\nEast Claytonchester, AL 93843',
    'text': 'Movie military field garden author. Much voice approach same age tonight. Play allow poor election claim court notice cup.\nDespite arm represent move. Order individual such product.',
    'email': 'lopezalice@example.net',
    'phone_number': '+1-659-856-2319x931',
    'json': {
    'name': 'Susan Parker',
    'address': '4482 Richard Harbor Apt. 418\nKentburgh, NH 89192',
},
    'key4693': 'value70058',
    'key52654': 'value48738',
    'key21205': 'value17590',
},
    {
    'id': 17527482541282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jesse Cole',
    'address': '3080 Garcia Bridge Apt. 681\nNorth Sandraland, AS 55861',
    'text': 'Less personal would. Father return provide market military.\nLater color sometimes live brother prepare.',
    'email': 'qrhodes@example.org',
    'phone_number': '001-447-894-5571x18440',
    'json': {
    'name': 'Jeffrey Lang Jr.',
    'address': 'Unit 3230 Box 4038\nDPO AE 87805',
},
    'key75493': 'value20683',
    'key66282': 'value61438',
    'key41544': 'value25594',
},
    {
    'id': 17527482541291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Emily Clark PhD',
    'address': '1956 Joe Rapid Suite 892\nJenniferchester, AK 43119',
    'text': 'Value check receive feel into whatever off. Effort citizen grow clear. Consumer together down newspaper.\nDebate candidate main I. Act parent third me including.',
    'email': 'rogersmarissa@example.org',
    'phone_number': '+1-778-749-6715x09508',
    'json': {
    'name': 'Jason Wilson',
    'address': '94599 Willie Springs Apt. 296\nBakerview, KS 68111',
},
    'key57823': 'value91050',
    'key95244': 'value70759',
    'key89590': 'value4597',
    'key60671': 'value14752',
    'key8816': 'value52000',
    'key16501': 'value29295',
    'key62951': 'value65207',
    'key19566': 'value90475',
},
    {
    'id': 17527482541302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Colleen Spears',
    'address': '8330 Mark Walks\nSouth Jillianside, GU 09144',
    'text': 'Throw break Congress against break somebody compare. Rich happy form however feel resource. Particularly area beautiful next community drug.',
    'email': 'jterrell@example.com',
    'phone_number': '(777)428-2196x54779',
    'json': {
    'name': 'Aaron Hill',
    'address': '218 Soto Radial\nSouth Ruth, UT 05176',
},
    'key75415': 'value28778',
    'key99575': 'value67384',
    'key34511': 'value20157',
    'key10634': 'value33611',
    'key80569': 'value2999',
    'key68003': 'value4187',
    'key60604': 'value28048',
    'key29356': 'value88026',
},
    {
    'id': 17527482541313,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kelly Hoffman',
    'address': '66029 Warren Estates\nMcconnellborough, NY 12145',
    'text': 'General song environment father throw. Else indicate floor notice close main.\nPlant reflect everybody technology mother. Allow teacher first sell.',
    'email': 'wcooper@example.net',
    'phone_number': '9265415336',
    'json': {
    'name': 'Angelica Johnson',
    'address': '197 Ruben Camp Suite 334\nPort Robert, AL 27933',
},
    'key73016': 'value15218',
    'key36122': 'value51412',
    'key14305': 'value19864',
    'key75287': 'value42977',
    'key55134': 'value44829',
    'key10604': 'value14501',
    'key99882': 'value26449',
},
    {
    'id': 17527482541324,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Shirley Owen',
    'address': '950 Norma Junctions Apt. 864\nStevensonton, CA 75596',
    'text': 'Worker surface environment. Me practice part must five gun. Quickly data east forget window.\nCouple stay ground. Must fight behind popular. Action into organization bit ground.',
    'email': 'joseph03@example.org',
    'phone_number': '903-302-3357x583',
    'json': {
    'name': 'Jacqueline Jimenez',
    'address': '72143 Dyer Meadow Suite 015\nNorth Kristen, NJ 72773',
},
    'key96915': 'value63551',
},
    {
    'id': 17527482541335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Rebecca Gibson',
    'address': '765 Dunn Coves Apt. 584\nPort Brian, MP 66224',
    'text': 'Of show so happen quality always. Imagine southern artist property.\nClose sell effort manage. Pull executive ground family two understand recognize five.',
    'email': 'stevensemily@example.com',
    'phone_number': '001-244-980-3894x01717',
    'json': {
    'name': 'Michael Rodriguez',
    'address': 'PSC 6073, Box 8309\nAPO AE 61553',
},
    'key61894': 'value122',
    'key27473': 'value26343',
    'key32731': 'value53598',
    'key19421': 'value68090',
    'key44281': 'value87834',
    'key70040': 'value24029',
    'key16960': 'value26830',
},
    {
    'id': 17527482541345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Charles Orozco',
    'address': '602 Alexis Mill Suite 432\nEast Karenfort, AL 50315',
    'text': 'Entire ok western growth event but. Alone task down provide.\nSea respond dog determine consider visit. Either especially involve it series argue.\nActually half affect why. Then arrive page visit.',
    'email': 'linda03@example.org',
    'phone_number': '9223130846',
    'json': {
    'name': 'Sheila Stone',
    'address': '65416 Jeffrey Throughway\nPort David, ME 53736',
},
    'key87624': 'value46427',
    'key44985': 'value13254',
    'key47303': 'value97557',
    'key44679': 'value56839',
    'key51709': 'value19174',
    'key40489': 'value39755',
    'key65314': 'value73090',
    'key78869': 'value44846',
    'key44752': 'value42352',
    'key86938': 'value52797',
},
    {
    'id': 17527482541355,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Joseph Hill',
    'address': '3319 Kenneth Heights\nWest Laurahaven, ME 89795',
    'text': 'Lot number later great. Answer safe arm growth situation even. Ten land hair.\nTogether yard thus star. Money officer better card mission put building young. Front road general after.',
    'email': 'millskaren@example.org',
    'phone_number': '322-377-7499',
    'json': {
    'name': 'Sheena Evans',
    'address': 'USNV Thornton\nFPO AA 85172',
},
    'key98476': 'value89191',
    'key9175': 'value75741',
    'key22878': 'value64172',
    'key25934': 'value14808',
    'key47667': 'value12227',
    'key74630': 'value67344',
    'key64117': 'value93885',
    'key19712': 'value91245',
    'key7169': 'value30498',
},
    {
    'id': 17527482541365,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Morgan Anderson',
    'address': '3446 Linda Flats\nCooperside, NY 11914',
    'text': 'Positive lead ever even save ability lead remain. Include simply job poor size Congress.\nOwner us father write. Stuff statement Mr save. With white beyond.',
    'email': 'oconnorcraig@example.com',
    'phone_number': '288-724-6766x7493',
    'json': {
    'name': 'Mark Garrison',
    'address': '88137 Andrea Manor Suite 277\nPerezborough, AZ 13751',
},
    'key30940': 'value47110',
    'key70571': 'value74968',
    'key88133': 'value57642',
    'key96662': 'value86108',
    'key96244': 'value74408',
    'key71817': 'value25263',
    'key73568': 'value6375',
},
    {
    'id': 17527482541377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jessica Lynch',
    'address': '6863 Amber Terrace Suite 149\nEast William, MH 15820',
    'text': 'Spend will mind statement. Determine strategy back. Air total true tend easy.\nDefense red movie sister anyone site. Hear spend into market action less. Yard blue interesting painting.',
    'email': 'renee80@example.org',
    'phone_number': '356-428-8226x8931',
    'json': {
    'name': 'Heather Hart',
    'address': '71907 Kevin Shoals\nMeganburgh, OH 58595',
},
    'key49481': 'value487',
    'key62566': 'value31238',
    'key95552': 'value44267',
    'key82342': 'value5037',
    'key97799': 'value43268',
    'key17639': 'value33604',
    'key81298': 'value45958',
},
    {
    'id': 17527482541387,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jacob Miller',
    'address': '1993 Jamie Hollow\nJamesmouth, VA 61395',
    'text': 'Night enter represent loss. May big song scientist song.\nHave traditional several pull discuss. Approach charge example under team chair heavy voice.',
    'email': 'yhughes@example.org',
    'phone_number': '430-869-9504',
    'json': {
    'name': 'Emily Stone',
    'address': '75545 Alison Ports Apt. 287\nIsabellahaven, AK 82817',
},
    'key12565': 'value17052',
    'key22410': 'value91113',
    'key21134': 'value48303',
},
    {
    'id': 17527482541398,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Mark Taylor',
    'address': '49840 Robert Ville\nWest Justinhaven, GU 23942',
    'text': 'Cover throw upon. Expect middle lead training interest deep whose. Vote age bag goal above couple education ball.',
    'email': 'ioliver@example.org',
    'phone_number': '5719333232',
    'json': {
    'name': 'Alex Smith',
    'address': '658 James Squares\nEast Kelseyland, VT 99501',
},
    'key27029': 'value81085',
    'key61762': 'value70294',
    'key1782': 'value6608',
    'key28977': 'value98790',
    'key46385': 'value71406',
    'key88104': 'value98939',
    'key21900': 'value94060',
    'key30350': 'value54524',
},
    {
    'id': 17527482541408,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Lindsay Munoz',
    'address': '264 Ruiz Common\nPort Paulbury, OR 31619',
    'text': 'You floor half every until term now concern. Set prepare summer language.\nSite inside enough detail white. Involve when on year interview.\nTime try fast safe.',
    'email': 'brittneybullock@example.com',
    'phone_number': '838.959.3287',
    'json': {
    'name': 'Christopher Duncan',
    'address': 'Unit 1758 Box 1679\nDPO AE 78307',
},
    'key24834': 'value53065',
    'key14164': 'value75286',
    'key21278': 'value99299',
    'key37404': 'value64175',
    'key66698': 'value46598',
    'key84574': 'value70846',
},
    {
    'id': 17527482541417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kathleen Jones',
    'address': '414 Maureen Island\nMorganstad, AS 90399',
    'text': 'Service economy national today consumer seat international anything.\nMore technology share simply up movement available eight.\nMagazine statement put. Discuss particularly ten sell doctor.',
    'email': 'yangnathan@example.org',
    'phone_number': '001-560-858-9100',
    'json': {
    'name': 'David Atkins',
    'address': '18866 Ricardo Stravenue\nDawnberg, ME 41531',
},
    'key11320': 'value22505',
    'key13638': 'value45986',
    'key11925': 'value72481',
},
    {
    'id': 17527482541428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Renee Davis',
    'address': '835 Jackson Landing\nLewisfurt, OR 78798',
    'text': 'Radio visit own thank. Tax board chance sure capital. Top show class offer story bit seat.',
    'email': 'brianna89@example.net',
    'phone_number': '724-852-2687',
    'json': {
    'name': 'Susan Quinn',
    'address': '5096 Amanda Drive\nAndrewstad, NV 25997',
},
    'key9452': 'value24390',
    'key78147': 'value43961',
    'key83287': 'value51320',
    'key78463': 'value95839',
    'key64378': 'value35131',
    'key79369': 'value53162',
    'key62790': 'value76965',
    'key66466': 'value17528',
    'key72993': 'value54524',
    'key88169': 'value6793',
},
    {
    'id': 17527482541439,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Alex Gardner',
    'address': '5172 Jacob Crest\nSarahmouth, WY 49980',
    'text': 'Past war you other put sister. Situation fill where physical alone. Close growth audience instead herself image.\nField these tend will bring true. Your ground rule pay worker. Myself wear better.',
    'email': 'sarah17@example.org',
    'phone_number': '+1-249-610-4364x92872',
    'json': {
    'name': 'Robert Lindsey',
    'address': '7158 Evan Centers Apt. 152\nNorth Tara, NH 21287',
},
    'key12053': 'value37609',
    'key63569': 'value93328',
    'key89288': 'value22078',
    'key61518': 'value96973',
    'key54696': 'value65855',
    'key21477': 'value52449',
    'key23016': 'value26691',
    'key67364': 'value80921',
},
    {
    'id': 17527482541449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Carol Becker',
    'address': 'Unit 3508 Box 7768\nDPO AA 03237',
    'text': 'Ever tend political think. Keep assume son talk.\nAt claim writer. No court stay decision research.',
    'email': 'richardsonvictoria@example.net',
    'phone_number': '+1-745-381-6315',
    'json': {
    'name': 'Lauren Miller',
    'address': 'Unit 7445 Box 1086\nDPO AP 89230',
},
    'key49682': 'value19018',
},
    {
    'id': 17527482541456,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Megan Jones',
    'address': '473 Perez Pine\nAntonioside, SC 37032',
    'text': 'Few debate seat despite according go cost yard. West rather spend clear painting nature. Bag respond chance member.',
    'email': 'robertcoleman@example.com',
    'phone_number': '922-857-3000x841',
    'json': {
    'name': 'Tammie Wang',
    'address': '744 Dennis Neck\nLake Jessicaville, IA 04451',
},
    'key90253': 'value21943',
    'key53670': 'value33927',
    'key25406': 'value36810',
},
    {
    'id': 17527482541467,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Tricia White',
    'address': '4432 Gould Highway Suite 044\nNorth Jacobhaven, TX 59062',
    'text': 'Kitchen machine tonight next security authority. House want great increase. Represent his top evidence behavior.\nMain since woman old. Pay water up.',
    'email': 'oliverrussell@example.net',
    'phone_number': '(406)802-8522',
    'json': {
    'name': 'Cheryl Kim',
    'address': '68407 Thomas Stravenue Suite 624\nTrevorfurt, OR 16067',
},
    'key35210': 'value79109',
    'key80832': 'value28895',
    'key41305': 'value67028',
    'key67989': 'value10398',
    'key37318': 'value83542',
    'key28670': 'value10305',
    'key69637': 'value2958',
    'key96704': 'value10221',
    'key11318': 'value99463',
},
    {
    'id': 17527482541479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Natasha Herrera',
    'address': '739 James Village\nBrianafort, NV 91755',
    'text': 'Another moment win. South feel trip.\nStart management become heavy teacher run.\nReflect be north worry weight day born. Happy his economic today industry tend.\nThe have account single.',
    'email': 'fuentesangela@example.com',
    'phone_number': '780-904-8024',
    'json': {
    'name': 'Veronica Roberts',
    'address': '5754 Jay Gardens\nEast Lisa, KY 38944',
},
    'key37734': 'value93121',
    'key48181': 'value43313',
    'key79480': 'value54005',
    'key25590': 'value20545',
},
    {
    'id': 17527482541490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Jeffrey Ballard',
    'address': '09236 Aaron Pines Apt. 931\nNorth Abigail, MD 50255',
    'text': 'Road difference rather mother.\nSmall which report arrive raise natural. Might bag town race.\nWhether off them difference risk. Painting work network off community accept fear.',
    'email': 'norrisjuan@example.net',
    'phone_number': '(356)741-8255x671',
    'json': {
    'name': 'Tracy Anderson',
    'address': '06954 Grace Via Suite 929\nBarnesport, VA 45349',
},
    'key45459': 'value80674',
    'key96330': 'value57985',
    'key90312': 'value2287',
},
    {
    'id': 17527482541502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Crystal Randall',
    'address': '0960 William Fords\nPortershire, RI 08562',
    'text': 'Seat determine wear fire chance people executive. Although it decide prepare language responsibility. Several phone control board.',
    'email': 'mreyes@example.org',
    'phone_number': '+1-311-796-5527x6353',
    'json': {
    'name': 'Desiree Boone',
    'address': '6645 Murphy Glen Apt. 545\nTerrishire, FM 62929',
},
    'key58156': 'value10853',
    'key82161': 'value34606',
    'key25986': 'value32685',
    'key99947': 'value37299',
},
    {
    'id': 17527482541513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Shannon Holt',
    'address': '24924 Williams Lodge Apt. 926\nLucasport, FM 76239',
    'text': 'Media history back if. His identify feel dinner box.\nSimply money each risk pretty piece professor serve. Top impact summer think. Season Mrs leg ball.',
    'email': 'mking@example.net',
    'phone_number': '712.340.7995x407',
    'json': {
    'name': 'Melissa Ward',
    'address': 'Unit 3711 Box 2346\nDPO AA 61107',
},
    'key91953': 'value38526',
    'key37173': 'value55347',
    'key29874': 'value24415',
    'key95831': 'value42793',
    'key70654': 'value66639',
    'key32403': 'value60285',
    'key31382': 'value80925',
    'key42607': 'value74483',
},
    {
    'id': 17527482541522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Scott Jones',
    'address': '78755 Daniel Courts\nSheilafort, NM 76377',
    'text': 'Clearly walk culture wait. Never coach image our sing.\nTop size cover care. Analysis term artist hear identify.\nChurch wind who but after walk.',
    'email': 'clester@example.net',
    'phone_number': '973.881.0764x71160',
    'json': {
    'name': 'Ruth Fernandez',
    'address': '854 Jennifer Trail\nBaileyland, KS 47729',
},
    'key67118': 'value99173',
    'key38531': 'value12861',
    'key86097': 'value92803',
    'key74383': 'value37345',
    'key39509': 'value27836',
},
    {
    'id': 17527482541532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jessica Baker',
    'address': 'USNV Boone\nFPO AP 34321',
    'text': 'Music too return pay know card often hundred. Anyone her even mean protect.\nCentury development difficult together. Drug loss special game admit drive often wide. Drive with leg continue trouble.',
    'email': 'matthew94@example.net',
    'phone_number': '001-919-200-4117x87088',
    'json': {
    'name': 'Ashley Hensley',
    'address': '87767 Holden Parks\nAmandaburgh, VT 90704',
},
    'key11262': 'value31710',
},
    {
    'id': 17527482541541,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jason Brown',
    'address': '4786 Tyler Pass Apt. 314\nPort Michaela, VA 79349',
    'text': 'Between hot kid city how conference. Once reality firm onto official.',
    'email': 'cynthia51@example.net',
    'phone_number': '710-697-2684x02367',
    'json': {
    'name': 'Mrs. Cathy Clarke DDS',
    'address': '543 Steven Orchard\nAngelaport, WI 93365',
},
    'key28943': 'value27479',
    'key66792': 'value29371',
    'key88223': 'value2710',
    'key23079': 'value58958',
    'key87880': 'value34469',
    'key18745': 'value25347',
},
    {
    'id': 17527482541551,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Megan Clark',
    'address': '45450 Warner Key\nNew Bonnie, CA 75107',
    'text': 'Loss left world it morning activity ready. Crime grow best treatment. Pretty pull or not.\nReason change my tonight. Sell blood become herself key official. Yes light four race late because ball.',
    'email': 'kbell@example.com',
    'phone_number': '887.730.9612x3555',
    'json': {
    'name': 'Joseph Pearson',
    'address': '57476 Thompson Haven Apt. 427\nHollyfurt, HI 35821',
},
    'key45552': 'value36361',
    'key52341': 'value43034',
    'key89604': 'value70570',
    'key45734': 'value74723',
    'key67520': 'value12956',
},
    {
    'id': 17527482541562,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Megan Mcguire',
    'address': '0728 Vanessa Union\nJonesview, VI 41263',
    'text': 'Far black run institution account. Husband choose behind tend beat little. Offer food step few trouble mean.\nBill against PM. Environment station reality become. Trouble manager doctor off.',
    'email': 'zimmermanmichael@example.net',
    'phone_number': '685.468.4213x78987',
    'json': {
    'name': 'Nicole Brown',
    'address': '347 Katie Locks Apt. 506\nKennethmouth, FL 47255',
},
    'key95380': 'value63610',
},
    {
    'id': 17527482541574,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Meghan Black',
    'address': '18679 Amanda Loaf Apt. 055\nPort Heather, SC 74650',
    'text': 'Can view beyond hand later time operation. Major available vote someone probably board deal.\nNight that mention early relate. Draw involve challenge hundred though camera.',
    'email': 'andrewanderson@example.org',
    'phone_number': '627-513-7967x32852',
    'json': {
    'name': 'Jessica Simmons',
    'address': '480 Scott Springs\nGuzmanville, CA 03946',
},
    'key1115': 'value86399',
    'key84065': 'value82834',
    'key32590': 'value58892',
    'key3178': 'value14759',
    'key70576': 'value73206',
    'key49381': 'value37933',
    'key90283': 'value41394',
    'key95211': 'value70814',
    'key2822': 'value96153',
    'key79406': 'value46613',
},
    {
    'id': 17527482541585,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Caitlin Lee',
    'address': '026 Copeland Estates\nElizabethview, MN 21384',
    'text': 'Realize analysis begin. Analysis language reflect experience office. Within between forget outside read quite.\nOperation each successful create audience. Plant may commercial avoid.',
    'email': 'watkinsjon@example.net',
    'phone_number': '562-549-1800',
    'json': {
    'name': 'Sheila Salazar',
    'address': '1634 Anderson Way Apt. 547\nGreenbury, MH 50783',
},
    'key12229': 'value27710',
    'key96210': 'value53144',
    'key21194': 'value63270',
    'key88182': 'value55969',
    'key96425': 'value9670',
    'key6243': 'value94123',
    'key6618': 'value73814',
    'key80770': 'value84055',
    'key63484': 'value89421',
},
    {
    'id': 17527482541598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Troy Allen',
    'address': '45176 Kerry Summit Suite 437\nValerieburgh, NC 47551',
    'text': 'Crime example among improve. Boy look year total language technology. Take tax add get responsibility own.\nBecause range standard focus experience half determine.',
    'email': 'aaronritter@example.com',
    'phone_number': '645-642-5088',
    'json': {
    'name': 'Tiffany Peterson',
    'address': '05779 Michael Valley Suite 223\nWest Cassandra, NH 77178',
},
    'key56322': 'value98993',
    'key94713': 'value67357',
},
    {
    'id': 17527482541609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Tina Smith',
    'address': '7425 Lee Haven Suite 661\nSouth Brandon, UT 68266',
    'text': 'Mean interesting last turn floor. Author product teacher rule necessary teach.\nParticipant I animal book cell office edge. Respond far well from.',
    'email': 'nlewis@example.com',
    'phone_number': '001-437-618-0289x0199',
    'json': {
    'name': 'Ms. Tammy Morrison DVM',
    'address': '2507 Thomas Valley\nEast Hailey, FL 23377',
},
    'key27885': 'value48739',
    'key70685': 'value87217',
    'key16632': 'value93995',
    'key10423': 'value14254',
    'key81717': 'value38896',
},
    {
    'id': 17527482541620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Dale Hammond',
    'address': '86824 Jacqueline Lodge\nHaileyburgh, IL 14667',
    'text': 'Figure hard region catch soldier. Six hospital style friend level.\nSuccessful executive buy age. Fast school according base vote happy discussion.',
    'email': 'veronicablake@example.net',
    'phone_number': '001-715-680-4968',
    'json': {
    'name': 'Jeffrey Alvarez',
    'address': 'Unit 8641 Box 9052\nDPO AP 40733',
},
    'key97719': 'value75306',
    'key91719': 'value43342',
    'key63750': 'value69733',
    'key39363': 'value59303',
    'key70238': 'value35218',
    'key69404': 'value92322',
    'key92333': 'value96466',
},
    {
    'id': 17527482541629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Alicia Johnson',
    'address': '98224 Cameron Estate Suite 791\nKatiefurt, ME 88286',
    'text': 'Nice teacher word itself agree both south. Cost political top after prove training. Personal what parent him east religious.\nAnything really value lawyer likely take. How stay direction.',
    'email': 'jack83@example.net',
    'phone_number': '917.693.2071x9166',
    'json': {
    'name': 'Michael Gonzales',
    'address': '751 Carpenter Oval Suite 358\nMariamouth, SD 35364',
},
    'key62785': 'value84792',
    'key64378': 'value78815',
    'key39753': 'value67657',
    'key78188': 'value64538',
    'key39899': 'value56644',
    'key37777': 'value63758',
    'key6614': 'value23726',
    'key9488': 'value82816',
    'key98273': 'value20184',
},
    {
    'id': 17527482541639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Brittany Williams',
    'address': '930 Hoffman Flats Apt. 711\nEast Saraburgh, NV 18009',
    'text': 'Not behind toward from skin. Item response important area. Spend go suddenly seven.',
    'email': 'jacob71@example.org',
    'phone_number': '575-985-9426',
    'json': {
    'name': 'Cody Garcia',
    'address': '1690 Ryan Plains\nChristinamouth, TN 97333',
},
    'key10714': 'value27354',
    'key94102': 'value31111',
    'key72923': 'value43811',
    'key73286': 'value90318',
    'key31428': 'value16784',
    'key63569': 'value50410',
    'key71293': 'value50873',
},
    {
    'id': 17527482541650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Amy Myers',
    'address': '281 Guzman Circle Apt. 809\nLarsonmouth, AS 12560',
    'text': 'Talk near tree page language coach art. Upon try stuff letter because nearly structure. Beat federal just yard.\nApproach various too crime. Fast seven natural.',
    'email': 'william47@example.net',
    'phone_number': '+1-524-274-6833',
    'json': {
    'name': 'Karen Diaz',
    'address': '790 Shawn Terrace\nMartinezfurt, IL 70240',
},
    'key39832': 'value37452',
    'key81850': 'value68036',
    'key36026': 'value34451',
    'key38774': 'value95899',
},
    {
    'id': 17527482541661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jennifer Reed',
    'address': '4954 Matthew Burgs\nCynthiamouth, RI 95931',
    'text': 'Process population yes carry population here. Environment pattern call number. Again huge sister also service Mr.',
    'email': 'erikaklein@example.org',
    'phone_number': '527.696.3618x7567',
    'json': {
    'name': 'Deborah Fernandez',
    'address': '421 Karen Summit Suite 820\nCurtisfort, GU 33141',
},
    'key56332': 'value66408',
    'key24052': 'value83105',
    'key17894': 'value80645',
    'key31241': 'value1234',
    'key3288': 'value48096',
    'key83518': 'value28502',
    'key83336': 'value66944',
    'key71472': 'value59513',
},
    {
    'id': 17527482541672,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Katherine Bautista',
    'address': '1851 Travis Summit\nNew Meganbury, SD 57607',
    'text': 'Teach certain account full. Themselves Mr six attorney half lay billion.\nPolitics family seat two notice. Part space change operation. Down politics court give industry play.',
    'email': 'kevin48@example.com',
    'phone_number': '6143363462',
    'json': {
    'name': 'Amanda Harris',
    'address': '88201 Larson Roads Apt. 500\nDanielleside, NE 67857',
},
    'key56858': 'value67637',
    'key25868': 'value71524',
    'key53011': 'value43320',
    'key47455': 'value71960',
    'key94055': 'value53668',
    'key42826': 'value49093',
    'key5926': 'value90628',
    'key96668': 'value72901',
    'key32918': 'value17610',
},
    {
    'id': 17527482541682,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Michelle Mcdaniel',
    'address': '57542 Peters Turnpike\nWest William, LA 21611',
    'text': 'In blue sit tonight. Citizen usually side seven manage no.\nSister head population through rule more. Though democratic paper change.',
    'email': 'kimberlyhowell@example.com',
    'phone_number': '+1-662-843-6890',
    'json': {
    'name': 'Charles Alvarado',
    'address': 'PSC 2917, Box 8503\nAPO AE 40570',
},
    'key24806': 'value82575',
    'key81424': 'value79192',
    'key50634': 'value96252',
    'key76744': 'value98476',
    'key36218': 'value52181',
    'key93768': 'value70623',
    'key34382': 'value19899',
    'key83095': 'value50086',
    'key47833': 'value64683',
    'key40457': 'value43049',
},
    {
    'id': 17527482541692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Miguel Parker',
    'address': '21745 Salas Courts Suite 038\nElizabethchester, ME 14394',
    'text': 'Something husband far spend indeed. Citizen front outside easy stuff down voice. Board allow shake parent real unit someone.\nLanguage book debate sound from about build. Let grow begin serious.',
    'email': 'rclark@example.net',
    'phone_number': '625-558-9584x30517',
    'json': {
    'name': 'Brandon Wilson',
    'address': '284 Andrew Canyon\nKyleside, AS 31969',
},
    'key95744': 'value3884',
    'key33280': 'value38762',
    'key21651': 'value94858',
    'key78631': 'value50949',
    'key54181': 'value23560',
    'key72189': 'value99730',
    'key60179': 'value6889',
},
    {
    'id': 17527482541702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Alex Graham',
    'address': '614 Turner Shore\nSouth Jacob, AK 78123',
    'text': 'Would modern travel hear around among especially. Ball hold who call she style effect particular. Focus president difficult stop community before you.',
    'email': 'brian49@example.net',
    'phone_number': '(232)659-5208x5022',
    'json': {
    'name': 'Mitchell Pena',
    'address': '901 Suzanne Run Suite 350\nWilliamsberg, MA 51354',
},
    'key39516': 'value6151',
    'key85469': 'value58505',
    'key6906': 'value79981',
    'key93127': 'value42380',
    'key63008': 'value68354',
    'key48918': 'value53860',
    'key67308': 'value56096',
},
    {
    'id': 17527482541713,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Sarah Wolfe',
    'address': '109 Kimberly Shoal\nMargaretport, RI 19153',
    'text': 'Whom know side ever main magazine throughout. Exist statement prepare term.\nSite crime today chance whole. Throw organization others food picture detail audience.',
    'email': 'markmoore@example.org',
    'phone_number': '(402)970-2629x95871',
    'json': {
    'name': 'Nancy Wilson',
    'address': '6149 Janet Mall\nLake Roy, NJ 21664',
},
    'key1570': 'value16851',
    'key86913': 'value10568',
    'key95117': 'value62396',
    'key55646': 'value928',
    'key96627': 'value89492',
    'key87931': 'value16409',
    'key93110': 'value13195',
    'key84095': 'value88857',
},
    {
    'id': 17527482541724,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Christopher Thomas',
    'address': '6586 Crawford Parks Apt. 982\nAndersonville, GA 65826',
    'text': 'Big base seem dinner teacher consider treatment. Sing stop across above care someone or. Writer with heart deal person.',
    'email': 'spencerburke@example.net',
    'phone_number': '(598)359-3893x17478',
    'json': {
    'name': 'Kelly Bender',
    'address': '24448 Jennifer Mount\nJamieshire, NH 66003',
},
    'key90743': 'value52464',
    'key48510': 'value74391',
},
    {
    'id': 17527482541736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Suzanne Hughes',
    'address': '724 Austin Locks Suite 555\nMichaeltown, PA 60995',
    'text': 'Main follow purpose better training. Treat perform early century.\nSafe economic else manager into set. Air positive around condition senior what. Fall field area these.',
    'email': 'kelly15@example.net',
    'phone_number': '(880)866-3946x69394',
    'json': {
    'name': 'Mrs. Diane Carr MD',
    'address': '229 Courtney Pike Suite 732\nLake Richard, DE 17499',
},
    'key88716': 'value51046',
    'key29308': 'value50460',
    'key61742': 'value94313',
    'key14948': 'value43665',
},
    {
    'id': 17527482541747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Kevin Montgomery',
    'address': '36995 Tammy Oval\nEast Michael, OK 41559',
    'text': 'Discover range program miss. Information side food thousand important between story. Travel place forward news relate together late.',
    'email': 'jennifer26@example.com',
    'phone_number': '679.630.6436x81193',
    'json': {
    'name': 'Kenneth Frank',
    'address': '7760 Miller Ford Apt. 798\nNorth Brettbury, IL 29965',
},
    'key21315': 'value15834',
    'key8690': 'value95173',
    'key83674': 'value54080',
    'key66060': 'value22166',
    'key97755': 'value22149',
    'key84751': 'value58385',
    'key84602': 'value6580',
},
    {
    'id': 17527482541757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Tammy Melendez',
    'address': '945 Amber Mountains\nJohnsonstad, NY 72445',
    'text': 'Carry use hospital ago voice.\nSon else huge speech thank personal. Citizen official thank citizen open under can behind. Eye good whose.\nBetween general particular owner debate next defense.',
    'email': 'brianmalone@example.org',
    'phone_number': '+1-843-969-7589x678',
    'json': {
    'name': 'Sara Thomas',
    'address': '09064 Thomas Garden Apt. 762\nChristopherstad, KS 23834',
},
    'key91769': 'value83312',
    'key26123': 'value31101',
},
    {
    'id': 17527482541769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Vanessa Green',
    'address': '5016 Christopher Turnpike\nAshleetown, AK 06325',
    'text': 'Successful happy ten establish build. Paper prove discussion design cup business. Candidate kid learn.\nYoung argue can Democrat. Responsibility institution goal former sit.',
    'email': 'garrett00@example.com',
    'phone_number': '001-412-921-2627x27465',
    'json': {
    'name': 'Virginia Richards',
    'address': 'PSC 8742, Box 5758\nAPO AA 59868',
},
    'key90743': 'value61396',
    'key30409': 'value52922',
    'key96625': 'value12530',
    'key5252': 'value79281',
    'key84507': 'value63672',
    'key32922': 'value89061',
    'key55736': 'value30455',
    'key15714': 'value76990',
},
    {
    'id': 17527482541777,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Samantha Francis',
    'address': '9760 Brittany Union Apt. 353\nWest Charles, CO 86074',
    'text': 'Plant often style provide. Bank body paper understand ahead. Hope such every.\nPerform similar Congress first. End attorney task plan century finish. New any development tree nearly worry.',
    'email': 'vwhite@example.net',
    'phone_number': '+1-696-625-5695x647',
    'json': {
    'name': 'Daniel Barnett',
    'address': '951 Deborah Village\nChristensenchester, MA 86368',
},
    'key50239': 'value44703',
    'key66450': 'value92352',
    'key71878': 'value8308',
    'key55288': 'value75297',
    'key41533': 'value98126',
    'key4614': 'value40815',
},
    {
    'id': 17527482541788,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Nicole Smith',
    'address': '0772 Pena Garden Apt. 661\nMichellechester, SC 33505',
    'text': 'Use close authority let believe student decade draw. Bad pressure enjoy.\nFront between risk identify ready spend. City case real everyone military. Last sell price Congress sure.',
    'email': 'anna44@example.net',
    'phone_number': '+1-239-791-3402x44648',
    'json': {
    'name': 'Desiree Hutchinson',
    'address': '2035 Eric Meadows\nVargashaven, ID 68819',
},
    'key4112': 'value56957',
    'key13129': 'value9736',
    'key55314': 'value69102',
    'key69827': 'value26931',
    'key65578': 'value90001',
    'key13402': 'value62526',
    'key67390': 'value57939',
    'key15354': 'value43748',
    'key65579': 'value37130',
},
    {
    'id': 17527482541798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Elizabeth Bautista',
    'address': '3035 Kimberly Drive\nLeonburgh, WA 32880',
    'text': 'Improve probably baby huge then budget watch. Series make agree capital. Drive at environmental cultural heavy imagine there.\nAbility she according hard. Sort president focus and.',
    'email': 'rebecca94@example.net',
    'phone_number': '718-653-7711',
    'json': {
    'name': 'Debra Thomas',
    'address': '7228 Moran Turnpike Apt. 090\nWest Anne, GU 38001',
},
    'key87402': 'value27751',
    'key87562': 'value69269',
    'key93305': 'value72964',
    'key73399': 'value82429',
},
    {
    'id': 17527482541809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Rebecca Guzman',
    'address': '1850 Bates Turnpike Apt. 814\nHowardhaven, TN 41358',
    'text': 'Girl imagine worry throw some.\nYour idea we rest contain. Suddenly part see style add rather.\nFollow nothing read machine and. Above last late interest because.',
    'email': 'cayala@example.com',
    'phone_number': '226-555-6236x290',
    'json': {
    'name': 'David Ross',
    'address': '401 Dawn Shores\nPort Christianberg, AR 56434',
},
    'key16946': 'value37705',
    'key9266': 'value4716',
},
    {
    'id': 17527482541820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Lisa Willis',
    'address': '8865 Anthony Circle\nEricberg, PW 95530',
    'text': 'Per party focus visit west north throw. Role those president discover just.',
    'email': 'conleydouglas@example.org',
    'phone_number': '001-565-789-9392x0531',
    'json': {
    'name': 'Pamela Robinson',
    'address': '9006 Neal Spring\nEast Lindseyland, MD 15460',
},
    'key10564': 'value79659',
    'key24238': 'value14762',
    'key66274': 'value70244',
},
    {
    'id': 17527482541831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sharon Padilla',
    'address': 'Unit 3666 Box 5127\nDPO AE 60127',
    'text': 'New place front American game detail. Where fire suggest science tend again to. Rich page find for sound character.',
    'email': 'wtodd@example.com',
    'phone_number': '(648)744-4544x314',
    'json': {
    'name': 'Monique Bates',
    'address': '263 Meghan Overpass\nKellyberg, CA 05653',
},
    'key35806': 'value32666',
    'key22815': 'value79786',
    'key97199': 'value6539',
    'key9871': 'value91684',
    'key74445': 'value53397',
    'key51330': 'value39841',
    'key62499': 'value42599',
},
    {
    'id': 17527482541840,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Douglas Moore',
    'address': '1894 Villa Ridge Suite 946\nLake Karenmouth, CT 90384',
    'text': 'New which ten science their policy attack. Join sort another try.\nMemory past order two. Eight close save may best whole.',
    'email': 'zdavis@example.net',
    'phone_number': '001-530-353-4165x3194',
    'json': {
    'name': 'Brandon Castillo',
    'address': '11718 James Summit\nLake Jeffrey, OH 60818',
},
    'key3271': 'value29824',
    'key88245': 'value38654',
    'key13833': 'value50974',
    'key26164': 'value23055',
    'key21256': 'value57742',
    'key30090': 'value81874',
    'key97690': 'value80255',
},
    {
    'id': 17527482541851,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Ryan Allen',
    'address': '41507 Spears Prairie Apt. 161\nPort Corey, ND 55625',
    'text': 'School quickly soon blue accept. Between as from song.\nLaw accept view size. Visit increase city talk full.\nHuge size movement fish. Put side result every somebody lot way. Security even garden fish.',
    'email': 'johnfleming@example.org',
    'phone_number': '+1-697-729-2491x982',
    'json': {
    'name': 'William Bishop',
    'address': '1658 Michael Garden Suite 051\nShafferhaven, AZ 93496',
},
    'key15060': 'value5952',
    'key71151': 'value59260',
    'key20422': 'value86936',
    'key18241': 'value81005',
    'key10972': 'value71606',
    'key75620': 'value59726',
    'key33173': 'value15700',
    'key16611': 'value82447',
},
    {
    'id': 17527482541863,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Debra Chavez',
    'address': '304 Silva Keys\nColintown, AL 83511',
    'text': 'Consider unit minute machine million develop. Wish reduce reason ball amount.\nForm ahead consumer success star worker politics well. Interesting I occur can green church suddenly.',
    'email': 'kendra50@example.com',
    'phone_number': '001-990-504-0535x043',
    'json': {
    'name': 'Allison Clark',
    'address': '933 Roberts Shores Apt. 820\nSouth Anthony, MT 44801',
},
    'key44920': 'value3975',
    'key16358': 'value95097',
    'key49485': 'value76434',
    'key44084': 'value77800',
    'key90082': 'value32821',
    'key96093': 'value42617',
    'key52867': 'value31111',
    'key64598': 'value29460',
    'key39153': 'value75479',
    'key59199': 'value84266',
},
    {
    'id': 17527482541874,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Roger Stark',
    'address': '53538 Michael Pass Suite 887\nNorth Brandi, PR 47806',
    'text': 'Moment whose allow personal trial. Almost style area board happen drug green. Environmental term threat phone those something.',
    'email': 'steven12@example.org',
    'phone_number': '001-557-870-7334x9630',
    'json': {
    'name': 'Micheal Henry',
    'address': '64476 Franco Mall Suite 421\nRachelshire, ME 45083',
},
    'key91655': 'value38548',
    'key10783': 'value60231',
    'key13029': 'value15640',
    'key53026': 'value53435',
},
    {
    'id': 17527482541884,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Eric Glenn',
    'address': '235 Peterson Alley Apt. 967\nWest Stephenburgh, WY 12115',
    'text': 'Garden authority show piece its when face. Because hot hear first play do.\nStock film agent. Describe discussion practice develop memory general.',
    'email': 'kboyd@example.org',
    'phone_number': '(498)386-7240',
    'json': {
    'name': 'Steven Swanson',
    'address': '2216 Andrew Well Suite 155\nNew Hectorland, FM 88621',
},
    'key68452': 'value76291',
    'key10157': 'value60600',
    'key37432': 'value45583',
    'key10546': 'value91742',
    'key28630': 'value29463',
},
    {
    'id': 17527482541895,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Ashley Rodriguez',
    'address': '361 Maureen Views\nKevinbury, NE 28264',
    'text': 'It share price Congress. Almost scientist help interview. No according politics event.\nImagine finally back thought check. President boy attack arrive add society far current.',
    'email': 'joshua45@example.com',
    'phone_number': '001-918-744-0030x7155',
    'json': {
    'name': 'Travis Blevins',
    'address': '4833 Erik Estate Apt. 382\nNew Diana, NJ 94499',
},
    'key58224': 'value98913',
},
    {
    'id': 17527482541905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Jennifer Jackson',
    'address': '4831 Lopez Run\nLeeland, NY 25365',
    'text': 'Feeling professional concern technology central. Clear enter speech accept size most star. Democrat animal finally.\nAlone song cell enjoy chance.',
    'email': 'michelle44@example.com',
    'phone_number': '(464)813-1583',
    'json': {
    'name': 'Diana Pace',
    'address': '008 Sue Field\nLoweryburgh, WI 11686',
},
    'key66672': 'value22207',
    'key9099': 'value22652',
    'key82282': 'value15403',
    'key60351': 'value27806',
    'key79177': 'value65563',
    'key24238': 'value79455',
},
    {
    'id': 17527482541916,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Ryan Mosley',
    'address': '9146 Wu Turnpike\nHallmouth, SC 90997',
    'text': 'Best who sister similar decade parent night. Medical raise realize account. At perform discuss evidence avoid herself concern. Information similar fish several six indicate.',
    'email': 'susanhayden@example.org',
    'phone_number': '001-638-709-8389',
    'json': {
    'name': 'John Williams',
    'address': '23606 Matthew Lodge\nLake Brittany, WY 55324',
},
    'key46108': 'value14637',
},
    {
    'id': 17527482541928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Mary Brown',
    'address': '3423 Brian Forks\nEast Sharonton, DE 83124',
    'text': 'Arrive land perhaps if reflect notice marriage. Late minute someone take know lawyer simple. Marriage game my beyond.',
    'email': 'clarkchristopher@example.net',
    'phone_number': '299-859-1545',
    'json': {
    'name': 'Erica Bennett',
    'address': '334 Nunez Pike Suite 547\nOrtizbury, IN 01322',
},
    'key90512': 'value23406',
    'key78386': 'value95067',
    'key90882': 'value35131',
    'key74008': 'value81150',
    'key20030': 'value19882',
    'key86629': 'value49909',
    'key9609': 'value6965',
},
    {
    'id': 17527482541939,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Linda Arnold',
    'address': '7705 Jordan Summit Suite 722\nDavisside, MS 76653',
    'text': 'Me party through. Case media six security every interview situation.\nCatch require appear job enter chance.\nName parent author. Imagine always media often nothing. Never account laugh whether.',
    'email': 'newmanbrooke@example.org',
    'phone_number': '+1-942-609-2715x96599',
    'json': {
    'name': 'Andrea Williams',
    'address': '8547 Gabriel Lodge Apt. 357\nMejiaborough, NE 76138',
},
    'key29485': 'value60681',
    'key21289': 'value40252',
    'key94644': 'value30129',
    'key31192': 'value16104',
    'key14708': 'value80701',
    'key74947': 'value67361',
    'key75228': 'value79829',
    'key70612': 'value10048',
    'key3234': 'value68143',
    'key84869': 'value93052',
},
    {
    'id': 17527482541951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'David Johnson',
    'address': '998 Chad Motorway\nNorth Donna, IA 96263',
    'text': 'Team near agree animal beat. Generation who small house team but. Behavior after ten increase serious.',
    'email': 'parksthomas@example.net',
    'phone_number': '+1-280-775-1503',
    'json': {
    'name': 'Beth Ford DDS',
    'address': '1266 Clark Neck\nAdamsshire, OK 25160',
},
    'key15774': 'value18202',
},
    {
    'id': 17527482541963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Susan Fuller',
    'address': '0589 Dean Ridges\nNorth Joshuachester, KS 12267',
    'text': 'Worry maybe rock final save with firm maintain. Nation describe least begin begin business understand.',
    'email': 'kimberly74@example.org',
    'phone_number': '(646)982-1437',
    'json': {
    'name': 'Shawn Wilson',
    'address': '4178 Alicia Roads Apt. 887\nGillespiechester, TX 89734',
},
    'key88383': 'value84652',
    'key28243': 'value83099',
    'key99983': 'value85274',
    'key45568': 'value80832',
    'key82308': 'value13387',
    'key2849': 'value93121',
    'key83464': 'value74569',
},
    {
    'id': 17527482541973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Jennifer Kline',
    'address': '4937 Jacqueline Loaf Suite 140\nRayberg, IN 36487',
    'text': 'From important race though and eat field. Class artist small hold realize step big. Baby attention this on law yard.',
    'email': 'rhernandez@example.net',
    'phone_number': '+1-875-461-0102x9842',
    'json': {
    'name': 'Jasmine Wise',
    'address': 'USNV Valentine\nFPO AA 96614',
},
    'key50606': 'value48707',
    'key85070': 'value83646',
    'key15693': 'value73373',
},
    {
    'id': 17527482541983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Jill Wright',
    'address': '85241 Christian Summit\nLake Allenchester, TN 25587',
    'text': 'Specific dark administration. Leader high article democratic open. Specific until do PM officer before.\nProtect entire she third door other alone.',
    'email': 'karajohnston@example.com',
    'phone_number': '443-235-2234',
    'json': {
    'name': 'Trevor Perez',
    'address': '8540 Jackson Plaza Apt. 024\nNew Yvonne, NC 66942',
},
    'key4443': 'value22662',
    'key16896': 'value48810',
    'key16287': 'value78110',
},
    {
    'id': 17527482541994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Troy Guzman',
    'address': '116 Fields Forest\nBeckerhaven, HI 41848',
    'text': 'Action decade piece tough. Instead cup help live. National phone president artist upon.\nRun debate practice toward never especially five. Society book style difference decade main.',
    'email': 'uarnold@example.net',
    'phone_number': '705-287-5240',
    'json': {
    'name': 'Kerry Burke',
    'address': '38978 Fuentes Fork Apt. 428\nEast Lorifurt, MH 45548',
},
    'key85399': 'value59142',
    'key34334': 'value85040',
    'key43877': 'value11680',
},
    {
    'id': 17527482542004,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Dr. David Jones',
    'address': '7335 Frances Ports Suite 368\nStewartshire, NV 80676',
    'text': 'Fine military their bank. Use return until. Recognize happy house week rate including.\nGreat everything alone while thing. Business here factor effort what involve.',
    'email': 'leejoseph@example.net',
    'phone_number': '+1-906-760-5761x06531',
    'json': {
    'name': 'Stephen Gibson',
    'address': '54203 Gates Squares\nLake Kaylafurt, HI 05574',
},
    'key26813': 'value83373',
    'key8275': 'value61829',
},
    {
    'id': 17527482542016,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Nathaniel Lara',
    'address': '369 Dickson Harbor\nBrentborough, VT 52469',
    'text': 'Inside popular ball message too show. Stop sit everybody ready scene. Another economy final hand hundred who subject.\nRemain boy fast western. Letter show up list finally.',
    'email': 'hendersonrachael@example.com',
    'phone_number': '(698)991-6424x1960',
    'json': {
    'name': 'Luis Jones',
    'address': '139 Watson Lodge Suite 946\nEast Lisaburgh, AK 36470',
},
    'key58056': 'value52992',
},
    {
    'id': 17527482542028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Brandy Hill',
    'address': 'PSC 3442, Box 5342\nAPO AE 05065',
    'text': 'Her brother star. Require wrong until everyone Mr cultural.\nFall everybody late view believe admit see. Face line me parent.\nBuy stand great. Human hear bring worry share that visit.',
    'email': 'pmack@example.net',
    'phone_number': '(627)640-3459',
    'json': {
    'name': 'Anthony Matthews',
    'address': '280 Cross Hills\nWalshfurt, WV 84773',
},
    'key68554': 'value62337',
},
    {
    'id': 17527482542038,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Dawn Schwartz',
    'address': '1381 Martin Fort\nNorth Denise, MO 70100',
    'text': 'According growth camera institution answer notice begin. All from former stage trip recent. Challenge deal agent data main policy director opportunity.',
    'email': 'david37@example.org',
    'phone_number': '576-975-6705x560',
    'json': {
    'name': 'Mary Gonzalez',
    'address': '60496 Carr Spring Apt. 190\nSouth Leslieburgh, MO 80185',
},
    'key65315': 'value11933',
    'key30426': 'value14691',
    'key99636': 'value87287',
    'key83065': 'value40748',
    'key2719': 'value15150',
    'key18160': 'value36168',
    'key73828': 'value33890',
    'key82824': 'value37448',
    'key31386': 'value95680',
},
    {
    'id': 17527482542048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'David White',
    'address': '74590 Kylie Knolls Apt. 187\nGarnerburgh, PW 86453',
    'text': 'Skin give prove. Detail look network after. Exactly particular cause ten use put.',
    'email': 'whutchinson@example.com',
    'phone_number': '+1-922-767-8769',
    'json': {
    'name': 'Erin Douglas',
    'address': '454 Joseph Plain\nBrianshire, VT 34777',
},
    'key39400': 'value50726',
},
    {
    'id': 17527482542059,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Elizabeth Hays',
    'address': '47737 Gonzalez Locks\nGarrisonview, IA 02784',
    'text': 'As someone film know.\nStandard serious condition finally white than. Magazine attorney method positive.',
    'email': 'ronaldcollins@example.com',
    'phone_number': '766-409-2895x60523',
    'json': {
    'name': 'Craig Sherman',
    'address': '1533 Donald Islands\nNew Emilyport, NM 44080',
},
    'key55890': 'value82168',
    'key40284': 'value51261',
    'key13004': 'value46235',
    'key13720': 'value99449',
    'key38604': 'value98208',
    'key64297': 'value65828',
    'key2793': 'value51823',
    'key30497': 'value32268',
    'key70059': 'value43422',
    'key97673': 'value20564',
},
    {
    'id': 17527482542070,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Mary Reyes',
    'address': '7256 Golden Springs\nSouth Garystad, ND 17983',
    'text': 'Drug alone interesting operation.\nDemocratic wrong anything bad back. Series myself quite far this. Cold such magazine skin wife mean budget.',
    'email': 'coreyjones@example.net',
    'phone_number': '791-523-7082x74882',
    'json': {
    'name': 'Rachel Craig',
    'address': '76015 Graham Pines Suite 995\nLake Denisestad, DC 38958',
},
    'key39962': 'value84372',
    'key89718': 'value85888',
    'key35790': 'value11783',
    'key8795': 'value99172',
    'key14331': 'value7989',
    'key92121': 'value18088',
    'key33512': 'value31867',
},
    {
    'id': 17527482542082,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Laurie Robbins',
    'address': '39350 Cory Plains Suite 369\nLake Jessefurt, DC 25280',
    'text': 'Positive hair wear everybody to strategy enough. Contain others plan tax fill. Country myself beautiful hear finish itself.\nWeight story process be he. Usually hold story up movement compare.',
    'email': 'loganleslie@example.org',
    'phone_number': '2116232371',
    'json': {
    'name': 'Jessica Butler',
    'address': '21832 Ellis Falls\nCherylmouth, OK 13785',
},
    'key30484': 'value11231',
    'key81836': 'value31088',
    'key2770': 'value92246',
    'key7489': 'value1452',
    'key15046': 'value51618',
},
    {
    'id': 17527482542094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Janice Osborn',
    'address': '27681 Tina Road\nWest Christopherhaven, MD 19150',
    'text': 'Into cause try.\nRespond animal wear class road allow nearly. Always full medical ok.\nRather threat walk tax show. Majority oil know dream attention. Sport own crime industry ready somebody on.',
    'email': 'jdavis@example.com',
    'phone_number': '428-586-9837x63295',
    'json': {
    'name': 'Martha Howe',
    'address': 'PSC 5515, Box 9900\nAPO AA 30147',
},
    'key76527': 'value66839',
    'key39333': 'value73536',
    'key80864': 'value41360',
    'key35516': 'value28197',
    'key82271': 'value89534',
    'key75310': 'value18223',
    'key79808': 'value74013',
    'key74654': 'value61047',
    'key65499': 'value39356',
    'key92699': 'value49474',
},
    {
    'id': 17527482542103,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Marie Shaw',
    'address': '6002 Lopez Divide\nWatsonstad, MH 69287',
    'text': 'Chair matter section area here interest yourself suffer. Face beyond culture yet likely democratic. Consider share than make.\nWhy take however nature. We reveal old position.',
    'email': 'thomas41@example.net',
    'phone_number': '593.721.2025',
    'json': {
    'name': 'Wendy Salinas',
    'address': '56478 Reyes Walk Suite 938\nThorntonton, GU 75581',
},
    'key65841': 'value58231',
    'key2946': 'value65782',
    'key89492': 'value35019',
    'key92667': 'value40737',
    'key26404': 'value88077',
    'key96638': 'value17730',
},
    {
    'id': 17527482542114,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'James Williams',
    'address': '56048 Katherine Port\nRogerston, GU 97608',
    'text': 'Herself scientist stock range. Ready such she brother human just.\nLeast someone beyond so later late. Rather whom tree debate tax debate.',
    'email': 'morrisapril@example.org',
    'phone_number': '894.802.7129x04875',
    'json': {
    'name': 'Kristi Brown',
    'address': '62059 Lopez Station Apt. 919\nMackview, AK 09929',
},
    'key65181': 'value22407',
    'key9991': 'value18812',
    'key3451': 'value94920',
},
    {
    'id': 17527482542126,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Kevin Hicks',
    'address': '6203 Wilson Lodge Suite 221\nKathrynview, TN 35679',
    'text': 'Color kind far serve ten speak stop.\nAlthough former memory else early part window. Pay tend system region north out collection. Chair sit than what market it.',
    'email': 'suzanneparker@example.org',
    'phone_number': '726.293.4694x196',
    'json': {
    'name': 'Christine Roberson',
    'address': '3009 Tracy Union\nWest Christophermouth, TX 16029',
},
    'key9697': 'value26263',
    'key63692': 'value19072',
    'key18215': 'value17531',
    'key9311': 'value86513',
},
    {
    'id': 17527482542137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Mrs. Karen Padilla',
    'address': '25076 Jacob Shoals\nBradleyshire, NM 52742',
    'text': 'Today continue send but security everybody interest. Certain dog game natural green recent.',
    'email': 'bakerpatricia@example.org',
    'phone_number': '6364225659',
    'json': {
    'name': 'Haley Rodriguez',
    'address': '692 Crawford Centers Apt. 558\nTammybury, NY 60905',
},
    'key31673': 'value44342',
    'key27242': 'value91211',
    'key79389': 'value86436',
    'key14977': 'value77145',
    'key38493': 'value39065',
    'key84121': 'value258',
    'key58857': 'value69400',
    'key49747': 'value43284',
},
    {
    'id': 17527482542149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Jordan Allen',
    'address': '9517 Alicia Drive Apt. 083\nPerkinsville, CO 31344',
    'text': 'Item nearly wrong Congress man experience will. Million study person system sea.\nTeacher likely perhaps tough. Effect represent although. Majority purpose first such. Crime mouth book player policy.',
    'email': 'thomas96@example.net',
    'phone_number': '515-374-0927',
    'json': {
    'name': 'Katie Wolf',
    'address': '606 Patty Fork\nNorth Kayla, SD 40840',
},
    'key51571': 'value52697',
    'key86253': 'value22988',
},
    {
    'id': 17527482542159,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Tracy Rodriguez',
    'address': '964 Tammy Creek Suite 814\nEast Williamfort, AR 21761',
    'text': 'Practice almost enter almost seven whether. Pattern paper traditional talk.\nGas group husband watch that. Quality recently soldier. Left compare school late series.',
    'email': 'curtismaynard@example.net',
    'phone_number': '575.809.3888',
    'json': {
    'name': 'Laura Lynch',
    'address': '281 Karen Crossing\nPattersonhaven, GA 48770',
},
    'key75894': 'value6425',
    'key65539': 'value77731',
    'key80921': 'value69421',
    'key18171': 'value40897',
    'key13960': 'value79466',
    'key20846': 'value45889',
    'key32711': 'value72629',
},
    {
    'id': 17527482542171,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Lori Villegas',
    'address': '7195 Zachary Mountain\nNorth Kimberlyfort, CO 05241',
    'text': 'This box watch foot baby pick including step. Like movement agent prevent what station. Join service just feel someone happy.',
    'email': 'cingram@example.com',
    'phone_number': '893.632.7029x6914',
    'json': {
    'name': 'Michael Price',
    'address': '669 Corey Run Apt. 219\nWest Gregoryview, NY 69876',
},
    'key48438': 'value43917',
    'key52418': 'value818',
},
    {
    'id': 17527482542181,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Dawn Moore',
    'address': '16371 Johnston Grove Apt. 173\nNorth Lisa, TX 25217',
    'text': 'Street sound any moment her. Staff mother could statement.\nHair give particularly consider everything it. Respond several once offer on so medical watch. Approach before institution shoulder.',
    'email': 'browningchristopher@example.org',
    'phone_number': '607-361-9142x06630',
    'json': {
    'name': 'Regina Robinson',
    'address': '5696 April Harbor Suite 979\nNorth Jeffrey, FM 55932',
},
    'key47667': 'value34623',
    'key6793': 'value22153',
},
    {
    'id': 17527482542193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Jason Torres',
    'address': '25283 Grant Crossing\nAnthonyfort, OH 12256',
    'text': 'As what indeed ever teach seem quality. Only drug floor both situation difficult seem south.',
    'email': 'baileymary@example.com',
    'phone_number': '(906)905-2132',
    'json': {
    'name': 'Andrew Boyle',
    'address': '08703 Thomas Way\nPatrickton, AL 76712',
},
    'key96617': 'value27732',
    'key96716': 'value28625',
    'key17303': 'value72108',
    'key78800': 'value98550',
    'key48043': 'value65279',
    'key9802': 'value8350',
    'key47899': 'value47892',
},
    {
    'id': 17527482542204,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Christopher Nguyen',
    'address': '726 Day Spurs Suite 216\nPatrickbury, TN 49528',
    'text': 'Teach public be wish suggest pay name. Themselves work physical stage run. Million according piece run set manage ago others.',
    'email': 'hwilliams@example.net',
    'phone_number': '+1-359-209-0099x80696',
    'json': {
    'name': 'Nicholas Aguilar',
    'address': '2276 Emily Trail\nBowersburgh, WA 47578',
},
    'key42292': 'value47733',
    'key45907': 'value55593',
    'key32775': 'value272',
    'key35521': 'value24297',
    'key94515': 'value811',
    'key50890': 'value42849',
},
    {
    'id': 17527482542216,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Amber Edwards',
    'address': 'PSC 7067, Box 3978\nAPO AE 63094',
    'text': 'Where sport real improve beat a skin. Learn when contain deal.\nAdult side certainly particular until executive management.',
    'email': 'montgomeryeric@example.org',
    'phone_number': '+1-270-536-2598',
    'json': {
    'name': 'Victoria Duran',
    'address': '5665 Knight Alley Apt. 039\nMelissachester, PR 57371',
},
    'key19729': 'value53567',
    'key52828': 'value11526',
    'key30525': 'value23078',
    'key52673': 'value24094',
    'key69824': 'value88492',
    'key45209': 'value11445',
    'key90277': 'value51105',
    'key15966': 'value88156',
    'key17406': 'value74244',
},
    {
    'id': 17527482542225,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Sean Cervantes',
    'address': '6782 Michael Wells Suite 430\nMaldonadotown, SC 56631',
    'text': 'Early budget bad somebody campaign. Style effort generation across.\nClearly easy mouth green. Laugh but girl security add good help yard.\nRange tax sure section. National main eight town kind budget.',
    'email': 'xbrown@example.net',
    'phone_number': '+1-425-304-5970',
    'json': {
    'name': 'John Scott',
    'address': '68076 Abigail Unions Apt. 474\nBrandonfort, FL 59526',
},
    'key24218': 'value97257',
    'key31538': 'value89231',
    'key6363': 'value19292',
    'key9393': 'value9109',
    'key1330': 'value5051',
    'key7351': 'value12109',
    'key22685': 'value14294',
    'key74707': 'value23834',
    'key44746': 'value89310',
},
    {
    'id': 17527482542236,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Jenny Moore',
    'address': '5454 Williams Heights Apt. 556\nAdamside, ME 62178',
    'text': 'Season knowledge story claim possible. Any garden night least science. Approach indicate official bill grow large role media.\nAttention allow base oil girl. Science assume bring lead message.',
    'email': 'rebekahbray@example.net',
    'phone_number': '943-621-5557',
    'json': {
    'name': 'Beth Ramirez',
    'address': '23262 Singleton Union Apt. 476\nLake Tylerview, CO 46236',
},
    'key34299': 'value27995',
    'key66869': 'value21403',
    'key63594': 'value70013',
    'key52556': 'value74852',
},
    {
    'id': 17527482542248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Connie Johnson',
    'address': '3158 Monroe Estate Suite 344\nEast Tammyhaven, NH 42570',
    'text': 'Environmental computer throughout. High number second central. Fast more result worker science ability.\nDifference book identify daughter both public yard. Husband common pay medical officer.',
    'email': 'brandydrake@example.org',
    'phone_number': '001-383-389-6270',
    'json': {
    'name': 'Mark Romero',
    'address': '282 Michael Trafficway Suite 010\nWest Angelfort, PW 02570',
},
    'key98454': 'value25328',
    'key71010': 'value20230',
    'key45235': 'value66196',
    'key73351': 'value63263',
    'key55432': 'value62566',
},
    {
    'id': 17527482542259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Melissa Rodriguez',
    'address': '307 Williams Union\nPort Samuelburgh, UT 21757',
    'text': 'Range hour tonight stay maybe present no. Include bring star finally market whose parent raise.\nBank today many reflect follow. Movement talk according animal yourself drug.',
    'email': 'martinjennifer@example.org',
    'phone_number': '+1-744-343-9078',
    'json': {
    'name': 'Mr. Louis Griffith',
    'address': '74261 Glenn Ranch Apt. 337\nKarenview, UT 10146',
},
    'key7651': 'value45497',
    'key14662': 'value53440',
},
    {
    'id': 17527482542271,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Michael Phillips',
    'address': '62727 Courtney Extensions\nPort Carla, MD 59367',
    'text': 'Any like tell list way. Consumer hard catch question. Rate site degree treat.\nHer herself medical whole. Him deep attention skill painting history.',
    'email': 'michaelbradshaw@example.net',
    'phone_number': '001-892-579-5498x546',
    'json': {
    'name': 'Stephen Williams',
    'address': '4116 Braun Station\nWest Angelica, PA 71219',
},
    'key5208': 'value8202',
    'key96940': 'value62211',
    'key80560': 'value9545',
    'key11395': 'value3901',
    'key24246': 'value78340',
    'key49613': 'value36644',
    'key86960': 'value25608',
    'key81549': 'value78083',
    'key24969': 'value47763',
},
    {
    'id': 17527482542282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Frank Potter',
    'address': 'PSC 3345, Box 5191\nAPO AP 87524',
    'text': 'War positive player smile. Kid treatment hundred manager. Among play phone PM.\nSell black ability tend business right chair. Either cold century player.',
    'email': 'eric22@example.com',
    'phone_number': '001-887-229-3388x41897',
    'json': {
    'name': 'Jose Taylor',
    'address': 'Unit 5025 Box 1780\nDPO AE 46776',
},
    'key72053': 'value26876',
    'key87227': 'value56527',
},
    {
    'id': 17527482542289,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Cindy Lopez',
    'address': 'USNV Sanchez\nFPO AA 92452',
    'text': 'Note blood sing money sister. Blood assume person. Public me follow these onto resource foreign.',
    'email': 'billysims@example.net',
    'phone_number': '001-654-336-0573x547',
    'json': {
    'name': 'Barbara Chandler',
    'address': '50753 Jennifer Pine\nNorth Daniel, WV 25948',
},
    'key4599': 'value48204',
    'key49760': 'value57240',
    'key93206': 'value70258',
    'key26513': 'value90417',
    'key54682': 'value6939',
    'key23902': 'value23108',
    'key7677': 'value70392',
    'key82918': 'value61832',
    'key44134': 'value93977',
    'key24177': 'value7747',
},
    {
    'id': 17527482542299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Matthew Hill',
    'address': '187 Nelson Gateway Suite 469\nLoriville, NJ 52894',
    'text': 'Conference land away organization it. Past buy away century computer rather meet country.\nIncrease able receive. Skin feel also.',
    'email': 'jessicadiaz@example.org',
    'phone_number': '351-803-0587x786',
    'json': {
    'name': 'Anthony Moore',
    'address': '402 Meyer Mission\nLake Evanport, VA 08775',
},
    'key27951': 'value16653',
},
    {
    'id': 17527482542310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Nathaniel Townsend',
    'address': 'PSC 3797, Box 9983\nAPO AE 31424',
    'text': 'Subject international various. Explain offer staff it direction. Catch trip about issue live.\nGrow investment we sell no must. Over term fight.',
    'email': 'walkermichael@example.net',
    'phone_number': '+1-205-401-4109x8172',
    'json': {
    'name': 'Jennifer Coleman',
    'address': '1380 Taylor Shores\nLake Nicolechester, IN 66430',
},
    'key19156': 'value23689',
    'key33036': 'value45384',
    'key75750': 'value25354',
},
    {
    'id': 17527482542319,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Ms. Jessica Nunez',
    'address': '5362 Downs Radial\nNorth Jason, MH 96238',
    'text': 'Staff attention least probably. Since site something. All purpose why artist. Lawyer poor threat sea manager.',
    'email': 'ericramirez@example.net',
    'phone_number': '001-358-253-1859x24320',
    'json': {
    'name': 'Danielle Valentine',
    'address': '1381 Edwin Canyon\nClaudiaville, GU 97941',
},
    'key73911': 'value55150',
    'key36155': 'value1379',
    'key76191': 'value48792',
},
    {
    'id': 17527482542330,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Stephanie Gonzalez',
    'address': '21593 Garcia Hill Apt. 545\nSmithville, PA 92930',
    'text': 'During walk case class sell art. Expect market authority spend actually. Move fast improve.\nCitizen word nice this lose citizen field. Example stand look open surface almost majority community.',
    'email': 'holson@example.com',
    'phone_number': '(798)310-0551',
    'json': {
    'name': 'Julie Parks',
    'address': '32727 Rose Fort Suite 515\nRobertside, SC 46964',
},
    'key88801': 'value81520',
    'key54905': 'value55371',
    'key12853': 'value86737',
    'key90016': 'value3697',
    'key41158': 'value16370',
    'key81923': 'value26555',
    'key99314': 'value50550',
    'key17192': 'value16079',
},
    {
    'id': 17527482542342,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Amy Stewart',
    'address': '278 Flores Overpass\nNicolebury, OR 14180',
    'text': 'Now difficult another back relationship large. Way million art. Member during lawyer tonight participant mouth.\nHalf value assume. Carry win anything today forward issue magazine.',
    'email': 'brittany04@example.com',
    'phone_number': '+1-275-526-8867x04841',
    'json': {
    'name': 'Sherri Ray',
    'address': '727 Wendy Brooks Suite 300\nWest Robinshire, PR 57552',
},
    'key42221': 'value72444',
    'key22208': 'value54105',
    'key54913': 'value46090',
},
    {
    'id': 17527482542352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Lee Sandoval',
    'address': '010 Leah Vista Apt. 138\nLake Cody, MT 11756',
    'text': 'Four will trip phone. Gun remember field whose.\nRelationship compare meeting store must mean once.\nSeries girl house. Main much trial vote. Moment scene little then force prepare game.',
    'email': 'marquezmichael@example.com',
    'phone_number': '809-398-5461x02921',
    'json': {
    'name': 'Christopher Ross',
    'address': '7254 Darin Extensions Suite 099\nEast Michaelview, MO 35671',
},
    'key69243': 'value25667',
    'key91986': 'value97453',
    'key86642': 'value91772',
    'key99178': 'value55870',
},
    {
    'id': 17527482542364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Alyssa Tate',
    'address': '52374 Jasmine Mall\nPamelafort, NY 12525',
    'text': 'Especially popular really green detail stage. Others board education job ask offer hospital. Best attention option improve become oil.',
    'email': 'moodychristina@example.org',
    'phone_number': '783.537.1194x63726',
    'json': {
    'name': 'Mark Patterson',
    'address': '51155 Karen Falls\nMichellebury, UT 49226',
},
    'key84530': 'value10146',
    'key227': 'value76411',
    'key65147': 'value5600',
    'key37735': 'value82938',
    'key68385': 'value68395',
},
    {
    'id': 17527482542375,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Benjamin Snyder',
    'address': '358 Collins Plaza Apt. 033\nWest Emilyberg, SD 26189',
    'text': 'Lead factor indeed establish. Among public character will citizen door season. Area traditional drug shake.',
    'email': 'howardkelly@example.net',
    'phone_number': '001-774-538-0818',
    'json': {
    'name': 'Jillian Stewart',
    'address': 'Unit 7349 Box 8863\nDPO AE 70072',
},
    'key31222': 'value71649',
    'key77350': 'value90028',
    'key17182': 'value35187',
},
    {
    'id': 17527482542384,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Amanda Carlson',
    'address': '32771 Michael Road Suite 325\nEast Heather, TX 23661',
    'text': 'Behavior race drop. Decision writer glass commercial father draw able. Kitchen it conference international ball.',
    'email': 'jacob92@example.net',
    'phone_number': '936.774.2038x9660',
    'json': {
    'name': 'Grace Vazquez',
    'address': '346 Rachel Roads\nRoseport, VT 25204',
},
    'key11044': 'value67497',
    'key18290': 'value73541',
    'key99865': 'value1357',
    'key9837': 'value81107',
    'key9505': 'value84793',
    'key75647': 'value63588',
    'key10282': 'value29775',
    'key98125': 'value23039',
    'key48646': 'value20548',
    'key83965': 'value99019',
},
    {
    'id': 17527482542394,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Jenna Andrade',
    'address': '1696 Brooke Land\nEast Steven, MH 91177',
    'text': 'Head structure above per win. Son girl relate. Right night action set prepare within.\nEast expect baby more doctor born or. Seem people his identify region onto seem. Talk score at road four nation.',
    'email': 'hector14@example.net',
    'phone_number': '+1-529-896-7303x545',
    'json': {
    'name': 'Brenda Phillips',
    'address': '4090 Lindsay Crescent\nMillerfurt, MS 21800',
},
    'key84450': 'value49786',
    'key95148': 'value17588',
    'key5344': 'value77714',
    'key28658': 'value47443',
    'key67732': 'value83977',
    'key22452': 'value73521',
    'key33045': 'value85458',
    'key30247': 'value5216',
    'key42170': 'value2766',
},
    {
    'id': 17527482542405,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Thomas Cruz',
    'address': '0209 Brooke Crest\nDylanfurt, TX 65138',
    'text': 'Every Democrat law thousand. Enough course hear ever evening.\nSoon cover difference event also. Sit school out pretty least eat. Quality win measure three arrive but.',
    'email': 'lreyes@example.org',
    'phone_number': '815.950.9940',
    'json': {
    'name': 'Eric Armstrong',
    'address': '095 Stout Mountain\nLake Alan, FL 60351',
},
    'key18521': 'value31678',
    'key38810': 'value92169',
    'key86570': 'value52426',
    'key91536': 'value68373',
},
    {
    'id': 17527482542415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'William Phillips',
    'address': '67894 Carolyn Circle\nNew Adam, AR 88539',
    'text': 'Team push entire me. Whether nearly issue total your beautiful letter.\nWould civil indeed key. Win within red of else when when. Baby over involve leader real difficult necessary.',
    'email': 'kramerjoshua@example.net',
    'phone_number': '001-664-314-1088x223',
    'json': {
    'name': 'Zachary Maldonado',
    'address': '1901 Amy Mountain\nRobinsonmouth, AR 19310',
},
    'key73351': 'value77820',
    'key12080': 'value96358',
    'key41025': 'value57970',
    'key88458': 'value1510',
    'key29452': 'value85214',
    'key405': 'value34686',
    'key84927': 'value57741',
    'key30673': 'value78524',
},
    {
    'id': 17527482542426,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Jamie Harrison',
    'address': '5972 Martinez Loop Suite 469\nNorth Robert, OK 88289',
    'text': 'Activity onto meeting program enough. Choose without term standard road response company. Direction form either look trouble whose.',
    'email': 'marilyn91@example.com',
    'phone_number': '578-871-7217x84698',
    'json': {
    'name': 'George Smith',
    'address': 'USNS Boone\nFPO AE 71583',
},
    'key23521': 'value27424',
    'key48470': 'value79122',
    'key9611': 'value83407',
},
    {
    'id': 17527482542436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Cynthia Bright',
    'address': '73193 John Inlet\nGeorgeside, PW 29449',
    'text': 'Director official keep expect teach. Can else determine specific. Consumer increase letter hold.\nAsk skin couple agent dark week. Left through structure we stop. Turn have serve.',
    'email': 'sgill@example.org',
    'phone_number': '+1-888-648-1291x9014',
    'json': {
    'name': 'Matthew Soto',
    'address': '49888 Marquez Circles\nHillport, AR 90303',
},
    'key19757': 'value96177',
    'key56385': 'value30568',
    'key7412': 'value16370',
    'key24394': 'value11900',
    'key91773': 'value32869',
    'key24396': 'value93846',
    'key2218': 'value33984',
    'key76334': 'value21416',
    'key1845': 'value89476',
    'key85537': 'value74282',
},
    {
    'id': 17527482542447,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Nicole Fitzgerald',
    'address': '3986 Smith Lane Apt. 638\nPort Katherinetown, WY 52547',
    'text': 'Data would speech spend look cold. Management him natural throw.\nDo language poor late. Than modern specific skill during leave style. Piece it now book vote send degree.',
    'email': 'sanchezzachary@example.org',
    'phone_number': '5679331706',
    'json': {
    'name': 'Stephanie Guzman',
    'address': '215 Kimberly Island\nEast Brendafort, IL 45326',
},
    'key76546': 'value47307',
    'key69211': 'value90447',
    'key79239': 'value24541',
},
    {
    'id': 17527482542458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Tony Garcia',
    'address': '9141 Darrell Way\nDanielland, LA 17826',
    'text': 'Condition also never. Hotel cause again work. Draw approach teacher. There news film including.',
    'email': 'anna12@example.net',
    'phone_number': '(620)362-4594x236',
    'json': {
    'name': 'Kenneth Sanders',
    'address': '8358 Whitaker Rest Apt. 255\nByrdfort, AS 17001',
},
    'key46657': 'value56931',
    'key14989': 'value23755',
    'key40008': 'value11793',
    'key37285': 'value19286',
    'key81125': 'value65441',
    'key50588': 'value82233',
},
    {
    'id': 17527482542469,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Teresa Mosley',
    'address': '93579 Malone Summit\nPort Micheleville, WY 38121',
    'text': 'Sit season make first old morning talk. Price speech at responsibility determine. Exist my position few easy least paper.',
    'email': 'victor61@example.org',
    'phone_number': '744-695-8774x4877',
    'json': {
    'name': 'Charles Williams',
    'address': '60754 Gray Stream Suite 875\nJohnton, PW 68388',
},
    'key90261': 'value5193',
    'key79675': 'value7250',
    'key40637': 'value81113',
    'key38825': 'value96473',
    'key7102': 'value42445',
    'key87187': 'value15046',
    'key57767': 'value64697',
    'key72877': 'value52799',
    'key35342': 'value81803',
    'key42586': 'value68488',
},
    {
    'id': 17527482542479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Patricia Roberts',
    'address': 'USNS Tran\nFPO AE 78982',
    'text': 'Have night leave agree art. Parent race network.\nAllow media evidence age notice. Late table lose billion law trouble mention.',
    'email': 'matthewhicks@example.net',
    'phone_number': '707-698-3185',
    'json': {
    'name': 'Susan Casey DDS',
    'address': '4355 Michael Place\nNew Jayburgh, NC 12640',
},
    'key42676': 'value3272',
    'key60016': 'value34594',
    'key31555': 'value45890',
    'key55340': 'value43379',
    'key52785': 'value15897',
    'key50669': 'value57913',
},
    {
    'id': 17527482542489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Stuart Castaneda',
    'address': '10345 Gray Mission Apt. 943\nNorth Amyberg, MT 94449',
    'text': 'South race south meeting PM feeling cell. Sell such spring hundred training media appear.\nSpeech risk choose administration arm ball. Fast parent tree leg.',
    'email': 'mendozasara@example.net',
    'phone_number': '(607)479-9525',
    'json': {
    'name': 'Tammy Johnson',
    'address': 'USCGC Smith\nFPO AA 32813',
},
    'key46578': 'value57611',
    'key49371': 'value14092',
    'key47115': 'value87398',
    'key6045': 'value14354',
},
    {
    'id': 17527482542499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Angela Villanueva',
    'address': 'PSC 1292, Box 1927\nAPO AA 43212',
    'text': 'Near whether hundred seem wonder want any. Knowledge strong church. Poor enough court spring suggest.',
    'email': 'kelsey20@example.com',
    'phone_number': '651.820.9378x8381',
    'json': {
    'name': 'Michael Smith',
    'address': '487 Greene Forge Apt. 870\nNorth Christinaside, DC 38154',
},
    'key5617': 'value25115',
    'key43262': 'value47746',
    'key23632': 'value48796',
    'key80313': 'value57023',
    'key23955': 'value19925',
    'key15877': 'value21650',
},
    {
    'id': 17527482542508,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Charles Wilson',
    'address': '47905 West Divide Apt. 449\nYoungmouth, DC 89982',
    'text': 'Require resource teach far above American world. Trial black lawyer role true area general.',
    'email': 'krhodes@example.net',
    'phone_number': '+1-545-601-7180x516',
    'json': {
    'name': 'Jason Boyer',
    'address': '0938 Martinez Isle\nSouth Anna, PR 63990',
},
    'key41261': 'value26583',
    'key84348': 'value41509',
},
    {
    'id': 17527482542518,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Brenda Robinson',
    'address': '285 Barnett Harbor Apt. 763\nNorth Whitney, TN 52934',
    'text': 'Piece result decide property. Special board away maybe stop car.\nFor green wall small beat dream under company. Voice soldier three suddenly. Worker people pull school.',
    'email': 'djohnson@example.com',
    'phone_number': '+1-214-673-5309x601',
    'json': {
    'name': 'Catherine Phillips',
    'address': '5096 Zoe Ranch Suite 470\nWest Jennifer, LA 27490',
},
    'key80155': 'value17191',
},
    {
    'id': 17527482542529,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Angelica Duke',
    'address': '1497 Collier Mountains Apt. 551\nLucasfort, WY 98900',
    'text': 'Final during between. Style serve scientist wear term.\nWhat stage responsibility Mr onto professional. College recent notice summer voice particularly fast.',
    'email': 'jasonhayes@example.com',
    'phone_number': '(879)915-8219x87616',
    'json': {
    'name': 'Ashley Hart',
    'address': '199 Jack Neck Apt. 751\nLake David, MP 07247',
},
    'key84533': 'value94278',
    'key71027': 'value26698',
    'key70442': 'value39879',
},
    {
    'id': 17527482542541,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Leslie Robinson',
    'address': '7784 Nunez Pine\nPort Danielborough, NE 76410',
    'text': 'Ever down direction people decision customer Republican. Analysis station put political Republican prevent. Fact since book memory.\nManagement either last kitchen color. Past receive record dream.',
    'email': 'smithalejandro@example.com',
    'phone_number': '4628223117',
    'json': {
    'name': 'Carmen Barrett',
    'address': '19928 Robert Pines Apt. 633\nWilsonland, PA 61796',
},
    'key37161': 'value95379',
    'key59962': 'value69138',
    'key93536': 'value69317',
    'key29813': 'value21946',
    'key20677': 'value2141',
    'key50796': 'value7242',
    'key54108': 'value8982',
    'key83026': 'value42783',
    'key58568': 'value67584',
},
    {
    'id': 17527482542553,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Alyssa Mcdaniel',
    'address': '73790 Shari Forges\nEdwardmouth, IN 23349',
    'text': 'Television statement clear several meeting position beautiful. Mention might give build want. Floor establish wall they then sure work. Sea protect west heavy would.',
    'email': 'ylewis@example.com',
    'phone_number': '+1-847-242-0877',
    'json': {
    'name': 'Thomas Kim',
    'address': '1059 Harris Trail Apt. 207\nPort Hannah, NC 06016',
},
    'key54095': 'value16417',
    'key98564': 'value31062',
    'key9371': 'value66483',
    'key65635': 'value7477',
    'key70734': 'value89910',
    'key94281': 'value88743',
    'key93852': 'value2468',
    'key33348': 'value22123',
    'key44822': 'value89886',
},
    {
    'id': 17527482542563,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Jennifer Miller',
    'address': '849 Phillips Run Apt. 480\nCalhounhaven, DE 61994',
    'text': 'Tend threat too professional despite say vote.\nRed fast draw despite public dream. Way though executive. Suggest available again.',
    'email': 'stacyalexander@example.net',
    'phone_number': '528-382-6352',
    'json': {
    'name': 'Rachel Mitchell',
    'address': '3850 Robinson Squares Suite 569\nSouth Kimberly, MP 07677',
},
    'key69560': 'value27589',
    'key85587': 'value56840',
    'key78003': 'value50129',
    'key85142': 'value78470',
    'key56862': 'value20681',
    'key24045': 'value25526',
    'key75797': 'value69260',
    'key15586': 'value60327',
    'key39118': 'value33177',
},
    {
    'id': 17527482542575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'John Mcclain',
    'address': '67945 Lowe Rue\nMartineztown, FM 81282',
    'text': 'Few over front leader material parent whether.\nResearch son first certainly. History if idea budget stage determine. Animal left road bill.',
    'email': 'lee82@example.com',
    'phone_number': '001-929-382-4487x493',
    'json': {
    'name': 'Sandra Brown',
    'address': 'PSC 9816, Box 3792\nAPO AP 31691',
},
    'key90249': 'value45674',
    'key52025': 'value41134',
    'key47699': 'value90318',
    'key74267': 'value54695',
    'key68035': 'value18673',
    'key14434': 'value80171',
    'key78565': 'value68584',
    'key75034': 'value83336',
    'key54518': 'value57866',
},
    {
    'id': 17527482542584,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Debra Obrien',
    'address': 'USCGC Welch\nFPO AP 72519',
    'text': 'Any church enter spring.\nProbably phone deep nearly sometimes. Discussion safe court such.\nWait tree believe glass. Fire fire clearly later same.',
    'email': 'brandonmoses@example.org',
    'phone_number': '(582)326-0941',
    'json': {
    'name': 'Brendan Rubio',
    'address': 'PSC 0129, Box 3294\nAPO AE 87305',
},
    'key30608': 'value1814',
    'key3503': 'value30197',
    'key98609': 'value3670',
    'key88065': 'value65107',
    'key58175': 'value89150',
    'key89453': 'value6158',
    'key65324': 'value34802',
},
    {
    'id': 17527482542593,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Joshua Davidson',
    'address': '99862 Courtney Ports Suite 448\nNorth Denise, AZ 85734',
    'text': 'Up listen walk just upon. Rest finish life audience.\nMan anyone parent foot. Need stock bring ago. Factor certainly building child however explain else.',
    'email': 'jose64@example.com',
    'phone_number': '265.301.0196',
    'json': {
    'name': 'Carlos Adams',
    'address': '79718 Ward Mews Suite 102\nStephenview, HI 09021',
},
    'key17349': 'value33477',
    'key83115': 'value86600',
    'key65113': 'value20792',
    'key4042': 'value94667',
    'key34806': 'value8589',
    'key50846': 'value61786',
    'key66678': 'value95747',
    'key19454': 'value61149',
    'key27518': 'value69929',
},
    {
    'id': 17527482542604,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Trevor Wilson',
    'address': '4449 Green Prairie Apt. 155\nPort Janet, CT 14818',
    'text': 'Mean bag season each. Father play send will people become score.\nTheir film shoulder. Nature chance cover who fall. None share born while walk.',
    'email': 'michael57@example.net',
    'phone_number': '(856)656-7058',
    'json': {
    'name': 'Dr. Amy Patel',
    'address': '2145 Morris Rapid\nPatriciachester, MH 52632',
},
    'key15762': 'value98277',
    'key32321': 'value31211',
    'key70120': 'value95109',
},
    {
    'id': 17527482542614,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Sherry Reyes',
    'address': '8410 Taylor Glen\nEast Eric, PW 77093',
    'text': 'My same believe soon reason arrive research. Budget me unit hope direction brother case. Number beautiful experience cell generation even.',
    'email': 'amandamcintyre@example.com',
    'phone_number': '001-974-700-0800x253',
    'json': {
    'name': 'Jean Allison',
    'address': '06973 Daniel Passage\nPort Mike, NY 23533',
},
    'key58701': 'value12551',
    'key3065': 'value7027',
    'key76608': 'value69369',
},
    {
    'id': 17527482542625,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Dawn Stokes',
    'address': '5235 Jasmine Expressway\nSouth Tommyhaven, NM 02297',
    'text': 'Quality for news lawyer probably second smile. Republican rock likely southern.\nHow hotel value. Best recognize yes expert ten mission man. Town certainly election nice of group evening American.',
    'email': 'kimberlymiller@example.net',
    'phone_number': '+1-693-667-5011x34618',
    'json': {
    'name': 'Joseph Wilson',
    'address': '32892 Tammy Ramp\nSantanaview, UT 39595',
},
    'key95047': 'value49894',
    'key85081': 'value47197',
    'key91568': 'value72773',
    'key89638': 'value71956',
    'key65341': 'value288',
    'key78611': 'value21659',
    'key4885': 'value96364',
},
    {
    'id': 17527482542637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Christopher Jones',
    'address': '4212 Nancy Alley\nTonitown, OR 17945',
    'text': 'Agree affect million life join us. Second should mention yourself leader.',
    'email': 'kim13@example.net',
    'phone_number': '(585)649-8695',
    'json': {
    'name': 'Ronald Bailey',
    'address': '95712 Wong Mission\nGallagherchester, NY 30596',
},
    'key87507': 'value45561',
    'key65110': 'value42894',
},
    {
    'id': 17527482542647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Cody Collins',
    'address': '9955 Carlos Lane Suite 708\nLefort, FM 19159',
    'text': 'Section father goal join teach which.\nWindow girl job bit often general decade. Work continue different respond site network. Quite first tend behind feeling.',
    'email': 'ashleymurphy@example.org',
    'phone_number': '001-627-848-2332x94033',
    'json': {
    'name': 'Shannon Graham',
    'address': '5983 Ramirez Prairie Apt. 559\nEast Elaine, MO 62659',
},
    'key44942': 'value22697',
    'key80209': 'value6682',
    'key1083': 'value66344',
    'key81261': 'value22669',
},
    {
    'id': 17527482542659,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Richard Choi',
    'address': '864 Hogan Streets Apt. 484\nMarthaburgh, SD 25724',
    'text': 'Health position develop actually in. Significant you difference when response Republican. Attention relationship art heavy everyone free can quite.\nFrom third player. Thus day series sort.',
    'email': 'tyronebradshaw@example.com',
    'phone_number': '+1-693-746-6749x6621',
    'json': {
    'name': 'Brandy Wade',
    'address': '58595 Jerry Estates Apt. 042\nGregoryborough, AR 85115',
},
    'key21794': 'value59440',
    'key28252': 'value92468',
    'key92799': 'value5022',
    'key77456': 'value46175',
},
    {
    'id': 17527482542670,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Steve Garcia',
    'address': '53361 Holloway Hill\nNew Taylorport, MT 49432',
    'text': 'Give practice relate professor four pass. Service impact one million. Collection news film information sure wind.\nImage modern house. Along lay cover.',
    'email': 'carlos50@example.net',
    'phone_number': '813-765-5097',
    'json': {
    'name': 'Veronica Powell',
    'address': '524 Sawyer Corners\nWest Jamiechester, NC 02724',
},
    'key78822': 'value99291',
    'key42424': 'value9821',
    'key12836': 'value745',
    'key7522': 'value12485',
    'key44942': 'value77211',
    'key45730': 'value59549',
    'key56221': 'value36041',
    'key11124': 'value57566',
    'key94981': 'value35277',
    'key47368': 'value47480',
},
    {
    'id': 17527482542681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Maria Vazquez',
    'address': '402 Brenda Alley\nJoelberg, IA 50869',
    'text': 'Rather series above example do suggest. Discussion gun law security to wonder Mrs.\nFew church write series indicate job bag. Performance beat decade former likely bill.',
    'email': 'webbhannah@example.org',
    'phone_number': '(560)383-1487x373',
    'json': {
    'name': 'Christina Murphy',
    'address': '539 Stuart Street\nSouth Ruben, UT 26170',
},
    'key10996': 'value88301',
    'key96419': 'value79394',
    'key58596': 'value77623',
    'key88942': 'value82895',
    'key33314': 'value50092',
    'key41303': 'value40199',
    'key27156': 'value45933',
    'key32711': 'value12295',
},
    {
    'id': 17527482542693,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Kimberly Hansen',
    'address': '62847 Jamie Lights\nDanieltown, WI 08352',
    'text': 'Poor power dream sort. Create street as especially level.\nGuess serious edge able. Learn then stuff.\nProfessional nearly loss stock military strategy recognize. Describe surface radio cut be trouble.',
    'email': 'jeremymartinez@example.com',
    'phone_number': '+1-491-649-1620x10746',
    'json': {
    'name': 'Sara Hill',
    'address': '438 Devin Alley Suite 531\nWest Douglas, OR 53359',
},
    'key88069': 'value88156',
    'key78369': 'value89981',
    'key34639': 'value43111',
    'key84476': 'value66051',
    'key44106': 'value28569',
    'key86395': 'value32814',
    'key80046': 'value31165',
    'key65564': 'value40927',
},
    {
    'id': 17527482542704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Aaron Pitts',
    'address': '536 Johnson Knolls\nHartmanview, IL 29278',
    'text': 'Ten one go into. Special sort water no financial large discussion quality.',
    'email': 'rpatton@example.com',
    'phone_number': '001-876-968-4711x9530',
    'json': {
    'name': 'James Terry DDS',
    'address': '1114 Melanie View Suite 614\nJamieburgh, AL 04038',
},
    'key67312': 'value20672',
    'key96186': 'value34803',
    'key26518': 'value82011',
    'key34684': 'value8913',
    'key95502': 'value13826',
    'key43408': 'value64861',
    'key91837': 'value14356',
    'key94728': 'value68193',
    'key25978': 'value11642',
    'key16101': 'value7003',
},
    {
    'id': 17527482542715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Karen Mejia DDS',
    'address': '8944 Davidson Greens Suite 764\nSouth Dennis, CT 74918',
    'text': 'Large half when. Yourself stage school board. Let son form.\nSchool strong grow agency after. Discuss skill group value life. Teach state least.',
    'email': 'tanya14@example.com',
    'phone_number': '(453)679-5466x2836',
    'json': {
    'name': 'Sandra Greer',
    'address': '0322 Brady Trail\nWest Kevinstad, GU 96295',
},
    'key91668': 'value82686',
    'key8639': 'value91160',
    'key74867': 'value22873',
    'key72655': 'value95567',
},
    {
    'id': 17527482542726,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Kevin Garcia',
    'address': '774 Randall Drives\nSouth Richard, OR 76063',
    'text': 'Point pretty what response difficult. Long song him myself. Us skill argue court value far reach.',
    'email': 'hcurtis@example.com',
    'phone_number': '241-632-6150',
    'json': {
    'name': 'William Anderson',
    'address': '913 Mary Rest Suite 683\nFletcherport, AL 38962',
},
    'key90251': 'value4363',
    'key52285': 'value95213',
    'key48286': 'value46736',
    'key43592': 'value65559',
    'key76610': 'value96715',
},
    {
    'id': 17527482542736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'John Thompson',
    'address': '14179 Anderson Divide Apt. 161\nNorth Brian, CT 01793',
    'text': 'Law research live speech. Market seven case former morning month government.\nWide question student. Sometimes wish floor pick ok music conference. Phone million relate degree development.',
    'email': 'nicole29@example.net',
    'phone_number': '+1-468-355-3542x33440',
    'json': {
    'name': 'Melanie Hebert',
    'address': '286 Tina River\nAmyberg, MN 88746',
},
    'key32050': 'value62328',
    'key11527': 'value80412',
    'key40707': 'value49901',
    'key57722': 'value76187',
    'key44666': 'value83385',
    'key10998': 'value20752',
},
    {
    'id': 17527482542747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Christina Lambert',
    'address': '4671 Jillian Village Suite 077\nNew Amandaville, AR 38679',
    'text': 'Stop with shake human. Ok window focus article class. Spend sense expert prevent quality event.\nStandard body woman expect special film. Activity significant sea late guy. Positive chair firm nature.',
    'email': 'tiffanycook@example.com',
    'phone_number': '(339)357-2561x33185',
    'json': {
    'name': 'Chelsea Miller',
    'address': '4898 Santana Inlet Suite 262\nPort Billyfort, CA 40273',
},
    'key99926': 'value89837',
    'key38213': 'value60764',
    'key89386': 'value68136',
    'key58732': 'value45951',
    'key34348': 'value30988',
    'key66739': 'value61039',
    'key41728': 'value7671',
    'key62074': 'value45448',
    'key27475': 'value41511',
    'key90121': 'value12570',
},
    {
    'id': 17527482542759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Stacey Cole',
    'address': '7708 Alexander View\nTonyaview, PW 95299',
    'text': 'Usually south yourself discussion. Anyone start board.\nSister direction with TV rich civil market. Protect audience purpose class road some. Movement fine seek region likely born seat perform.',
    'email': 'stevensonjoshua@example.com',
    'phone_number': '3202809537',
    'json': {
    'name': 'Sarah Clark',
    'address': 'PSC 1363, Box 7983\nAPO AE 79276',
},
    'key29056': 'value76934',
    'key20978': 'value97336',
    'key52173': 'value5352',
    'key4473': 'value48044',
    'key49564': 'value69866',
},
    {
    'id': 17527482542768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Larry Rodriguez',
    'address': '82248 Riley Stravenue\nSouth Blakefurt, GA 75923',
    'text': 'Chance agent line class at. Star rest year try anyone. Interest on my view. Mind table kitchen fear close control peace.',
    'email': 'ffitzgerald@example.com',
    'phone_number': '360-436-7276',
    'json': {
    'name': 'Allen Ellis',
    'address': '19452 Johnson Roads Suite 313\nEricachester, SD 50546',
},
    'key70640': 'value76767',
    'key67813': 'value19819',
    'key3169': 'value330',
},
    {
    'id': 17527482542779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Cindy Martinez',
    'address': '5865 Jenkins Mission Apt. 005\nEvansside, VT 19974',
    'text': 'Ready from follow page current seat. Board real least wonder. Off only Mrs force three since.\nShow fast west trip. Tax market exist reveal magazine onto.',
    'email': 'richardsonkimberly@example.org',
    'phone_number': '001-470-395-0160x4021',
    'json': {
    'name': 'Sara Calderon',
    'address': '7338 Bailey Drives\nNancyshire, OK 43654',
},
    'key4779': 'value74454',
    'key33200': 'value41860',
    'key60758': 'value62413',
},
    {
    'id': 17527482542791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Catherine Chavez',
    'address': '67130 Lucas Inlet\nBensonmouth, MH 78656',
    'text': 'Pull group skin discussion record chair. Mouth girl like. Onto machine understand claim among seat two.\nMore mission over actually toward hit. Off more politics however behavior around strong return.',
    'email': 'jenna41@example.net',
    'phone_number': '234-895-5147',
    'json': {
    'name': 'Laurie Silva',
    'address': '41683 Andre View Apt. 678\nEast Nicholas, WI 56912',
},
    'key27921': 'value89060',
    'key2466': 'value67721',
    'key97459': 'value90706',
    'key960': 'value43802',
    'key96301': 'value45850',
    'key21302': 'value35226',
},
    {
    'id': 17527482542801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Jerome Hodges',
    'address': '4409 Ward Mountain\nNorth Heather, CO 54020',
    'text': 'Party night all different deep past. Military try discussion country.\nDebate plan popular both consider. Former activity owner.',
    'email': 'alexander38@example.org',
    'phone_number': '001-854-465-1450x4510',
    'json': {
    'name': 'Wendy Pham',
    'address': '27505 Clayton Squares\nRiverafurt, VI 35445',
},
    'key41203': 'value44259',
    'key25707': 'value47522',
    'key71738': 'value71299',
    'key24768': 'value83733',
    'key72602': 'value74567',
    'key70270': 'value46327',
    'key94291': 'value48886',
    'key52902': 'value29542',
},
    {
    'id': 17527482542812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Amanda Young',
    'address': '078 Natalie Estate Suite 645\nNorth Devonville, NV 57800',
    'text': 'Within individual same. Hear will expect though prove television receive event. Space because star include lead until goal.\nPhysical sea total though. Hit road better wear art.',
    'email': 'shelleyjohnson@example.net',
    'phone_number': '477.661.8637x894',
    'json': {
    'name': 'Laura Barry',
    'address': '05113 Jaime Stream\nMillerville, AZ 40003',
},
    'key11901': 'value82327',
    'key49842': 'value45864',
    'key80446': 'value60248',
    'key40628': 'value83181',
    'key58414': 'value38136',
    'key73886': 'value58019',
    'key53522': 'value21284',
},
    {
    'id': 17527482542824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'John Jenkins',
    'address': '16262 Harris Track\nSouth Dominiqueview, DC 87066',
    'text': 'Necessary sort involve common somebody nation. Allow attack discover great our.',
    'email': 'wwashington@example.com',
    'phone_number': '+1-444-880-1306',
    'json': {
    'name': 'Alexis Wise',
    'address': '98302 Taylor Squares Suite 613\nWest Alexander, HI 95426',
},
    'key44015': 'value52414',
    'key96623': 'value18513',
},
    {
    'id': 17527482542835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Kristen Lewis',
    'address': 'Unit 2858 Box 3018\nDPO AE 40197',
    'text': 'Body tree beautiful region. Home on air himself discussion. Magazine method huge management factor would everything.',
    'email': 'velasquezjennifer@example.net',
    'phone_number': '9256923979',
    'json': {
    'name': 'Anita Cruz',
    'address': '6995 Peter Stream Apt. 137\nWest Andrea, HI 17665',
},
    'key6406': 'value91226',
},
    {
    'id': 17527482542844,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Timothy Decker',
    'address': '334 Middleton Keys\nLake Kevin, FL 24912',
    'text': 'Mrs nor myself call. Majority table hundred commercial back sense.\nIssue doctor relationship present fall quickly. Nation last form.',
    'email': 'abooth@example.com',
    'phone_number': '841.863.8826x8056',
    'json': {
    'name': 'Mark Gray MD',
    'address': '73391 Justin Isle Apt. 427\nNew Monicaport, PA 14118',
},
    'key74068': 'value49096',
    'key19663': 'value35328',
},
    {
    'id': 17527482542854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Brandon Weaver',
    'address': '11941 Matthew Union\nEast Natalie, NM 59942',
    'text': 'Mission than my traditional everyone source. Run but item with for.\nAdult range affect outside. Single win authority measure rule.',
    'email': 'dalelee@example.net',
    'phone_number': '(785)547-6289',
    'json': {
    'name': 'Jared Edwards',
    'address': '99643 Richard Grove\nWest Randallberg, AS 27173',
},
    'key13530': 'value63817',
},
    {
    'id': 17527482542865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Jay Bailey',
    'address': '6180 Laura Shore\nNorth Susan, LA 45560',
    'text': 'Door information support either focus shoulder buy. No data push total election.\nLose word happy seven of candidate. Peace option individual because writer business enough. Raise million staff check.',
    'email': 'hoffmanjames@example.org',
    'phone_number': '001-939-877-1624x0829',
    'json': {
    'name': 'Nathan Smith',
    'address': '4022 Williams Trafficway\nTheresastad, AR 99657',
},
    'key3979': 'value45737',
    'key50970': 'value7499',
},
    {
    'id': 17527482542876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Sandy Green',
    'address': '21779 Morris Gateway Suite 250\nNorth Cindy, AL 98288',
    'text': 'Morning later the very. Region people laugh past religious wear. Say memory other perhaps side information her. Effect health long have car perform.',
    'email': 'clayton09@example.com',
    'phone_number': '435-405-6364x7287',
    'json': {
    'name': 'Timothy Pineda Jr.',
    'address': '6629 Rios Green Suite 879\nSouth Tammyview, IN 10959',
},
    'key62090': 'value2172',
    'key44212': 'value16880',
    'key9233': 'value10048',
    'key29053': 'value99969',
    'key31164': 'value7940',
    'key78745': 'value17660',
    'key58197': 'value28344',
},
    {
    'id': 17527482542887,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Michael Benson',
    'address': '2918 Watson Streets Apt. 485\nLeetown, KY 78803',
    'text': 'Similar water paper grow feeling. Significant local rise TV.\nAnyone town community between young Mr. Travel carry scene avoid.\nOn stay letter. Fight season they its likely.',
    'email': 'bairdtammie@example.net',
    'phone_number': '632-205-3556x542',
    'json': {
    'name': 'Andrew Walker',
    'address': '891 White Club Apt. 042\nSmithview, OH 51846',
},
    'key44031': 'value58130',
    'key70177': 'value77026',
    'key9235': 'value62954',
    'key76803': 'value57063',
    'key81521': 'value36883',
    'key56566': 'value26849',
    'key11442': 'value48474',
},
    {
    'id': 17527482542899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Frank Rosales',
    'address': '9156 Amanda Track Suite 155\nClarkport, SC 49560',
    'text': 'Skill feel southern send family bank. Manage through apply describe. Item eye couple eight dinner.\nGive campaign side challenge song staff. Factor series dinner year television provide opportunity.',
    'email': 'xlowe@example.org',
    'phone_number': '(485)682-7605',
    'json': {
    'name': 'Sarah Freeman',
    'address': '471 Johnson Inlet Suite 648\nNew Amandamouth, MP 40289',
},
    'key65989': 'value97417',
    'key9729': 'value71280',
    'key11209': 'value36876',
    'key74256': 'value34455',
    'key42452': 'value15733',
    'key35103': 'value65091',
    'key62218': 'value17561',
    'key63835': 'value90438',
},
    {
    'id': 17527482542911,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Donna Garcia',
    'address': 'Unit 0312 Box 3587\nDPO AP 30181',
    'text': 'Rate young tend happen small staff door cultural. Sit year they measure parent. Paper successful opportunity party act agree result.',
    'email': 'lindseydixon@example.com',
    'phone_number': '+1-896-400-9700x4615',
    'json': {
    'name': 'Luis Martinez',
    'address': '1635 Wade Fields Suite 285\nMccormickfurt, NJ 43581',
},
    'key50561': 'value32820',
    'key62112': 'value58405',
    'key57409': 'value43847',
    'key16066': 'value874',
    'key87450': 'value98228',
    'key66835': 'value47721',
    'key82685': 'value59952',
},
    {
    'id': 17527482542921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Katherine Hammond',
    'address': '337 Williams Lodge Suite 726\nBryanborough, FL 75645',
    'text': 'Learn conference consider. Thousand believe him. Range public quite very.\nAhead senior yourself sport nice pick end. This something our. Common cultural whether American.',
    'email': 'jessicagarcia@example.com',
    'phone_number': '+1-866-281-2409',
    'json': {
    'name': 'Amy Grant',
    'address': '8530 Carpenter Meadow\nPort Davidbury, DE 68366',
},
    'key74671': 'value89526',
    'key61920': 'value1212',
    'key60807': 'value68023',
    'key76540': 'value92048',
    'key84837': 'value44270',
    'key21806': 'value62390',
    'key25796': 'value1572',
},
    {
    'id': 17527482542932,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Amanda Smith',
    'address': '15069 Cory Crest\nStoutfurt, MO 52461',
    'text': 'Worry house next budget. Article Mrs fact order.\nTest decision no attention impact. Give paper score quite natural else movement detail.',
    'email': 'pmorris@example.org',
    'phone_number': '(937)358-2873x953',
    'json': {
    'name': 'Cheryl Griffin',
    'address': '475 Nancy Mountain Apt. 757\nBethanyborough, VT 37449',
},
    'key42602': 'value21809',
    'key55587': 'value42597',
    'key44419': 'value71511',
    'key67899': 'value63694',
    'key2709': 'value42306',
    'key39466': 'value84435',
},
    {
    'id': 17527482542942,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Mr. Thomas Pacheco MD',
    'address': '1420 Humphrey Wall\nJessicastad, MT 70437',
    'text': 'Economy party stop. Here soldier drop white. Enter nearly exist federal.\nTrue represent wife year left. News hope floor much some order.',
    'email': 'hpowers@example.net',
    'phone_number': '(419)766-6777',
    'json': {
    'name': 'Johnny Sawyer',
    'address': 'PSC 4337, Box 9833\nAPO AA 04120',
},
    'key75147': 'value63089',
    'key68779': 'value57508',
    'key33663': 'value45940',
    'key47373': 'value53473',
    'key45994': 'value73316',
},
    {
    'id': 17527482542951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Heather Fletcher',
    'address': '00255 Smith Street\nLake Kim, MN 05468',
    'text': 'Strategy college sing direction station page anything can. Head place eye tough son poor thus.\nGreen social already to.\nCouple left that like property. Boy after even case partner across should.',
    'email': 'acook@example.com',
    'phone_number': '857.588.8463x898',
    'json': {
    'name': 'Eric Roach',
    'address': 'PSC 8366, Box 0856\nAPO AA 60641',
},
    'key50787': 'value70477',
    'key57637': 'value39090',
    'key17340': 'value39256',
    'key31227': 'value20059',
    'key62427': 'value30641',
    'key23836': 'value43037',
    'key20125': 'value44070',
    'key97853': 'value98093',
    'key82484': 'value67225',
    'key87264': 'value17446',
},
    {
    'id': 17527482542960,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Joshua Fernandez',
    'address': '3370 Leonard Spurs Apt. 109\nPort Patrick, PW 36551',
    'text': 'Generation marriage seat. Whose can travel personal everybody claim. Baby build watch create.\nNice behind thus measure class pull as. Positive hot fact customer.',
    'email': 'benjamin64@example.org',
    'phone_number': '869.770.7736x2859',
    'json': {
    'name': 'Kathleen Chase',
    'address': '320 Patrick Causeway\nSilvafurt, MH 06438',
},
    'key9451': 'value91423',
},
    {
    'id': 17527482542974,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Colleen Johnson',
    'address': '56631 Thompson Ridge\nPort Robert, VA 20134',
    'text': 'Free modern military front almost. Own sell computer education their.\nIts majority serious consider. Discover they full rather might election market.',
    'email': 'cynthia69@example.org',
    'phone_number': '6299619644',
    'json': {
    'name': 'Jennifer Baldwin',
    'address': 'PSC 4806, Box 7962\nAPO AP 45262',
},
    'key69996': 'value84335',
    'key32936': 'value72117',
    'key28846': 'value85887',
    'key75538': 'value65769',
    'key46691': 'value64211',
    'key55405': 'value20727',
    'key22290': 'value39500',
    'key76707': 'value84431',
    'key77367': 'value97093',
},
    {
    'id': 17527482542983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Bobby Weber',
    'address': '27028 Heather Cove\nWhiteborough, LA 34840',
    'text': 'Maintain look garden continue act early. Many well develop some away nothing understand.\nWall attention light sort cup product since take. Money put impact six. Process myself old fast.',
    'email': 'lnavarro@example.org',
    'phone_number': '753.597.4404',
    'json': {
    'name': 'Jessica Diaz',
    'address': '112 Mary Stream Suite 249\nWallaceside, NM 65428',
},
    'key44060': 'value90026',
    'key89522': 'value28549',
    'key18605': 'value7165',
    'key10024': 'value38167',
    'key45052': 'value29545',
},
    {
    'id': 17527482542994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Abigail Williams',
    'address': '28997 Durham Ville\nEast Jacob, GA 17122',
    'text': 'Indicate little land dinner. Former begin visit pull decade.\nOnce moment month lot race range. What idea likely. Smile around important heavy.\nReality look above collection ability.',
    'email': 'xhowell@example.net',
    'phone_number': '(273)594-8051',
    'json': {
    'name': 'Kimberly Wheeler',
    'address': '88493 Brett Coves Suite 447\nElliottberg, ID 19967',
},
    'key41625': 'value24914',
    'key35921': 'value86894',
    'key79368': 'value95168',
    'key98339': 'value13973',
    'key5784': 'value6029',
},
    {
    'id': 17527482543005,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Raymond Jackson',
    'address': 'Unit 4691 Box 3163\nDPO AE 59304',
    'text': 'Western speech minute only kind. Hair official oil tough they leader happen. After prove fill attorney want.',
    'email': 'woodcheyenne@example.org',
    'phone_number': '829-587-1095',
    'json': {
    'name': 'Michelle Price',
    'address': '3739 Joyce Estates\nChristinahaven, NY 50374',
},
    'key94917': 'value45211',
    'key35152': 'value96365',
    'key64483': 'value59072',
    'key83546': 'value65464',
    'key56394': 'value68235',
    'key69367': 'value47350',
    'key32454': 'value9038',
    'key616': 'value20482',
    'key62336': 'value95135',
},
    {
    'id': 17527482543014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Glenda Hall',
    'address': '27018 Vicki Plains\nParrishhaven, SC 11825',
    'text': 'Individual purpose person huge hour. Rule your pass. Play best teacher responsibility happy process history.',
    'email': 'david88@example.org',
    'phone_number': '(450)993-6538',
    'json': {
    'name': 'Raymond Johnson',
    'address': '81655 Karen Port\nNicholasport, KS 76122',
},
    'key82055': 'value39377',
    'key56583': 'value73708',
},
    {
    'id': 17527482543024,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Patricia Aguilar',
    'address': '7834 Karen Mill\nSouth Russell, CT 27865',
    'text': 'Dinner care common minute write benefit type. Strong country case consider.',
    'email': 'johnsonalison@example.net',
    'phone_number': '9022937618',
    'json': {
    'name': 'Jennifer Romero',
    'address': '5116 Warren Village Apt. 212\nMasonhaven, GU 32600',
},
    'key92879': 'value65755',
    'key48021': 'value62395',
    'key19364': 'value86065',
    'key18400': 'value37274',
    'key51313': 'value79412',
},
    {
    'id': 17527482543035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Nicholas Jackson',
    'address': '94296 Daniel Square Suite 002\nEricmouth, NM 85089',
    'text': 'Face loss last resource cup.\nOff contain cell.\nParent capital challenge morning. Shoulder rich white think watch.\nDown scene time charge against man economy station.',
    'email': 'elizabeth38@example.org',
    'phone_number': '001-490-251-7002x176',
    'json': {
    'name': 'Ruben Dennis',
    'address': '9289 Hannah Pine\nHoffmanchester, WY 81965',
},
    'key28350': 'value28873',
    'key35177': 'value11268',
    'key62773': 'value67598',
    'key34886': 'value80570',
    'key4982': 'value6240',
    'key81795': 'value18952',
    'key97238': 'value78029',
},
    {
    'id': 17527482543046,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Anthony Cook MD',
    'address': '296 Lynch Mountain Suite 139\nFergusonton, AR 04794',
    'text': 'Both cold strong public result western. That will up which suggest care. Rest figure clear soldier forward.\nPiece enjoy as during.',
    'email': 'david39@example.com',
    'phone_number': '928.885.8703x7805',
    'json': {
    'name': 'Susan Blankenship',
    'address': '02397 Hudson Common\nNorth Derrick, OR 61294',
},
    'key44844': 'value50234',
    'key96751': 'value31179',
    'key82632': 'value24956',
    'key79728': 'value66566',
},
    {
    'id': 17527482543057,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Denise Carter',
    'address': '15948 Keith Tunnel Apt. 487\nSuehaven, TN 16015',
    'text': 'Too environmental then item story play. Seven front read happy traditional hand however. Term design somebody.',
    'email': 'vvaldez@example.org',
    'phone_number': '001-913-997-5925x17288',
    'json': {
    'name': 'Ashley Smith',
    'address': '631 Cindy Light\nKimberlyport, MP 32623',
},
    'key26732': 'value80197',
    'key1082': 'value34969',
    'key31054': 'value28654',
    'key95552': 'value39651',
    'key54070': 'value20733',
    'key39604': 'value47071',
},
    {
    'id': 17527482543067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'James Jimenez',
    'address': '18809 Ryan Alley Suite 237\nChristineshire, VA 23803',
    'text': 'Official century indicate until scene war. Hair for we property central.',
    'email': 'xmoore@example.net',
    'phone_number': '6929007372',
    'json': {
    'name': 'Jessica Combs',
    'address': '651 Heather Plain\nNorth Damonfurt, MI 09489',
},
    'key72558': 'value3592',
    'key97813': 'value96974',
    'key50724': 'value65671',
    'key84445': 'value64627',
},
    {
    'id': 17527482543078,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Diane Mitchell',
    'address': '787 Sabrina Mountains Suite 198\nAdamfurt, WY 89993',
    'text': 'Many such throughout much standard bill generation. Job friend mind whole sell draw. Call perhaps or expert author help report.',
    'email': 'christina83@example.com',
    'phone_number': '540-884-6949x79726',
    'json': {
    'name': 'Cheyenne Spencer',
    'address': '9797 Keller Drive Apt. 626\nFieldsborough, MI 44499',
},
    'key66685': 'value26252',
    'key32006': 'value75869',
    'key54075': 'value90633',
    'key99078': 'value48987',
    'key8373': 'value44162',
    'key79708': 'value43702',
    'key58188': 'value62474',
    'key4806': 'value44908',
},
    {
    'id': 17527482543088,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Mrs. Anne Johnson',
    'address': '1216 Simon Mountains Apt. 657\nAshleyberg, AR 79228',
    'text': 'Second begin around central pattern us huge week. Early above pull local issue model best. Evidence sometimes care against pass.',
    'email': 'johnhunter@example.org',
    'phone_number': '+1-884-988-9954',
    'json': {
    'name': 'Duane Ramirez',
    'address': '78963 Shelby Alley\nToddfurt, SD 32568',
},
    'key88210': 'value50958',
    'key66484': 'value77288',
    'key64939': 'value46977',
    'key14422': 'value59114',
    'key29113': 'value789',
    'key41960': 'value87664',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
    'data': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'json',
],
    'filter': 'name like \'Jo%\'',
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
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
    'RequestId': '1a90bf10-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_48_059870lWxImJMu',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name like "placeholder%"]_1752748257.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithComplexVarcharFilterNameLikePlaceholder1752748257Json()
    test.run_tests()
