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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestGetVector_test_get_vector_complex[True-True-one]_1752749098_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestGetVector_test_get_vector_complex[True-True-one]_1752749098.json"
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



class AllmilvusLogtestgetvectorTestGetVectorComplexTrueTrueOne1752749098Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestGetVector_test_get_vector_complex[True-True-one]_1752749098.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestGetVector_test_get_vector_complex[True-True-one]_1752749098.json"
        self.test_count = 9  # 测试方法数量
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
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
    'data': [
    {
    'id': 17527490930344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Carol Mueller',
    'address': 'USNV Martinez\nFPO AA 35436',
    'text': 'Reveal least crime site. Career amount thought series respond audience remain. Have establish drop provide board measure really.\nNation data behavior arm almost. Fund seek he take explain Mrs.',
    'email': 'perrytaylor@example.net',
    'phone_number': '001-762-406-5848',
    'json': {
    'name': 'Jessica Robinson',
    'address': '8892 Fernandez Road Apt. 202\nNorth Dannyside, MO 05479',
},
    'key64338': 'value48597',
    'key3341': 'value22127',
    'key61481': 'value16114',
    'key43803': 'value6628',
    'key29048': 'value98773',
    'key45726': 'value15351',
    'key95412': 'value115',
    'key29675': 'value19107',
    'key81256': 'value87938',
    'key504': 'value49064',
},
    {
    'id': 17527490930362,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sheila Freeman',
    'address': '4448 Tyrone Loaf Apt. 327\nAndrewbury, VA 96278',
    'text': 'Line somebody all ago hope. Mr only military perform.\nMain meet believe health medical. Protect fast game night building.\nAlready according great of long first wrong.',
    'email': 'larry88@example.net',
    'phone_number': '001-278-930-5459',
    'json': {
    'name': 'Michael Brown',
    'address': '9377 Young Prairie Suite 927\nRussellchester, PW 28346',
},
    'key82716': 'value80959',
    'key2591': 'value91323',
    'key70776': 'value96507',
    'key18215': 'value27777',
    'key24215': 'value37267',
    'key30953': 'value9645',
    'key82979': 'value24604',
    'key64456': 'value81844',
    'key70066': 'value18820',
    'key21999': 'value3037',
},
    {
    'id': 17527490930376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Amber Phelps',
    'address': '2717 Aguilar Cove\nLake Jonathanside, DE 38386',
    'text': 'Current population drug evidence air interesting. She task town vote wall.\nChurch black loss about. Respond culture several positive although. Within sort wonder animal debate herself exactly.',
    'email': 'dphillips@example.net',
    'phone_number': '+1-556-770-4323x043',
    'json': {
    'name': 'Sarah French',
    'address': '557 Harrell Orchard\nMichelleburgh, NJ 16934',
},
    'key1237': 'value61340',
    'key80623': 'value38513',
    'key86704': 'value84450',
    'key63095': 'value51954',
    'key83377': 'value63288',
    'key85685': 'value82376',
    'key36372': 'value9900',
},
    {
    'id': 17527490930390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Vanessa Scott',
    'address': '1800 Kimberly Ford\nPort Michael, ID 71056',
    'text': 'Chair hot only inside manager. Term whose first concern some improve. Place hundred when affect indeed perhaps.\nHot drug enter mouth friend my. Hand take on fall.',
    'email': 'hornjustin@example.com',
    'phone_number': '6212453486',
    'json': {
    'name': 'Lindsey Russell',
    'address': '67353 Crystal Ferry\nCollinshire, CT 97662',
},
    'key12385': 'value48741',
    'key49341': 'value96077',
},
    {
    'id': 17527490930404,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Joshua Smith',
    'address': '64533 Martin Haven Apt. 238\nLake Sandra, SD 53080',
    'text': 'Find part now opportunity maintain.\nReceive rest wait professor major now sing. Various board life. Manager minute receive everything field bad.',
    'email': 'robert23@example.com',
    'phone_number': '312.820.5455x890',
    'json': {
    'name': 'Daniel Mack',
    'address': '37810 Mary Grove\nDaviston, TX 63351',
},
    'key61061': 'value15790',
    'key96934': 'value9872',
    'key38879': 'value15249',
    'key9275': 'value8369',
    'key61583': 'value96246',
    'key40860': 'value38043',
},
    {
    'id': 17527490930416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'William Thomas',
    'address': 'USCGC Singh\nFPO AE 56795',
    'text': 'Move plan spring company Democrat believe security. Central for set guy home. Face on develop draw customer attack.',
    'email': 'rebekah11@example.net',
    'phone_number': '(393)218-6895x85106',
    'json': {
    'name': 'Gregory Dudley',
    'address': '48329 Collins Island Apt. 861\nCarlosmouth, NY 15125',
},
    'key92896': 'value17455',
    'key73501': 'value56556',
    'key51355': 'value25029',
    'key71653': 'value28219',
},
    {
    'id': 17527490930427,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Leslie Duncan',
    'address': '60043 Scott Flats\nHardyport, PA 15339',
    'text': 'College medical usually whole away.\nBox born fill wonder world respond until. Sense account analysis compare partner factor.',
    'email': 'dwalsh@example.net',
    'phone_number': '606-773-7143x37830',
    'json': {
    'name': 'William Johnson',
    'address': '6474 Michael Lock Apt. 346\nSouth Debratown, FM 13999',
},
    'key70750': 'value6676',
    'key62480': 'value76426',
    'key58958': 'value17333',
    'key75398': 'value80079',
    'key96982': 'value71019',
    'key60949': 'value13766',
    'key35257': 'value87565',
},
    {
    'id': 17527490930438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Michael King',
    'address': '97304 Sullivan Gateway\nWest Matthew, WI 83031',
    'text': 'Exist learn other eye late indeed air. Rather almost trade voice radio report.\nLot site want watch learn understand. Manager thousand street none appear clear.',
    'email': 'tyrone78@example.org',
    'phone_number': '329-818-5481',
    'json': {
    'name': 'Debbie Alexander',
    'address': '399 Kenneth Ville\nJasonbury, MO 25790',
},
    'key86752': 'value21588',
    'key24306': 'value98139',
    'key17293': 'value50485',
    'key40295': 'value49654',
},
    {
    'id': 17527490930449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Scott Hamilton',
    'address': '8475 Paul Wall Suite 941\nMaloneton, PA 14509',
    'text': 'Key turn station community example night often already.\nAbout who agreement rich mind rather. Grow need where light collection environment. Here marriage trip reveal so history argue value.',
    'email': 'ryan44@example.net',
    'phone_number': '955-517-9973x708',
    'json': {
    'name': 'Christina Hogan',
    'address': '58469 Kenneth Pines\nKimberlybury, AZ 51919',
},
    'key96168': 'value79898',
    'key356': 'value79597',
    'key41091': 'value72689',
    'key97780': 'value33561',
},
    {
    'id': 17527490930459,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Crystal Hughes',
    'address': '8048 Ferguson Gateway\nLake Davidland, GU 67775',
    'text': 'People political budget operation. Why happen western their family thus foreign. Only on store night police staff.',
    'email': 'robertomarshall@example.org',
    'phone_number': '970-702-1898x1784',
    'json': {
    'name': 'Sonya Stein',
    'address': '89388 Amanda Trace Suite 684\nGarciaville, AL 65212',
},
    'key8877': 'value76069',
    'key61398': 'value36697',
    'key37600': 'value513',
},
    {
    'id': 17527490930471,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Theresa Baker',
    'address': '3242 Stephanie Fork\nSouth Chasestad, CT 77984',
    'text': 'Could energy from marriage right.\nMiddle personal simple control life. Take stand any expect.\nHit start identify return. Weight spring management Mrs. Commercial heavy morning.',
    'email': 'thompsonedward@example.net',
    'phone_number': '866.949.3772',
    'json': {
    'name': 'Christopher Powell',
    'address': '987 Lauren Valleys\nHamiltonfurt, NH 75585',
},
    'key90500': 'value14694',
    'key3423': 'value97148',
    'key74247': 'value91217',
    'key88608': 'value61937',
},
    {
    'id': 17527490930482,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Ronald Woodward',
    'address': '968 Perry Valley Apt. 579\nNew Brandiberg, MN 27586',
    'text': 'Many bad west smile player fire change no. Kitchen morning white western trial.\nTen science guy throughout with. Energy career quality give other. Player culture part trial vote.',
    'email': 'mbryant@example.org',
    'phone_number': '(362)797-9093x1852',
    'json': {
    'name': 'Jonathon Smith',
    'address': '40309 Sarah Locks Apt. 001\nShannonfort, OH 86395',
},
    'key30916': 'value14993',
    'key33917': 'value95751',
    'key42198': 'value7171',
    'key24985': 'value90248',
    'key87805': 'value50442',
    'key59403': 'value24387',
},
    {
    'id': 17527490930494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Kathy Hall',
    'address': '353 Douglas Hills Apt. 125\nSouth Jennifer, VA 04942',
    'text': 'However coach field light drop. Catch others yourself class father.',
    'email': 'ztodd@example.org',
    'phone_number': '+1-485-868-2573x5803',
    'json': {
    'name': 'Margaret Combs',
    'address': '01444 Stacey Hill\nGoodmanton, MS 52502',
},
    'key56920': 'value84200',
    'key21344': 'value1613',
    'key74173': 'value53766',
    'key53614': 'value28949',
    'key55347': 'value45884',
    'key53596': 'value78024',
    'key80639': 'value16860',
    'key28693': 'value48099',
    'key18511': 'value96569',
},
    {
    'id': 17527490930505,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Heather White',
    'address': '4479 Taylor Parkway Apt. 889\nEricfort, AS 17247',
    'text': 'Phone start none difference suffer while. Article interesting media knowledge.\nNewspaper large nor skin growth provide center experience. Land article American even around other.',
    'email': 'devon85@example.net',
    'phone_number': '761-854-8903',
    'json': {
    'name': 'Amber Becker',
    'address': '278 Haley Locks\nPatriciahaven, PW 40805',
},
    'key84977': 'value15895',
    'key72679': 'value7558',
    'key56572': 'value94757',
    'key27293': 'value12427',
    'key71792': 'value42520',
    'key52582': 'value58734',
    'key52329': 'value90660',
    'key77509': 'value21514',
    'key72968': 'value56557',
},
    {
    'id': 17527490930516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Annette Smith',
    'address': '4712 Glenn Camp Apt. 609\nBethanyborough, PW 92252',
    'text': 'Front nearly present shoulder free. Window forget way every trip.',
    'email': 'erica55@example.com',
    'phone_number': '(627)212-0961',
    'json': {
    'name': 'Melanie Richard',
    'address': '6085 George Village\nEast John, GU 37512',
},
    'key87568': 'value99291',
    'key70613': 'value72473',
    'key7882': 'value49659',
    'key18273': 'value2810',
    'key6886': 'value3408',
},
    {
    'id': 17527490930525,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jose Brown',
    'address': '10504 Gentry Falls\nJacksonborough, WV 90159',
    'text': 'Head voice marriage reason range try. Blood plan administration building power she history.\nEnter man leave customer. None small reach system hit.',
    'email': 'andrewcollins@example.net',
    'phone_number': '526.651.0343',
    'json': {
    'name': 'Sophia Snyder',
    'address': '2407 Carrie Alley Suite 450\nHallfort, NC 79019',
},
    'key34258': 'value23897',
    'key6420': 'value99678',
    'key29298': 'value40005',
    'key56475': 'value60128',
    'key63261': 'value11046',
    'key93972': 'value81714',
    'key23596': 'value50346',
},
    {
    'id': 17527490930537,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Dennis Fernandez',
    'address': '255 Stephanie Turnpike\nPort Kimberly, CT 68150',
    'text': 'Agreement partner among. Lead beautiful treatment late various white final.',
    'email': 'smithsarah@example.com',
    'phone_number': '699-667-9910x410',
    'json': {
    'name': 'Mary Mcgee',
    'address': '62216 Amy Street\nDeniseville, AR 58408',
},
    'key74770': 'value32769',
    'key81835': 'value10648',
    'key72041': 'value97654',
    'key43132': 'value14512',
    'key59500': 'value43399',
    'key3967': 'value75702',
    'key80027': 'value76700',
    'key18112': 'value75032',
    'key76365': 'value18780',
},
    {
    'id': 17527490930547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Linda Schmidt',
    'address': '33649 Mejia Coves Apt. 431\nVelezchester, WV 91416',
    'text': 'Cost ready small moment. Involve might by alone onto cold beautiful. Great reach them base.\nCare hair particular simply back current us. Consumer fire room thus.',
    'email': 'rchung@example.com',
    'phone_number': '405.930.3230',
    'json': {
    'name': 'Billy Barrett',
    'address': '86580 Gardner Field Suite 558\nWest Shawnside, MO 90126',
},
    'key67385': 'value7651',
    'key1702': 'value58551',
    'key42191': 'value35893',
    'key63658': 'value36452',
    'key80645': 'value81833',
    'key87215': 'value33669',
    'key66637': 'value31955',
    'key61947': 'value91628',
    'key88283': 'value57397',
    'key16827': 'value12309',
},
    {
    'id': 17527490930559,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Ryan Thomas',
    'address': '11764 Heath Lane Apt. 507\nRobertmouth, VT 54976',
    'text': 'Show drive wonder. Carry drive none western own person need ten. Particularly choose fire special million sit. Budget happy address laugh each size responsibility.',
    'email': 'mark21@example.net',
    'phone_number': '972.345.6561x60364',
    'json': {
    'name': 'John Roman',
    'address': '985 Carl Light Suite 493\nSouth Heatherside, TX 17555',
},
    'key39296': 'value18950',
    'key7484': 'value501',
    'key21696': 'value57413',
    'key32454': 'value36741',
    'key99379': 'value93854',
    'key37553': 'value23022',
    'key85433': 'value19862',
    'key19522': 'value44850',
    'key94832': 'value73790',
},
    {
    'id': 17527490930570,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Patrick Edwards',
    'address': '18455 Anderson Villages Apt. 563\nMelissaport, SC 15899',
    'text': 'Bed they sister though one ball. Open finally local not coach least. Support good discover value run sign around structure. Color most very our majority action.',
    'email': 'justin79@example.com',
    'phone_number': '+1-859-229-4264',
    'json': {
    'name': 'Elizabeth Rodriguez',
    'address': '3610 Turner Ville Suite 463\nHeatherfort, MA 48655',
},
    'key51103': 'value7028',
    'key1578': 'value55835',
    'key21868': 'value27933',
    'key80750': 'value81463',
    'key31830': 'value15003',
    'key99549': 'value17191',
},
    {
    'id': 17527490930581,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Mr. Edwin Ortiz',
    'address': '710 Alvarez Forks\nNorth Annland, MI 71795',
    'text': 'Particular start computer able picture speak with list. Fly break something stop.',
    'email': 'onealjames@example.org',
    'phone_number': '674-700-4848',
    'json': {
    'name': 'Amber Wilson',
    'address': '06999 Susan Shoal\nLake Meganview, NJ 25643',
},
    'key64318': 'value63146',
},
    {
    'id': 17527490930592,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'David Vazquez',
    'address': 'Unit 1752 Box 3050\nDPO AP 24780',
    'text': 'Century evening human plan another sport during stand. Close share present election suffer. Mind try life.',
    'email': 'nicholas00@example.net',
    'phone_number': '694.752.7690x422',
    'json': {
    'name': 'Jessica Powell MD',
    'address': '97561 Smith Summit Suite 437\nFrederickview, IA 84754',
},
    'key85097': 'value20071',
    'key38771': 'value31844',
    'key14346': 'value64379',
    'key90319': 'value52304',
},
    {
    'id': 17527490930601,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Erin Smith',
    'address': 'USS Rollins\nFPO AP 77377',
    'text': 'Term amount cold down able. Box national music process. Marriage add their laugh traditional.\nDifficult fight avoid collection risk nation. Discuss charge huge before. Town bar by fast or personal.',
    'email': 'janderson@example.net',
    'phone_number': '(951)385-0093',
    'json': {
    'name': 'Jeff Anderson',
    'address': '80450 Green Bypass Apt. 126\nNew William, NE 19495',
},
    'key90830': 'value44051',
    'key36395': 'value69775',
    'key70533': 'value94440',
    'key8596': 'value92908',
    'key74943': 'value74524',
    'key69659': 'value36917',
    'key97082': 'value79911',
    'key67043': 'value49370',
    'key69396': 'value3824',
},
    {
    'id': 17527490930611,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jessica Murray',
    'address': '3662 Lawson Square Apt. 262\nSouth Douglas, MH 60136',
    'text': 'Ok today month scientist. See century interview tonight few.\nHour company decide race itself loss walk painting.\nRelate paper something standard pick. Color cut evening deal your value.',
    'email': 'wshelton@example.net',
    'phone_number': '001-277-785-6540x24921',
    'json': {
    'name': 'Brett Gay',
    'address': '88375 Stephenson Pine Apt. 934\nHebertborough, VA 79780',
},
    'key51422': 'value83177',
    'key10460': 'value16505',
    'key41922': 'value78860',
    'key25514': 'value82758',
},
    {
    'id': 17527490930623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Brandon Navarro',
    'address': '7579 Gregory Unions Suite 703\nHannahfort, OK 88778',
    'text': 'Too table magazine exist walk game increase. Center before protect step. Show yard activity everyone.\nPlant turn piece remain health image next control.\nCourse sport value oil too turn surface.',
    'email': 'emedina@example.com',
    'phone_number': '(593)936-4284',
    'json': {
    'name': 'Ashley Blevins',
    'address': '216 Wilson Row Apt. 777\nEast Sarah, TN 79321',
},
    'key24': 'value22817',
    'key17570': 'value93889',
    'key33261': 'value5597',
    'key57149': 'value49317',
    'key42702': 'value13630',
    'key5034': 'value17014',
    'key78222': 'value29899',
},
    {
    'id': 17527490930634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Christopher Harrison',
    'address': '22256 Brenda Locks\nJenniferbury, SD 43995',
    'text': 'Adult foreign become tend better certain baby. Break player its peace lawyer.\nOccur west look bank skill according. Song far tonight run. Trouble second important often more onto.',
    'email': 'zcoleman@example.net',
    'phone_number': '(413)448-8101',
    'json': {
    'name': 'Jennifer Stone',
    'address': '458 Randy Forge\nChristopherberg, NH 75664',
},
    'key42842': 'value35683',
    'key78321': 'value24583',
    'key56548': 'value88416',
    'key97827': 'value9456',
    'key16561': 'value8975',
},
    {
    'id': 17527490930645,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Stephen Vazquez',
    'address': '06765 Wagner Circles\nChandlerview, AS 60238',
    'text': 'Hotel hospital likely laugh if. Into make treatment. Firm whose at model PM.',
    'email': 'shariward@example.net',
    'phone_number': '001-529-745-4371x74415',
    'json': {
    'name': 'Lisa Erickson MD',
    'address': 'PSC 9806, Box 6487\nAPO AP 03503',
},
    'key24589': 'value39586',
    'key99307': 'value43616',
    'key22220': 'value24266',
    'key51843': 'value87634',
    'key28645': 'value24770',
    'key24484': 'value40187',
    'key28870': 'value20600',
    'key66790': 'value3135',
},
    {
    'id': 17527490930655,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Samantha Clark',
    'address': '680 Julia Prairie Suite 769\nTaylorstad, VI 38660',
    'text': 'Pick quality others left. Serve establish scientist song. Experience present skill sister.\nEvery low it close authority. Successful white real mouth. Goal step by free.',
    'email': 'vanessa03@example.com',
    'phone_number': '+1-638-566-2436x84659',
    'json': {
    'name': 'April Love',
    'address': '96832 Thompson Camp\nBrownstad, AR 78142',
},
    'key49322': 'value38291',
    'key32943': 'value98785',
    'key46377': 'value48288',
    'key44863': 'value78743',
    'key60038': 'value37633',
    'key66936': 'value86086',
    'key48682': 'value51755',
},
    {
    'id': 17527490930666,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Ashley Simon',
    'address': '17035 Miller Rest\nDoyleport, AL 99614',
    'text': 'Total hope offer actually. Fill if pretty travel shake. Democratic fill sometimes some article.',
    'email': 'martinezpatrick@example.org',
    'phone_number': '854-934-2698',
    'json': {
    'name': 'Eduardo Thomas',
    'address': '1517 Christopher Mission\nGillespiemouth, PA 58577',
},
    'key4944': 'value32381',
    'key92695': 'value94696',
},
    {
    'id': 17527490930678,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Stephanie Bullock',
    'address': '4649 Watkins Radial Apt. 101\nSouth Jeffrey, WA 39152',
    'text': 'American defense claim part statement fact mother. Us question whether available commercial personal. No movie former.',
    'email': 'jordan54@example.org',
    'phone_number': '3637499506',
    'json': {
    'name': 'John Myers',
    'address': '582 Leah Lodge Apt. 439\nSouth Nancyfurt, PA 89589',
},
    'key21296': 'value45689',
    'key94901': 'value33305',
    'key91021': 'value85230',
    'key43726': 'value78854',
    'key3442': 'value9910',
    'key4969': 'value28320',
    'key30830': 'value94910',
    'key93819': 'value77598',
},
    {
    'id': 17527490930688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Sabrina Owens',
    'address': '619 Michael Glens Apt. 785\nNew Shawn, KY 66946',
    'text': 'Billion everything question call level enter. Unit analysis ever even teacher.\nFriend yet beautiful. Play population fire course skill nor reach.',
    'email': 'sbrown@example.net',
    'phone_number': '001-527-711-7105x4795',
    'json': {
    'name': 'Paula Washington',
    'address': '253 Warner Inlet\nNorth Robertside, KS 81848',
},
    'key19846': 'value94388',
    'key96520': 'value92257',
    'key51309': 'value24248',
    'key79714': 'value12630',
    'key35659': 'value10904',
    'key95640': 'value17746',
    'key86896': 'value93522',
    'key41064': 'value74552',
    'key5971': 'value6932',
    'key81620': 'value97325',
},
    {
    'id': 17527490930699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'David Brooks',
    'address': '93270 Justin Lights Apt. 221\nEast Justinville, IA 56760',
    'text': 'Them forget lawyer whatever technology plan model play. Various magazine year end address listen tell common.\nList bed improve whatever. Do to art task simple.',
    'email': 'christinemontgomery@example.net',
    'phone_number': '001-757-308-5513x6133',
    'json': {
    'name': 'Matthew Fleming',
    'address': '698 Washington Junctions\nAlexanderland, AR 95896',
},
    'key68957': 'value91626',
    'key96943': 'value13673',
},
    {
    'id': 17527490930711,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Hannah Bailey MD',
    'address': '25666 Morales Prairie Apt. 977\nNew Joseph, NE 45316',
    'text': 'Crime provide should him pull against beautiful seek. Tonight seven return thing. Property itself far bank oil itself someone do.\nSeat meeting behavior late sometimes. Drop standard laugh.',
    'email': 'michaelwright@example.net',
    'phone_number': '636.710.8747x4487',
    'json': {
    'name': 'Jason Brown',
    'address': '7406 Joseph Mews\nEast Stephanieland, AS 44729',
},
    'key62452': 'value87462',
    'key56618': 'value78111',
    'key76512': 'value40540',
    'key61457': 'value94243',
    'key35668': 'value10984',
    'key16301': 'value77246',
    'key52025': 'value9099',
    'key80119': 'value26987',
    'key99166': 'value56206',
},
    {
    'id': 17527490930723,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Zachary Miles',
    'address': '46215 Kim Fork Suite 300\nSouth Katherine, PA 54549',
    'text': 'Region spend speak protect. Body factor green health perhaps threat run. Writer court social approach then tell.\nLet ask first night explain represent. Generation your sport notice part sound end TV.',
    'email': 'mhowe@example.com',
    'phone_number': '(645)812-0292x87378',
    'json': {
    'name': 'Scott Ware',
    'address': '662 Baker Tunnel\nWest Donna, IL 22283',
},
    'key39307': 'value77231',
},
    {
    'id': 17527490930734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Steven Smith',
    'address': '092 Beck Dale Apt. 378\nEast Jodiburgh, WY 66419',
    'text': 'Nice couple boy woman teacher smile tell. Discover either certainly. Personal book miss increase trial.\nIf per charge have increase.\nFor indicate individual explain. Very author less.',
    'email': 'lori66@example.com',
    'phone_number': '878.693.3526x795',
    'json': {
    'name': 'Jim Briggs',
    'address': '41486 Mark Spring Suite 271\nThomasland, SC 06786',
},
    'key64149': 'value83658',
    'key89599': 'value48681',
    'key84943': 'value83649',
    'key5669': 'value28351',
    'key34701': 'value80934',
},
    {
    'id': 17527490930744,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Noah Diaz',
    'address': '919 Heath Expressway\nWest Brandon, MA 25385',
    'text': 'Hold instead difference popular seven. Fast success cup light like.\nSome soldier southern together last us clearly. Morning culture father language attention animal wear.',
    'email': 'hernandezdylan@example.org',
    'phone_number': '(466)697-3161x87346',
    'json': {
    'name': 'Alejandro Kelly',
    'address': '95132 Robert Camp\nClarkstad, SD 21824',
},
    'key54582': 'value7719',
},
    {
    'id': 17527490930756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Meagan Mendoza',
    'address': '604 Horton Field Apt. 410\nNorth Andrew, AZ 07473',
    'text': 'Better resource throughout. Section manage trouble soon nor wait. Need yeah expert raise two. Tonight stand culture condition watch body on.',
    'email': 'wilsonjeremy@example.net',
    'phone_number': '861-963-3932x43798',
    'json': {
    'name': 'Marcus Oliver',
    'address': '4624 Amy Plains Apt. 288\nNew Michaelville, OH 31642',
},
    'key58075': 'value9175',
    'key82689': 'value56599',
    'key63114': 'value29390',
},
    {
    'id': 17527490930768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Cindy Walker',
    'address': '8864 Short Grove\nNorth Jessica, PA 12047',
    'text': 'Voice each address hot. Run business adult cut main.\nIndividual goal director contain police.\nWar bad standard stuff. Walk wonder side would raise man statement. Check standard set large hit.',
    'email': 'rkramer@example.org',
    'phone_number': '001-916-522-2228x430',
    'json': {
    'name': 'Rebecca Long',
    'address': '2940 Ford Estates\nNorth Joshua, TN 21915',
},
    'key30358': 'value97309',
    'key5259': 'value95787',
    'key81374': 'value14398',
    'key76535': 'value82294',
    'key34698': 'value11326',
    'key95241': 'value97154',
    'key7339': 'value7642',
    'key37052': 'value3539',
    'key61217': 'value42982',
    'key48841': 'value68910',
},
    {
    'id': 17527490930779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Mr. Keith Rhodes',
    'address': '47970 Ellison Views Suite 008\nNorth Kennethfurt, DC 52966',
    'text': 'Hit example let yet prepare.\nOff physical billion within soon. Say control nice.\nMaintain full size community wear. Bed answer two picture someone court my southern.',
    'email': 'sreed@example.org',
    'phone_number': '613-836-7242',
    'json': {
    'name': 'Evan Moore',
    'address': '30156 Ricky Rapids\nTimothyton, GA 32998',
},
    'key48643': 'value81365',
    'key43511': 'value16233',
},
    {
    'id': 17527490930789,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Michael Ponce',
    'address': '353 Bryan Meadow\nLake Mckenziefort, OK 25218',
    'text': 'Crime view their particularly whatever. Statement hotel human should well. Five onto determine draw none community most painting.',
    'email': 'rangelalexander@example.net',
    'phone_number': '8198040126',
    'json': {
    'name': 'Christopher Burgess',
    'address': '061 Swanson Roads\nPort Tina, AS 35376',
},
    'key82922': 'value22',
    'key80171': 'value85787',
    'key40043': 'value33982',
    'key66485': 'value97964',
    'key89606': 'value3040',
    'key62924': 'value76436',
    'key25310': 'value66354',
    'key42341': 'value53245',
    'key89883': 'value98653',
},
    {
    'id': 17527490930801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Rachel Merritt',
    'address': 'PSC 9115, Box 5764\nAPO AA 03749',
    'text': 'Where floor under thousand direction. Forward rock agent onto hope others.\nOf community although entire. Road tax activity why. Effect easy area fill mention place lawyer during.',
    'email': 'alexander50@example.org',
    'phone_number': '4428034024',
    'json': {
    'name': 'Brenda Miles',
    'address': '56568 Amber Lock\nNew Amyfurt, OK 16474',
},
    'key85494': 'value56037',
    'key33497': 'value45085',
    'key85790': 'value33488',
    'key89485': 'value60160',
    'key25798': 'value68159',
    'key73098': 'value58519',
    'key93011': 'value29239',
    'key22146': 'value10906',
    'key99953': 'value47748',
    'key41577': 'value59569',
},
    {
    'id': 17527490930810,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Heather Stone',
    'address': '74023 Thomas Forks\nRussellberg, MA 89467',
    'text': 'Carry actually agent whether science arrive. Return evening total argue. Himself culture security event.\nHalf human kitchen. Scientist blood fight me current.',
    'email': 'jenningsedwin@example.net',
    'phone_number': '8283432327',
    'json': {
    'name': 'Megan Vasquez',
    'address': '179 Murray Extensions Suite 068\nAndrewbury, OH 18885',
},
    'key58747': 'value64366',
    'key14461': 'value1222',
    'key18868': 'value69829',
    'key13012': 'value61128',
    'key21085': 'value16594',
    'key46985': 'value92694',
    'key65438': 'value89339',
    'key82764': 'value17559',
    'key33074': 'value70388',
},
    {
    'id': 17527490930822,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Christine Baker',
    'address': '1017 Michelle Turnpike\nPort Rebeccaborough, WI 49179',
    'text': 'Light natural win Mr central foreign. Family tonight account conference Mrs card.',
    'email': 'hilljennifer@example.com',
    'phone_number': '+1-520-762-2029',
    'json': {
    'name': 'Suzanne Miller',
    'address': '870 David Squares\nWilliamview, NJ 81799',
},
    'key94615': 'value51321',
    'key33': 'value78309',
    'key18684': 'value38517',
    'key59666': 'value32236',
},
    {
    'id': 17527490930832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'David Matthews',
    'address': '7842 Scott Glens Apt. 882\nNorth Nicholasborough, MT 55582',
    'text': 'Join start instead both play many. What tree woman decision speak lay. Production interest every onto much section ask.\nNothing above themselves. Campaign group artist make.',
    'email': 'stephen35@example.org',
    'phone_number': '382-836-1769x449',
    'json': {
    'name': 'Kevin Wilson',
    'address': '2899 Holly Fords Apt. 396\nEast Dianaton, IN 06954',
},
    'key90878': 'value22094',
    'key30164': 'value42858',
    'key69779': 'value47960',
    'key23109': 'value37451',
    'key84635': 'value67899',
    'key83789': 'value57408',
    'key87931': 'value89005',
},
    {
    'id': 17527490930844,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Christy Knight',
    'address': '70947 Casey Manors Apt. 404\nPort Johnbury, TN 76964',
    'text': 'Research peace page.\nPoint ground series help next over. Couple available agent including I.',
    'email': 'awoodard@example.net',
    'phone_number': '265-354-5995',
    'json': {
    'name': 'Joshua Gilbert',
    'address': '8483 Pearson Expressway Apt. 748\nLewisfort, FM 71155',
},
    'key56115': 'value90052',
    'key79378': 'value66063',
    'key73902': 'value17528',
},
    {
    'id': 17527490930856,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Sara Ray',
    'address': '1558 Herbert Divide Apt. 720\nWest Erikmouth, DE 67418',
    'text': 'Challenge nature grow spend wife. Protect guy above lay lose soon language. New understand beautiful price could.\nBuild seat message sea leg professor. Half return participant tough high.',
    'email': 'fsmith@example.org',
    'phone_number': '+1-667-558-1934x9765',
    'json': {
    'name': 'Stephanie Hanna',
    'address': 'Unit 7060 Box 8117\nDPO AE 02750',
},
    'key2988': 'value30937',
    'key25342': 'value7478',
    'key89019': 'value39237',
    'key93537': 'value62844',
    'key3596': 'value49611',
},
    {
    'id': 17527490930865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Jennifer Taylor MD',
    'address': '283 Browning Spurs\nMaystown, IL 66599',
    'text': 'Do page at decide. Only want across pressure perform. Interest standard name.\nAdd term officer fly hundred admit appear imagine. Happen especially born.',
    'email': 'zmoore@example.com',
    'phone_number': '958.946.8409',
    'json': {
    'name': 'Jonathan Gill',
    'address': '53759 Christina Ridges Apt. 416\nSouth Rebeccaport, KS 93833',
},
    'key32384': 'value92157',
    'key9805': 'value89368',
    'key7221': 'value7856',
},
    {
    'id': 17527490930876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Michael Smith',
    'address': '673 Jasmine Islands Apt. 635\nRhondaberg, TX 43083',
    'text': 'Fine list left whose safe few. Eat low success.\nEverything play enter. Go traditional wide business agent. Trip military finish how.',
    'email': 'trevinorobert@example.com',
    'phone_number': '703.538.6453x170',
    'json': {
    'name': 'Marilyn Brown',
    'address': '726 Huang Flats Suite 537\nLaurentown, AK 47536',
},
    'key86604': 'value69641',
},
    {
    'id': 17527490930887,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Darlene Acosta',
    'address': 'USNV Tran\nFPO AA 19162',
    'text': 'Very beyond tonight accept. Travel feeling fly argue as.\nWide thank close standard hair network cell. Father music third.',
    'email': 'patriciadennis@example.net',
    'phone_number': '609.676.1361x9319',
    'json': {
    'name': 'Angela Scott',
    'address': '8065 Gonzalez Mountains Suite 522\nChristophertown, MA 32094',
},
    'key53226': 'value5743',
    'key63956': 'value20843',
    'key12682': 'value53300',
},
    {
    'id': 17527490930897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Charles Foster',
    'address': '759 Nolan Village\nNorth Samuel, MA 89932',
    'text': 'Deal fly difficult start end civil think. Law meeting future property.\nPosition these back minute good management go. Source deep before side.',
    'email': 'pedrolowe@example.org',
    'phone_number': '001-512-560-6331x57393',
    'json': {
    'name': 'Kelly Jones',
    'address': 'Unit 7713 Box 9562\nDPO AP 83789',
},
    'key28320': 'value34478',
    'key91125': 'value83541',
    'key50600': 'value72894',
    'key61513': 'value4323',
    'key26223': 'value35097',
    'key94705': 'value47208',
    'key82830': 'value47293',
    'key72128': 'value42447',
    'key23410': 'value5156',
},
    {
    'id': 17527490930907,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Amy Coffey',
    'address': '53176 Robinson Camp\nPort Crystal, TN 10294',
    'text': 'Scene place population guess score structure less boy. Once majority best bar central clear woman.\nAnyone protect nothing minute. Poor thus sister resource. Base without before send indeed resource.',
    'email': 'cbruce@example.com',
    'phone_number': '+1-820-932-2214x660',
    'json': {
    'name': 'Donald Frazier',
    'address': '91932 Gonzales Gardens Suite 065\nWilliamborough, MA 48291',
},
    'key36870': 'value57767',
    'key38053': 'value21435',
    'key27836': 'value2277',
    'key13414': 'value14150',
    'key79763': 'value78148',
    'key82624': 'value54259',
    'key44106': 'value7972',
    'key68404': 'value89820',
},
    {
    'id': 17527490930918,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kimberly Williams',
    'address': '34872 Tammy Divide Suite 097\nHeathershire, DC 38275',
    'text': 'Time message Democrat.\nOpen game high reflect green study way. Report special pay ask. Difficult might including majority responsibility dog.',
    'email': 'angelsanders@example.net',
    'phone_number': '+1-498-418-0316x416',
    'json': {
    'name': 'William White',
    'address': 'Unit 8422 Box 6397\nDPO AA 21562',
},
    'key92772': 'value60382',
    'key82706': 'value59736',
    'key59506': 'value73176',
    'key41535': 'value29915',
    'key60987': 'value43120',
    'key57548': 'value31040',
    'key77114': 'value6371',
    'key11507': 'value69550',
    'key20590': 'value42583',
},
    {
    'id': 17527490930927,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Rachel Bruce',
    'address': '96082 Linda Flat Apt. 382\nAnitafurt, GA 98260',
    'text': 'Red forget all pull good necessary. Research short system want leg that.\nCertainly wife administration remain road research inside. Rich arrive light which stand.',
    'email': 'zacharyflores@example.com',
    'phone_number': '(987)598-6664x456',
    'json': {
    'name': 'Randy Powell',
    'address': '552 Garcia Falls\nSarahland, IA 30526',
},
    'key38477': 'value21081',
    'key41135': 'value32458',
    'key30670': 'value54890',
},
    {
    'id': 17527490930939,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Richard Banks',
    'address': '33606 Patel Wells\nKevinbury, SD 18880',
    'text': 'During go staff. Remember collection parent especially vote. Industry prepare economy author risk economic right voice.\nStreet sometimes full spend staff total owner.',
    'email': 'ricky51@example.net',
    'phone_number': '907.874.0820x8464',
    'json': {
    'name': 'Kenneth Hill',
    'address': '50854 Lauren Burgs\nLake Tamara, MS 88452',
},
    'key24308': 'value38436',
    'key31887': 'value47640',
},
    {
    'id': 17527490930949,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Michael Adams',
    'address': '08685 Jennifer Junctions Apt. 652\nKevinshire, ID 26434',
    'text': 'Ten campaign including step bit. Hope him whose account another compare television.\nHouse program investment. Indicate recognize determine former.',
    'email': 'bruce55@example.net',
    'phone_number': '(266)789-9885',
    'json': {
    'name': 'Melissa Johnson',
    'address': '78990 Gabriella Viaduct\nLewishaven, NC 03710',
},
    'key58353': 'value99953',
    'key50349': 'value41306',
    'key7206': 'value59810',
    'key63137': 'value28268',
    'key36141': 'value84426',
    'key14765': 'value24447',
    'key23086': 'value70349',
},
    {
    'id': 17527490930959,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Lisa Trujillo',
    'address': '6075 Crystal Isle\nKimberlyville, IN 08662',
    'text': 'Laugh really system either computer someone. Small place produce cup.',
    'email': 'daviselizabeth@example.com',
    'phone_number': '428.911.2786',
    'json': {
    'name': 'Robert Gray',
    'address': '0807 Jasmine Walk\nWatkinsside, GA 61480',
},
    'key89168': 'value17121',
    'key97496': 'value30785',
    'key82165': 'value13507',
    'key3845': 'value92227',
    'key56497': 'value88215',
    'key76586': 'value49265',
    'key19657': 'value31104',
    'key13514': 'value26264',
    'key28176': 'value49585',
},
    {
    'id': 17527490930971,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Erika Bailey',
    'address': '40723 Brian Center Suite 581\nBenjamintown, NY 43183',
    'text': 'Movie discussion cup require. Store involve away professional price health ball dog. Much like so well charge. Century six stuff crime.',
    'email': 'dickersonnancy@example.org',
    'phone_number': '001-894-727-8295x44829',
    'json': {
    'name': 'Christopher Bell',
    'address': '94625 Jones Streets Suite 957\nOrtegafurt, KS 79793',
},
    'key45203': 'value79401',
    'key38974': 'value74829',
    'key42141': 'value82307',
    'key62898': 'value78036',
    'key95758': 'value52325',
    'key85057': 'value43202',
    'key55624': 'value28811',
    'key66015': 'value71777',
    'key43261': 'value42867',
    'key78680': 'value77815',
},
    {
    'id': 17527490930983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Anthony Smith',
    'address': '903 Tracey Village\nWest Jill, WA 07648',
    'text': 'School attorney ability hair positive religious.\nSuch hard customer grow radio he. Sing national occur personal little sell human. Health audience prove operation site operation.',
    'email': 'sampsonbryan@example.org',
    'phone_number': '566-895-7598x9572',
    'json': {
    'name': 'John Hart',
    'address': '9117 Johnson Parks Suite 591\nPatrickstad, MO 26650',
},
    'key82799': 'value18210',
    'key298': 'value88253',
    'key12229': 'value74018',
    'key49832': 'value92662',
    'key18771': 'value40840',
    'key93624': 'value8703',
    'key47437': 'value40437',
    'key59561': 'value79747',
    'key4238': 'value60084',
    'key24762': 'value40864',
},
    {
    'id': 17527490930994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Charles Knight',
    'address': '810 Arnold Tunnel\nGonzalezland, OH 37801',
    'text': 'That light thousand some sound return usually. Wish picture explain morning rather. Consumer wife involve themselves around.',
    'email': 'jessicaallison@example.com',
    'phone_number': '963-929-7990',
    'json': {
    'name': 'Ashley Morales',
    'address': '0264 Ortega Stream\nMeganview, MD 73690',
},
    'key90962': 'value63661',
    'key11635': 'value16502',
    'key71299': 'value9446',
    'key50348': 'value10579',
    'key84711': 'value36329',
    'key86025': 'value47688',
},
    {
    'id': 17527490931006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Nicholas Martin',
    'address': '189 Amy Stream Suite 275\nLake Kellyside, WY 59751',
    'text': 'Relate participant apply bring. Medical we send major.\nAgain decision total success. Way social some on study memory both.',
    'email': 'jenkinsalex@example.com',
    'phone_number': '(243)765-3841x23567',
    'json': {
    'name': 'Mrs. Deborah Brown',
    'address': '98027 Gutierrez Radial Suite 952\nJustinburgh, FL 85062',
},
    'key98563': 'value49263',
    'key32060': 'value55197',
    'key36274': 'value85488',
    'key85477': 'value47460',
    'key47211': 'value16213',
    'key81959': 'value2253',
},
    {
    'id': 17527490931019,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jacob Harmon',
    'address': '0250 Sabrina Centers\nKylestad, MT 99307',
    'text': 'Could example likely agent management. Put more radio outside early him turn.\nThis health big become. Call environmental quickly yes community for chair work. Through nor number data.',
    'email': 'schroederelizabeth@example.com',
    'phone_number': '+1-314-474-0632',
    'json': {
    'name': 'Michelle Lopez',
    'address': '072 John Springs Apt. 603\nLake Tammy, PR 78069',
},
    'key99801': 'value65184',
    'key54787': 'value13589',
    'key34522': 'value70378',
    'key12245': 'value34758',
    'key23968': 'value78805',
    'key2905': 'value47091',
    'key77664': 'value38801',
    'key67070': 'value82508',
    'key3101': 'value72669',
    'key50540': 'value46371',
},
    {
    'id': 17527490931031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Robert Atkins',
    'address': '19672 David Wall\nFlowersview, FM 64835',
    'text': 'Rather anything edge anything page. Tell range take site operation there wear decade. Baby quite leg hospital huge board return.',
    'email': 'coopercassandra@example.org',
    'phone_number': '612.740.6520',
    'json': {
    'name': 'Willie Jones',
    'address': '522 Mays Walks\nVictorville, PA 40507',
},
    'key57417': 'value92593',
},
    {
    'id': 17527490931043,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Melinda Schneider',
    'address': '8523 Kevin Fields Apt. 634\nPhillipshaven, UT 91186',
    'text': 'Front during conference from. General race question laugh medical.\nBaby leg speech stock coach yet. Why so purpose commercial. Experience and plan save whether.',
    'email': 'michaeldyer@example.org',
    'phone_number': '606-454-7568x859',
    'json': {
    'name': 'Billy White',
    'address': '277 Harris Trafficway Suite 176\nDavidton, WV 50554',
},
    'key67196': 'value39749',
    'key40956': 'value80611',
    'key17562': 'value7651',
    'key47862': 'value6533',
},
    {
    'id': 17527490931054,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Matthew Ellis',
    'address': '349 Gomez Lodge Apt. 936\nRaymondton, FM 95130',
    'text': 'Film pay less worry. Deep treat recent everybody director.',
    'email': 'wthompson@example.org',
    'phone_number': '001-780-630-8602x3207',
    'json': {
    'name': 'Amber Brown',
    'address': '0855 Matthews Underpass\nPort Jenniferton, IN 99018',
},
    'key27507': 'value59869',
    'key6187': 'value41239',
    'key62633': 'value8616',
},
    {
    'id': 17527490931065,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Amber Thomas',
    'address': '3988 Frank Valley\nPort Cynthia, DE 42373',
    'text': 'With will Democrat stand idea same from entire. South race network build office modern popular. College common now arrive stand example. Bed according east forget into dark life.',
    'email': 'kmoss@example.com',
    'phone_number': '642.894.8429',
    'json': {
    'name': 'Garrett Huff',
    'address': 'USNV Powell\nFPO AA 26954',
},
    'key23837': 'value11201',
    'key38694': 'value46701',
    'key70234': 'value7094',
    'key26030': 'value5638',
    'key99907': 'value14923',
    'key35697': 'value97122',
},
    {
    'id': 17527490931074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jody Jackson',
    'address': '931 Morris Forks\nGlassfurt, MP 95586',
    'text': 'Usually fall wide ground history research believe summer. Town soon structure onto hot.',
    'email': 'erinstafford@example.org',
    'phone_number': '919-867-4886x403',
    'json': {
    'name': 'Nicholas Pearson',
    'address': '4856 Schwartz Extensions Apt. 626\nMatthewton, MS 88395',
},
    'key20211': 'value33283',
    'key39214': 'value62758',
    'key7942': 'value36992',
},
    {
    'id': 17527490931086,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jeremy Kelly',
    'address': '346 Clinton Crossroad Suite 142\nBishopland, AR 05885',
    'text': 'Safe now second at. Religious series environmental young party major man quickly. Report yes significant approach explain.',
    'email': 'gwhite@example.org',
    'phone_number': '+1-441-619-1630x0219',
    'json': {
    'name': 'Sarah Mayer',
    'address': '038 Molina Port Suite 707\nKarenmouth, WV 72628',
},
    'key40553': 'value26864',
    'key93062': 'value20621',
    'key99250': 'value48770',
},
    {
    'id': 17527490931096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Spencer Dixon',
    'address': '18222 Angel Cliff\nAlexisstad, MD 34409',
    'text': 'Information anyone rather seek society. Great staff life be lay thank. Challenge piece level five.',
    'email': 'jennifer11@example.net',
    'phone_number': '453.850.0401x4223',
    'json': {
    'name': 'Jason Owens',
    'address': '92206 Joseph Prairie\nPort Colton, WI 68200',
},
    'key15999': 'value92229',
    'key7651': 'value77842',
    'key27803': 'value76336',
    'key81319': 'value27867',
    'key38908': 'value21641',
    'key37787': 'value89303',
    'key55057': 'value12838',
    'key80107': 'value8400',
},
    {
    'id': 17527490931106,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Donna Stewart',
    'address': '66624 Matthew Unions Suite 677\nNew Randy, AZ 90022',
    'text': 'Responsibility among sell manage finish. Whole Republican main open turn also. Table capital this help foot green.',
    'email': 'hendrickscatherine@example.net',
    'phone_number': '5728631592',
    'json': {
    'name': 'Anthony Hill',
    'address': '441 Sheri Inlet\nCoffeyfort, AK 77120',
},
    'key70495': 'value36911',
    'key24229': 'value35732',
    'key86019': 'value99398',
    'key47654': 'value67525',
    'key5612': 'value19128',
    'key27182': 'value65673',
    'key71991': 'value49070',
    'key84349': 'value72231',
    'key83279': 'value87458',
    'key82017': 'value95069',
},
    {
    'id': 17527490931117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'David Figueroa',
    'address': '400 Zachary Avenue\nNorth Mary, DE 75036',
    'text': 'More memory describe positive. Author personal white by race boy pattern.\nBank range any either could day east relate. Staff firm the culture Mrs. Carry really note yourself always.',
    'email': 'codykelley@example.com',
    'phone_number': '877.213.2580',
    'json': {
    'name': 'Elizabeth Lynch',
    'address': '032 Allen Tunnel\nEmilyside, LA 62616',
},
    'key91079': 'value34332',
},
    {
    'id': 17527490931128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Joseph Mccullough',
    'address': 'USCGC Stewart\nFPO AA 25317',
    'text': 'Town country range spend Congress during. Specific over pretty trade pretty week trial. Key like current gun paper mother produce.',
    'email': 'pauljackson@example.net',
    'phone_number': '(882)637-9092',
    'json': {
    'name': 'Kristina Sandoval',
    'address': '624 Logan Row Apt. 691\nNorth Nicholas, GU 32371',
},
    'key18274': 'value94724',
    'key20182': 'value15257',
    'key48015': 'value37514',
    'key15566': 'value13549',
    'key18724': 'value82069',
    'key33379': 'value88433',
    'key97268': 'value73722',
    'key37267': 'value87012',
    'key67840': 'value54592',
    'key18206': 'value62991',
},
    {
    'id': 17527490931139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Heidi Rhodes',
    'address': '3984 Burns Meadow\nPort Sharon, MD 67371',
    'text': 'Onto look way study level answer. Worker fill dog put be about.\nCare white natural start know finally sure future.\nFact early her difficult finally. Decision throughout century.',
    'email': 'qtapia@example.org',
    'phone_number': '597.861.9604x660',
    'json': {
    'name': 'Emily Bennett',
    'address': '656 Johnson Shoal\nBakerhaven, PW 45501',
},
    'key29614': 'value24720',
    'key3301': 'value34510',
    'key42839': 'value6939',
    'key60818': 'value15021',
},
    {
    'id': 17527490931150,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Troy Roy',
    'address': '05220 Melissa Burg Suite 900\nBrandonview, DC 04911',
    'text': 'Mission again challenge suffer pretty ahead build. Account catch since white true structure this. Too improve education certainly.',
    'email': 'litonya@example.org',
    'phone_number': '4595408151',
    'json': {
    'name': 'Teresa Hoffman',
    'address': '95550 Murphy Crossroad Apt. 310\nGordonfurt, SC 79534',
},
    'key7554': 'value85531',
    'key24328': 'value93787',
},
    {
    'id': 17527490931161,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Erica Pratt',
    'address': '6099 Moore Pass\nPort Anneland, IL 98634',
    'text': 'Stop beat politics true international girl laugh. Respond spring he reason.\nDescribe business any notice hope wife debate.',
    'email': 'reginabrown@example.net',
    'phone_number': '+1-558-658-8888x5627',
    'json': {
    'name': 'Aaron Mann',
    'address': '545 Villegas Summit Suite 725\nEast Paulland, NC 06950',
},
    'key66516': 'value75702',
    'key41246': 'value72682',
    'key4321': 'value89500',
    'key78372': 'value40285',
    'key8616': 'value7420',
    'key60469': 'value40620',
    'key4291': 'value20424',
    'key23705': 'value95244',
},
    {
    'id': 17527490931172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Melissa Hess',
    'address': '33693 Carlson River\nJasminemouth, AZ 42155',
    'text': 'Central man key arm parent. Western citizen work stuff magazine truth occur. Or security move poor present.\nThing really third just.',
    'email': 'jwerner@example.com',
    'phone_number': '722-200-8962',
    'json': {
    'name': 'Emily Contreras',
    'address': '543 Stephanie Road Apt. 259\nWest Stephaniechester, AS 79599',
},
    'key88704': 'value99278',
    'key75350': 'value77072',
    'key26078': 'value66058',
    'key91153': 'value47466',
    'key76684': 'value20348',
    'key52321': 'value42618',
    'key62701': 'value81995',
    'key78694': 'value48651',
    'key87613': 'value33435',
},
    {
    'id': 17527490931183,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Carolyn Lewis',
    'address': '37797 Rivera Lodge Suite 978\nNorth Amanda, NM 40526',
    'text': 'Edge perhaps outside office sport class sound. Together guy thing bank letter. Minute plant treat everybody like today.',
    'email': 'pecktoni@example.com',
    'phone_number': '+1-978-596-6490',
    'json': {
    'name': 'Brandon Thomas',
    'address': '33576 Rebecca Creek\nSolomonborough, CO 70381',
},
    'key36540': 'value19157',
    'key24059': 'value46476',
    'key22135': 'value23307',
    'key11888': 'value17927',
    'key32662': 'value62735',
},
    {
    'id': 17527490931195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Patricia Larson',
    'address': '2856 Walters Mount\nSchultzton, MD 63188',
    'text': 'Manage along story risk eye cost quite. Indeed believe mention news happen place. Possible some about since.\nCollege life scientist.',
    'email': 'karlajohnson@example.net',
    'phone_number': '507.980.3343',
    'json': {
    'name': 'Jennifer Green',
    'address': '972 Mark Forge\nGeorgemouth, PW 72804',
},
    'key46965': 'value46106',
},
    {
    'id': 17527490931206,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Andrea Graham',
    'address': '7676 Brown Turnpike Suite 254\nEricchester, CT 98535',
    'text': 'Look safe interview create. Explain night night foot. Tonight easy son special investment position.\nWant magazine animal. Site cup without defense American computer college.',
    'email': 'robert51@example.org',
    'phone_number': '(737)846-6535x950',
    'json': {
    'name': 'Wesley Davis',
    'address': '044 Salazar Trail Apt. 890\nAndrewsburgh, TX 09266',
},
    'key71323': 'value736',
    'key72819': 'value62034',
    'key38382': 'value60342',
    'key25451': 'value43039',
    'key89146': 'value70253',
},
    {
    'id': 17527490931217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Michael Jenkins',
    'address': '49250 Krista Throughway Suite 826\nLake Melissa, WI 52847',
    'text': 'Time staff human street president rate right. Series central trip ground smile after. Drive woman its section remember bad write.\nDuring film receive. Son speak woman score.',
    'email': 'hermantim@example.com',
    'phone_number': '529.973.8323',
    'json': {
    'name': 'Joseph Martin',
    'address': '1200 Myers Court\nNew Andrew, NH 86278',
},
    'key52255': 'value19052',
    'key82601': 'value64224',
    'key82290': 'value54504',
    'key16324': 'value77802',
    'key14072': 'value30787',
    'key46528': 'value67529',
    'key87600': 'value51787',
    'key94955': 'value62530',
    'key66858': 'value97653',
},
    {
    'id': 17527490931229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Morgan Proctor',
    'address': '649 George Forges Apt. 552\nEvansview, NY 22210',
    'text': 'Benefit open nature against system site. Give local form market practice point remain. Although baby someone either.',
    'email': 'john28@example.net',
    'phone_number': '(765)765-0784x7645',
    'json': {
    'name': 'Pamela Foster',
    'address': 'PSC 9034, Box 0485\nAPO AA 04214',
},
    'key29417': 'value5149',
    'key1338': 'value20590',
    'key6343': 'value73797',
    'key19542': 'value31774',
},
    {
    'id': 17527490931239,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Barbara Cunningham',
    'address': '9347 Jean Ridge\nAmbermouth, NC 24867',
    'text': 'Girl star arm send marriage. Idea when buy society.\nRoom everybody themselves day even seem east. Early two generation the gas kitchen.',
    'email': 'goodwingina@example.net',
    'phone_number': '(529)879-2029x47084',
    'json': {
    'name': 'Valerie Jones',
    'address': '0172 Emily Station Suite 561\nChristopherstad, MH 79904',
},
    'key95913': 'value29157',
    'key69957': 'value95312',
    'key57798': 'value50622',
},
    {
    'id': 17527490931250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Tammy Meadows',
    'address': '0363 Turner Square Apt. 905\nNorth Marcusberg, MS 71256',
    'text': 'Throughout cup figure stuff author.\nPage apply everybody. Human pick reduce entire. Participant movie economic example.',
    'email': 'jonesrichard@example.org',
    'phone_number': '732.584.4430',
    'json': {
    'name': 'Aaron Jimenez',
    'address': '37511 Julia Loaf\nEast Christine, NC 32897',
},
    'key98991': 'value19579',
    'key39804': 'value85422',
    'key40540': 'value42903',
},
    {
    'id': 17527490931262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sarah Faulkner',
    'address': '0370 Mitchell Shore\nAnitaview, NM 24687',
    'text': 'Whose high begin citizen future agent by. Group hand upon collection officer.\nIdentify rich rest training risk there less. Job glass food outside.',
    'email': 'whiteheaddiana@example.net',
    'phone_number': '689.250.6705',
    'json': {
    'name': 'Mark Lee',
    'address': '6602 Williams Camp Suite 325\nAnthonyfort, NM 92787',
},
    'key34424': 'value98475',
    'key95763': 'value7913',
    'key63118': 'value94058',
    'key17939': 'value6719',
},
    {
    'id': 17527490931274,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Hannah Simpson',
    'address': '015 Fletcher Underpass Suite 058\nPort Ricky, MS 66704',
    'text': 'Experience other whether such nation. Without site better rise community.\nWish scene direction voice law. Hear these including short them. Many most never sure.',
    'email': 'meghan22@example.org',
    'phone_number': '+1-731-986-7898x00161',
    'json': {
    'name': 'Jeffrey Wong',
    'address': '6422 Paul Fields Suite 848\nEast Colton, UT 07203',
},
    'key32490': 'value53944',
    'key85468': 'value69994',
    'key76046': 'value78937',
    'key25741': 'value29452',
    'key92529': 'value15011',
    'key78762': 'value53944',
    'key47206': 'value6238',
    'key92324': 'value74232',
},
    {
    'id': 17527490931286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Eugene Scott',
    'address': '7127 Santiago Courts Apt. 734\nNew Sean, ID 82882',
    'text': 'Situation address federal sit us which agent. Floor western read today newspaper general.\nHimself strong hot charge television miss. Hour bed environment discuss all threat.',
    'email': 'jon75@example.net',
    'phone_number': '(817)818-0041x2905',
    'json': {
    'name': 'Kristin Thomas',
    'address': 'PSC 4771, Box 3643\nAPO AE 06081',
},
    'key75869': 'value41363',
    'key40366': 'value84818',
    'key76537': 'value7082',
    'key95317': 'value10299',
    'key53802': 'value95278',
    'key70556': 'value57121',
    'key89797': 'value11835',
    'key5484': 'value31086',
},
    {
    'id': 17527490931296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Elizabeth Mcdonald',
    'address': '93636 Johnson Ridges Apt. 400\nJohnsonville, OK 90344',
    'text': 'Too mean generation learn adult page after. Tree among lose experience feeling form.\nBlue guess group tree.\nProcess note agent now those ten. Firm world buy senior soon car.',
    'email': 'ksmith@example.net',
    'phone_number': '+1-916-265-3207x719',
    'json': {
    'name': 'Robert Brown',
    'address': '175 Baker Course Suite 280\nGlenmouth, IN 43916',
},
    'key60733': 'value84707',
    'key64357': 'value56595',
    'key16572': 'value95001',
},
    {
    'id': 17527490931309,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Melissa Cohen',
    'address': '52763 Jack Forges Suite 661\nLake Hailey, NH 59842',
    'text': 'Meet nice close of adult. Ahead yard environment dinner western. Spend agreement sense environmental source fish.',
    'email': 'anne34@example.net',
    'phone_number': '(677)619-3533x7976',
    'json': {
    'name': 'Evan Davis',
    'address': '9994 Jacob Groves Suite 118\nPort Yolanda, ID 85939',
},
    'key22573': 'value45600',
    'key37016': 'value25171',
    'key42151': 'value96931',
    'key84922': 'value96130',
    'key13019': 'value42709',
    'key7735': 'value47443',
    'key11814': 'value16436',
    'key22026': 'value16180',
},
    {
    'id': 17527490931320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Angela Andrews',
    'address': '4816 Stephanie Ridges Apt. 281\nSouth Richardhaven, NY 76333',
    'text': 'Name close second side drop finish. Body art most feel suffer maintain executive draw. Evidence right expert catch.\nMight language attorney discussion husband under somebody.',
    'email': 'suzannemora@example.org',
    'phone_number': '456-496-8393',
    'json': {
    'name': 'Joseph Hampton',
    'address': '2557 Simmons Rue Suite 705\nPort Rebecca, ND 62810',
},
    'key61381': 'value6049',
    'key35529': 'value39486',
    'key99618': 'value10973',
    'key42661': 'value49326',
    'key36296': 'value21692',
    'key24470': 'value43661',
    'key22546': 'value99636',
},
    {
    'id': 17527490931331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Zoe Robertson',
    'address': '919 Jacob Crest Suite 579\nYoungport, CA 26028',
    'text': 'Effort lot center soon exactly phone PM. Less wind thus reason issue prove task.\nMember spend sometimes which party the approach. Real treat Mrs hundred. Now want rock force state.',
    'email': 'ashleyhamilton@example.com',
    'phone_number': '001-689-989-0113x997',
    'json': {
    'name': 'Sarah Martinez',
    'address': 'Unit 5436 Box 1073\nDPO AE 51405',
},
    'key41538': 'value79013',
    'key39637': 'value33066',
    'key69643': 'value32569',
    'key26363': 'value98513',
    'key29770': 'value83521',
    'key25576': 'value76402',
},
    {
    'id': 17527490931341,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Paul Hines',
    'address': '25022 John Courts\nKimberlytown, ME 09958',
    'text': 'Subject do still likely fund whole. Hear them hotel campaign. Down wind let themselves happen.\nMake none by tonight natural investment. Best matter structure another compare write process popular.',
    'email': 'brian77@example.net',
    'phone_number': '5452285304',
    'json': {
    'name': 'James Hernandez',
    'address': '88637 Owens Underpass\nHolmesland, PR 56813',
},
    'key34768': 'value73959',
    'key95030': 'value31926',
    'key69260': 'value16248',
    'key59553': 'value47905',
    'key92352': 'value48270',
    'key22320': 'value48231',
    'key84061': 'value34640',
},
    {
    'id': 17527490931351,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Jessica Schaefer',
    'address': '3431 Timothy Drives\nRonaldtown, AK 90445',
    'text': 'Prepare interesting story. Third rate thank six modern through since.',
    'email': 'uharrell@example.org',
    'phone_number': '544.311.3960',
    'json': {
    'name': 'Ashley Davis',
    'address': '61559 Cynthia Fork Suite 914\nWest Michael, RI 86436',
},
    'key49745': 'value84089',
    'key14124': 'value8363',
    'key417': 'value62236',
    'key2892': 'value65827',
    'key22568': 'value69216',
},
    {
    'id': 17527490931361,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Timothy Murphy',
    'address': '18208 Robin Greens Suite 957\nEast John, WV 14224',
    'text': 'Health dog rock turn price radio quite. Ready need among find gun.\nSign draw know wrong lose newspaper word.',
    'email': 'cbowen@example.org',
    'phone_number': '684-789-9536',
    'json': {
    'name': 'James Torres',
    'address': '5319 Hill Islands Suite 966\nKellyton, MS 97753',
},
    'key41289': 'value33750',
    'key97871': 'value60645',
    'key80199': 'value40413',
    'key47911': 'value94729',
    'key74913': 'value29787',
},
    {
    'id': 17527490931373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Hunter Rodriguez',
    'address': '13532 Julie Spur Suite 970\nEast Maria, OR 90807',
    'text': 'Sit wish specific project adult wind fire team. Sure under face lay. Choose exist her spend already soon.',
    'email': 'kwalker@example.com',
    'phone_number': '(890)385-9731x382',
    'json': {
    'name': 'Michele Barnes',
    'address': '60595 Rivas Land\nNorth James, TN 57560',
},
    'key73562': 'value61872',
    'key52245': 'value52345',
    'key73728': 'value19060',
    'key91493': 'value12107',
    'key15352': 'value74940',
    'key14895': 'value18063',
    'key37495': 'value21361',
    'key51079': 'value89777',
    'key46689': 'value44400',
},
    {
    'id': 17527490931383,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Sharon Scott',
    'address': '234 Austin Parkways Suite 473\nSethport, NV 48716',
    'text': 'Population leave year car. Wind use kitchen somebody say environmental put. Without best up common treatment focus message.',
    'email': 'nicolashorton@example.org',
    'phone_number': '653-897-5435',
    'json': {
    'name': 'Ashley Mccarthy',
    'address': '2234 Black Common\nNew Joseborough, NC 01096',
},
    'key58257': 'value13002',
    'key70679': 'value12818',
    'key33364': 'value79179',
    'key18154': 'value73359',
},
    {
    'id': 17527490931395,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Stephanie Mendez',
    'address': '675 Holly Knolls Suite 086\nPort Jessicatown, SD 59043',
    'text': 'Politics pattern public walk ability. Collection same face concern something. Word statement take move.',
    'email': 'wagnerjohn@example.net',
    'phone_number': '(511)948-7806x2237',
    'json': {
    'name': 'Angela Hartman',
    'address': '55916 Ross Ridges\nWilsonstad, OH 62742',
},
    'key46206': 'value86125',
    'key84211': 'value19081',
},
    {
    'id': 17527490931407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Anita Best',
    'address': '788 Meyers Glen Suite 694\nSmithview, UT 66237',
    'text': 'Sister shoulder computer street important these meet. Meet here couple inside network box.\nNumber ability series one dream. Staff although like its quite bit throughout.',
    'email': 'nelsonderek@example.org',
    'phone_number': '620-208-2149x866',
    'json': {
    'name': 'Christopher Graham',
    'address': '45926 Matthew Burgs Suite 586\nNew Nicole, MI 61443',
},
    'key5619': 'value8834',
    'key56296': 'value29385',
    'key59677': 'value63765',
    'key78670': 'value32774',
},
    {
    'id': 17527490931418,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Karen Wiley',
    'address': '895 Jones Avenue\nNorth Michael, NC 30549',
    'text': 'Despite still staff big brother. Career us there glass environmental probably.\nThrough card million house. Ok unit dinner threat answer mean personal. Able everything across single shake.',
    'email': 'garciaeric@example.org',
    'phone_number': '(877)393-1752',
    'json': {
    'name': 'Alexandra Williams',
    'address': '9492 Peterson Corners\nLaurafurt, SC 28163',
},
    'key95118': 'value4402',
    'key72321': 'value70071',
    'key57152': 'value96981',
    'key40831': 'value37293',
    'key51696': 'value35922',
    'key47895': 'value46012',
    'key65624': 'value19621',
},
    {
    'id': 17527490931430,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Matthew Smith',
    'address': '06814 Hubbard Underpass\nPatriciaville, TN 60887',
    'text': 'Suddenly east level ten trouble ten foot matter. Audience doctor environmental voice rise smile. Foreign soon various western population organization.',
    'email': 'chavezwendy@example.org',
    'phone_number': '(218)838-0081x474',
    'json': {
    'name': 'Jason Wilson',
    'address': '354 Cox Forks Suite 434\nEast Matthewmouth, NH 44913',
},
    'key37013': 'value19318',
    'key65832': 'value3090',
    'key20151': 'value45312',
    'key45274': 'value2900',
    'key9230': 'value29748',
    'key26855': 'value27218',
},
    {
    'id': 17527490931442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Brittany Palmer DDS',
    'address': '134 Levine Rest Suite 312\nLake Alicia, MN 58029',
    'text': 'Coach picture everyone avoid these policy continue behavior. Current fall type word reason. Order father admit.',
    'email': 'whitejeffrey@example.net',
    'phone_number': '839-393-2984',
    'json': {
    'name': 'Crystal Kennedy',
    'address': '134 Hoffman Heights Apt. 046\nNorth Christinefort, MI 50732',
},
    'key86836': 'value58775',
    'key70155': 'value85396',
    'key76121': 'value53570',
    'key4872': 'value71345',
    'key54514': 'value92604',
    'key59237': 'value37160',
    'key94214': 'value83807',
},
    {
    'id': 17527490931454,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Emily Young',
    'address': 'Unit 7856 Box 1527\nDPO AP 38042',
    'text': 'Beautiful activity major standard behind past discuss. Certainly structure add sell white possible. Later almost manager age ball quickly.',
    'email': 'ashleymiller@example.org',
    'phone_number': '4333890250',
    'json': {
    'name': 'Erik Davis',
    'address': '091 Benton Ridges Apt. 778\nAguirreview, IN 47460',
},
    'key19362': 'value34328',
    'key92068': 'value69511',
    'key87675': 'value23753',
    'key21128': 'value47357',
    'key7387': 'value91927',
    'key60860': 'value29320',
},
    {
    'id': 17527490931464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Stephen Butler',
    'address': '861 Lopez Way Apt. 119\nWest Robert, ID 71292',
    'text': 'White window form attorney shoulder. Report I floor would.\nManager today approach call rich business for.\nOthers explain then who southern yourself foreign.',
    'email': 'brandimiller@example.org',
    'phone_number': '617-632-5417x651',
    'json': {
    'name': 'Robert Williams',
    'address': '03639 Benson Spur Suite 995\nWest John, NY 93401',
},
    'key30944': 'value94911',
    'key19128': 'value22962',
},
    {
    'id': 17527490931476,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'James Morales',
    'address': '2916 Fletcher Street\nMoorefurt, OR 16668',
    'text': 'Machine meeting learn charge and. Chance within deal family majority under program to.',
    'email': 'robinsonsarah@example.com',
    'phone_number': '(524)754-0047x959',
    'json': {
    'name': 'Brittany Hernandez',
    'address': '8711 Karen Village Apt. 698\nGreenchester, NM 64428',
},
    'key55710': 'value34432',
    'key2666': 'value2008',
    'key53917': 'value86326',
    'key22533': 'value49326',
    'key95297': 'value58705',
    'key95451': 'value21426',
    'key26259': 'value68830',
},
    {
    'id': 17527490931489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Christopher Hudson',
    'address': '081 Michael Ports Apt. 286\nWest Martin, AZ 71508',
    'text': 'Run necessary sound doctor difficult pressure. Return care effort.\nDrive so smile clearly necessary why news. Phone possible back. Control you green stuff those exactly law.',
    'email': 'christopher64@example.net',
    'phone_number': '001-914-904-0572',
    'json': {
    'name': 'Craig Mitchell',
    'address': '1442 Sawyer Inlet\nWest Danielmouth, IN 95636',
},
    'key74112': 'value33230',
    'key38640': 'value48852',
    'key13056': 'value81537',
    'key92075': 'value35662',
    'key24298': 'value23066',
    'key36581': 'value82891',
    'key22175': 'value65676',
    'key33960': 'value35886',
    'key13349': 'value95094',
},
    {
    'id': 17527490931500,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Kelly White',
    'address': '900 Nathan Bypass Apt. 160\nWest Joseph, NM 73501',
    'text': 'Material wide whatever general. Situation take thank head popular try example. Population them stop election pass.',
    'email': 'donaldclark@example.org',
    'phone_number': '647-782-7880x0712',
    'json': {
    'name': 'Elizabeth Campbell',
    'address': '55354 Manuel Valley\nPort Brandonville, AK 82725',
},
    'key78828': 'value30375',
    'key62926': 'value68259',
    'key45317': 'value42241',
    'key47112': 'value67514',
    'key68409': 'value44344',
    'key91412': 'value73680',
    'key62392': 'value92464',
    'key6817': 'value74527',
    'key30984': 'value10456',
    'key98573': 'value35273',
},
    {
    'id': 17527490931512,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Eric Santana',
    'address': 'Unit 8070 Box 8344\nDPO AA 28364',
    'text': 'Sing rest state four lawyer short. One state oil reduce. Approach assume later.\nAcross since truth senior heavy herself.',
    'email': 'caroline99@example.net',
    'phone_number': '001-644-869-5387x319',
    'json': {
    'name': 'Gregory Stone',
    'address': '35277 Anthony Underpass\nKarenville, NH 27869',
},
    'key2835': 'value31637',
    'key95022': 'value89777',
    'key23965': 'value25170',
    'key93819': 'value7194',
    'key8957': 'value43000',
    'key7589': 'value54336',
    'key9602': 'value47461',
    'key2738': 'value3761',
    'key86480': 'value86308',
},
    {
    'id': 17527490931521,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Joseph Howard',
    'address': '695 Donna Ramp\nPort Nicole, ID 64772',
    'text': 'Theory billion spend great prepare.\nAmount cost administration cost sign seek. Certainly television per parent three like church.',
    'email': 'andreasmith@example.org',
    'phone_number': '(918)554-3876x696',
    'json': {
    'name': 'Haley Dalton',
    'address': '1631 Anderson Parkways Suite 332\nPort Adam, MO 55560',
},
    'key32676': 'value56524',
},
    {
    'id': 17527490931532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Russell Cabrera',
    'address': '890 Huffman Throughway Suite 082\nLake Rachelshire, ID 39955',
    'text': 'Agreement possible crime bill window stock big dinner. Agency point miss sort charge born. Board necessary like head coach teacher PM.',
    'email': 'baileykayla@example.org',
    'phone_number': '(490)505-7451x77125',
    'json': {
    'name': 'Jessica Turner',
    'address': 'USNV Solis\nFPO AP 37800',
},
    'key83416': 'value74898',
    'key95700': 'value32733',
    'key35847': 'value47893',
    'key90013': 'value10992',
    'key3331': 'value72042',
    'key15488': 'value57634',
},
    {
    'id': 17527490931542,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Karla Morse',
    'address': '8356 Price Lights\nNorth Donna, LA 41059',
    'text': 'Or quite what senior director play lay. Evening identify his feeling camera method.',
    'email': 'cuevasvictor@example.org',
    'phone_number': '292-263-9911',
    'json': {
    'name': 'Catherine Brown',
    'address': '5635 Evans Ramp\nNew Wandahaven, AK 25061',
},
    'key31928': 'value59796',
    'key81860': 'value94018',
    'key71855': 'value82929',
},
    {
    'id': 17527490931553,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Darrell Mccarthy',
    'address': '526 Hess Burgs\nJohnsonville, TN 09362',
    'text': 'Wall expect what little response. Goal condition purpose. Community tell total miss.',
    'email': 'rubenmcpherson@example.org',
    'phone_number': '625.342.3288x664',
    'json': {
    'name': 'Alan Jackson',
    'address': '0366 Washington Village Suite 488\nWest Rachel, PW 40339',
},
    'key66332': 'value62592',
    'key2064': 'value83152',
},
    {
    'id': 17527490931565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Nancy Poole',
    'address': '18653 Carrie Garden Apt. 426\nNew Noahtown, TN 25084',
    'text': 'Manage during fish money wonder recent.\nWife catch live step. Politics someone within cause government. Article serious learn personal page middle positive.',
    'email': 'hernandezsean@example.net',
    'phone_number': '001-333-730-2098x238',
    'json': {
    'name': 'Marcus Miller',
    'address': '7392 Noah Courts Apt. 795\nLoriville, GA 74892',
},
    'key10737': 'value84466',
    'key5751': 'value1822',
},
    {
    'id': 17527490931577,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Kenneth Evans',
    'address': '12398 Roger Harbor Suite 358\nWilliamsburgh, VT 30633',
    'text': 'Take rise financial feeling. Baby remember piece test find.\nCost base debate toward. Think live article conference government shoulder. Light one practice mean continue land.',
    'email': 'pwhite@example.com',
    'phone_number': '475-313-2956',
    'json': {
    'name': 'Ryan Burgess MD',
    'address': '7186 Craig Lock\nAndersonchester, NC 31788',
},
    'key1254': 'value53767',
    'key14798': 'value80231',
    'key71810': 'value48063',
    'key73592': 'value80960',
    'key30700': 'value54613',
    'key8879': 'value18144',
    'key47592': 'value95179',
    'key14410': 'value25363',
    'key10378': 'value69893',
    'key51316': 'value69442',
},
    {
    'id': 17527490931588,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Victoria Grant',
    'address': '714 Monica Drive\nPamelafort, ME 97078',
    'text': 'She memory natural before.\nParticular establish pass future different data there cause. New establish left total maybe whatever evidence. Culture night start seem health as last nature.',
    'email': 'melvin08@example.net',
    'phone_number': '(755)311-4877',
    'json': {
    'name': 'Eric Hutchinson',
    'address': '72874 Allen Landing Suite 111\nJessicachester, PA 09706',
},
    'key44736': 'value84729',
    'key35135': 'value28204',
    'key31168': 'value69280',
    'key7928': 'value97279',
    'key79035': 'value14646',
    'key46253': 'value71697',
    'key91866': 'value47661',
    'key27439': 'value50637',
    'key98504': 'value24326',
    'key11339': 'value79829',
},
    {
    'id': 17527490931598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Mrs. Breanna Warren',
    'address': '1588 Angelica Mission\nSouth Chase, UT 16029',
    'text': 'Son on growth training.\nOutside everything reduce remember. Task anything establish this room hot. Citizen job be chance few bed.\nEdge into establish sense. News truth view.',
    'email': 'daniellehill@example.org',
    'phone_number': '5965476687',
    'json': {
    'name': 'Melody Adams',
    'address': '47977 Freeman Trail Suite 848\nNorth Gary, SC 05267',
},
    'key73190': 'value38837',
    'key83834': 'value70494',
    'key39752': 'value98583',
},
    {
    'id': 17527490931610,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Jeanette Olsen',
    'address': '99357 Zachary Viaduct Apt. 197\nSnyderburgh, WV 96217',
    'text': 'Suddenly product put child sound window born effort. Per order mind practice partner support. Mention they real language ball back tend. Worry feeling well her.',
    'email': 'huntvanessa@example.net',
    'phone_number': '639-250-5482x2865',
    'json': {
    'name': 'Joshua Nguyen',
    'address': '8455 Tracy Shore Suite 184\nAlejandrotown, CT 99488',
},
    'key112': 'value83527',
    'key90850': 'value74648',
    'key98836': 'value61894',
    'key89197': 'value42834',
},
    {
    'id': 17527490931621,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'James Bolton',
    'address': '317 Caroline Locks Suite 595\nSouth Paula, CT 09077',
    'text': 'Size indeed send network pretty society. Must money top others official nothing specific.\nFree environment hard agent child majority. Strong huge best include.',
    'email': 'thomasvincent@example.org',
    'phone_number': '001-346-834-9696x584',
    'json': {
    'name': 'Nicholas Andrade',
    'address': 'PSC 1905, Box 6559\nAPO AP 50633',
},
    'key46162': 'value58032',
    'key46843': 'value60047',
    'key87819': 'value39986',
    'key57807': 'value57961',
    'key87393': 'value45844',
    'key90176': 'value90048',
    'key11222': 'value89495',
    'key36972': 'value94494',
    'key96277': 'value69491',
},
    {
    'id': 17527490931631,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Rachel Arellano',
    'address': '08936 Cervantes Prairie\nFarmerview, LA 11286',
    'text': 'Imagine different modern policy. Throw tonight watch while report drop expert.\nCamera that sense agent. Window director big nothing today.',
    'email': 'gordonbradley@example.com',
    'phone_number': '+1-548-480-1359',
    'json': {
    'name': 'Ashley Parker',
    'address': '91841 Martinez Fields Suite 625\nCummingsfurt, MO 70847',
},
    'key99041': 'value27493',
    'key7648': 'value47394',
    'key48506': 'value39736',
    'key41943': 'value2891',
    'key51740': 'value60118',
    'key96911': 'value39159',
    'key50505': 'value90124',
    'key39816': 'value3758',
    'key52516': 'value29146',
    'key18960': 'value40681',
},
    {
    'id': 17527490931642,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Judith Waller',
    'address': '09717 Brandon Bridge\nCastillofurt, VI 35111',
    'text': 'Case skill piece hair bag. After end provide nor company democratic.\nSit money suddenly interest. Personal partner buy impact. Produce item buy tonight eight off main.',
    'email': 'schultznicholas@example.net',
    'phone_number': '+1-817-356-1499x0300',
    'json': {
    'name': 'Raymond Maxwell',
    'address': '830 Gibbs Trail Suite 782\nLake Erica, NJ 41886',
},
    'key34011': 'value84771',
    'key63064': 'value68838',
},
    {
    'id': 17527490931654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Alison Williams',
    'address': '825 Sean Fort Suite 072\nArthurfort, WY 91061',
    'text': 'Future turn stand well reach fact. American can citizen social.\nFamily amount if than. Prepare and help modern project.\nEnough day adult imagine ok water.',
    'email': 'lisa86@example.net',
    'phone_number': '851-522-3961x37756',
    'json': {
    'name': 'Matthew Brown',
    'address': '99688 Brown Radial Suite 653\nMitchellville, FM 25083',
},
    'key78184': 'value17977',
    'key84579': 'value60732',
    'key98584': 'value91166',
    'key28218': 'value6291',
    'key52202': 'value6155',
},
    {
    'id': 17527490931665,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Cynthia Ward',
    'address': '436 Galloway Turnpike\nGrantberg, IA 53805',
    'text': 'Network feel only nor tough guess so. He continue threat.\nSport term something no surface still open. Scene until in medical stage. Team third too head century develop region before.',
    'email': 'victor70@example.com',
    'phone_number': '715.453.3925x928',
    'json': {
    'name': 'Patricia Hughes',
    'address': '436 Brandon Meadows Apt. 369\nLake Chris, AK 46019',
},
    'key88741': 'value73381',
},
    {
    'id': 17527490931676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Rebekah Frederick',
    'address': '10175 Marvin Brook Suite 478\nNew Aaronside, WY 24817',
    'text': 'Agreement peace tough hear now.\nDecade hour week should across somebody. Raise more democratic power here read right trip.',
    'email': 'thanson@example.net',
    'phone_number': '3839642121',
    'json': {
    'name': 'Victor Myers',
    'address': '8486 Hughes Village\nBellberg, HI 82655',
},
    'key3079': 'value87381',
    'key59600': 'value91308',
    'key84543': 'value47843',
    'key55410': 'value58546',
    'key20021': 'value3770',
},
    {
    'id': 17527490931687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Joseph Brown',
    'address': '881 King Via\nPort Angela, SD 14690',
    'text': 'Newspaper teacher law standard positive move. Hot program camera condition near. Scientist any exactly author money find current happen.\nCamera star Mrs deal.\nHealth cell night maybe.',
    'email': 'yorkdeborah@example.org',
    'phone_number': '938-559-5742x7533',
    'json': {
    'name': 'Sandra Farmer',
    'address': '6712 David Cape\nPort Stevenside, MN 24135',
},
    'key66644': 'value90892',
    'key6325': 'value92570',
    'key73885': 'value24647',
    'key36012': 'value88074',
    'key87055': 'value58868',
    'key62901': 'value62689',
},
    {
    'id': 17527490931698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Shawn Robinson',
    'address': '64062 Summers Villages\nSaundersberg, TN 87711',
    'text': 'Human left sort these. Land base five among. Especially product mouth administration give say trade development.\nFood outside in remain lawyer tonight any. Board go also your tough cold.',
    'email': 'imalone@example.net',
    'phone_number': '715.955.5168',
    'json': {
    'name': 'Nicholas Holmes',
    'address': 'PSC 4442, Box 6411\nAPO AA 21264',
},
    'key22962': 'value38559',
    'key5013': 'value87251',
    'key25864': 'value46876',
    'key55027': 'value7693',
    'key54114': 'value52160',
    'key68903': 'value42441',
    'key64287': 'value63868',
    'key53909': 'value85563',
    'key46931': 'value72002',
    'key39077': 'value10605',
},
    {
    'id': 17527490931707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'David Perry',
    'address': '619 Barrera Walk Apt. 720\nLake Kristen, OK 81700',
    'text': 'Age partner back member mind. Its boy project fight actually. Lawyer friend live remember professional.\nOver education condition. One really during feel pretty.',
    'email': 'galvanandrea@example.net',
    'phone_number': '486.893.7603',
    'json': {
    'name': 'Timothy Herrera',
    'address': '622 Carl Corner Apt. 174\nPriscillafurt, MN 00878',
},
    'key74207': 'value97114',
    'key75596': 'value75018',
},
    {
    'id': 17527490931718,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Micheal Clay',
    'address': '542 Kyle Parkways Apt. 318\nJefferyfurt, MD 39014',
    'text': 'Per increase including ten yourself bed why thus. The traditional hotel theory year. Century necessary moment push. Action position child audience success success.',
    'email': 'paulmurillo@example.com',
    'phone_number': '+1-412-955-8053x978',
    'json': {
    'name': 'Omar Brooks',
    'address': '89036 Gina Forge Apt. 819\nGrayfurt, DE 89077',
},
    'key7690': 'value56184',
    'key42736': 'value90298',
    'key99495': 'value17451',
    'key7776': 'value82921',
},
    {
    'id': 17527490931730,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Mark White',
    'address': '18353 Chavez Knolls Apt. 245\nHooverview, NE 44364',
    'text': 'Couple low poor. Force seek value impact energy. Cell small toward a watch security.',
    'email': 'hernandezrachel@example.org',
    'phone_number': '+1-345-821-7638x12185',
    'json': {
    'name': 'Heather Price',
    'address': '695 Matthew Landing\nWest Danielport, MH 64171',
},
    'key98731': 'value86606',
    'key2788': 'value65870',
    'key6987': 'value22083',
    'key17269': 'value70590',
    'key59721': 'value2504',
    'key22637': 'value73266',
    'key30016': 'value94626',
    'key57797': 'value87532',
},
    {
    'id': 17527490931742,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Katie Hernandez',
    'address': '00527 Solis Junction\nLopezville, MH 31653',
    'text': 'Compare face yard room whatever. Recently form hair son.\nHard some contain rather garden. Art yes structure certainly wall simply. Lead rule anyone key special most thus sign.',
    'email': 'ronald30@example.org',
    'phone_number': '+1-579-641-6645x29991',
    'json': {
    'name': 'Corey Gardner',
    'address': '15874 Daniel Knolls Suite 971\nCourtneymouth, PW 24950',
},
    'key72813': 'value61866',
    'key81136': 'value68354',
    'key94999': 'value70834',
    'key31864': 'value76310',
    'key18519': 'value637',
},
    {
    'id': 17527490931752,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Peter Hanson',
    'address': '44053 Scott Harbor\nEast Roger, GA 63417',
    'text': 'Field public now glass letter to.\nBeautiful tax either yeah would already again. Might firm behind least. Nice Congress TV girl because consumer.\nGreen soldier information worker whom.',
    'email': 'garciaderek@example.com',
    'phone_number': '566.846.8204x1989',
    'json': {
    'name': 'Edward Long',
    'address': '7639 Collins Ports\nSouth Kennethhaven, GA 97284',
},
    'key66871': 'value21112',
    'key52713': 'value23228',
    'key68495': 'value82021',
    'key75181': 'value43421',
},
    {
    'id': 17527490931764,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Shelley Bennett',
    'address': 'Unit 8362 Box 5979\nDPO AE 72024',
    'text': 'True some single smile right sound. Character measure stand feeling live turn white.\nThird usually drug eight. Lot much scientist my.',
    'email': 'dmedina@example.org',
    'phone_number': '+1-494-284-4989x264',
    'json': {
    'name': 'Aaron Brady',
    'address': '3432 Jacobs Falls Suite 384\nBrownshire, AK 44637',
},
    'key73074': 'value41139',
    'key95319': 'value26418',
    'key26150': 'value43154',
},
    {
    'id': 17527490931773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Belinda Kennedy',
    'address': '81741 Jordan Lodge\nWest Ruth, DE 21012',
    'text': 'Point energy history group. Place mean start military whole.\nNor near positive with. Base reflect data over plan evening. Statement various shake cost mouth address.',
    'email': 'xgarcia@example.com',
    'phone_number': '+1-954-318-5163x46899',
    'json': {
    'name': 'Wanda Fitzpatrick',
    'address': '919 Edwards Spring\nNew Ericside, OR 37645',
},
    'key83045': 'value35331',
    'key54643': 'value82552',
    'key93132': 'value68305',
    'key25607': 'value14010',
    'key23849': 'value94500',
},
    {
    'id': 17527490931784,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'William Mason',
    'address': '082 Sanders Underpass Apt. 899\nFarrellbury, WY 17112',
    'text': 'Peace condition home word. Place pass study keep there face player. In the any begin poor guess. Half available six start.',
    'email': 'jamesfleming@example.com',
    'phone_number': '+1-872-801-7949x33409',
    'json': {
    'name': 'Carlos Thompson',
    'address': 'PSC 1462, Box 1736\nAPO AA 26532',
},
    'key99720': 'value20460',
    'key45096': 'value43875',
    'key92499': 'value11789',
    'key95778': 'value86355',
},
    {
    'id': 17527490931794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Paul Maddox',
    'address': '233 Robert Grove\nSalasmouth, AS 66824',
    'text': 'See network language.\nRepresent professor specific show young attorney.\nBase another show. Area evening rule usually. Single strategy now meeting as notice space.',
    'email': 'mlong@example.com',
    'phone_number': '(519)312-3430',
    'json': {
    'name': 'Heather Young',
    'address': '646 Brown Village Apt. 048\nEast Jaimetown, ID 90540',
},
    'key93316': 'value41969',
    'key73406': 'value98448',
    'key16016': 'value2839',
    'key41893': 'value10270',
    'key95938': 'value68534',
    'key17628': 'value46088',
},
    {
    'id': 17527490931804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Brianna Miller',
    'address': '244 David Fall\nLake Anitachester, WV 16527',
    'text': 'Impact economy doctor eat quickly experience. Performance resource he.\nAvailable total science join bar five reason. Remain fly usually if land. All grow class.',
    'email': 'jennifer05@example.net',
    'phone_number': '442-395-2500',
    'json': {
    'name': 'Thomas Lopez',
    'address': '26540 Rachael Point\nFergusonfort, ND 49718',
},
    'key20297': 'value2271',
    'key49034': 'value65630',
},
    {
    'id': 17527490931814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Shannon Walker',
    'address': '25410 Raymond Springs Apt. 503\nEileenmouth, OH 12726',
    'text': 'Officer view even bring hold tell miss. Ok star hold boy heavy foreign campaign. Music story small food idea.',
    'email': 'juan95@example.net',
    'phone_number': '639.375.1999',
    'json': {
    'name': 'Andrew Craig',
    'address': '1545 Barker Keys\nCohenhaven, AL 06049',
},
    'key42407': 'value72943',
},
    {
    'id': 17527490931824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'William Werner',
    'address': '995 Jerry Vista Apt. 005\nNorth Michael, PA 42630',
    'text': 'Pick word bring message future rule myself property. Quickly system month customer. Teacher woman why effort money behavior.',
    'email': 'grahamdanielle@example.com',
    'phone_number': '509-341-7097x3576',
    'json': {
    'name': 'Jeremy Gray',
    'address': '716 Thomas Station\nWest Stacie, MH 64096',
},
    'key68792': 'value69876',
    'key84344': 'value16534',
    'key97939': 'value11662',
},
    {
    'id': 17527490931835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Andrew Rhodes',
    'address': '1494 Stewart Highway Suite 419\nNorth Morganside, SC 41030',
    'text': 'Glass order behind management. Easy win artist response customer official sure.\nStore see data weight way himself. Congress wonder assume make vote something office position.',
    'email': 'spencelisa@example.org',
    'phone_number': '826.685.4019x4589',
    'json': {
    'name': 'Jeffrey Walker',
    'address': '374 Jacob Mountains Apt. 145\nWest David, VI 23623',
},
    'key55979': 'value58706',
    'key59582': 'value69429',
    'key22956': 'value41051',
    'key25892': 'value30059',
    'key71202': 'value11200',
},
    {
    'id': 17527490931847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Brett Kelley',
    'address': '42245 James Ways\nMadisonfort, MA 20581',
    'text': 'Answer why first cell. Blue street contain toward hand put.',
    'email': 'hrios@example.org',
    'phone_number': '+1-920-241-2563',
    'json': {
    'name': 'George Thompson',
    'address': '817 Edward Spur Apt. 684\nNew Dennisville, MT 47528',
},
    'key40008': 'value90625',
    'key852': 'value30112',
    'key98090': 'value49047',
},
    {
    'id': 17527490931856,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Jennifer Bruce',
    'address': 'Unit 8180 Box 7800\nDPO AE 99115',
    'text': 'Until develop deal. Appear three company decide. Decide analysis own maybe identify.\nPaper enough tell but. Off analysis much identify rule hospital.',
    'email': 'vkelly@example.com',
    'phone_number': '662.866.6105x30401',
    'json': {
    'name': 'Kevin Hines',
    'address': '1436 Sullivan Port Apt. 318\nMurrayton, MH 30749',
},
    'key17274': 'value56844',
    'key89179': 'value85740',
    'key71491': 'value79164',
    'key25980': 'value67732',
    'key62379': 'value19335',
    'key85385': 'value12158',
    'key31725': 'value26455',
},
    {
    'id': 17527490931865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Hayley Brooks',
    'address': '42607 Wolf Streets\nDannyborough, MD 62940',
    'text': 'Since become force go guy. Relate player somebody life happy by.\nOften plant world recently treat expect. Industry that art seem service tax service.',
    'email': 'jgutierrez@example.com',
    'phone_number': '2914427225',
    'json': {
    'name': 'Luke Shields',
    'address': '955 Michaela Motorway Apt. 824\nVegahaven, ND 05690',
},
    'key19773': 'value13822',
    'key89203': 'value68807',
},
    {
    'id': 17527490931876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Rachel Brown',
    'address': 'USNV Johnson\nFPO AP 04148',
    'text': 'Deal minute cover look story. Card issue actually letter drug century significant.\nSection type simple. Piece raise remain pattern quite even day high.',
    'email': 'laura22@example.com',
    'phone_number': '309-461-9652',
    'json': {
    'name': 'Steven Edwards',
    'address': '5761 Rivera Parkway\nRichardsbury, NM 12160',
},
    'key51100': 'value50746',
},
    {
    'id': 17527490931886,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'David Patterson',
    'address': '49288 Jordan Knolls Suite 843\nMerrittton, AL 31667',
    'text': 'Room total from. Speak sister when best. Describe rich take most animal.\nIndustry board program. Common thought whatever imagine leave. She player management key place cultural try.',
    'email': 'leslie32@example.org',
    'phone_number': '(850)699-4030',
    'json': {
    'name': 'Matthew Anderson',
    'address': '0917 Warren Square\nSarabury, NY 76616',
},
    'key51652': 'value3930',
    'key45786': 'value2566',
    'key23061': 'value5585',
},
    {
    'id': 17527490931897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Richard Perez',
    'address': 'PSC 9928, Box 1177\nAPO AP 69202',
    'text': 'Family argue or what. Participant east adult himself never environment would.',
    'email': 'normanbrittany@example.org',
    'phone_number': '450.796.1378',
    'json': {
    'name': 'Elizabeth Mcmahon',
    'address': '6193 Greene Plains\nGomezmouth, AZ 92855',
},
    'key20946': 'value697',
    'key48501': 'value36648',
    'key8500': 'value60650',
    'key15207': 'value18961',
    'key70398': 'value57821',
    'key93695': 'value28723',
    'key21065': 'value25438',
    'key90735': 'value25207',
    'key45071': 'value57289',
},
    {
    'id': 17527490931906,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Miss Amy Hopkins',
    'address': '7268 Foley Neck\nPort Jonathanbury, SC 62247',
    'text': 'Focus onto discover film how.\nFight should trade employee discussion. Fill blue bill meeting maybe gun eye. Town would financial war team eye someone.\nWithout rather bed edge manage happy eye.',
    'email': 'bobchavez@example.net',
    'phone_number': '001-261-311-5683x0083',
    'json': {
    'name': 'Julie Walters',
    'address': '25690 Anderson Parkway Apt. 649\nMcdowellfort, TX 17880',
},
    'key15627': 'value39525',
    'key99746': 'value7155',
    'key57800': 'value22507',
    'key68114': 'value87404',
    'key44892': 'value56473',
    'key91124': 'value72214',
    'key19328': 'value78316',
    'key16643': 'value67113',
    'key29747': 'value82531',
    'key13805': 'value55638',
},
    {
    'id': 17527490931918,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Jessica Reed',
    'address': '063 Garrett Walk\nRussellburgh, FM 00988',
    'text': 'Yet not answer society interesting.\nMention sure might next surface break how. Just hard interest but. Listen ready for plan hundred.',
    'email': 'carolwalters@example.net',
    'phone_number': '504-232-1144x5360',
    'json': {
    'name': 'Justin Johnson',
    'address': '0181 Christine Bypass Apt. 136\nSouth Christinachester, TX 73408',
},
    'key81748': 'value75642',
    'key23281': 'value5946',
    'key6363': 'value89907',
    'key63390': 'value34811',
    'key95282': 'value81221',
    'key11574': 'value59236',
    'key14790': 'value92400',
    'key73300': 'value81623',
    'key972': 'value96141',
},
    {
    'id': 17527490931930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Gloria Webb',
    'address': '394 Bryant Gateway\nHeatherhaven, AZ 25077',
    'text': 'Act land training sign radio after age. Rise it measure himself today quality character.\nCurrent describe away house. Or there pick bit structure. Kind property policy direction term.',
    'email': 'agraves@example.org',
    'phone_number': '+1-827-679-4130',
    'json': {
    'name': 'Amanda Blevins',
    'address': '6049 Castro Loop\nLake Miranda, WY 81778',
},
    'key38161': 'value64918',
    'key76941': 'value58987',
    'key94102': 'value32813',
    'key80137': 'value67979',
    'key70053': 'value18773',
    'key84325': 'value64919',
    'key74576': 'value14002',
},
    {
    'id': 17527490931940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Christopher Swanson',
    'address': '02096 Perez Estates\nMejiaberg, ID 11293',
    'text': 'Myself follow rate drive student money nice. Into get hotel glass tend agent.\nAdult office student easy record. Audience middle this candidate different federal.',
    'email': 'christine80@example.com',
    'phone_number': '218.237.4174',
    'json': {
    'name': 'Cynthia Williams',
    'address': '5711 David Station Suite 906\nSuzannechester, VA 17182',
},
    'key14111': 'value36100',
    'key15652': 'value73648',
    'key10945': 'value14428',
    'key56445': 'value23089',
    'key14841': 'value87716',
    'key91680': 'value64482',
    'key63194': 'value36078',
    'key84164': 'value44048',
},
    {
    'id': 17527490931951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Denise Klein',
    'address': '84922 Lopez Avenue Apt. 337\nEast Hollyberg, AR 49352',
    'text': 'A probably audience people skin improve. Yet follow reveal focus base.\nKid institution administration bed reality next case protect. Fear family himself.',
    'email': 'lopezlauren@example.net',
    'phone_number': '(707)655-8217x05210',
    'json': {
    'name': 'Anthony Pearson',
    'address': 'USNV Brown\nFPO AA 47220',
},
    'key34024': 'value90796',
    'key38800': 'value60918',
    'key74318': 'value70286',
    'key21709': 'value26228',
    'key35952': 'value34628',
    'key63416': 'value90649',
},
    {
    'id': 17527490931962,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Anthony Wiley',
    'address': '20083 Robinson Course Suite 004\nLake Julia, CT 68179',
    'text': 'Wrong action score director. Happen above energy minute really.\nGrowth it trade miss five base these effect. Budget development probably pretty reveal child.',
    'email': 'aliciaromero@example.org',
    'phone_number': '253.977.2173',
    'json': {
    'name': 'Terry Pierce',
    'address': '48728 Christian Parks Suite 641\nBrownborough, GU 53065',
},
    'key38079': 'value98816',
    'key14574': 'value22223',
    'key44664': 'value63835',
    'key19968': 'value22192',
    'key26553': 'value22050',
    'key68558': 'value52344',
    'key8626': 'value99479',
    'key40472': 'value42060',
},
    {
    'id': 17527490931974,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Ebony Carrillo',
    'address': '5091 Murphy Mountains Suite 229\nLake Earlview, KS 93136',
    'text': 'Alone these three agency century lead. Challenge sort important raise. Create ahead letter social care security hold.',
    'email': 'fernandezjames@example.com',
    'phone_number': '(807)653-8104x7627',
    'json': {
    'name': 'Kyle Davis',
    'address': '550 Shawn Rue\nSmithshire, NJ 31130',
},
    'key15634': 'value58214',
    'key51723': 'value54384',
    'key76662': 'value22710',
    'key41153': 'value83164',
    'key31012': 'value67101',
    'key431': 'value96662',
    'key38534': 'value43348',
    'key75834': 'value22226',
},
    {
    'id': 17527490931985,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Steven Rosales',
    'address': '6836 White Neck Apt. 889\nCindychester, NJ 43981',
    'text': 'Wide assume easy respond. Audience listen under especially tonight. Answer commercial moment idea focus mean few task.',
    'email': 'haastimothy@example.net',
    'phone_number': '844-441-4866x9622',
    'json': {
    'name': 'Mr. Brandon Strong',
    'address': '76002 Lopez Place Apt. 705\nJuanstad, SC 20393',
},
    'key8840': 'value49719',
    'key29143': 'value5768',
    'key50375': 'value91925',
    'key28445': 'value45974',
    'key18328': 'value12380',
    'key20090': 'value22511',
    'key47364': 'value63177',
    'key20307': 'value8462',
    'key60794': 'value21267',
},
    {
    'id': 17527490931997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Steven Lee',
    'address': '14524 Kristen Lane Apt. 154\nRyanfurt, VA 94965',
    'text': 'Charge civil thought like keep fine. Child mission other discussion mouth pretty author. Number whether scientist east relate.',
    'email': 'larsonnicole@example.com',
    'phone_number': '480-398-2073',
    'json': {
    'name': 'John Smith',
    'address': '73363 Cox Island Suite 246\nMichaelview, UT 62586',
},
    'key79577': 'value76088',
    'key36846': 'value78600',
    'key29235': 'value93613',
    'key26421': 'value37892',
    'key80985': 'value12887',
    'key35360': 'value56000',
    'key46492': 'value17541',
    'key75666': 'value86009',
    'key83172': 'value2744',
    'key38169': 'value2403',
},
    {
    'id': 17527490932009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Miss Hannah Jackson DDS',
    'address': '773 Alexander Ramp Apt. 278\nJamieberg, OK 48721',
    'text': 'Fall late investment item exactly significant. Under spend paper represent loss figure. Sea matter yard high change little positive.',
    'email': 'turnerthomas@example.com',
    'phone_number': '(951)223-7700x5957',
    'json': {
    'name': 'Kimberly Reynolds',
    'address': 'PSC 5426, Box 4388\nAPO AE 31790',
},
    'key19232': 'value9389',
    'key17615': 'value93663',
    'key33872': 'value39136',
    'key36636': 'value54411',
},
    {
    'id': 17527490932019,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Michelle Reese',
    'address': 'Unit 5770 Box 8582\nDPO AP 71568',
    'text': 'Specific senior very prevent. Who of dog such have be indicate deal. Heavy school condition movement.',
    'email': 'wschultz@example.org',
    'phone_number': '419-959-7441',
    'json': {
    'name': 'Paul Kelly',
    'address': '303 Caitlin Spring Suite 676\nTurnerland, RI 81615',
},
    'key77356': 'value98755',
    'key22814': 'value75045',
    'key75285': 'value68094',
    'key90890': 'value36687',
    'key41766': 'value59684',
    'key30959': 'value79665',
    'key18521': 'value84867',
    'key42537': 'value16940',
},
    {
    'id': 17527490932027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Randy Buchanan',
    'address': '8679 Jason Branch Suite 763\nSouth Jonathanshire, TX 76121',
    'text': 'Night could who direction real clearly paper. Face gun enjoy live opportunity executive break.\nWestern trip and space environment avoid city thing. Concern front still woman too accept speak attack.',
    'email': 'jackson93@example.net',
    'phone_number': '(403)529-0682',
    'json': {
    'name': 'Christopher Cruz',
    'address': '16010 Booth Row Suite 037\nEast Scott, WA 78334',
},
    'key39219': 'value94389',
    'key65823': 'value68741',
    'key90229': 'value99084',
    'key99599': 'value94101',
},
    {
    'id': 17527490932037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Andrea Vega',
    'address': '817 Bryant Port\nLake Nicole, LA 33164',
    'text': 'Feel travel wind professional car claim. Growth since performance account apply. Approach name management fact among follow exactly.\nExactly yeah while difficult. Take society student hard.',
    'email': 'brittany59@example.com',
    'phone_number': '+1-618-910-0611x82145',
    'json': {
    'name': 'Zachary Spencer',
    'address': '382 Baker Fort Suite 588\nHoffmanton, WY 75669',
},
    'key22099': 'value12560',
    'key62267': 'value32211',
    'key38119': 'value78634',
    'key23165': 'value19233',
    'key49575': 'value57953',
    'key1334': 'value52540',
},
    {
    'id': 17527490932048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Allen Moran',
    'address': '70556 Sutton Glens Apt. 471\nWest Michaelberg, IA 88917',
    'text': 'Ready compare increase daughter. Inside turn position democratic edge. Easy institution news ok my entire always to.',
    'email': 'toddgray@example.com',
    'phone_number': '001-284-713-2878',
    'json': {
    'name': 'Ricardo Martinez',
    'address': '2341 Shannon Parks Apt. 404\nMelissashire, OR 57342',
},
    'key9751': 'value78889',
    'key50062': 'value74999',
    'key55617': 'value56010',
    'key35223': 'value18467',
    'key89658': 'value14190',
},
    {
    'id': 17527490932060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Ryan Smith',
    'address': 'Unit 6576 Box 1141\nDPO AP 48431',
    'text': 'Body eight activity occur bring. Information own final meeting human new evening. Scene religious type agent tend service.\nResearch economic fast can factor time job. Near create physical speech.',
    'email': 'vdowns@example.net',
    'phone_number': '363.551.4766x58951',
    'json': {
    'name': 'Elizabeth Coleman',
    'address': '673 Justin Spurs\nWilliamchester, WA 42027',
},
    'key96728': 'value90417',
    'key15321': 'value38703',
    'key51575': 'value1154',
    'key57977': 'value63101',
    'key25290': 'value74193',
    'key10027': 'value77496',
    'key18794': 'value37623',
    'key29680': 'value71263',
    'key35574': 'value67273',
},
    {
    'id': 17527490932068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Christian Proctor',
    'address': '592 Amanda Plaza\nWest William, MA 13917',
    'text': 'Road new ever.\nEye in fly positive. Newspaper end maybe worry concern beyond.\nOffer special exactly quality because to. Hand power message energy citizen.',
    'email': 'umartin@example.net',
    'phone_number': '6127951212',
    'json': {
    'name': 'Jamie Smith',
    'address': '384 Robert Mission Suite 804\nWest Derrickberg, PA 99677',
},
    'key41352': 'value73774',
    'key23593': 'value40034',
    'key78074': 'value63871',
    'key59193': 'value59585',
    'key38802': 'value28701',
    'key24482': 'value55523',
    'key76663': 'value75147',
},
    {
    'id': 17527490932079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Jeremy Patterson',
    'address': '228 Holt Trace\nPort Christinaville, NY 99838',
    'text': 'Example around industry study center serious. Method church close hold feel expert.',
    'email': 'frank39@example.net',
    'phone_number': '(748)678-7916x2552',
    'json': {
    'name': 'Paul Walter',
    'address': '9642 Hunter Crossroad\nNew Davidfurt, CT 53271',
},
    'key36883': 'value63085',
    'key86451': 'value33446',
    'key69110': 'value26163',
    'key85434': 'value74267',
    'key12280': 'value50075',
    'key27805': 'value74630',
    'key87935': 'value79655',
    'key70793': 'value51582',
    'key56057': 'value3224',
    'key31129': 'value31992',
},
    {
    'id': 17527490932089,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Deborah Jefferson',
    'address': '088 Carney Manors\nNew Jenna, NE 19554',
    'text': 'Front stage part store enough thousand fine prepare. Imagine short suddenly job mean board side. Be pressure wide under list magazine at.',
    'email': 'michellenewton@example.org',
    'phone_number': '001-929-384-4714x006',
    'json': {
    'name': 'Andrew Jones',
    'address': '6100 David Trail Suite 722\nStephenhaven, IL 39685',
},
    'key26437': 'value37979',
    'key91450': 'value55451',
    'key92646': 'value28427',
    'key13507': 'value83874',
    'key19866': 'value15201',
    'key37215': 'value56057',
    'key49449': 'value57440',
    'key13919': 'value27469',
},
    {
    'id': 17527490932100,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Amy Mathis',
    'address': '3239 Heather Estate Suite 289\nJacksonchester, IN 83796',
    'text': 'Recognize capital eight evidence. Their white medical movement month clearly establish pattern. Note before even agreement television.',
    'email': 'larryphillips@example.com',
    'phone_number': '(770)589-5955x8924',
    'json': {
    'name': 'Julie Wilson',
    'address': '81456 Samuel Flats\nBurgessborough, MP 08853',
},
    'key21123': 'value58112',
    'key29876': 'value56281',
    'key10745': 'value43109',
    'key92479': 'value93086',
    'key10211': 'value42601',
    'key17927': 'value75500',
    'key23713': 'value11171',
    'key71709': 'value11784',
},
    {
    'id': 17527490932112,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Dale Moore',
    'address': '4345 Elizabeth Summit\nSouth Jacobmouth, NE 50123',
    'text': 'Bed apply tonight understand green in nearly throw. Pattern family impact deep evidence visit. Common thus clearly majority seek bit wall method. Figure town because care item table.',
    'email': 'sheila57@example.net',
    'phone_number': '001-274-461-5074',
    'json': {
    'name': 'David Morgan',
    'address': '031 Traci Key\nRosshaven, NV 37768',
},
    'key95607': 'value87611',
    'key78664': 'value51203',
    'key84240': 'value28810',
    'key39451': 'value30630',
    'key82098': 'value4516',
    'key69996': 'value57855',
    'key72496': 'value5664',
    'key74687': 'value68365',
    'key55094': 'value83347',
    'key53340': 'value94157',
},
    {
    'id': 17527490932122,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Karen Turner',
    'address': '5169 Nathan Tunnel\nCastrofurt, RI 40880',
    'text': 'Son want industry key inside should note.\nActivity road life make eat. Size morning you rise rather.\nEight way high computer word into support fly. Term bill change show case ready discover.',
    'email': 'hughescourtney@example.org',
    'phone_number': '(275)779-6542',
    'json': {
    'name': 'Grant Garcia',
    'address': '8951 Hudson Viaduct Suite 139\nNicholaschester, WI 77067',
},
    'key62167': 'value37795',
    'key95306': 'value66168',
    'key63213': 'value86339',
},
    {
    'id': 17527490932133,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Penny Edwards',
    'address': '88260 Gail Mountain\nEdwardchester, IN 39041',
    'text': 'Will leader career section hospital. Across threat later everything discover. Eat year low natural decide close protect.',
    'email': 'sean14@example.com',
    'phone_number': '913-658-1186x239',
    'json': {
    'name': 'Crystal Hawkins',
    'address': '11174 Jacob Curve Apt. 310\nArianaberg, MD 79907',
},
    'key43181': 'value75912',
    'key99367': 'value89540',
    'key51213': 'value80712',
    'key37307': 'value83521',
    'key41039': 'value16509',
    'key45917': 'value88485',
    'key35778': 'value66377',
    'key45534': 'value55816',
},
    {
    'id': 17527490932143,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Leslie Allen',
    'address': '6256 Alan Via\nLauramouth, GA 35681',
    'text': 'Month reach into. Policy on decade role leader term anyone officer. Glass stock occur movie truth.',
    'email': 'dustin56@example.net',
    'phone_number': '4245513661',
    'json': {
    'name': 'Stephanie Jones',
    'address': '41809 Shirley Meadows Apt. 907\nEast Jennifertown, NC 15185',
},
    'key98109': 'value16897',
    'key61841': 'value33028',
    'key15035': 'value59364',
    'key63631': 'value45164',
    'key96829': 'value79303',
},
    {
    'id': 17527490932153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Robert Holmes',
    'address': '025 Gomez Cape\nPort Laura, OR 38381',
    'text': 'Finally meet power. Happy agent type like full picture.\nMean among thing these bar cost. Admit course financial grow special eye skin. Property field finally finally inside ten.',
    'email': 'catherine53@example.com',
    'phone_number': '001-320-676-4041x828',
    'json': {
    'name': 'John Hardy',
    'address': '0899 Hammond Lane Suite 922\nPort Denise, NJ 56539',
},
    'key20994': 'value48923',
    'key88895': 'value60317',
    'key55575': 'value58649',
    'key85479': 'value47029',
    'key46051': 'value74380',
    'key40044': 'value89539',
    'key83466': 'value93720',
},
    {
    'id': 17527490932164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Marcus Collins Jr.',
    'address': '865 Allen Green Suite 779\nBrowningland, MA 36470',
    'text': 'Miss people that almost film PM every. Town whom number ball Congress artist mission. Particular once song start industry affect factor.',
    'email': 'mosesdiane@example.com',
    'phone_number': '877.286.9491x53572',
    'json': {
    'name': 'Lisa Barr',
    'address': '58131 Martinez Summit Suite 891\nKeithburgh, HI 05043',
},
    'key7352': 'value44220',
    'key16173': 'value78287',
    'key34346': 'value58211',
    'key35491': 'value99689',
    'key67764': 'value71535',
},
    {
    'id': 17527490932175,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Rhonda Campbell',
    'address': '35590 Wood Pass\nEast Feliciaview, ND 44324',
    'text': 'You woman author remain usually chair. Real seem live dog figure. Beat one free yeah interesting support.',
    'email': 'parkerrivera@example.com',
    'phone_number': '(951)476-7496x10561',
    'json': {
    'name': 'Charles Taylor',
    'address': '8311 Gregory Common Suite 639\nWest Gregoryfort, VT 79108',
},
    'key13416': 'value20948',
    'key51721': 'value82145',
    'key63528': 'value29681',
    'key39242': 'value40401',
    'key42953': 'value52317',
    'key21101': 'value21738',
    'key83788': 'value47914',
},
    {
    'id': 17527490932187,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Jessica Glover',
    'address': '635 Russell Drives\nKatherinefurt, OR 64212',
    'text': 'Various personal camera score kitchen. Possible entire peace.\nFederal smile computer Democrat economy so. Drive adult pretty water base lose.',
    'email': 'brian69@example.com',
    'phone_number': '929.846.0222x573',
    'json': {
    'name': 'Shannon Hickman',
    'address': '86347 Casey Parkways\nEast Saraberg, MA 83325',
},
    'key91194': 'value86622',
    'key37351': 'value32228',
    'key88343': 'value50912',
    'key49164': 'value3486',
    'key23956': 'value61183',
},
    {
    'id': 17527490932197,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Adam Jackson',
    'address': '54192 Nixon Radial\nEast Richardville, ID 53651',
    'text': 'Interesting pull serious then adult enough relationship themselves.\nTelevision must bed statement better would song. Thing design democratic until five fact identify admit.',
    'email': 'taylortanner@example.org',
    'phone_number': '705-425-3156x986',
    'json': {
    'name': 'Laura Hernandez',
    'address': '00662 Todd Fork\nHardinview, GA 15772',
},
    'key64713': 'value37134',
    'key97975': 'value12966',
    'key23833': 'value39703',
    'key17607': 'value87150',
    'key87627': 'value53286',
    'key39590': 'value50343',
},
    {
    'id': 17527490932208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Carol Reed',
    'address': '880 Justin Radial Apt. 577\nEast Vanessachester, VA 95351',
    'text': 'Officer industry management record song. Serve instead call late late.\nProve exactly recently measure. Under process keep stay night security. Join none area owner language especially suggest.',
    'email': 'ntaylor@example.net',
    'phone_number': '283-294-3721',
    'json': {
    'name': 'Samantha Lee',
    'address': '904 Bryan Village\nNew Brian, MT 03945',
},
    'key71886': 'value50447',
    'key3284': 'value54272',
    'key60272': 'value91751',
    'key66600': 'value15438',
    'key54328': 'value6335',
    'key91384': 'value23825',
    'key53882': 'value73925',
    'key38080': 'value14019',
    'key31900': 'value89736',
    'key17402': 'value68144',
},
    {
    'id': 17527490932219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Abigail Deleon',
    'address': '428 Jessica Trace Suite 826\nPort Veronicaville, MI 40525',
    'text': 'Stock news per goal agency product animal. Your condition pattern. Man life age physical sport weight.',
    'email': 'barryphillip@example.org',
    'phone_number': '+1-916-984-1239x749',
    'json': {
    'name': 'Craig Tucker',
    'address': '898 Kathy Rue\nLaurentown, LA 14820',
},
    'key86062': 'value96609',
    'key61416': 'value337',
    'key69429': 'value70815',
    'key27130': 'value22774',
    'key94691': 'value68242',
    'key81996': 'value11567',
    'key42916': 'value87052',
    'key21386': 'value86307',
},
    {
    'id': 17527490932230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Brandon Fox',
    'address': '0024 Christy Avenue\nEast Mariaville, MH 19113',
    'text': 'Now on interest stage. Health kid also statement ready. Boy area memory phone imagine even.\nCongress would quite. Dinner daughter policy source whole half.',
    'email': 'kcurtis@example.net',
    'phone_number': '6083170621',
    'json': {
    'name': 'Christopher Holmes',
    'address': '488 Glenda Inlet Suite 018\nKelseytown, HI 96130',
},
    'key74410': 'value79188',
},
    {
    'id': 17527490932240,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Mark Shaw',
    'address': '83759 Vargas Ridge\nEast Paultown, OH 87795',
    'text': 'Improve always wait nor care. Share save crime likely. Anything image include hair bring next. Cup six arrive relationship.',
    'email': 'jthornton@example.net',
    'phone_number': '633-669-9341',
    'json': {
    'name': 'Mr. Ronald Lam Jr.',
    'address': 'PSC 7139, Box 5212\nAPO AE 10888',
},
    'key247': 'value50082',
    'key5210': 'value69261',
    'key95622': 'value77964',
    'key12494': 'value62220',
    'key61438': 'value31741',
},
    {
    'id': 17527490932249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Audrey Ross',
    'address': '5457 Howard Plain\nEast Jessica, PW 47294',
    'text': 'Piece condition society attention animal modern. Sign college bar start. Maintain four result.\nAct business yeah every part growth. First notice official six beat with order step. Figure on real.',
    'email': 'jamesjacob@example.net',
    'phone_number': '+1-855-694-1379x11414',
    'json': {
    'name': 'Amy Hansen',
    'address': 'Unit 2037 Box 2311\nDPO AA 59407',
},
    'key59725': 'value45043',
},
    {
    'id': 17527490932259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Brian Hartman',
    'address': '44441 Diane Pass\nWest Kevin, IL 09336',
    'text': 'It continue itself job. Scene section enough relationship lose generation government lot.\nMeasure create three bed spend enjoy agreement. Final mother federal.',
    'email': 'aglover@example.org',
    'phone_number': '588-433-2860x406',
    'json': {
    'name': 'Charles Cooper',
    'address': '233 Nichols Key\nWest Peter, VA 48084',
},
    'key32737': 'value77375',
    'key2052': 'value13605',
    'key38020': 'value60349',
    'key85947': 'value63642',
    'key26709': 'value41073',
    'key3969': 'value15379',
    'key21659': 'value31055',
    'key29805': 'value61685',
    'key39304': 'value86078',
    'key18430': 'value52575',
},
    {
    'id': 17527490932269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Jeffrey Smith',
    'address': '57188 Vincent Spurs\nEast Martin, CO 64132',
    'text': 'Week support tonight give.\nWatch if method industry prepare. Involve Mr stuff the wait side help. Or western indicate base. Painting risk picture attack chance.\nYes media under.',
    'email': 'david96@example.com',
    'phone_number': '+1-579-762-9393x429',
    'json': {
    'name': 'Richard Smith',
    'address': '442 Elizabeth Plains Apt. 434\nWest Ashley, AK 56700',
},
    'key44172': 'value69274',
},
    {
    'id': 17527490932291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Melissa Schneider',
    'address': '202 David Brook\nDeniseton, AK 25487',
    'text': 'Hotel happen certain real other follow. Outside season notice use paper blue laugh.\nMight one like natural cause according. Medical year despite measure tough plan.',
    'email': 'william14@example.com',
    'phone_number': '795-958-8114x191',
    'json': {
    'name': 'Emily Brown',
    'address': '52050 Shepherd Ville\nEast Paul, NM 03724',
},
    'key31635': 'value78321',
    'key5605': 'value63351',
    'key38737': 'value22717',
},
    {
    'id': 17527490932302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Dana Austin',
    'address': '34685 Blake Squares Apt. 107\nLake Heatherfurt, LA 45701',
    'text': 'Information analysis cause property. Have participant fall time discussion receive score.',
    'email': 'schultzvincent@example.org',
    'phone_number': '931.840.1058x2031',
    'json': {
    'name': 'Patrick Carlson',
    'address': '24222 Anthony Island\nFischerstad, PR 05901',
},
    'key37155': 'value60422',
    'key12218': 'value18458',
    'key51664': 'value81718',
    'key57331': 'value51342',
    'key32557': 'value92250',
    'key76175': 'value14500',
    'key39943': 'value22597',
    'key33163': 'value77863',
    'key43798': 'value76422',
},
    {
    'id': 17527490932314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Mary Weaver',
    'address': '6224 Fuller Port Suite 228\nRamirezton, MA 57006',
    'text': 'Television know position all. Take determine church memory.\nAffect even form movie quite total bank seat. Ball lose be manager list responsibility seem. Reach draw large laugh while father.',
    'email': 'robertmiller@example.org',
    'phone_number': '(964)875-5863x7112',
    'json': {
    'name': 'Steven Turner',
    'address': 'PSC 2538, Box 9244\nAPO AP 23923',
},
    'key10880': 'value26332',
    'key69349': 'value25781',
    'key69283': 'value11423',
    'key10501': 'value75493',
    'key87654': 'value51935',
    'key50900': 'value94435',
},
    {
    'id': 17527490932325,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'William Morgan',
    'address': '84534 Sanchez Islands\nCalhountown, AR 97238',
    'text': 'Spend education build film set chance traditional. Wonder positive reduce appear performance your just. Still room side. East me above success nice Democrat see knowledge.',
    'email': 'thomas61@example.com',
    'phone_number': '3697725318',
    'json': {
    'name': 'Caitlin Thomas',
    'address': '0152 Koch Dam Suite 596\nNormanmouth, NM 33963',
},
    'key6514': 'value99281',
    'key76202': 'value45787',
    'key10920': 'value73151',
    'key98780': 'value36266',
    'key14770': 'value71343',
    'key90883': 'value59327',
    'key65328': 'value42972',
},
    {
    'id': 17527490932336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Patricia Keith',
    'address': '2569 Clayton Lock\nCoryfurt, NC 94118',
    'text': 'Issue lot car person although. Forward dinner bring add week require. Score which fight ready.\nPer paper interview beautiful record save travel.',
    'email': 'stephanie34@example.org',
    'phone_number': '315-203-4328x4310',
    'json': {
    'name': 'Todd Gomez',
    'address': '651 Debra Rue Suite 774\nLoganmouth, GA 67876',
},
    'key20026': 'value38969',
    'key84671': 'value62305',
    'key31545': 'value38150',
    'key76636': 'value74829',
    'key70691': 'value30669',
    'key92324': 'value36012',
    'key77059': 'value16726',
},
    {
    'id': 17527490932347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Charles Washington',
    'address': '35947 Rogers Extensions\nJamesfort, CA 02969',
    'text': 'Course good conference professor. News star simple history. Would various total a simply time.',
    'email': 'justin31@example.com',
    'phone_number': '656.644.8069',
    'json': {
    'name': 'Lori Johnston',
    'address': '1030 White Manors\nEast Jacksonstad, GU 64123',
},
    'key88674': 'value70089',
    'key95249': 'value56572',
},
    {
    'id': 17527490932357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'John Krueger',
    'address': '486 Alex Path\nNorth Rachel, PW 31643',
    'text': 'Hope once take so. Foot gun process fish fact magazine. Water paper leader consumer.\nWe apply fear fill federal hold. Accept community by class. Election bank nearly respond social skin turn.',
    'email': 'smithsuzanne@example.net',
    'phone_number': '5132712293',
    'json': {
    'name': 'Cynthia Hampton',
    'address': '99658 Jamie Prairie Suite 618\nWest Anthony, TN 20329',
},
    'key89082': 'value16858',
    'key86117': 'value59793',
    'key90640': 'value5891',
    'key75850': 'value44922',
    'key13899': 'value78160',
    'key99002': 'value617',
    'key69021': 'value25676',
},
    {
    'id': 17527490932369,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Michael Gray',
    'address': 'Unit 7761 Box 7694\nDPO AE 45226',
    'text': 'News large thus throughout wall offer two.\nAnd machine already certain remain others reveal home. Player loss trade ready or. Green price will whether.',
    'email': 'michaeljohnson@example.net',
    'phone_number': '+1-978-503-7002',
    'json': {
    'name': 'James Mcintosh',
    'address': '02889 Glenn Shore Apt. 856\nMeganburgh, NM 47193',
},
    'key94235': 'value11287',
    'key13598': 'value16602',
    'key43719': 'value84862',
    'key67907': 'value67656',
},
    {
    'id': 17527490932378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Joseph Thompson',
    'address': '1116 Amber Causeway\nPort Steven, AZ 06787',
    'text': 'Scientist clearly TV interview black experience involve participant. Cost hit as successful song. Draw very design must TV news. Program note bed over machine southern seven require.',
    'email': 'marcus73@example.org',
    'phone_number': '(548)719-3155x383',
    'json': {
    'name': 'Gary Miller',
    'address': '01167 Sean Bridge Apt. 179\nWest Ryanside, WA 82278',
},
    'key50345': 'value88922',
    'key89205': 'value68257',
    'key21113': 'value65631',
    'key75991': 'value86595',
    'key5765': 'value86433',
},
    {
    'id': 17527490932388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Gordon Hall',
    'address': '72135 Mays Rapids\nNormanshire, CO 66247',
    'text': 'Green argue wrong become participant condition election himself. Five industry modern policy play charge. If enter reflect responsibility particular late.',
    'email': 'yward@example.com',
    'phone_number': '905-872-0913x0708',
    'json': {
    'name': 'Mrs. Samantha Horton',
    'address': '34301 Grimes Vista Suite 962\nNorth Alexstad, NC 58575',
},
    'key44281': 'value95359',
    'key21809': 'value87841',
    'key56216': 'value27654',
    'key40163': 'value60481',
    'key1063': 'value44347',
    'key38177': 'value41053',
    'key93261': 'value41419',
    'key45969': 'value74620',
},
    {
    'id': 17527490932399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Jason Cook',
    'address': '84955 Hunter Heights Suite 435\nSouth Zacharyfort, WV 59066',
    'text': 'Pm realize this box us drop. Event almost beat such game. Pressure direction only raise along.\nIndicate idea career according group. Shoulder president evening over.',
    'email': 'terrencepeters@example.org',
    'phone_number': '001-461-242-7531x260',
    'json': {
    'name': 'Nathan Contreras',
    'address': '5845 Destiny Corner\nNorth Jennifer, OK 34443',
},
    'key57366': 'value29038',
    'key44244': 'value80607',
    'key84660': 'value32841',
},
    {
    'id': 17527490932411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Jennifer Scott',
    'address': '18209 Tracy Mountain\nPort Vanessaburgh, GA 48673',
    'text': 'Exactly visit single learn. Rate store against subject. Her hospital represent suggest sell everything difficult. Staff thank fear quickly father probably.',
    'email': 'gpatterson@example.org',
    'phone_number': '818-604-9019x015',
    'json': {
    'name': 'Cheryl Scott DVM',
    'address': '219 Russell Stream\nWest Dale, TX 88409',
},
    'key5619': 'value51328',
    'key54764': 'value80740',
    'key79573': 'value2497',
},
    {
    'id': 17527490932421,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Mark George',
    'address': '69434 Natalie Mission\nPort Judy, IN 50857',
    'text': 'Friend performance popular attention. Up long new. Discussion on relationship edge happy memory community.\nInterview bar accept reality score. Life student guy brother.',
    'email': 'stephenrusso@example.net',
    'phone_number': '+1-395-842-9564x138',
    'json': {
    'name': 'John Stephens',
    'address': '114 Morgan Court Apt. 133\nNorth Albertfort, LA 86648',
},
    'key44461': 'value41183',
    'key34389': 'value62928',
},
    {
    'id': 17527490932433,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Joseph Kent',
    'address': '74458 Jon Trail Apt. 900\nNew Sharon, FM 07951',
    'text': 'Crime value skill watch treatment play choice. Green resource manager soldier at step. Build candidate deep sister work hand pull maybe.\nTv ready by. Prevent minute run set.',
    'email': 'kevin03@example.org',
    'phone_number': '(485)754-8590x47390',
    'json': {
    'name': 'William Orr',
    'address': '30982 Stephanie Field\nNorth Pamela, MP 17169',
},
    'key8509': 'value60771',
    'key57648': 'value10552',
},
    {
    'id': 17527490932443,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Elizabeth Rose',
    'address': '715 Allison Route\nNew Christopher, ME 17715',
    'text': 'Community including size wait catch.\nEconomy impact help care build something next. Win soon million poor. Mission hair wind teacher measure.',
    'email': 'debra21@example.net',
    'phone_number': '+1-409-615-1503x65946',
    'json': {
    'name': 'Joanna Adams MD',
    'address': '755 Ball Knoll Apt. 288\nRebeccatown, WI 82258',
},
    'key96893': 'value68404',
    'key10217': 'value33940',
    'key25087': 'value95507',
},
    {
    'id': 17527490932458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Kathryn Phillips',
    'address': '5933 Amanda Dam\nStevemouth, MN 14159',
    'text': 'Scientist pass data authority. House than enough job indeed road office among.',
    'email': 'xwalter@example.org',
    'phone_number': '244-678-4898',
    'json': {
    'name': 'Jessica Preston',
    'address': 'USCGC Campbell\nFPO AP 75495',
},
    'key68887': 'value52394',
    'key74158': 'value63909',
    'key25339': 'value65076',
    'key12923': 'value18359',
    'key1472': 'value35454',
    'key73641': 'value80326',
    'key15188': 'value13029',
    'key91806': 'value14126',
    'key62199': 'value20602',
},
    {
    'id': 17527490932468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Bailey Turner',
    'address': '48922 Tate Burgs Apt. 269\nDavidport, VI 87179',
    'text': 'Cell study model free. Himself design check court. Point tonight building he his special federal.\nCongress suddenly view behavior care fight. Anyone billion various somebody.',
    'email': 'susankelly@example.net',
    'phone_number': '988-338-2475',
    'json': {
    'name': 'Joseph Richards',
    'address': '240 Melissa Forges Suite 219\nNorth Melissafurt, IL 55111',
},
    'key46990': 'value34637',
    'key35877': 'value39259',
    'key78945': 'value11263',
    'key3039': 'value80087',
    'key9305': 'value39044',
    'key74096': 'value83695',
    'key50666': 'value90737',
    'key56536': 'value73868',
    'key36222': 'value33888',
},
    {
    'id': 17527490932479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Lisa Jones',
    'address': '887 Campbell Shore Apt. 005\nShaneside, MN 96206',
    'text': 'Special require great deal. Entire likely opportunity consumer strategy throughout various within.',
    'email': 'mbowman@example.net',
    'phone_number': '(941)929-0950x0337',
    'json': {
    'name': 'Deborah Holmes',
    'address': '30475 Michael Cliff\nNorth Lisa, LA 43805',
},
    'key92009': 'value33228',
    'key61925': 'value85039',
    'key44895': 'value73810',
    'key50913': 'value56689',
    'key44469': 'value64947',
    'key89167': 'value42282',
    'key59234': 'value41893',
    'key33114': 'value13531',
    'key89260': 'value14905',
},
    {
    'id': 17527490932490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Daniel Rios',
    'address': '23996 Johnson Lane Suite 083\nNorth Travis, IA 99243',
    'text': 'Memory sell leave role between. Institution parent plant east eight line. Occur religious traditional off his movement report.\nReveal help tonight movement. Usually or value technology most hair.',
    'email': 'wrobertson@example.net',
    'phone_number': '001-792-397-4010x846',
    'json': {
    'name': 'Manuel Gentry',
    'address': '506 Hall Lakes Apt. 646\nNorth Michaelmouth, DE 74988',
},
    'key21287': 'value22228',
    'key42746': 'value80152',
},
    {
    'id': 17527490932501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Christopher Malone',
    'address': '471 Steele Ridges Suite 562\nNew Andrew, MS 94870',
    'text': 'Type analysis we and different. Water pay off rock white always affect. Certainly service get step second speech.\nInto film offer woman. Instead focus tend either plan guess out.',
    'email': 'kimberly21@example.net',
    'phone_number': '310.252.0837x4877',
    'json': {
    'name': 'Terri Ballard',
    'address': '92489 Keith Road Apt. 864\nTurnerton, KS 26454',
},
    'key39580': 'value51800',
    'key28388': 'value41395',
    'key30989': 'value35454',
    'key47784': 'value74167',
    'key25973': 'value16439',
    'key16823': 'value91901',
    'key65543': 'value61656',
},
    {
    'id': 17527490932512,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Janet Harris',
    'address': '477 Bowen Ramp Suite 058\nEricborough, IA 58805',
    'text': 'Song into certain air cut popular with. Build spend service reduce. Total decision board.\nTheir technology fund whole build.\nHusband exist science manager do art wish than. Personal least daughter.',
    'email': 'hopkinsbryan@example.com',
    'phone_number': '578.632.9467',
    'json': {
    'name': 'Michelle Glass',
    'address': '902 Pace Haven\nSouth Shelley, FM 31114',
},
    'key68359': 'value36830',
    'key66883': 'value41847',
    'key53921': 'value60616',
    'key83759': 'value14500',
    'key94793': 'value94585',
    'key77700': 'value19971',
},
    {
    'id': 17527490932525,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Mr. Brian Johnson DDS',
    'address': '35100 Perkins Springs\nTurnerburgh, IA 89872',
    'text': 'Personal three forget direction positive. Major finally example ball. Would sing house head degree.\nMore finally benefit long piece suffer music. Necessary political remember senior.',
    'email': 'jessicaescobar@example.org',
    'phone_number': '001-833-943-2829x18193',
    'json': {
    'name': 'Angel Sanchez',
    'address': '95374 Collins Locks Suite 540\nEast Andreashire, AR 92446',
},
    'key59984': 'value94808',
    'key61135': 'value58993',
    'key34216': 'value80622',
    'key50199': 'value51828',
    'key16826': 'value83226',
    'key63601': 'value52676',
},
    {
    'id': 17527490932537,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Jonathan Adkins',
    'address': 'USCGC Castillo\nFPO AE 48440',
    'text': 'Box country meet mean point question citizen. Low season energy doctor. Simple film dog inside nearly fight capital.',
    'email': 'xnelson@example.org',
    'phone_number': '(722)314-5368x185',
    'json': {
    'name': 'Austin Figueroa',
    'address': '28392 Ford View Apt. 117\nRobinview, MA 14603',
},
    'key21978': 'value61526',
    'key40644': 'value63889',
},
    {
    'id': 17527490932546,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Marcus Mendoza',
    'address': '905 Mccarthy Flats\nMuellerborough, PW 16844',
    'text': 'Health buy floor rock. Everyone bit among program government story compare. Might southern spend attorney garden season. Dog success probably imagine vote degree around.',
    'email': 'bbrown@example.org',
    'phone_number': '917-573-6081x950',
    'json': {
    'name': 'Kayla Knight',
    'address': '219 Ford Spring\nNew Debra, FL 64339',
},
    'key55495': 'value90933',
    'key25439': 'value6960',
    'key33450': 'value54412',
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
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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
    'filter': 'uid in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199]',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/get"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/get")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/get'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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
    'id': 0,
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
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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
        """测试请求 7 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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



    def test_request_8(self):
        """测试请求 8 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0e985fcc-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_46_970994DxBvQPXV',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestGetVector_test_get_vector_complex[True-True-one]_1752749098.json')
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
    test = AllmilvusLogtestgetvectorTestGetVectorComplexTrueTrueOne1752749098Json()
    test.run_tests()
