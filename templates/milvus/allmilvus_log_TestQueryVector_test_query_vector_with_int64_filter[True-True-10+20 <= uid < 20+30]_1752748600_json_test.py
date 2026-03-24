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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752748600_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752748600.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrue1020Uid20301752748600Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752748600.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752748600.json"
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
    'RequestId': 'e572ae0a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_28_440737KyNMuSao',
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
    'RequestId': 'e572ae0a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_28_440737KyNMuSao',
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
    'RequestId': 'e572ae0a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_28_440737KyNMuSao',
    'data': [
    {
    'id': 17527485944852,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Andrea Krueger',
    'address': '8010 Michael Shoal\nLake Donnaside, GA 71123',
    'text': 'Three enter special space modern. Into pretty also street would boy environment. Man perhaps like majority voice produce let.',
    'email': 'hcontreras@example.net',
    'phone_number': '+1-469-374-9070x99509',
    'json': {
    'name': 'Jessica Hart',
    'address': '338 Avila Mews Suite 687\nLake Andrew, NV 84453',
},
    'key44417': 'value51351',
    'key37171': 'value81884',
    'key64192': 'value72296',
    'key70939': 'value36911',
    'key51419': 'value89740',
},
    {
    'id': 17527485944880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Stephen Holt',
    'address': '097 Angela Underpass\nSamanthabury, OR 33833',
    'text': 'Movement prevent here hair low write begin. Talk maintain sound myself health laugh.\nLawyer rule young I. Condition my go again visit cost yes. Away beautiful begin will.',
    'email': 'dwayne53@example.com',
    'phone_number': '988-290-7772x8314',
    'json': {
    'name': 'Morgan Richardson',
    'address': '851 Bowen Shore Suite 142\nMaxwellfort, AK 13051',
},
    'key7880': 'value98886',
    'key7407': 'value23912',
    'key49817': 'value7813',
    'key92067': 'value7623',
    'key48808': 'value7862',
    'key25027': 'value84019',
    'key98840': 'value47147',
},
    {
    'id': 17527485944895,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Walter Clark',
    'address': '5589 White Lights Apt. 556\nLake Lisahaven, NH 74308',
    'text': 'Crime life clear catch big well send room. Else buy of against help woman.\nPretty where land point thank. Home black section toward.',
    'email': 'bryantjohn@example.net',
    'phone_number': '+1-581-569-6096x43670',
    'json': {
    'name': 'Joseph Sherman',
    'address': 'Unit 9190 Box 9229\nDPO AE 20049',
},
    'key48317': 'value31923',
},
    {
    'id': 17527485944908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Miranda Weiss',
    'address': '92363 Hughes Junction\nLake Amberstad, ND 52334',
    'text': 'Beautiful situation plan. Which commercial west price ability house customer. Statement clearly article fish. Cell understand yeah.',
    'email': 'ian14@example.com',
    'phone_number': '2629025625',
    'json': {
    'name': 'Laurie Miller',
    'address': '82629 Scott Dale\nAustinmouth, PW 62917',
},
    'key64801': 'value33935',
    'key82435': 'value59670',
    'key36570': 'value15279',
    'key72072': 'value1974',
    'key55825': 'value7446',
    'key47407': 'value47026',
    'key16529': 'value23790',
    'key82553': 'value56808',
},
    {
    'id': 17527485944923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Olivia Sanchez',
    'address': '67105 Vazquez Trail Suite 124\nBurnsside, ID 01424',
    'text': 'Remain fear story clear message close. Those now must believe indeed scene.\nMedia couple whether agreement around defense until.',
    'email': 'charles73@example.com',
    'phone_number': '824-413-1470x86575',
    'json': {
    'name': 'Barbara Johnson',
    'address': '1932 Calvin Prairie\nMariaside, AZ 94087',
},
    'key52903': 'value57853',
    'key70731': 'value87224',
    'key59267': 'value44983',
    'key34782': 'value76453',
    'key76771': 'value28240',
    'key69479': 'value73417',
    'key77126': 'value20355',
    'key55167': 'value96616',
},
    {
    'id': 17527485944938,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Donald Johnson',
    'address': '3163 Robin Creek\nPort Amanda, OH 92067',
    'text': 'Hair majority image. Research conference politics step deal charge stuff. Into data true create he.\nPurpose its heavy. Owner president white may.',
    'email': 'paul37@example.com',
    'phone_number': '+1-404-905-1458x10761',
    'json': {
    'name': 'Bryan Turner',
    'address': '322 Aaron Ville Apt. 072\nEast Melinda, HI 41286',
},
    'key58424': 'value85878',
    'key93091': 'value7791',
    'key52820': 'value56264',
    'key29212': 'value32489',
},
    {
    'id': 17527485944951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Jonathan Ryan',
    'address': '4373 Lisa Squares\nLewisshire, WA 85519',
    'text': 'Best program admit sense billion water. Keep himself staff natural media risk energy tough. Available treatment key lawyer.',
    'email': 'charlesdecker@example.org',
    'phone_number': '+1-993-291-6659x44522',
    'json': {
    'name': 'Stephanie Ferguson',
    'address': '4870 David Glens\nHallland, KY 24756',
},
    'key23390': 'value39344',
    'key83493': 'value22544',
},
    {
    'id': 17527485944966,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Kelly Lopez',
    'address': '44017 Jennings Key Apt. 493\nPrestonmouth, NV 66341',
    'text': 'Collection relationship behind after six deal. Win baby live group. City interview fine run smile. Skill today model test.',
    'email': 'peterbrown@example.org',
    'phone_number': '419.293.2366x2501',
    'json': {
    'name': 'Lori Suarez',
    'address': '1399 Gallegos Flats\nJillbury, GA 81114',
},
    'key22805': 'value40423',
    'key40921': 'value47926',
    'key78907': 'value27490',
    'key30280': 'value33844',
    'key18131': 'value8783',
    'key93567': 'value16927',
},
    {
    'id': 17527485944980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Peter Lopez',
    'address': '62868 Miller Harbor Suite 930\nPort Sandraland, WA 93440',
    'text': 'Second suddenly traditional research against travel senior. Myself lot mean customer.\nReturn event positive assume so name. Author possible late view low. Operation likely member ready continue.',
    'email': 'vparks@example.net',
    'phone_number': '240.579.9451x20986',
    'json': {
    'name': 'Clayton Hatfield',
    'address': '43420 Barbara Wall Suite 902\nSouth Julie, SD 30371',
},
    'key10997': 'value69252',
    'key51660': 'value99522',
    'key17480': 'value90553',
},
    {
    'id': 17527485944991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brian Ali',
    'address': '05390 Laura Lane\nLake Kimberly, MH 51978',
    'text': 'Especially feeling week few idea stop. Until organization interesting culture true. Up myself meeting.\nMr require or beat those. Might ago serious such worker want.',
    'email': 'jennadavis@example.com',
    'phone_number': '(988)266-4018',
    'json': {
    'name': 'Angela Davis',
    'address': 'Unit 3579 Box 6430\nDPO AA 56479',
},
    'key86124': 'value86778',
    'key85111': 'value78610',
    'key3640': 'value73282',
    'key13168': 'value8367',
    'key13567': 'value78938',
    'key12029': 'value27838',
    'key28158': 'value61807',
    'key11985': 'value45961',
    'key57461': 'value69168',
    'key41310': 'value66266',
},
    {
    'id': 17527485945002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Monica Williams',
    'address': '467 Francis Knoll Suite 223\nSmithview, FM 19077',
    'text': 'Occur position ever society. Assume why easy book. Court the should law.\nFour bank actually world. Doctor cause shoulder usually close.',
    'email': 'lewisstephanie@example.org',
    'phone_number': '294.921.6254',
    'json': {
    'name': 'Leonard Haney',
    'address': '427 Clark Parks\nPetersonbury, IA 70403',
},
    'key16759': 'value36467',
    'key38744': 'value57544',
    'key76523': 'value35671',
    'key56049': 'value20387',
    'key88794': 'value1282',
    'key19111': 'value41021',
},
    {
    'id': 17527485945014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Jacob Rodriguez',
    'address': '103 Davis Crescent\nWest Brittanyhaven, DE 42459',
    'text': 'Different head hundred bank.\nAge western data bank black rise institution. Take explain picture crime up. Follow bill those modern instead culture.',
    'email': 'jennifer40@example.com',
    'phone_number': '842-450-9052',
    'json': {
    'name': 'Diane Richardson',
    'address': '71596 Andrea Divide Suite 003\nMcfarlandfurt, CO 61445',
},
    'key89650': 'value41385',
    'key48903': 'value98166',
    'key66161': 'value30239',
    'key80174': 'value3877',
    'key19665': 'value71820',
    'key93242': 'value38761',
},
    {
    'id': 17527485945025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Michael Williams',
    'address': '3579 Nicholas Freeway Suite 633\nBenjaminhaven, DE 43027',
    'text': 'Mother analysis blood raise along. Perhaps charge nature deep old although.\nCertainly economic party sing capital. Road eye against manage become marriage ground end.',
    'email': 'kristin55@example.net',
    'phone_number': '525.998.1825x91144',
    'json': {
    'name': 'Ryan Harris',
    'address': '9298 Brian Vista Suite 503\nLake Patricialand, AL 93668',
},
    'key94417': 'value52028',
    'key38319': 'value3602',
    'key87759': 'value16272',
    'key53772': 'value46556',
    'key32087': 'value30242',
    'key73467': 'value43002',
    'key54950': 'value24801',
},
    {
    'id': 17527485945036,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jose Thompson',
    'address': '18026 Fletcher Pike\nEast Robert, MA 19332',
    'text': 'Yeah television natural material way same mind degree. Raise policy effort become half interview design wall. Seek but language allow century.',
    'email': 'kristengomez@example.org',
    'phone_number': '001-969-440-8458x5571',
    'json': {
    'name': 'Laura Hood',
    'address': '27830 Monica Run Apt. 209\nSouth Melanie, VA 43366',
},
    'key91474': 'value58388',
    'key45177': 'value89672',
    'key15167': 'value47760',
    'key10875': 'value37906',
    'key74507': 'value87836',
    'key39759': 'value41298',
    'key47367': 'value71282',
},
    {
    'id': 17527485945053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Kenneth Martinez',
    'address': '601 Aaron Spur Apt. 700\nFoxfort, SC 54022',
    'text': 'Police smile agreement gas everyone already down color. Decide loss girl debate American become.\nThey for brother bank.',
    'email': 'christopherwhite@example.net',
    'phone_number': '+1-677-410-2379x59148',
    'json': {
    'name': 'Ashley Harvey',
    'address': '98924 Samuel Center\nFranklinview, IL 43284',
},
    'key33772': 'value38326',
    'key70101': 'value37645',
    'key93487': 'value28288',
    'key30015': 'value26579',
    'key39745': 'value62216',
    'key13814': 'value20006',
    'key50745': 'value4721',
    'key82769': 'value51823',
    'key16080': 'value82429',
},
    {
    'id': 17527485945068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Thomas Watkins',
    'address': '05502 Santos Squares\nEast Rebekahborough, SC 33547',
    'text': 'Performance collection reality future. Half race stop. Like morning cup best go of.\nManage focus ability rate walk economy. Woman easy star rise.',
    'email': 'staceybell@example.net',
    'phone_number': '001-225-956-0860x295',
    'json': {
    'name': 'Troy Arnold',
    'address': 'PSC 7428, Box 7293\nAPO AA 90193',
},
    'key15496': 'value49849',
    'key22608': 'value95866',
    'key74500': 'value56550',
    'key15534': 'value5763',
    'key41668': 'value41404',
},
    {
    'id': 17527485945080,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Mr. Michael Marquez',
    'address': '44353 Peterson Loaf\nPort Joan, VT 37189',
    'text': 'Rise position computer dark able. Page change threat environmental left. Front spring again reason.',
    'email': 'sgreen@example.net',
    'phone_number': '(454)210-4015x2951',
    'json': {
    'name': 'Keith Gibson',
    'address': '99047 Garcia Fall\nNorth Lori, MA 89752',
},
    'key70347': 'value585',
    'key85019': 'value45819',
    'key88419': 'value35400',
    'key55097': 'value82061',
    'key67148': 'value5245',
    'key42192': 'value48385',
    'key65062': 'value40737',
},
    {
    'id': 17527485945092,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tammy Day',
    'address': 'USNS Weeks\nFPO AE 16530',
    'text': 'Another let range air. System system weight trial. Major question father exist exist since support.\nSuddenly score seek. Much worker law reflect.',
    'email': 'david27@example.com',
    'phone_number': '001-302-222-2834x9331',
    'json': {
    'name': 'James Welch',
    'address': '22319 Green Mount\nMelaniebury, IA 24433',
},
    'key86697': 'value55889',
    'key74490': 'value19036',
    'key47775': 'value64490',
    'key27646': 'value3802',
    'key60835': 'value82911',
    'key48225': 'value43740',
    'key11373': 'value82065',
},
    {
    'id': 17527485945104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Cheryl Gibson',
    'address': '2725 Garcia Fork\nRamseyfurt, FM 57791',
    'text': 'Impact station minute.\nHand plan fight five big human age a. Painting specific wait moment find. Work military free somebody money world. Should film policy process.',
    'email': 'denise61@example.com',
    'phone_number': '245.553.9034',
    'json': {
    'name': 'Jeremy Avila',
    'address': '78922 Ashley Locks\nLake Deborah, MD 47640',
},
    'key31284': 'value86997',
    'key4001': 'value57694',
    'key87383': 'value9581',
    'key7736': 'value92900',
    'key51977': 'value34048',
    'key29299': 'value15364',
    'key54078': 'value2932',
},
    {
    'id': 17527485945117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Robert Gentry',
    'address': '342 Carlos Row Apt. 372\nSouth Charles, GU 50096',
    'text': 'Old impact likely serious weight blood also. Something ten care history stop level together. Yard pass once commercial stand.\nGrowth such east gun certainly. Pretty range keep accept increase.',
    'email': 'zcook@example.com',
    'phone_number': '+1-452-868-0256x804',
    'json': {
    'name': 'James Scott',
    'address': '51124 Eddie Row\nNew Markberg, AK 69700',
},
    'key59350': 'value648',
},
    {
    'id': 17527485945131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Ashley Cooper',
    'address': '2811 Danielle Field\nGreenebury, MD 87734',
    'text': 'Scientist clearly we right.\nGame adult spend should. Exist model assume money.\nStudy be nation best certain cause. You many letter chair dog.',
    'email': 'kjohnson@example.org',
    'phone_number': '001-758-964-5251x45701',
    'json': {
    'name': 'Bradley Brown',
    'address': '15779 Wade Square Suite 193\nNorth Samuelberg, AR 42582',
},
    'key13588': 'value28730',
    'key55666': 'value85674',
},
    {
    'id': 17527485945153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Angel Reynolds',
    'address': '2230 Amy Well Apt. 209\nNorth Caitlin, WA 01275',
    'text': 'Shoulder until field amount either free. Social kid dinner simply education.',
    'email': 'walkermichelle@example.com',
    'phone_number': '+1-909-227-9551x2676',
    'json': {
    'name': 'Phyllis Thomas',
    'address': '125 Dustin Landing Suite 431\nNew Meredith, DE 56186',
},
    'key96388': 'value58798',
    'key5124': 'value63962',
    'key14057': 'value54948',
},
    {
    'id': 17527485945175,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Allison Pena DDS',
    'address': '037 Kennedy Points Suite 015\nNew Patrick, IN 81761',
    'text': 'Dinner either general notice picture trip. Half ten hair resource occur make long. Room suggest seem still anyone learn.\nIndeed while car contain structure special argue. Friend last rest only.',
    'email': 'kennethramirez@example.org',
    'phone_number': '001-646-517-7118',
    'json': {
    'name': 'Vincent Edwards',
    'address': '714 Victoria Union Apt. 439\nValenzuelaberg, AL 82530',
},
    'key9876': 'value88992',
    'key68847': 'value82068',
    'key67594': 'value58060',
    'key90538': 'value47434',
    'key9618': 'value14684',
    'key24326': 'value90278',
    'key80214': 'value12169',
    'key28738': 'value43776',
    'key428': 'value75915',
    'key64493': 'value9514',
},
    {
    'id': 17527485945195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Sarah Vargas MD',
    'address': 'USS Johnson\nFPO AE 33692',
    'text': 'Minute weight home anyone marriage you. Interesting many forget side capital. Respond out recognize local huge drive hot.',
    'email': 'amymartin@example.org',
    'phone_number': '001-247-575-6244x8805',
    'json': {
    'name': 'Alejandra Greer',
    'address': '12275 Williams Plaza Apt. 228\nCoryburgh, SD 37273',
},
    'key87307': 'value42812',
    'key36670': 'value98531',
    'key67748': 'value84009',
    'key38897': 'value23574',
    'key31318': 'value66925',
},
    {
    'id': 17527485945208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Johnny Walton',
    'address': '6071 Richard Alley Suite 684\nTerryside, NJ 62018',
    'text': 'Help explain size north. Deep reach catch think. But thus operation agree yourself manage owner side.',
    'email': 'mark75@example.com',
    'phone_number': '+1-949-261-6648x4862',
    'json': {
    'name': 'Jodi Saunders',
    'address': '81987 Powers Station Suite 507\nLake Victor, AR 91198',
},
    'key56889': 'value28029',
    'key11930': 'value10687',
    'key55933': 'value6781',
    'key87582': 'value75491',
    'key303': 'value2408',
},
    {
    'id': 17527485945222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Christine Boyle',
    'address': '52059 Hurley Mission\nWilliamsville, NJ 20896',
    'text': 'Likely fight method way something. Question able stuff suffer. Want article dog town TV chance.\nWhom she window entire military. Through foot article down father do amount action.',
    'email': 'harrypatterson@example.com',
    'phone_number': '001-606-668-3206x3263',
    'json': {
    'name': 'Antonio Hickman',
    'address': '620 Jimenez Overpass Suite 507\nChadview, WV 15907',
},
    'key75887': 'value13302',
},
    {
    'id': 17527485945237,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Brittany Martinez',
    'address': '623 Todd Plain\nJessicaview, WY 23684',
    'text': 'Light oil edge right land poor certainly study. Tree scientist find start prepare. Talk remember life laugh itself stage none.\nFace themselves one. Director catch happen baby receive dog trip north.',
    'email': 'william76@example.net',
    'phone_number': '424.785.8975',
    'json': {
    'name': 'Tammy Smith',
    'address': '191 Pollard Causeway\nWest Nicole, GA 68972',
},
    'key44585': 'value66797',
    'key27065': 'value6842',
},
    {
    'id': 17527485945251,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Darius Beck',
    'address': '128 Angela Ridge\nPort Jamesmouth, MN 93503',
    'text': 'Ability structure leave different total window our grow. Actually despite child court article.',
    'email': 'heather92@example.com',
    'phone_number': '483.589.0880x347',
    'json': {
    'name': 'Caitlin Russell',
    'address': 'PSC 4905, Box 8434\nAPO AA 13505',
},
    'key47621': 'value82879',
    'key54665': 'value26350',
    'key71382': 'value62125',
    'key20999': 'value2832',
},
    {
    'id': 17527485945261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Tara Vasquez',
    'address': 'Unit 6467 Box 4949\nDPO AE 28889',
    'text': 'Security picture white interest wear. Identify else win opportunity hand.',
    'email': 'rosesims@example.org',
    'phone_number': '207.929.9280x35290',
    'json': {
    'name': 'Heidi James',
    'address': '0599 Debra Tunnel Suite 333\nChristopherfort, WY 79246',
},
    'key16048': 'value57987',
},
    {
    'id': 17527485945273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Helen Jenkins',
    'address': '288 Moore Green\nSierrafort, NV 87726',
    'text': 'Here again professor catch service office collection. Quality image they involve.\nDevelop bag rule lead organization thank. Research play allow cultural beyond man party.',
    'email': 'cmora@example.org',
    'phone_number': '001-975-942-8372',
    'json': {
    'name': 'Jacob Anderson',
    'address': '37515 Justin Ways Apt. 315\nCarolinefort, MS 17166',
},
    'key40585': 'value89124',
    'key52823': 'value1611',
    'key35581': 'value67469',
    'key24832': 'value41877',
    'key5991': 'value66714',
},
    {
    'id': 17527485945287,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Michael Williamson',
    'address': '51720 Berg Flat\nLake John, OH 76148',
    'text': 'Media beyond wear for brother reality. If pick claim one story. During stuff manage.',
    'email': 'chanvictoria@example.net',
    'phone_number': '(735)299-8336x33013',
    'json': {
    'name': 'Steven Roberson',
    'address': '289 Erin Station\nAliciabury, UT 11406',
},
    'key48747': 'value9895',
    'key29691': 'value51695',
    'key66531': 'value86753',
    'key24215': 'value15723',
    'key74540': 'value11028',
    'key47871': 'value26881',
    'key73472': 'value17824',
    'key34735': 'value32783',
    'key43282': 'value71624',
},
    {
    'id': 17527485945299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Madison Benson',
    'address': '099 Johnson Creek Suite 621\nBrendafort, PW 35018',
    'text': 'Kid hundred tonight everything. All stuff common instead.\nForce thought process really. Table school floor community accept morning.',
    'email': 'imahoney@example.net',
    'phone_number': '217-424-5633x099',
    'json': {
    'name': 'John Dillon',
    'address': '3255 Jones Manor Apt. 061\nChrishaven, MA 59348',
},
    'key60355': 'value59570',
    'key8782': 'value37805',
    'key48508': 'value6710',
    'key92496': 'value97335',
},
    {
    'id': 17527485945310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Jonathan Avila',
    'address': '2362 Bailey Terrace\nPadillamouth, PW 33179',
    'text': 'Fast mission bag economic. No rest fear student quality money. Work worry true course beautiful.\nQuestion care force something. Change head painting. Long once really attack court focus story.',
    'email': 'valdezbrady@example.org',
    'phone_number': '+1-740-854-0578x9519',
    'json': {
    'name': 'Andrew Watts',
    'address': '262 Webb Points\nNew Johnport, TN 62377',
},
    'key21897': 'value14140',
    'key8292': 'value35771',
},
    {
    'id': 17527485945322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Brandon Wagner',
    'address': '4365 Smith Dam\nWest Travis, MN 75932',
    'text': 'Rest require series technology surface before prepare choose. Human art audience career. Technology team inside development finish no young. Weight and either at take what seat control.',
    'email': 'kimberly53@example.com',
    'phone_number': '(430)910-8879x007',
    'json': {
    'name': 'Margaret Schmidt',
    'address': '43239 French Port\nThompsonton, PW 40004',
},
    'key41789': 'value64851',
    'key96492': 'value52568',
},
    {
    'id': 17527485945333,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Cynthia Mendez',
    'address': '1696 Davis Ridges Apt. 743\nPort Margaretport, AS 74742',
    'text': 'Leave right western provide. Life fill conference keep.\nI there enter hope. Picture father try painting against blue cause.\nFuture daughter argue sit doctor.',
    'email': 'luis76@example.net',
    'phone_number': '484.280.2233',
    'json': {
    'name': 'Yvette Price',
    'address': '4980 Morris Islands\nJennaburgh, OH 44486',
},
    'key40450': 'value32356',
    'key46758': 'value79541',
    'key66138': 'value15146',
    'key12589': 'value45764',
    'key42997': 'value64112',
    'key70320': 'value60564',
},
    {
    'id': 17527485945344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Katherine Byrd',
    'address': '3767 Reid Ramp\nWest Arthurmouth, MO 26932',
    'text': 'Table range after rest out seem. Shoulder poor operation have single city.\nNot east pull leave hear two quite. Health military national time.',
    'email': 'davidwells@example.net',
    'phone_number': '805-888-0210',
    'json': {
    'name': 'Joseph Jacobson',
    'address': '144 Wallace Roads\nEast Harryborough, ID 04900',
},
    'key90139': 'value39767',
    'key36708': 'value22406',
    'key12340': 'value38077',
    'key51577': 'value45394',
    'key81472': 'value78281',
    'key70707': 'value42627',
    'key78857': 'value71122',
    'key85172': 'value36290',
    'key55260': 'value36582',
},
    {
    'id': 17527485945356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Jennifer Summers',
    'address': '10722 Tammy Locks\nVelasquezstad, MH 75204',
    'text': 'Provide garden test couple environmental strong. Maybe national anyone power early. Act share might whose measure likely.',
    'email': 'fosterricky@example.net',
    'phone_number': '(350)314-8843x06716',
    'json': {
    'name': 'Angela Miller',
    'address': '5170 Debra Flat Apt. 430\nRodriguezport, AL 10669',
},
    'key62767': 'value63698',
    'key35258': 'value6227',
    'key9617': 'value88399',
    'key67879': 'value7326',
},
    {
    'id': 17527485945368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Roberto Wallace',
    'address': '077 Randall Glen\nWest Richard, RI 19244',
    'text': 'Open parent seem face. Ahead occur picture condition finish explain war. Herself worker so get within sell onto city.\nLocal modern doctor apply. Partner statement someone.',
    'email': 'james83@example.net',
    'phone_number': '+1-616-539-9536x045',
    'json': {
    'name': 'Yolanda Johnson',
    'address': 'PSC 6039, Box 9953\nAPO AE 44951',
},
    'key72522': 'value2246',
    'key30607': 'value58021',
    'key64516': 'value83171',
    'key13286': 'value52328',
    'key91566': 'value39337',
},
    {
    'id': 17527485945376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Tonya Anderson',
    'address': '3974 Bowman Summit\nPort Colleenhaven, MO 93229',
    'text': 'Language under eight dinner own good. Decade support good skin inside ok. Thousand head direction you.\nDetail at question hundred. Present responsibility hard lawyer.',
    'email': 'delacruzbenjamin@example.com',
    'phone_number': '(704)588-9642',
    'json': {
    'name': 'Gerald Brown',
    'address': 'Unit 3940 Box 1735\nDPO AA 92750',
},
    'key85623': 'value6964',
    'key90057': 'value90797',
    'key75486': 'value92415',
    'key35314': 'value41168',
    'key98343': 'value81032',
    'key32493': 'value95596',
    'key27268': 'value13936',
    'key34685': 'value83998',
},
    {
    'id': 17527485945386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Phillip Herring',
    'address': '6636 Autumn Estates\nSouth Evelynberg, ME 28357',
    'text': 'White camera reflect structure. Reduce do enough series wish bag. Identify growth plan American adult media.\nDo free wish collection yard kitchen war. Land after major teacher foreign.',
    'email': 'emartin@example.net',
    'phone_number': '001-812-478-1048',
    'json': {
    'name': 'Elizabeth Robinson',
    'address': '364 Carter Lights\nLake Jean, HI 54877',
},
    'key45361': 'value45846',
    'key87754': 'value63711',
    'key27281': 'value97419',
    'key92589': 'value49737',
    'key2803': 'value61872',
    'key33684': 'value51118',
    'key50153': 'value63565',
    'key97528': 'value30891',
    'key54403': 'value59351',
    'key5481': 'value44395',
},
    {
    'id': 17527485945397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Angela Martinez',
    'address': '233 Cortez Road\nNorth Tylertown, NM 61525',
    'text': 'Sister perform too. Trade word beyond glass sit power.\nUpon tough seem nature source. Art chance whether serious few of really sound. Kid card want.',
    'email': 'nandrews@example.org',
    'phone_number': '(988)707-2353',
    'json': {
    'name': 'Shelley Hughes',
    'address': '725 Lisa Route\nChristopherside, ID 97222',
},
    'key60990': 'value34397',
    'key75207': 'value88584',
    'key20795': 'value38083',
    'key15751': 'value34485',
    'key75556': 'value77020',
    'key59222': 'value95675',
    'key44049': 'value46512',
},
    {
    'id': 17527485945408,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Cassandra Flores',
    'address': '38328 Robert Knoll Suite 875\nLake Scott, AK 80466',
    'text': 'Outside whom factor baby necessary individual itself. Join evidence owner plan bar how feeling dinner. Seek mother forward last study economy.',
    'email': 'john20@example.org',
    'phone_number': '001-666-270-9252',
    'json': {
    'name': 'Richard Prince',
    'address': '9758 Dawn Hill Suite 546\nShawnfort, FM 25456',
},
    'key52416': 'value14709',
    'key74080': 'value23647',
    'key85166': 'value19771',
    'key51011': 'value37902',
    'key77576': 'value70883',
    'key59473': 'value91854',
},
    {
    'id': 17527485945418,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Brian Williams',
    'address': '6597 Gina Court Apt. 628\nMariahaven, PA 72024',
    'text': 'Necessary even three. Capital save job. Field career artist determine far.\nNecessary remain must according day clear pretty. Beat pass community. Pick site ok.',
    'email': 'kimberly43@example.net',
    'phone_number': '+1-281-624-8534x39200',
    'json': {
    'name': 'Katherine Hampton',
    'address': '0886 Ferguson Port Apt. 783\nKlineville, OH 21003',
},
    'key91456': 'value80099',
    'key27169': 'value99576',
    'key85067': 'value57967',
    'key86226': 'value79404',
    'key13381': 'value48538',
    'key30653': 'value83803',
    'key1580': 'value95528',
    'key59550': 'value28040',
},
    {
    'id': 17527485945429,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Karen Pope',
    'address': '3423 Horn Station Apt. 266\nNew Marie, NJ 90507',
    'text': 'Hit million doctor through art resource. Much particular skin exist clearly thank. Free whatever Republican.\nAnswer yourself hold half idea. Find thousand heavy camera meet standard how.',
    'email': 'bflynn@example.com',
    'phone_number': '2747234985',
    'json': {
    'name': 'Amanda Wilkerson',
    'address': '61090 Jackson Track Apt. 479\nPort Douglasberg, VT 28094',
},
    'key58178': 'value36395',
    'key45086': 'value16511',
    'key41341': 'value54165',
},
    {
    'id': 17527485945440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Angela Reed',
    'address': '29608 White Forks\nNew Stevenstad, PR 18511',
    'text': 'Position still assume however best. Develop lay discussion hundred them hospital. Listen raise despite information to deal.',
    'email': 'davisrebecca@example.org',
    'phone_number': '001-475-357-7796x69295',
    'json': {
    'name': 'Christine Bonilla',
    'address': '843 Patrick Mission\nBlackwellfurt, KY 16745',
},
    'key4127': 'value84506',
    'key98566': 'value68436',
    'key97320': 'value36935',
},
    {
    'id': 17527485945452,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Jerry Wilkerson',
    'address': '67665 Benjamin Spring\nCunninghamton, HI 71162',
    'text': 'Threat room kind song family keep. Party stay walk. Mind learn either business.',
    'email': 'dominique92@example.org',
    'phone_number': '(203)485-6110',
    'json': {
    'name': 'Dave Bowers',
    'address': '3220 Nicholas Mall Apt. 483\nWilsonbury, PA 33947',
},
    'key77489': 'value13581',
},
    {
    'id': 17527485945462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Paul Wilson',
    'address': '59629 Katherine Lodge Suite 801\nPort Laura, VI 98774',
    'text': 'Coach while word the woman pick. Admit may senior fish.\nMeet risk wrong common. List medical agree teacher show civil. Three some others near able bank.\nThe here station dinner coach million.',
    'email': 'kleinmichael@example.net',
    'phone_number': '(542)386-7335x828',
    'json': {
    'name': 'Daniel Stone',
    'address': '150 Meadows Mill\nAndrewburgh, GA 43269',
},
    'key3553': 'value62505',
    'key62317': 'value45347',
    'key93711': 'value59380',
    'key68317': 'value28250',
    'key41239': 'value81575',
    'key14873': 'value25074',
    'key39292': 'value91216',
    'key83972': 'value17217',
    'key65624': 'value59224',
},
    {
    'id': 17527485945473,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Jonathan Sheppard',
    'address': '634 Daniel Run\nWest Joseph, DE 22930',
    'text': 'Generation police between quality. Set garden performance parent because court smile. Risk herself goal good mean.',
    'email': 'maureenbrooks@example.net',
    'phone_number': '001-496-864-3686x1837',
    'json': {
    'name': 'Darren Hickman',
    'address': '298 Torres Rue\nBergerville, VT 12622',
},
    'key55710': 'value54395',
    'key17213': 'value40411',
    'key34399': 'value71788',
    'key94228': 'value26502',
    'key69171': 'value61242',
    'key94352': 'value9190',
    'key17749': 'value15561',
    'key24189': 'value96670',
},
    {
    'id': 17527485945484,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Hannah Fuller',
    'address': '93889 Sanford Point\nAnnaburgh, MO 06875',
    'text': 'Receive we data under guess of. Economy sure view arm edge.\nCare her husband. Vote sure say year. Company be issue reason.',
    'email': 'bmiller@example.org',
    'phone_number': '+1-996-756-3869x570',
    'json': {
    'name': 'Catherine Alexander',
    'address': 'USCGC Welch\nFPO AP 20366',
},
    'key69769': 'value44308',
    'key84533': 'value66135',
    'key26248': 'value57730',
    'key40578': 'value18573',
    'key88356': 'value80539',
    'key59343': 'value28996',
    'key50933': 'value2832',
},
    {
    'id': 17527485945494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Mrs. Melissa Wheeler',
    'address': '17978 Thomas Square Apt. 967\nWongberg, TN 78605',
    'text': 'Home offer key floor. Former black how nation heavy help approach. Book collection wind word space teach.',
    'email': 'leejasmine@example.net',
    'phone_number': '001-205-915-1713x729',
    'json': {
    'name': 'Paul Williams',
    'address': '36280 Kemp Lights Apt. 820\nNorth Laura, SC 33570',
},
    'key20787': 'value18457',
    'key49244': 'value31471',
},
    {
    'id': 17527485945505,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Lee Zimmerman',
    'address': '31913 Rebecca Trail Suite 451\nNorth Derek, NC 09499',
    'text': 'Money reach half accept. Country meet administration focus exist financial.\nSend why city church. Suggest despite gun owner. Agree third history trouble Congress.',
    'email': 'rtucker@example.net',
    'phone_number': '818.270.5455',
    'json': {
    'name': 'Traci Williams',
    'address': '959 Christina Streets Suite 735\nLake Andrew, KS 41728',
},
    'key6221': 'value47446',
    'key15136': 'value70589',
    'key71162': 'value97332',
    'key75': 'value54104',
    'key11762': 'value88148',
    'key70679': 'value57601',
},
    {
    'id': 17527485945516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Rhonda Tran',
    'address': 'PSC 9907, Box 9436\nAPO AP 58603',
    'text': 'Environmental despite then property. Although serve production at.\nCause improve few able. Everything game case nor property bill hard.',
    'email': 'banksmichelle@example.com',
    'phone_number': '457-457-4586x5115',
    'json': {
    'name': 'Mike Murillo',
    'address': '08629 Beverly Ports Suite 816\nNorth Bradleyfort, LA 96754',
},
    'key40020': 'value89068',
},
    {
    'id': 17527485945526,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Jennifer Kelley',
    'address': '7972 Manuel Ridge\nBradshire, MS 91441',
    'text': 'Model certain thank western. Reduce building many health.\nPolitics service tonight image change. Low center technology.',
    'email': 'jamesromero@example.com',
    'phone_number': '942-617-6452x722',
    'json': {
    'name': 'Eric Mosley',
    'address': '91045 Phillips Grove Apt. 438\nSouth Kaitlyn, KY 75123',
},
    'key60942': 'value30192',
    'key19783': 'value59608',
    'key35289': 'value48991',
},
    {
    'id': 17527485945537,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Richard Thomas',
    'address': '747 Thomas Isle\nNorth Antoniomouth, NJ 09386',
    'text': 'Activity cover just force. Note network quality always series.\nServe weight small great week deal less. Position interest group whatever information.',
    'email': 'fmoran@example.com',
    'phone_number': '001-948-320-8206x856',
    'json': {
    'name': 'Carl Stewart',
    'address': '260 Jenkins Coves Suite 253\nMariomouth, MS 24987',
},
    'key54173': 'value98624',
    'key92882': 'value93082',
    'key86408': 'value12447',
    'key60592': 'value40956',
    'key90946': 'value6225',
    'key79500': 'value9169',
    'key20364': 'value52624',
},
    {
    'id': 17527485945548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Lori Jones',
    'address': '864 Torres Ways Apt. 145\nNorth Kathleen, PR 89961',
    'text': 'Her site mean dog rule even pay. Remember beautiful result ok group suddenly play. Charge station carry situation road leave.',
    'email': 'browntimothy@example.org',
    'phone_number': '404-433-3176',
    'json': {
    'name': 'Christopher Sharp',
    'address': 'PSC 9754, Box 9452\nAPO AP 49260',
},
    'key20578': 'value47270',
    'key25919': 'value33878',
    'key43582': 'value193',
    'key34669': 'value35733',
    'key13943': 'value4295',
    'key64990': 'value91237',
    'key90498': 'value58410',
},
    {
    'id': 17527485945557,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'James Webster',
    'address': '21596 Williams Mount Suite 479\nAlanshire, MN 86032',
    'text': 'Region sense his power talk politics worker. President east kind which bring foreign outside. Reveal up medical set voice so.',
    'email': 'thomas18@example.net',
    'phone_number': '681-642-9737x9165',
    'json': {
    'name': 'Amber Gregory',
    'address': 'Unit 4796 Box 9556\nDPO AE 90932',
},
    'key27356': 'value17482',
    'key19750': 'value25658',
    'key15974': 'value68180',
    'key25995': 'value40371',
    'key92854': 'value33227',
    'key49453': 'value2203',
    'key81509': 'value45011',
    'key45088': 'value91783',
    'key39802': 'value73455',
    'key26969': 'value21587',
},
    {
    'id': 17527485945566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mark Sanchez',
    'address': 'PSC 1118, Box 6571\nAPO AP 20461',
    'text': 'Position soldier always south. Interesting character never have it save. Network nothing under if usually.\nHundred condition leave debate tell truth once. Top add degree attack professor commercial.',
    'email': 'hbanks@example.net',
    'phone_number': '+1-587-917-8017x604',
    'json': {
    'name': 'Jason White',
    'address': '39896 Barker Mount\nWest Allison, KY 26229',
},
    'key37373': 'value63602',
    'key29572': 'value73338',
    'key78804': 'value80816',
    'key35637': 'value82362',
    'key48146': 'value75567',
    'key93110': 'value38948',
    'key44486': 'value20117',
    'key39470': 'value79769',
    'key48020': 'value75874',
},
    {
    'id': 17527485945575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jason Miller PhD',
    'address': '554 George Oval Suite 681\nWest Luisberg, WI 67951',
    'text': 'Message still reality rather resource. Threat east my sit whatever suggest smile.\nMovie picture say nature accept leader above. Office onto carry attack.',
    'email': 'breanna15@example.com',
    'phone_number': '(414)242-2311',
    'json': {
    'name': 'Jennifer Wilson',
    'address': '1854 Dawn Light\nCollinsstad, IL 27778',
},
    'key16003': 'value46832',
    'key51827': 'value25393',
    'key61678': 'value88500',
    'key5072': 'value77645',
    'key70619': 'value59807',
    'key72585': 'value30805',
    'key40847': 'value50389',
    'key5505': 'value14524',
},
    {
    'id': 17527485945585,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Kathy Shah',
    'address': '199 Mary Roads\nPonceview, UT 92302',
    'text': 'Discuss your key bring ever discover modern. Before special hope sit. Get entire water story anything college wonder.',
    'email': 'louisdean@example.com',
    'phone_number': '+1-653-920-3881',
    'json': {
    'name': 'Teresa Ayala',
    'address': '697 Powell Curve Apt. 370\nRogersfurt, SD 20126',
},
    'key2214': 'value38243',
    'key25691': 'value15045',
    'key92497': 'value5464',
    'key34775': 'value26357',
    'key11831': 'value43979',
    'key23455': 'value2651',
    'key97451': 'value48933',
},
    {
    'id': 17527485945597,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Ashley Sanchez',
    'address': '44887 Stephen Rue Suite 549\nLovechester, IA 89676',
    'text': 'Help wide painting son cut method information. Magazine safe laugh pick beautiful positive dog.\nBecause call start save executive you. Vote young quality.',
    'email': 'younglisa@example.net',
    'phone_number': '975.322.7204x155',
    'json': {
    'name': 'Mr. Austin Taylor PhD',
    'address': '34808 Katherine Corners\nPort Ashleychester, KS 66901',
},
    'key41923': 'value5755',
    'key69220': 'value35396',
    'key67346': 'value82974',
    'key61717': 'value56564',
    'key17392': 'value68684',
    'key99631': 'value21568',
    'key24599': 'value71361',
    'key77714': 'value45079',
    'key63019': 'value15331',
},
    {
    'id': 17527485945609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Eric Adams',
    'address': '699 Friedman Valleys\nDiazfort, KY 28075',
    'text': 'Increase term bad late. Notice make themselves action space professional. Several however question whole.',
    'email': 'sroberson@example.com',
    'phone_number': '413.217.2296x6250',
    'json': {
    'name': 'Jermaine Campbell',
    'address': '3497 Wells Wells\nSouth Jennifer, AZ 42402',
},
    'key9407': 'value12674',
    'key55686': 'value74138',
    'key72598': 'value86224',
    'key41568': 'value30693',
    'key3876': 'value93958',
    'key5683': 'value45987',
},
    {
    'id': 17527485945620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Mr. John Robles DDS',
    'address': '03390 Erika Keys Apt. 123\nRobertbury, MN 04530',
    'text': 'Political size interest seven source. Large wide option left executive. Daughter form stuff friend sit security only. Entire well whatever around.',
    'email': 'mark09@example.org',
    'phone_number': '460.675.2102x22716',
    'json': {
    'name': 'Gina Mcgee',
    'address': '57140 Frey Lakes\nJohnsonshire, WA 62641',
},
    'key78397': 'value39218',
    'key80005': 'value45613',
    'key57814': 'value90503',
    'key77347': 'value78571',
},
    {
    'id': 17527485945631,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Brandon Porter',
    'address': '26457 Curry Circle Apt. 468\nEast Ryan, IN 76263',
    'text': 'Teach must appear space improve. Tax arm anyone catch final. Impact structure century me plan.\nChair child issue. Change exactly late body plant trial job.',
    'email': 'mmoon@example.com',
    'phone_number': '911-327-2343',
    'json': {
    'name': 'Donald Wright',
    'address': '654 Jay Corner\nLeeshire, GU 96952',
},
    'key21194': 'value34804',
    'key86767': 'value69610',
    'key54491': 'value98285',
    'key46755': 'value81032',
    'key21789': 'value67739',
    'key39509': 'value38956',
    'key17771': 'value56334',
    'key8316': 'value24926',
    'key48183': 'value50654',
    'key76539': 'value9962',
},
    {
    'id': 17527485945642,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Michael Evans',
    'address': '54534 Tucker Mission\nWest Jenniferstad, TN 80999',
    'text': 'Hotel carry economic sea. Realize accept degree.\nChoose identify fund. Forget concern color man itself to property. Fund expert air usually seek first my.',
    'email': 'victoria06@example.net',
    'phone_number': '(626)223-4288',
    'json': {
    'name': 'Michelle Shea',
    'address': '61454 Julia Mount\nBassfort, MD 85646',
},
    'key54685': 'value65603',
    'key2883': 'value18999',
    'key77737': 'value53017',
},
    {
    'id': 17527485945653,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Patrick Thomas',
    'address': '345 Pierce Fords\nSouth Brian, VT 75223',
    'text': 'Finish trouble soon leave pull notice including. Position plan information way of industry fact. Your become employee Democrat public east lose.',
    'email': 'timothyray@example.com',
    'phone_number': '(634)616-3216',
    'json': {
    'name': 'Maxwell Terry',
    'address': '5330 Smith Roads\nEast Jennifer, PR 82736',
},
    'key3982': 'value99258',
    'key93956': 'value58250',
    'key81864': 'value48435',
    'key98059': 'value27945',
    'key65558': 'value26728',
    'key59299': 'value91512',
    'key63059': 'value7519',
    'key46197': 'value69958',
    'key84651': 'value13485',
},
    {
    'id': 17527485945664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Erica Shelton',
    'address': '912 Pineda Plain\nLindseyview, TX 55074',
    'text': 'Sit method some room. Five leave them test form. Together choose camera organization.',
    'email': 'hernandezmichael@example.net',
    'phone_number': '856-468-6050x259',
    'json': {
    'name': 'Matthew Gutierrez',
    'address': '073 William Streets\nNew Hunterville, NY 89833',
},
    'key54218': 'value75268',
    'key20177': 'value31353',
    'key77313': 'value17315',
    'key74952': 'value82552',
    'key72104': 'value29958',
    'key85811': 'value22989',
    'key97307': 'value27900',
    'key34424': 'value40887',
},
    {
    'id': 17527485945675,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Courtney Gonzalez',
    'address': '527 Thomas Track\nSouth Jenniferburgh, OH 97141',
    'text': 'People step easy line themselves despite us exactly. Nearly low campaign institution. Hand worry interesting.\nEnvironmental family wear song age. Message then oil ability much.',
    'email': 'johnlee@example.net',
    'phone_number': '+1-404-339-7282x79830',
    'json': {
    'name': 'David Strong',
    'address': '15853 Michelle Port Suite 891\nLake Heatherburgh, CA 02080',
},
    'key61161': 'value21754',
    'key1346': 'value97754',
    'key85076': 'value66990',
    'key47039': 'value99572',
    'key56210': 'value16327',
    'key20951': 'value78282',
    'key54277': 'value32442',
    'key73125': 'value61265',
},
    {
    'id': 17527485945687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Michelle Hughes',
    'address': '711 Jordan Overpass\nVictoriaport, TN 96673',
    'text': 'Big allow until agent. Thus positive personal off check central.\nLeast agency rule fire table. Television staff technology fight whether. Election body much.',
    'email': 'velazquezkristina@example.org',
    'phone_number': '(326)454-0779',
    'json': {
    'name': 'Robert Martinez',
    'address': '4330 Alyssa Mountain\nEast Ashleyland, RI 30456',
},
    'key11712': 'value5202',
    'key52652': 'value56968',
    'key18441': 'value4036',
    'key41181': 'value24524',
},
    {
    'id': 17527485945698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Kimberly Martin',
    'address': '69712 John Spring Apt. 169\nSouth Melinda, WI 81346',
    'text': 'Issue lead first career change full great situation.\nActivity from red rule stop.',
    'email': 'moranamber@example.net',
    'phone_number': '(241)536-9125x658',
    'json': {
    'name': 'Kimberly Franklin',
    'address': '57013 Mcdonald Alley Suite 499\nAngelastad, DE 22376',
},
    'key27172': 'value96151',
    'key28415': 'value54465',
    'key25439': 'value54252',
    'key72833': 'value23694',
    'key58370': 'value54783',
    'key9822': 'value72471',
    'key73728': 'value66910',
    'key99126': 'value61542',
},
    {
    'id': 17527485945710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Nicholas Frazier',
    'address': '4206 Troy Circles Suite 998\nSouth Christian, FM 14538',
    'text': 'Need stay set require leave themselves walk. Almost whatever early matter hot western table hospital.\nBudget hear small skin. Majority after girl far he.',
    'email': 'catherineschmidt@example.net',
    'phone_number': '+1-338-508-2673',
    'json': {
    'name': 'Amber Boyer',
    'address': 'Unit 9042 Box 9696\nDPO AA 49781',
},
    'key38674': 'value6752',
},
    {
    'id': 17527485945719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'John Johnson',
    'address': '82874 John Stravenue\nCarolton, WA 29798',
    'text': 'Phone order other serious learn door send.\nName up there ball trouble series call. Out break base law back far. Within soon baby ready feel or ready.',
    'email': 'kayla22@example.com',
    'phone_number': '3364486472',
    'json': {
    'name': 'Christopher Jones',
    'address': 'USS Walker\nFPO AP 84458',
},
    'key42738': 'value12141',
},
    {
    'id': 17527485945728,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jamie Alvarez',
    'address': 'PSC 9465, Box 4831\nAPO AE 25117',
    'text': 'Develop truth especially involve. Owner site create range media. Truth finally animal executive.\nMain we recent too floor most. Ahead beat be significant serve. Leader room gas nearly party.',
    'email': 'alexanderandrew@example.com',
    'phone_number': '427.811.9475x56766',
    'json': {
    'name': 'Matthew Williams',
    'address': '212 Cody Fall\nGarrettchester, GA 57554',
},
    'key65687': 'value22210',
    'key24448': 'value61306',
    'key83793': 'value82499',
    'key52155': 'value66027',
    'key65889': 'value40313',
    'key51358': 'value845',
    'key71016': 'value49727',
    'key60258': 'value29886',
    'key72134': 'value29159',
    'key8519': 'value90412',
},
    {
    'id': 17527485945737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Luis Mcdonald',
    'address': 'PSC 4088, Box 8551\nAPO AE 46880',
    'text': 'Away administration any however north book case put. Apply general eye world wish.\nSouthern ground direction involve moment send. Stage memory test say rich. Section mouth fire bit especially.',
    'email': 'donaldortiz@example.com',
    'phone_number': '001-341-394-6854x90984',
    'json': {
    'name': 'Erika Harper',
    'address': '42327 Deborah Walk\nCarterbury, CT 04772',
},
    'key15594': 'value94926',
    'key8190': 'value33416',
    'key66994': 'value65994',
    'key10944': 'value94161',
    'key13814': 'value41695',
    'key42996': 'value72123',
    'key64696': 'value24895',
    'key1091': 'value82064',
},
    {
    'id': 17527485945747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Nicole Jones',
    'address': '6505 Davis Points\nPort Sean, CT 74345',
    'text': 'Institution imagine same. Beautiful may without. Vote method somebody interesting wear top.\nLawyer scientist reveal since sense education where. World city your popular.',
    'email': 'shelly72@example.com',
    'phone_number': '219.239.7100x373',
    'json': {
    'name': 'Valerie Cochran',
    'address': '0705 Laura Junction Apt. 058\nHaysfurt, PA 02235',
},
    'key8361': 'value20891',
    'key17815': 'value56331',
    'key21000': 'value84841',
},
    {
    'id': 17527485945758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Kayla Mitchell',
    'address': '633 Jacobson Gateway\nLake Ian, NV 81616',
    'text': 'Trial say science reach. Ground home lot approach.\nHot international occur.',
    'email': 'brent22@example.net',
    'phone_number': '001-511-985-1515x5130',
    'json': {
    'name': 'Rebecca Cortez',
    'address': '0834 Clark Island Apt. 759\nStacymouth, MO 54502',
},
    'key37482': 'value46701',
    'key83813': 'value39018',
    'key69765': 'value90400',
    'key43340': 'value62569',
    'key33244': 'value6319',
    'key80424': 'value59135',
    'key10499': 'value27213',
    'key85693': 'value10545',
    'key23499': 'value27568',
    'key301': 'value95131',
},
    {
    'id': 17527485945769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Karla Bell',
    'address': '1706 Stephanie Loaf Apt. 475\nBrowntown, RI 43568',
    'text': 'Remember treat guy hour. Word understand pattern dinner wife. Spring wide where test good language.\nAttention hour pick point cell design. Carry produce shoulder news.',
    'email': 'janechambers@example.com',
    'phone_number': '(488)986-2925x604',
    'json': {
    'name': 'Stephanie Peters',
    'address': '1891 Bradford Loop\nWest Jonathanfurt, KS 98429',
},
    'key90880': 'value33235',
    'key70513': 'value19713',
    'key99763': 'value17324',
    'key26588': 'value39627',
    'key96438': 'value13529',
    'key64804': 'value83344',
    'key17557': 'value41076',
    'key27350': 'value22389',
    'key11499': 'value73817',
    'key39539': 'value82508',
},
    {
    'id': 17527485945782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Kimberly Robinson',
    'address': '22413 Torres Wells Apt. 357\nSouth Jamesberg, ND 42314',
    'text': 'Ok consider watch theory say. Believe bring ability themselves woman nothing mouth operation. Out evening reveal challenge pressure skill station manager.',
    'email': 'fschaefer@example.net',
    'phone_number': '(849)701-8047x696',
    'json': {
    'name': 'Jessica Matthews',
    'address': '64305 Kristin Row Suite 512\nWest Carla, OK 74336',
},
    'key63374': 'value1724',
    'key4515': 'value99546',
    'key39826': 'value82350',
},
    {
    'id': 17527485945792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Heather Mcfarland',
    'address': 'Unit 9360 Box 9364\nDPO AE 38343',
    'text': 'Recognize business rule lead. Pressure likely cell even adult receive. Speak go then camera guy catch million.\nWithout watch away region positive ten. I reach think. Kind wish small letter.',
    'email': 'hrogers@example.org',
    'phone_number': '001-659-778-8537x879',
    'json': {
    'name': 'Brian Berry',
    'address': '3994 Martinez Station\nNew Laurenmouth, MI 39536',
},
    'key7659': 'value81275',
    'key12442': 'value42441',
    'key99734': 'value55813',
},
    {
    'id': 17527485945802,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Sherry Morris',
    'address': '029 Jonathan Rest\nNew Jose, MP 61732',
    'text': 'People they go focus send concern arrive. Training care that.',
    'email': 'lindseyclark@example.com',
    'phone_number': '597.486.6087',
    'json': {
    'name': 'Michael Cook',
    'address': 'PSC 4433, Box 8070\nAPO AP 61581',
},
    'key29977': 'value39181',
    'key21708': 'value87578',
    'key28429': 'value61705',
    'key91378': 'value84722',
},
    {
    'id': 17527485945811,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Stephanie Walker',
    'address': '8357 Moody Pines Apt. 849\nJohnberg, UT 75276',
    'text': 'Performance same economic table commercial there but. Collection person war try none ten. Stay compare really main deep real worker amount.',
    'email': 'lhughes@example.net',
    'phone_number': '(842)757-4157',
    'json': {
    'name': 'Patrick Lee',
    'address': '434 Stephens Greens Apt. 493\nPetersentown, OR 11694',
},
    'key17081': 'value78918',
    'key85255': 'value80124',
    'key98016': 'value45763',
},
    {
    'id': 17527485945821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Renee Caldwell',
    'address': 'Unit 9988 Box 3409\nDPO AP 25410',
    'text': 'Color prove seek cost challenge. Security world guess specific world. Exactly keep always room pick three style.',
    'email': 'harrisamber@example.org',
    'phone_number': '(327)610-0377x5981',
    'json': {
    'name': 'Brittany Meyer',
    'address': '926 Scott Via\nRonaldville, SD 93902',
},
    'key96321': 'value44237',
    'key17447': 'value15272',
    'key61207': 'value88231',
    'key41145': 'value53253',
    'key27998': 'value38229',
    'key62887': 'value85674',
    'key59057': 'value10448',
    'key78191': 'value9773',
    'key71786': 'value86010',
},
    {
    'id': 17527485945831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Amber Jones',
    'address': '734 Cruz Freeway Suite 632\nLake Nicole, PR 05124',
    'text': 'History name read word. Benefit perhaps yet agreement available.\nGo happy partner contain traditional. According see performance above me prepare remember sort.',
    'email': 'jordan22@example.net',
    'phone_number': '(505)693-6523x074',
    'json': {
    'name': 'Paul Martin',
    'address': '3966 Clayton Inlet Suite 425\nRossburgh, SD 64215',
},
    'key18136': 'value24694',
    'key21665': 'value97689',
    'key8': 'value77063',
    'key67483': 'value33084',
},
    {
    'id': 17527485945841,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Eric Park',
    'address': 'USNV York\nFPO AE 52546',
    'text': 'Data tend worry them industry true. New significant seat argue.\nBusiness buy movement. Question international young present.',
    'email': 'dawn96@example.org',
    'phone_number': '301.570.8367x282',
    'json': {
    'name': 'Carmen Frazier',
    'address': '460 Jill Grove Apt. 205\nLake Alex, ND 90882',
},
    'key63645': 'value81086',
    'key96843': 'value34087',
    'key65392': 'value88205',
    'key7493': 'value85077',
    'key7300': 'value88514',
    'key16498': 'value94863',
    'key24692': 'value50001',
    'key24074': 'value56716',
    'key88855': 'value31774',
},
    {
    'id': 17527485945851,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Nicole Young',
    'address': '497 Chen Oval Apt. 754\nBowmanbury, MH 98502',
    'text': 'Believe friend nothing story I evening audience. Police media include resource my together. Country feel side.',
    'email': 'melissalewis@example.org',
    'phone_number': '226.972.6312x0246',
    'json': {
    'name': 'Jennifer James',
    'address': '8996 Robinson Lodge\nStaceychester, RI 34922',
},
    'key88862': 'value9628',
    'key80751': 'value75415',
    'key36833': 'value73416',
    'key26033': 'value72902',
    'key28582': 'value83533',
    'key60307': 'value67693',
    'key70738': 'value77554',
},
    {
    'id': 17527485945862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Tracy Taylor',
    'address': 'PSC 4770, Box 4834\nAPO AA 05613',
    'text': 'Reflect whom hour leg school. Wear run purpose care bill in himself.\nForeign statement page letter able also. City describe wrong spend same.\nProduce interesting discuss.',
    'email': 'yjohnson@example.net',
    'phone_number': '+1-622-554-4453',
    'json': {
    'name': 'Taylor Reese',
    'address': '075 Brown Motorway Apt. 292\nMillsmouth, NM 38863',
},
    'key40789': 'value85571',
    'key44653': 'value18058',
    'key45210': 'value68860',
    'key9928': 'value49835',
    'key64757': 'value30669',
    'key7935': 'value91166',
},
    {
    'id': 17527485945871,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Thomas Ray',
    'address': '122 Tyler Fort Apt. 223\nNew Andre, MP 25498',
    'text': 'Reach professor pass place. Red include write upon cost word notice future. Country attention adult team race.',
    'email': 'colemankeith@example.com',
    'phone_number': '466-990-7254x471',
    'json': {
    'name': 'Nicole Barnes',
    'address': '09493 Michelle Mill Apt. 714\nEast Bryanside, MN 59874',
},
    'key24987': 'value46020',
    'key86597': 'value35407',
    'key82328': 'value88249',
    'key51508': 'value52307',
},
    {
    'id': 17527485945882,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Dr. Stacy Mckee',
    'address': '915 Felicia Plain\nNew Adam, VA 86076',
    'text': 'Research writer heavy push free walk letter. Little best outside until agreement board have. Company leave face war position sort her save.',
    'email': 'christophercampbell@example.net',
    'phone_number': '229.574.2056x315',
    'json': {
    'name': 'Brenda Dominguez',
    'address': '8010 Melissa Course Apt. 699\nSouth Ashleyview, PW 55525',
},
    'key26835': 'value58290',
    'key13228': 'value45384',
    'key18513': 'value14505',
    'key4347': 'value91408',
    'key90933': 'value47959',
    'key77491': 'value15069',
    'key32023': 'value29969',
    'key72076': 'value16640',
    'key36610': 'value70156',
},
    {
    'id': 17527485945894,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Darrell Ruiz',
    'address': '602 Price Via\nNew Robertville, DC 72223',
    'text': 'Imagine yard kid.\nAgo with kitchen. Beat color agree vote. Decide career sound attorney name.\nPull generation then Democrat space including. Should decision just about history phone.',
    'email': 'ojackson@example.com',
    'phone_number': '8545217353',
    'json': {
    'name': 'Carlos Tucker',
    'address': '218 William Gardens Suite 478\nLake Craig, LA 74608',
},
    'key60218': 'value81076',
    'key25355': 'value88844',
    'key36546': 'value94864',
    'key69418': 'value27454',
    'key23': 'value71147',
    'key42499': 'value93889',
},
    {
    'id': 17527485945906,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kimberly Burke',
    'address': '9001 Henry Street Apt. 280\nChristopherchester, SC 35583',
    'text': 'Know hard however. Yourself near program thing this. Turn camera region lay.',
    'email': 'setharnold@example.org',
    'phone_number': '001-754-698-2910x8784',
    'json': {
    'name': 'Alejandro Ellis',
    'address': '51386 Cindy Meadow Suite 133\nGrantfurt, ID 97058',
},
    'key59561': 'value38935',
    'key84125': 'value32393',
    'key38018': 'value320',
    'key26225': 'value19070',
    'key16946': 'value38299',
    'key69491': 'value15548',
    'key82741': 'value33584',
    'key70730': 'value5569',
    'key40346': 'value38953',
},
    {
    'id': 17527485945929,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Brianna Cox',
    'address': '70834 Moore Forge Suite 300\nWest Lisa, MP 74205',
    'text': 'Benefit against away.\nModern professional despite where beautiful. Television friend capital create before start receive.',
    'email': 'norrisfelicia@example.net',
    'phone_number': '426-734-4622x09225',
    'json': {
    'name': 'Cristian George',
    'address': '851 Wilson Drives Apt. 468\nAshleytown, WI 27620',
},
    'key72625': 'value3249',
    'key2482': 'value40675',
    'key66107': 'value82368',
    'key71068': 'value49764',
    'key86188': 'value53530',
    'key6785': 'value7654',
    'key33702': 'value44818',
},
    {
    'id': 17527485945943,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Tiffany Ward',
    'address': '85192 Hopkins Lights Apt. 338\nSouth Robertview, WV 03066',
    'text': 'According break note can strong stage clearly sometimes. Our billion call present set kid student. Over water send soon.\nForward writer model foreign.',
    'email': 'nbutler@example.net',
    'phone_number': '(960)862-4881',
    'json': {
    'name': 'Gregory Chavez',
    'address': '637 Moreno Divide Suite 479\nRussellport, NV 98411',
},
    'key13426': 'value69152',
    'key94521': 'value69253',
    'key59984': 'value545',
    'key91544': 'value2868',
    'key62526': 'value87936',
    'key86936': 'value12917',
    'key13947': 'value34980',
    'key70360': 'value56915',
    'key95125': 'value23305',
    'key9673': 'value6048',
},
    {
    'id': 17527485945955,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Elizabeth Dennis',
    'address': '1752 Mckenzie Underpass Suite 738\nHallmouth, CA 55753',
    'text': 'Really impact to culture trouble piece. The material task. Central success measure six eat. He where interview must head hit view.',
    'email': 'johnsonanna@example.com',
    'phone_number': '(438)368-9047x192',
    'json': {
    'name': 'Richard Obrien',
    'address': '101 Daniel Cliffs Suite 434\nBrianport, VI 30470',
},
    'key5105': 'value98417',
    'key18983': 'value41353',
    'key90935': 'value48511',
    'key60436': 'value95707',
    'key98245': 'value18423',
    'key51275': 'value22580',
    'key94426': 'value52889',
    'key34547': 'value41109',
},
    {
    'id': 17527485945968,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jonathan Wolf',
    'address': '76333 Blevins Flat Apt. 395\nEast Jennifer, TX 41463',
    'text': 'Expert seven man prove front. Manager condition author street.\nLocal fund would test person southern live. Act field realize simply my mean them.',
    'email': 'fergusonjulie@example.net',
    'phone_number': '(772)513-3367',
    'json': {
    'name': 'Madeline Howe',
    'address': '3634 William Hollow Suite 688\nYoungville, ND 49019',
},
    'key32598': 'value37236',
    'key31810': 'value30979',
    'key6484': 'value42828',
    'key85566': 'value32234',
    'key85564': 'value12536',
    'key13368': 'value32872',
    'key74942': 'value19148',
    'key93823': 'value3840',
    'key28152': 'value31167',
    'key16422': 'value87271',
},
    {
    'id': 17527485945981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Matthew Forbes',
    'address': '443 Peters Lake\nCurtisborough, TX 78633',
    'text': 'Treat upon yes world bank realize positive. Write institution still wind. Speech figure position defense house believe.',
    'email': 'gregorykelly@example.net',
    'phone_number': '345-674-2089x416',
    'json': {
    'name': 'Rita Oliver',
    'address': '102 Woodard Field Suite 252\nRickyview, MN 66984',
},
    'key27173': 'value50967',
    'key31067': 'value99481',
    'key83117': 'value10122',
    'key86718': 'value517',
    'key33268': 'value73820',
    'key79318': 'value27932',
    'key22132': 'value29569',
    'key90495': 'value22603',
    'key66225': 'value69188',
},
    {
    'id': 17527485945993,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Richard Larson',
    'address': '374 Sharon Estate\nElliottbury, FL 93048',
    'text': 'Soldier class debate while stock. Reality decade to risk I same information. Here several cut.\nIssue grow write one. Other explain capital time step. Carry without who prepare civil measure.',
    'email': 'icummings@example.net',
    'phone_number': '001-731-690-2858x880',
    'json': {
    'name': 'Lee Smith',
    'address': '13146 Chavez Well Apt. 184\nEarlchester, CT 24480',
},
    'key46745': 'value93975',
    'key4980': 'value90860',
},
    {
    'id': 17527485946004,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Christy Townsend',
    'address': '50632 Dillon Loop Suite 776\nEllenburgh, OR 94496',
    'text': 'Daughter government news amount. Majority manage argue opportunity authority. Run lead friend above program.',
    'email': 'robert28@example.net',
    'phone_number': '001-951-791-0331',
    'json': {
    'name': 'Shawn Howard',
    'address': '57398 Jennings Loaf Suite 399\nSouth Benjamin, AL 33989',
},
    'key7338': 'value65954',
},
    {
    'id': 17527485946015,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Lisa Harvey',
    'address': '455 Joshua Shoals Apt. 476\nJeffreyborough, WV 08409',
    'text': 'Talk money young. Mind just pick gas environmental doctor. Car me letter first soldier.\nScience Mrs sing field those. Cause child sure off chair. Administration something natural.',
    'email': 'everettbrian@example.org',
    'phone_number': '983-275-1171x02400',
    'json': {
    'name': 'Brian Johnson',
    'address': 'USCGC Hernandez\nFPO AA 86639',
},
    'key62151': 'value49437',
    'key29446': 'value42390',
    'key2878': 'value40979',
},
    {
    'id': 17527485946026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Linda Medina',
    'address': '69434 Tran Villages Suite 282\nEast Jenniferton, PA 17652',
    'text': 'May up election staff budget leave speech. Customer begin but usually such stuff.',
    'email': 'robertsonjustin@example.com',
    'phone_number': '001-729-710-3478x34576',
    'json': {
    'name': 'Michael Waters',
    'address': '5453 May Field\nClaudiahaven, RI 73051',
},
    'key36735': 'value660',
},
    {
    'id': 17527485946038,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Benjamin Adams',
    'address': '1504 Peterson Mission Suite 695\nSouth Ralph, MP 19637',
    'text': 'Benefit state among last series long. Class participant performance government analysis white suddenly.\nThink avoid teach television society me. Beautiful send discover paper southern.',
    'email': 'uwilkins@example.com',
    'phone_number': '(550)829-7149x39949',
    'json': {
    'name': 'Dennis Nelson',
    'address': '66328 Odonnell Ways\nNew Glen, AR 42672',
},
    'key14136': 'value88162',
    'key31205': 'value2843',
    'key78341': 'value4775',
    'key91894': 'value7736',
    'key14622': 'value16114',
    'key79752': 'value31617',
    'key38872': 'value19192',
    'key44917': 'value39787',
    'key89788': 'value89813',
    'key78326': 'value14429',
},
    {
    'id': 17527485946049,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Sherry Shannon',
    'address': '237 Anderson Club Apt. 586\nWest Steven, WY 80589',
    'text': 'Much prepare name population ball.\nReason last book dog control happy a. Mouth short guy finally six its.\nRepresent head direction mother. Money alone learn debate capital. Give hour wall various.',
    'email': 'george83@example.org',
    'phone_number': '756-503-6927x09318',
    'json': {
    'name': 'Alan Gonzales',
    'address': '9095 Odonnell Island\nJennifermouth, UT 62328',
},
    'key47077': 'value24114',
    'key39018': 'value7162',
    'key60218': 'value93704',
    'key94350': 'value96963',
    'key51879': 'value81939',
    'key31354': 'value10227',
    'key70224': 'value49061',
    'key53581': 'value6132',
    'key64676': 'value74995',
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
    'RequestId': 'e572ae0a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_28_440737KyNMuSao',
    'filter': '10+20 <= uid < 20+30',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'uid',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'e572ae0a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_28_440737KyNMuSao',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752748600.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrue1020Uid20301752748600Json()
    test.run_tests()
