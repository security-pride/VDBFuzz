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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752748674_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752748674.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid100AndUid1001752748674Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752748674.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752748674.json"
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
    'RequestId': '110dd8c8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_41_599052RUsVwTVr',
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
    'RequestId': '110dd8c8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_41_599052RUsVwTVr',
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
    'RequestId': '110dd8c8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_41_599052RUsVwTVr',
    'data': [
    {
    'id': 17527486676348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Samantha Burch',
    'address': '3107 Don River Apt. 140\nSamanthaton, AL 62958',
    'text': 'Do field son. East whole during hand occur machine easy.\nCase available reveal know tell itself budget. Reach financial wait floor. Church glass open least.',
    'email': 'boydtoni@example.net',
    'phone_number': '+1-683-722-6731',
    'json': {
    'name': 'Samantha Glenn',
    'address': '07541 Jenkins Stream Suite 396\nLaurentown, SC 79298',
},
    'key23905': 'value11466',
    'key46768': 'value1609',
    'key20626': 'value26167',
    'key6700': 'value56586',
    'key43610': 'value77069',
    'key3235': 'value94519',
    'key29510': 'value33943',
    'key46770': 'value57990',
    'key25483': 'value82786',
    'key68742': 'value77150',
},
    {
    'id': 17527486676366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Mrs. Ashley Garcia',
    'address': '6351 Morris Greens Apt. 845\nNunezhaven, GA 63622',
    'text': 'Involve bank commercial adult direction call born. Future near plan administration old.\nReceive free material discover budget. Process unit story friend night.',
    'email': 'ronnie46@example.org',
    'phone_number': '(704)308-9297x46827',
    'json': {
    'name': 'Kyle Rodriguez',
    'address': 'Unit 5274 Box 6223\nDPO AE 47423',
},
    'key56229': 'value39396',
    'key17454': 'value28762',
    'key16336': 'value32726',
},
    {
    'id': 17527486676378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Julia Parker MD',
    'address': '062 Mitchell Throughway\nKarenmouth, NM 14425',
    'text': 'During here trial rock act join recently open. Skin watch a sing.\nOld friend lose company painting beyond. Else relationship heavy any.',
    'email': 'brendamora@example.net',
    'phone_number': '586.228.5633',
    'json': {
    'name': 'Joshua Murphy',
    'address': '99954 Sparks Village Apt. 200\nEast Teresaberg, FL 30238',
},
    'key9258': 'value79158',
    'key80426': 'value45058',
    'key55736': 'value33180',
    'key56378': 'value42199',
    'key27938': 'value3956',
    'key5844': 'value30451',
},
    {
    'id': 17527486676392,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Samuel Lin',
    'address': '2934 Pace Inlet Suite 262\nCampbellside, HI 26634',
    'text': 'Travel end amount parent. Loss part give father simple. Owner thus so work small four.\nHis hit style she current why. Particular compare theory fire environment southern affect.',
    'email': 'oscarroberts@example.com',
    'phone_number': '456-415-4596x1577',
    'json': {
    'name': 'Ronald Clark',
    'address': 'Unit 6902 Box 3751\nDPO AE 97220',
},
    'key30382': 'value24936',
    'key52255': 'value92680',
    'key17789': 'value90904',
    'key27448': 'value43154',
    'key61504': 'value78397',
    'key55634': 'value60268',
    'key50148': 'value34652',
},
    {
    'id': 17527486676405,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Stephanie Lopez',
    'address': '65586 Castillo Ramp Suite 597\nPatriciamouth, MP 61532',
    'text': 'Store light player program follow. Put activity another woman message.\nYes national force base. System spring design method.\nData bank us three look every. Employee century ahead.',
    'email': 'timothygarcia@example.org',
    'phone_number': '+1-773-969-1365x1860',
    'json': {
    'name': 'Nicole Briggs',
    'address': '1159 Elizabeth Fork\nLake Elaineshire, DE 29171',
},
    'key11933': 'value96682',
    'key31258': 'value84312',
    'key25350': 'value51347',
    'key52923': 'value85223',
    'key63944': 'value85570',
},
    {
    'id': 17527486676419,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Patrick Obrien',
    'address': '4047 Angela Greens Apt. 426\nSouth Justinmouth, MT 22381',
    'text': 'Share particular morning. Feel everything hope institution put later write sport. Subject out see word benefit group rock.\nWear yard add.',
    'email': 'tonyaalvarado@example.com',
    'phone_number': '(995)687-7627',
    'json': {
    'name': 'Emily Anderson',
    'address': '983 Catherine Expressway\nPort Kristen, SC 81162',
},
    'key37024': 'value89401',
    'key56919': 'value16472',
    'key99747': 'value90224',
    'key59176': 'value11659',
    'key96346': 'value75898',
},
    {
    'id': 17527486676432,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Nathan Dominguez',
    'address': '4691 Heather Circle\nHernandezmouth, WY 58103',
    'text': 'Wind season glass. Sound movement citizen size thus really. Sit seat read find end stuff stage dream.\nDecision police brother increase look several. Economic voice house but.',
    'email': 'jessicagarcia@example.org',
    'phone_number': '001-681-566-7237x0821',
    'json': {
    'name': 'Daniel Harris',
    'address': '8019 Benjamin Hills Suite 852\nLake Sara, OR 12584',
},
    'key61007': 'value70536',
    'key44399': 'value99064',
    'key22365': 'value82250',
},
    {
    'id': 17527486676445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jason Mcknight',
    'address': '88183 Maria Common Suite 459\nJohnsonchester, MO 16474',
    'text': 'Tax claim save. Whatever son idea figure.\nSize leader age. Serve event before such traditional author. Unit beyond professor manager quality prepare.',
    'email': 'edwardgoodman@example.net',
    'phone_number': '432.973.3298x002',
    'json': {
    'name': 'Amber Bartlett',
    'address': '2625 Brenda Wells\nNorth Laura, MP 06044',
},
    'key19690': 'value8789',
    'key1939': 'value85714',
    'key14824': 'value96013',
    'key24859': 'value16633',
},
    {
    'id': 17527486676458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jonathon Carter',
    'address': 'PSC 2781, Box 2233\nAPO AA 68732',
    'text': 'Behavior board believe. Area office student money up let leg both.\nDay drive hit. Spring catch or. Want administration human meet day ground score.',
    'email': 'abennett@example.com',
    'phone_number': '(552)796-9981',
    'json': {
    'name': 'Monica Johnson',
    'address': '083 Lester Square\nLake Daniel, MD 26876',
},
    'key47054': 'value32830',
    'key13259': 'value65215',
    'key54116': 'value23486',
    'key59729': 'value96603',
    'key65786': 'value53052',
    'key4014': 'value93039',
    'key6836': 'value66889',
},
    {
    'id': 17527486676467,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Amanda Coleman',
    'address': '231 Linda Square\nNew Martha, TX 02413',
    'text': 'Capital anyone throw feel pay will garden clear. Guess professor enjoy huge. Policy catch various purpose out also source.',
    'email': 'ztaylor@example.org',
    'phone_number': '319-942-0937',
    'json': {
    'name': 'Richard Clayton',
    'address': '51386 Hodge Meadows\nDonaldhaven, GA 51411',
},
    'key12503': 'value27959',
    'key64685': 'value97428',
},
    {
    'id': 17527486676478,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Roger Moore',
    'address': '7445 Adam Parks Suite 234\nMarcusfort, GU 87770',
    'text': 'Only cost class article short a leg. Gun writer candidate seek have. Material wall sing civil training son child bill. Recently power campaign father.',
    'email': 'richardnguyen@example.com',
    'phone_number': '(791)597-2430',
    'json': {
    'name': 'Christine Sanchez',
    'address': 'USCGC Roberts\nFPO AP 03045',
},
    'key18923': 'value62793',
    'key3625': 'value86384',
    'key24787': 'value57216',
    'key53133': 'value11232',
    'key27095': 'value67615',
},
    {
    'id': 17527486676489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Brett King',
    'address': 'Unit 8032 Box 0522\nDPO AE 53696',
    'text': 'Far brother some indeed nor myself would.\nFeeling relationship participant ago short. Official form rise TV foot stock ball poor. Tend like social hit necessary keep fine.',
    'email': 'alvarezsamantha@example.net',
    'phone_number': '001-370-916-4216x12392',
    'json': {
    'name': 'Christopher Leonard',
    'address': '28390 Taylor Green\nGrantshire, FM 58268',
},
    'key2552': 'value68154',
    'key5647': 'value29801',
    'key96771': 'value2511',
    'key61207': 'value65178',
    'key65752': 'value26059',
    'key87192': 'value94445',
    'key75730': 'value13714',
    'key945': 'value36278',
    'key49396': 'value48744',
},
    {
    'id': 17527486676499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'David Peterson',
    'address': '4365 Mooney Square Apt. 612\nMarshallton, SC 44725',
    'text': 'Particular the pick across. Now page act economy free his.\nHeavy daughter threat traditional race although. Today enter field tend month although.',
    'email': 'latoya77@example.com',
    'phone_number': '+1-688-213-9599x419',
    'json': {
    'name': 'Kara Robinson',
    'address': '31809 Brown Track\nPort Paulland, NM 48031',
},
    'key82425': 'value87760',
    'key3958': 'value39777',
    'key39561': 'value23142',
    'key97161': 'value92931',
},
    {
    'id': 17527486676511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Eduardo Roth',
    'address': '02612 Kelly Haven Suite 949\nKristinborough, PW 94678',
    'text': 'Effort part woman without improve. Only care sport else court debate. Boy east team lot participant painting team.',
    'email': 'hacosta@example.org',
    'phone_number': '001-550-458-4287x1266',
    'json': {
    'name': 'Steven Lester',
    'address': '0676 Gomez Overpass Apt. 931\nWest Tina, FM 27054',
},
    'key34596': 'value7817',
    'key13829': 'value67455',
    'key80503': 'value11608',
    'key58849': 'value42074',
    'key31459': 'value33274',
    'key48880': 'value61372',
    'key81985': 'value39643',
    'key58400': 'value38919',
    'key83449': 'value29605',
},
    {
    'id': 17527486676522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Brandon Sparks',
    'address': '9588 Barbara Pike\nCarolynstad, VT 78573',
    'text': 'Also play herself everyone these. Want hotel sure seem whether.\nAuthor social operation few. Almost break I resource ten.',
    'email': 'jarellano@example.com',
    'phone_number': '(716)567-7974x88047',
    'json': {
    'name': 'Stephanie Greene',
    'address': '6252 Ebony Parks\nBrandistad, IA 19864',
},
    'key11709': 'value38468',
    'key88263': 'value67128',
    'key12916': 'value20747',
    'key19172': 'value58176',
    'key22119': 'value41343',
    'key38019': 'value60348',
    'key13375': 'value31147',
},
    {
    'id': 17527486676532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Katherine Pierce',
    'address': '0323 Jesse Fall Apt. 809\nHuntermouth, NY 19363',
    'text': 'Drive might memory everything military. Without woman amount total. Nor admit fish your southern certainly. Pay not simple pass job boy.',
    'email': 'joshuaaustin@example.org',
    'phone_number': '771.949.7717x24999',
    'json': {
    'name': 'Julie Gould',
    'address': '3809 Johnny Brooks Suite 481\nWest Kaitlin, NV 70610',
},
    'key24543': 'value92359',
    'key1403': 'value9900',
    'key3469': 'value55179',
    'key20652': 'value69935',
    'key62311': 'value70891',
},
    {
    'id': 17527486676544,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Stacy Harper',
    'address': '87412 Sims Heights Suite 007\nCowanburgh, NC 58344',
    'text': 'Company moment television let several once meet. Popular church dream discover somebody if tend for. Student southern head their religious.',
    'email': 'dbarajas@example.com',
    'phone_number': '509.898.8521x741',
    'json': {
    'name': 'Alexandra Watson',
    'address': '0565 Miller Skyway Apt. 473\nHernandezside, MH 59212',
},
    'key33019': 'value30154',
    'key46227': 'value13713',
    'key48124': 'value74965',
    'key14234': 'value99351',
},
    {
    'id': 17527486676555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Joshua Donovan',
    'address': '94530 Derek Shoal\nChristinaland, DC 46782',
    'text': 'Important not popular human. Fill movement accept guy view artist drive. Oil idea while mention message visit.\nCommon difference yet remain black health. Stand trial movement future.',
    'email': 'nfuller@example.com',
    'phone_number': '+1-957-562-9467x83573',
    'json': {
    'name': 'Michael Allen',
    'address': '68511 Stephen Point Apt. 942\nNicholasfort, WY 23000',
},
    'key64987': 'value31489',
    'key60686': 'value87221',
    'key42958': 'value17927',
    'key97109': 'value51396',
    'key89702': 'value85709',
    'key16735': 'value65352',
    'key38833': 'value25301',
    'key65016': 'value80435',
    'key61963': 'value19673',
    'key22145': 'value63939',
},
    {
    'id': 17527486676566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Robyn Wolf',
    'address': '185 Christopher Rue\nWilsonmouth, CA 44878',
    'text': 'Opportunity shoulder character tend another even report cut. Final lose behavior learn party opportunity.',
    'email': 'xstanley@example.com',
    'phone_number': '524.240.6744',
    'json': {
    'name': 'Kevin Kelley',
    'address': 'USS Jackson\nFPO AA 51500',
},
    'key95892': 'value92786',
    'key55409': 'value52146',
    'key7697': 'value73975',
    'key56580': 'value47114',
},
    {
    'id': 17527486676575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Christopher Sanders',
    'address': '27941 Mcintyre Drives Apt. 344\nGarciamouth, CA 67369',
    'text': 'How sound talk though power some those. Kitchen answer themselves price.\nTechnology reflect set central friend tell me notice. Real charge none challenge. Black interesting much third blue future.',
    'email': 'frostjessica@example.net',
    'phone_number': '519-690-6221x39192',
    'json': {
    'name': 'Tiffany Bates',
    'address': '9426 Smith Parkway\nWest Christopherhaven, KS 87698',
},
    'key61466': 'value96684',
    'key5201': 'value51132',
    'key84425': 'value58715',
},
    {
    'id': 17527486676587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Tommy Clark',
    'address': '8056 Billy Manor Suite 025\nClementsland, MD 27250',
    'text': 'Student nor expert talk free reveal evidence light. Personal discuss senior wish dream.\nThousand fire time whole across. List article inside for line almost site say. Stock southern wait agency step.',
    'email': 'wendy63@example.com',
    'phone_number': '+1-254-581-6217x0044',
    'json': {
    'name': 'Steven Collins',
    'address': '1446 Daugherty Field\nBakerland, ID 32202',
},
    'key52514': 'value71444',
    'key97645': 'value46100',
    'key66929': 'value33976',
    'key46692': 'value88130',
    'key33558': 'value19402',
    'key54783': 'value65204',
    'key9907': 'value98488',
    'key34140': 'value87144',
},
    {
    'id': 17527486676598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Kathleen Jackson',
    'address': 'PSC 3318, Box 6610\nAPO AP 59820',
    'text': 'Method marriage social doctor tonight. Edge force southern suddenly paper.',
    'email': 'cookcolin@example.com',
    'phone_number': '(394)274-6136',
    'json': {
    'name': 'Ellen Hayes',
    'address': '3747 Taylor Springs\nNew Todd, DE 51024',
},
    'key4896': 'value51597',
    'key23852': 'value88830',
    'key95379': 'value19372',
},
    {
    'id': 17527486676607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Robin Wise',
    'address': '2922 Hannah Lodge\nLake Danahaven, AS 71724',
    'text': 'Wrong plan offer act. Long place responsibility executive mouth.\nBecome challenge figure security southern. Return hand TV management entire anyone.',
    'email': 'dhughes@example.com',
    'phone_number': '001-320-468-8916x98672',
    'json': {
    'name': 'Anthony Little',
    'address': '438 John Fork Suite 752\nPort Austinborough, RI 68122',
},
    'key99914': 'value33611',
    'key3230': 'value62499',
    'key38444': 'value55513',
    'key98416': 'value57009',
    'key35979': 'value59063',
},
    {
    'id': 17527486676617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Patricia Murillo',
    'address': '4025 Martin Canyon\nNew Lisa, ID 72694',
    'text': 'Firm face vote Democrat. Hotel serious create.\nManagement collection realize. Road instead either.\nAbove report dream piece other store scientist respond. Vote former century address.',
    'email': 'gillchristopher@example.com',
    'phone_number': '8764806221',
    'json': {
    'name': 'Michelle Wilson',
    'address': '0788 Christian Lake Suite 152\nLake Kathryntown, ME 40403',
},
    'key46026': 'value44094',
    'key43056': 'value72568',
    'key13808': 'value83685',
    'key51160': 'value55493',
},
    {
    'id': 17527486676629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Daniel Liu',
    'address': 'Unit 6526 Box 1559\nDPO AA 59433',
    'text': 'Customer second campaign under eight. Explain that black no land.',
    'email': 'jessicahowell@example.net',
    'phone_number': '+1-257-509-6410x379',
    'json': {
    'name': 'Kelli Sanchez',
    'address': '138 Booth Ford\nNorth Elizabethport, LA 47141',
},
    'key11336': 'value81418',
    'key11356': 'value24338',
    'key27660': 'value13531',
},
    {
    'id': 17527486676638,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Julia Douglas',
    'address': '7088 Fletcher Key\nGravesshire, CA 31144',
    'text': 'Require story end city mission space. Appear include parent where manager. Turn local a.\nStep wait exactly ever. Radio white raise box win parent which. Nor agree few situation possible very month.',
    'email': 'castanedabrian@example.net',
    'phone_number': '663.969.1645x605',
    'json': {
    'name': 'Alyssa Lane',
    'address': '296 Miles Greens Suite 387\nAndersenport, MT 97506',
},
    'key74274': 'value23922',
    'key27310': 'value90833',
    'key43275': 'value34596',
    'key58485': 'value39181',
    'key61180': 'value45387',
    'key19363': 'value1556',
    'key84665': 'value66139',
    'key92093': 'value25696',
    'key98862': 'value85361',
    'key66716': 'value96512',
},
    {
    'id': 17527486676650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'David Pham',
    'address': '6694 David Loop Suite 228\nLake Ritastad, RI 53145',
    'text': 'Scientist tend focus. Push yes itself situation image southern most nation.\nOver more important seem but.',
    'email': 'elizabeth70@example.net',
    'phone_number': '8569064844',
    'json': {
    'name': 'Brett King',
    'address': '791 Stewart Lane\nTammyfort, KS 40492',
},
    'key11979': 'value8309',
    'key2722': 'value8720',
    'key46371': 'value50010',
    'key97400': 'value24470',
    'key18594': 'value4546',
    'key82551': 'value38247',
},
    {
    'id': 17527486676660,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'David Marshall',
    'address': '13571 Kim Route\nNew Alexville, KS 09227',
    'text': 'Everything worker to public. Sound visit shake measure perform. Light often center true exactly discover. Body technology model civil wrong main town.',
    'email': 'caroljones@example.org',
    'phone_number': '001-396-536-0799x34909',
    'json': {
    'name': 'Kayla Gomez',
    'address': '8436 Kathleen Vista\nReidfort, VA 23118',
},
    'key79436': 'value59256',
    'key17466': 'value92516',
    'key25598': 'value9395',
    'key79530': 'value52197',
    'key6613': 'value43649',
    'key73026': 'value92214',
    'key68132': 'value10614',
},
    {
    'id': 17527486676672,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Daniel Ramos',
    'address': '27630 Scott Hill\nSouth David, MS 75230',
    'text': 'Maintain girl get author.\nAlready actually movement large. Hope staff civil tonight.\nPerformance property rest.\nProcess thought usually west.',
    'email': 'denise64@example.net',
    'phone_number': '+1-472-416-6981',
    'json': {
    'name': 'Stephanie Scott',
    'address': '61320 Michael Crossing Suite 806\nHeathermouth, IL 55527',
},
    'key79558': 'value12158',
    'key91674': 'value32998',
    'key44545': 'value96242',
    'key4335': 'value36905',
    'key65539': 'value56274',
    'key76910': 'value39237',
    'key10246': 'value71954',
    'key33274': 'value49450',
},
    {
    'id': 17527486676682,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Kristin Ballard',
    'address': '545 Hernandez Ways\nSouth Sharonland, IA 15800',
    'text': 'Issue half Congress raise dark detail ahead. Call onto cut life contain country.\nWorker painting catch structure. Director suddenly alone any difference. For performance specific room value.',
    'email': 'craigclark@example.net',
    'phone_number': '2743435565',
    'json': {
    'name': 'Rhonda Fletcher',
    'address': '580 Kevin Tunnel\nAnthonyhaven, PA 23414',
},
    'key55570': 'value32944',
    'key49366': 'value78842',
    'key4927': 'value15444',
    'key12579': 'value96021',
    'key93601': 'value73843',
    'key1793': 'value35895',
    'key32048': 'value39841',
    'key28356': 'value54408',
},
    {
    'id': 17527486676694,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Brian Butler',
    'address': '7219 Anthony Villages Apt. 481\nMichaelshire, NJ 93139',
    'text': 'Strategy through ten these treatment head make.\nSign smile mind edge just expert. I audience full debate. Yet business those shoulder.',
    'email': 'andrewritter@example.org',
    'phone_number': '+1-569-263-6548x36626',
    'json': {
    'name': 'Joshua Collins',
    'address': '383 Thomas Square Suite 359\nEast Jeffreyview, CA 13698',
},
    'key44963': 'value52393',
},
    {
    'id': 17527486676705,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Corey Freeman',
    'address': '846 Jones Pine\nMichaelstad, MA 21701',
    'text': 'Help financial major Mrs bit hour choice. Must across discuss support. Onto leader energy discussion also management approach.',
    'email': 'elarson@example.com',
    'phone_number': '001-683-212-8904x726',
    'json': {
    'name': 'Kelly Reyes',
    'address': '74814 Spencer Meadows\nAaronstad, MI 25693',
},
    'key64185': 'value77875',
    'key49392': 'value31494',
    'key35795': 'value48620',
    'key42313': 'value66770',
    'key59154': 'value35965',
    'key84563': 'value72135',
    'key49302': 'value71532',
    'key18066': 'value90805',
    'key71412': 'value78490',
},
    {
    'id': 17527486676716,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Amanda Hernandez',
    'address': '13960 Douglas Trail Apt. 035\nNorth Brenda, MH 09639',
    'text': 'Marriage window war expect. Language tough many firm authority far. Soldier form beat paper prevent main note.',
    'email': 'angela90@example.org',
    'phone_number': '344-356-5742',
    'json': {
    'name': 'Timothy Smith',
    'address': '3813 Lee Circle\nEast Michaelchester, MN 77148',
},
    'key88476': 'value62122',
    'key12435': 'value15573',
    'key70349': 'value73870',
    'key22948': 'value26979',
    'key18286': 'value70426',
    'key11766': 'value8515',
    'key72596': 'value13445',
    'key19242': 'value44960',
    'key27202': 'value8616',
},
    {
    'id': 17527486676727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Savannah Ochoa',
    'address': '5035 Monica Mews\nJennastad, AK 58443',
    'text': 'Have nothing country develop. Mouth life find born natural.',
    'email': 'shannonconner@example.com',
    'phone_number': '825.258.3252x8736',
    'json': {
    'name': 'Kari Green',
    'address': '1635 Curry Square\nAndrewberg, WV 33931',
},
    'key79885': 'value17426',
    'key17693': 'value49370',
    'key50304': 'value46923',
    'key91005': 'value73837',
    'key68490': 'value88119',
    'key94065': 'value33648',
    'key36070': 'value32754',
},
    {
    'id': 17527486676738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Heather Burgess',
    'address': '06307 Riddle Fort\nLake Tara, IN 73251',
    'text': 'Person pressure million human data recently perform. Thought back every would what site sometimes. Place myself town.\nFall skin around hour lot. Oil benefit water yourself.',
    'email': 'rebecca02@example.org',
    'phone_number': '+1-608-879-5976',
    'json': {
    'name': 'Rebecca Dunn',
    'address': 'PSC 4631, Box 2841\nAPO AA 34167',
},
    'key47195': 'value91631',
    'key19472': 'value33021',
    'key31612': 'value3811',
    'key93849': 'value72366',
    'key79283': 'value45663',
    'key21688': 'value67092',
    'key5696': 'value87453',
},
    {
    'id': 17527486676747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Michelle Jenkins',
    'address': '646 Lisa Ville Apt. 488\nNew Phillip, IL 87523',
    'text': 'Work worry claim in cup economy girl. Poor sense site report offer guess local. Player much away no imagine agreement.',
    'email': 'hramirez@example.net',
    'phone_number': '802.390.1621',
    'json': {
    'name': 'Hailey Eaton',
    'address': '7631 James Court\nCruzberg, NM 05000',
},
    'key65704': 'value40303',
    'key17136': 'value45461',
    'key69834': 'value30626',
    'key86749': 'value86369',
    'key53451': 'value42523',
    'key51975': 'value52316',
    'key62337': 'value71314',
},
    {
    'id': 17527486676757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Joshua Rice',
    'address': '16168 Shepard Springs\nLake Kyleland, CA 77188',
    'text': 'Decade open news Mrs. Simple describe ever base again.\nPhone material good stage political rock. Especially behind pretty let early artist rate.\nBecause help build opportunity smile out.',
    'email': 'alexandermark@example.org',
    'phone_number': '(387)296-0717x72896',
    'json': {
    'name': 'Mary Russell',
    'address': 'USCGC Pierce\nFPO AP 17338',
},
    'key93861': 'value36399',
    'key18430': 'value27497',
    'key30914': 'value10799',
    'key43719': 'value6161',
    'key81136': 'value68637',
    'key10137': 'value46801',
    'key24522': 'value41505',
    'key85114': 'value62265',
    'key56191': 'value5101',
    'key17947': 'value64500',
},
    {
    'id': 17527486676768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Amber Stewart',
    'address': 'USS Pruitt\nFPO AA 92982',
    'text': 'Card food artist possible. Protect city whole sort table. May let show central concern.',
    'email': 'callahanbonnie@example.org',
    'phone_number': '001-266-637-0131x08890',
    'json': {
    'name': 'Anthony Davis',
    'address': '68365 Leon Square Suite 248\nPalmertown, MA 97934',
},
    'key26945': 'value8705',
    'key48167': 'value95429',
    'key18073': 'value20326',
    'key63986': 'value76399',
    'key60270': 'value49539',
    'key16685': 'value37251',
    'key9680': 'value76033',
    'key15936': 'value16725',
    'key67634': 'value43372',
},
    {
    'id': 17527486676779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Brandon Salazar',
    'address': '224 Whitehead Circles Suite 999\nLake Vicki, NY 73634',
    'text': 'Position eat stage explain more statement. White area physical require.\nMouth include possible others put worker. Little should daughter see think ok husband.',
    'email': 'qbarnes@example.com',
    'phone_number': '563.448.9048',
    'json': {
    'name': 'Jill Perkins',
    'address': '24342 Richardson Center\nWilliamstad, GU 31337',
},
    'key87717': 'value31900',
    'key16984': 'value74228',
    'key98234': 'value72871',
    'key5280': 'value78805',
    'key17980': 'value43163',
    'key34635': 'value81586',
    'key97627': 'value31945',
    'key73170': 'value15177',
    'key41384': 'value20066',
},
    {
    'id': 17527486676790,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Lawrence Smith',
    'address': '217 Young Extensions Apt. 145\nNorth Patrick, MT 11259',
    'text': 'Government including officer. Without wait market onto government. More parent rich win public.\nSouthern pattern skin here also view. Program subject sort happy.',
    'email': 'thompsonfranklin@example.net',
    'phone_number': '(824)789-4230',
    'json': {
    'name': 'Denise Drake',
    'address': '15488 Michelle Motorway Apt. 088\nStephaniechester, PW 58038',
},
    'key86911': 'value68782',
    'key16193': 'value74148',
    'key82064': 'value9303',
    'key20070': 'value58212',
    'key24228': 'value43200',
    'key69751': 'value18437',
},
    {
    'id': 17527486676805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Joseph Smith',
    'address': '50125 Micheal Mills Apt. 902\nSouth Erika, MH 71268',
    'text': 'Sometimes base age remember sing. Fear month any theory.\nDoctor picture economy fight.\nBook over police sometimes. Tend notice range why common anyone thought.',
    'email': 'velasquezmarilyn@example.org',
    'phone_number': '(941)302-4440',
    'json': {
    'name': 'Mia Villarreal',
    'address': '686 Rachel Island\nScottmouth, NH 81427',
},
    'key47807': 'value49908',
    'key65719': 'value9103',
    'key76611': 'value22063',
},
    {
    'id': 17527486676819,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Kelly Johnson',
    'address': '16262 Denise Center\nJessicastad, GU 88718',
    'text': 'Series trouble stand husband while. Talk moment about operation administration pass onto. Guy try then will gun page.',
    'email': 'jamescaleb@example.org',
    'phone_number': '346-523-5865x369',
    'json': {
    'name': 'Kyle Cooper',
    'address': '555 Ray Turnpike Suite 125\nCisnerosville, GU 14108',
},
    'key71547': 'value30199',
    'key90879': 'value99926',
    'key11469': 'value62021',
    'key2679': 'value37164',
    'key48792': 'value29031',
    'key29259': 'value61147',
    'key68492': 'value86311',
},
    {
    'id': 17527486676834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Megan Le',
    'address': '6943 Mark Fork\nLake Patricia, ID 02841',
    'text': 'Station central purpose network. Participant style student affect star down. Black party tell sure up.',
    'email': 'garyturner@example.com',
    'phone_number': '+1-762-955-9897x435',
    'json': {
    'name': 'John Espinoza',
    'address': '833 Brittany Trafficway\nPort Christine, MI 38605',
},
    'key38870': 'value65437',
    'key47645': 'value11004',
},
    {
    'id': 17527486676848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Juan Zamora',
    'address': '966 Antonio Shores\nNorth Steven, MP 22442',
    'text': 'Total specific technology become student film place. Pm north investment girl education. Natural collection bill anything give.\nRemain reduce later well. Want various site method among stay.',
    'email': 'keith99@example.org',
    'phone_number': '+1-566-232-7965x4817',
    'json': {
    'name': 'Mark Contreras',
    'address': '19588 Graham Bridge Apt. 160\nStefanieborough, MD 57011',
},
    'key23194': 'value31755',
    'key84163': 'value46062',
    'key26642': 'value55072',
},
    {
    'id': 17527486676861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Tyler Jackson',
    'address': '46573 Parsons Unions Suite 653\nWest Kimfurt, ME 20685',
    'text': 'Blue heart build military treatment both turn. Her best grow without resource card first.\nOwn write ask particular section thing great. Remember this force red role. Force customer always style.',
    'email': 'alvarezjoe@example.com',
    'phone_number': '515-734-9733x52242',
    'json': {
    'name': 'Renee Weber',
    'address': '46359 Baldwin Lake Apt. 973\nSouth Becky, GU 61553',
},
    'key26508': 'value94971',
    'key55688': 'value50661',
    'key81532': 'value34197',
    'key75953': 'value81123',
    'key83128': 'value4343',
    'key49911': 'value82129',
    'key66947': 'value7595',
},
    {
    'id': 17527486676875,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Jill Walsh PhD',
    'address': '6274 Allison Crossroad\nArnoldtown, DE 84740',
    'text': 'Five hand question raise source method better. Use evening rich senior husband moment police. National draw argue system administration agreement.',
    'email': 'frankmark@example.org',
    'phone_number': '+1-449-423-9315x583',
    'json': {
    'name': 'Linda Delgado',
    'address': '3763 Mason Cliff\nWrightberg, PW 33895',
},
    'key98436': 'value34656',
    'key26526': 'value19473',
    'key18350': 'value13667',
    'key96764': 'value80191',
    'key2957': 'value35026',
    'key53485': 'value25667',
},
    {
    'id': 17527486676890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michelle Mills',
    'address': '163 Williams Junction\nNorth James, AR 73581',
    'text': 'Others better read central dinner. Clear citizen stay note character before speak.\nBe ground well meet little serious summer major. Way career add present body.',
    'email': 'shawn79@example.org',
    'phone_number': '(468)680-7377x86306',
    'json': {
    'name': 'Vincent Dawson',
    'address': '00081 James Viaduct\nDonnaville, DE 11452',
},
    'key14284': 'value34811',
    'key74812': 'value72171',
    'key19883': 'value1501',
    'key44695': 'value51244',
    'key15853': 'value53051',
    'key59550': 'value3173',
    'key51669': 'value22523',
    'key1475': 'value30367',
},
    {
    'id': 17527486676903,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Nicole Maxwell MD',
    'address': '79447 Alexander Key Suite 202\nSilvaview, OH 42234',
    'text': 'Have take seek research get room thing. Response eat financial treat state show.\nThemselves can through red enjoy. Government adult shoulder spend bit specific training.',
    'email': 'boydkaren@example.com',
    'phone_number': '+1-241-720-8779',
    'json': {
    'name': 'Stephen Smith',
    'address': '796 Thomas Orchard\nNew Ronnieshire, RI 51287',
},
    'key69260': 'value97827',
    'key18173': 'value57996',
    'key12565': 'value48424',
    'key64129': 'value88449',
    'key69940': 'value37186',
    'key37925': 'value72526',
    'key13730': 'value18690',
    'key71146': 'value47442',
    'key81531': 'value43320',
},
    {
    'id': 17527486676916,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Samuel Fox',
    'address': '513 Melissa Ways\nNicholasside, KS 90960',
    'text': 'On goal test development rate charge evening. Other will speech. Parent experience father worker skin word. Outside direction sport wonder production.',
    'email': 'tcoleman@example.net',
    'phone_number': '398.726.4662',
    'json': {
    'name': 'Elizabeth Weber',
    'address': '45226 Michael Ferry\nPort Susanfort, CO 70025',
},
    'key65260': 'value71099',
    'key25837': 'value55638',
    'key82742': 'value48176',
    'key31368': 'value13019',
},
    {
    'id': 17527486676926,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Michael Reynolds',
    'address': '290 Brian Turnpike Suite 316\nAyalaview, CA 76682',
    'text': 'Stand game their parent possible. Who ok to force call.\nBetter top reality TV deep role. Campaign area smile. Deal last know blue join job.',
    'email': 'mckaylucas@example.org',
    'phone_number': '766.627.4295x563',
    'json': {
    'name': 'Katherine Ross',
    'address': '0661 Wade Hollow\nWilliamchester, FL 71097',
},
    'key10650': 'value82078',
    'key45346': 'value78781',
    'key81703': 'value88912',
    'key98420': 'value84549',
    'key96489': 'value26813',
    'key6430': 'value38836',
    'key3471': 'value39687',
    'key87079': 'value91222',
    'key17692': 'value2065',
    'key1772': 'value62746',
},
    {
    'id': 17527486676938,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Sharon Benton',
    'address': '821 Hernandez Expressway\nWest Angela, PA 20546',
    'text': 'Personal these step message thus report quite even. Difficult ability certain entire. Couple they religious simple according true.',
    'email': 'michelle28@example.org',
    'phone_number': '2738298104',
    'json': {
    'name': 'Jessica Thomas',
    'address': 'Unit 8442 Box 1546\nDPO AE 29733',
},
    'key6988': 'value43640',
},
    {
    'id': 17527486676946,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Mark Warren',
    'address': '2171 Megan Ports Apt. 658\nSmithshire, NH 82040',
    'text': 'From city clearly structure Democrat decade. Action movie unit you kitchen. Development provide large similar.',
    'email': 'glennjohnson@example.net',
    'phone_number': '393-990-8714x006',
    'json': {
    'name': 'Hunter Reed',
    'address': '419 Samantha Centers\nLake Michaelborough, HI 25523',
},
    'key50408': 'value55870',
    'key28455': 'value99228',
    'key65612': 'value40742',
    'key79793': 'value41823',
    'key71352': 'value48402',
    'key60812': 'value88457',
    'key65248': 'value44145',
},
    {
    'id': 17527486676957,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Priscilla Barnes',
    'address': '01738 Kerr Prairie Suite 517\nMarissaborough, LA 92463',
    'text': 'Newspaper write fish who. Blood television true bring politics really might.\nSeven fund church seat know. Travel necessary actually consider list. Television top pull meeting.',
    'email': 'cruzbrian@example.com',
    'phone_number': '+1-968-995-2244x65962',
    'json': {
    'name': 'Francisco Saunders',
    'address': '631 Sutton Court\nMurphymouth, WV 64541',
},
    'key92853': 'value63272',
    'key49046': 'value94167',
    'key13417': 'value49547',
    'key74982': 'value16517',
    'key59990': 'value7373',
    'key84012': 'value18040',
    'key4564': 'value47515',
    'key27754': 'value49164',
    'key98085': 'value12995',
    'key20466': 'value4375',
},
    {
    'id': 17527486676970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Austin Jones',
    'address': '2332 King Estates Suite 831\nWest Gary, IL 80670',
    'text': 'Avoid art hair himself hotel. Less audience catch few item like listen. Save ever economic although draw. Seek pressure live open employee factor.',
    'email': 'martindiana@example.net',
    'phone_number': '2749846857',
    'json': {
    'name': 'Kimberly Harris',
    'address': '1014 James Centers Apt. 336\nNew Colleen, AZ 64251',
},
    'key27031': 'value36763',
    'key48201': 'value4811',
    'key79664': 'value28697',
    'key91107': 'value15567',
    'key88168': 'value1591',
},
    {
    'id': 17527486676982,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Michael Strickland',
    'address': '99447 Shannon Haven Suite 485\nAdamsshire, FL 06577',
    'text': 'Serve American somebody animal hundred. Plan main people everybody local. Politics season spend chair gun part north these. Goal your visit ok feeling physical.',
    'email': 'sextonelizabeth@example.org',
    'phone_number': '841.333.0987',
    'json': {
    'name': 'Sara Silva',
    'address': '963 Madeline Center\nDavisville, MH 78529',
},
    'key52232': 'value82345',
},
    {
    'id': 17527486676993,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Raymond Carter',
    'address': '5393 Johnson Course Suite 432\nNew David, TN 82343',
    'text': 'Hour evidence cold think floor usually phone. West fish matter run difference must media. Treatment next charge white best year free.',
    'email': 'cookkayla@example.org',
    'phone_number': '561.505.6698x8184',
    'json': {
    'name': 'Samuel Mathis',
    'address': '8331 Karen Throughway\nWest Laurie, MS 30495',
},
    'key15921': 'value55489',
    'key94822': 'value80977',
    'key19325': 'value76143',
    'key2158': 'value98467',
    'key59031': 'value4141',
    'key34139': 'value76836',
},
    {
    'id': 17527486677005,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kimberly Atkins',
    'address': '8847 Tyler Estate Suite 622\nSarashire, GA 24446',
    'text': 'Particular should land identify positive. Former fast culture form stay us.\nAnother these within decade.\nShoulder Mr degree. Fast particular relationship environmental budget hot believe.',
    'email': 'laurakirby@example.com',
    'phone_number': '671-290-1720x91286',
    'json': {
    'name': 'Mary Hudson',
    'address': 'PSC 7368, Box 3550\nAPO AP 71723',
},
    'key81736': 'value72366',
    'key86519': 'value47971',
    'key67523': 'value59917',
},
    {
    'id': 17527486677014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Justin Baker',
    'address': '81404 Michelle Plain\nStantonborough, ND 95107',
    'text': 'I task into nothing rise note ready. Late future nothing type one issue account. Design image age doctor eight.\nReduce address theory leg. Treat rise step that medical yet. Carry claim law best.',
    'email': 'ahernandez@example.org',
    'phone_number': '385-924-9656x6110',
    'json': {
    'name': 'Lauren Davis',
    'address': '523 Lonnie Landing Apt. 147\nNorth Amyhaven, TN 27173',
},
    'key10950': 'value13958',
    'key45723': 'value73186',
    'key75338': 'value14909',
    'key2062': 'value78005',
    'key57244': 'value14982',
    'key25978': 'value8121',
},
    {
    'id': 17527486677025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Kathy Parker',
    'address': '697 Alan Parkway\nSouth Kristy, OH 21152',
    'text': 'Recently time board him floor major wish address. Lose she family wall popular church road.',
    'email': 'sclark@example.com',
    'phone_number': '001-847-390-2552x748',
    'json': {
    'name': 'Beverly Sherman',
    'address': '18824 Jacob Valley Suite 079\nEmmaborough, WA 09606',
},
    'key20046': 'value69018',
    'key19745': 'value20292',
    'key39054': 'value20169',
    'key85586': 'value42635',
    'key86240': 'value41997',
    'key85478': 'value88203',
    'key46421': 'value64605',
    'key84927': 'value73996',
},
    {
    'id': 17527486677035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Tracy Brandt',
    'address': '27133 Angela Parkways\nGayberg, FM 35535',
    'text': 'Result tax bit glass go billion concern. Begin author night arrive. No federal fish arrive daughter less first.',
    'email': 'nferguson@example.net',
    'phone_number': '001-284-834-5209x5664',
    'json': {
    'name': 'Stephen Velez',
    'address': '0476 Michelle Meadows Apt. 369\nNew Karenhaven, MN 72227',
},
    'key89228': 'value16557',
    'key81359': 'value10285',
    'key26962': 'value57149',
    'key87260': 'value3275',
    'key9523': 'value2257',
    'key51327': 'value39998',
    'key43525': 'value98551',
    'key28650': 'value82299',
    'key8149': 'value62619',
},
    {
    'id': 17527486677046,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'James Christensen',
    'address': '25802 Amy Mills Suite 858\nBestfurt, MA 37108',
    'text': 'Character with family behind quite sort program image. Miss full society drug able detail do. Decide foot total.\nHimself way responsibility grow bring. It friend young kitchen.',
    'email': 'tylerian@example.net',
    'phone_number': '317.534.6605x5964',
    'json': {
    'name': 'Brittany Carroll',
    'address': 'PSC 6500, Box 4209\nAPO AA 33481',
},
    'key76328': 'value62067',
    'key15805': 'value73578',
    'key29241': 'value96245',
    'key41701': 'value91406',
    'key82946': 'value65969',
    'key12404': 'value43937',
    'key15272': 'value94503',
},
    {
    'id': 17527486677056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Jonathan Johnson',
    'address': '967 Howard Extension\nNorth Shelly, ME 22452',
    'text': 'Series know save indeed.\nRather task according author become value develop. Represent decision child unit catch certainly.',
    'email': 'gomezmarcus@example.net',
    'phone_number': '001-858-809-1601x370',
    'json': {
    'name': 'Jesus Oconnor',
    'address': '158 Johnson Terrace Apt. 582\nPort Tyler, WV 33445',
},
    'key35155': 'value99189',
    'key86893': 'value53217',
    'key45632': 'value56643',
},
    {
    'id': 17527486677068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Frank Clements',
    'address': '47714 Courtney Crossroad Suite 124\nLake Christine, NV 75241',
    'text': 'Discussion growth day. Everybody scientist let behavior weight.\nWriter view sell area money. Board piece dark wish dream.\nCertainly yard general let vote. During marriage record learn. Do seat least.',
    'email': 'sperry@example.com',
    'phone_number': '+1-229-294-1225',
    'json': {
    'name': 'Michael Barrett',
    'address': '3380 Leonard Ports Suite 727\nJacobstad, WV 96374',
},
    'key97483': 'value18712',
    'key46471': 'value73030',
    'key41450': 'value46236',
    'key13494': 'value46543',
    'key58667': 'value35788',
    'key59262': 'value5192',
    'key7410': 'value97130',
    'key44609': 'value45237',
    'key11973': 'value39358',
    'key95764': 'value98418',
},
    {
    'id': 17527486677079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Danielle Williams',
    'address': 'PSC 5981, Box 9726\nAPO AA 21631',
    'text': 'Each when organization Congress behavior national.\nMachine purpose provide task. Dream total stock air very red. Five cause many mind.\nMethod cell miss loss approach.',
    'email': 'orramber@example.org',
    'phone_number': '8289406504',
    'json': {
    'name': 'Danny Howard',
    'address': '118 Lynn Underpass Suite 868\nSouth Kimberly, SC 49362',
},
    'key44738': 'value75519',
    'key75326': 'value75249',
    'key47011': 'value51912',
    'key95607': 'value27834',
    'key44598': 'value9890',
},
    {
    'id': 17527486677089,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'James Doyle',
    'address': '0693 Reeves Falls\nNew Darren, MT 10570',
    'text': 'World edge marriage physical international we. Grow same wind knowledge laugh none. Sure much practice near.\nStyle face daughter together skin stuff share. Truth stuff firm treatment our center.',
    'email': 'paul11@example.com',
    'phone_number': '001-346-705-1376x08048',
    'json': {
    'name': 'Joshua Bailey',
    'address': '64469 Sharon Inlet\nNew Rachaelfort, MT 28102',
},
    'key34588': 'value2779',
},
    {
    'id': 17527486677099,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jeremy Jones',
    'address': '017 Torres Corners Apt. 188\nWilliamstown, PA 29714',
    'text': 'Small me guess class picture increase. Deal leg find tonight should apply. Watch school defense dinner must pull.',
    'email': 'amandagray@example.net',
    'phone_number': '+1-825-856-0007',
    'json': {
    'name': 'Ronnie Davis',
    'address': '201 Stefanie Shoal\nEast Jenniferside, GA 02254',
},
    'key56392': 'value3230',
    'key61153': 'value49304',
    'key71598': 'value39310',
},
    {
    'id': 17527486677110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Margaret Contreras',
    'address': '18166 James Squares Apt. 821\nTorresberg, RI 84944',
    'text': 'Exist court owner house build show former father. Performance ever likely admit alone common.',
    'email': 'reynoldschristian@example.net',
    'phone_number': '489-258-2615x0567',
    'json': {
    'name': 'Ashley Ramirez',
    'address': '32971 Jenkins Trail Suite 624\nCortezmouth, CA 83857',
},
    'key89794': 'value91042',
    'key30390': 'value23647',
},
    {
    'id': 17527486677122,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Joshua King',
    'address': '8510 Russo Ways Suite 913\nNew Tyrone, OR 35339',
    'text': 'Right bed try up most great. Big occur could serious ago second market.\nDevelopment point road perhaps defense allow. Also suffer Mr environmental.',
    'email': 'josethompson@example.com',
    'phone_number': '(861)554-2823x18132',
    'json': {
    'name': 'Kenneth Foster',
    'address': '339 Gonzalez Inlet Apt. 206\nPort Andrew, MP 02139',
},
    'key21798': 'value13918',
    'key5184': 'value63008',
    'key67774': 'value88047',
    'key99572': 'value80170',
    'key16698': 'value54855',
    'key7849': 'value54998',
    'key45089': 'value86970',
    'key84236': 'value59050',
    'key84211': 'value12011',
    'key8134': 'value26097',
},
    {
    'id': 17527486677134,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Andrew Riley',
    'address': '5055 Lisa Ports Suite 615\nAdamsstad, NV 46113',
    'text': 'Into article field news peace mission low. Whom positive have minute call eye with.',
    'email': 'david98@example.org',
    'phone_number': '2119580553',
    'json': {
    'name': 'Cynthia Williams',
    'address': '04015 Sherry Unions\nLake Jessica, HI 34822',
},
    'key76658': 'value74192',
    'key91195': 'value18988',
    'key68593': 'value84326',
    'key4554': 'value3254',
},
    {
    'id': 17527486677145,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Heather Foster',
    'address': '2675 Melissa Extension\nWest Melanieshire, RI 20349',
    'text': 'Deal news area their her Mr later. Floor set much. Head customer though itself true white exist. Fall process if baby support feeling.\nBe beautiful carry thought require others finish himself.',
    'email': 'qmedina@example.com',
    'phone_number': '849.387.6508x146',
    'json': {
    'name': 'Tara Bass',
    'address': '5115 Mallory Centers Apt. 791\nEast Mark, ID 01737',
},
    'key67993': 'value7832',
    'key64998': 'value29856',
    'key21620': 'value41618',
},
    {
    'id': 17527486677155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Kevin Cabrera',
    'address': '27140 Erin Stravenue\nSouth Rebecca, NV 75046',
    'text': 'Unit could future much note order accept. Issue certainly watch may Mr.\nNothing put him. Far free believe. Pattern religious house mouth single follow.',
    'email': 'kevin29@example.net',
    'phone_number': '(802)207-1444',
    'json': {
    'name': 'David James',
    'address': '95903 Gwendolyn Oval\nLongmouth, LA 34384',
},
    'key20498': 'value14925',
},
    {
    'id': 17527486677165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Heather Schneider',
    'address': '24184 Dean Hill Apt. 141\nNorth Donnaburgh, MA 64991',
    'text': 'Computer task through her determine property threat. That chair establish issue finish.\nRole across new response. Deep indeed name area fast. Stage reality example soon.',
    'email': 'barbarawise@example.org',
    'phone_number': '649-469-2076x3585',
    'json': {
    'name': 'Alison Henry',
    'address': 'USCGC Walter\nFPO AE 03968',
},
    'key92594': 'value92769',
    'key66455': 'value84502',
    'key14814': 'value46821',
    'key52224': 'value27896',
    'key9648': 'value32206',
    'key61148': 'value3073',
    'key1388': 'value48545',
    'key94502': 'value76067',
    'key20477': 'value88925',
    'key58895': 'value37637',
},
    {
    'id': 17527486677176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Laura Simpson',
    'address': 'USNS Diaz\nFPO AE 35063',
    'text': 'Chance above federal rest. Audience industry heart way seem.\nWestern site idea myself positive affect. Bill friend beyond child.',
    'email': 'hurstalexis@example.com',
    'phone_number': '+1-687-711-0226x77146',
    'json': {
    'name': 'Jesus Murray',
    'address': '4771 Gordon Mews\nSouth Vincent, OH 07724',
},
    'key52096': 'value92152',
    'key92970': 'value66947',
    'key96919': 'value27885',
    'key35702': 'value12872',
    'key11603': 'value59881',
    'key58502': 'value18185',
    'key10265': 'value99947',
    'key66468': 'value8325',
    'key66941': 'value57345',
    'key81857': 'value22377',
},
    {
    'id': 17527486677186,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'William Higgins',
    'address': '8502 Black Wall\nJonesside, LA 92262',
    'text': 'Three along floor mother board small. These although compare edge understand guy try. Real industry country little certainly little.',
    'email': 'delgadochelsey@example.org',
    'phone_number': '2097899762',
    'json': {
    'name': 'Michael Scott',
    'address': '71582 James Knolls\nTroyville, MI 13778',
},
    'key74021': 'value98522',
    'key19781': 'value67838',
    'key2713': 'value95443',
    'key68429': 'value32766',
    'key50593': 'value1563',
    'key12822': 'value52868',
    'key90730': 'value66939',
    'key49861': 'value43076',
    'key20906': 'value62966',
},
    {
    'id': 17527486677198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Ryan Manning',
    'address': '2990 Curtis Hills Apt. 357\nDanielville, MN 40680',
    'text': 'National wrong expert site team draw. Enough audience prove check main wish.\nWhile life throughout school. If information mention meet.',
    'email': 'ryanwilliams@example.org',
    'phone_number': '360.468.7364',
    'json': {
    'name': 'Jamie Barnes',
    'address': 'PSC 7401, Box 3295\nAPO AA 25826',
},
    'key1538': 'value47994',
    'key99593': 'value74781',
},
    {
    'id': 17527486677208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Charles Roach',
    'address': '1895 Joseph Streets Suite 499\nLake Aprilburgh, WY 12199',
    'text': 'Rate my guy management national institution finally. Several firm best half. You finally easy religious throughout.',
    'email': 'ewilliamson@example.org',
    'phone_number': '254-801-9019x7959',
    'json': {
    'name': 'Melinda Lowe',
    'address': 'Unit 3068 Box 3984\nDPO AE 05132',
},
    'key90312': 'value43198',
    'key49610': 'value13083',
    'key48638': 'value15432',
    'key86787': 'value47796',
    'key62585': 'value17062',
},
    {
    'id': 17527486677216,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Patrick Lucas',
    'address': '9707 Jessica Squares Suite 657\nPort Pamela, KY 31594',
    'text': 'Cup service car brother hair drug light.\nMedia real news player scientist natural investment media. Which analysis instead offer. Which customer age history ready challenge.',
    'email': 'jamescraig@example.net',
    'phone_number': '(822)648-9889x2389',
    'json': {
    'name': 'Michelle Johnson',
    'address': 'PSC 7741, Box 6541\nAPO AE 14652',
},
    'key14607': 'value911',
    'key24782': 'value67982',
    'key89391': 'value19114',
    'key46119': 'value79806',
    'key74260': 'value83765',
    'key92554': 'value89713',
    'key6410': 'value3299',
},
    {
    'id': 17527486677226,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Mary Lewis',
    'address': '93380 Gardner Pike\nWest Matthew, WI 43673',
    'text': 'Hard group mother money.\nGrowth cut our machine. Yet serve to none across.\nAgain environmental into particular apply their thousand. Decide common direction mission.',
    'email': 'scottbeasley@example.org',
    'phone_number': '(491)775-2563x362',
    'json': {
    'name': 'Melissa Ball',
    'address': '3528 Sutton Pike\nNorth Douglas, OR 38556',
},
    'key41776': 'value17448',
    'key53369': 'value33214',
},
    {
    'id': 17527486677237,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Joseph Johnson',
    'address': '2041 Carl Glen\nNorth Julie, TX 55738',
    'text': 'Here tonight lay. Cost either building great. Car say fill not believe.',
    'email': 'allisonanderson@example.net',
    'phone_number': '893-673-2921',
    'json': {
    'name': 'Tiffany Johnson',
    'address': '02030 Morgan Plains\nHaastown, VA 85556',
},
    'key35338': 'value77900',
    'key90503': 'value10242',
    'key83794': 'value69613',
},
    {
    'id': 17527486677248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Christine Gomez',
    'address': '93226 Alexis Corners Apt. 445\nAndrewview, VT 97769',
    'text': 'Yes talk the service must dinner conference. Left rich concern consider. Read throughout theory color collection difference.',
    'email': 'patelvalerie@example.net',
    'phone_number': '001-584-666-2378x007',
    'json': {
    'name': 'Jaime Thomas',
    'address': '127 Clark Forest\nNorth Adamburgh, ID 54019',
},
    'key45917': 'value62557',
    'key93641': 'value81458',
    'key54165': 'value82575',
    'key29064': 'value36296',
},
    {
    'id': 17527486677259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Ashley Montoya',
    'address': '16102 Steven Mission Suite 211\nRamirezfurt, NC 23134',
    'text': 'Girl green food theory. Movie little dog tonight business kind. Rule eye state manage huge. Various industry also daughter four dark citizen.',
    'email': 'christopher09@example.org',
    'phone_number': '(986)600-0832',
    'json': {
    'name': 'Jill Johnston',
    'address': '881 Christopher Brook Suite 753\nPort Victor, ND 42048',
},
    'key17040': 'value28309',
},
    {
    'id': 17527486677270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Ashley Miller',
    'address': 'USCGC Edwards\nFPO AE 60192',
    'text': 'Movie player relate set bar marriage strategy enough. Tonight Democrat energy magazine. Per relate president.\nWhere field final quite. Than along edge century.',
    'email': 'lisa87@example.com',
    'phone_number': '+1-327-925-9381x95118',
    'json': {
    'name': 'Richard Harrison',
    'address': '2358 Rojas Ridges Suite 346\nPort Dylanshire, TN 08500',
},
    'key84215': 'value39707',
    'key48332': 'value15284',
    'key89777': 'value91632',
    'key37967': 'value63162',
    'key77022': 'value18359',
    'key97475': 'value88664',
    'key70372': 'value21608',
    'key52602': 'value99670',
    'key97728': 'value38195',
},
    {
    'id': 17527486677280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Amber Torres',
    'address': '440 Anderson Cliff\nDanielleberg, TN 30187',
    'text': 'Rest pick each issue red. Letter value whether way.',
    'email': 'daviesdouglas@example.net',
    'phone_number': '565-864-4226x468',
    'json': {
    'name': 'Alexis Clark',
    'address': '56806 Liu Shoals Apt. 812\nLake Martin, AK 92643',
},
    'key96538': 'value7938',
    'key6812': 'value70622',
    'key41446': 'value68903',
    'key22153': 'value88056',
},
    {
    'id': 17527486677291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Courtney Robinson',
    'address': '704 Ashley Trace\nSouth Regina, FM 16522',
    'text': 'Provide machine sort owner culture. Account second social light imagine join exist remain.\nSouth reduce civil throw. Pattern any cover report environmental back. Heart sure mean worry industry.',
    'email': 'kimberly37@example.com',
    'phone_number': '001-922-357-5039x6169',
    'json': {
    'name': 'Mathew Hoffman',
    'address': '83767 Kathy Ports\nNorth Williamshire, TX 59063',
},
    'key85754': 'value55695',
    'key76113': 'value19944',
    'key78265': 'value57634',
    'key45403': 'value36402',
    'key14079': 'value36638',
},
    {
    'id': 17527486677302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'John Gomez',
    'address': '7409 Stewart Knolls Apt. 347\nEast Matthew, MA 83224',
    'text': 'Until war so what identify ok. Amount news radio feeling local feel. On despite likely voice occur bed someone.\nHelp month form so. Big could occur where.',
    'email': 'logan49@example.com',
    'phone_number': '(208)633-4578',
    'json': {
    'name': 'Robert Bradshaw',
    'address': 'USCGC Ray\nFPO AE 80728',
},
    'key11296': 'value18806',
    'key25072': 'value41631',
    'key61943': 'value29',
    'key46728': 'value63405',
    'key64398': 'value13419',
    'key66879': 'value13384',
    'key92608': 'value9483',
    'key9724': 'value4963',
},
    {
    'id': 17527486677311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Jimmy Neal',
    'address': '736 Eric Falls\nRossside, NV 60490',
    'text': 'Become attorney onto at feeling view.\nRate interest network tonight make vote. What building it election then song total.\nAttack best her. Model might become analysis officer.',
    'email': 'robertbarber@example.org',
    'phone_number': '+1-882-800-0509x152',
    'json': {
    'name': 'Michele Smith',
    'address': '163 Faulkner Throughway\nLake Jacob, WV 73817',
},
    'key48855': 'value29464',
    'key95087': 'value29575',
    'key65721': 'value50028',
    'key56639': 'value40872',
    'key42180': 'value34158',
    'key23155': 'value5117',
},
    {
    'id': 17527486677323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Theresa Lynch',
    'address': '9554 Fernandez Garden Apt. 657\nPamelabury, KY 40418',
    'text': 'Half seem agreement. Information beyond process special. Cultural question only how.\nShould police week tax. Take hand serve trouble truth power allow. Sell senior own play long food short former.',
    'email': 'watkinspeter@example.net',
    'phone_number': '(271)966-6475x98755',
    'json': {
    'name': 'Lance Johnson',
    'address': 'Unit 4518 Box 3034\nDPO AA 21412',
},
    'key67965': 'value20432',
    'key23092': 'value40990',
    'key95715': 'value23958',
    'key3410': 'value90267',
    'key84278': 'value62174',
    'key63258': 'value5622',
    'key35577': 'value89414',
    'key71084': 'value43711',
},
    {
    'id': 17527486677332,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Tyler Brown',
    'address': '4456 Gentry Squares Suite 395\nNew Brandonchester, GA 44057',
    'text': 'And expert situation throughout data idea second teacher. Some however anything north budget.\nScience response way leave suffer hope including dinner. Human writer part.',
    'email': 'carla61@example.com',
    'phone_number': '9453142955',
    'json': {
    'name': 'Joshua Ritter',
    'address': '132 Lewis Center Apt. 413\nMcdanieltown, NY 03029',
},
    'key28515': 'value98683',
    'key45756': 'value62315',
    'key74203': 'value99717',
    'key1579': 'value14578',
    'key5621': 'value96928',
},
    {
    'id': 17527486677343,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Bruce Hardy',
    'address': '161 Derek Dam\nHoffmanmouth, HI 04521',
    'text': 'Box professor recently professor. Ahead everything democratic rather budget.\nFloor season imagine. Project high firm manage amount.\nTonight image pressure like husband against cold.',
    'email': 'matthew90@example.net',
    'phone_number': '+1-655-550-4958x4649',
    'json': {
    'name': 'Beverly Jones',
    'address': '7620 Jones Ports\nEdwardton, DE 16916',
},
    'key95047': 'value33789',
    'key94171': 'value84965',
    'key78368': 'value72786',
    'key11231': 'value60782',
    'key36926': 'value75366',
    'key29588': 'value81804',
    'key74466': 'value60081',
},
    {
    'id': 17527486677354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Kimberly Garrison',
    'address': '19552 Wright Underpass\nEast Bruceside, TX 11264',
    'text': 'Writer scientist enough material set. Memory determine me assume.\nTree news performance while will. Forward second will state hospital another against.',
    'email': 'calhounrebecca@example.net',
    'phone_number': '001-761-847-0691x8689',
    'json': {
    'name': 'David Joseph',
    'address': '357 Mitchell Rue Apt. 124\nHansentown, GU 30964',
},
    'key94942': 'value31933',
    'key89220': 'value12930',
    'key1336': 'value13808',
    'key95820': 'value47006',
    'key83318': 'value41201',
    'key48261': 'value86137',
    'key70997': 'value37405',
},
    {
    'id': 17527486677366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Bryan Mckee',
    'address': '53667 Jennifer Pine\nGreerfurt, MS 56492',
    'text': 'Model system travel here address official. Others cultural human.\nFar cost sound. Energy child us appear range loss. Republican along case before.',
    'email': 'stephanie89@example.net',
    'phone_number': '737-658-4820',
    'json': {
    'name': 'Maria Adams',
    'address': '74548 George Parkway\nNew Michelleberg, WI 96400',
},
    'key59521': 'value7256',
    'key2485': 'value93996',
},
    {
    'id': 17527486677376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Karen Turner',
    'address': '4659 John Motorway Suite 430\nBradyview, WA 58646',
    'text': 'Upon talk small on reason. Speech billion able. Apply think new you action lawyer. Available place page pull discussion.',
    'email': 'alexanderoconnor@example.com',
    'phone_number': '001-896-776-8447x473',
    'json': {
    'name': 'Linda Porter',
    'address': 'Unit 5365 Box 0767\nDPO AE 11399',
},
    'key35884': 'value76303',
    'key40832': 'value31894',
    'key97741': 'value28708',
    'key36745': 'value79019',
    'key75183': 'value35351',
    'key55053': 'value59477',
    'key17174': 'value81297',
    'key11915': 'value1852',
    'key56145': 'value1802',
    'key43074': 'value3697',
},
    {
    'id': 17527486677386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Ellen Murphy',
    'address': '161 Bonilla Avenue\nLake Jacquelinebury, PA 79035',
    'text': 'Opportunity art event quite majority. Full our card resource list debate.\nYeah song process last economic laugh. Begin exactly thousand improve wear eight partner.',
    'email': 'vasquezbrent@example.com',
    'phone_number': '+1-724-340-5852x415',
    'json': {
    'name': 'Steven Powers',
    'address': '680 Anderson Squares\nSouth David, IN 17417',
},
    'key40795': 'value92186',
    'key91131': 'value41099',
},
    {
    'id': 17527486677397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Lori Tucker',
    'address': '9306 Johnson Haven\nPamelamouth, AL 33098',
    'text': 'Performance action community wall. Protect choose professional single. Account bed team however floor film.',
    'email': 'edward95@example.com',
    'phone_number': '926.970.4517',
    'json': {
    'name': 'Ashley Ellis',
    'address': '174 Williams Terrace\nAlexaside, SC 82576',
},
    'key60759': 'value85839',
    'key73595': 'value52478',
},
    {
    'id': 17527486677407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jennifer Jennings',
    'address': '307 Fisher Lane Suite 445\nSouth Rhondaburgh, CT 93704',
    'text': 'Mouth feel bad high. Maintain policy training line true difference responsibility visit. Return sea matter boy report that.\nFood indeed window take son. After yet result.',
    'email': 'fenglish@example.net',
    'phone_number': '614-651-7329x1710',
    'json': {
    'name': 'Rachel Rice',
    'address': '03240 Mallory Meadows\nEast Denise, PR 37381',
},
    'key42539': 'value9059',
    'key35419': 'value67760',
},
    {
    'id': 17527486677417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Joseph Wilson',
    'address': '054 May Plain\nNew Michelleville, MI 57617',
    'text': 'These everybody lose run. Design maintain environment success once situation leg. Let another challenge of instead.\nSell shoulder game rate minute. Management some direction different arrive.',
    'email': 'coreyrobles@example.org',
    'phone_number': '665-799-1599',
    'json': {
    'name': 'Peter Dillon',
    'address': '6404 Melissa Springs\nGrahammouth, DC 47738',
},
    'key131': 'value43747',
    'key74296': 'value62857',
    'key23287': 'value5062',
    'key1873': 'value83107',
    'key47374': 'value36900',
    'key85382': 'value69983',
    'key30220': 'value6292',
    'key51224': 'value77829',
    'key84786': 'value33109',
    'key98132': 'value44955',
},
    {
    'id': 17527486677429,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Desiree Harvey',
    'address': '23997 Lauren Road Apt. 178\nPort Rebeccamouth, VI 90898',
    'text': 'Garden hold value itself. Ground parent brother beat artist prepare nation example.\nListen fact recent white radio play. Sound past send argue war.',
    'email': 'harrisjulie@example.org',
    'phone_number': '357.344.6525x297',
    'json': {
    'name': 'Jennifer Mendoza',
    'address': '59579 Meyers Corner\nMichaelton, TN 96150',
},
    'key3165': 'value68874',
    'key74748': 'value79512',
    'key35939': 'value74717',
    'key52652': 'value65023',
    'key89980': 'value98705',
    'key29380': 'value21967',
},
    {
    'id': 17527486677440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Jacqueline Becker',
    'address': '87613 Karen Park\nWest Laurieland, PA 23104',
    'text': 'Down receive power beat citizen else. Year officer husband one.\nUnit process factor unit state cold. Item much garden often. Color nice interest these without serious.',
    'email': 'swhite@example.net',
    'phone_number': '+1-622-790-0279',
    'json': {
    'name': 'Krystal Hernandez',
    'address': 'Unit 0288 Box 1008\nDPO AP 09405',
},
    'key34920': 'value6631',
    'key37482': 'value13943',
    'key92404': 'value15490',
},
    {
    'id': 17527486677449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jonathan Fisher',
    'address': '5353 Angel Shoals Suite 179\nPerezberg, RI 91190',
    'text': 'Dream focus call among mean none sure. Debate production practice us heavy. Forward what prove develop worker wife save. Special kid important political.',
    'email': 'linda65@example.net',
    'phone_number': '001-922-502-9577x45083',
    'json': {
    'name': 'Patricia Estrada',
    'address': '864 Bowen Run Suite 256\nEast Christopher, MA 13172',
},
    'key50912': 'value64111',
    'key29362': 'value11230',
    'key61594': 'value62434',
    'key64863': 'value75031',
    'key86260': 'value95619',
    'key47948': 'value2649',
    'key14454': 'value8841',
},
    {
    'id': 17527486677460,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Roger Thompson',
    'address': '85758 Stewart Roads Suite 724\nSmithland, CA 50948',
    'text': 'Fire paper once past know accept new usually. Amount right amount hot also challenge.\nWrong represent shoulder seven general voice position. Six raise statement weight possible less.',
    'email': 'tmejia@example.net',
    'phone_number': '+1-723-743-9865x440',
    'json': {
    'name': 'Joshua Sandoval',
    'address': 'USNS Huff\nFPO AE 46187',
},
    'key53056': 'value92831',
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
    'RequestId': '110dd8c8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_41_599052RUsVwTVr',
    'filter': 'uid > -100 and uid < 100',
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
    'RequestId': '110dd8c8-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_41_599052RUsVwTVr',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752748674.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid100AndUid1001752748674Json()
    test.run_tests()
