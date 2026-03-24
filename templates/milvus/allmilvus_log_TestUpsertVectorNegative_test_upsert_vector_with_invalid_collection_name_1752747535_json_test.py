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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestUpsertVectorNegative_test_upsert_vector_with_invalid_collection_name_1752747535_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestUpsertVectorNegative_test_upsert_vector_with_invalid_collection_name_1752747535.json"
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



class AllmilvusLogtestupsertvectornegativeTestUpsertVectorWithInvalidCollectionName1752747535Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestUpsertVectorNegative_test_upsert_vector_with_invalid_collection_name_1752747535.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestUpsertVectorNegative_test_upsert_vector_with_invalid_collection_name_1752747535.json"
        self.test_count = 6  # 测试方法数量
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
    'RequestId': '706c1918-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_18_53_114013KUVHpLZL',
    'dimension': 128,
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
    'RequestId': '706c1918-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_18_53_114013KUVHpLZL',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v2/vectordb/entities/upsert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/upsert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/upsert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '706c1918-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'invalid_collection_name',
    'data': [
    {
    'id': 17527475341489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Stacey Simon',
    'address': '126 Kevin Plains Apt. 553\nLake Gregory, AZ 54991',
    'text': 'Executive must later say. Than usually cell middle into.\nFund recently soldier. Bank including space forget. Set pay stop security collection pay range knowledge.',
    'email': 'reevesrobert@example.com',
    'phone_number': '001-559-274-2836x359',
    'json': {
    'name': 'Andrew Chapman',
    'address': '08449 Kathleen Islands\nMadisonmouth, KS 70324',
},
    'key18590': 'value39339',
    'key26620': 'value87953',
    'key954': 'value87217',
    'key37811': 'value65179',
    'key82830': 'value31118',
    'key45710': 'value41123',
    'key43169': 'value61872',
    'key16476': 'value85782',
    'key23106': 'value57034',
    'key14652': 'value4931',
},
    {
    'id': 17527475341512,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sandra Brown',
    'address': '7577 Charles Rest\nSouth Laurafurt, VI 97251',
    'text': 'Us value trouble glass want. Positive success instead may knowledge on.\nSecond prove store live would three. Describe and production believe position effort.',
    'email': 'davidmccarty@example.com',
    'phone_number': '285.281.1649x7085',
    'json': {
    'name': 'Megan Fowler',
    'address': '11505 Johnson Green Suite 673\nPort Stephanie, ND 65827',
},
    'key47814': 'value71526',
    'key72362': 'value84224',
    'key45185': 'value45212',
    'key23112': 'value35420',
    'key28493': 'value54328',
    'key71071': 'value59162',
    'key73086': 'value98896',
    'key91908': 'value63573',
    'key7252': 'value23886',
    'key86792': 'value45951',
},
    {
    'id': 17527475341528,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Eric Robinson DDS',
    'address': '0976 Ramsey Landing\nJulieport, CA 64467',
    'text': 'Woman mission respond without let able window think. Rate base expert maybe recently coach reveal. Central citizen draw order. Over beautiful capital court audience.',
    'email': 'nashmary@example.org',
    'phone_number': '583-582-3484x038',
    'json': {
    'name': 'Shari Castaneda',
    'address': '207 Joshua Prairie Suite 089\nBradleyport, MI 37173',
},
    'key51440': 'value5092',
    'key62983': 'value21928',
},
    {
    'id': 17527475341542,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Kristen Jackson',
    'address': '956 Espinoza Land Suite 743\nSinghfurt, VT 85509',
    'text': 'Benefit message available hit begin everyone.\nBoth happy painting service process nothing. Sit seat baby recent ball.\nVery continue until decade full everybody event.',
    'email': 'rpotts@example.org',
    'phone_number': '+1-347-648-5582',
    'json': {
    'name': 'James Barnett',
    'address': '94642 Patel Crossroad\nEast Katherinemouth, NM 84574',
},
    'key46365': 'value35418',
    'key15434': 'value14068',
    'key86251': 'value89733',
    'key5222': 'value13495',
    'key60331': 'value58079',
},
    {
    'id': 17527475341556,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Stephen Matthews',
    'address': '9092 Amanda Glen Apt. 433\nJamesmouth, OH 07493',
    'text': 'Suddenly side under deal officer about few. Author peace movie indeed street.\nYoung attack notice go much smile street goal. Fund manage ten feel rule.',
    'email': 'rogerkennedy@example.net',
    'phone_number': '314-269-9906',
    'json': {
    'name': 'Lori Wright',
    'address': '8059 Hart Hills\nLeemouth, OK 55543',
},
    'key38420': 'value69109',
    'key46148': 'value63233',
},
    {
    'id': 17527475341571,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jose Anderson',
    'address': 'USS Webster\nFPO AA 48079',
    'text': 'College down authority clearly trial model. Final forget kid movie plan would perhaps memory.\nSea east discuss consider voice. Soldier sea without glass final wear. Move pay after.',
    'email': 'perezdavid@example.net',
    'phone_number': '+1-787-755-8371x0719',
    'json': {
    'name': 'Martha Hernandez',
    'address': '239 Pamela Inlet Suite 568\nCummingsshire, MH 63732',
},
    'key20015': 'value67971',
    'key95853': 'value39277',
    'key9132': 'value58091',
    'key69038': 'value6020',
},
    {
    'id': 17527475341592,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Steven Phillips',
    'address': '384 Conley Forest\nJohnchester, GA 06108',
    'text': 'Office no station over care. Former identify system perform bag. Boy dream Mrs describe.\nGreen news game structure hundred statement beyond. Candidate share I tonight everyone senior.',
    'email': 'joshuaanderson@example.org',
    'phone_number': '696-677-5687x7427',
    'json': {
    'name': 'Willie Wu PhD',
    'address': '27513 Nicole Oval Apt. 848\nParkerton, NV 12717',
},
    'key87992': 'value13019',
    'key10976': 'value76912',
},
    {
    'id': 17527475341612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Stephanie Ayala',
    'address': '37056 Anderson Square Apt. 533\nChambersmouth, MP 10642',
    'text': 'Identify which race movie. World avoid third system involve market show major. Among scientist audience until.\nCommon fill rest edge must drop. Down down theory scene.',
    'email': 'brownbeth@example.com',
    'phone_number': '544.770.6409',
    'json': {
    'name': 'Adam Bell',
    'address': '14824 Rodriguez Spur Suite 857\nEast Chad, ND 11803',
},
    'key87520': 'value34367',
},
    {
    'id': 17527475341637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jacob Taylor',
    'address': '93724 Devin Ports Suite 500\nNew Noahtown, MH 39430',
    'text': 'Ahead right morning article. Thing use hair food myself again hold. Way both group.\nReally traditional player fish evidence information. Thus share team important last writer report.',
    'email': 'jfleming@example.net',
    'phone_number': '001-386-755-8665x75335',
    'json': {
    'name': 'Michael Hernandez',
    'address': '3724 Wu Orchard Apt. 760\nNorth Mitchelltown, ID 06522',
},
    'key56797': 'value40068',
    'key69671': 'value68391',
    'key13775': 'value71907',
    'key24678': 'value60023',
    'key96642': 'value85053',
    'key2312': 'value16481',
    'key85746': 'value15284',
    'key60777': 'value30066',
},
    {
    'id': 17527475341663,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Richard Webster',
    'address': '573 Cooper Glen\nNew Nicole, WI 26701',
    'text': 'Measure short place apply system serious sure if. Bad do top baby pass best. Discussion candidate dark guess care should.',
    'email': 'nicole87@example.org',
    'phone_number': '8985619520',
    'json': {
    'name': 'Jesus Perez',
    'address': '878 William Shoal Suite 248\nHoltside, PR 81886',
},
    'key48514': 'value30044',
    'key7083': 'value84189',
    'key95563': 'value99911',
    'key19318': 'value55380',
    'key12760': 'value30765',
    'key15631': 'value3101',
    'key90668': 'value91616',
    'key27585': 'value28616',
    'key30582': 'value16880',
    'key10425': 'value20920',
},
    {
    'id': 17527475341684,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Hailey Lowe',
    'address': '960 Carr Bypass Apt. 812\nPort Edwardborough, PW 75459',
    'text': 'Open right hot. Box themselves force under pass miss believe.\nWhite discover job. Above power other defense. Scene information certain.',
    'email': 'hendersongabriel@example.net',
    'phone_number': '3419171711',
    'json': {
    'name': 'Samantha Williams',
    'address': '33358 Gary Run Suite 849\nSouth Anthony, FM 53108',
},
    'key12074': 'value34813',
    'key57833': 'value74197',
    'key65330': 'value93228',
    'key55557': 'value33347',
    'key37235': 'value69909',
    'key34409': 'value96052',
    'key59619': 'value68138',
    'key50656': 'value36801',
},
    {
    'id': 17527475341704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Leslie Roberson',
    'address': '2527 Darren Crescent\nLake Karatown, CT 93312',
    'text': 'Term blue quite face. Owner need clearly to.\nRealize push someone break charge. Often accept second first win production same.',
    'email': 'alexanderjackson@example.com',
    'phone_number': '+1-761-362-7176x8739',
    'json': {
    'name': 'Jordan Rodriguez',
    'address': '8297 Mark Squares\nNorth Kristen, CT 22881',
},
    'key18651': 'value47715',
    'key18800': 'value60264',
    'key2034': 'value25374',
    'key55013': 'value40790',
    'key42260': 'value55329',
    'key39322': 'value17163',
    'key37276': 'value82828',
    'key49017': 'value49392',
},
    {
    'id': 17527475341721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Steven Zhang',
    'address': '1260 Roberts Summit Apt. 128\nNorth Melissaburgh, NM 02472',
    'text': 'Chair court art high institution lead. Much continue put fill. Health similar car sea price loss others.\nHere somebody movement exist occur traditional.',
    'email': 'hansenjohn@example.com',
    'phone_number': '+1-647-308-4397x5458',
    'json': {
    'name': 'Amanda Murphy',
    'address': '94221 Sarah Road Apt. 010\nSuarezstad, DC 23592',
},
    'key28635': 'value38807',
    'key99093': 'value61227',
},
    {
    'id': 17527475341739,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'William Hudson',
    'address': '7456 Bobby Loaf Apt. 161\nNorth Daniel, NJ 46716',
    'text': 'Seem everybody event. Address need finally ask word or close.\nQuestion perhaps seek who audience allow political. Design age recently hit central.\nVery policy pattern its. My east letter across.',
    'email': 'jenniferturner@example.org',
    'phone_number': '001-369-798-6469',
    'json': {
    'name': 'Michael Chandler',
    'address': '39963 Walsh Lodge Apt. 518\nEvansfurt, MN 18974',
},
    'key32413': 'value55476',
    'key45043': 'value28169',
    'key75630': 'value53243',
    'key94332': 'value21487',
    'key66967': 'value58657',
    'key36539': 'value98699',
    'key36007': 'value7605',
    'key61958': 'value8182',
},
    {
    'id': 17527475341758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'James Ramos',
    'address': '2806 Michael Radial\nKristaville, VA 82210',
    'text': 'Identify represent east democratic enjoy like. Role along particular debate. Wall be last.\nNothing institution some teacher international. Change along fact nor road ground herself.',
    'email': 'erin00@example.org',
    'phone_number': '001-223-503-6425x3451',
    'json': {
    'name': 'Mary Ritter',
    'address': '266 Cheyenne Club Apt. 299\nGuzmanland, DC 07928',
},
    'key32549': 'value29141',
    'key12471': 'value40766',
    'key4265': 'value88180',
    'key20816': 'value7529',
},
    {
    'id': 17527475341774,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Grace Arias',
    'address': '1468 Connie Islands Suite 330\nPort Ashley, ND 49328',
    'text': 'Cell onto like create. Ability answer low station dinner.\nScene again Democrat save consumer fire thousand. Ever less newspaper total beyond mean. Painting media rule plan television direction.',
    'email': 'elizabethjackson@example.net',
    'phone_number': '728-454-1232x97405',
    'json': {
    'name': 'Heather Cunningham',
    'address': '677 Johnston Road Suite 606\nYounghaven, RI 39504',
},
    'key68310': 'value23304',
    'key7997': 'value2262',
    'key84493': 'value52746',
    'key52228': 'value20797',
    'key33154': 'value5373',
    'key78874': 'value91462',
    'key12700': 'value39962',
    'key5728': 'value7453',
    'key6698': 'value12447',
},
    {
    'id': 17527475341792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Christina Richardson',
    'address': '73178 Nicholas Throughway Apt. 374\nSouth Christopherbury, DE 78619',
    'text': 'Mrs teacher relationship join. Third fall future dinner. Language couple professor this consumer.\nAll eight test nearly matter. National most hospital against ask line through.',
    'email': 'perezjack@example.com',
    'phone_number': '9476496354',
    'json': {
    'name': 'Oscar Lee',
    'address': '39473 Stone Vista Suite 318\nWest Mark, SD 67027',
},
    'key36985': 'value33148',
    'key41852': 'value86734',
    'key69089': 'value461',
    'key49939': 'value18035',
    'key58518': 'value72719',
    'key88390': 'value71841',
    'key33544': 'value78399',
    'key502': 'value45872',
},
    {
    'id': 17527475341806,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Rebecca Davis',
    'address': '198 Barrera Glen\nJacksonville, VA 39748',
    'text': 'Today office professor nothing event listen animal. Appear speak to.\nScore Mr view mention a. Very under south late summer. Really sell these cost center act.\nSuffer church direction usually movie.',
    'email': 'uphillips@example.org',
    'phone_number': '001-482-826-9037x8353',
    'json': {
    'name': 'Jasmine Baker',
    'address': '4619 Troy Wall Suite 747\nEast Joseph, MD 67631',
},
    'key37634': 'value4339',
    'key58481': 'value84710',
    'key20963': 'value18243',
},
    {
    'id': 17527475341820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Dawn Pope',
    'address': '919 Jeremiah Island Apt. 277\nThomasstad, VI 24285',
    'text': 'Measure control watch ball suffer. Myself arrive enjoy explain once.\nDefense cut my suggest although follow. Nature fact executive town technology. From decide cost any at drug study.',
    'email': 'samanthaboone@example.org',
    'phone_number': '456-661-0245x33354',
    'json': {
    'name': 'Anita Hamilton',
    'address': 'USNS Navarro\nFPO AP 62252',
},
    'key51080': 'value81904',
    'key68208': 'value37536',
    'key95675': 'value10524',
},
    {
    'id': 17527475341833,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Natasha Garrett',
    'address': '0830 Love Spurs Suite 855\nAlexanderbury, HI 19963',
    'text': 'Clearly when perform government maintain generation often. Fact sing cost success get end hit common. Stock arm mean huge soldier.\nBox music condition data glass bank. Store later it show.',
    'email': 'nwright@example.net',
    'phone_number': '+1-563-556-1060x977',
    'json': {
    'name': 'Christine Hayes',
    'address': '419 Gonzalez Springs Apt. 597\nPort Jennifer, WY 53408',
},
    'key18753': 'value70394',
    'key25612': 'value14417',
},
    {
    'id': 17527475341848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Anthony Smith',
    'address': '4016 Richardson Land Apt. 291\nSouth Troy, MT 31582',
    'text': 'Prepare Mr poor mother senior. Account although public just citizen.\nArticle list career me also door someone. Something employee year exactly. Generation when until effort trade until dog end.',
    'email': 'zunigajacqueline@example.net',
    'phone_number': '3005654982',
    'json': {
    'name': 'Paige Hudson',
    'address': '9571 Raymond Curve\nPort Casey, FM 31559',
},
    'key60526': 'value75026',
    'key83936': 'value42503',
    'key92108': 'value17272',
    'key33244': 'value97600',
    'key47121': 'value61143',
    'key99779': 'value50777',
    'key90277': 'value30471',
    'key10535': 'value59379',
    'key63782': 'value87643',
    'key51103': 'value19612',
},
    {
    'id': 17527475341865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jennifer Collier',
    'address': '12156 Nelson Ramp Apt. 804\nEast Lisa, GA 55781',
    'text': 'Eat on customer model speech close.\nCamera plan at opportunity forward letter discuss. Whose note water hospital. Time wrong join talk high. Road unit number plant wind.',
    'email': 'debbie33@example.org',
    'phone_number': '001-224-779-9129',
    'json': {
    'name': 'Harry Huber',
    'address': '528 Morales Camp\nPort Alexandra, MI 60397',
},
    'key38147': 'value26188',
    'key18585': 'value48180',
    'key57575': 'value91801',
    'key57955': 'value95831',
    'key63680': 'value76258',
},
    {
    'id': 17527475341877,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jill Ross',
    'address': '15080 Bennett Turnpike Suite 470\nSilvafurt, VI 93790',
    'text': 'Read station yeah test amount. Find on interesting out particular animal. Set through home help respond seek admit.\nResource paper again commercial everything. Traditional else ago owner.',
    'email': 'zdougherty@example.com',
    'phone_number': '001-871-745-6200',
    'json': {
    'name': 'Jacob Carter',
    'address': '6730 Gomez Fords Apt. 002\nNorth Kristin, GU 77134',
},
    'key11146': 'value62792',
},
    {
    'id': 17527475341889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Michael Campos',
    'address': '1162 Diana Walks\nLarashire, CT 28213',
    'text': 'Affect seem different. Change by better others law.\nCity us full why culture. At marriage modern environmental stock.',
    'email': 'taylor30@example.com',
    'phone_number': '+1-674-414-2698x7909',
    'json': {
    'name': 'Lori Klein',
    'address': '523 Murphy Grove Suite 220\nNew Matthewside, AR 57042',
},
    'key11728': 'value46321',
    'key74909': 'value78139',
},
    {
    'id': 17527475341902,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Aaron Nelson',
    'address': 'USCGC Hayes\nFPO AA 75446',
    'text': 'Way cell full accept early draw commercial. Near deep within their stand ago. Two my many since.\nThought range another. You cover structure fill explain suddenly response. Store with charge might.',
    'email': 'ccampos@example.org',
    'phone_number': '869-211-8649x633',
    'json': {
    'name': 'Chase Chavez',
    'address': '55029 Arnold Fields\nLake Thomas, SD 80235',
},
    'key4871': 'value65903',
    'key27541': 'value4801',
    'key72649': 'value93514',
    'key79851': 'value76450',
},
    {
    'id': 17527475341920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Audrey Allen',
    'address': '6783 Obrien Light\nMeltonview, KY 16145',
    'text': 'Human cold stay garden. Recently team college choice.\nCamera medical especially often. Important they evening quite ten bit personal.',
    'email': 'linda23@example.net',
    'phone_number': '662.787.8310x4456',
    'json': {
    'name': 'Aaron Henry',
    'address': '6329 Dean Loaf Apt. 653\nAshleybury, MO 98804',
},
    'key11256': 'value84878',
    'key47294': 'value7585',
    'key21400': 'value16601',
    'key74737': 'value55504',
    'key36545': 'value81741',
    'key59480': 'value20293',
    'key72210': 'value2915',
},
    {
    'id': 17527475341938,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Luis Clark',
    'address': '943 Nancy Dale\nMatthewsfort, NV 24056',
    'text': 'Agreement lose in argue prepare catch prepare. Memory value unit serve including.\nHome risk material choose mean task significant. Event early imagine manager.',
    'email': 'xavier05@example.net',
    'phone_number': '001-248-553-2677',
    'json': {
    'name': 'Michael Thompson',
    'address': '01325 Allison Light Suite 760\nEast Kevin, AL 88213',
},
    'key95567': 'value40355',
    'key24254': 'value26129',
    'key86581': 'value24602',
},
    {
    'id': 17527475341957,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Nicole Romero',
    'address': '31396 Brandon Coves\nNealfort, OR 26014',
    'text': 'Company wait our wall land. Thousand field early old stage nearly. Soon player similar job.\nIndeed maintain teacher. Community write report store process. Name finish until right husband scene.',
    'email': 'knightnatasha@example.net',
    'phone_number': '9716391481',
    'json': {
    'name': 'Jessica Brown',
    'address': '1678 Kenneth Roads Apt. 773\nMichaelshire, VA 45690',
},
    'key81588': 'value65439',
    'key93904': 'value13338',
    'key44590': 'value30158',
    'key63940': 'value90075',
    'key50591': 'value12541',
    'key98653': 'value75521',
},
    {
    'id': 17527475341982,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Malik Potts',
    'address': '0251 Stephanie Motorway\nJenniferhaven, CT 96085',
    'text': 'Kitchen garden work drop argue. Level might white perhaps discuss third. Summer be himself sing call parent.\nCall often generation child stand now. Child ever talk no way.',
    'email': 'travis19@example.org',
    'phone_number': '719-652-8974',
    'json': {
    'name': 'Peter Ochoa',
    'address': '326 Mary Center\nNew Stevenland, IL 92372',
},
    'key53261': 'value52396',
    'key96613': 'value50631',
    'key43269': 'value95573',
    'key8191': 'value75808',
    'key74488': 'value230',
    'key80452': 'value86235',
    'key78993': 'value75881',
    'key36442': 'value53368',
},
    {
    'id': 17527475341999,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Todd Cohen',
    'address': '97634 Jill Path Suite 072\nPort James, AR 21533',
    'text': 'Candidate before gas. Expect southern change serve. Hour friend approach suddenly.\nPressure good away evidence. Share raise within month. Yard parent either mention bit into similar.',
    'email': 'larry02@example.net',
    'phone_number': '914-217-0275',
    'json': {
    'name': 'Kendra Hines',
    'address': 'USNS Delgado\nFPO AA 17191',
},
    'key53874': 'value31193',
    'key43773': 'value56145',
    'key29544': 'value93587',
    'key88344': 'value80568',
    'key93088': 'value68802',
    'key83259': 'value19349',
    'key17485': 'value10825',
    'key413': 'value37945',
    'key19267': 'value4095',
},
    {
    'id': 17527475342012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Nicole Murray',
    'address': '72223 Adam Row Suite 854\nEast Stephaniebury, AZ 63143',
    'text': 'Answer much throughout customer cup. Day generation decide site. Standard investment figure sport home particular.\nA year break imagine executive safe. Away might tell game last.',
    'email': 'tracygonzalez@example.com',
    'phone_number': '(380)762-9014x68549',
    'json': {
    'name': 'Eduardo Hall',
    'address': '963 Bailey Forge\nNew Brandy, MD 32681',
},
    'key945': 'value19212',
    'key99838': 'value29868',
    'key61124': 'value1816',
},
    {
    'id': 17527475342025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Jennifer Dunn',
    'address': '940 Nathaniel Locks Apt. 119\nDavidton, IA 75262',
    'text': 'Practice somebody whole cut occur. Statement step dark old.\nHistory structure herself process theory future. Congress treat design level treat others. Action old pay interesting state door those.',
    'email': 'bethany36@example.org',
    'phone_number': '738-997-7208x96026',
    'json': {
    'name': 'Lisa Mccarthy',
    'address': '5780 Ralph Manors Apt. 956\nNew Nicholas, PR 08332',
},
    'key51304': 'value48176',
    'key79446': 'value97941',
    'key72787': 'value56632',
    'key18952': 'value69880',
    'key2227': 'value93568',
},
    {
    'id': 17527475342039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Tracy Gibbs',
    'address': '8377 Kristina Canyon Suite 020\nJonathanfurt, FL 13767',
    'text': 'Size box seek speech pattern on spring any.\nNothing pressure environment federal shoulder. Point process concern suddenly.',
    'email': 'rodriguezbrandon@example.com',
    'phone_number': '551.565.9965x1833',
    'json': {
    'name': 'Dennis Stephenson',
    'address': '3105 Graham Divide\nNew Brittanyville, SC 35853',
},
    'key68129': 'value37936',
    'key10051': 'value98177',
    'key19920': 'value37772',
    'key26695': 'value83498',
    'key31673': 'value41343',
},
    {
    'id': 17527475342053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Patricia Morales',
    'address': 'USS Black\nFPO AA 34484',
    'text': 'Entire change pay not radio current goal. Drug baby rest begin international near suffer simple. International still listen modern various lead whom.',
    'email': 'ismith@example.net',
    'phone_number': '226-293-5100x789',
    'json': {
    'name': 'Kevin King',
    'address': '543 Denise Camp Suite 430\nNorth Diana, IA 64829',
},
    'key59533': 'value65176',
    'key30230': 'value45972',
    'key94963': 'value18894',
    'key37895': 'value83529',
},
    {
    'id': 17527475342065,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Scott Williams',
    'address': 'USNS Waters\nFPO AE 55018',
    'text': 'Sound personal Congress plan beautiful enjoy. Strategy yard wall often. Stock stay off great people everyone everyone.\nWhose consider require blue which total. Walk name lose police white.',
    'email': 'jenniferjoseph@example.org',
    'phone_number': '571.893.4731x246',
    'json': {
    'name': 'Mary Mason',
    'address': '20083 Christensen Street Apt. 853\nPrestonborough, MP 22212',
},
    'key28608': 'value52862',
    'key15894': 'value70918',
    'key33691': 'value9424',
    'key17719': 'value72191',
    'key59333': 'value76897',
    'key7915': 'value16872',
    'key83695': 'value99354',
    'key9510': 'value47106',
    'key79870': 'value66003',
},
    {
    'id': 17527475342079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Lisa Espinoza',
    'address': '46401 Derrick Dam Suite 730\nNorth Jeffrey, VT 01125',
    'text': 'Employee read civil.\nEasy along rule yet. Test guy leader look official amount practice role.\nAccording investment probably cost. Her decide source price east enough. Win college human create their.',
    'email': 'zramirez@example.org',
    'phone_number': '+1-925-844-1729x99819',
    'json': {
    'name': 'Becky Roach',
    'address': 'USNS Richardson\nFPO AE 84093',
},
    'key74533': 'value4615',
    'key5557': 'value87105',
    'key54665': 'value34488',
    'key83663': 'value59626',
    'key57955': 'value68860',
    'key611': 'value2854',
    'key22756': 'value62078',
    'key89284': 'value47541',
    'key23989': 'value92208',
},
    {
    'id': 17527475342091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Michael Jacobs',
    'address': '51107 Evans Fields\nSouth Jennaport, ME 34809',
    'text': 'Hand develop work however people why. Usually message boy. Determine five source leave leg whose.\nKeep realize outside statement kid cell hot loss. City radio democratic in. Face glass parent fine.',
    'email': 'banderson@example.com',
    'phone_number': '+1-204-830-6216x25661',
    'json': {
    'name': 'Dillon Goodwin',
    'address': '105 John Orchard\nSouth Jamesfort, IL 42985',
},
    'key7852': 'value40636',
    'key20873': 'value92034',
    'key76546': 'value86819',
    'key52935': 'value90457',
    'key53051': 'value74787',
    'key80444': 'value73342',
    'key98504': 'value54909',
    'key99753': 'value32568',
    'key94677': 'value64027',
},
    {
    'id': 17527475342103,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Diana Robinson MD',
    'address': '904 Ariel Gateway\nChavezside, UT 27995',
    'text': 'Face speech own goal around left energy. More skin draw reach record.\nTravel meet manager item without food mention. Prove not right rock. Raise early point us draw.\nDoctor true think how artist.',
    'email': 'ahuff@example.com',
    'phone_number': '474-660-8222x4581',
    'json': {
    'name': 'Lauren Young',
    'address': '76484 Miller Track\nNorth Josephburgh, ME 66839',
},
    'key76944': 'value310',
    'key58168': 'value36784',
    'key49348': 'value44275',
    'key98254': 'value33195',
    'key7449': 'value86613',
},
    {
    'id': 17527475342115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Hector Bowers',
    'address': '6207 Burns Turnpike Suite 615\nDanielview, FL 25484',
    'text': 'Or certainly trade human box most. Draw none enjoy the subject.\nEspecially family return TV Democrat direction senior. Model entire direction general.',
    'email': 'boylejulie@example.org',
    'phone_number': '+1-644-819-4230x292',
    'json': {
    'name': 'Kristin Lamb',
    'address': '251 Stuart Dam Suite 164\nGreenport, OR 70164',
},
    'key24199': 'value16956',
    'key54749': 'value27293',
},
    {
    'id': 17527475342127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Christina Chaney',
    'address': '898 Kane Lakes\nLake Josephfurt, VA 24081',
    'text': 'Behind rock moment occur east away PM. Leg tonight station. Care quite scene back.\nWhile at center phone live year. The education program participant. They entire cause fine group place.',
    'email': 'alexandragarcia@example.net',
    'phone_number': '+1-322-426-4971x718',
    'json': {
    'name': 'Ryan Delgado',
    'address': '8193 Carter Village\nShannonbury, MH 47364',
},
    'key81793': 'value59762',
    'key15177': 'value19513',
    'key16727': 'value83510',
    'key94094': 'value54535',
    'key14167': 'value39828',
    'key14128': 'value98427',
    'key64974': 'value61671',
    'key15286': 'value33803',
    'key64475': 'value89683',
},
    {
    'id': 17527475342140,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Kimberly Thompson',
    'address': '98256 Martinez Trail Apt. 956\nNorth Kristiborough, WV 16262',
    'text': 'Share science everything seven share none staff. Surface particular sing wrong what wife able. Republican rest husband style relationship. Likely quickly prevent chance.',
    'email': 'kylekrueger@example.com',
    'phone_number': '899-717-3207x032',
    'json': {
    'name': 'Laura Contreras',
    'address': '42903 Dennis Stravenue Apt. 390\nPort Kristen, MO 79226',
},
    'key28811': 'value72074',
    'key87693': 'value24962',
    'key4829': 'value73391',
    'key1552': 'value6928',
    'key97834': 'value14100',
    'key69432': 'value95654',
    'key42279': 'value10862',
},
    {
    'id': 17527475342151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jessica Hall',
    'address': '6515 Porter Expressway\nLake Jasonport, MO 91721',
    'text': 'Produce student popular.\nCompany hit degree we past interest network. Book service rate. Health organization under.',
    'email': 'beardamanda@example.com',
    'phone_number': '+1-805-933-8486x504',
    'json': {
    'name': 'Megan Atkins',
    'address': '5865 Booth Shoal Suite 463\nDaniellechester, MP 14339',
},
    'key3255': 'value30805',
    'key50739': 'value47293',
},
    {
    'id': 17527475342163,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Rachael Davis',
    'address': 'PSC 7745, Box 4572\nAPO AP 48394',
    'text': 'No practice market something job. Agreement fund green believe suffer glass.\nLive which head rule. You boy hard not shoulder page kid. Operation television customer smile scene nearly lose.',
    'email': 'jamesparrish@example.com',
    'phone_number': '811-540-8332',
    'json': {
    'name': 'Ashley Wise',
    'address': '83075 Dustin Meadow Suite 323\nSmallland, CT 92314',
},
    'key560': 'value84363',
    'key74054': 'value57741',
},
    {
    'id': 17527475342173,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Roberto Patterson',
    'address': 'PSC 5742, Box 7392\nAPO AE 37432',
    'text': 'Affect hospital remain magazine major situation ask. Prepare five discussion hope job gun. Thank feel various cultural country age.\nHe occur mind avoid maybe. Address scientist result war.',
    'email': 'kristincampbell@example.org',
    'phone_number': '(315)565-3890x36561',
    'json': {
    'name': 'Dawn Walker',
    'address': '1054 Shelley Drive\nWest Nancyfort, WY 20439',
},
    'key1038': 'value75067',
    'key40678': 'value57544',
    'key12505': 'value31424',
    'key70490': 'value69901',
    'key67852': 'value55557',
    'key57408': 'value2348',
    'key1442': 'value23819',
    'key57453': 'value32303',
    'key13092': 'value55118',
},
    {
    'id': 17527475342182,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Cheryl Blanchard',
    'address': '8989 Garcia Flat\nNew Davidside, NM 73266',
    'text': 'Rise thousand finish every defense whole. Mean level small sign much stage.\nCareer later single. Air series nature food media skill food. Maintain whom suffer kind ready fear church.',
    'email': 'owalker@example.net',
    'phone_number': '893.756.9253x85185',
    'json': {
    'name': 'Eric Dunn',
    'address': '9808 David Center Apt. 898\nRichardtown, AL 01353',
},
    'key44127': 'value87165',
    'key81457': 'value80253',
    'key87093': 'value34231',
    'key5496': 'value1928',
    'key75667': 'value10494',
    'key38650': 'value78375',
    'key50102': 'value93846',
    'key42882': 'value36749',
    'key34151': 'value33693',
    'key40253': 'value92027',
},
    {
    'id': 17527475342193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Diana James',
    'address': '72298 Jennifer Spurs Suite 753\nNew Heathermouth, NM 69322',
    'text': 'Attorney different computer half truth Republican. Available forward issue black help wall. Teach hold behind century response.\nBall data how save. Few man this people effort wind development world.',
    'email': 'andrewbauer@example.com',
    'phone_number': '673.524.5511x80714',
    'json': {
    'name': 'Tiffany Bates',
    'address': '38772 Karen Summit\nLake Nicole, FM 55252',
},
    'key70958': 'value68673',
    'key62080': 'value4786',
    'key22974': 'value95616',
    'key62540': 'value7859',
    'key32454': 'value82639',
    'key53521': 'value31957',
    'key26090': 'value99599',
    'key48788': 'value61992',
    'key8941': 'value87412',
    'key36687': 'value14548',
},
    {
    'id': 17527475342205,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Daniel Miller',
    'address': '02064 Denise Spur Suite 642\nPayneland, RI 80172',
    'text': 'Car imagine popular book three happen. Discover the brother wall suggest.\nProject history from. Next fish speak national. Occur skin without here yeah during something.',
    'email': 'fosterkathleen@example.net',
    'phone_number': '482.734.4540x3750',
    'json': {
    'name': 'Rachel Frey',
    'address': '27096 Russell Wall Apt. 260\nSouth Michael, CA 44939',
},
    'key49281': 'value16248',
    'key31818': 'value77972',
    'key85126': 'value57244',
    'key41379': 'value79566',
    'key5181': 'value48726',
    'key23977': 'value69444',
    'key8344': 'value43136',
    'key88465': 'value57264',
    'key44092': 'value42926',
},
    {
    'id': 17527475342217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Dennis Tapia',
    'address': '96294 Wells Mission Apt. 519\nJessicaview, UT 18598',
    'text': 'Board including better mind itself. Point course play face report very marriage. Want yard matter.\nPolitical building floor attack tonight culture.',
    'email': 'jodi85@example.org',
    'phone_number': '697.900.1980x4297',
    'json': {
    'name': 'John Pennington',
    'address': '086 Walton Ferry Suite 954\nEast Danielle, IL 70042',
},
    'key50730': 'value22369',
    'key57697': 'value58614',
    'key17742': 'value59279',
    'key8962': 'value10590',
    'key76096': 'value58763',
    'key70593': 'value35711',
    'key80408': 'value76337',
    'key25921': 'value5217',
},
    {
    'id': 17527475342228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Kristen Chase',
    'address': '5040 Williams Road Suite 895\nMelissamouth, ME 31191',
    'text': 'Season success establish want contain able same. Study resource end buy long.\nRequire look might generation answer with. Coach really air us when air political cover.',
    'email': 'ramosnicholas@example.com',
    'phone_number': '(953)601-7983',
    'json': {
    'name': 'Randy Underwood',
    'address': '700 Nathaniel Square\nLake Johnland, VI 79634',
},
    'key87096': 'value11394',
    'key9202': 'value64109',
    'key52056': 'value55631',
    'key89076': 'value75231',
},
    {
    'id': 17527475342239,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Christopher Quinn',
    'address': '6102 Reyes Squares\nHermanmouth, MA 71209',
    'text': 'Amount market professional Mr. Suffer way any.\nShow military page. Open type cut no environment animal mission. Box toward can consumer city agreement.',
    'email': 'thenry@example.com',
    'phone_number': '001-406-443-0072x333',
    'json': {
    'name': 'Zachary Roberts',
    'address': '54442 Holland Avenue\nColleenborough, OR 94412',
},
    'key10463': 'value24724',
    'key94152': 'value67022',
    'key3941': 'value94678',
    'key38531': 'value77642',
    'key7520': 'value5260',
    'key97884': 'value99523',
},
    {
    'id': 17527475342250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Jaime Johnson',
    'address': '3122 Edwards Way Suite 291\nNew Katie, CO 15827',
    'text': 'Consider article white seat level above.\nHelp better industry door. Conference their country should quite. Along easy particular gun history.',
    'email': 'mmoreno@example.com',
    'phone_number': '809.496.0027x27766',
    'json': {
    'name': 'Kelly Hampton',
    'address': '572 Mahoney Lakes Suite 902\nWest Carmenstad, GU 37829',
},
    'key60425': 'value95865',
    'key78586': 'value68078',
    'key91746': 'value89353',
    'key76762': 'value84768',
    'key69173': 'value26902',
    'key5688': 'value41061',
    'key36434': 'value99345',
    'key57599': 'value91675',
    'key91938': 'value53308',
    'key26546': 'value13821',
},
    {
    'id': 17527475342261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Erika Lee',
    'address': '543 Robert Canyon Apt. 532\nPort Valeriehaven, AZ 84575',
    'text': 'Serious so outside and. Away city begin responsibility culture worry.\nLeg hot later interview set worry. Friend guy attention apply set.',
    'email': 'clarkkenneth@example.org',
    'phone_number': '664-711-7182',
    'json': {
    'name': 'Christopher Moran',
    'address': '3954 Matthew Well Suite 541\nDukeshire, MH 92916',
},
    'key6994': 'value40871',
    'key84887': 'value45000',
    'key59727': 'value25265',
    'key85634': 'value5633',
    'key93500': 'value2992',
    'key26363': 'value79680',
},
    {
    'id': 17527475342273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Cynthia Anderson',
    'address': '8689 Jose Station\nJohnsonchester, TX 44374',
    'text': 'Material firm song magazine government class glass. Set though forward official cell half item.\nBig officer newspaper worry include. Better mission answer blue follow we off.',
    'email': 'howardantonio@example.com',
    'phone_number': '7337031870',
    'json': {
    'name': 'Richard Sosa',
    'address': '5350 Ian Shore\nLeahchester, WA 34341',
},
    'key73517': 'value55985',
    'key26381': 'value80570',
    'key27802': 'value71002',
},
    {
    'id': 17527475342285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Thomas Jimenez',
    'address': '15821 Jessica Field Suite 574\nNew Scott, NJ 15213',
    'text': 'Tell me edge production style population. Avoid left and wrong street.\nThank white media green his authority. Its hot tough. Necessary blood resource election.',
    'email': 'tammy03@example.org',
    'phone_number': '457-252-7959',
    'json': {
    'name': 'Kristen Price',
    'address': 'Unit 1925 Box 5989\nDPO AA 42760',
},
    'key4858': 'value95296',
    'key28079': 'value15577',
},
    {
    'id': 17527475342293,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jamie Hart',
    'address': '585 Randy Corner Apt. 936\nKennethbury, PW 30045',
    'text': 'Other present maintain full under fire himself. Suffer back individual station son mother. Ahead low develop. Indicate ever identify east inside employee.',
    'email': 'sharon82@example.net',
    'phone_number': '001-576-291-7195',
    'json': {
    'name': 'Paul Wilson MD',
    'address': '45584 Lawson Way\nNorth Stephen, MH 38558',
},
    'key86074': 'value80735',
    'key90939': 'value51644',
    'key28630': 'value83213',
    'key43080': 'value5134',
    'key85786': 'value37523',
    'key50749': 'value58289',
},
    {
    'id': 17527475342303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Leonard Martinez',
    'address': '932 Gross Spur\nNorth David, AR 16609',
    'text': 'Water hundred consumer kind morning enter. Expert high throw current real.\nApply watch ago leave late. Easy able read white place business bag. Speech all cultural treat tough feel.',
    'email': 'andrew02@example.net',
    'phone_number': '632-821-0866',
    'json': {
    'name': 'Daniel Miranda',
    'address': '91722 Huber Mountain\nWest Amyland, GA 69464',
},
    'key24448': 'value96599',
    'key17341': 'value37077',
    'key10348': 'value42035',
    'key1551': 'value50860',
    'key93501': 'value85645',
    'key62793': 'value77879',
},
    {
    'id': 17527475342314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Dustin Cook',
    'address': '6680 Steele Mountains Apt. 798\nLake Meganstad, DC 18043',
    'text': 'Tv she institution most I study medical. Between hit out successful. Hope compare force he left focus.',
    'email': 'ojones@example.net',
    'phone_number': '001-734-791-8564x6860',
    'json': {
    'name': 'Rhonda Lawson',
    'address': '449 Sarah Meadows\nDebbiefurt, RI 86001',
},
    'key86937': 'value23987',
    'key76003': 'value58437',
    'key24527': 'value32862',
    'key80657': 'value21439',
    'key75732': 'value7600',
    'key52900': 'value18920',
    'key34139': 'value70755',
    'key5775': 'value34823',
},
    {
    'id': 17527475342325,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Briana Rodriguez',
    'address': '029 Jones Lane\nSouth Dillon, KS 94604',
    'text': 'Effort first activity six question position should. Mean him fly I. However money your visit.\nThis chance build save reflect. Move teacher class suffer. Simply mother much single upon range another.',
    'email': 'zthomas@example.org',
    'phone_number': '(831)353-9870x70380',
    'json': {
    'name': 'Michael Miranda',
    'address': '965 Gonzalez Bypass\nSalazarland, ME 12694',
},
    'key16762': 'value77838',
    'key53417': 'value24896',
},
    {
    'id': 17527475342336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jessica Morrow',
    'address': '5878 Tracy Forks Apt. 055\nNew Sethport, CA 77432',
    'text': 'Dream party service guess area reality. If throughout student rock fight cover.\nOthers budget successful chair product table. Source parent thus small partner little for.',
    'email': 'glassmary@example.com',
    'phone_number': '001-792-614-4498x8396',
    'json': {
    'name': 'Derek Monroe',
    'address': '383 Christian Pines\nGravestown, PW 73264',
},
    'key4536': 'value78227',
    'key7658': 'value46045',
    'key11280': 'value57805',
    'key89197': 'value93520',
    'key54072': 'value79829',
    'key67113': 'value42448',
    'key76118': 'value98010',
    'key38782': 'value18198',
},
    {
    'id': 17527475342347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Katherine Wright',
    'address': '007 Bruce Square Suite 872\nLake Valerieborough, RI 71883',
    'text': 'Quickly between manager style. Home during run big describe week.\nSingle month book student mother mean nearly. Need fish south go scientist tough. Plant prepare too.\nYour around since reduce.',
    'email': 'esmith@example.org',
    'phone_number': '+1-489-307-8139x17149',
    'json': {
    'name': 'John Ibarra',
    'address': 'PSC 8849, Box 3978\nAPO AA 08826',
},
    'key60050': 'value6357',
},
    {
    'id': 17527475342356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Matthew Ross',
    'address': '117 Pruitt Road\nMichaelland, OR 56863',
    'text': 'Prove above final news American authority fund. Later approach media usually. South attorney according increase maintain miss.',
    'email': 'douglas23@example.org',
    'phone_number': '001-804-350-7302x552',
    'json': {
    'name': 'Bethany Cruz',
    'address': '7260 Reed Trafficway\nPort David, CT 08393',
},
    'key37140': 'value9821',
    'key94442': 'value72595',
    'key2806': 'value28552',
    'key62630': 'value42490',
    'key64895': 'value55821',
},
    {
    'id': 17527475342366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'William Gonzalez',
    'address': '3426 Hudson View\nSouth Timothyton, PR 74153',
    'text': 'Third other care. Wonder human during wait. Whether while defense middle.\nConference school large per you TV. Rest success store evidence professional five mean.',
    'email': 'michaelsnow@example.org',
    'phone_number': '631-907-7602',
    'json': {
    'name': 'Nicholas Schwartz',
    'address': '7286 Angela Keys\nLake Danabury, NJ 92932',
},
    'key92705': 'value58273',
    'key79431': 'value72942',
    'key18093': 'value97523',
},
    {
    'id': 17527475342378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Thomas Moore',
    'address': '408 Lloyd Views Suite 653\nHendersonborough, CO 19955',
    'text': 'Beyond smile site lay age. Where large something message language office.\nWhat thus sit loss during. Discuss wall region suggest ability friend join.',
    'email': 'annacummings@example.com',
    'phone_number': '+1-827-906-3497x8308',
    'json': {
    'name': 'Raymond Rodriguez',
    'address': 'USNS Larson\nFPO AA 88605',
},
    'key29443': 'value81024',
    'key12783': 'value10919',
    'key78696': 'value26757',
    'key8537': 'value63700',
    'key59154': 'value77754',
    'key85916': 'value17864',
    'key59799': 'value26895',
},
    {
    'id': 17527475342388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mary Romero',
    'address': '09144 Elaine Rapids\nKathleenbury, AR 98059',
    'text': 'Ok responsibility wrong executive. Hear clear west training perform series positive. Something effort available character same science knowledge indeed.',
    'email': 'evansholly@example.net',
    'phone_number': '860.688.2262x3374',
    'json': {
    'name': 'Gregory Hampton',
    'address': '5604 Michael River Apt. 105\nNew Tommy, AR 26836',
},
    'key5756': 'value16294',
    'key11879': 'value9829',
    'key69052': 'value9298',
    'key50961': 'value96576',
    'key49302': 'value77023',
    'key10395': 'value69052',
    'key7987': 'value94059',
},
    {
    'id': 17527475342399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Jon Wilson',
    'address': '9822 John Summit\nMartineztown, LA 05053',
    'text': 'Large where investment teach whether. Get really factor great Republican parent bill. Indicate century research fund alone determine.',
    'email': 'millerkristina@example.net',
    'phone_number': '878.637.5811x6153',
    'json': {
    'name': 'Jessica Gray',
    'address': '551 Cody Valley\nEast Jamesbury, NJ 03187',
},
    'key95879': 'value26447',
},
    {
    'id': 17527475342410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Rhonda Smith',
    'address': '4290 Seth Port\nSerranostad, MD 83954',
    'text': 'Wide bag performance effect edge.\nFederal call build major.\nMonth million glass article role western. Company fight business million.\nBillion beautiful through kid.',
    'email': 'dustinharris@example.org',
    'phone_number': '789-375-3316x583',
    'json': {
    'name': 'Jason Martin',
    'address': '217 David Skyway Suite 412\nNorth Seanport, VT 90837',
},
    'key26339': 'value77651',
    'key12451': 'value34774',
    'key39107': 'value66577',
    'key30104': 'value30707',
    'key3682': 'value91425',
    'key68453': 'value75209',
    'key26973': 'value34951',
},
    {
    'id': 17527475342421,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Sean Randall Jr.',
    'address': '5926 Jessica Tunnel\nNew Matthew, MT 58200',
    'text': 'Follow ahead dog probably Democrat ball. Anyone table magazine along artist program event.\nFinal skill art chair executive apply. Woman week writer month store. Color popular address local seat.',
    'email': 'roberthuerta@example.org',
    'phone_number': '593.961.6274',
    'json': {
    'name': 'Jon Wilson',
    'address': '4639 Gabriel Trail\nSouth Joel, MI 79716',
},
    'key46328': 'value8213',
    'key15020': 'value73160',
    'key21235': 'value12351',
    'key97801': 'value86747',
    'key96634': 'value43548',
    'key12510': 'value98556',
    'key16627': 'value92907',
    'key23104': 'value56075',
    'key65052': 'value48234',
    'key98868': 'value25212',
},
    {
    'id': 17527475342432,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Joseph Mendoza',
    'address': '2842 Ashley Camp Apt. 740\nNew Christianstad, KY 13170',
    'text': 'To PM change idea newspaper wall. Within pay scientist future compare administration.\nMaterial all owner play free. Congress guess truth.',
    'email': 'phillipsutton@example.com',
    'phone_number': '437.444.6280',
    'json': {
    'name': 'Bryan Baker',
    'address': '29185 Perez Pine\nLake Bethany, CA 11270',
},
    'key82250': 'value54430',
},
    {
    'id': 17527475342443,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Lori Snow',
    'address': '298 Lucas Trace\nWest Kennethside, KY 05774',
    'text': 'Stand simple soldier billion. Drug develop test. Card rock foot property nice total.\nLight opportunity into stock more size.',
    'email': 'freyes@example.com',
    'phone_number': '8843503321',
    'json': {
    'name': 'Lauren Prince',
    'address': '8263 Rollins Flat Apt. 929\nChristophermouth, CO 36624',
},
    'key1289': 'value4105',
    'key11902': 'value65938',
    'key37688': 'value33401',
    'key86787': 'value9261',
    'key93519': 'value88277',
    'key8838': 'value27004',
},
    {
    'id': 17527475342454,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Kim Best',
    'address': 'USNS Webb\nFPO AA 84841',
    'text': 'Analysis control general sense. Major student give thank new list along. Above increase week threat pass several none. Difference wide lose party woman member.',
    'email': 'matthewmoore@example.net',
    'phone_number': '(505)902-2075',
    'json': {
    'name': 'Jason Mccarthy DDS',
    'address': '298 Renee Inlet\nLittletown, AK 25839',
},
    'key71334': 'value50575',
    'key56627': 'value21108',
    'key60501': 'value37106',
    'key56304': 'value85553',
    'key49102': 'value52020',
    'key45148': 'value38386',
    'key78492': 'value20119',
},
    {
    'id': 17527475342464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Joshua Brown',
    'address': '962 Nicole Stream\nGraystad, MT 79720',
    'text': 'Hospital reason form bit pull staff. Fear recently open treat receive ask study. Hotel paper member catch season.',
    'email': 'richardsmith@example.com',
    'phone_number': '+1-727-653-0174x18138',
    'json': {
    'name': 'Krystal Mullins',
    'address': '59603 Bowman Burg Apt. 166\nElizabethville, HI 08357',
},
    'key55574': 'value67027',
    'key12398': 'value53227',
    'key53246': 'value5987',
    'key31611': 'value32269',
    'key33299': 'value22476',
    'key56477': 'value76340',
    'key48640': 'value29395',
},
    {
    'id': 17527475342476,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Matthew Davidson',
    'address': '851 Laurie Port\nEast Sharon, AS 46292',
    'text': 'Act ten management eat company level. Enter everything each father decide piece finish. Condition local follow raise beyond soldier nice.',
    'email': 'heatherhubbard@example.com',
    'phone_number': '(486)966-2881x17469',
    'json': {
    'name': 'Patrick Black',
    'address': 'Unit 9424 Box 4899\nDPO AA 28186',
},
    'key10466': 'value80984',
    'key16455': 'value31279',
    'key11024': 'value17155',
    'key5564': 'value86992',
    'key30805': 'value27428',
    'key5433': 'value77799',
    'key50248': 'value79677',
    'key99357': 'value90105',
    'key83127': 'value81740',
    'key87193': 'value41872',
},
    {
    'id': 17527475342485,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Stephanie Hernandez',
    'address': '984 Ashley Keys\nStevenchester, MT 65142',
    'text': 'Owner message speak. Be push wall deal age gun along.\nThat cover bed alone serious. Seat benefit how. Mother prove wife born whose.',
    'email': 'zsmith@example.com',
    'phone_number': '001-783-390-3283',
    'json': {
    'name': 'William Myers',
    'address': '70102 Anthony Walk Apt. 046\nRandallberg, NJ 36379',
},
    'key47877': 'value65008',
    'key15305': 'value29035',
    'key5727': 'value23709',
    'key77530': 'value55886',
    'key34385': 'value47265',
    'key38847': 'value90103',
    'key21468': 'value36264',
},
    {
    'id': 17527475342495,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Claire Stewart',
    'address': '374 Dustin Mission Suite 423\nPort Whitney, MD 69613',
    'text': 'Threat very change than teach research hospital. Trial modern sell wait drug receive interesting.\nChoice least else image western answer.',
    'email': 'john43@example.net',
    'phone_number': '001-560-723-9044x305',
    'json': {
    'name': 'Gina Williams',
    'address': '878 Kari Glens Apt. 599\nCarlsonfort, RI 87618',
},
    'key36681': 'value444',
    'key18504': 'value61900',
    'key62962': 'value34701',
    'key74519': 'value92467',
    'key97217': 'value43839',
    'key15356': 'value90624',
},
    {
    'id': 17527475342505,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jeffrey Smith',
    'address': '4153 Karen Trail Apt. 284\nPort Sherry, OR 11829',
    'text': 'Tonight computer long. Computer watch yourself write drop. Ability bad senior. Clearly chair set series service news offer.',
    'email': 'annahorton@example.net',
    'phone_number': '3757970877',
    'json': {
    'name': 'Amanda Sampson',
    'address': '793 Thompson Falls\nJaneberg, WA 13113',
},
    'key832': 'value37321',
    'key61227': 'value30143',
    'key99908': 'value78860',
    'key59240': 'value29191',
    'key77822': 'value15180',
    'key30929': 'value81811',
    'key56892': 'value23354',
},
    {
    'id': 17527475342516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Brittany Fuentes',
    'address': 'USCGC Shelton\nFPO AE 49542',
    'text': 'Loss develop administration method threat him. Field personal defense.\nCentral today our become baby plan piece. Well better national movie sing run above.\nSuggest anything again.',
    'email': 'stacynguyen@example.com',
    'phone_number': '001-537-299-5999x619',
    'json': {
    'name': 'Darrell Gutierrez',
    'address': '78546 Clifford Forks Apt. 958\nShannonville, WV 79839',
},
    'key92982': 'value76784',
    'key29201': 'value40377',
    'key29107': 'value31673',
    'key79696': 'value65941',
    'key25509': 'value35762',
},
    {
    'id': 17527475342526,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Michele Evans',
    'address': '38124 Ricardo Circles\nSherryshire, PA 48660',
    'text': 'Available leave skill environment sister safe those. Rock article agree one.\nInternational positive education feel down sense. Air fire TV issue example.',
    'email': 'becky00@example.org',
    'phone_number': '313-847-7464x3553',
    'json': {
    'name': 'Kenneth Montgomery',
    'address': '0846 Joanna Pines\nNew Randy, PW 23934',
},
    'key19992': 'value83090',
    'key25771': 'value42075',
    'key11797': 'value45429',
    'key28254': 'value58242',
},
    {
    'id': 17527475342536,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'David Kline',
    'address': '4735 Brandon Trail\nAngelatown, AS 05470',
    'text': 'Decision less people fund father role road. Just when collection support very.\nDream education real theory nature couple. Training culture keep prevent none ask together. Coach feel morning quite.',
    'email': 'xjackson@example.net',
    'phone_number': '001-350-926-5594',
    'json': {
    'name': 'John Gray',
    'address': '24467 Jillian Trail\nJenkinsborough, GA 97243',
},
    'key55093': 'value50109',
    'key92461': 'value9658',
    'key24098': 'value91473',
    'key68719': 'value10853',
},
    {
    'id': 17527475342546,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Mr. Nicholas Klein',
    'address': '74669 Ewing Brook Apt. 552\nVegaburgh, KY 68360',
    'text': 'Value start strategy often too thought as. Total capital social.\nOutside scientist along pull. Easy cost break. Long seven always night of discussion.',
    'email': 'piercelori@example.net',
    'phone_number': '(870)491-6277',
    'json': {
    'name': 'Julia Green',
    'address': '795 Anderson Place\nNew Tiffany, ND 85363',
},
    'key783': 'value2844',
    'key26795': 'value50694',
    'key4805': 'value44184',
    'key25554': 'value61153',
},
    {
    'id': 17527475342558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'James Stevens',
    'address': '045 Tony Radial\nEast Shannon, MT 78561',
    'text': 'Look across song land. Arm list figure cultural lot scene.',
    'email': 'steven31@example.com',
    'phone_number': '265-412-2417',
    'json': {
    'name': 'Christopher Cruz',
    'address': '26687 John Stream Apt. 822\nEast Teresaport, IN 73438',
},
    'key3142': 'value31487',
    'key39316': 'value98242',
    'key8073': 'value33759',
},
    {
    'id': 17527475342568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Madison Evans',
    'address': '92447 Wiley Street Suite 897\nSullivanchester, CA 66429',
    'text': 'Prepare tend they by score music commercial.\nEffort never employee follow scientist particular hold. Happy leave treat soon.\nBlue situation task especially stock pressure. Specific build view most.',
    'email': 'dwallace@example.org',
    'phone_number': '9474327913',
    'json': {
    'name': 'Dylan Powell',
    'address': '6144 Timothy Ranch\nAnthonymouth, PR 54547',
},
    'key75791': 'value47313',
    'key22114': 'value67565',
    'key10429': 'value6091',
    'key47809': 'value42149',
    'key61587': 'value45836',
    'key64229': 'value69138',
},
    {
    'id': 17527475342578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Edward Welch',
    'address': '814 Jessica Key Apt. 588\nNew Brookebury, NJ 48222',
    'text': 'Protect defense own purpose who appear as. Forget enter successful believe. Lawyer pressure any ability.\nCover might strategy son put. Professional though nearly anything someone.',
    'email': 'grace19@example.org',
    'phone_number': '281-370-5313',
    'json': {
    'name': 'Tracey Franklin',
    'address': '285 Samuel Lane\nEast Lauraburgh, DC 70060',
},
    'key28804': 'value53462',
},
    {
    'id': 17527475342588,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Virginia Norton',
    'address': '603 Lisa River Apt. 773\nCarrollmouth, WY 78090',
    'text': 'Book key movie find dog behavior why. Assume rock everything child.\nNearly remain science receive. Record concern summer crime.\nActivity moment well us. Occur week town conference scientist foot.',
    'email': 'stephen50@example.com',
    'phone_number': '+1-952-705-5087x032',
    'json': {
    'name': 'Mr. Ronald Sandoval',
    'address': '2288 Edwards Trail Suite 331\nWest Roberta, NV 44543',
},
    'key32470': 'value47343',
    'key70458': 'value1797',
    'key41243': 'value91616',
    'key95770': 'value92374',
    'key83535': 'value16662',
    'key87137': 'value89629',
    'key44579': 'value95066',
    'key18055': 'value82592',
},
    {
    'id': 17527475342599,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Christopher Boyer',
    'address': '4202 Mitchell Squares Suite 746\nNew Lisaland, IN 79350',
    'text': 'Million south husband official. Small seven situation actually policy. Maintain why ability bank hear player again.\nLast difference whether. Product reduce suggest speak. A final big.',
    'email': 'hvillarreal@example.com',
    'phone_number': '+1-662-254-2265x166',
    'json': {
    'name': 'Deanna Henderson',
    'address': '272 Sara Points Apt. 963\nEast Danny, MN 05398',
},
    'key245': 'value47238',
    'key61326': 'value85570',
    'key63880': 'value59068',
    'key22089': 'value79864',
    'key10495': 'value12274',
    'key82022': 'value5370',
    'key13893': 'value90833',
    'key45829': 'value15848',
},
    {
    'id': 17527475342610,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Nicholas Powers',
    'address': '17883 Vanessa Island\nLake Ashlee, MP 51909',
    'text': 'Total yes way reach manage not. Ahead hit north word.\nAgent side hotel no research check because.\nYourself thought term also member teacher lose. What strategy very edge.',
    'email': 'petersoncheryl@example.com',
    'phone_number': '(729)587-7280x557',
    'json': {
    'name': 'Gabrielle Perez',
    'address': 'USNS Abbott\nFPO AA 88395',
},
    'key14381': 'value58458',
    'key78176': 'value68139',
    'key16569': 'value36490',
    'key3049': 'value83612',
},
    {
    'id': 17527475342620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Christopher Farmer MD',
    'address': 'PSC 3872, Box 6073\nAPO AE 62573',
    'text': 'Court nice back word product receive all. Dream against include open student ask seek. World use visit reach teach make green traditional. End former nice decision.',
    'email': 'rowlandbarbara@example.com',
    'phone_number': '597-444-7488',
    'json': {
    'name': 'Kelsey Anderson',
    'address': '8780 Scott Crossroad\nNorth Michael, DC 66203',
},
    'key21285': 'value55890',
    'key43232': 'value42094',
    'key90633': 'value22247',
    'key16809': 'value2033',
    'key27145': 'value70315',
    'key27202': 'value37947',
    'key12634': 'value60294',
    'key22287': 'value7128',
},
    {
    'id': 17527475342629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Lauren Castro',
    'address': '80672 Palmer Freeway Apt. 698\nSouth Jasonville, NH 29523',
    'text': 'Bill plan chance collection. Key relate serious talk many prevent company. Any black understand trade wide edge weight idea. Stay no story north often feel full government.',
    'email': 'jonathonvazquez@example.net',
    'phone_number': '001-476-541-7184x750',
    'json': {
    'name': 'Melissa Lindsey',
    'address': '9041 George Pass\nGarciafort, CT 54602',
},
    'key6944': 'value76930',
    'key7192': 'value88552',
    'key8200': 'value32983',
    'key75138': 'value58924',
    'key35191': 'value64500',
    'key7124': 'value42250',
},
    {
    'id': 17527475342642,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Elizabeth Sullivan',
    'address': '749 Garcia Square Suite 953\nWest Thomasport, ME 27464',
    'text': 'Go affect walk rise until mission. Pick weight service sort.\nJob she management interest management. Firm air play three contain place soldier.',
    'email': 'christopherwilliams@example.org',
    'phone_number': '939.921.0437x2674',
    'json': {
    'name': 'Brittany Higgins',
    'address': '47868 Ward Glens\nNorth Maria, GA 75461',
},
    'key23064': 'value15486',
    'key37119': 'value20863',
    'key197': 'value44404',
    'key66570': 'value4998',
    'key44382': 'value53554',
    'key50745': 'value35704',
    'key54638': 'value79880',
    'key21329': 'value2177',
    'key90498': 'value83953',
},
    {
    'id': 17527475342656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Sandra Wright',
    'address': '952 Samuel Harbors\nMitchellview, AS 12898',
    'text': 'Describe I case rise stay film foreign. Operation to deal me leg realize.\nBecause special newspaper water better particular. Figure daughter receive defense. Low mother last often fish worker even.',
    'email': 'stewartmichelle@example.org',
    'phone_number': '(507)452-1527',
    'json': {
    'name': 'Timothy Johnson',
    'address': '8623 Carlson Motorway\nPort Gina, IL 39522',
},
    'key3348': 'value99242',
    'key23981': 'value47007',
    'key43381': 'value57426',
},
    {
    'id': 17527475342670,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Shannon Mooney',
    'address': '4481 Robbins Centers Suite 534\nEast Sandrachester, MO 16126',
    'text': 'Happy include church through available. Evening community short better social.\nSurface either turn but.',
    'email': 'sydneyhahn@example.org',
    'phone_number': '485-673-7485x23550',
    'json': {
    'name': 'Dave Barron',
    'address': '976 Green Motorway Apt. 872\nSouth Andrea, UT 59273',
},
    'key17291': 'value32034',
    'key60296': 'value7136',
    'key4823': 'value47239',
    'key2075': 'value95693',
    'key60564': 'value24698',
    'key40228': 'value49123',
},
    {
    'id': 17527475342688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Alejandro Ingram',
    'address': '621 Rogers Estate\nEast Audrey, OH 98642',
    'text': 'Tonight common grow guy field church. Difficult join require argue land. Congress everything different step including example past create.\nManager respond debate determine.',
    'email': 'wadetimothy@example.net',
    'phone_number': '211.273.8927x48972',
    'json': {
    'name': 'Shannon Gentry',
    'address': '109 Becker Ports Suite 903\nSouth Amanda, MD 95225',
},
    'key54181': 'value92916',
    'key8821': 'value13872',
    'key18326': 'value99698',
    'key27153': 'value45439',
    'key97647': 'value66303',
    'key98945': 'value53955',
    'key93416': 'value65930',
    'key53316': 'value62194',
},
    {
    'id': 17527475342709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Karen Hines',
    'address': '0924 Davis Circle\nSaraland, NE 66142',
    'text': 'Work herself cold amount create. Resource up crime simply lead.\nCurrent expert wonder authority. Travel brother else toward song opportunity top.',
    'email': 'adamsthomas@example.org',
    'phone_number': '794-450-9120x3124',
    'json': {
    'name': 'Rebecca Vasquez',
    'address': '7874 Mark Avenue Apt. 760\nLake Oscar, IL 64705',
},
    'key56241': 'value75411',
    'key78889': 'value90955',
    'key43898': 'value33235',
    'key65863': 'value21257',
    'key10401': 'value37950',
    'key11704': 'value35375',
    'key23624': 'value71199',
    'key49227': 'value81113',
    'key31245': 'value75443',
    'key69178': 'value34625',
},
    {
    'id': 17527475342724,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Gene Villanueva',
    'address': '61167 Thomas Stravenue Suite 755\nPort Kimberlyfurt, FM 40977',
    'text': 'Large consider compare like the let key ten. Since build south final.',
    'email': 'andrew27@example.net',
    'phone_number': '633.902.9117x58718',
    'json': {
    'name': 'Maria Horton',
    'address': '4637 Young Station\nAmandahaven, KS 45509',
},
    'key75189': 'value65470',
    'key73548': 'value65825',
    'key40365': 'value60698',
    'key73859': 'value13314',
    'key92878': 'value12577',
},
    {
    'id': 17527475342737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Donald Cook',
    'address': 'PSC 1504, Box 8183\nAPO AE 96691',
    'text': 'Learn accept left. Player close general bank both. Prevent son organization real box amount by.\nMajority reason land garden man control product. Thing sound including case usually gun sense.',
    'email': 'matthew66@example.net',
    'phone_number': '(200)270-6700x062',
    'json': {
    'name': 'Lynn Williams',
    'address': 'Unit 2406 Box 1390\nDPO AA 10971',
},
    'key39758': 'value88497',
    'key58773': 'value70395',
    'key32950': 'value67782',
    'key32197': 'value7172',
},
    {
    'id': 17527475342746,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Colin Acosta',
    'address': '57014 Clark Grove Suite 176\nLake Sheri, TN 91608',
    'text': 'Kind state particular hard so list. Always me kitchen choice. Prepare add dark.\nChoose my free job financial. Cover across wind green because person quite.',
    'email': 'smithdavid@example.net',
    'phone_number': '(584)892-4995',
    'json': {
    'name': 'Pam Nelson',
    'address': 'USNV Dalton\nFPO AA 52575',
},
    'key64146': 'value16140',
    'key63767': 'value21104',
},
    {
    'id': 17527475342759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Lisa Walker',
    'address': '8724 Amy Port Apt. 583\nEast Lauraport, DE 96077',
    'text': 'West certainly indicate turn. Budget age husband data race. Clearly system result culture.\nMoment budget action heart determine arrive only. Else important hot. You help cut none change enough.',
    'email': 'jamesharrison@example.net',
    'phone_number': '573.597.0014x539',
    'json': {
    'name': 'Omar Davis',
    'address': '1484 Krista Divide\nCordovashire, TN 83459',
},
    'key33314': 'value78925',
    'key57998': 'value57886',
    'key30734': 'value8835',
    'key20338': 'value4777',
    'key85942': 'value33203',
    'key72441': 'value45000',
    'key9444': 'value91393',
    'key12599': 'value15564',
},
    {
    'id': 17527475342773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Whitney Nguyen',
    'address': '7291 James Ranch\nSouth Heathermouth, PR 19410',
    'text': 'Series outside purpose month that. Plan rise compare friend authority social. Them anyone people public response ready. Process seek economic seat Republican really run.',
    'email': 'robertsondakota@example.com',
    'phone_number': '786-262-5695',
    'json': {
    'name': 'Kayla Gonzalez',
    'address': '764 Emily Ports Suite 976\nAaronport, OH 66632',
},
    'key21029': 'value77987',
    'key61290': 'value28330',
    'key78464': 'value63984',
    'key56132': 'value23936',
    'key4835': 'value56626',
    'key87259': 'value85532',
},
    {
    'id': 17527475342787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Mario Gray',
    'address': '5709 Mark Streets Apt. 815\nKimberlyton, KS 95778',
    'text': 'Gas whose admit soon knowledge religious a federal. Everyone stuff many various available medical sometimes low. Other plant dark do social lay best wait.',
    'email': 'imcknight@example.com',
    'phone_number': '7615559029',
    'json': {
    'name': 'Christine Henry',
    'address': 'PSC 7516, Box 3667\nAPO AA 66918',
},
    'key94191': 'value24205',
    'key34513': 'value59378',
    'key42044': 'value93585',
    'key22891': 'value22267',
    'key11917': 'value90692',
    'key21802': 'value63054',
    'key23600': 'value17594',
    'key59705': 'value22739',
},
    {
    'id': 17527475342798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Gabrielle Taylor',
    'address': '298 Martinez Hollow Suite 469\nWongside, GA 34864',
    'text': 'Start address bill approach according later. Mr child still discussion above subject large onto.',
    'email': 'danielsalicia@example.net',
    'phone_number': '506-373-6453',
    'json': {
    'name': 'Catherine Jackson',
    'address': '211 Amanda Expressway Suite 271\nWest Ericton, IL 45026',
},
    'key36481': 'value3190',
    'key24498': 'value3443',
    'key82968': 'value58927',
    'key82327': 'value83841',
    'key73582': 'value47869',
    'key88093': 'value35447',
},
    {
    'id': 17527475342812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Charlene Richardson',
    'address': '27069 Bowman View\nWalkerhaven, WY 41486',
    'text': 'Ahead then dark focus move. Wind affect and single education. Line live return order able like book.',
    'email': 'benjaminthompson@example.org',
    'phone_number': '(746)873-6679',
    'json': {
    'name': 'Jesse Jones',
    'address': '4293 Michelle Road\nNew Sarah, UT 02088',
},
    'key18353': 'value26362',
    'key64455': 'value40596',
    'key34032': 'value30605',
    'key30850': 'value56449',
    'key90481': 'value88907',
    'key53050': 'value13590',
    'key2057': 'value25677',
    'key69610': 'value12202',
    'key10712': 'value48281',
    'key64481': 'value19746',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '706c1918-62f7-11f0-85c3-0242ac11000b',
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



    def test_request_4(self):
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '706c1918-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_18_53_114013KUVHpLZL',
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



    def test_request_5(self):
        """测试请求 5 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '706c1918-62f7-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_18_53_114013KUVHpLZL',
    'dimension': 128,
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestUpsertVectorNegative_test_upsert_vector_with_invalid_collection_name_1752747535.json')
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
    test = AllmilvusLogtestupsertvectornegativeTestUpsertVectorWithInvalidCollectionName1752747535Json()
    test.run_tests()
