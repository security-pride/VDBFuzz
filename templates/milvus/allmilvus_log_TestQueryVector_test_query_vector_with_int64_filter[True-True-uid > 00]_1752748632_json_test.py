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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 00]_1752748632_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 00]_1752748632.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid001752748632Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 00]_1752748632.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 00]_1752748632.json"
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
    'data': [
    {
    'id': 17527486236014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Rachel Thornton',
    'address': '285 Margaret Meadows\nWilliamberg, SD 56806',
    'text': 'Expert top boy student we once week. Site much low. Spring think go yet once form.\nMy reduce night leg. Wish PM then yes challenge. Big home seem support information year. Step stock professional.',
    'email': 'ymiller@example.org',
    'phone_number': '+1-539-711-3080x069',
    'json': {
    'name': 'Matthew Arias',
    'address': 'Unit 3306 Box 8663\nDPO AE 75488',
},
    'key31383': 'value59005',
    'key84430': 'value11954',
    'key56352': 'value70777',
},
    {
    'id': 17527486236028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Andrew Barrett',
    'address': '10531 Olsen Point\nNorth Justin, DE 10554',
    'text': 'Task individual offer guy power station the shoulder. Win community seek now shake actually machine. Pattern professor television action usually.',
    'email': 'caldwellcraig@example.net',
    'phone_number': '(495)494-9411x799',
    'json': {
    'name': 'Robert Valencia',
    'address': '90031 Stacy Prairie\nWest Edwin, NY 95027',
},
    'key65810': 'value4986',
    'key57352': 'value92723',
    'key75355': 'value43882',
    'key85900': 'value58143',
    'key82102': 'value99173',
    'key26442': 'value47031',
    'key4847': 'value31644',
},
    {
    'id': 17527486236041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Lauren Lucero',
    'address': '289 Stewart Mount\nTimothyberg, VA 05736',
    'text': 'Chance hear agency. Recognize talk certainly then.\nDo throughout herself kid Republican. Check crime none air usually allow. Product ready their. Difficult young million special.',
    'email': 'craigmegan@example.net',
    'phone_number': '(529)513-1721x0764',
    'json': {
    'name': 'John Horne',
    'address': '83781 Sergio Isle\nDavidfort, NC 52399',
},
    'key20621': 'value12735',
    'key28651': 'value76929',
    'key76987': 'value28638',
    'key3295': 'value19624',
    'key52121': 'value91543',
    'key88289': 'value4737',
},
    {
    'id': 17527486236053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'William Hubbard',
    'address': '346 Ruiz Ville\nNancyton, UT 55772',
    'text': 'Glass fear school agreement. Wall executive we trial.\nComputer vote himself since last would material. Low summer sometimes. Improve hit what.',
    'email': 'coleashley@example.com',
    'phone_number': '924.786.3968x4918',
    'json': {
    'name': 'Felicia Branch',
    'address': '953 Parker Ports Suite 035\nAshleyland, OH 79566',
},
    'key50902': 'value62612',
},
    {
    'id': 17527486236066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Jeremiah Hernandez',
    'address': '9255 Victoria Roads Suite 967\nLake Kristina, AZ 05832',
    'text': 'Citizen catch draw picture brother strategy. Bad quite color charge. Fill certain too yard like myself. Perform manager room.',
    'email': 'john72@example.com',
    'phone_number': '898-690-5360x7022',
    'json': {
    'name': 'Melissa Wright',
    'address': '215 Thomas Club Apt. 909\nKristimouth, NC 08126',
},
    'key750': 'value36655',
    'key53055': 'value21042',
    'key87040': 'value51385',
    'key61469': 'value57947',
},
    {
    'id': 17527486236078,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jennifer Gutierrez',
    'address': '48631 Pamela Bypass Apt. 995\nEast Justin, SD 40194',
    'text': 'Country sign investment trip base war. Former talk far. Us page nation.\nWonder physical information play call guess.\nPainting role true three yard. Himself instead accept food happy.',
    'email': 'floydheather@example.com',
    'phone_number': '(680)657-8905x4778',
    'json': {
    'name': 'James Reid',
    'address': '21032 Dixon Trace Suite 598\nFergusonport, OR 77462',
},
    'key89563': 'value24101',
    'key13577': 'value67395',
    'key50265': 'value18419',
    'key20773': 'value47935',
    'key42479': 'value54229',
    'key42749': 'value87228',
},
    {
    'id': 17527486236091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Tyler Griffith',
    'address': '3428 Ramsey Roads\nPort Raymondside, DE 26272',
    'text': 'Especially assume no nature wife. Sense property read community animal.\nKnow during letter cut while weight star. About on benefit go.\nReceive develop red plant myself buy reason.',
    'email': 'umoreno@example.net',
    'phone_number': '864.651.9109',
    'json': {
    'name': 'Mark Hanson',
    'address': '963 Michael Plain Suite 278\nNorth Amanda, IA 05424',
},
    'key46002': 'value13726',
    'key32409': 'value45450',
    'key75897': 'value78358',
    'key15763': 'value51250',
    'key17734': 'value16367',
    'key78546': 'value53588',
    'key25569': 'value63116',
},
    {
    'id': 17527486236103,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Philip Grant',
    'address': '2788 Tammy Hill\nVictorberg, RI 35584',
    'text': 'Perhaps personal however performance also either. True long industry customer.\nSeveral run budget bank area even. Way product including citizen head everybody.',
    'email': 'michaelwells@example.net',
    'phone_number': '492-285-9995x14450',
    'json': {
    'name': 'Frank Wolf',
    'address': '6413 Clark Avenue Suite 008\nPort Scott, NE 38718',
},
    'key14140': 'value864',
    'key33220': 'value18461',
    'key92450': 'value87285',
    'key26360': 'value65010',
    'key8767': 'value82854',
    'key98972': 'value43684',
},
    {
    'id': 17527486236116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jason Casey',
    'address': '693 Stacey Stream Suite 122\nHughesside, WY 02202',
    'text': 'Relate shake rest ever. Player tell especially party score happen. Service degree speak range newspaper.',
    'email': 'jeremyfernandez@example.com',
    'phone_number': '432.927.8783x249',
    'json': {
    'name': 'Melissa Hall',
    'address': '142 Johnston Turnpike Suite 196\nMccoyland, LA 01780',
},
    'key72423': 'value38613',
    'key62364': 'value23064',
    'key75958': 'value2203',
    'key83826': 'value95942',
    'key54188': 'value66741',
    'key94802': 'value23140',
},
    {
    'id': 17527486236131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Kelly Stout',
    'address': '63305 Morton Extension Apt. 750\nShariport, SD 86662',
    'text': 'Window defense never yes large health. Art administration strategy support wide put. Detail event audience film.\nSound believe live evening. Name record top class owner owner lose.',
    'email': 'tylerking@example.org',
    'phone_number': '(515)312-2164',
    'json': {
    'name': 'Alison Andrews',
    'address': '159 Brenda Cliffs Apt. 592\nGlovershire, PR 49851',
},
    'key63983': 'value61969',
    'key38917': 'value35734',
    'key11116': 'value62026',
    'key55667': 'value27770',
    'key1301': 'value92760',
    'key95965': 'value6178',
    'key70506': 'value39546',
    'key47027': 'value81291',
},
    {
    'id': 17527486236145,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Rebecca Henderson',
    'address': '57323 Jones Road Apt. 388\nPort Benjamin, MD 33880',
    'text': 'Assume store sign many field. Improve body factor first prepare. Issue husband wind role under whatever ok happen.\nFight others us news civil per anyone. Suddenly example information stock special.',
    'email': 'robinsonjeffrey@example.org',
    'phone_number': '913-843-9488x5751',
    'json': {
    'name': 'Sandra Jones',
    'address': '5435 Love Square\nPatelfurt, WY 50348',
},
    'key635': 'value10883',
    'key85429': 'value52391',
},
    {
    'id': 17527486236160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Dana Beck',
    'address': '39444 Amy Islands Apt. 441\nNorth Mitchellfort, GU 96130',
    'text': 'Six drive however water hope resource side understand. Young tax Mr evidence particularly. Respond establish cell thing hour training.',
    'email': 'wbecker@example.org',
    'phone_number': '+1-288-894-7252x832',
    'json': {
    'name': 'Laura Moran',
    'address': '7932 Joe Islands Suite 045\nTaraborough, NE 82703',
},
    'key21924': 'value53202',
    'key30177': 'value76821',
},
    {
    'id': 17527486236172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Anthony Thomas',
    'address': '0197 Chavez Ways\nLake Kyleport, WI 40381',
    'text': 'Less blood help minute cup activity if law. Opportunity within single pressure. Threat Mrs design major old attention. Middle general name year little impact.\nStructure answer official wide sort.',
    'email': 'santiagoveronica@example.com',
    'phone_number': '+1-423-386-5080x182',
    'json': {
    'name': 'Victor Taylor',
    'address': '7524 Scott Wall Suite 082\nTammyborough, SC 53256',
},
    'key28700': 'value15774',
    'key59626': 'value28587',
    'key6546': 'value35998',
    'key48886': 'value77343',
    'key72452': 'value97023',
    'key13514': 'value20993',
    'key45220': 'value91665',
},
    {
    'id': 17527486236186,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Kaitlyn Johnson',
    'address': 'USNV Lee\nFPO AA 14300',
    'text': 'Often reduce provide bag painting section. Science word southern throw middle.\nSomebody management seven few guess else dream. Election enter best them behind. Table until baby move similar.',
    'email': 'morganharris@example.net',
    'phone_number': '001-568-599-7857x68854',
    'json': {
    'name': 'David Roberts',
    'address': '9705 Strong Meadows Suite 489\nNorth Ricky, SC 97232',
},
    'key94812': 'value12267',
    'key12982': 'value52932',
},
    {
    'id': 17527486236198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Shane Smith',
    'address': '240 Emily Court Suite 657\nJonesburgh, MT 15236',
    'text': 'Fight magazine crime that decision including card claim. Throw be win situation positive traditional economic. Space close right other then Republican. Prevent six college carry degree.',
    'email': 'ruben82@example.net',
    'phone_number': '(855)399-4743',
    'json': {
    'name': 'Elizabeth Conway',
    'address': '0008 Burton Valley\nWest Paul, DE 63231',
},
    'key3356': 'value28006',
    'key5409': 'value63097',
    'key12506': 'value97438',
    'key36573': 'value12884',
    'key37738': 'value25632',
    'key54132': 'value96325',
    'key77258': 'value88549',
    'key54071': 'value33353',
    'key91880': 'value58071',
    'key56873': 'value51344',
},
    {
    'id': 17527486236211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'David Parker',
    'address': '26745 Olson Oval Apt. 532\nPort Teresastad, FL 97317',
    'text': 'Letter before could site may. Choice PM through majority. City two teach themselves.\nPartner leader up second contain. Assume anyone prove hear. Remain above project born explain through.',
    'email': 'carrie43@example.net',
    'phone_number': '(901)836-7371x28454',
    'json': {
    'name': 'Sharon Salinas',
    'address': '864 Eric Forges Suite 688\nEast Katelynmouth, AL 07419',
},
    'key65473': 'value67199',
    'key99133': 'value59585',
    'key89475': 'value89684',
    'key77238': 'value35454',
},
    {
    'id': 17527486236221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Amber Barajas',
    'address': '92953 Darius Route Apt. 495\nNew Andrewfurt, IL 11111',
    'text': 'Any bad similar total. Even key black social our including.\nImportant peace moment check material its push. Good family leave fall song edge.\nBy about art pick three issue whose.',
    'email': 'savannah56@example.net',
    'phone_number': '(691)856-9760x9905',
    'json': {
    'name': 'Gregory Nelson',
    'address': '40026 Farrell Port\nHernandezton, MT 60699',
},
    'key60386': 'value32588',
    'key65114': 'value7123',
},
    {
    'id': 17527486236232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Justin Rivera',
    'address': '2921 Robin Mountain Suite 881\nNew Richardstad, PR 58934',
    'text': 'Cultural beyond shoulder organization. Large read amount. Space think involve expect. We computer maintain lot cost.',
    'email': 'brucerose@example.com',
    'phone_number': '505-764-6439',
    'json': {
    'name': 'Jamie Martinez',
    'address': '46937 Brown Manor Suite 463\nCaseyview, OH 20012',
},
    'key62654': 'value23626',
    'key80067': 'value17315',
    'key94248': 'value38537',
    'key60403': 'value53036',
    'key51538': 'value21979',
    'key34860': 'value86218',
    'key17899': 'value46788',
    'key95214': 'value44953',
},
    {
    'id': 17527486236244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Mary King',
    'address': '2500 Christopher Lane\nRosariostad, WI 01067',
    'text': 'Present ball through owner decide industry. Prove record side hold. Color white west civil analysis east.',
    'email': 'hodgesjoe@example.org',
    'phone_number': '328.696.0953x77642',
    'json': {
    'name': 'Daniel Heath',
    'address': '33777 Jenna Freeway\nSouth Danielchester, VI 94173',
},
    'key56045': 'value37473',
    'key89051': 'value65468',
    'key94302': 'value91610',
    'key61058': 'value20089',
    'key89482': 'value38937',
    'key54314': 'value37376',
    'key58468': 'value94336',
    'key40007': 'value81067',
    'key2520': 'value39011',
    'key67361': 'value48782',
},
    {
    'id': 17527486236256,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Kaitlyn Reyes',
    'address': '5283 Orr Turnpike\nNew Cindytown, MI 97841',
    'text': 'Instead much society maintain. Past know interesting owner each short.\nManager happy long watch majority.\nCapital cost story responsibility resource including. Truth must black it often ground.',
    'email': 'kennethsaunders@example.com',
    'phone_number': '+1-958-651-2886x68261',
    'json': {
    'name': 'Gary Vaughn',
    'address': '157 Leslie Falls\nNew Sarah, MA 41286',
},
    'key21363': 'value9902',
    'key23945': 'value68734',
    'key24054': 'value49591',
    'key74612': 'value44185',
    'key89458': 'value72773',
    'key44933': 'value40729',
    'key50246': 'value96939',
    'key2029': 'value43584',
    'key87273': 'value68302',
},
    {
    'id': 17527486236268,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Tony Lang',
    'address': '084 Bates Bridge Suite 116\nFullerport, PR 00850',
    'text': 'Kitchen TV gas. Month similar certain. Already social ready safe. Own be man far treatment thus let cultural.\nScientist soon both low hear receive few. Lose political into. Arm behind stay too might.',
    'email': 'ewerner@example.org',
    'phone_number': '001-349-697-8768x2550',
    'json': {
    'name': 'Amber Sims',
    'address': '41953 Jones Radial\nAlexandriafort, AK 56467',
},
    'key16814': 'value99997',
},
    {
    'id': 17527486236279,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Dana Lee',
    'address': 'Unit 5337 Box 7398\nDPO AA 67550',
    'text': 'Hit walk share. Teacher simply reach house country. Sense board walk court glass across.',
    'email': 'antonio08@example.net',
    'phone_number': '+1-490-333-9377x74619',
    'json': {
    'name': 'Rachel Huffman',
    'address': 'PSC 5288, Box 6714\nAPO AE 54071',
},
    'key8352': 'value31644',
},
    {
    'id': 17527486236286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Stephen Massey',
    'address': '34615 Ruiz Islands Suite 052\nNorth Robert, MA 42724',
    'text': 'Team war kind behavior.\nReach quite country stop assume know. Debate hundred light speak site small. Walk according report ever.\nStand continue computer campaign all class. Alone a find maybe.',
    'email': 'yhansen@example.org',
    'phone_number': '001-445-804-9561',
    'json': {
    'name': 'Isaac Patel',
    'address': 'Unit 5271 Box 7733\nDPO AE 01099',
},
    'key97341': 'value24108',
    'key19529': 'value93514',
    'key53709': 'value52987',
    'key75242': 'value91460',
    'key13022': 'value41219',
    'key79690': 'value89991',
},
    {
    'id': 17527486236295,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Preston Lane',
    'address': '20225 Aaron Junctions\nNew Jennifer, FM 87867',
    'text': 'Better story plan conference by soldier financial. Toward line audience sit mind.',
    'email': 'parkergary@example.org',
    'phone_number': '558.223.8155',
    'json': {
    'name': 'Andrew Pitts',
    'address': '346 Hall Crest\nWest Michealport, KY 46405',
},
    'key62609': 'value36120',
    'key60545': 'value48348',
    'key4150': 'value3494',
},
    {
    'id': 17527486236306,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Amy Moore',
    'address': 'PSC 2026, Box 2209\nAPO AA 53888',
    'text': 'Artist man admit history agreement training than. Huge case by fish open rate down.\nSince event billion buy night. Full within serve structure hotel. Respond rate science.',
    'email': 'mollybrown@example.com',
    'phone_number': '671-914-7234',
    'json': {
    'name': 'Anna Lee',
    'address': '38131 Taylor Falls\nNorth Heatherbury, GA 17145',
},
    'key8019': 'value89279',
    'key97011': 'value60329',
    'key10168': 'value97662',
    'key74060': 'value47510',
    'key36152': 'value53125',
    'key72637': 'value23025',
    'key85382': 'value19811',
    'key40669': 'value60619',
},
    {
    'id': 17527486236316,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Andre Nguyen',
    'address': '7678 Erin Creek Apt. 852\nPort Jamestown, FL 58049',
    'text': 'Station education between form later identify bad word. Property avoid prepare.\nEnvironment tend color manager college culture election sense. Thus Congress make provide.',
    'email': 'patrick35@example.org',
    'phone_number': '+1-528-967-4764',
    'json': {
    'name': 'Sarah James',
    'address': '7207 Ernest Landing Suite 718\nWalkerchester, PA 45296',
},
    'key16325': 'value48055',
    'key29126': 'value11144',
    'key71337': 'value47578',
    'key14448': 'value32091',
    'key89297': 'value54518',
},
    {
    'id': 17527486236326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'William Burgess',
    'address': '497 Angelica Loop Suite 052\nWest Bobmouth, VI 38809',
    'text': 'Or enough get weight take other use similar. Chance have decision easy. Fill stop almost serve early but.',
    'email': 'kayla24@example.net',
    'phone_number': '709.205.5851x87062',
    'json': {
    'name': 'John Zimmerman',
    'address': '52353 Christopher Viaduct Suite 082\nSouth Erin, AL 58944',
},
    'key74286': 'value34950',
    'key30963': 'value8112',
},
    {
    'id': 17527486236336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'John Parrish',
    'address': '3139 Goodwin Mountain\nNew Meganhaven, RI 95612',
    'text': 'Century never management certainly heavy group your. Modern money decade style property. Drive free person many up.\nRest huge agency small. South character increase cup.',
    'email': 'audreyfields@example.net',
    'phone_number': '635-410-0616',
    'json': {
    'name': 'Allison Williams',
    'address': '3472 Alexandra Forge Apt. 391\nDonnaborough, MI 76501',
},
    'key25158': 'value52055',
    'key39592': 'value37314',
    'key29536': 'value61713',
    'key84213': 'value38300',
    'key94024': 'value30433',
    'key16389': 'value39694',
    'key48390': 'value60382',
    'key74512': 'value11301',
},
    {
    'id': 17527486236347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Eric Frazier',
    'address': '40242 Cruz Causeway Suite 818\nClaytonton, HI 56637',
    'text': 'Ask include leg affect season. Draw turn others PM.\nPopular live than cover industry morning imagine. Art network other prove. Really think tree. Oil group discover good image threat.',
    'email': 'jordanleon@example.org',
    'phone_number': '646.928.6641',
    'json': {
    'name': 'Jeffery Armstrong',
    'address': '14209 Keith Pike Suite 806\nPort Bradyville, IA 85836',
},
    'key48041': 'value48189',
    'key52973': 'value40458',
    'key83078': 'value45878',
    'key54470': 'value68870',
},
    {
    'id': 17527486236358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Tracy Burke',
    'address': '510 Brandon Springs Apt. 598\nStuartview, GA 65989',
    'text': 'Bad true agree paper. Yard discussion window order notice discuss yet.\nFree team point week environmental region. Nearly four couple carry care money that. Explain save account eye.',
    'email': 'samuel28@example.net',
    'phone_number': '(660)903-0953',
    'json': {
    'name': 'Christina Johnson',
    'address': '6542 Silva Falls Apt. 605\nPort Caroline, CO 96279',
},
    'key38046': 'value99022',
    'key44345': 'value74807',
    'key75674': 'value85953',
    'key14609': 'value94860',
},
    {
    'id': 17527486236369,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'James Romero',
    'address': '4633 Robert Neck\nNew Julie, NM 24804',
    'text': 'Person knowledge describe month owner medical trade. Bill ago air night woman. Front first best.\nSeason town issue so. Movie go learn best.',
    'email': 'jamescarla@example.net',
    'phone_number': '342.706.8142x7925',
    'json': {
    'name': 'Pamela Drake',
    'address': 'USNS Campbell\nFPO AE 57624',
},
    'key78498': 'value63522',
    'key81172': 'value82271',
    'key25194': 'value48551',
    'key6359': 'value62315',
    'key31814': 'value28408',
    'key92636': 'value30093',
    'key52028': 'value39479',
},
    {
    'id': 17527486236379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Ryan Rojas',
    'address': '00197 Turner Divide\nLake Katrinafort, OH 29666',
    'text': 'East with until his color. Million often will need. Simply call but bank trip couple. Gas around hair bank difference hear.',
    'email': 'davidtaylor@example.net',
    'phone_number': '738-284-8152x845',
    'json': {
    'name': 'Timothy Brown',
    'address': '91135 Jeffery Summit Apt. 974\nPort Nicole, VA 68167',
},
    'key41834': 'value64729',
    'key62411': 'value8008',
    'key75140': 'value25969',
},
    {
    'id': 17527486236391,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'John Stein',
    'address': 'USS Hutchinson\nFPO AP 67176',
    'text': 'See friend customer toward throughout major. A degree region morning try eye total. Street glass enjoy there.\nGive region concern under security throw. Thing save its inside keep.',
    'email': 'pwilliams@example.net',
    'phone_number': '564.806.6028',
    'json': {
    'name': 'Derrick Herman',
    'address': '14754 Mark Islands\nNorth Andrewstad, AL 53445',
},
    'key26527': 'value58713',
    'key32598': 'value71857',
    'key1607': 'value55452',
},
    {
    'id': 17527486236400,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Rachel Johnson',
    'address': '78832 Jennifer Lock Suite 005\nSouth Rogerfurt, ND 49072',
    'text': 'Phone together rich throughout skin. West right something recently. Bag thing really affect state quality together. Necessary visit camera.',
    'email': 'mirandatimothy@example.org',
    'phone_number': '933.356.8438',
    'json': {
    'name': 'Christopher Hayden',
    'address': 'USS Delgado\nFPO AE 88663',
},
    'key27683': 'value46481',
    'key41969': 'value95322',
    'key83815': 'value78008',
},
    {
    'id': 17527486236410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Jason Kelly',
    'address': '9974 Armstrong Streets Apt. 868\nNew Sethtown, NC 38435',
    'text': 'Consumer entire month. Moment at eat usually present. Get career up everybody participant significant.',
    'email': 'warrenelizabeth@example.net',
    'phone_number': '+1-923-977-5733x786',
    'json': {
    'name': 'Richard Moran',
    'address': 'PSC 3387, Box 2857\nAPO AP 98207',
},
    'key91083': 'value39117',
    'key67204': 'value67090',
    'key8408': 'value66284',
    'key75068': 'value43380',
    'key88296': 'value79472',
    'key72295': 'value73271',
    'key92841': 'value29292',
    'key53608': 'value47567',
    'key51250': 'value31860',
    'key75898': 'value36437',
},
    {
    'id': 17527486236420,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'John Gonzalez',
    'address': '3766 Christopher River Suite 708\nWilsonland, DE 31666',
    'text': 'Stop current consumer these. Quickly set the local focus.\nDrug task other quality minute mission. In quality question past per. Result learn spend wind turn address exactly.',
    'email': 'melissa17@example.com',
    'phone_number': '+1-329-780-8670',
    'json': {
    'name': 'Andrew Mueller',
    'address': '667 Burton Ridge Suite 382\nLake Devonbury, PR 57406',
},
    'key3635': 'value50297',
    'key1331': 'value91559',
},
    {
    'id': 17527486236430,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Julian Higgins',
    'address': '7974 Ramirez Isle Apt. 897\nSouth Brenda, GU 82537',
    'text': 'Recognize occur employee able through order about church. Number within quality describe story.',
    'email': 'teresawoods@example.org',
    'phone_number': '379-714-7045',
    'json': {
    'name': 'Michael Cole IV',
    'address': '68912 Rice Flat\nSouth Robert, MH 54316',
},
    'key86722': 'value99171',
    'key23541': 'value38361',
    'key29669': 'value77177',
    'key64542': 'value94815',
    'key28409': 'value57328',
    'key46339': 'value50213',
    'key93420': 'value27002',
    'key92335': 'value2899',
    'key86561': 'value11212',
},
    {
    'id': 17527486236442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Sheila King',
    'address': '6489 Johnson Mission Apt. 604\nJessicashire, MT 16042',
    'text': 'Final week see like work want contain. Little its partner hard. Move end or central special.',
    'email': 'derrickmoore@example.org',
    'phone_number': '876-627-9553x030',
    'json': {
    'name': 'Elizabeth Lopez',
    'address': '29447 Fisher Land\nSouth Joshuamouth, DE 12685',
},
    'key71658': 'value51728',
    'key71096': 'value55966',
    'key97128': 'value6834',
    'key34250': 'value83386',
    'key2331': 'value29030',
},
    {
    'id': 17527486236453,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Elizabeth Rivera',
    'address': '055 Robertson Lights\nHugheshaven, KS 09775',
    'text': 'Can affect all nature.\nAgainst message surface finally however process. Threat you special person around again. Church often watch size full walk.',
    'email': 'jacob68@example.net',
    'phone_number': '889.586.9891',
    'json': {
    'name': 'Zachary Johnson',
    'address': '93337 Tapia Lodge\nRoseside, ND 42453',
},
    'key10264': 'value81516',
},
    {
    'id': 17527486236464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Allen Proctor',
    'address': '7679 Madison Highway Suite 502\nWhiteland, IA 50940',
    'text': 'Mrs general various produce western. Help however friend either suddenly.\nWorker after determine sound born shoulder. Develop method score move. Past make force economy especially.',
    'email': 'walkersheryl@example.net',
    'phone_number': '001-947-715-9506x07304',
    'json': {
    'name': 'Molly Scott',
    'address': '56824 Mallory Rue\nMarymouth, MA 54896',
},
    'key73915': 'value57094',
    'key35672': 'value59576',
    'key26279': 'value59061',
    'key37394': 'value2339',
    'key75195': 'value68088',
},
    {
    'id': 17527486236476,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Tyler Peters',
    'address': '57129 Christopher Canyon\nNew Angelside, PA 02360',
    'text': 'Thing face girl paper pass service some. Low I why officer food. Foot write recent office.\nSuccessful hour bank guy whose have method. Which hope record. Notice visit doctor amount home top.',
    'email': 'sabrinawalker@example.org',
    'phone_number': '637.390.6098x76971',
    'json': {
    'name': 'Susan Young',
    'address': '0609 Williams Cliffs Suite 467\nWilkinsberg, IL 43755',
},
    'key63300': 'value83830',
},
    {
    'id': 17527486236488,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Kristy Smith',
    'address': '027 Rangel Skyway Suite 799\nCraigburgh, MS 57341',
    'text': 'Against now heavy democratic me financial person customer. Too resource interest event color.',
    'email': 'melissajohnson@example.net',
    'phone_number': '314.284.7356',
    'json': {
    'name': 'Christine Salazar',
    'address': '921 Steven Harbors\nPort Carmenmouth, HI 42272',
},
    'key98891': 'value76897',
    'key94496': 'value25104',
    'key68248': 'value29081',
    'key31777': 'value64572',
    'key65791': 'value44902',
    'key998': 'value42782',
},
    {
    'id': 17527486236499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Susan Hudson',
    'address': '0387 Heather Pines Suite 561\nEast Amy, KS 20545',
    'text': 'Fire glass whom their some. Class current air weight.\nPrevent wall chair look discover report successful. Ask yourself general bill.',
    'email': 'rclark@example.org',
    'phone_number': '795-257-0905x8260',
    'json': {
    'name': 'Cynthia Spence',
    'address': '725 Desiree Junction\nNorth Tracey, MI 49789',
},
    'key11611': 'value90566',
    'key42355': 'value11923',
    'key79135': 'value41739',
    'key93099': 'value70375',
    'key74358': 'value21821',
},
    {
    'id': 17527486236510,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Jeffrey Clayton',
    'address': 'USCGC Harris\nFPO AE 44819',
    'text': 'Inside receive color chair area sport. Summer nothing final ball PM whether daughter.\nCare else bar garden dinner he. Find accept feeling agency loss.',
    'email': 'elewis@example.org',
    'phone_number': '8312205702',
    'json': {
    'name': 'Matthew Herman',
    'address': '9038 Watson Garden\nLake Paul, TX 56443',
},
    'key6028': 'value95226',
    'key33790': 'value14333',
    'key59757': 'value58617',
    'key70941': 'value90233',
    'key57158': 'value57744',
    'key51510': 'value79104',
    'key70748': 'value75543',
    'key26727': 'value49567',
    'key18404': 'value62265',
},
    {
    'id': 17527486236520,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'John Steele',
    'address': 'USCGC Moyer\nFPO AA 44478',
    'text': 'Water again stock should. Forward employee dream system.\nWould huge direction. Cover nature whether we prepare against follow improve. Term company control single.',
    'email': 'bellpatricia@example.net',
    'phone_number': '6713281923',
    'json': {
    'name': 'Linda Gilmore',
    'address': '47788 Anthony Port\nVincentborough, DE 98913',
},
    'key46941': 'value44225',
},
    {
    'id': 17527486236530,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Scott Garcia',
    'address': '7975 Mccoy Courts Suite 240\nLake Jessicaview, GA 44595',
    'text': 'Surface store result eat. Family direction people store offer lot hit. Activity worry explain least fine especially.',
    'email': 'troy55@example.org',
    'phone_number': '+1-744-822-4290x03553',
    'json': {
    'name': 'Michael Webb',
    'address': '340 Adams Meadow Suite 989\nGuerratown, NY 30349',
},
    'key76930': 'value35184',
    'key99886': 'value23708',
    'key30478': 'value39539',
    'key34345': 'value6836',
    'key55120': 'value28100',
},
    {
    'id': 17527486236541,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Krista Roman',
    'address': '99227 Nicole Center\nAnnaborough, CO 60656',
    'text': 'Half per fact more. Civil ok mean than surface. May simple run pressure.\nPopulation remember office finish. Significant human fall state tonight. Mind city low own quite.',
    'email': 'jevans@example.com',
    'phone_number': '365.847.7545',
    'json': {
    'name': 'Travis Levine',
    'address': '340 Patel Center\nManuelton, DE 37172',
},
    'key96122': 'value16238',
    'key21553': 'value19829',
    'key33546': 'value87722',
    'key89534': 'value16701',
    'key56662': 'value50701',
    'key30502': 'value39980',
    'key87738': 'value1414',
    'key2607': 'value40170',
    'key8629': 'value83663',
    'key25453': 'value63281',
},
    {
    'id': 17527486236552,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Cody Mckenzie',
    'address': '608 Rich Mills\nNew Matthew, PR 11992',
    'text': 'Road wide might peace prevent forward drop. Floor wife Democrat on. Able themselves door discover customer. Weight method within however cost.',
    'email': 'usanchez@example.com',
    'phone_number': '001-601-751-9850x291',
    'json': {
    'name': 'Amy Cabrera',
    'address': '36002 Bell Vista Apt. 262\nHuberton, IN 08997',
},
    'key17032': 'value99443',
    'key15375': 'value30961',
    'key44803': 'value93712',
},
    {
    'id': 17527486236563,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Angel Braun',
    'address': '3371 Jessica Well\nPort Carrie, MT 57705',
    'text': 'Budget music but tax some government. Cell power two many. Else should window career. Red beat campaign character none when.',
    'email': 'peter90@example.net',
    'phone_number': '6684214073',
    'json': {
    'name': 'Kenneth Hatfield',
    'address': 'PSC 5671, Box 4972\nAPO AE 15531',
},
    'key39623': 'value93123',
    'key57700': 'value2063',
    'key43971': 'value96226',
    'key56058': 'value39206',
    'key58029': 'value20559',
    'key39475': 'value273',
    'key37395': 'value3927',
    'key38295': 'value70833',
    'key1391': 'value57107',
    'key73474': 'value68428',
},
    {
    'id': 17527486236572,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Ricky Pierce',
    'address': '3121 Trevino Ferry Apt. 399\nWest Jenniferland, IL 37872',
    'text': 'Concern important Mrs both. Water tree collection also surface red. Theory maintain increase measure create TV.\nReport not event great during. Indicate ask hour quickly read history today.',
    'email': 'pmartinez@example.net',
    'phone_number': '001-438-264-2492x31986',
    'json': {
    'name': 'Jason Wright',
    'address': '65062 Patton Parkway Apt. 030\nHughesland, KS 25860',
},
    'key41969': 'value8122',
    'key29291': 'value32179',
    'key65260': 'value807',
    'key4213': 'value18118',
},
    {
    'id': 17527486236583,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Elizabeth Wood',
    'address': '7885 Benjamin Brooks\nEatonport, MP 60159',
    'text': 'Onto market possible inside week what. Story range everyone. Since attack language night memory.\nHuge heavy show main. Bag newspaper sometimes group. Cell rest where drop what bring move.',
    'email': 'allenchristine@example.com',
    'phone_number': '001-267-455-0665x83676',
    'json': {
    'name': 'Philip Mcgee',
    'address': '216 Ingram Drive\nDuncanberg, DE 32054',
},
    'key84523': 'value8324',
    'key74300': 'value60237',
    'key6423': 'value29035',
    'key52320': 'value40091',
    'key10950': 'value35975',
},
    {
    'id': 17527486236594,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Karen Miller',
    'address': '84736 Elizabeth Mountain Apt. 815\nSmithstad, KY 69763',
    'text': 'Recognize already enter course. Want day production despite century take.\nTax personal week arrive lose next catch himself. Main black fine from that network particularly. Think wait ok.',
    'email': 'timothyhawkins@example.com',
    'phone_number': '+1-941-998-4892x9035',
    'json': {
    'name': 'Christopher Barron',
    'address': '95950 Brown Village\nEast Angelashire, DC 41096',
},
    'key99055': 'value74631',
    'key68692': 'value17494',
    'key57943': 'value81980',
    'key37453': 'value50782',
    'key44250': 'value34138',
    'key44934': 'value32696',
    'key47188': 'value71358',
    'key23407': 'value12676',
    'key17304': 'value5847',
},
    {
    'id': 17527486236606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Elizabeth Anderson',
    'address': '8244 Clayton Valleys Suite 273\nPort Jill, AK 50591',
    'text': 'Capital five plant game work. Will crime compare believe common board drug. See power subject protect market herself live.',
    'email': 'andrew13@example.com',
    'phone_number': '001-855-561-2082x36579',
    'json': {
    'name': 'Lisa Love',
    'address': '522 Smith Track\nSmithshire, AS 22209',
},
    'key34008': 'value66050',
    'key9057': 'value43327',
    'key10264': 'value55727',
    'key25861': 'value96572',
    'key36106': 'value75166',
},
    {
    'id': 17527486236617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Brad Strong',
    'address': '347 Nguyen Stream Suite 387\nPort Christopher, PW 33286',
    'text': 'Thank federal born theory toward our director box. Force nature above might writer will himself. Out tonight less network.',
    'email': 'cynthia84@example.com',
    'phone_number': '545.270.8439',
    'json': {
    'name': 'Michael Smith',
    'address': 'Unit 9788 Box 0382\nDPO AE 79004',
},
    'key70947': 'value66607',
    'key97839': 'value42475',
    'key48906': 'value3316',
    'key15360': 'value80298',
    'key3486': 'value25021',
},
    {
    'id': 17527486236626,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Charles Stevenson',
    'address': '01006 Ramirez Pines\nWernerburgh, MT 69845',
    'text': 'Eat bring adult stuff. Explain responsibility behind. Response visit blue region. Her before them like thought.\nCommercial hour add lot.',
    'email': 'christine70@example.org',
    'phone_number': '+1-956-588-9084x2932',
    'json': {
    'name': 'Thomas Rodriguez',
    'address': '931 Mitchell Wall\nMartinport, RI 99083',
},
    'key6013': 'value41072',
    'key25428': 'value72171',
    'key8137': 'value94195',
},
    {
    'id': 17527486236637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jamie Baker',
    'address': '54746 Colin Neck Apt. 804\nEast Sandra, NY 96371',
    'text': 'Mrs American ground product race maybe sell. Skill near just behind not baby.\nFrom structure beautiful course. Class action begin adult. End cover score inside chair station form send.',
    'email': 'alex59@example.net',
    'phone_number': '+1-731-648-5232x49180',
    'json': {
    'name': 'Troy Edwards',
    'address': '2179 Robinson Isle\nNorth Lori, RI 21783',
},
    'key59917': 'value15271',
    'key90648': 'value31239',
    'key56773': 'value55493',
    'key93157': 'value70534',
},
    {
    'id': 17527486236647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Erin Clark',
    'address': '295 Jacqueline Locks\nWest Frances, RI 51786',
    'text': 'Recent television break month anything continue fight. Financial answer type watch size space old.\nWest eight a card.\nLead improve them natural listen. End authority reduce entire.',
    'email': 'fsparks@example.net',
    'phone_number': '617-702-8358x73534',
    'json': {
    'name': 'Lori Turner',
    'address': '2624 Watkins Port\nWest Connietown, SC 80934',
},
    'key32742': 'value75316',
    'key58225': 'value52393',
    'key47318': 'value57845',
    'key91633': 'value80330',
    'key14268': 'value31690',
},
    {
    'id': 17527486236658,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Sarah Chung',
    'address': '5396 Megan Hollow\nPort Karenstad, GA 63970',
    'text': 'Himself parent still avoid education. Today activity some everything.\nWatch now person car material. Black mission country eight administration.',
    'email': 'eddie10@example.net',
    'phone_number': '7525238843',
    'json': {
    'name': 'Melissa Scott',
    'address': '779 Baird Path\nWest Michaelmouth, MD 57592',
},
    'key27343': 'value75060',
    'key62778': 'value72644',
    'key76339': 'value85885',
    'key55357': 'value71195',
    'key9676': 'value64209',
    'key65579': 'value55391',
    'key43105': 'value18954',
    'key94990': 'value35762',
},
    {
    'id': 17527486236669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Michael Baker',
    'address': '644 Nelson Cove Suite 815\nNew Danielview, VI 66844',
    'text': 'Both forward deal father nor around affect. Woman edge left maintain establish five.\nStatement others best far step. Human unit not later have wonder.',
    'email': 'ehicks@example.org',
    'phone_number': '900-523-0141',
    'json': {
    'name': 'Katherine Case',
    'address': '05419 Phillips Keys Apt. 048\nFreymouth, MI 08562',
},
    'key68160': 'value59471',
    'key53043': 'value85644',
    'key9683': 'value79502',
    'key99658': 'value43893',
    'key65245': 'value14981',
    'key84159': 'value15677',
    'key50825': 'value92978',
    'key56645': 'value16724',
},
    {
    'id': 17527486236680,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Karen Woods',
    'address': '4619 Garcia Shoal\nJessicaport, MH 98019',
    'text': 'Little customer will. Affect eight training strong single space. Picture perform send. Test ahead dog bill month forward.',
    'email': 'michaelallen@example.com',
    'phone_number': '9295054569',
    'json': {
    'name': 'Wendy Griffin',
    'address': '11089 King Islands\nNorth Karla, DE 64412',
},
    'key25883': 'value12266',
    'key8468': 'value66789',
    'key52205': 'value52585',
    'key10853': 'value5742',
    'key15628': 'value86048',
    'key55410': 'value15790',
    'key48053': 'value18776',
    'key5324': 'value41356',
},
    {
    'id': 17527486236692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Nicholas Hall',
    'address': '985 Meyer Dale\nWest Georgeton, PR 16784',
    'text': 'Memory maybe argue large picture my. Reach cost culture city suddenly play resource.',
    'email': 'david06@example.org',
    'phone_number': '5893833064',
    'json': {
    'name': 'Lisa Lee',
    'address': '10842 Lindsay Inlet\nCharlesmouth, MD 79439',
},
    'key8754': 'value99406',
    'key8216': 'value14887',
    'key77580': 'value77356',
},
    {
    'id': 17527486236702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Joseph Harrison',
    'address': 'PSC 5790, Box 5005\nAPO AA 09232',
    'text': 'Them seven star report board artist include least. Thing base piece number young into.\nGuy miss put world maybe or. Arrive school plan modern head avoid.',
    'email': 'coryramirez@example.net',
    'phone_number': '001-693-603-4000',
    'json': {
    'name': 'Zachary Weber',
    'address': '324 William Point\nEast Pamela, HI 92410',
},
    'key90001': 'value46895',
    'key4063': 'value49537',
},
    {
    'id': 17527486236710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Laura White',
    'address': 'Unit 2101 Box 4682\nDPO AA 72116',
    'text': 'Trade type traditional various place. Imagine development southern woman trip behavior. Painting bill traditional home.',
    'email': 'kristin59@example.org',
    'phone_number': '294.309.8705x088',
    'json': {
    'name': 'Paul Lee',
    'address': '07348 Kenneth Mews\nRebeccaport, CT 62492',
},
    'key56988': 'value31617',
    'key71326': 'value58709',
    'key32346': 'value39250',
    'key67221': 'value60540',
    'key45655': 'value32349',
    'key6161': 'value3448',
    'key41510': 'value70084',
    'key50919': 'value38358',
    'key4822': 'value37769',
    'key57275': 'value73190',
},
    {
    'id': 17527486236719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Christina Boyer',
    'address': '5218 Dodson Row\nMerrittville, TX 77881',
    'text': 'Sell produce Congress without idea. Wife central type difference.\nSingle remember game need. Agree share development tend. Much drug appear morning. Ok act account available walk player program.',
    'email': 'julianhampton@example.com',
    'phone_number': '362-396-0662x2556',
    'json': {
    'name': 'Joseph Mcgee',
    'address': '76704 Becker Forges\nLake Karenborough, TN 91880',
},
    'key66682': 'value10714',
    'key76404': 'value3793',
    'key90241': 'value99822',
    'key4490': 'value91823',
    'key81691': 'value91126',
    'key73179': 'value46973',
    'key11418': 'value91649',
    'key86369': 'value66385',
},
    {
    'id': 17527486236730,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Stephen Ellis',
    'address': 'Unit 0176 Box 4694\nDPO AA 98502',
    'text': 'Always thought nothing every group protect. Spend throw her protect once.',
    'email': 'pbenton@example.net',
    'phone_number': '(701)630-6193',
    'json': {
    'name': 'Molly Osborne',
    'address': '19935 Stewart Unions\nSouth Kathy, PR 84904',
},
    'key81425': 'value10999',
    'key86532': 'value61510',
    'key49854': 'value29728',
    'key65228': 'value81537',
    'key55530': 'value2020',
    'key70109': 'value34138',
},
    {
    'id': 17527486236739,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Bryan Krueger',
    'address': '80091 Marquez Mission\nNew Robert, TN 33629',
    'text': 'Price six attorney doctor Congress simply state. Agency black what option sound soldier. Reveal world family state.\nSit expect same provide. Relationship happy reduce.',
    'email': 'jjackson@example.net',
    'phone_number': '420.566.2566',
    'json': {
    'name': 'Haley Arnold',
    'address': '625 Vanessa Highway Suite 761\nJenkinsside, DC 11849',
},
    'key73738': 'value44533',
    'key28608': 'value5297',
    'key1258': 'value70379',
    'key24445': 'value64146',
},
    {
    'id': 17527486236750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'David Valentine',
    'address': '82577 Larry Forges Suite 760\nWillieport, PA 82858',
    'text': 'Town turn type resource off head group. What trouble off discuss.\nShow child particular. Easy everyone really middle top. Money style between agree economic top sister.',
    'email': 'lwalters@example.net',
    'phone_number': '+1-835-859-7587x869',
    'json': {
    'name': 'Mark Weaver',
    'address': '680 Conway Plain\nLake Matthewview, AZ 39432',
},
    'key83447': 'value9937',
    'key16069': 'value78305',
},
    {
    'id': 17527486236761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Matthew Johnson',
    'address': 'PSC 9821, Box 2544\nAPO AA 43837',
    'text': 'Apply employee much. Base not will gas painting serve any concern. Energy people both new provide protect.',
    'email': 'mejiajeffrey@example.com',
    'phone_number': '001-963-552-7190x5497',
    'json': {
    'name': 'David Houston',
    'address': '32661 Edward Ways\nNew Stevenmouth, VT 20130',
},
    'key30000': 'value65738',
    'key61113': 'value22413',
    'key34620': 'value89021',
    'key55168': 'value57871',
    'key52302': 'value11117',
    'key33222': 'value58370',
    'key69526': 'value50065',
    'key61501': 'value64208',
    'key3733': 'value69988',
    'key4660': 'value70774',
},
    {
    'id': 17527486236770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Ernest Meyer',
    'address': 'PSC 6545, Box 3002\nAPO AA 42759',
    'text': 'Full hair hundred resource. Tell executive away Mrs window dog free long. Admit word home window.\nVery score century. Thought hard machine green adult.',
    'email': 'jasonchen@example.net',
    'phone_number': '+1-507-734-3702',
    'json': {
    'name': 'Jeffrey Villa',
    'address': '083 Lawson Trail\nFrankborough, TX 04462',
},
    'key96623': 'value97534',
    'key64252': 'value26615',
    'key15239': 'value30772',
    'key57282': 'value64393',
},
    {
    'id': 17527486236779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jeffrey Carney',
    'address': '81024 Angela Curve\nSherryfurt, GU 96959',
    'text': 'Song I take available front language pattern. Enjoy list particular.\nVisit training feel charge. Herself increase nice.',
    'email': 'aprilmiller@example.net',
    'phone_number': '802.548.0470x75876',
    'json': {
    'name': 'Cathy Mills',
    'address': '347 Ronnie Neck Apt. 425\nCatherinetown, IL 42689',
},
    'key26862': 'value47799',
    'key46216': 'value14908',
    'key5343': 'value38493',
    'key68769': 'value8533',
},
    {
    'id': 17527486236791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Julie Yang',
    'address': 'PSC 1303, Box 8988\nAPO AP 50797',
    'text': 'Recent sort lawyer her nation pass customer. Magazine account owner ready. Alone middle often start them book.\nSend effort local recent line. Recent open TV so.',
    'email': 'lauren76@example.org',
    'phone_number': '786.267.2258x2029',
    'json': {
    'name': 'Ashley Davis',
    'address': '728 Stout Locks Suite 294\nReyesside, UT 78152',
},
    'key93010': 'value74655',
    'key1691': 'value41664',
    'key28912': 'value28878',
},
    {
    'id': 17527486236800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Matthew Thomas',
    'address': '5502 Wilson Forge Suite 189\nWest Zachary, CO 17336',
    'text': 'Hotel until least. Hold main goal stay occur executive list.\nDetail forward again reality source. Both remain include idea thank however. Letter animal three hold event.',
    'email': 'tmoss@example.com',
    'phone_number': '001-863-853-9150x19383',
    'json': {
    'name': 'Carrie Larson',
    'address': '220 Curtis Passage Apt. 525\nPort Melissaport, VT 10987',
},
    'key57861': 'value40002',
    'key41187': 'value56433',
    'key99306': 'value52894',
    'key68757': 'value28911',
    'key56375': 'value11416',
},
    {
    'id': 17527486236812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Steven Rocha',
    'address': 'PSC 7864, Box 2433\nAPO AE 36424',
    'text': 'Study level per own. Democratic thought that nothing true board organization. Investment bad staff produce walk.\nLess pretty main line per perhaps truth.\nOfficer that wall current gun.',
    'email': 'melindalarsen@example.org',
    'phone_number': '591-794-0934',
    'json': {
    'name': 'Cheryl Bell',
    'address': '6044 Perkins Mills Suite 303\nWest Nathanielberg, IA 49114',
},
    'key91217': 'value38707',
    'key83403': 'value37376',
    'key86369': 'value24131',
    'key11049': 'value7999',
    'key24745': 'value72604',
    'key17481': 'value66640',
    'key83965': 'value86365',
    'key14612': 'value7319',
},
    {
    'id': 17527486236823,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Phillip Murphy',
    'address': '19955 Duncan Walk\nSouth Connorbury, NY 53708',
    'text': 'Customer upon lot century.\nSister forget source relationship senior everything. Half pressure worker skin. Because society factor indeed day must hundred.',
    'email': 'markwallace@example.net',
    'phone_number': '834.309.8765',
    'json': {
    'name': 'Anthony Stephens',
    'address': '147 Rodriguez Fords\nNorth Annettemouth, SC 49208',
},
    'key8981': 'value97760',
},
    {
    'id': 17527486236836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Margaret Shields',
    'address': 'PSC 5108, Box 6277\nAPO AE 27581',
    'text': 'Born author data few. Find decide really mission. Also condition always voice lot pattern.\nControl lead experience short positive treat professional. Number recent adult security pull read research.',
    'email': 'jscott@example.org',
    'phone_number': '(313)760-8413x0916',
    'json': {
    'name': 'Christina Mcclain',
    'address': '555 William View Suite 413\nNorth Jessicafurt, AR 14605',
},
    'key93928': 'value73977',
    'key83490': 'value97489',
    'key19862': 'value77914',
    'key6354': 'value96614',
    'key60268': 'value25178',
    'key80760': 'value9560',
},
    {
    'id': 17527486236845,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Joseph Peters',
    'address': '78371 Bridges Ranch\nNorth Sherryshire, CO 49392',
    'text': 'Land whose young travel outside join. Hot song after man physical partner. Entire rest course development.',
    'email': 'jacob01@example.com',
    'phone_number': '953.201.6919x6876',
    'json': {
    'name': 'Jessica Collins',
    'address': '1341 Perez Streets\nNorth Craigfort, NH 45908',
},
    'key72477': 'value96192',
    'key30881': 'value57951',
    'key36178': 'value50351',
    'key81650': 'value48036',
    'key53103': 'value65901',
    'key37570': 'value10119',
    'key97770': 'value12057',
    'key44169': 'value89263',
    'key86949': 'value80287',
    'key41055': 'value80169',
},
    {
    'id': 17527486236857,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Thomas Lewis',
    'address': '88798 David Vista\nAbbottshire, MN 10265',
    'text': 'Bag think single scientist prove much morning. Close tax along lay surface house. Million dark point. Measure accept just court purpose view purpose.',
    'email': 'connorabbott@example.net',
    'phone_number': '(408)553-6997x699',
    'json': {
    'name': 'Denise Robertson',
    'address': '72658 Dennis Viaduct Apt. 150\nLake Kristin, KY 90968',
},
    'key31269': 'value69039',
    'key25947': 'value9680',
    'key44238': 'value57904',
    'key82926': 'value61872',
    'key41329': 'value15018',
    'key54342': 'value39991',
    'key67488': 'value45780',
    'key36254': 'value19066',
    'key9300': 'value64931',
},
    {
    'id': 17527486236869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'James White',
    'address': 'Unit 0689 Box 7311\nDPO AP 66691',
    'text': 'According field poor pay medical section travel.\nName north tax mother magazine fall voice. Development material star report often ever job.',
    'email': 'megansanchez@example.com',
    'phone_number': '(721)740-3193x19270',
    'json': {
    'name': 'Johnathan Navarro',
    'address': '649 Hall Squares Suite 522\nPhillipstown, MP 45611',
},
    'key66491': 'value53855',
},
    {
    'id': 17527486236880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Ryan Harris',
    'address': '627 Stephanie Port Suite 743\nSouth Jacqueline, CO 96811',
    'text': 'Protect economy performance now wonder result our. Capital Republican production environment relationship agent. Research Republican continue chair bit gas assume expert.',
    'email': 'longfrank@example.net',
    'phone_number': '001-569-811-2721x1288',
    'json': {
    'name': 'Walter Martinez',
    'address': '0477 Dawn Fork\nBrownhaven, UT 57082',
},
    'key95530': 'value83466',
    'key56686': 'value19346',
    'key40545': 'value12697',
    'key1490': 'value39171',
    'key88632': 'value95178',
},
    {
    'id': 17527486236890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Angela Owens',
    'address': '1527 Toni Spur Apt. 169\nGutierrezhaven, WY 25272',
    'text': 'Determine official second former hear director you. Soon next discussion charge. Put manage cause director.',
    'email': 'jcarrillo@example.org',
    'phone_number': '645-259-6157x0653',
    'json': {
    'name': 'Miguel Rodriguez',
    'address': '462 Wilkinson Row Apt. 240\nSouth Eugeneside, NE 72379',
},
    'key67512': 'value616',
    'key11284': 'value91069',
    'key19585': 'value44470',
    'key91140': 'value60305',
    'key34763': 'value41496',
    'key47034': 'value1843',
    'key29372': 'value80256',
    'key82472': 'value13856',
    'key35844': 'value89059',
    'key68078': 'value869',
},
    {
    'id': 17527486236901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Richard Gray',
    'address': '8301 Davis Heights\nRachelfort, OR 61589',
    'text': 'Others read economic. Name strong stop once reality.\nOr realize claim. Staff ago science reality direction.\nOf describe help event. Project mission investment book cultural.',
    'email': 'tjones@example.org',
    'phone_number': '8438459980',
    'json': {
    'name': 'Joseph Hartman',
    'address': '2497 Hicks Crescent\nSouth Kevinfort, NM 39669',
},
    'key91500': 'value75131',
    'key96755': 'value58468',
    'key3167': 'value98767',
    'key42603': 'value24165',
    'key34204': 'value12496',
    'key27395': 'value77304',
    'key95937': 'value31780',
},
    {
    'id': 17527486236912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Erica Greer',
    'address': '653 Nicole Turnpike Apt. 560\nEast Brandon, IL 31820',
    'text': 'Of fill knowledge power. Prevent both much also try appear. Including issue career your never yourself effort design.',
    'email': 'wrichardson@example.org',
    'phone_number': '5973334561',
    'json': {
    'name': 'Kathleen Lopez',
    'address': '23591 Rachel Tunnel Suite 319\nPerezberg, HI 53749',
},
    'key77513': 'value64844',
    'key5769': 'value96790',
    'key95776': 'value68332',
    'key42083': 'value35655',
},
    {
    'id': 17527486236923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sheri Pacheco',
    'address': '28567 Wyatt Glen\nEast Danielberg, NM 56808',
    'text': 'Behind strategy determine adult development traditional your. Own serve drive fight back. Development give agent international game begin.',
    'email': 'chadanderson@example.com',
    'phone_number': '753.473.0319',
    'json': {
    'name': 'Eric Berry',
    'address': '407 Roy Ramp Suite 231\nJamesberg, GU 21278',
},
    'key38770': 'value11173',
    'key1467': 'value8238',
    'key12118': 'value81993',
    'key61767': 'value89091',
    'key40147': 'value67891',
},
    {
    'id': 17527486236934,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jasmine Graham',
    'address': '1292 Steven Cape Suite 444\nGarciachester, GU 46298',
    'text': 'Art item name window others. Check only indicate old. Rich major start until more car letter company.\nHealth talk college skin. Perform wall so parent enjoy half. Themselves form country whole.',
    'email': 'thomas29@example.com',
    'phone_number': '(944)611-8271x097',
    'json': {
    'name': 'Jason Weaver',
    'address': '9637 Reed Plaza\nGibbsborough, MH 31859',
},
    'key89033': 'value83458',
},
    {
    'id': 17527486236945,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Amber Combs',
    'address': '281 Stacey Forest Apt. 156\nSouth Leahmouth, SD 53777',
    'text': 'Health message animal practice pass. Ask step great tough keep.\nSummer may study collection tough vote. Less mouth throw look. Us wear few election production them.\nSimply carry in officer.',
    'email': 'daniel23@example.org',
    'phone_number': '+1-218-546-3037x67090',
    'json': {
    'name': 'Virginia Alvarez',
    'address': '2792 Garcia Pines Suite 710\nRickshire, WY 68753',
},
    'key82522': 'value14892',
    'key33675': 'value71415',
    'key43400': 'value47123',
},
    {
    'id': 17527486236956,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Derek Jones',
    'address': '787 Washington Trace Suite 202\nNew Jessica, FL 10288',
    'text': 'Stuff money as television similar in rich. Science reveal current before could else.',
    'email': 'gwood@example.net',
    'phone_number': '001-628-856-3426',
    'json': {
    'name': 'Louis Harrison',
    'address': '663 John Stravenue\nPort Deniseburgh, DC 17515',
},
    'key54335': 'value5289',
    'key28479': 'value70748',
    'key68920': 'value52410',
    'key28197': 'value84837',
},
    {
    'id': 17527486236967,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kimberly Harrington',
    'address': '109 Fox Overpass Apt. 202\nSouth Marioland, UT 75532',
    'text': 'Read chance all notice. During argue true offer court likely.\nBuilding ten specific best. Suffer early report analysis place. House relationship model day easy evening.',
    'email': 'joshua85@example.com',
    'phone_number': '681-962-4503x15577',
    'json': {
    'name': 'William Ellis',
    'address': '0301 Bernard Circle\nCameronburgh, MS 06900',
},
    'key13558': 'value7628',
    'key74760': 'value95281',
    'key47010': 'value87013',
    'key80993': 'value6100',
},
    {
    'id': 17527486236978,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Henry Petty',
    'address': '91057 Smith Club Apt. 232\nLaramouth, ID 36168',
    'text': 'Glass case miss than human realize. Well west environment tend like thousand.\nCareer eye keep. Resource never store rather because rich.',
    'email': 'paul70@example.org',
    'phone_number': '(979)341-8877x22654',
    'json': {
    'name': 'Sarah Austin',
    'address': 'PSC 1585, Box 7563\nAPO AE 80532',
},
    'key61998': 'value41381',
    'key37702': 'value21881',
    'key89402': 'value91253',
    'key61096': 'value69456',
    'key53361': 'value40754',
    'key58963': 'value92274',
    'key17678': 'value25015',
    'key63085': 'value45652',
    'key91852': 'value10929',
},
    {
    'id': 17527486236987,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Joshua Oconnor',
    'address': '246 Johnson Divide Suite 082\nAshleyville, WY 26917',
    'text': 'Behavior guy he way me community better. Law street hold clearly ever particular school. Dark treat church successful camera.',
    'email': 'hammondrobert@example.net',
    'phone_number': '657-392-7979',
    'json': {
    'name': 'Eileen Nichols',
    'address': '611 Monica Rest\nLake Patriciafurt, GA 21142',
},
    'key29771': 'value51671',
    'key414': 'value40601',
    'key6398': 'value76800',
},
    {
    'id': 17527486236998,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Kristin Griffin',
    'address': '9185 Emily Trace\nNew Sandraville, CA 53720',
    'text': 'Movement since left. History response world road. Student painting newspaper lot everything range. Time maintain at avoid garden.',
    'email': 'matthew84@example.com',
    'phone_number': '001-249-227-0096x190',
    'json': {
    'name': 'Amanda Crawford',
    'address': '83893 Hernandez Forge Apt. 596\nBrittneyfurt, SC 36767',
},
    'key46280': 'value82025',
},
    {
    'id': 17527486237008,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Brandi Miller',
    'address': '27600 Nicole Roads Suite 544\nAaronshire, LA 54574',
    'text': 'Central seat apply news business stay. Know change as concern.\nDuring conference choice reason hear course claim individual.\nTough choice long fact. Main population let big. Pay guy down rest.',
    'email': 'denisehenderson@example.com',
    'phone_number': '+1-689-788-4678x961',
    'json': {
    'name': 'Misty Smith',
    'address': '95047 Atkinson Meadow\nNorth Lucaschester, SC 36679',
},
    'key4612': 'value79562',
    'key64605': 'value86126',
    'key39274': 'value9916',
    'key96650': 'value15828',
    'key34471': 'value36632',
    'key54893': 'value46319',
    'key93696': 'value6226',
    'key91169': 'value59163',
    'key92981': 'value83116',
    'key54640': 'value63682',
},
    {
    'id': 17527486237020,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Katelyn Travis',
    'address': '33346 Hunter Trail\nWest Jamiefort, MH 66698',
    'text': 'Report foot how child available. Big western first according business.\nAhead white peace customer including building safe. Recognize guy high guess compare cold situation he.',
    'email': 'davidsparks@example.net',
    'phone_number': '6788489717',
    'json': {
    'name': 'Anthony Holden',
    'address': '41489 Blake Common\nJonathanberg, VT 36279',
},
    'key92125': 'value54023',
    'key80385': 'value67846',
    'key34083': 'value58611',
    'key52280': 'value66352',
    'key36626': 'value29952',
    'key55113': 'value88863',
    'key96758': 'value63875',
    'key95366': 'value75055',
    'key96228': 'value7063',
    'key97124': 'value38872',
},
    {
    'id': 17527486237032,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'James Kelly',
    'address': '643 William Village\nGrantburgh, CT 35419',
    'text': 'Allow agency than manager put. Involve process town development ago. Modern until mention discussion size once sell.',
    'email': 'tanya79@example.com',
    'phone_number': '(749)462-5831x788',
    'json': {
    'name': 'Curtis Sims',
    'address': '75986 Wallace Circle Suite 191\nSmithbury, SC 81436',
},
    'key73272': 'value90312',
    'key1508': 'value59644',
    'key46281': 'value98259',
    'key36992': 'value49160',
    'key38133': 'value52130',
    'key26737': 'value79092',
},
    {
    'id': 17527486237043,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Laura Nguyen',
    'address': '4801 Foster Bridge Apt. 240\nPort Mistystad, NJ 29383',
    'text': 'Southern although job half tax agree. Wish just organization nearly lay.\nOnce American back. Help dream know traditional. Four best guy cost gas agreement.',
    'email': 'sharon05@example.org',
    'phone_number': '583.523.7244',
    'json': {
    'name': 'Brian Gomez',
    'address': 'Unit 9659 Box 6907\nDPO AP 37738',
},
    'key80980': 'value83166',
    'key17586': 'value97126',
},
    {
    'id': 17527486237052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Kenneth Melendez',
    'address': '3479 Jones Orchard\nLake Thomasside, NH 60868',
    'text': 'Opportunity take anyone compare space campaign find force. Few performance focus administration key data group can.',
    'email': 'dlara@example.org',
    'phone_number': '(695)983-5108x3237',
    'json': {
    'name': 'Natalie Lynch',
    'address': 'PSC 5985, Box 4062\nAPO AE 50160',
},
    'key37297': 'value28182',
    'key74521': 'value2423',
    'key74114': 'value38057',
    'key39389': 'value92899',
    'key48755': 'value48856',
    'key80446': 'value25743',
    'key15520': 'value5172',
    'key69419': 'value62592',
    'key56169': 'value73468',
    'key48956': 'value49136',
},
    {
    'id': 17527486237060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Amanda Huerta',
    'address': '13360 Ware Mountain Apt. 344\nNorth Todd, DC 98558',
    'text': 'Can in boy. Hundred stuff black activity blood. Clear garden culture need sense network your break.\nForce yeah start high reality wait final successful.',
    'email': 'hooperamanda@example.org',
    'phone_number': '8369768374',
    'json': {
    'name': 'Alan Griffin',
    'address': '8720 Travis Fork\nLake Kathrynburgh, AZ 07001',
},
    'key68273': 'value43902',
    'key50404': 'value82979',
    'key1108': 'value25861',
    'key6574': 'value17889',
    'key24549': 'value99400',
    'key16549': 'value11846',
},
    {
    'id': 17527486237072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Derrick Hawkins',
    'address': '75826 Cook Harbor Suite 982\nMonicaville, HI 13989',
    'text': 'Summer offer only reduce. Realize actually important agree. Tend throw free company then respond.\nAttack prevent brother team. Wrong discover whole despite.',
    'email': 'matthewburton@example.org',
    'phone_number': '001-388-959-3028x19929',
    'json': {
    'name': 'Julian Russell',
    'address': '3390 Reeves Spring Suite 383\nDanielshire, OR 26367',
},
    'key37670': 'value66219',
},
    {
    'id': 17527486237084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'John Pacheco',
    'address': '890 Sarah Rest\nMaryberg, FL 35207',
    'text': 'Hotel plan similar act official want. Help hold but specific.\nToward politics memory. Professional adult down early pick concern.\nGuy establish return heart tree. Sell recently focus else agency.',
    'email': 'lisamartinez@example.org',
    'phone_number': '953-870-3201x136',
    'json': {
    'name': 'Timothy Owens',
    'address': '41282 Nolan Coves\nVincentmouth, GU 51057',
},
    'key41709': 'value90125',
    'key66308': 'value29621',
    'key39406': 'value98124',
    'key28542': 'value47857',
    'key5616': 'value9209',
    'key6111': 'value35630',
    'key20635': 'value10459',
    'key76205': 'value38280',
},
    {
    'id': 17527486237095,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Nicholas Davis',
    'address': '639 Erika Point\nRoseport, WI 49911',
    'text': 'After help spring here community.\nHead draw drop. Become office yet able per.\nHealth second capital discover loss. Amount teach small public only better. Region finish us they design.',
    'email': 'gwebb@example.com',
    'phone_number': '343-347-3821x61653',
    'json': {
    'name': 'Kenneth Drake',
    'address': '399 Andrew Estates Apt. 670\nLake Veronica, WY 81404',
},
    'key41781': 'value17296',
    'key97310': 'value50630',
    'key85090': 'value3578',
    'key58069': 'value80955',
    'key41072': 'value15228',
    'key33121': 'value94015',
},
    {
    'id': 17527486237106,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Duane Hardy',
    'address': '73984 Velez Cape\nSouth Elizabeth, IN 11559',
    'text': 'Now type face business. Alone price though some organization chance. Range economic instead color bar today same.',
    'email': 'michael60@example.net',
    'phone_number': '(607)204-4191',
    'json': {
    'name': 'Veronica Harris',
    'address': '954 Fields Mount Suite 677\nRobertville, UT 27894',
},
    'key51420': 'value43180',
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
    'filter': 'uid > 0',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
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
    'RequestId': 'f6ceca08-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_57_565234drGzdFev',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 00]_1752748632.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid001752748632Json()
    test.run_tests()
