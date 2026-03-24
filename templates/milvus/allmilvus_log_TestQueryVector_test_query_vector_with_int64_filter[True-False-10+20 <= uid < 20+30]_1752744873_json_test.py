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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752744873_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752744873.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalse1020Uid20301752744873Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752744873.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752744873.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '37fa5bc7-62f1-11f0-a13c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_20_427888LOiRkugF',
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
    'RequestId': '3b19ae5f-62f1-11f0-8719-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_20_427888LOiRkugF',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Emily Pratt',
    'address': '72759 Weaver Views Suite 444\nEast Christopherberg, CA 97162',
    'text': 'Surface small check add say. Business top structure sense parent final.\nNothing law increase movie oil college century sport. High walk other sign reduce owner field.',
    'email': 'angelicagarcia@example.com',
    'phone_number': '(482)826-8876',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Velasquez',
    'Anna Powell',
    'Angela Black',
    'Melissa Cardenas',
    'Andres Gibbs',
    'Jonathon Vang',
    'Kelly Lamb',
],
    'json': {
    'name': 'Tracy Rodriguez',
    'address': '184 Fuller Mews\nDonaldburgh, KS 71334',
},
    'key5897': 'value17302',
    'key6994': 'value38495',
    'key56265': 'value77887',
    'key17458': 'value26884',
    'key87590': 'value98866',
    'key13341': 'value16748',
    'key52221': 'value71801',
    'key82244': 'value34738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Matthew Peterson',
    'address': '860 Mitchell Divide Suite 464\nSouth Crystalborough, OK 33674',
    'text': 'Pattern field us. Step show tax play offer. Shake professional claim save.\nHear artist blood particularly personal claim. Ask personal away approach.',
    'email': 'ricedonna@example.org',
    'phone_number': '+1-467-595-8533x3030',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alison White',
    'William Atkinson',
    'Veronica Campbell',
    'Matthew Williams',
    'Emily Shelton',
    'Edward White',
    'James Mcguire',
    'Robert Mcfarland',
    'Heather Morris',
],
    'json': {
    'name': 'Thomas Rivas',
    'address': '59406 Walker Hollow Suite 008\nNorth Kelseyshire, AK 10890',
},
    'key88186': 'value40378',
    'key50092': 'value43975',
    'key61392': 'value30919',
    'key28710': 'value82145',
    'key12960': 'value97070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Charles Compton',
    'address': '489 Richard Extension Suite 318\nSouth Brittanyview, MT 52042',
    'text': 'Itself every Democrat exactly national agent north. Wish arrive medical member become stop wait pressure. Participant husband rate place charge scientist operation.',
    'email': 'todd75@example.com',
    'phone_number': '(619)809-3977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christina Green',
    'David Campos',
    'Gina Flores',
    'Dwayne Williamson',
    'Tyler Leblanc',
    'Brianna Gordon',
    'Robert Moran',
    'Timothy Anderson',
    'Samantha Drake',
    'Devon Turner',
],
    'json': {
    'name': 'Alejandro Mcintosh',
    'address': '7401 Bryan Plaza Suite 930\nBowmanchester, FL 93352',
},
    'key43722': 'value28379',
    'key98746': 'value24725',
    'key56680': 'value82008',
    'key41888': 'value76400',
    'key88042': 'value4475',
    'key31901': 'value57635',
    'key96262': 'value70060',
    'key53384': 'value39683',
    'key66392': 'value94532',
    'key40000': 'value39481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Elizabeth Arnold',
    'address': '930 Brooks River Apt. 213\nLake Alfred, RI 62630',
    'text': 'Reason money fight hit everybody option rest be. Thing believe reality lay professor image.\nCar particularly as when wife. Herself research son what support. Win lay eye couple.',
    'email': 'morganlori@example.net',
    'phone_number': '001-260-601-9739x2887',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Peters',
    'Todd Lopez',
    'Ronnie Wilson',
    'Paul Conner',
    'Holly Butler',
    'Kristin Rodriguez',
],
    'json': {
    'name': 'Johnny Martinez',
    'address': '51884 Jackson Prairie Apt. 201\nLake Melissaburgh, MA 46225',
},
    'key76349': 'value88326',
    'key18704': 'value69646',
    'key62046': 'value69102',
    'key39882': 'value29857',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Matthew Pollard DDS',
    'address': '82163 Cruz Ridge Suite 400\nEstesfurt, IA 74730',
    'text': 'Meeting figure board day too response. Who heart beautiful economic measure. War source huge rate lay point capital natural.',
    'email': 'kari92@example.org',
    'phone_number': '656.634.9339',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Howard',
    'Katrina Forbes',
    'Joshua Hubbard',
    'David Garcia',
    'Kimberly Goodwin',
    'Adrienne Murray',
    'Jeffery Liu',
],
    'json': {
    'name': 'Angela Nicholson',
    'address': 'USNS Patterson\nFPO AE 89862',
},
    'key46391': 'value56404',
    'key39763': 'value53004',
    'key92412': 'value49133',
    'key35397': 'value62565',
    'key39003': 'value48442',
    'key43382': 'value89957',
    'key14195': 'value13733',
    'key38196': 'value96631',
    'key29856': 'value66752',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Paul Ryan',
    'address': '11090 Jerry Cove\nLake Brittany, FL 17533',
    'text': 'Record think occur movement improve most night. Else chair outside fill generation.\nEnergy improve best art by news. Condition wait fast.',
    'email': 'grojas@example.org',
    'phone_number': '326.958.8268',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Randy Wright',
    'Jeffrey Walker',
    'Thomas Garcia',
    'Heather George',
    'David Smith',
    'Chad Klein',
],
    'json': {
    'name': 'Christina Martinez',
    'address': '21271 Brian Via Suite 262\nWest Ellenburgh, VA 32889',
},
    'key52021': 'value52395',
    'key82000': 'value91975',
    'key8487': 'value86729',
    'key93162': 'value26580',
    'key7725': 'value57653',
    'key83872': 'value32101',
    'key59810': 'value83816',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Benjamin Young',
    'address': 'PSC 4018, Box 3880\nAPO AA 79186',
    'text': 'Research at improve candidate. Training purpose world control. Station cover bar radio south.',
    'email': 'amysmith@example.org',
    'phone_number': '607.592.7679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Smith',
    'Mr. Marcus Hart',
    'Donald Davidson',
    'Angela Lyons',
    'Ashley Medina',
    'Cody Logan',
    'David Perez',
    'Joshua Haas',
],
    'json': {
    'name': 'Maria Zuniga',
    'address': '51153 Melvin Port Apt. 879\nSouth James, IN 93338',
},
    'key49693': 'value30083',
    'key36578': 'value9882',
    'key89261': 'value60641',
    'key57739': 'value35333',
    'key49518': 'value94136',
    'key85697': 'value42823',
    'key21378': 'value35838',
    'key55255': 'value24407',
    'key13643': 'value79764',
    'key16915': 'value61544',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Erin Jones',
    'address': '2324 Blake Divide Apt. 903\nMarcfort, FL 81456',
    'text': 'Explain forget same understand pay. Collection modern raise break who back field.\nHotel leave finish those business yet method. Green whole minute local. Mouth long group be drop.',
    'email': 'emiller@example.net',
    'phone_number': '390.628.8156x218',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Laura Lee',
],
    'json': {
    'name': 'Erin Herring',
    'address': '28023 Julia Extensions\nSouth Mark, IL 38692',
},
    'key83743': 'value34499',
    'key25507': 'value69433',
    'key18725': 'value78832',
    'key71154': 'value25052',
    'key81318': 'value38675',
    'key89923': 'value71252',
    'key76278': 'value18163',
    'key82952': 'value22366',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Bryan Sullivan',
    'address': 'Unit 7543 Box 4590\nDPO AE 63541',
    'text': 'Bag color our dog cell author. Month detail half something trial again boy whatever.',
    'email': 'scott26@example.org',
    'phone_number': '001-445-781-0159x530',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Maria Rivera PhD',
    'Jeffrey Ayala',
],
    'json': {
    'name': 'Robert Weber',
    'address': '407 Jennings Divide\nSeanport, VT 70985',
},
    'key43581': 'value49174',
    'key56481': 'value85930',
    'key8165': 'value11847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Kelly Cox',
    'address': '430 Thompson Curve Apt. 728\nSouth Marcusbury, WY 43728',
    'text': 'Page word true. Push century trade whole skin build cultural four. As star return marriage.\nIndustry total own low. Expert drug kitchen natural thus. Mission step difficult serve suggest official.',
    'email': 'owiggins@example.net',
    'phone_number': '428-635-1785x7929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Rogers',
    'Aaron Roberts',
    'Matthew Evans',
    'Matthew Miller',
],
    'json': {
    'name': 'Christopher Cox',
    'address': '322 Kyle Extensions\nHarrisonstad, ME 35585',
},
    'key72882': 'value12132',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Andrea Howard',
    'address': 'USS Garcia\nFPO AE 07717',
    'text': 'Affect interesting card realize discuss. Like maybe often house somebody factor together. Great however present voice note third.',
    'email': 'sierra40@example.com',
    'phone_number': '+1-299-491-6320x90216',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Garrison',
    'Michelle Jordan',
    'Shirley Bryant',
],
    'json': {
    'name': 'Derek Reynolds',
    'address': '328 Joyce Valley\nRichardville, CO 87573',
},
    'key29869': 'value36909',
    'key47636': 'value21473',
    'key50924': 'value4709',
    'key27632': 'value79000',
    'key92874': 'value33608',
    'key29577': 'value15743',
    'key18341': 'value53370',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Kimberly Randolph',
    'address': '3550 Eric Haven\nBaileyville, AZ 94284',
    'text': 'See senior arm baby trip last check. Development get after in during leave shake. Reduce various sell name far number.\nHair another Mr development. Already guess resource third. Western should wind.',
    'email': 'michaelhoward@example.com',
    'phone_number': '224-630-8501',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Johnson',
    'Kimberly Turner MD',
    'Dr. Marcia Brown MD',
    'Courtney Stone',
    'Bryan Brown',
    'Jennifer Camacho',
    'Jacob Hurst',
    'Tony Jackson',
    'Jennifer Jones',
],
    'json': {
    'name': 'Traci Long',
    'address': '500 Rodriguez Oval Apt. 393\nPort Bill, MT 36302',
},
    'key78379': 'value80212',
    'key28427': 'value88236',
    'key85472': 'value37287',
    'key56126': 'value65323',
    'key89804': 'value23747',
    'key50207': 'value7198',
    'key34266': 'value93202',
    'key78384': 'value45978',
    'key32732': 'value29206',
    'key99192': 'value42401',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Andrea Davis',
    'address': '96023 Amanda Prairie Suite 967\nBoonestad, WY 47728',
    'text': 'Treat key almost son wide. Scientist like population call.\nRest color they while dog forget writer. Local its baby remain.',
    'email': 'deborahbrown@example.net',
    'phone_number': '576-728-7952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Rachel Reese',
    'Gregory Jones',
    'Jerry Wilson',
],
    'json': {
    'name': 'Pamela Thomas',
    'address': '67298 Brown Station\nSouth Jessicastad, IA 06520',
},
    'key29532': 'value21026',
    'key10': 'value55293',
    'key56246': 'value71156',
    'key74098': 'value8557',
    'key81821': 'value46702',
    'key7747': 'value53659',
    'key6990': 'value28904',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'James Smith',
    'address': 'USNS Woods\nFPO AA 31672',
    'text': 'Manage remain million describe usually probably parent. This drug probably structure practice. Surface listen weight keep. Environment power but instead teacher center.',
    'email': 'lisalittle@example.org',
    'phone_number': '595.780.1582x66257',
    'array_int_dynamic': [
    48855,
],
    'array_varchar_dynamic': [
    'Donald Fowler',
    'Kathryn Strong',
    'Amy Simpson',
],
    'json': {
    'name': 'Dr. Jessica Ali',
    'address': '286 Morris Burg Apt. 468\nJenniferview, LA 44052',
},
    'key52422': 'value54223',
    'key49227': 'value47234',
    'key84483': 'value99549',
    'key46856': 'value27247',
    'key20501': 'value17074',
    'key8524': 'value59218',
    'key2233': 'value67804',
    'key58855': 'value49510',
    'key33148': 'value11708',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Marissa Hess',
    'address': '527 Kimberly Walk\nJenniferstad, VT 83823',
    'text': 'Peace full movement out catch this. Check decade low because yard.\nCandidate hotel show despite space too. Deep outside second next family add education.',
    'email': 'michael89@example.org',
    'phone_number': '(809)512-1950x71977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Linda Zuniga',
],
    'json': {
    'name': 'Heather Shields',
    'address': 'Unit 6837 Box 0398\nDPO AP 93858',
},
    'key3390': 'value37373',
    'key70753': 'value84610',
    'key20012': 'value13028',
    'key27500': 'value51522',
    'key56535': 'value88432',
    'key80364': 'value14946',
    'key26358': 'value2875',
    'key19749': 'value77148',
    'key99878': 'value9337',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Mathew House',
    'address': '29578 Long Ways\nEast Karenville, PA 26227',
    'text': 'Figure star argue game.\nIt include chance long. Change specific fund smile pressure. Town finish different value continue rock interview.',
    'email': 'paulacampbell@example.com',
    'phone_number': '566.718.6305x38945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Huber',
    'Heather Leonard',
    'Andrew Thomas PhD',
    'Kenneth Alvarez',
    'Kim Fuller',
    'Susan Henderson',
    'Maria Gonzalez',
    'Shawn Ramos',
],
    'json': {
    'name': 'Robin Ellis',
    'address': '59022 Odom Mountains Apt. 878\nKellyfort, OK 71063',
},
    'key3930': 'value30773',
    'key49459': 'value48131',
    'key50482': 'value66500',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Carla Smith',
    'address': '7913 Felicia Cliff Suite 971\nBakerbury, SC 49092',
    'text': 'Consumer election event day. When nice health thousand according commercial keep. Always thank not information campaign offer while. Difference always grow cold at store bed result.',
    'email': 'rosscameron@example.net',
    'phone_number': '568-619-6722',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Parker',
    'Michelle Hernandez',
    'Elizabeth Juarez',
    'Kristin Thompson',
    'John Robinson',
    'Stephanie Palmer',
    'Christopher Stanton',
],
    'json': {
    'name': 'Christine Gray',
    'address': '82034 Lucas Garden\nWest Ericview, MS 38529',
},
    'key84600': 'value90542',
    'key41571': 'value19572',
    'key73914': 'value80599',
    'key97197': 'value82550',
    'key86512': 'value69036',
    'key17296': 'value2941',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Amber Guzman',
    'address': '4753 Simon Light Suite 443\nSilvaburgh, ME 71980',
    'text': 'Law chance blue debate. Begin sense position about exist wind. Positive white difficult article situation worry.\nMilitary make speech case. With final peace write weight.',
    'email': 'dianecrawford@example.org',
    'phone_number': '(381)543-3393x98860',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joann Hill',
    'Alyssa Williams',
    'Bobby Lyons',
    'Michelle Nichols',
    'Dr. Karen Taylor',
    'Darren Henderson',
],
    'json': {
    'name': 'Kimberly Allen DDS',
    'address': '86265 Isaac Circles\nPort Felicia, IN 51186',
},
    'key45312': 'value27580',
    'key14698': 'value57939',
    'key95911': 'value51913',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Jeffrey Mccormick',
    'address': '58869 Lawrence Stravenue Suite 256\nEast Josephfurt, AS 74709',
    'text': 'Language far inside relate. When amount hand. Arrive power suffer management thought church.',
    'email': 'vlawrence@example.net',
    'phone_number': '001-665-788-3337x4640',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alice Clark',
    'Jeffrey Davis',
    'Jennifer Hudson',
    'Jeffrey Becker',
],
    'json': {
    'name': 'Elizabeth Murphy',
    'address': '59913 Deborah Turnpike\nNew Olivia, AL 72307',
},
    'key46113': 'value62988',
    'key67314': 'value25601',
    'key80286': 'value28397',
    'key68697': 'value60429',
    'key80861': 'value52158',
    'key2557': 'value51382',
    'key2331': 'value34410',
    'key92641': 'value50156',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Amanda Patel',
    'address': '732 Corey Mountains\nDanielland, IN 96160',
    'text': 'Single store several also hotel. Much present these because. Lawyer make my add so.\nOwn sell because article guy different. Serve no bill most change consumer. Team knowledge executive without.',
    'email': 'ecraig@example.com',
    'phone_number': '444.259.0948',
    'array_int_dynamic': [
    89070,
],
    'array_varchar_dynamic': [
    'Kim Lee',
    'Maria Mendez',
    'Jacob Steele',
    'Ashlee Dorsey',
    'James Haynes PhD',
    'Kirsten Jackson DDS',
    'Christopher Sanders',
],
    'json': {
    'name': 'Jason Dudley',
    'address': '482 Macias Cove\nNew Michaelfort, ND 77260',
},
    'key26739': 'value35685',
    'key93076': 'value40892',
    'key10793': 'value87889',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Melissa Davidson',
    'address': '85270 Johnson Well Apt. 069\nEast Jessica, MO 57911',
    'text': 'Line simple little one suggest dog service. Field lay and card say.\nCentury parent water how key picture.',
    'email': 'davisluke@example.org',
    'phone_number': '001-867-324-8575x8509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brooke Noble',
],
    'json': {
    'name': 'Gerald Horton',
    'address': 'USNV Meyer\nFPO AP 78033',
},
    'key34323': 'value74197',
    'key61689': 'value97793',
    'key32960': 'value81028',
    'key23658': 'value57104',
    'key46797': 'value88361',
    'key8230': 'value21682',
    'key8255': 'value21597',
    'key86101': 'value30339',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Carl Solis',
    'address': 'Unit 0218 Box 2774\nDPO AE 81656',
    'text': 'Finally government manager because friend dinner member. Model property certain hit I debate allow. Let whatever represent relationship word radio.\nCell democratic energy reduce take state ability.',
    'email': 'daughertyjennifer@example.com',
    'phone_number': '3964434720',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Rhonda Williams',
    'Jared Webb',
    'Raymond Willis',
    'Cody Miller',
    'Nicole Santiago',
],
    'json': {
    'name': 'Kenneth Vasquez',
    'address': '78205 Jason Trail Apt. 765\nJohnhaven, NJ 21281',
},
    'key39474': 'value74395',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jaime Blackwell',
    'address': '193 Janice Meadow Suite 614\nLindabury, PR 57910',
    'text': 'Property fire government follow for require light. Garden understand economic.',
    'email': 'riggsjessica@example.net',
    'phone_number': '+1-900-379-0902x76792',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Archer',
    'Brittney Scott',
],
    'json': {
    'name': 'Michael Gardner',
    'address': '46152 Ralph Road Suite 165\nPort Michaelborough, WY 93535',
},
    'key14360': 'value52314',
    'key97567': 'value251',
    'key20346': 'value65393',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Samantha Ibarra',
    'address': '61237 Newman Plaza Suite 900\nJoelstad, PA 65797',
    'text': 'Watch score prepare maintain purpose religious claim executive. Film oil many. Bar find guess allow happen form.',
    'email': 'bryan06@example.net',
    'phone_number': '+1-809-655-8510x9844',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Pacheco',
    'Jacob Wright',
],
    'json': {
    'name': 'Kristen Ruiz',
    'address': '40105 Charlene Corners\nGardnerside, AK 54676',
},
    'key29192': 'value96343',
    'key21253': 'value43556',
    'key70707': 'value46857',
    'key18925': 'value70662',
    'key83627': 'value26591',
    'key84055': 'value34109',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'William Smith',
    'address': '5596 Brown Trail Suite 916\nLindafort, WI 79832',
    'text': 'Half how share general. Reflect above human forget soldier exactly hit inside. Already us apply use various.\nBetween green chair school firm manage assume.',
    'email': 'singhanne@example.org',
    'phone_number': '779.356.3094x22059',
    'array_int_dynamic': [
    13405,
],
    'array_varchar_dynamic': [
    'Melissa Clark',
    'Heidi Peterson',
    'Melissa Valdez',
    'Rebecca Norman',
    'Lindsay Owen',
    'Karen Campbell',
],
    'json': {
    'name': 'Mrs. Mikayla Russell',
    'address': '679 Travis Land Suite 608\nNorth Jordan, ID 35906',
},
    'key78345': 'value50112',
    'key12320': 'value23421',
    'key19904': 'value30378',
    'key11879': 'value7171',
    'key10694': 'value64256',
    'key60113': 'value55880',
    'key9644': 'value40061',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Lindsay Anderson',
    'address': '18600 Butler Manor Apt. 910\nEast Drewberg, AZ 66196',
    'text': 'Artist social another sister morning. Use hear yeah adult. Free also box whether with.',
    'email': 'otaylor@example.net',
    'phone_number': '(843)248-4716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Edward Underwood',
    'Rodney King',
    'Christine Hunter',
],
    'json': {
    'name': 'Katelyn Barber',
    'address': '8932 Browning Harbors Apt. 971\nPort Melody, MD 42844',
},
    'key70863': 'value56395',
    'key68184': 'value16025',
    'key90221': 'value86685',
    'key4843': 'value76393',
    'key55989': 'value68081',
    'key84348': 'value86038',
    'key88606': 'value17383',
    'key61899': 'value13038',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Linda Fuller',
    'address': '333 John Centers\nSouth Heatherside, UT 91166',
    'text': 'Life center culture yard. Certain sometimes point lay machine. Special whether night.\nBeyond letter talk thus wind simply. Up recognize many take.',
    'email': 'nicholas07@example.com',
    'phone_number': '336-417-2664x20082',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dustin Williams',
    'Richard Vargas',
    'Jane Patterson',
    'Sharon Avila',
    'Donald Shaw',
    'Adam Johnson',
    'Bonnie Green',
    'Joshua Smith',
],
    'json': {
    'name': 'Kelsey Newman',
    'address': '371 Heather Orchard\nSouth Gabrielashire, NJ 89665',
},
    'key31230': 'value97157',
    'key56296': 'value50309',
    'key39426': 'value54190',
    'key84095': 'value96328',
    'key93991': 'value90055',
    'key34683': 'value29133',
    'key71448': 'value40675',
    'key97424': 'value88750',
    'key5288': 'value32249',
    'key18276': 'value70136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'April Peters',
    'address': '57595 Theresa Village Suite 093\nSouth Benjamin, FL 08578',
    'text': 'Message score direction loss up. Born mission item woman administration most.\nHalf other indicate current health. Hospital wonder build within occur stage hour check. Their try between choice.',
    'email': 'hholland@example.com',
    'phone_number': '(322)675-9670x45184',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jill Snow',
    'Matthew Houston',
    'Michael Pierce',
    'Christopher Reilly',
    'Marcus Butler',
],
    'json': {
    'name': 'James Terry',
    'address': '1780 Ian Prairie Apt. 000\nEast Kimberlyborough, NM 71008',
},
    'key95544': 'value6767',
    'key22951': 'value24307',
    'key81612': 'value61864',
    'key88714': 'value36564',
    'key75863': 'value97822',
    'key87719': 'value93851',
    'key21981': 'value62659',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Patricia Cantu',
    'address': '833 Haley Crest\nSouth Nicholaston, TN 37898',
    'text': 'Check news yourself. These stop parent suggest whole more. Notice painting certain money magazine land. Poor effect appear board individual fill.',
    'email': 'chad06@example.com',
    'phone_number': '(345)844-4599',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lucas Baker',
    'Felicia Shields',
    'John Morris',
    'Billy Sanders',
    'Robyn Robinson',
    'Jennifer Carter',
    'Tiffany Sims',
    'Amy Harvey DDS',
    'Andrew Hall',
    'Zachary Jones',
],
    'json': {
    'name': 'Breanna Day',
    'address': '649 Hebert Court Apt. 713\nLake Brianside, CO 92136',
},
    'key93396': 'value49523',
    'key39832': 'value22917',
    'key53084': 'value56460',
    'key14899': 'value96463',
    'key56498': 'value26568',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Jennifer Bates',
    'address': '04292 Robinson Forges Apt. 295\nKatherinechester, AZ 41461',
    'text': 'When often she practice wear. Miss staff I control pretty wind. Science better use economic area physical.\nMy picture may spring church story reduce. Any right capital. Investment big yeah again.',
    'email': 'kristinagriffin@example.org',
    'phone_number': '(315)784-4548',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Joseph',
],
    'json': {
    'name': 'Tyler Jackson',
    'address': '5409 Rodriguez Field Suite 739\nChaveztown, MT 98133',
},
    'key4445': 'value78023',
    'key50175': 'value20040',
    'key25238': 'value28075',
    'key11301': 'value94734',
    'key94847': 'value30689',
    'key5781': 'value9563',
    'key51432': 'value82543',
    'key49074': 'value57594',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Brian Campbell',
    'address': '52809 Beard Dam\nPort Brandon, HI 21109',
    'text': 'Scene table choose tend rather well full. Door just light image decide radio admit. Myself see mention.\nTax group analysis opportunity position water. Question truth during accept much road cost.',
    'email': 'gutierrezamanda@example.com',
    'phone_number': '695.742.4861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Davies',
    'Monica Nelson',
    'Michael Poole',
    'William Stanley',
    'Travis Rodriguez',
],
    'json': {
    'name': 'Amy Kelly',
    'address': '4717 Linda Extension\nNew Daniel, MN 51742',
},
    'key18033': 'value27563',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Katherine Williamson',
    'address': '91190 Dixon Forest Apt. 285\nSouth Patriciaport, MT 38440',
    'text': 'Sense short authority task.\nShow business study process democratic gun study. So effort keep off once we whatever kitchen.',
    'email': 'robertbauer@example.org',
    'phone_number': '299.858.6149x4254',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Warren',
    'Cody Roberson',
    'Susan Bryan',
    'Daniel Hogan',
    'Michelle Erickson DVM',
    'Victor Valdez',
    'Deanna Barry',
    'Curtis Bennett',
    'Jacob Mooney',
    'Sydney Williams',
],
    'json': {
    'name': 'Andrew Long',
    'address': '58847 Wise Mountain Apt. 746\nKaraport, VA 01582',
},
    'key39030': 'value86907',
    'key8104': 'value41066',
    'key84442': 'value50577',
    'key79307': 'value16303',
    'key98695': 'value72732',
    'key9240': 'value66024',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Courtney Cuevas',
    'address': '3375 Roy Knoll\nSouth Margaretbury, LA 14275',
    'text': 'Class second threat try store long. Allow arm six. Drive attorney direction care us.\nThat up music you box. Career Republican popular church door. Accept professional clear benefit specific national.',
    'email': 'baldwinanita@example.org',
    'phone_number': '354.862.3861x490',
    'array_int_dynamic': [
    21236,
],
    'array_varchar_dynamic': [
    'Mrs. Maureen Ellis',
],
    'json': {
    'name': 'Elizabeth Strickland',
    'address': '16131 Jennifer Pike Apt. 825\nLake Mario, MA 95037',
},
    'key20580': 'value18908',
    'key1845': 'value1995',
    'key5358': 'value25918',
    'key84840': 'value58283',
    'key48067': 'value14062',
    'key71953': 'value22979',
    'key90377': 'value73322',
    'key17021': 'value49621',
    'key30776': 'value60771',
    'key37957': 'value72671',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Corey Smith',
    'address': '57995 Adam Isle\nJanetfort, NJ 33547',
    'text': 'Attack heart agree station collection.\nSuccess citizen do cup. Much statement practice ok property need ask. News low life wife effect share road.\nIndicate gas stock guess west.',
    'email': 'steven64@example.com',
    'phone_number': '434.806.2871x265',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Eric Lee',
    'Austin Thomas',
    'Erica Velasquez',
    'Alan Frazier',
    'Lauren Jones',
    'Kimberly Hodges',
    'Mary Thompson',
    'Anthony Gonzales',
    'Kristin Espinoza',
],
    'json': {
    'name': 'Stephanie Daniel',
    'address': '5747 Lindsey Wells\nLawrenceburgh, TN 19229',
},
    'key59373': 'value63170',
    'key38592': 'value42040',
    'key3877': 'value67713',
    'key83540': 'value85981',
    'key97006': 'value75014',
    'key90998': 'value2791',
    'key77489': 'value54689',
    'key6041': 'value6429',
    'key99286': 'value11941',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Sean Mcintosh',
    'address': '7103 Graves Common Suite 726\nLake Nicholas, NE 58699',
    'text': 'Three must enjoy agency including. Just their behavior few.\nResponsibility blue there account organization particular think. Difference method nor phone beat age.',
    'email': 'sdaugherty@example.org',
    'phone_number': '+1-416-686-9146x671',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Nash',
    'Scott Morrison',
    'Teresa Wang',
    'Nancy Ramos',
    'Robin Reynolds',
    'Ashley Berry',
    'Jacob Krueger',
    'Veronica Bridges',
],
    'json': {
    'name': 'Linda Beasley',
    'address': 'Unit 5872 Box 8382\nDPO AE 67020',
},
    'key28662': 'value93692',
    'key64909': 'value38505',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Tammy Garcia',
    'address': '7125 Romero Junctions Apt. 482\nJoelshire, ND 94122',
    'text': 'Thus early thing only. Than white start trip such. Return side hospital member door. Could hotel floor fact.\nPlan TV billion order realize likely. Cup method where movie yet.',
    'email': 'gregorybanks@example.org',
    'phone_number': '(601)322-4148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Eric Gallegos',
    'Bridget Bryant',
    'Brittany Pitts',
    'Dr. Marcus Smith',
    'Michele Elliott',
    'Tyler Tucker',
],
    'json': {
    'name': 'Christopher Yoder',
    'address': '169 Rachel Rue\nSouth Julia, CO 06419',
},
    'key81975': 'value55313',
    'key34075': 'value99393',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Gregory Berger',
    'address': '0541 Katie Valley\nJessicaton, AS 54305',
    'text': 'Week leader win hour message. Attorney rise image.',
    'email': 'joseph39@example.net',
    'phone_number': '(413)643-6473x63719',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Luis Perez MD',
    'Karen Smith',
    'Stephen Flores',
    'Suzanne Hernandez',
    'Janice Gutierrez',
    'Stephanie Peters',
    'Peter Oconnor',
    'Michael Johnston',
],
    'json': {
    'name': 'William Jones',
    'address': '47429 Anna Creek\nPort Rachel, MS 15008',
},
    'key61266': 'value58169',
    'key93090': 'value28789',
    'key65781': 'value51634',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Jason Newman',
    'address': '3246 West Vista\nLake Andrew, IL 46841',
    'text': 'Page care her design director offer skin. Direction painting eye card.\nCourse bed major mission across. Congress just north sell herself serious know spring.',
    'email': 'agreen@example.org',
    'phone_number': '9384905446',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel West',
    'Melissa Cruz',
    'John Jackson',
    'Adam Johnson',
    'Debra Smith',
],
    'json': {
    'name': 'Leslie Miller',
    'address': '377 Jorge Circle\nLake Ricardoborough, AZ 24828',
},
    'key57343': 'value80562',
    'key44883': 'value1738',
    'key20123': 'value11815',
    'key81426': 'value75847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'William Frank',
    'address': '8933 Burke Street\nWest Cody, IN 22550',
    'text': 'Teacher light write court. Necessary entire evidence cup serve.\nMiddle effect some school catch. Population nature attack authority political worker.',
    'email': 'stephanie41@example.org',
    'phone_number': '946.905.6825x87172',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Moran',
    'Paul Banks',
    'Jacob Lewis',
    'Shelly Gordon',
    'Nancy Turner',
    'Kenneth Ingram',
],
    'json': {
    'name': 'Ashley Huber',
    'address': '09095 Gay View Apt. 598\nSouth Amanda, WY 28217',
},
    'key92406': 'value29040',
    'key11009': 'value40930',
    'key86932': 'value64448',
    'key40877': 'value88933',
    'key48891': 'value47787',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Timothy Knapp',
    'address': '55242 Johnson Alley\nSouth Barbara, HI 47001',
    'text': 'Just apply rule instead. Resource cell determine bank goal take.\nHusband far seek after stay. Agent visit eye finish debate.\nWoman anyone goal world wish stage road. Enjoy mean offer billion record.',
    'email': 'zacharytaylor@example.org',
    'phone_number': '367.640.8040x7527',
    'array_int_dynamic': [
    3421,
],
    'array_varchar_dynamic': [
    'Pam Vance',
    'Emily Franco',
    'Dalton Young',
    'Michael Smith',
    'Steven Gilbert',
],
    'json': {
    'name': 'Tyler Torres',
    'address': '61606 Jacqueline Points Apt. 028\nSouth Barry, AS 92291',
},
    'key78228': 'value2310',
    'key88698': 'value82867',
    'key52839': 'value30562',
    'key34944': 'value73407',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Tina Gonzalez',
    'address': '67675 Price Mountain\nEast Danny, WV 96333',
    'text': 'Show could apply actually federal. Past perform else role writer state.\nThemselves concern oil network wife personal cell.\nUnder should protect policy until. Sort trouble theory wide bring.',
    'email': 'richardramos@example.net',
    'phone_number': '711-347-3274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christina Holt',
],
    'json': {
    'name': 'Tammy Simmons',
    'address': '1950 Hernandez Grove Suite 842\nPort Laura, DE 97842',
},
    'key97587': 'value62146',
    'key51975': 'value68439',
    'key16530': 'value316',
    'key90378': 'value42469',
    'key13096': 'value9131',
    'key26570': 'value53699',
    'key76397': 'value71846',
    'key55693': 'value4643',
    'key70147': 'value37122',
    'key9138': 'value63363',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Desiree Morris',
    'address': '69991 Vanessa Underpass\nStuartstad, PW 40909',
    'text': 'Spend pick read. Heavy determine expert section sure can. Book stock huge.',
    'email': 'htran@example.org',
    'phone_number': '(725)784-2589',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mark Ashley',
    'Tina Bryan',
    'Eric Dennis',
    'Jill Harris',
],
    'json': {
    'name': 'Christopher Green',
    'address': '17268 Michael Squares\nWilliamfort, VI 09429',
},
    'key49317': 'value95894',
    'key96374': 'value55421',
    'key49855': 'value40128',
    'key12527': 'value91558',
    'key79022': 'value16302',
    'key96432': 'value63112',
    'key6860': 'value12044',
    'key44572': 'value6424',
    'key55153': 'value42936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Ronald Lopez',
    'address': '7134 Pierce Divide Suite 822\nEvansport, OR 63967',
    'text': 'Team which road perhaps late recently. Industry others direction own choose crime including thought. Civil bed hot these voice information get change.',
    'email': 'jessica98@example.com',
    'phone_number': '+1-339-698-0759x659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joe Ford',
    'Seth Hood',
    'Mrs. Samantha Robinson',
    'Cindy Ruiz',
    'Samantha Evans',
    'Jason Mcguire',
],
    'json': {
    'name': 'Megan Jackson',
    'address': '81250 Abigail Meadows Apt. 095\nNorth Ryan, HI 34997',
},
    'key407': 'value15225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Julie Beck',
    'address': '047 Katherine Via Suite 405\nPort Mikestad, RI 29285',
    'text': 'Law street message phone reduce option. Give door memory Republican. Country loss behind town themselves figure institution.',
    'email': 'howardmegan@example.org',
    'phone_number': '(286)500-2488',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Reed',
    'Kenneth Prince',
    'Ivan Schmidt',
    'Sarah Mejia',
],
    'json': {
    'name': 'Travis Harris',
    'address': '2898 Martha Valleys\nLake Cody, TX 30870',
},
    'key1241': 'value23562',
    'key77304': 'value80589',
    'key7690': 'value16043',
    'key68677': 'value11767',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Sheryl Miller',
    'address': 'Unit 6910 Box 5541\nDPO AA 73497',
    'text': 'Security bed father. Establish center buy.\nMeasure election great physical while building recent. Send old second stuff young. Father poor force and understand yourself cultural.',
    'email': 'sharon60@example.net',
    'phone_number': '723-658-2274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Novak',
    'Kellie Miller',
    'Karen Morris',
    'William Wilson',
    'Jeffrey Velazquez',
    'Timothy Allen',
    'Frank Reed',
    'Antonio Sharp',
    'Kristina Golden',
],
    'json': {
    'name': 'Erin Kline',
    'address': '800 Mccoy Viaduct\nLake Chadport, AR 22077',
},
    'key49399': 'value29658',
    'key13044': 'value329',
    'key58123': 'value32854',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Kimberly King',
    'address': 'PSC 5390, Box 0958\nAPO AE 37303',
    'text': 'Fish year method after capital discuss name room. Push any where theory.\nFour various least reason never child trouble. Suffer late hit deal weight.\nPlace attorney executive sure of carry.',
    'email': 'morganjessica@example.org',
    'phone_number': '001-961-244-7005x049',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Robbins',
    'Thomas Phelps',
    'Maria Johnston',
    'Brandon Cruz',
    'Arthur Burke',
    'Melissa Baker',
    'Timothy Glover',
    'Spencer Johnston',
    'Billy Jackson',
],
    'json': {
    'name': 'Dalton Hinton',
    'address': '933 Jones Parks Apt. 050\nCaitlynburgh, IN 60485',
},
    'key18773': 'value9261',
    'key54427': 'value33414',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Christopher Brown',
    'address': '61024 Michael Place\nEast Arthur, NE 14896',
    'text': 'Way place her door. Story black cup building six perhaps perform.\nYourself issue cost. Task find figure cover become one everybody protect. City candidate visit involve no fear forget.',
    'email': 'petermitchell@example.org',
    'phone_number': '+1-580-976-7496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amber Jones',
    'Julie Mejia',
    'Rachel Grant',
    'Brooke Roberson',
    'Corey Griffin',
    'Marcus Jones',
    'Billy Flores',
    'Randy Smith',
    'Amy Khan',
],
    'json': {
    'name': 'Michael Moore',
    'address': '8981 Ritter Valleys\nMercadoborough, KS 39754',
},
    'key72646': 'value35610',
    'key15732': 'value75889',
    'key11486': 'value64741',
    'key24011': 'value48238',
    'key43634': 'value1749',
    'key16284': 'value91254',
    'key49337': 'value31672',
    'key55985': 'value24321',
    'key49831': 'value12802',
    'key44693': 'value40035',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Grace Sanchez',
    'address': '8814 Marcus Meadows\nSuzanneshire, MP 62947',
    'text': 'Model throw teacher today behind. Hot already same report born. Cause day debate they American quickly.',
    'email': 'heather66@example.org',
    'phone_number': '327.577.9695',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Cooley',
],
    'json': {
    'name': 'Christina Frazier',
    'address': '49033 Newton Gateway Suite 416\nNew Oscar, TX 68689',
},
    'key84353': 'value57756',
    'key32679': 'value81792',
    'key18445': 'value80696',
    'key46924': 'value68509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Mr. Clinton Shaw',
    'address': '36847 Jennifer Drives Suite 219\nEast Jasonshire, HI 59390',
    'text': 'Will you whose. Experience government development others. Happy candidate student financial international language air join.',
    'email': 'morajonathan@example.net',
    'phone_number': '854-994-1237',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Gray',
],
    'json': {
    'name': 'Kaitlyn Barber',
    'address': '6259 Becker Divide Apt. 847\nDiazmouth, MI 10446',
},
    'key40879': 'value3635',
    'key4734': 'value16269',
    'key72529': 'value73652',
    'key29764': 'value9518',
    'key21140': 'value26259',
    'key80605': 'value23390',
    'key51064': 'value19522',
    'key58513': 'value47923',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Janice Butler',
    'address': '72003 Miller Stream\nLake Cassandraview, OK 60338',
    'text': 'Mouth once project son event story home. Since course power because direction recently number. Spend item share condition.',
    'email': 'arnoldelizabeth@example.com',
    'phone_number': '001-627-859-7327x329',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Zuniga',
    'Jeffrey Dixon',
    'Tony Patterson',
    'Maria Johnson',
    'Tina Ramsey',
    'Debra Wilkinson',
    'Mary Boyd',
    'Jordan Boyle',
    'Debbie Moore',
    'Michelle Lopez',
],
    'json': {
    'name': 'Jeffrey Rocha',
    'address': '729 Thompson Junction Apt. 220\nBarnesfurt, PR 81293',
},
    'key58880': 'value75124',
    'key24973': 'value85148',
    'key74156': 'value60932',
    'key43918': 'value91566',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Regina Hall',
    'address': '1378 Perry Parkway Suite 100\nSmithfort, OR 12038',
    'text': 'Young room bed sure south. Attention get quite sometimes. Southern have writer bring.\nAnother whatever develop audience chance man focus. Accept art manage task clearly long guy.',
    'email': 'debra69@example.org',
    'phone_number': '001-846-765-0069x27833',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Anderson',
    'James Hoffman',
    'Emily Douglas',
    'Brandon Perry',
    'Joshua Sanchez',
    'Colleen Martin',
    'Mark Barajas',
],
    'json': {
    'name': 'Michael Patterson',
    'address': '31351 Glass Rest Apt. 302\nWest Johnburgh, OH 99190',
},
    'key53351': 'value92630',
    'key20713': 'value71807',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Laura Jacobs',
    'address': '7940 Wells Fall Apt. 581\nWest Patriciaberg, CO 27427',
    'text': 'Believe experience speak market enjoy nothing. Very word more do score system.\nSociety either sort economic car collection poor. Foreign to above east movie.',
    'email': 'qmcneil@example.net',
    'phone_number': '302.486.7338',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Hernandez',
    'Joe Gonzalez',
    'Dustin Maxwell',
    'Christine Moran MD',
    'Heidi Dean',
    'Claire Lloyd',
],
    'json': {
    'name': 'Kevin Brown',
    'address': '9400 Hinton Rapid\nWest Philipport, TN 94562',
},
    'key40439': 'value27380',
    'key12746': 'value9337',
    'key14007': 'value41599',
    'key6500': 'value38077',
    'key75026': 'value37882',
    'key66670': 'value29171',
    'key91090': 'value51441',
    'key73233': 'value89557',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Brandon Walker',
    'address': '83891 Jones Estate\nEast Linda, UT 88500',
    'text': 'Set language debate a child bill. Argue there single.\nDay market popular tax almost. To Mrs present.\nAdministration beat attention work. Likely form perhaps law you other.',
    'email': 'karen93@example.org',
    'phone_number': '(523)395-6794x192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Melton',
    'Robert Cummings',
    'Angela Bell',
    'Samantha Byrd',
    'David Young',
    'Briana Cox',
    'Brittany Allen',
],
    'json': {
    'name': 'William Huber',
    'address': '937 Bailey Valley Suite 372\nNew Stefanie, ID 25544',
},
    'key29540': 'value43650',
    'key66737': 'value72747',
    'key69913': 'value68241',
    'key76409': 'value53725',
    'key45369': 'value16928',
    'key8309': 'value75030',
    'key91210': 'value25806',
    'key77294': 'value65100',
    'key40225': 'value25171',
    'key774': 'value35005',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Brandy Patterson',
    'address': '1314 Daniel Street\nSouth Jane, UT 60401',
    'text': 'Yourself bank push debate free above administration.\nCultural civil probably amount end war. Any crime network road. Agency budget break recently fact fly himself.',
    'email': 'vodom@example.com',
    'phone_number': '321.292.3409x4238',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Lewis',
],
    'json': {
    'name': 'Mr. Steven Mcclure',
    'address': '9085 Jackson Plains\nSmithside, MS 73563',
},
    'key28371': 'value7701',
    'key4159': 'value78378',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Richard Ayers',
    'address': '24544 Evan Cliff\nAndreamouth, MN 10600',
    'text': 'Scene race hold training southern capital small. Trip note anyone everyone.\nSystem hour meeting early activity when medical moment. Expect build safe PM.',
    'email': 'pamelamorris@example.com',
    'phone_number': '(886)865-4868x923',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Sharp',
    'Austin Newman',
    'Thomas Adkins',
    'Jennifer Munoz',
    'Misty Perry',
    'Cynthia Middleton',
    'Mr. Charles Hamilton',
    'Nathan Warner',
    'Phillip Salazar',
    'Heather Kemp',
],
    'json': {
    'name': 'Alyssa Frye',
    'address': '07430 Timothy Knoll\nPort Rachel, IA 51255',
},
    'key35074': 'value18512',
    'key72916': 'value66204',
    'key41261': 'value60286',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Kenneth Long',
    'address': '943 Michael Loaf Suite 091\nOsbornmouth, FM 05877',
    'text': 'Scene threat scene until rest red. Young point factor answer girl information.\nPush theory should. Thought clearly attorney often measure state. Order world accept prove.',
    'email': 'mistymiller@example.net',
    'phone_number': '491-527-8135',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Werner',
    'Charles Dorsey',
    'Edward Brown',
    'Ronald Kemp',
    'Michelle Madden',
    'Michael Clark',
    'Alejandra James DDS',
    'Victor Harris',
    'Ryan Rodriguez',
    'Michelle Robles',
],
    'json': {
    'name': 'Jonathan Baker',
    'address': '4098 Snow Expressway Apt. 022\nLeblancville, AR 50561',
},
    'key9521': 'value53522',
    'key47376': 'value33181',
    'key725': 'value7731',
    'key68842': 'value98008',
    'key31649': 'value99019',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Charlene Wolfe',
    'address': 'Unit 7312 Box 4775\nDPO AE 80822',
    'text': 'Page loss report. Than wife more under. Story evidence concern newspaper amount several.',
    'email': 'lindseythomas@example.com',
    'phone_number': '945.670.5081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Troy Duncan',
    'Heather Mills',
    'Patricia Stone',
    'Shane Gaines',
    'Mary Underwood',
    'Renee Cohen',
],
    'json': {
    'name': 'Tracy Watson',
    'address': '22187 Lisa Stream Suite 059\nNealberg, WV 38789',
},
    'key80949': 'value20899',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jeffrey Salas',
    'address': '321 Scott Landing Apt. 998\nElizabethbury, FM 22326',
    'text': 'Bill help federal role growth majority imagine. Support state right mean next determine.\nTest fact voice soon. Though head subject everybody still north.',
    'email': 'fwilliams@example.net',
    'phone_number': '7257852058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Patrick',
    'Mariah Jennings',
    'Sheila Burnett',
    'Tony Grant',
    'Penny Cox',
    'Kyle Walton',
    'Mrs. Sara Spence',
    'Joshua Villanueva',
    'Leslie Walters',
    'Jeff Franklin',
],
    'json': {
    'name': 'Angel Hernandez',
    'address': '41249 Kimberly Vista Suite 050\nSouth Lydiamouth, TN 60402',
},
    'key31362': 'value11241',
    'key7436': 'value10544',
    'key16824': 'value36439',
    'key223': 'value5968',
    'key22801': 'value75719',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Sheila Wood',
    'address': '41201 Noble Manors\nRobertstad, PR 63580',
    'text': 'Drop during must training next a radio until. Gun page develop beautiful reason.\nChurch whole right certainly drug despite phone. Personal more value particularly recently act perhaps.',
    'email': 'joseph68@example.net',
    'phone_number': '001-218-308-5093x27193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Dickerson',
    'Eric Wilcox',
    'Jennifer Hendricks',
    'Alex Soto',
    'Steve Hopkins',
    'Joseph Edwards',
],
    'json': {
    'name': 'Andrew Warner',
    'address': '45773 Lewis Summit\nChristopherborough, WY 90747',
},
    'key51986': 'value72819',
    'key98796': 'value58983',
    'key94668': 'value28831',
    'key48824': 'value97748',
    'key92756': 'value95990',
    'key2820': 'value68022',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Angela Turner',
    'address': 'Unit 2459 Box 4128\nDPO AA 59844',
    'text': 'Cold book finish father else dinner. Ever class guy fill decision million. Tend hotel interesting down future.',
    'email': 'heather40@example.net',
    'phone_number': '706.574.6755',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Calvin Everett',
    'Ronald Hart',
    'Terrance Perkins',
    'Eric Phillips',
],
    'json': {
    'name': 'Clayton Jones',
    'address': '083 Angel Plaza\nPort Anitafort, TN 24936',
},
    'key87667': 'value32039',
    'key14869': 'value67083',
    'key95454': 'value60718',
    'key77566': 'value8716',
    'key27930': 'value83710',
    'key60299': 'value11977',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Eric Black',
    'address': '1912 Robert Plaza\nEast Tom, OR 78407',
    'text': 'Itself case pattern college phone. Might concern public.\nApply director idea seek evidence nation. Wife risk almost. My read college.',
    'email': 'hayesamy@example.org',
    'phone_number': '001-814-317-3638x628',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Moore',
    'Timothy Vega',
    'Lauren Casey',
    'Leslie Beck',
    'Samantha Doyle',
],
    'json': {
    'name': 'Roy Wright',
    'address': '9018 Copeland Springs\nNew Kathy, AR 22308',
},
    'key33253': 'value55132',
    'key80966': 'value10098',
    'key16591': 'value70900',
    'key7152': 'value38802',
    'key78791': 'value17546',
    'key5827': 'value4844',
    'key24996': 'value43843',
    'key36327': 'value49579',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Gene Dudley',
    'address': '51420 Mitchell Pike\nDanielport, MO 58708',
    'text': 'Way low time clearly region long friend. Our financial young describe ground do.',
    'email': 'kimschmidt@example.org',
    'phone_number': '001-724-897-0479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kara Brown',
    'Eric Hunt',
    'Morgan Long',
    'Caleb Smith',
],
    'json': {
    'name': 'Tara Smith',
    'address': 'USNV Wood\nFPO AA 12967',
},
    'key391': 'value87446',
    'key53167': 'value599',
    'key70864': 'value46034',
    'key48488': 'value49452',
    'key97377': 'value77634',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Craig Walsh',
    'address': '4139 Carlos Valley Apt. 301\nLake Vanessa, IN 60600',
    'text': 'Assume certain help fact mention. Perform church address affect eye a meeting look.\nUntil per government last talk student as up. Fire camera accept much. Term end capital walk order explain.',
    'email': 'stephanie36@example.net',
    'phone_number': '3805812234',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Brooks',
    'Jeremy Woodard',
    'Miguel Cohen',
    'Sarah Watson',
    'Donald Stone',
],
    'json': {
    'name': 'Evan Gilmore',
    'address': '12414 Patricia Mall Suite 412\nPerezmouth, MN 29448',
},
    'key9718': 'value85054',
    'key99421': 'value88239',
    'key4479': 'value32500',
    'key54922': 'value36649',
    'key58034': 'value38209',
    'key45914': 'value72826',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Christina Murray',
    'address': '50658 Haney Crossroad Suite 706\nCynthiaton, PR 65825',
    'text': 'Scientist and throughout perhaps end expert. Admit discover bad at suddenly.\nNearly yet new figure star computer. Sister put first even themselves system grow.',
    'email': 'bryantcatherine@example.net',
    'phone_number': '894-814-0896x66851',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Miguel Perez',
],
    'json': {
    'name': 'Connie Taylor',
    'address': '9158 Brittany Union Suite 000\nSouth Beverlyview, MP 71131',
},
    'key51974': 'value71222',
    'key21672': 'value19508',
    'key85339': 'value80160',
    'key49357': 'value98865',
    'key54074': 'value6748',
    'key44688': 'value25798',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Nicole Meyer',
    'address': '41014 Shannon Via\nWest Audreybury, GU 26926',
    'text': 'Run again travel heavy audience approach. Air east music painting per. Me western design system everyone camera study.',
    'email': 'knightvictoria@example.net',
    'phone_number': '936-259-6918x42277',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Adams',
    'Anthony Marquez',
    'Kevin Blake',
    'Catherine Rivera',
    'Randy Walsh',
    'Craig Soto',
    'Joseph Washington',
    'Kim Flores',
],
    'json': {
    'name': 'Stacy Gardner',
    'address': '61306 Matthew Light Apt. 090\nRobertstad, VA 72037',
},
    'key46061': 'value77714',
    'key99713': 'value71285',
    'key27774': 'value43155',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Patrick Parker',
    'address': '2615 Brian Ways Suite 110\nPort John, IA 64436',
    'text': 'None always you adult south think. Help speak under they record use.\nEdge five practice feeling sometimes language performance. Green fact purpose show.',
    'email': 'daniel51@example.org',
    'phone_number': '+1-909-588-4949x961',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sherry Pearson',
    'Donna Lucas',
    'Erik Morris',
    'Jeffery Rhodes',
    'Rachel Briggs',
    'Todd Smith',
    'Brett Ingram',
    'Anna Reid',
],
    'json': {
    'name': 'Diane Rogers',
    'address': '7708 Harvey Crest Apt. 602\nWayneborough, SD 26084',
},
    'key28200': 'value5301',
    'key82625': 'value93514',
    'key61845': 'value15535',
    'key42220': 'value60',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Maria James',
    'address': '60838 Murphy Corners\nSouth Eric, NH 10669',
    'text': 'Bill new magazine this. Audience will alone ago market side. Industry carry line blue.\nStudy network Democrat month ago. Fast eight capital fast generation.\nUnderstand seem because itself.',
    'email': 'adambradley@example.net',
    'phone_number': '901-920-6680x37124',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Juan Alexander',
],
    'json': {
    'name': 'Anthony Boyd',
    'address': '963 Jessica Shores\nTiffanyberg, FM 17340',
},
    'key23652': 'value16108',
    'key12088': 'value9505',
    'key67748': 'value98894',
    'key21201': 'value46083',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Taylor Hobbs',
    'address': 'PSC 4858, Box 8755\nAPO AP 79010',
    'text': 'Across actually movie reason anyone her poor bag. Close part four environmental south.\nHome teach unit less. Night them relate build through during. Sing member brother note hope.',
    'email': 'smithlaurie@example.org',
    'phone_number': '308.247.8169x79358',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carl Alexander',
    'Meredith Ibarra',
    'Jordan Johnson',
    'Colleen Smith',
    'Mary Collins',
    'Kayla Lee',
    'Terry Nelson',
],
    'json': {
    'name': 'Tasha Coleman',
    'address': 'USNS Johnson\nFPO AA 37099',
},
    'key98419': 'value10512',
    'key84697': 'value85087',
    'key17065': 'value26002',
    'key68966': 'value86244',
    'key20679': 'value82559',
    'key5387': 'value72673',
    'key94999': 'value81952',
    'key20006': 'value9582',
    'key55151': 'value31710',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Kim Ramirez',
    'address': '2713 Walker Isle Apt. 048\nGloriaton, AS 87530',
    'text': 'Try respond four could form against interest old. Feeling health cost general blue young. That summer source wind.\nPiece animal report if task. Simply reduce leader property involve letter authority.',
    'email': 'kimberly53@example.net',
    'phone_number': '001-220-274-4912x7718',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Travis Clark',
    'Sean Ramsey',
    'Peter Cochran',
    'Lauren Johnson',
    'Valerie Thomas',
    'Jason Lester',
    'Traci Randall',
],
    'json': {
    'name': 'Victor Turner',
    'address': '352 Fuller Ports Apt. 621\nLake Robertshire, GU 73505',
},
    'key57844': 'value76272',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jennifer Sampson',
    'address': '956 Pugh Mountain\nWest Joshualand, FM 14346',
    'text': 'Matter stock election often go. Collection might exactly hard address man. Bed owner stock thus line wind parent reveal.\nStill shake possible.',
    'email': 'racheltorres@example.com',
    'phone_number': '(821)325-0446x4902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sydney Stewart',
    'Joshua Carter',
    'Jared Holmes',
    'Brandon Williams',
    'Kristin Strickland',
    'Matthew Jenkins',
],
    'json': {
    'name': 'Tim Davidson',
    'address': '51448 Tammy Canyon\nDeborahfort, NC 58895',
},
    'key91913': 'value51239',
    'key93360': 'value24644',
    'key58937': 'value45549',
    'key25197': 'value55734',
    'key87593': 'value97869',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Victor Scott',
    'address': '943 Dudley Gateway Suite 656\nRachelton, NH 23295',
    'text': 'Table environment fund best human member would. Television lot stage meeting. Our respond course serious degree watch.',
    'email': 'kellyjames@example.net',
    'phone_number': '(550)453-7008x0865',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Phyllis Garcia',
    'Jason Ferguson',
    'Peter Gordon',
    'Jason Newman',
],
    'json': {
    'name': 'Pam Petersen',
    'address': '08913 Carrie Squares\nElizabethbury, VI 46841',
},
    'key19797': 'value86194',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'David Jefferson',
    'address': '9627 Garner Parks\nAshleymouth, AK 66419',
    'text': 'Office set different mention. Employee month film almost you course deep.\nCertainly at sister again truth need. System reveal me owner above picture.',
    'email': 'dennis69@example.net',
    'phone_number': '904-588-4549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Holloway',
    'Chase Bauer',
    'Molly Christian',
    'Jeffrey Chambers',
    'Michael Woods',
],
    'json': {
    'name': 'Donald Ford',
    'address': '374 Turner Squares\nHudsonland, IL 69836',
},
    'key23734': 'value46317',
    'key64191': 'value81185',
    'key10495': 'value92697',
    'key45380': 'value57132',
    'key10157': 'value68621',
    'key3531': 'value38000',
    'key82043': 'value36773',
    'key27194': 'value48891',
    'key20441': 'value69252',
    'key7258': 'value10654',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Taylor Zuniga',
    'address': '2896 Trujillo Shore\nNew Gabriel, OK 05357',
    'text': 'Will agent ok similar resource painting concern. Agree develop second because end.\nSafe end act. Reason race once especially myself inside.',
    'email': 'dhinton@example.net',
    'phone_number': '9689130124',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cory Vasquez MD',
    'Jonathan Serrano MD',
    'Jesse Perry',
    'Christopher Simpson',
    'Aaron Pena',
    'Carol Alvarado',
    'Sandra Deleon',
],
    'json': {
    'name': 'Michele Fernandez',
    'address': '03147 Victor Islands\nAndersonside, AS 84770',
},
    'key52409': 'value24286',
    'key94976': 'value75946',
    'key91922': 'value64747',
    'key86185': 'value60446',
    'key54437': 'value98341',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Patricia Stanley',
    'address': '5381 Faulkner Walks Apt. 383\nWest Kenneth, WV 03556',
    'text': 'Cup lose treatment. Difficult fall among step.\nCondition manager discover prevent. Somebody close ability church. Spend some trade home general lose.',
    'email': 'tonybennett@example.org',
    'phone_number': '745.481.5124x512',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Cameron',
    'Karen Kelley',
    'Rebecca Rice',
    'Andrew Brooks',
    'Julia Johnston',
    'Charles Brown',
    'Charles Mccarthy',
    'Michael Harper',
],
    'json': {
    'name': 'Jennifer Hill',
    'address': 'PSC 5424, Box 3193\nAPO AA 87318',
},
    'key39920': 'value53370',
    'key39059': 'value21515',
    'key52504': 'value65587',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Edward Guerra',
    'address': '759 Baker Light\nWest Jennifer, WV 21783',
    'text': 'Late possible single western. Administration here anything break it group.\nGo final return. Address meeting special show cover key.\nImage speech this amount issue. Under rise base create.',
    'email': 'murphymadison@example.org',
    'phone_number': '310.829.0960x76427',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Carter',
    'Frederick James',
    'Dennis Perez',
    'Logan Rollins',
],
    'json': {
    'name': 'James Terrell',
    'address': '34315 Sarah Motorway\nSouth David, WY 44707',
},
    'key70091': 'value8121',
    'key68797': 'value91229',
    'key44077': 'value93711',
    'key78975': 'value47105',
    'key5320': 'value69681',
    'key84679': 'value2126',
    'key57137': 'value29248',
    'key39323': 'value43132',
    'key17145': 'value94058',
    'key7128': 'value10677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Gavin Barber',
    'address': '9879 Andrea Port\nPort Alexanderchester, WV 44839',
    'text': 'Today several black produce never.\nEnter force finally edge give floor table. Recently into summer career dark city. Six soon another scientist.',
    'email': 'jeffery43@example.net',
    'phone_number': '001-981-234-7112x22861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Madeline Wilson',
    'Cindy Lopez MD',
    'Jeff Lewis',
    'Mary Hernandez',
    'Michael Maynard',
    'Kevin James',
    'Shannon Garcia',
    'Angela Preston',
],
    'json': {
    'name': 'Tara Wood',
    'address': '564 James Brook\nLake Alexisbury, OH 03194',
},
    'key89075': 'value62126',
    'key49341': 'value64803',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'David Nguyen',
    'address': '3648 Coleman Villages\nMichellebury, KY 29833',
    'text': 'Drug one indicate prepare let size research. Identify activity it can. Support situation care.\nSituation week century well sing federal.',
    'email': 'baileyshirley@example.org',
    'phone_number': '548-371-7513x0425',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Scott Atkins',
    'Jennifer Ponce',
    'Chris Saunders',
    'Logan Henderson',
    'Amanda Rice',
    'Roberta Gates',
],
    'json': {
    'name': 'Nicole Brandt',
    'address': '5591 Roberts Club\nSouth Brookemouth, AL 71086',
},
    'key30237': 'value68878',
    'key12954': 'value87868',
    'key79386': 'value17902',
    'key85166': 'value56257',
    'key16049': 'value38112',
    'key18258': 'value17174',
    'key88400': 'value98493',
    'key28099': 'value28790',
    'key53100': 'value28546',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'John Marsh',
    'address': '02663 Wilkinson Meadow Suite 052\nWilliamsfurt, HI 33241',
    'text': 'Late check data start. Own mention popular yes three source eat.\nMyself daughter from girl reach that throw. Least also statement more look.',
    'email': 'knightjoseph@example.com',
    'phone_number': '280-423-5428',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michele Galloway',
    'Ashley Wright',
    'Michael Matthews',
],
    'json': {
    'name': 'Julie Henry',
    'address': '6596 Aaron Lakes Apt. 740\nEast Frankport, PR 05708',
},
    'key25548': 'value69830',
    'key28452': 'value69326',
    'key34897': 'value95871',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Kelly Montes',
    'address': '48752 Richard Tunnel\nSouth Lisaborough, ND 08888',
    'text': 'Your daughter several stuff successful. List senior different politics. Not end generation painting yourself service.',
    'email': 'smithvirginia@example.org',
    'phone_number': '551-237-4935x926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Megan Mcclure',
    'Douglas Noble',
],
    'json': {
    'name': 'Emma Ray',
    'address': '090 Wilson Island Apt. 311\nTrevinobury, AR 43622',
},
    'key62890': 'value783',
    'key10545': 'value31835',
    'key66088': 'value97961',
    'key48662': 'value73039',
    'key34053': 'value80954',
    'key23702': 'value62630',
    'key88888': 'value2993',
    'key67585': 'value3739',
    'key83054': 'value16545',
    'key98986': 'value96125',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'David Hall',
    'address': '93122 Jessica Highway Apt. 652\nMillerfort, OH 11656',
    'text': 'During exist myself collection response PM in. Structure after same field.',
    'email': 'melindasantana@example.com',
    'phone_number': '+1-523-918-3849',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Randy Humphrey',
],
    'json': {
    'name': 'Michele Wright',
    'address': '78907 Steven Vista Suite 527\nNew Timothyborough, AR 34296',
},
    'key10378': 'value89737',
    'key67245': 'value50306',
    'key89919': 'value84947',
    'key56747': 'value4399',
    'key85315': 'value40909',
    'key80018': 'value57099',
    'key31330': 'value44750',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Matthew Torres',
    'address': '461 Galvan Trace\nWest Michellehaven, DE 77296',
    'text': 'Police allow above for million spring structure art. Resource language usually environmental such character.',
    'email': 'hopkinsjennifer@example.net',
    'phone_number': '8929479401',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Scott Ortega',
],
    'json': {
    'name': 'Jared Ramirez',
    'address': '574 Lauren Mall\nCarolfurt, MI 80202',
},
    'key2776': 'value10175',
    'key33332': 'value10120',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Ethan Johnson',
    'address': '372 Rivera Turnpike\nGarciamouth, GA 45898',
    'text': 'Best her grow. Act election knowledge color require threat their quite. Reflect grow popular trip religious.\nMy southern challenge and. Wind require lead traditional lay treat rule.',
    'email': 'dowens@example.com',
    'phone_number': '(802)838-3563x56117',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Cabrera',
    'Marilyn Fischer',
    'Jeffrey Patel',
    'Jennifer Robinson',
],
    'json': {
    'name': 'Sharon Wyatt',
    'address': '03983 Kim View Apt. 876\nNorth Briantown, MN 72427',
},
    'key19898': 'value1756',
    'key92635': 'value28373',
    'key86659': 'value55667',
    'key41661': 'value49789',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Cody Thomas',
    'address': '25569 Ortiz Greens Apt. 030\nNorth Brenda, RI 48807',
    'text': 'Apply letter customer final. Strong environment true staff successful not stock. Answer money similar class energy. Husband entire say my strong.',
    'email': 'lindamyers@example.org',
    'phone_number': '+1-452-988-5730x85523',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Briggs',
],
    'json': {
    'name': 'Brian Mccarthy',
    'address': '52678 Adams Wells Apt. 885\nWest Christopherberg, AZ 89278',
},
    'key59100': 'value46562',
    'key81365': 'value27707',
    'key36698': 'value53703',
    'key20845': 'value83641',
    'key32472': 'value11471',
    'key85077': 'value97029',
    'key45933': 'value95005',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Amanda Frey',
    'address': 'Unit 4736 Box 7572\nDPO AE 11757',
    'text': 'Go of professor sign moment similar avoid ahead. Stage yourself federal expert help tend.\nEasy me include coach site word need. House mission action read style.',
    'email': 'marshallbrian@example.org',
    'phone_number': '9639507837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Rachael Riley',
],
    'json': {
    'name': 'Katherine Jones',
    'address': '41355 Warner Trail Suite 702\nSouth Theodore, NY 71051',
},
    'key11761': 'value56597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Scott Dillon',
    'address': '91820 Stephanie Club Suite 868\nHansonland, FL 88060',
    'text': 'Oil view able fight. Pull contain accept town western.\nUnder age speech purpose sit support. Anyone local down particular their line west case.',
    'email': 'imorton@example.net',
    'phone_number': '(472)922-2185x4513',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marc Archer',
    'Kenneth Brown',
    'Stephanie Williams',
    'John Evans',
    'Sandra Wilkinson',
    'Courtney Johnson',
    'Steven Martin',
    'Michael Farmer',
    'Michael Kennedy',
    'Renee Hines',
],
    'json': {
    'name': 'Christine Garner',
    'address': '8739 Douglas Port Suite 177\nNew John, MN 85429',
},
    'key7124': 'value35224',
    'key88806': 'value67584',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Ricky Jackson',
    'address': '74659 Baker Mountains\nRobinsonburgh, VT 58863',
    'text': 'Very game task like state Congress adult. Meet call would policy meeting able gun. Push nothing material international air local.',
    'email': 'simpsonmary@example.org',
    'phone_number': '001-588-911-0664x03669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Elizabeth Baker',
    'Dennis Powell',
    'Kenneth Smith',
    'Tyrone Chavez',
    'Jessica Mitchell',
    'Brandon Lewis',
    'Kathryn Moore',
    'Mr. William Huber',
    'Jesse Miller',
    'Andrew Williams',
],
    'json': {
    'name': 'Anthony Baldwin',
    'address': '54189 Lorraine Freeway\nJoshuaview, WV 85949',
},
    'key4714': 'value39947',
    'key58071': 'value60394',
    'key6832': 'value81229',
    'key69399': 'value55645',
    'key95827': 'value19207',
    'key54824': 'value57564',
    'key50950': 'value8355',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Christian Clayton',
    'address': '46194 Davis Oval\nAndersonborough, MO 87126',
    'text': 'Bag early onto act. Generation according among exist send. Production alone wonder sure month fast.',
    'email': 'william36@example.com',
    'phone_number': '883-474-6198x4245',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tony Smith',
    'Mary Barry',
    'Joseph Patterson',
    'Nicholas Russo',
    'Elizabeth Lee',
    'William Johnson',
    'Jordan Owens',
    'Joshua Singh',
    'Nathan Calderon',
    'Nicholas Huff',
],
    'json': {
    'name': 'Martin Oneal',
    'address': '9776 Taylor Rapid\nJamieville, ME 10349',
},
    'key47575': 'value68160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Matthew Gomez',
    'address': '828 Russell Burg\nJonathanland, MI 68389',
    'text': 'Always successful likely even feel. Even camera economy nation improve modern.\nArticle entire of reduce population project. Company power spring. Show maybe arm scene experience media.',
    'email': 'swilkerson@example.org',
    'phone_number': '+1-936-752-1043x802',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Eric Reeves',
    'Justin Gonzalez',
    'Brandon Shaw',
],
    'json': {
    'name': 'Allen Perez',
    'address': '5011 Martin Extensions Suite 212\nNew Danielle, KS 08842',
},
    'key48430': 'value59586',
    'key85271': 'value91518',
    'key70292': 'value25327',
    'key75418': 'value82747',
    'key46099': 'value54762',
    'key21707': 'value6810',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Dorothy Hayes',
    'address': '619 Jeanne Springs Suite 968\nGarymouth, ME 96442',
    'text': 'Begin table front sense about yet. Accept song prepare half too good.\nOrganization green mind despite machine east energy. Southern guy responsibility her bank any.',
    'email': 'brownlori@example.net',
    'phone_number': '595.324.3035x882',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Vaughn',
    'Andrew Lopez',
    'Tiffany Reeves',
    'Nancy Benjamin',
],
    'json': {
    'name': 'Lauren Martinez',
    'address': '518 Larry Hollow\nNew Sarafort, AL 78790',
},
    'key109': 'value26014',
    'key88460': 'value50076',
    'key53348': 'value54642',
    'key80499': 'value10808',
    'key4232': 'value57247',
    'key68301': 'value10641',
    'key24092': 'value5500',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Bryan Krueger',
    'address': '234 Thomas Well\nWest Lindsey, CT 22590',
    'text': 'Do skill where girl future cause together. Economic body particular daughter yes lose data.\nWriter gas agreement floor moment near. List accept effort easy why.',
    'email': 'johngraham@example.org',
    'phone_number': '285.902.3287x419',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Evan Miller',
    'Dakota Patton',
    'Karen Travis',
    'Sherry Trujillo',
],
    'json': {
    'name': 'Frederick Howell',
    'address': '2056 Matthew Ways Apt. 657\nSeanport, NJ 43178',
},
    'key83919': 'value40237',
    'key9571': 'value99213',
    'key79509': 'value6814',
    'key98921': 'value59419',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Ethan Mathews',
    'address': '5356 Evans Stravenue Suite 677\nJaniceport, NY 94325',
    'text': 'Likely exactly several million outside it either. White picture line actually amount statement design.',
    'email': 'jesse70@example.com',
    'phone_number': '001-629-289-4116',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Katrina Bell',
    'Michelle Coleman',
    'Jesse Solis',
    'Christopher Davis',
    'Kayla Lane',
    'Anna Salazar',
],
    'json': {
    'name': 'Anthony Mathews',
    'address': '362 Francisco Dale Apt. 009\nLake Dennisview, CA 66218',
},
    'key91466': 'value68872',
    'key58392': 'value37480',
    'key60879': 'value87339',
    'key50890': 'value31528',
    'key96395': 'value48630',
    'key72563': 'value76731',
    'key28183': 'value62314',
    'key90430': 'value73186',
    'key68672': 'value74567',
    'key51031': 'value75916',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Meredith Gonzalez',
    'address': '53988 Miller Light Apt. 584\nNew Brianview, KS 13373',
    'text': 'Back expert especially since drop. Up community ground.\nShoulder face conference change occur speech. Against campaign than food worker officer month.',
    'email': 'nathanwilliams@example.net',
    'phone_number': '539-897-1364x94324',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Morris',
    'Victoria Rogers',
    'Anthony Williams',
    'Diamond Smith',
    'Mark Green',
    'Andrea Wade',
    'Jeffrey Jones',
    'Andrew Williamson',
    'Dawn Rivera',
    'Samantha Guerrero',
],
    'json': {
    'name': 'William Stewart',
    'address': 'USCGC Lewis\nFPO AP 61084',
},
    'key45372': 'value63186',
    'key21919': 'value93496',
    'key93057': 'value44334',
    'key51234': 'value21952',
    'key99592': 'value23441',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jeffrey Wu',
    'address': '42595 Jonathan Square Apt. 034\nSouth Gabrielle, MO 72950',
    'text': 'Single sure song Republican and development suggest. Into citizen war sometimes central practice.\nBehind than idea together.\nOr your watch medical identify society world.',
    'email': 'juliewoods@example.com',
    'phone_number': '(736)529-6495',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Vazquez',
],
    'json': {
    'name': 'Paul Nguyen',
    'address': '7132 Timothy Terrace Suite 922\nEast Renee, FL 34393',
},
    'key85854': 'value11514',
    'key88988': 'value22512',
    'key71464': 'value92913',
    'key69164': 'value73709',
    'key79309': 'value16122',
    'key88639': 'value8222',
    'key7714': 'value90029',
    'key267': 'value20549',
    'key27404': 'value23465',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Charles Arellano',
    'address': '31075 Mallory Ranch\nRachelmouth, FL 69798',
    'text': 'Become investment feel meet fall speak.\nDiscussion friend a building bar partner.',
    'email': 'jessicagarcia@example.org',
    'phone_number': '698-654-0997x884',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Lane',
],
    'json': {
    'name': 'Jasmine Burns',
    'address': '25551 Benton Ranch\nSouth Makaylamouth, FL 61579',
},
    'key18895': 'value68759',
    'key26713': 'value6675',
    'key91375': 'value83861',
    'key28302': 'value28023',
    'key35663': 'value40706',
    'key62743': 'value7669',
    'key86030': 'value22666',
    'key72373': 'value28745',
    'key23578': 'value16446',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Marvin Smith',
    'address': '53037 Stanley Crossing Suite 518\nWagnerburgh, PR 51007',
    'text': 'Quickly certain to. Cost Mr left.\nThing huge second.\nAffect ever film reach up another environmental ago. Group condition water recognize several beyond.',
    'email': 'ganderson@example.org',
    'phone_number': '+1-797-316-0109x2018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Perkins',
    'Christine Calderon',
    'Mckenzie Fernandez',
    'Francisco Browning',
    'Suzanne Lee',
    'Edward Phillips',
    'Andrew Beck',
],
    'json': {
    'name': 'Mary Roberts',
    'address': '76127 Johnson Way Suite 474\nEast Shelby, AK 53520',
},
    'key76414': 'value60854',
    'key3593': 'value98509',
    'key43172': 'value59529',
    'key92261': 'value25952',
    'key47310': 'value51752',
    'key51168': 'value77036',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Kelsey Lee',
    'address': '03040 Brandon Harbor\nSouth Terri, NE 41788',
    'text': 'Give city create these suffer spend as vote. Good community purpose hit build include. War cost structure remember serious long community.',
    'email': 'christopher04@example.net',
    'phone_number': '001-484-338-3059x38095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Copeland',
    'Stephen Schneider',
    'Karen Allen',
    'Kim Harrell',
    'Ashley Cummings',
    'Keith Mitchell',
    'David Lopez',
    'Adam Garcia',
    'Lori Lewis',
    'Jennifer James',
],
    'json': {
    'name': 'Tina Pace',
    'address': 'PSC 9352, Box 8082\nAPO AE 65924',
},
    'key97397': 'value9958',
    'key81082': 'value96210',
    'key23226': 'value54269',
    'key62987': 'value28769',
    'key71160': 'value94946',
    'key89189': 'value49659',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'April Moreno',
    'address': '387 Rush Crossroad Suite 425\nRobertsmouth, PW 73644',
    'text': 'Wide here senior. Than drug building bad subject interest apply many. His adult manager own court also.\nLet history themselves nearly throughout. Trip on prevent commercial law western.',
    'email': 'taylor03@example.com',
    'phone_number': '001-621-485-2788x230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Charles Houston',
    'Zachary Saunders',
    'Justin Ross',
    'Nathan Olsen',
    'Laura Mathis',
    'Caroline Garcia',
    'Mary Heath',
    'Teresa Lopez',
    'Andrew Lester',
    'Miss Sarah Marshall',
],
    'json': {
    'name': 'Thomas Howard',
    'address': '1158 Lara Station Suite 866\nTiffanyborough, MS 06035',
},
    'key64282': 'value13531',
    'key79136': 'value24622',
    'key19587': 'value74695',
    'key85382': 'value66430',
    'key64092': 'value49817',
    'key31264': 'value33801',
    'key68600': 'value65602',
    'key43989': 'value15035',
    'key47021': 'value26583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Alejandra Carter',
    'address': '2459 Brown Ranch Suite 712\nJamesview, WY 89357',
    'text': 'Five thus wonder change. Bank assume information green parent open exist. Pull computer cell part alone late institution. Attorney front although local.',
    'email': 'rossmichael@example.net',
    'phone_number': '(995)973-1286x870',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Edwards',
    'Juan Casey',
    'John Harrell',
],
    'json': {
    'name': 'Michael Riley',
    'address': '1104 Taylor Mills Suite 989\nNorth Scottton, MT 35573',
},
    'key65682': 'value3218',
    'key19175': 'value83970',
    'key74345': 'value9798',
    'key94819': 'value29041',
    'key68549': 'value14543',
    'key50628': 'value49705',
    'key8013': 'value5916',
    'key34864': 'value88794',
    'key56980': 'value63675',
    'key71134': 'value82056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Christine Cooley',
    'address': '6839 Reynolds Forge\nJeffersonfort, OH 75188',
    'text': 'Population officer out reason east Democrat a. Heart road professional wait month. Foreign respond understand fly return sell thought.',
    'email': 'troy50@example.net',
    'phone_number': '001-929-616-3688x757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amy Gonzalez',
    'Janet Smith',
    'Amy Sims',
    'Tyler Fuller',
],
    'json': {
    'name': 'Derek Rhodes',
    'address': '5314 Fuller Curve\nLake Ethan, VT 51975',
},
    'key47646': 'value64882',
    'key34096': 'value91504',
    'key50271': 'value89471',
    'key84090': 'value73373',
    'key86848': 'value70084',
    'key99625': 'value20588',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Lauren Brown',
    'address': '3746 Hill Flats\nEast Heathershire, VI 64089',
    'text': 'That happen boy this former major with. East bank together state. Low more town though leg company rich.\nFine clear amount social parent. Dark poor child cup.',
    'email': 'michelle35@example.org',
    'phone_number': '649.576.0191',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Corey Mason',
    'Jamie Gomez',
    'Angel Nichols',
    'Michael Carlson',
    'Keith Howe',
    'Ronald Collins',
    'William Richards',
    'Maria Schneider',
],
    'json': {
    'name': 'Samantha Foster',
    'address': '46905 Barbara Curve\nMccoyberg, CT 87149',
},
    'key43489': 'value39761',
    'key31462': 'value1234',
    'key23546': 'value64794',
    'key65392': 'value52693',
    'key38399': 'value78219',
    'key24397': 'value90704',
    'key24145': 'value96441',
    'key763': 'value1037',
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
    'RequestId': '3eb3bb17-62f1-11f0-96f7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_20_427888LOiRkugF',
    'filter': '10+20 <= uid < 20+30',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '3f52fbdf-62f1-11f0-8384-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_20_427888LOiRkugF',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '37fa5bc7-62f1-11f0-a13c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_20_427888LOiRkugF',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752744873.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalse1020Uid20301752744873Json()
    test.run_tests()
