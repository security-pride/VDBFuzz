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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_varchar_filter[True-name like "placeholder%"]_1752748989_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name like "placeholder%"]_1752748989.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithVarcharFilterTrueNameLikePlaceholder1752748989Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name like "placeholder%"]_1752748989.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name like "placeholder%"]_1752748989.json"
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
    'data': [
    {
    'id': 17527489863304,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Anthony Turner',
    'address': '8981 Tucker Ways\nNew Christopher, NM 54912',
    'text': 'Trouble thing girl shake front. Staff almost ok either. Admit think agreement respond.',
    'email': 'phyllis43@example.net',
    'phone_number': '(238)271-2968x24399',
    'json': {
    'name': 'Wanda Garcia',
    'address': '48478 Briggs Union Apt. 923\nCherylmouth, MA 79570',
},
    'key37371': 'value4515',
    'key68699': 'value50940',
    'key62226': 'value89457',
    'key64265': 'value6689',
    'key28052': 'value39261',
    'key9354': 'value59568',
    'key27184': 'value97281',
    'key13853': 'value48452',
    'key35785': 'value87968',
},
    {
    'id': 17527489863322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Michael Parsons',
    'address': '25939 Mary Mount\nHenrymouth, UT 87978',
    'text': 'Theory indicate nor smile drop. Responsibility around scientist never. Hold glass stuff cell guess growth.',
    'email': 'samanthajacobson@example.net',
    'phone_number': '804-671-3622x4006',
    'json': {
    'name': 'Angela Lopez',
    'address': '1769 Tran Lake Apt. 931\nBauerburgh, ID 45668',
},
    'key49698': 'value20171',
    'key71268': 'value76264',
    'key58386': 'value56668',
    'key91063': 'value89724',
},
    {
    'id': 17527489863337,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Natasha Rosales',
    'address': '75995 Thomas Expressway\nNew Donaldshire, CA 85244',
    'text': 'Eight rest everyone television painting live lose. Which seem before under clear air dream.',
    'email': 'james05@example.com',
    'phone_number': '421.543.5241',
    'json': {
    'name': 'Lynn Vega',
    'address': '1224 Harris Ridges Apt. 812\nPort Jenniferview, UT 42172',
},
    'key4296': 'value34509',
    'key93805': 'value33772',
    'key8725': 'value17681',
    'key20103': 'value89686',
    'key13888': 'value1271',
    'key24476': 'value43742',
    'key74475': 'value89308',
    'key43980': 'value83839',
    'key96039': 'value55951',
},
    {
    'id': 17527489863350,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Melissa Jenkins',
    'address': '9905 Juan Wall\nSouth Christina, OK 28237',
    'text': 'Recently check court talk. Bill glass such possible challenge even decade owner.\nPhysical candidate account. Beat drug candidate.',
    'email': 'gibsondavid@example.com',
    'phone_number': '296.515.2279x7723',
    'json': {
    'name': 'Angela Hall',
    'address': '040 Gregory Mount\nWest Vickieland, MT 72763',
},
    'key22883': 'value44087',
},
    {
    'id': 17527489863364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Michael Alvarez',
    'address': '4641 Monroe Meadows\nChristopherfort, MH 20132',
    'text': 'Game your think. Possible consumer represent PM.\nWhere for third specific.\nParty include billion born go myself before. About which dream fund admit arm fill.',
    'email': 'obartlett@example.com',
    'phone_number': '+1-998-709-2624x3187',
    'json': {
    'name': 'Kristopher Parker',
    'address': '95033 Hill Spur\nSouth Miguelside, ME 59368',
},
    'key68838': 'value55937',
    'key43997': 'value79863',
    'key88175': 'value64656',
    'key93350': 'value74106',
    'key2442': 'value65425',
    'key74081': 'value76621',
    'key84494': 'value97181',
    'key9356': 'value1814',
    'key74213': 'value36765',
},
    {
    'id': 17527489863378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joel Dennis',
    'address': '4802 Joyce Ports\nSouth Erikatown, MS 25758',
    'text': 'Behavior conference able would learn involve. Company test pattern operation by.\nTry this because do end rate color. Green economy bank own certain. Son grow store source smile.',
    'email': 'operez@example.net',
    'phone_number': '+1-641-337-2366x10565',
    'json': {
    'name': 'Jay Hayes',
    'address': '96448 Steven Ridge\nNicoleshire, VT 33807',
},
    'key27321': 'value48785',
    'key80954': 'value28719',
    'key70178': 'value73575',
    'key7968': 'value46764',
    'key28567': 'value26479',
    'key68861': 'value43191',
    'key39650': 'value39221',
    'key20902': 'value39957',
    'key93466': 'value63326',
    'key71696': 'value41077',
},
    {
    'id': 17527489863391,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'George Campbell',
    'address': '3455 Chad Points\nMatthewland, MA 56139',
    'text': 'Notice or factor each book. Site determine son bed cover. Measure do art form player interest quickly.\nItself option wait. White budget no doctor better during down. Respond carry language hand.',
    'email': 'sarah55@example.net',
    'phone_number': '3896052410',
    'json': {
    'name': 'Olivia Watson',
    'address': 'USNV Wright\nFPO AP 38440',
},
    'key55439': 'value24385',
    'key97933': 'value29767',
},
    {
    'id': 17527489863403,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Juan Gordon',
    'address': '818 Janice Estates\nLake Patrickberg, KY 93828',
    'text': 'Care step line quality public major evidence church.\nPlay fish say do task. According voice at others tough. Way identify I tax.',
    'email': 'denise39@example.net',
    'phone_number': '001-555-740-5173',
    'json': {
    'name': 'Maurice Terrell',
    'address': '50122 Wilson Loaf Suite 210\nPort Corey, FL 77987',
},
    'key58621': 'value3359',
    'key19529': 'value62046',
    'key97846': 'value27793',
    'key83008': 'value58246',
    'key39380': 'value67714',
    'key101': 'value76383',
    'key41203': 'value10916',
    'key71268': 'value9188',
    'key90497': 'value99232',
    'key61495': 'value79771',
},
    {
    'id': 17527489863416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kevin Sawyer',
    'address': '063 Sara Ford Suite 367\nLake Gloriafurt, TX 34510',
    'text': 'Employee our do. Guess hair identify these. Group wife whom leader Mr common head American. Contain son professional politics.\nProvide she which miss player. Young national Mr.',
    'email': 'carpenterthomas@example.com',
    'phone_number': '(453)231-8778',
    'json': {
    'name': 'Carlos Perry',
    'address': '5087 Miller Springs Suite 711\nLake Holly, FL 94487',
},
    'key30309': 'value86337',
    'key48633': 'value99499',
    'key30770': 'value78027',
    'key55022': 'value40765',
    'key38915': 'value79650',
    'key48219': 'value55084',
},
    {
    'id': 17527489863431,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'James Heath',
    'address': '093 Castro Road\nNorth Jessicafurt, MI 85814',
    'text': 'Support tonight know city television. Thank social window. Act rule appear option site.\nReligious free can boy fly. Action less professor. Prepare result cost least agent idea force.',
    'email': 'qturner@example.net',
    'phone_number': '330-912-3098',
    'json': {
    'name': 'Mrs. Rachel Waters DVM',
    'address': '013 Sanchez Way Suite 671\nWilliamston, CA 29665',
},
    'key3483': 'value85836',
    'key50037': 'value40685',
    'key59664': 'value93779',
    'key31915': 'value55189',
    'key81707': 'value1789',
    'key16236': 'value56221',
    'key29724': 'value30754',
},
    {
    'id': 17527489863445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'April Ramsey',
    'address': '413 Hector Garden Apt. 972\nMichaelberg, NC 72948',
    'text': 'Nothing can change me throw ball people. Building candidate husband year back. Effort enough be sport far.',
    'email': 'bethwhite@example.net',
    'phone_number': '001-280-535-7228x467',
    'json': {
    'name': 'Frances Johns',
    'address': 'Unit 6129 Box 7007\nDPO AE 13128',
},
    'key64633': 'value65554',
    'key72484': 'value73017',
    'key5021': 'value92847',
    'key89306': 'value15620',
    'key97533': 'value72451',
    'key18561': 'value60819',
    'key37005': 'value95881',
    'key95419': 'value12071',
    'key60620': 'value50259',
},
    {
    'id': 17527489863458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Edwin Williams',
    'address': '2642 Jason Trail Suite 473\nNew Nathan, AS 65228',
    'text': 'Open herself defense week southern. Than computer hope continue science. Police cup green culture push letter.\nArtist hot guess place. Or produce manager. Right design good.',
    'email': 'madelinepittman@example.org',
    'phone_number': '864.871.8484x8370',
    'json': {
    'name': 'Jeffrey Hall',
    'address': '81210 Patterson Bridge\nLake Joshua, OH 16386',
},
    'key6246': 'value3077',
    'key53985': 'value28769',
    'key51440': 'value59005',
    'key3977': 'value54071',
    'key77180': 'value52186',
},
    {
    'id': 17527489863472,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Misty Carter',
    'address': '8735 Soto Crescent Suite 908\nRobinsonshire, MS 77146',
    'text': 'Make seat star official. Arrive box treatment win scene unit stuff couple. Central partner station.\nBoy when money candidate despite. Plant south week around conference offer whose. Stock nearly get.',
    'email': 'ilawrence@example.net',
    'phone_number': '(233)477-0722x5215',
    'json': {
    'name': 'Cory Ibarra',
    'address': '5911 Danielle Pass Apt. 850\nHallshire, PA 66365',
},
    'key32173': 'value44025',
    'key37219': 'value58448',
    'key3263': 'value12774',
    'key74857': 'value21933',
    'key91667': 'value72150',
    'key53669': 'value59651',
    'key94874': 'value97067',
    'key37505': 'value39446',
    'key47029': 'value87472',
},
    {
    'id': 17527489863487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Tonya Monroe',
    'address': '46364 Morris Fall Suite 272\nWilliamsberg, MO 58687',
    'text': 'Person upon deep need. What professional lot soldier eye would. Although number truth able information.',
    'email': 'krose@example.net',
    'phone_number': '001-632-854-2463x6235',
    'json': {
    'name': 'Elizabeth Lee',
    'address': '74352 Chen Wells\nTeresaburgh, MA 50500',
},
    'key36142': 'value42315',
    'key34673': 'value70146',
    'key65012': 'value39467',
    'key35639': 'value94904',
    'key40922': 'value92532',
},
    {
    'id': 17527489863497,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Cynthia Byrd',
    'address': '60093 Hart Manor\nHaleyborough, IN 63576',
    'text': 'Rather finally professor at because according accept. Why strong here take.\nContinue take put today.\nCentral significant somebody born interest become. Six food boy open fly.',
    'email': 'oalvarez@example.com',
    'phone_number': '416.658.2992x41878',
    'json': {
    'name': 'Nicole Doyle',
    'address': '3248 Gonzalez Manor Suite 155\nWest Lisa, NE 60833',
},
    'key75659': 'value68790',
    'key75648': 'value34674',
    'key70799': 'value29454',
    'key1595': 'value45450',
    'key32446': 'value45579',
    'key66435': 'value89830',
    'key62563': 'value55651',
},
    {
    'id': 17527489863508,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Brandy Campbell',
    'address': '130 Timothy Pass\nNorth Katelyn, MH 74418',
    'text': 'Party market black protect push. Type continue claim myself political interesting consumer. Board ground themselves.',
    'email': 'john56@example.net',
    'phone_number': '(646)700-0410x07267',
    'json': {
    'name': 'Patricia Rodgers',
    'address': 'USS Mitchell\nFPO AE 30612',
},
    'key67124': 'value59678',
    'key85488': 'value79152',
    'key16446': 'value11148',
    'key85194': 'value67925',
    'key11333': 'value2028',
    'key56036': 'value51021',
    'key25937': 'value46324',
    'key76222': 'value10350',
    'key47564': 'value38843',
},
    {
    'id': 17527489863518,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kimberly Pace',
    'address': '21331 Ryan Islands\nCynthiaton, CT 63773',
    'text': 'Various long drop garden side. Nice such seat thought reflect thank.\nProbably charge leg. Situation central yeah beyond catch.',
    'email': 'lisa09@example.org',
    'phone_number': '936-262-3330x31212',
    'json': {
    'name': 'Karen Harrison',
    'address': '716 Jonathan Center Apt. 884\nEdwardsside, CO 43958',
},
    'key44159': 'value91164',
    'key10317': 'value93222',
},
    {
    'id': 17527489863527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tina Gomez',
    'address': '056 Ian Haven Apt. 998\nEdwardstown, NH 45703',
    'text': 'Central majority mouth live agreement identify protect. Rather claim alone eye land. Plant left however.\nFear responsibility light hotel role. During identify job build property fire.',
    'email': 'hking@example.org',
    'phone_number': '317.970.6087x72484',
    'json': {
    'name': 'John Smith',
    'address': '701 Mccoy Glens Suite 642\nBergburgh, WV 26275',
},
    'key28660': 'value11897',
},
    {
    'id': 17527489863539,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Michael Li',
    'address': '3869 Sutton Mills Apt. 976\nFoxbury, WI 46729',
    'text': 'Point three put member. Difficult yourself crime plant kid become term product.\nSpecial trade commercial meet radio.',
    'email': 'esimpson@example.net',
    'phone_number': '(300)818-9650',
    'json': {
    'name': 'Nicholas Simmons',
    'address': '0988 Wallace Trail Apt. 727\nDawsonview, TN 57983',
},
    'key13464': 'value41667',
    'key37727': 'value18899',
    'key54651': 'value72233',
    'key45498': 'value46098',
    'key32256': 'value99846',
},
    {
    'id': 17527489863550,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Susan Lucas',
    'address': '2696 Dunlap Corner Suite 352\nMorenoshire, VT 21305',
    'text': 'These explain economy expert. Source hard media get somebody age eat.\nBag prove very. Quickly similar any allow treat trip piece. Special speak likely full wide.',
    'email': 'ryanrobinson@example.org',
    'phone_number': '222.352.5556x5767',
    'json': {
    'name': 'Diana Brown',
    'address': '43135 Williams Harbors\nPort Hollyshire, AZ 99320',
},
    'key89351': 'value91835',
},
    {
    'id': 17527489863562,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Julia Rogers',
    'address': '2590 Smith Alley Apt. 742\nMelissaburgh, WY 81019',
    'text': 'During teacher here reach affect keep blood. They get air minute none vote suddenly.',
    'email': 'ineal@example.com',
    'phone_number': '7998552823',
    'json': {
    'name': 'Christopher Crawford',
    'address': '30825 Mccullough Parks Suite 340\nStephanieside, VA 52584',
},
    'key89586': 'value33836',
    'key5386': 'value29572',
    'key94847': 'value92616',
    'key78721': 'value14439',
    'key98277': 'value39140',
},
    {
    'id': 17527489863573,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Matthew Johnson',
    'address': '183 Mccarty Forks\nAprilmouth, OH 54097',
    'text': 'Ever hundred benefit could pass teach away science. Check want purpose hand station tough protect still.',
    'email': 'efarrell@example.com',
    'phone_number': '408.623.8179x9638',
    'json': {
    'name': 'Michael Dennis',
    'address': '627 Taylor Locks Suite 172\nMortontown, KS 37567',
},
    'key45125': 'value39307',
    'key20418': 'value90682',
    'key44524': 'value83343',
    'key4203': 'value16284',
    'key92347': 'value30384',
    'key89311': 'value8261',
    'key60788': 'value65854',
    'key68556': 'value13060',
    'key89960': 'value63129',
    'key11128': 'value77225',
},
    {
    'id': 17527489863584,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Timothy Weaver',
    'address': '02950 Amy Mews Apt. 160\nJohnsonfort, PW 23249',
    'text': 'Writer treat act along young. Sing itself both exactly official ask free. Go ready deep itself reduce sense indicate. Approach organization husband direction and fear.',
    'email': 'janet49@example.net',
    'phone_number': '402-801-1138x633',
    'json': {
    'name': 'Kelly Blake',
    'address': '1304 Perez River Apt. 463\nEast Maryfort, DC 28038',
},
    'key80666': 'value34',
    'key59415': 'value17320',
    'key99335': 'value38485',
    'key22368': 'value93389',
    'key40553': 'value51396',
    'key59713': 'value9166',
    'key92302': 'value45827',
    'key19331': 'value3938',
},
    {
    'id': 17527489863595,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Susan Todd',
    'address': '3047 Smith Dam\nPort Blakemouth, ME 85148',
    'text': 'Office mention man game.\nSociety discuss know opportunity support society month model. Unit people hope cause audience trial. Could style common.',
    'email': 'rachel71@example.org',
    'phone_number': '001-811-897-3198x060',
    'json': {
    'name': 'Margaret Ortiz',
    'address': '6728 Barbara Street\nNew Jeffrey, UT 89153',
},
    'key64263': 'value57155',
    'key72559': 'value78631',
},
    {
    'id': 17527489863606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'David Nguyen',
    'address': 'PSC 2541, Box 1301\nAPO AE 74715',
    'text': 'Entire where fight executive all must security. Where artist team seek city professional. Dog specific party play serious usually.',
    'email': 'brittanylopez@example.com',
    'phone_number': '854.652.3114x8770',
    'json': {
    'name': 'Ricky Brown',
    'address': '13521 Gregory Unions Apt. 042\nOdomstad, MS 27439',
},
    'key20593': 'value26599',
    'key37543': 'value18447',
    'key20340': 'value50317',
    'key29345': 'value1',
    'key17537': 'value10938',
},
    {
    'id': 17527489863616,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Joseph Pierce',
    'address': '728 Anita Estates\nBestbury, ND 84099',
    'text': 'Organization ago matter possible life. Dark data worry however range.\nTeam take seek cup program force member. Return keep security Congress herself seem.',
    'email': 'thomasandrew@example.com',
    'phone_number': '527.544.9560',
    'json': {
    'name': 'Jane Boone',
    'address': '1644 Aaron Loop Apt. 876\nNorth Christineview, TX 63641',
},
    'key31232': 'value37504',
    'key87100': 'value44079',
    'key8750': 'value74',
    'key3421': 'value52387',
    'key3262': 'value53189',
},
    {
    'id': 17527489863626,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Stephanie Jenkins',
    'address': '9401 Nelson Drive Suite 754\nMoorehaven, SC 10552',
    'text': 'Partner little may fine.\nBecome produce like radio. Sister this future season rock. Girl character away if last fund fight.',
    'email': 'collinsstephanie@example.org',
    'phone_number': '+1-450-588-7225',
    'json': {
    'name': 'Jennifer Rosales',
    'address': 'USCGC Donovan\nFPO AP 94077',
},
    'key80417': 'value43416',
    'key77276': 'value55022',
    'key47415': 'value73446',
    'key24746': 'value8934',
    'key67814': 'value15049',
},
    {
    'id': 17527489863637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Lisa Armstrong',
    'address': '6362 Bates Ramp Apt. 230\nTrevormouth, KY 21301',
    'text': 'Day leader democratic last thing wide several. Top improve view strategy.',
    'email': 'canderson@example.com',
    'phone_number': '253.623.6141x7805',
    'json': {
    'name': 'Ashley Baird',
    'address': '64642 Hanson Streets\nRosstown, VI 29666',
},
    'key23103': 'value10128',
    'key39801': 'value85990',
    'key96363': 'value12709',
    'key98137': 'value97873',
    'key65877': 'value94670',
    'key62547': 'value83818',
    'key156': 'value45412',
    'key26523': 'value60688',
    'key47358': 'value8832',
},
    {
    'id': 17527489863649,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Michael Bush',
    'address': '81521 John Mall\nWest Timothy, ME 88446',
    'text': 'Wide person force next contain.\nApply agent west believe in cup. But shoulder ahead fight effort.\nProject the its. Trade our team certain of police case read.',
    'email': 'katherine39@example.org',
    'phone_number': '001-293-326-8877',
    'json': {
    'name': 'John Smith',
    'address': '502 Williams Summit\nSouth Wanda, UT 16140',
},
    'key93352': 'value32416',
    'key40430': 'value50264',
    'key48875': 'value29471',
    'key24656': 'value47946',
    'key28447': 'value53556',
    'key80419': 'value41054',
    'key35458': 'value30353',
},
    {
    'id': 17527489863659,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Harold Ruiz',
    'address': '0625 Anthony Rapid\nNew Alice, VT 30941',
    'text': 'Everything pull western dark special animal less. Many ago about because head. Whom boy hard mean.',
    'email': 'nleblanc@example.org',
    'phone_number': '6007898227',
    'json': {
    'name': 'Anna Wright',
    'address': '475 Kim Isle\nLeefort, MP 47585',
},
    'key14930': 'value70067',
    'key73077': 'value87021',
    'key68917': 'value55087',
    'key18651': 'value40571',
    'key29649': 'value17607',
    'key69872': 'value12066',
},
    {
    'id': 17527489863669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Lindsey Alexander',
    'address': '2617 Wilson Well Suite 164\nJacquelinestad, FM 55806',
    'text': 'Business ahead star beat. Build body find leg. Both watch possible design.\nSeat future teacher oil once thank tonight. Economy sister three budget. Require father type always behavior show.',
    'email': 'lopezpaul@example.net',
    'phone_number': '985.337.8571',
    'json': {
    'name': 'Micheal Powers',
    'address': '9861 Willie Lane Suite 232\nAlyssaport, PA 83134',
},
    'key22360': 'value93128',
    'key15350': 'value27180',
},
    {
    'id': 17527489863681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Kevin Lester',
    'address': '95554 Morris Road Apt. 572\nNorth Lisastad, SC 04365',
    'text': 'Late available social take. Heart between age reflect safe central stay bit.\nFront television trip old bad. Benefit president war woman.',
    'email': 'matthewmontgomery@example.org',
    'phone_number': '(943)493-2997x553',
    'json': {
    'name': 'Crystal Bell',
    'address': '32557 Joshua Lock Suite 451\nNorth Tony, MS 56181',
},
    'key8557': 'value87019',
    'key14800': 'value30293',
    'key92419': 'value31734',
    'key99823': 'value59396',
    'key81606': 'value18378',
    'key66111': 'value90468',
    'key69490': 'value48837',
    'key3473': 'value25468',
    'key41184': 'value76734',
    'key8352': 'value77047',
},
    {
    'id': 17527489863693,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kyle Henderson',
    'address': '4593 Johnson Vista Apt. 139\nSimmonsborough, OR 93640',
    'text': 'Enough maintain near site five much. Significant building voice mission. Detail manage popular sport two.\nMarriage high future.',
    'email': 'joyce09@example.com',
    'phone_number': '433-481-9748x158',
    'json': {
    'name': 'Francis Mcgee',
    'address': '9137 Sandra Junctions\nChristopherton, NE 81226',
},
    'key77181': 'value30913',
    'key98793': 'value45507',
    'key78293': 'value79653',
    'key49149': 'value74030',
    'key22701': 'value96991',
    'key63885': 'value72850',
    'key82233': 'value99515',
},
    {
    'id': 17527489863704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jennifer Wilson',
    'address': '4627 Sandra Common Apt. 263\nMccartyport, AZ 01865',
    'text': 'Something dinner add. Cell personal item final public fund. Ground reality someone them how call citizen.\nEnter fish herself.',
    'email': 'preilly@example.net',
    'phone_number': '889-762-8421',
    'json': {
    'name': 'Robin Medina',
    'address': '878 John Plains\nTiffanyshire, SC 20253',
},
    'key41419': 'value77678',
    'key74336': 'value53361',
    'key49019': 'value98783',
    'key32373': 'value33801',
    'key90521': 'value43012',
},
    {
    'id': 17527489863714,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Megan Alexander',
    'address': '235 Erica Mill\nLake Jessica, DE 50691',
    'text': 'Road young notice boy have over season particularly. If reduce save share. Agreement technology week admit.',
    'email': 'bradley70@example.net',
    'phone_number': '2187190880',
    'json': {
    'name': 'Jennifer Green',
    'address': 'USNV Whitehead\nFPO AP 86855',
},
    'key69325': 'value13650',
    'key34068': 'value18348',
    'key74866': 'value39831',
    'key48558': 'value34725',
    'key51294': 'value74624',
    'key2023': 'value9929',
    'key83824': 'value2493',
    'key56236': 'value81097',
},
    {
    'id': 17527489863723,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'David Thomas',
    'address': '13063 Nicole Glen Apt. 051\nNew Andrew, IA 30403',
    'text': 'Instead too human where put. Worker explain yet great grow than.\nAgain number realize safe country best customer happy. Sport thousand rest record factor central.',
    'email': 'johnterry@example.com',
    'phone_number': '001-336-890-7839x821',
    'json': {
    'name': 'Jessica Hall',
    'address': '77939 Anthony Knoll\nStacyfort, OR 06480',
},
    'key10462': 'value38598',
    'key8287': 'value43038',
    'key80620': 'value86349',
    'key94294': 'value56041',
    'key8318': 'value86588',
    'key86765': 'value58133',
},
    {
    'id': 17527489863734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Mrs. Ashley Burnett',
    'address': '93172 Lopez Plains\nNew Danaburgh, DC 81282',
    'text': 'Green industry pressure leg run. Parent soon spend.\nMean night enjoy hit change. Resource add wind relationship lot social his. Top without few painting.',
    'email': 'charlesoconnell@example.org',
    'phone_number': '575.876.2234',
    'json': {
    'name': 'Jamie Sampson',
    'address': '13444 Cabrera River Suite 956\nMelissamouth, UT 39717',
},
    'key9462': 'value61514',
    'key95325': 'value32728',
    'key48848': 'value88942',
    'key64384': 'value11885',
    'key51263': 'value68704',
    'key78910': 'value85568',
    'key77486': 'value27314',
    'key13478': 'value56093',
},
    {
    'id': 17527489863746,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Paula Becker',
    'address': 'USS Freeman\nFPO AP 92211',
    'text': 'Return film event head year everyone cost can. Various we war deal glass. Condition discussion sense attention visit side trip.',
    'email': 'melissajackson@example.com',
    'phone_number': '404-948-6037x2782',
    'json': {
    'name': 'Matthew Salazar',
    'address': '4002 Austin Falls\nNorth Donnamouth, VI 33323',
},
    'key25565': 'value66929',
    'key75780': 'value75724',
    'key40320': 'value66299',
    'key7583': 'value89673',
    'key93828': 'value71',
},
    {
    'id': 17527489863756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Travis Hayes',
    'address': '9485 Kaufman Pass Apt. 353\nRonaldland, TX 35824',
    'text': 'Poor third and million. Almost she trip scientist without hotel reality. Sport result boy really house.',
    'email': 'diane10@example.net',
    'phone_number': '(908)611-6223x5667',
    'json': {
    'name': 'Alicia Dunn',
    'address': '88287 Schneider Highway Apt. 964\nSouth Bruce, VA 90124',
},
    'key38835': 'value69293',
    'key63079': 'value59799',
    'key51505': 'value61808',
    'key34827': 'value3223',
    'key49451': 'value8996',
    'key40210': 'value86590',
    'key33752': 'value16301',
},
    {
    'id': 17527489863766,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Michael Carter',
    'address': '661 Robert Bridge\nStephenton, MD 05456',
    'text': 'State walk process easy indicate produce. Player option return stuff.\nSecond item job time somebody add. Give too step name station treatment special.',
    'email': 'ojones@example.com',
    'phone_number': '7875172494',
    'json': {
    'name': 'Tiffany Sullivan',
    'address': '68479 Perkins Turnpike\nKyleton, NV 01896',
},
    'key43028': 'value45495',
    'key35861': 'value72635',
    'key14820': 'value38439',
    'key37413': 'value73792',
    'key75656': 'value35489',
    'key54076': 'value25103',
    'key83670': 'value76008',
    'key48159': 'value2555',
    'key75694': 'value83051',
    'key37585': 'value42370',
},
    {
    'id': 17527489863777,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'David Harding',
    'address': '6021 Strickland Glens\nSouth Markville, MT 37840',
    'text': 'Despite drug letter hospital who democratic message.\nEight record exactly want bank hope hospital go. Method business hospital woman. Apply war increase be.',
    'email': 'bmckee@example.net',
    'phone_number': '(387)311-9314x710',
    'json': {
    'name': 'Adam Hayes',
    'address': '976 Murphy Gardens Apt. 513\nMartinview, VT 12791',
},
    'key7588': 'value79625',
    'key30318': 'value28963',
    'key92688': 'value75479',
    'key59194': 'value38590',
    'key73149': 'value55130',
    'key77972': 'value14174',
},
    {
    'id': 17527489863788,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Mrs. Tammy Jackson DDS',
    'address': '3061 Hicks Island Apt. 233\nEast Jennifermouth, WY 82533',
    'text': 'Their trouble threat for. Her should election firm. Under run occur break mind land.\nChoice as world listen appear full meet. Pattern hundred have world new treatment. Test among garden.',
    'email': 'jeffreyjohnson@example.org',
    'phone_number': '355-390-5364x355',
    'json': {
    'name': 'Susan Alexander',
    'address': '0935 Peter Tunnel Suite 893\nAriasbury, NY 25192',
},
    'key89172': 'value8160',
},
    {
    'id': 17527489863800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Caroline Martin',
    'address': '8146 Elizabeth Canyon Suite 963\nLake Saraberg, CA 69026',
    'text': 'Group skin name toward image challenge. Degree form that fill reflect help range. Military rise process read fact. History onto name moment choose.',
    'email': 'timothy32@example.org',
    'phone_number': '001-344-586-4333x400',
    'json': {
    'name': 'Deanna Simmons',
    'address': '86237 Jennifer Lake Suite 381\nEast Codytown, OK 16122',
},
    'key81509': 'value32700',
    'key65360': 'value68565',
    'key4730': 'value65349',
    'key39610': 'value64623',
    'key76581': 'value88590',
},
    {
    'id': 17527489863811,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kyle Carter',
    'address': '16601 Barber Point\nPort Taylor, SD 36992',
    'text': 'Other provide month look. Sign girl million effort win. While feel laugh staff money.\nSimply traditional recognize necessary TV nature government. Total somebody social.',
    'email': 'foleyalex@example.org',
    'phone_number': '001-371-987-8118',
    'json': {
    'name': 'Lucas Hart',
    'address': 'PSC 0626, Box 1443\nAPO AE 44678',
},
    'key29643': 'value51414',
    'key65910': 'value11811',
    'key95758': 'value84419',
    'key54105': 'value21444',
    'key36585': 'value40576',
    'key85813': 'value76820',
    'key49186': 'value23140',
},
    {
    'id': 17527489863820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Brian Clay',
    'address': '29783 Stacey Camp Suite 496\nLake Kimberlyton, CA 21785',
    'text': 'Name computer out. Evidence Democrat shake I across. Factor mouth station spend. Work full television hundred.\nArea around executive rather could skin.',
    'email': 'marksmith@example.org',
    'phone_number': '302.643.7353x341',
    'json': {
    'name': 'Sean Smith',
    'address': '798 Simon Skyway Suite 115\nMercedesbury, AZ 99056',
},
    'key64503': 'value48979',
    'key88939': 'value65576',
    'key49582': 'value23189',
},
    {
    'id': 17527489863831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Chris Johnston',
    'address': '416 Nathan Springs Suite 021\nSouth Renee, OR 97126',
    'text': 'Drop single protect off. Ok section so term citizen technology.\nBig kid security hour produce heart ground. Song issue heart rise often season certain late.',
    'email': 'guzmanjessica@example.net',
    'phone_number': '001-268-447-0783x12118',
    'json': {
    'name': 'Tony Moss',
    'address': '658 Morgan Corner Apt. 066\nMichelleville, PW 31829',
},
    'key12546': 'value29892',
    'key91428': 'value81870',
    'key80086': 'value82087',
    'key6984': 'value2022',
    'key901': 'value68969',
    'key98604': 'value42343',
},
    {
    'id': 17527489863843,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Sheila Campbell',
    'address': '340 Wilson Square\nSouth Amanda, VA 18436',
    'text': 'Society next war really almost. Support issue fly so pattern environment operation.\nMemory approach sell black really already now. Focus probably father describe money else nation.',
    'email': 'josephsanchez@example.net',
    'phone_number': '811.929.7962x4270',
    'json': {
    'name': 'Ryan Wolf',
    'address': '271 David Pike Apt. 179\nKleinside, AR 27240',
},
    'key46907': 'value8576',
},
    {
    'id': 17527489863854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Allison Whitaker MD',
    'address': '1942 David Drive Suite 696\nAlexanderchester, ND 66290',
    'text': 'Official rather country talk often draw do. Maintain minute story official. Would hotel wind really drive piece role.',
    'email': 'edward59@example.com',
    'phone_number': '491.965.6542x565',
    'json': {
    'name': 'Jennifer Hurley',
    'address': '29217 Roberts Throughway Apt. 304\nSteventown, FL 32962',
},
    'key89737': 'value34050',
    'key51964': 'value24489',
    'key69687': 'value33749',
    'key81289': 'value10915',
    'key97363': 'value39235',
    'key90087': 'value62221',
},
    {
    'id': 17527489863865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Andrew Hartman',
    'address': '035 Todd Gateway\nNorth Kylefurt, VT 50402',
    'text': 'More true moment say well. Statement test baby along effort size.\nSeven military admit piece sing. Rate for mission human wind hope read. Learn affect save program change late.',
    'email': 'coxlinda@example.com',
    'phone_number': '(571)586-6028',
    'json': {
    'name': 'Danny Edwards',
    'address': '2506 Watson Crossing Suite 422\nEast Richardland, KS 85668',
},
    'key14182': 'value91279',
    'key71103': 'value51888',
    'key18310': 'value77667',
    'key78201': 'value77983',
    'key41686': 'value90532',
    'key79614': 'value28939',
    'key81290': 'value29203',
    'key85189': 'value55220',
    'key35594': 'value64511',
},
    {
    'id': 17527489863876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Ms. Cynthia Kennedy',
    'address': '413 Nicholas Burg\nPhillipsport, OR 72742',
    'text': 'Well institution top modern movement true on. Describe create suffer economic. Fast sea born whom town personal sit.',
    'email': 'jamesbrewer@example.com',
    'phone_number': '3696328719',
    'json': {
    'name': 'Shelby Park',
    'address': '835 Graham Lodge\nWrightchester, UT 90056',
},
    'key75733': 'value54124',
    'key13967': 'value99199',
    'key85230': 'value352',
    'key18280': 'value63376',
    'key25514': 'value56954',
    'key46170': 'value59686',
    'key39985': 'value7192',
    'key58675': 'value24862',
    'key44456': 'value72403',
},
    {
    'id': 17527489863888,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Cody Garcia',
    'address': '352 Watts Haven Apt. 894\nKarenfort, SC 93796',
    'text': 'Word near material dark sense woman. Season argue meet argue hospital smile. Yes door catch strong long.',
    'email': 'callen@example.com',
    'phone_number': '(606)450-6221x32218',
    'json': {
    'name': 'Lauren Mitchell',
    'address': '54700 Karen Underpass Apt. 579\nPort Aaronland, RI 18378',
},
    'key22565': 'value99427',
    'key6102': 'value45235',
    'key51097': 'value57526',
    'key68436': 'value98841',
},
    {
    'id': 17527489863899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Sara Thompson',
    'address': '37652 Caitlin Hill Apt. 977\nPort Julieton, MH 93429',
    'text': 'Bank address fear. By blue would civil.\nFull trade kitchen these character. Money financial international condition fight court.\nAnd card look able. Agent interest firm way final vote.',
    'email': 'wsanchez@example.com',
    'phone_number': '(448)307-9319x651',
    'json': {
    'name': 'Robert Lara',
    'address': '5876 Harding Fields\nEast Frankville, HI 99822',
},
    'key12': 'value53847',
    'key47391': 'value64879',
    'key91661': 'value41061',
    'key85650': 'value94030',
    'key72915': 'value96438',
},
    {
    'id': 17527489863910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Christopher Whitehead',
    'address': '6280 Joshua Oval\nLake Eric, PA 32419',
    'text': 'Wait room order top century per charge.\nResult fast necessary know surface price million look. Group star case room. That each different cold.',
    'email': 'allenvictoria@example.org',
    'phone_number': '808.576.2483',
    'json': {
    'name': 'Tammy Lowery',
    'address': '10108 Richard Court Apt. 067\nLawrencemouth, SC 98147',
},
    'key53526': 'value10589',
    'key75589': 'value77881',
    'key5208': 'value86974',
    'key28133': 'value61938',
    'key25063': 'value2302',
    'key43874': 'value30911',
    'key97406': 'value40443',
    'key47118': 'value14155',
    'key36472': 'value51498',
    'key44570': 'value58585',
},
    {
    'id': 17527489863921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Aaron Mills',
    'address': 'Unit 1497 Box 0084\nDPO AE 66632',
    'text': 'Relationship onto money. Down trade old consider. Why point base see within.\nDescribe international hard hold six according require issue.',
    'email': 'patricia69@example.com',
    'phone_number': '9528518371',
    'json': {
    'name': 'Jessica Jackson',
    'address': 'PSC 4776, Box 2361\nAPO AA 79361',
},
    'key7706': 'value43297',
    'key36951': 'value93239',
    'key25731': 'value38520',
    'key50099': 'value40681',
    'key92373': 'value30243',
    'key37766': 'value69804',
    'key51902': 'value51058',
},
    {
    'id': 17527489863928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jordan Thomas',
    'address': '4485 Ann Ramp Apt. 270\nNorth Laura, WY 65993',
    'text': 'Probably media stand next. Sell your worker analysis.\nChild various fish business understand speak fight. Get official night best month stay.\nCompare little force. Eye guy clearly site particularly.',
    'email': 'jamespace@example.net',
    'phone_number': '675.303.0484x46494',
    'json': {
    'name': 'Robert Martinez',
    'address': '888 Michelle Knoll\nKayleehaven, OR 68182',
},
    'key65329': 'value99701',
    'key80702': 'value62797',
    'key46395': 'value23739',
    'key89572': 'value89758',
    'key11740': 'value26723',
    'key9928': 'value83946',
    'key74100': 'value75150',
    'key7129': 'value49257',
    'key52484': 'value58295',
},
    {
    'id': 17527489863940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'James Scott',
    'address': '529 Sarah Cliff\nNorth Christopher, ND 45503',
    'text': 'Maintain manager social trouble language. Challenge pick assume nice. Person maybe let those size hope.',
    'email': 'zmora@example.com',
    'phone_number': '(444)743-9580x0197',
    'json': {
    'name': 'Brooke Johnson',
    'address': '45633 Margaret Canyon\nPeterstad, ND 28743',
},
    'key23151': 'value81527',
    'key42655': 'value43411',
    'key39461': 'value42649',
},
    {
    'id': 17527489863949,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Patrick Wilson',
    'address': '1826 Kenneth Court\nAnthonymouth, KS 35065',
    'text': 'Enough factor white meeting military where. Front how throughout.\nResponsibility fire phone approach dark message. Already field past movie card.\nEnjoy around by. Yard glass establish visit.',
    'email': 'brandonmaxwell@example.net',
    'phone_number': '590.407.4258x5694',
    'json': {
    'name': 'William Castaneda',
    'address': '21611 Lane Corner Suite 113\nMasonshire, CO 58312',
},
    'key17284': 'value48071',
    'key43191': 'value55520',
    'key1013': 'value48373',
    'key75002': 'value74629',
},
    {
    'id': 17527489863960,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Mark Powell',
    'address': '757 Willis Centers\nRamosbury, GU 33268',
    'text': 'Inside break media body poor.\nHistory argue international anyone. The thing crime close matter husband expert interview.',
    'email': 'gracepeterson@example.com',
    'phone_number': '900-541-0711x57794',
    'json': {
    'name': 'Andrew Roach',
    'address': '29313 Sharp Drive Suite 817\nAnthonyport, NE 77312',
},
    'key37058': 'value64446',
    'key59723': 'value29231',
    'key78682': 'value70424',
},
    {
    'id': 17527489863972,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Shelia Edwards',
    'address': '46393 Christina Meadows\nBradytown, GU 14412',
    'text': 'Seek enough professor why serve. Accept season difficult. Organization part third player person various. Less cut including response gas tough than start.',
    'email': 'kwashington@example.net',
    'phone_number': '560-243-6644',
    'json': {
    'name': 'Karen Lewis',
    'address': '6472 Ellen Prairie Apt. 322\nSouth Nicholas, FL 64846',
},
    'key26964': 'value87233',
    'key69863': 'value49846',
},
    {
    'id': 17527489863983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Christine Watts',
    'address': '46608 Todd Springs Apt. 608\nGreenville, PA 33074',
    'text': 'Watch carry decision. Age music save. Explain worry control lot win.\nProduce live save history. Perform on already major individual. Onto ready drug walk. Perform good commercial on shoulder.',
    'email': 'kramerluis@example.com',
    'phone_number': '(218)633-9206x3511',
    'json': {
    'name': 'Shane Gilmore',
    'address': '758 Anna Union Apt. 337\nLake Kenneth, NH 81604',
},
    'key97710': 'value9558',
    'key11558': 'value98368',
    'key18415': 'value52525',
    'key95942': 'value19378',
    'key96705': 'value69525',
    'key93056': 'value33227',
    'key62765': 'value11244',
    'key86392': 'value75749',
},
    {
    'id': 17527489863995,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Erin Carpenter',
    'address': '682 Theresa Square\nLake Ashley, ME 48861',
    'text': 'Cold report enjoy ten social drive air former. Simply third friend hotel media building. Car option play power large free.\nResult phone really oil. Her toward trial several economic down back.',
    'email': 'whiteronnie@example.net',
    'phone_number': '332.916.3174x467',
    'json': {
    'name': 'Michael Henderson',
    'address': '62218 Charles Lake Suite 886\nMeganburgh, WV 93400',
},
    'key31233': 'value7754',
    'key72356': 'value67291',
    'key40219': 'value18038',
    'key73801': 'value56859',
    'key26613': 'value57043',
},
    {
    'id': 17527489864006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Jason Edwards',
    'address': '37717 Johnson Valley\nKaylafort, HI 31796',
    'text': 'Issue son key look issue doctor sister.\nWatch writer again relationship suggest onto green. Nor others shoulder movement respond.\nRepresent record deep war fill. Evening course see church.',
    'email': 'zjackson@example.net',
    'phone_number': '874-840-2669x117',
    'json': {
    'name': 'Joshua Waters',
    'address': '05318 Anderson Mountains Suite 426\nLake Jacobmouth, HI 47985',
},
    'key99246': 'value5863',
    'key75118': 'value8224',
    'key96224': 'value17774',
    'key423': 'value78388',
    'key62697': 'value69811',
    'key25615': 'value80228',
    'key70730': 'value16627',
    'key35952': 'value72354',
},
    {
    'id': 17527489864017,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Rebecca Rogers',
    'address': '13458 Larry Loop Apt. 297\nSouth Gabrielle, UT 38837',
    'text': 'Goal authority operation. Writer assume behind next prove.\nSpend else offer significant deep sport speech. Tax nation ahead heavy do present.',
    'email': 'sjackson@example.org',
    'phone_number': '224-600-5984x16269',
    'json': {
    'name': 'April Reed',
    'address': '242 Curtis Turnpike Apt. 044\nStacyland, MH 40450',
},
    'key13668': 'value6669',
    'key30182': 'value64355',
    'key96625': 'value81005',
    'key24218': 'value85197',
    'key3768': 'value38138',
    'key47409': 'value58903',
    'key35759': 'value4783',
},
    {
    'id': 17527489864028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Courtney White',
    'address': '06833 Michael Square Suite 552\nPort Beverly, AR 88912',
    'text': 'Mouth analysis night fight give best blood then. Side listen where owner. Example ok performance society soon treatment game.\nCan ask body. Word simply past training attack born.',
    'email': 'walkerjames@example.net',
    'phone_number': '+1-543-655-3888x68802',
    'json': {
    'name': 'Sarah Weber',
    'address': '7145 Kimberly Well\nDavidhaven, GU 98937',
},
    'key38603': 'value22753',
    'key53286': 'value26799',
    'key29666': 'value59977',
    'key55006': 'value32319',
    'key41280': 'value45078',
    'key18600': 'value98497',
    'key17987': 'value95193',
    'key41538': 'value36049',
    'key82875': 'value57875',
},
    {
    'id': 17527489864039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Joel Campbell',
    'address': '918 Hill Landing Suite 967\nGregorymouth, IL 88630',
    'text': 'Seek woman without.\nStay another like like though out. Activity even method.\nFull degree old human. Large star property at summer feeling decide small.',
    'email': 'matthewduran@example.net',
    'phone_number': '(710)706-5331',
    'json': {
    'name': 'James Warner',
    'address': '02372 Rodriguez Light Apt. 680\nMaciasland, ME 69720',
},
    'key47041': 'value34963',
    'key99714': 'value27012',
    'key77705': 'value20909',
    'key39677': 'value69173',
    'key20720': 'value20135',
    'key28863': 'value63851',
    'key97403': 'value65217',
    'key98639': 'value80811',
    'key6781': 'value13829',
},
    {
    'id': 17527489864051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jill Moreno',
    'address': '620 Dillon Views\nMatthewland, FM 63776',
    'text': 'Story child despite minute. Sort sense score plant adult. Reduce through none police play page.\nOnto gun near his land network.',
    'email': 'chelsea79@example.net',
    'phone_number': '001-784-723-6502x521',
    'json': {
    'name': 'Jeremy Griffith',
    'address': 'Unit 2550 Box 0733\nDPO AE 61291',
},
    'key21334': 'value13035',
    'key73528': 'value4061',
    'key21650': 'value84034',
    'key96105': 'value9258',
    'key83833': 'value99969',
    'key15657': 'value34818',
    'key85471': 'value92507',
    'key46312': 'value61505',
},
    {
    'id': 17527489864060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Derrick Ellis',
    'address': '821 Pamela Drive Suite 422\nPort Hollyville, DE 14087',
    'text': 'Chance cost agreement. Different sit prove chair share eight perform.\nTv adult hold before return hit method. Blood compare or institution.',
    'email': 'taylorkristina@example.net',
    'phone_number': '611-278-2000x764',
    'json': {
    'name': 'Jennifer Allison',
    'address': '1144 Jordan Valley\nAnthonyshire, MA 14033',
},
    'key63364': 'value98200',
    'key49448': 'value1404',
    'key24176': 'value61193',
    'key57438': 'value62954',
},
    {
    'id': 17527489864070,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Nathaniel Bean',
    'address': '483 Mario Burg Suite 578\nFrederickville, ID 38482',
    'text': 'Prove simple husband responsibility. Do difference term project step. Sometimes go top effect study star important.',
    'email': 'anna49@example.org',
    'phone_number': '586-337-0235x754',
    'json': {
    'name': 'Emily Chambers',
    'address': '501 Ellis Glen Suite 667\nWest Shawnshire, AL 28993',
},
    'key98029': 'value46835',
    'key23110': 'value35394',
    'key24830': 'value71908',
    'key31528': 'value65242',
    'key87730': 'value38177',
    'key28784': 'value77242',
    'key20889': 'value60384',
},
    {
    'id': 17527489864081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Rebecca Allen',
    'address': '0742 Joshua Prairie Suite 487\nKingberg, WI 75626',
    'text': 'Deal exist nature trial none marriage would. Prevent table back usually.\nForget lot common young. Ground also we scientist activity worker.',
    'email': 'henryfrank@example.com',
    'phone_number': '480.923.4985x02836',
    'json': {
    'name': 'Carolyn Whitehead',
    'address': '45937 Bennett Port Suite 905\nMichaelton, GU 62661',
},
    'key78313': 'value25934',
    'key66764': 'value42300',
    'key91412': 'value55674',
    'key11116': 'value19190',
    'key79260': 'value54548',
    'key64333': 'value53993',
    'key44421': 'value84533',
},
    {
    'id': 17527489864093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Tonya Elliott',
    'address': '81607 Douglas Meadow Apt. 759\nRitaview, MD 60092',
    'text': 'Go include consumer north investment middle. Property improve property ever type lay door. Instead majority interesting strong rich.',
    'email': 'mathiskevin@example.org',
    'phone_number': '(654)692-3555',
    'json': {
    'name': 'Michael Sanchez',
    'address': '64658 Johnston Knoll Suite 371\nNew Anna, KS 81986',
},
    'key41522': 'value88575',
    'key83922': 'value34432',
    'key87499': 'value99546',
    'key56309': 'value7266',
    'key64973': 'value93065',
    'key882': 'value59837',
    'key70090': 'value71704',
    'key52090': 'value37405',
},
    {
    'id': 17527489864104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jacqueline Williams',
    'address': '0659 Jasmine Neck Suite 208\nNorth Nathan, MT 82501',
    'text': 'Child improve plan huge apply million very. Wear red bag stage any population article. Hit they black moment of old onto against.\nCentral line address happen.',
    'email': 'bobwinters@example.com',
    'phone_number': '(500)944-6725x448',
    'json': {
    'name': 'Maria Hall',
    'address': '204 Jennifer Port Suite 155\nEast Gregory, PA 18260',
},
    'key99738': 'value99885',
    'key53123': 'value42879',
    'key39645': 'value53923',
    'key9018': 'value20132',
    'key73439': 'value27440',
},
    {
    'id': 17527489864115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jessica Chang',
    'address': '42960 Larry Spurs\nNicholasmouth, WV 45597',
    'text': 'Build artist industry politics effort girl. Certain government thought clear star partner glass north. House final while career water. His focus way would paper.',
    'email': 'mitchellhart@example.net',
    'phone_number': '(239)328-4504x4595',
    'json': {
    'name': 'Elizabeth Davis',
    'address': '417 Karen Isle\nLake Benjaminhaven, IL 87992',
},
    'key40996': 'value52799',
    'key13218': 'value16516',
},
    {
    'id': 17527489864126,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Erin Cochran',
    'address': '175 Samantha Meadows Apt. 458\nValeriemouth, CO 37239',
    'text': 'Meeting detail each natural us. Role population too sister boy up. Room throw form usually sign speech.\nImpact use expert star above say life. Part reach behind test.',
    'email': 'sarah81@example.net',
    'phone_number': '+1-292-826-1150x56385',
    'json': {
    'name': 'Joseph Collins',
    'address': '195 Catherine Ports\nSouth Markfort, WA 65260',
},
    'key88183': 'value97946',
    'key28626': 'value60161',
    'key62427': 'value64885',
    'key48578': 'value16597',
    'key33958': 'value11739',
    'key46919': 'value97874',
    'key43632': 'value35732',
    'key34958': 'value44751',
    'key45453': 'value30047',
},
    {
    'id': 17527489864137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Stephen Walls',
    'address': 'PSC 9099, Box 9781\nAPO AA 47692',
    'text': 'Society eye cell open practice western. Assume season moment happen. Peace reflect ground outside impact.',
    'email': 'megan45@example.com',
    'phone_number': '+1-360-294-7887',
    'json': {
    'name': 'Carol Dixon',
    'address': '3780 Payne Place\nWest Sarahstad, NV 81018',
},
    'key57249': 'value55105',
    'key9182': 'value53749',
    'key82944': 'value80364',
    'key78575': 'value77495',
    'key66818': 'value50926',
    'key40743': 'value78794',
},
    {
    'id': 17527489864145,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Brent Wells',
    'address': '4837 Johnson Valleys\nSouth Amberview, OK 70185',
    'text': 'Federal ask fear order allow run whose. Professional page politics section.',
    'email': 'smithwilliam@example.com',
    'phone_number': '+1-470-232-6508x00574',
    'json': {
    'name': 'Sarah Murray',
    'address': 'USS Bentley\nFPO AP 90375',
},
    'key66551': 'value23559',
    'key12634': 'value28072',
    'key2171': 'value77661',
    'key38923': 'value55894',
    'key36372': 'value58389',
    'key86343': 'value35815',
},
    {
    'id': 17527489864155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Taylor Rogers',
    'address': '3732 Brittany Trail Suite 913\nLake Kylemouth, MS 50811',
    'text': 'Environment also inside police window. Bank world lose worker. Ahead town election business reduce test. When piece a grow section market chance.',
    'email': 'william79@example.net',
    'phone_number': '001-276-538-3268x0231',
    'json': {
    'name': 'Diana Day',
    'address': '801 Darren Radial\nBeverlyberg, CO 60021',
},
    'key78901': 'value44935',
},
    {
    'id': 17527489864165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Lindsay Harris',
    'address': '97413 Blake Plain\nPort Sophialand, MS 70885',
    'text': 'Carry professor member him itself majority add.\nLanguage capital just day follow. Hospital third sing.\nNever fight news yeah study really operation. In page offer sell.',
    'email': 'jacksonjacob@example.org',
    'phone_number': '431.638.2822x6478',
    'json': {
    'name': 'Richard Reyes',
    'address': '7573 Ray Garden Apt. 625\nFrazierhaven, FL 81010',
},
    'key37060': 'value66217',
    'key69851': 'value72307',
    'key54359': 'value90065',
    'key18935': 'value81422',
    'key11032': 'value90472',
    'key34930': 'value21646',
    'key1484': 'value3788',
    'key25177': 'value99650',
},
    {
    'id': 17527489864176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Barry Ross',
    'address': '1030 Jonathan Stream\nLindseystad, PW 76055',
    'text': 'Industry relationship us exactly lose no pressure. Edge style live level officer. Seat ago bit talk reveal religious.',
    'email': 'chanpamela@example.org',
    'phone_number': '(696)453-8763x645',
    'json': {
    'name': 'Charles Ramirez',
    'address': '88960 Amy Passage\nAndrademouth, IN 40711',
},
    'key30777': 'value29059',
},
    {
    'id': 17527489864187,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Gloria Perkins',
    'address': '02384 Linda Port\nWest Kimberlyland, NH 94306',
    'text': 'Cup focus second get usually fast. Prove stage because resource law address until trouble.',
    'email': 'hberry@example.net',
    'phone_number': '+1-595-259-0919x352',
    'json': {
    'name': 'Michael Smith',
    'address': '65914 Smith Terrace Apt. 857\nJacobhaven, LA 63075',
},
    'key74777': 'value52653',
    'key17561': 'value17693',
},
    {
    'id': 17527489864198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Pamela Hall',
    'address': '776 Michael Turnpike\nIanfurt, NY 54572',
    'text': 'Interview team all fund detail behavior. Instead behind through bad interesting myself back.\nStar simply meeting to state third. Each over as quality issue onto film.',
    'email': 'mscott@example.com',
    'phone_number': '349.811.9349x20221',
    'json': {
    'name': 'Elizabeth Parsons',
    'address': '2313 Jacob Gardens\nJillberg, RI 86957',
},
    'key69758': 'value67200',
    'key81470': 'value91569',
    'key96204': 'value10422',
    'key33966': 'value90458',
    'key61870': 'value51937',
},
    {
    'id': 17527489864208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Andrew Hamilton',
    'address': 'USS Brown\nFPO AE 27157',
    'text': 'Report game they buy. Score traditional list draw young only recognize.\nWest reach southern could few. Wind teach party someone.',
    'email': 'eric37@example.org',
    'phone_number': '001-322-998-8067x50356',
    'json': {
    'name': 'Lauren Ramirez',
    'address': '2732 Natalie Freeway Apt. 843\nSouth John, VA 10779',
},
    'key72575': 'value94817',
    'key27430': 'value19217',
    'key44977': 'value45803',
    'key46251': 'value37969',
    'key69938': 'value84077',
    'key25609': 'value36608',
},
    {
    'id': 17527489864218,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Christine Harris',
    'address': '84633 Katie Inlet Suite 639\nColetown, ID 99273',
    'text': 'Price clearly scene drug manager.\nPurpose body then right improve tax.\nNice region want ready some order.\nCentury nation find still must. Me send use statement. President this teach land.',
    'email': 'colemanlisa@example.net',
    'phone_number': '(747)944-1674x5234',
    'json': {
    'name': 'Caitlin Davis',
    'address': '337 Bond Estate\nEast Danashire, IN 74387',
},
    'key18748': 'value84894',
},
    {
    'id': 17527489864229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Christine Anderson',
    'address': '221 Dana Plaza\nEast Kelly, KY 60120',
    'text': 'But message general here. Firm market popular.\nDirection institution big scene instead. Make education memory sell.',
    'email': 'asimpson@example.com',
    'phone_number': '(625)912-3678x72926',
    'json': {
    'name': 'Julie Johnson',
    'address': '90031 Johnson Estates\nJessicafurt, AR 16869',
},
    'key97650': 'value86482',
    'key14643': 'value68706',
    'key71528': 'value41831',
    'key20949': 'value59337',
    'key59042': 'value35316',
    'key91276': 'value79512',
    'key10395': 'value47628',
    'key84563': 'value65328',
    'key94340': 'value77452',
    'key97514': 'value60480',
},
    {
    'id': 17527489864239,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Aimee Morris',
    'address': '4635 Ramirez Trail\nEast Davidside, AR 39507',
    'text': 'Mission gun dinner reflect mother join. Likely style early visit enjoy.\nAccording we key national. Quite bill part bar.',
    'email': 'michael34@example.net',
    'phone_number': '2327895255',
    'json': {
    'name': 'Zachary Caldwell',
    'address': '41956 Emily Tunnel Suite 631\nPort Christopher, NH 52280',
},
    'key4545': 'value94566',
    'key15006': 'value93881',
    'key18385': 'value51275',
    'key60376': 'value18096',
    'key89261': 'value2270',
},
    {
    'id': 17527489864250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Meghan Lynch',
    'address': '14605 Manuel Views Suite 599\nSouth Dylanfurt, MO 38508',
    'text': 'Strong control wife little cover. Determine picture risk thus.\nChance everything by religious break. Side memory understand bank mother sometimes. Treatment on call note society father between.',
    'email': 'hgonzalez@example.net',
    'phone_number': '(754)329-3215',
    'json': {
    'name': 'Daniel Parker Jr.',
    'address': '065 Cruz Creek\nAlexandertown, DE 97505',
},
    'key38943': 'value96059',
},
    {
    'id': 17527489864261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Kara Allen',
    'address': '138 Stewart Trace\nLake Amandatown, UT 08910',
    'text': 'Every during adult weight mean. Then father serve growth receive fine.\nSense seven gun child writer. Ball eight vote body successful truth beat. Soon case rest yeah write seven.',
    'email': 'graymichael@example.net',
    'phone_number': '479.295.0427',
    'json': {
    'name': 'Amy Hampton',
    'address': '5338 Jackson Hollow Suite 456\nLake Steven, VT 14631',
},
    'key23091': 'value74395',
    'key27076': 'value44827',
    'key45755': 'value55305',
    'key60851': 'value33108',
    'key86321': 'value59651',
    'key92236': 'value38931',
},
    {
    'id': 17527489864273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Christine Williams',
    'address': '14199 Christopher Station\nJennifertown, OK 08265',
    'text': 'Few represent answer wide marriage. Shoulder family easy agree.\nPartner herself color. Trip so often after father.\nRed half trial already.',
    'email': 'zzuniga@example.com',
    'phone_number': '001-951-767-3432x62027',
    'json': {
    'name': 'Karla Velasquez',
    'address': '1893 Perez Points Suite 854\nJuarezborough, FL 59209',
},
    'key17511': 'value69154',
    'key28440': 'value78542',
    'key79984': 'value54848',
    'key34793': 'value86640',
    'key22575': 'value23729',
    'key99405': 'value76344',
    'key94455': 'value11452',
    'key30804': 'value35113',
},
    {
    'id': 17527489864284,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Amanda Garcia',
    'address': '1724 Smith Flats\nJenniferberg, MA 60613',
    'text': 'Left possible beat agree foot year growth likely. Mind low fire future road defense eight.\nSee like job century field turn. Protect although interest.',
    'email': 'piercebrandon@example.net',
    'phone_number': '001-548-305-4273',
    'json': {
    'name': 'Michelle Hale',
    'address': '9085 Sarah Dam\nSouth James, AZ 37244',
},
    'key15653': 'value67163',
    'key6596': 'value14393',
    'key24698': 'value55203',
    'key93163': 'value1086',
    'key77942': 'value24790',
    'key59261': 'value63421',
    'key13933': 'value58614',
},
    {
    'id': 17527489864296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Charles Walker',
    'address': '7071 Reynolds Locks\nDontown, CO 48657',
    'text': 'Operation catch early. Of pay ahead adult form garden. People one though big because threat.',
    'email': 'dwong@example.org',
    'phone_number': '402.457.4285x701',
    'json': {
    'name': 'Allen Lawrence',
    'address': '797 Bass Manor\nWest Judithmouth, AR 25274',
},
    'key19800': 'value51400',
    'key11003': 'value87122',
    'key99879': 'value23429',
    'key32686': 'value20656',
},
    {
    'id': 17527489864306,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Cameron Robinson',
    'address': '175 Reynolds Bridge Suite 320\nSinghtown, OR 89876',
    'text': 'Stuff popular somebody. Say door very about. Cause field really each.\nPopular moment born toward. Sport five list economic.',
    'email': 'awhite@example.org',
    'phone_number': '+1-907-694-7599',
    'json': {
    'name': 'Collin Chavez',
    'address': '481 Sanchez Union\nNew Lauraburgh, MP 43734',
},
    'key29955': 'value67238',
    'key93633': 'value59605',
    'key34758': 'value25988',
    'key14274': 'value21413',
    'key54830': 'value94728',
    'key54054': 'value7377',
},
    {
    'id': 17527489864318,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Shane Jackson',
    'address': '92552 Ronald Street\nLindsayview, FM 05861',
    'text': 'Finish sea medical. Himself fill anyone bar idea particular risk.',
    'email': 'saralawson@example.com',
    'phone_number': '(623)461-8595x503',
    'json': {
    'name': 'Brenda Henderson',
    'address': 'Unit 6753 Box 0351\nDPO AP 45370',
},
    'key44947': 'value16175',
    'key47330': 'value57634',
    'key35566': 'value89072',
    'key89020': 'value97799',
    'key96924': 'value7677',
},
    {
    'id': 17527489864327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Mackenzie Chavez',
    'address': '7179 Hoffman Crossing Apt. 861\nMejiabury, MD 99758',
    'text': 'Money some state mouth prove trial. Stock capital early become identify claim partner face.\nLot appear born staff a.',
    'email': 'reginaldsmith@example.net',
    'phone_number': '616-663-6172',
    'json': {
    'name': 'Michael Ochoa',
    'address': '734 Hughes Mills Apt. 193\nAllisonborough, PR 55137',
},
    'key72589': 'value43954',
    'key69305': 'value79849',
    'key67182': 'value11768',
    'key17607': 'value12997',
    'key4201': 'value51992',
    'key11759': 'value88236',
    'key51381': 'value3067',
    'key82521': 'value10549',
},
    {
    'id': 17527489864338,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Megan Roth',
    'address': '786 Lewis Spring Suite 063\nSouth Jerryhaven, TX 87731',
    'text': 'Many follow strategy head make billion. Various point almost line fact show. Source performance knowledge cost only usually full tree.\nReport suffer first beat onto father.',
    'email': 'yrichards@example.net',
    'phone_number': '668.430.3955x104',
    'json': {
    'name': 'Patricia York',
    'address': '90661 Grant Park Apt. 875\nPort Kellybury, MA 43490',
},
    'key60267': 'value25892',
    'key68539': 'value38352',
    'key70232': 'value69609',
},
    {
    'id': 17527489864349,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Melissa Ellis',
    'address': '105 Moore Path Suite 541\nLake David, GA 52789',
    'text': 'Research technology prove people environmental early seven recognize. Certain together official discussion woman. Face off develop professional teach. See continue feeling international.',
    'email': 'zfoster@example.net',
    'phone_number': '943-742-1514',
    'json': {
    'name': 'Regina Stein',
    'address': '042 Gomez Brooks\nWoodsmouth, MS 88509',
},
    'key7487': 'value37661',
    'key1539': 'value10944',
    'key42104': 'value78146',
    'key70776': 'value14803',
    'key70371': 'value90217',
    'key1456': 'value93024',
    'key56984': 'value86153',
},
    {
    'id': 17527489864360,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Joshua Miller',
    'address': '58279 Day Drive\nWest Stephanie, MI 78273',
    'text': 'Price memory fill scene. Range work trade.\nImpact picture yard ability new phone Congress. Local leader require beat know church. Lay add rich town at second. Thus two institution financial say.',
    'email': 'mcfarlandgary@example.com',
    'phone_number': '416-288-0309x638',
    'json': {
    'name': 'William Lucas',
    'address': '76534 Michael Motorway\nPort Megan, NY 20552',
},
    'key44413': 'value2473',
    'key50634': 'value48890',
    'key18943': 'value71136',
    'key23186': 'value42728',
    'key37388': 'value65204',
    'key79701': 'value32236',
    'key60248': 'value60280',
    'key68896': 'value45122',
    'key72850': 'value15577',
    'key9598': 'value19877',
},
    {
    'id': 17527489864373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Teresa Gill',
    'address': '65154 Elizabeth Extension\nLake Sarahport, AL 52442',
    'text': 'Example party matter race since sell action. Who notice indicate.\nOutside field these. Door boy before religious four choose.\nIncluding police send much hot ground. Culture collection fact spring.',
    'email': 'browntiffany@example.net',
    'phone_number': '(891)653-3962x2695',
    'json': {
    'name': 'Amber Cuevas',
    'address': '028 Elizabeth Vista\nSouth Angela, WA 04449',
},
    'key88390': 'value72489',
    'key19594': 'value35144',
},
    {
    'id': 17527489864387,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Lindsay Patel',
    'address': '6517 Adams Spring\nSouth Joannashire, NJ 06224',
    'text': 'Government mother mouth cut politics. Ask technology certainly learn everybody indeed. Improve office front either.',
    'email': 'aschroeder@example.com',
    'phone_number': '885-471-3357x450',
    'json': {
    'name': 'Amanda Mccann',
    'address': '74095 Tonya Ridges\nEast Cory, UT 07082',
},
    'key39099': 'value22735',
    'key28528': 'value33794',
    'key93399': 'value58225',
    'key69351': 'value28605',
    'key3238': 'value56414',
    'key56657': 'value51730',
    'key89329': 'value21234',
    'key80688': 'value49867',
    'key9929': 'value58981',
},
    {
    'id': 17527489864401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'David Huff',
    'address': '7774 Alison Garden\nSouth Karaton, AK 47152',
    'text': 'Still hundred air. Green safe single claim.\nNewspaper evening television community much house wish. Camera form in doctor soldier accept.\nMyself wait clearly agree.',
    'email': 'mackenzieedwards@example.com',
    'phone_number': '938.736.3293x196',
    'json': {
    'name': 'Alexis Ramirez',
    'address': '99095 Laurie Drives\nWest Cassandra, KS 38280',
},
    'key84010': 'value90805',
    'key57571': 'value52735',
    'key50076': 'value99399',
    'key55255': 'value90650',
},
    {
    'id': 17527489864415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Brian Jones',
    'address': '4856 James Canyon Apt. 958\nBrittanyburgh, FM 64792',
    'text': 'Charge buy manager part. Financial issue face provide here late result. Person continue drive season others evening.',
    'email': 'velasquezmelanie@example.net',
    'phone_number': '(391)968-1990',
    'json': {
    'name': 'Candace Wright',
    'address': '34865 Michelle Brook Apt. 674\nNew Charlesborough, MT 04435',
},
    'key15471': 'value35278',
    'key49256': 'value59729',
},
    {
    'id': 17527489864429,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Margaret Conley',
    'address': '148 Jeremy Junction\nNew Alexaside, WA 73000',
    'text': 'Partner price win there Republican. According face close information enough.\nMaybe central opportunity look. During ok a news baby wait. Return factor suggest about.',
    'email': 'jeffrey30@example.com',
    'phone_number': '001-732-962-2774',
    'json': {
    'name': 'Bridget Rosales',
    'address': '2605 Gardner Road\nWest Jessica, NJ 82772',
},
    'key74752': 'value37185',
},
    {
    'id': 17527489864442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Joshua Page',
    'address': '1917 Erica Trafficway Suite 714\nJonesshire, AR 02098',
    'text': 'Tell trade miss visit language. Those another rock several mention show cost.\nGrowth medical ground economic. Decade treatment reveal decide memory.',
    'email': 'phillipsbrianna@example.com',
    'phone_number': '984-835-5845x0940',
    'json': {
    'name': 'Ashley Hamilton',
    'address': '63788 Munoz Ville\nAndersenborough, CA 76111',
},
    'key14256': 'value37506',
    'key35087': 'value68073',
    'key6897': 'value66258',
    'key70831': 'value2329',
    'key28514': 'value65742',
    'key79636': 'value10022',
    'key98452': 'value15256',
    'key25374': 'value66184',
    'key97439': 'value27192',
},
    {
    'id': 17527489864457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Brandy Cruz',
    'address': '0073 Justin Shore\nDonaldville, OH 42795',
    'text': 'Quality operation whole whom. Three public own clearly.\nComputer pass reveal son result. Edge school court apply.',
    'email': 'masonscott@example.net',
    'phone_number': '001-918-276-7854',
    'json': {
    'name': 'Allison Mendoza',
    'address': 'PSC 0534, Box 3258\nAPO AE 53834',
},
    'key98476': 'value90750',
    'key99717': 'value62483',
    'key3315': 'value17152',
    'key73090': 'value17427',
    'key47481': 'value45216',
    'key11522': 'value17718',
    'key55782': 'value94324',
},
    {
    'id': 17527489864469,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'John Boyd',
    'address': '562 Sims Trail\nNew Natalie, PR 78142',
    'text': 'Meeting shoulder worry land bed become. Dog executive memory most coach. Job on better give instead lawyer skill.',
    'email': 'taylorricky@example.net',
    'phone_number': '+1-308-756-5539x88552',
    'json': {
    'name': 'Rachel Robles',
    'address': 'PSC 2677, Box 0545\nAPO AA 36117',
},
    'key2771': 'value17041',
    'key44396': 'value79383',
    'key34270': 'value21632',
    'key15017': 'value75912',
    'key12552': 'value75138',
},
    {
    'id': 17527489864480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Kristina Mclaughlin MD',
    'address': '70922 Patricia Knoll Suite 101\nLake Michael, AR 82268',
    'text': 'Purpose second trade say official film remain. Carry black specific board account other. Anyone form there treatment risk.',
    'email': 'bradyjustin@example.org',
    'phone_number': '001-496-555-6091x072',
    'json': {
    'name': 'Dawn Reid',
    'address': '0737 Scott Shores Suite 753\nPort Bethany, MP 47257',
},
    'key10347': 'value11210',
    'key22759': 'value65921',
    'key27178': 'value48228',
    'key47206': 'value92755',
    'key56761': 'value3012',
    'key66549': 'value35573',
    'key71153': 'value88077',
},
    {
    'id': 17527489864491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Danielle Duran',
    'address': '35423 Susan Via Suite 381\nSouth Andrewport, SD 86341',
    'text': 'Positive career office pull he. Court religious military win born front. Work occur recognize fear.',
    'email': 'davidtorres@example.org',
    'phone_number': '706-589-8538',
    'json': {
    'name': 'Cheryl Martin',
    'address': '913 Charles Plain Apt. 195\nBillyland, LA 84053',
},
    'key74165': 'value57673',
    'key88056': 'value54158',
},
    {
    'id': 17527489864502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Christine Walsh',
    'address': '71385 Fisher Bridge\nGreenfurt, HI 16665',
    'text': 'Issue trial step table into cost. Work pick concern skill upon represent design. Cup summer woman.',
    'email': 'tyoder@example.org',
    'phone_number': '4318405062',
    'json': {
    'name': 'Jessica Roberts',
    'address': '6326 Kayla Parkway\nEast Samantha, KY 80249',
},
    'key42847': 'value62493',
    'key83527': 'value16809',
    'key87789': 'value17492',
    'key90739': 'value30329',
    'key25315': 'value57727',
    'key15706': 'value7067',
    'key57332': 'value32049',
    'key90607': 'value30213',
},
    {
    'id': 17527489864512,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'John Oconnor',
    'address': '16598 Debra Mills Suite 996\nBeckborough, NM 86324',
    'text': 'Modern push north training party recognize worry. Environment environmental join attention billion throw dark.\nLocal question hair attention difference everything.',
    'email': 'millsbrian@example.org',
    'phone_number': '880-244-8288x2995',
    'json': {
    'name': 'James Bell',
    'address': '920 Christopher Village\nNorth Juliafort, FM 07376',
},
    'key37929': 'value3147',
    'key46218': 'value79986',
    'key19716': 'value1517',
    'key94344': 'value26506',
    'key67678': 'value98634',
    'key79200': 'value27949',
    'key19585': 'value41769',
},
    {
    'id': 17527489864524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Kenneth Morris',
    'address': 'USCGC Brady\nFPO AE 76505',
    'text': 'Voice top American back civil just. Hard at human main. Service page position father shoulder what.',
    'email': 'davisjeffrey@example.com',
    'phone_number': '422.546.8755',
    'json': {
    'name': 'Nicole Castro',
    'address': '95767 Vaughn Row\nNew Joseshire, VA 00562',
},
    'key45533': 'value76051',
    'key21162': 'value69267',
    'key69332': 'value81499',
},
    {
    'id': 17527489864534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Brian Vargas',
    'address': '050 Edward Street\nSouth Amychester, KY 21012',
    'text': 'Oil look quickly key painting forward individual. Worker staff trip rule today. Read herself skin five force successful.\nEffort finally know not possible some through. Visit health he fact respond.',
    'email': 'christinawaters@example.com',
    'phone_number': '+1-297-731-3353',
    'json': {
    'name': 'Joseph Peters',
    'address': '780 Jorge Course Apt. 865\nLake Alan, KY 02457',
},
    'key3256': 'value57421',
},
    {
    'id': 17527489864545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Troy Hill',
    'address': 'PSC 2449, Box 5654\nAPO AA 57327',
    'text': 'Late prove company budget however likely say. Here many produce ok fish.\nHotel contain performance arrive environmental. Institution deal perhaps. Compare father four follow.',
    'email': 'taylorkatherine@example.net',
    'phone_number': '853.945.1029',
    'json': {
    'name': 'James Allen',
    'address': '7982 Smith Ville\nMichaelton, MH 15914',
},
    'key46536': 'value36815',
    'key77521': 'value4551',
    'key349': 'value26941',
    'key86544': 'value94667',
    'key54646': 'value53691',
    'key87890': 'value14420',
},
    {
    'id': 17527489864568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Natasha Acosta',
    'address': '69889 Julia Summit\nWilliamsport, PW 60478',
    'text': 'Century board compare body bad lose. Onto probably head including.\nOut myself cold physical seek fire within while. Defense medical no before degree name.',
    'email': 'raymond99@example.net',
    'phone_number': '+1-849-631-2557x890',
    'json': {
    'name': 'Cynthia Tran',
    'address': 'PSC 2324, Box 1838\nAPO AP 54223',
},
    'key14689': 'value40057',
    'key57698': 'value54072',
    'key16635': 'value96241',
    'key22521': 'value12189',
    'key71018': 'value63913',
    'key85995': 'value802',
    'key89544': 'value31444',
    'key70595': 'value16793',
    'key44893': 'value63209',
    'key44750': 'value5314',
},
    {
    'id': 17527489864577,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Lisa Ortiz',
    'address': '3702 Parks Springs Apt. 957\nTamiborough, HI 82659',
    'text': 'Since bed family. Cover name both interest on sound.\nState red serious late need. Single begin wall necessary affect police teach.',
    'email': 'rmills@example.com',
    'phone_number': '001-442-276-7089x6814',
    'json': {
    'name': 'Nancy Vincent',
    'address': '0185 Brown Stream Apt. 383\nPort Sethmouth, OR 02288',
},
    'key64046': 'value57250',
},
    {
    'id': 17527489864588,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Christina Moreno',
    'address': '53496 Craig Skyway\nEast Tracy, MO 43726',
    'text': 'Question moment as lose last history turn choose. Red look order media.\nWho price apply sense way realize fly her. Feel visit grow eye gun few. Continue expect believe difficult person us box.',
    'email': 'nicholas76@example.net',
    'phone_number': '399.324.5961',
    'json': {
    'name': 'Mark Miller',
    'address': '7991 Robbins Corners\nWilliamsberg, NH 91156',
},
    'key71800': 'value14595',
    'key26568': 'value88283',
    'key15006': 'value16375',
    'key69395': 'value97431',
    'key11813': 'value73344',
},
    {
    'id': 17527489864599,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Diana Vaughn',
    'address': '090 Harrington Stravenue Apt. 960\nBeanbury, IL 36400',
    'text': 'Very few risk with law store. Itself somebody data century. Eight as professor.',
    'email': 'howardamanda@example.org',
    'phone_number': '225.512.6239x9894',
    'json': {
    'name': 'Regina Eaton',
    'address': '8613 Nicole Spurs\nWilliamsview, UT 56516',
},
    'key51768': 'value43713',
    'key20296': 'value30038',
    'key48321': 'value51653',
    'key77264': 'value68680',
    'key36562': 'value88354',
    'key66364': 'value6824',
    'key41200': 'value62529',
    'key83831': 'value669',
},
    {
    'id': 17527489864610,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Guy Salinas',
    'address': 'USNS Espinoza\nFPO AA 53337',
    'text': 'Sometimes relate kind become while money. At score how claim.\nGarden middle employee feel rise show hear radio.\nPolitics rule page girl discuss. Worker only trouble chair response relationship.',
    'email': 'lfuller@example.com',
    'phone_number': '+1-965-934-3638',
    'json': {
    'name': 'Michael Whitehead',
    'address': '04813 Michele Villages\nNorth Adrienne, DE 79381',
},
    'key2026': 'value59783',
    'key85173': 'value89214',
    'key5466': 'value80346',
    'key72706': 'value36621',
},
    {
    'id': 17527489864620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Mark Nguyen',
    'address': '854 Conrad Isle\nChristopherchester, GU 06456',
    'text': 'Sea sometimes high perform hit. Approach reality environmental several situation think.\nWriter military four product. Market image like reveal.',
    'email': 'paul53@example.org',
    'phone_number': '833.724.5788x25854',
    'json': {
    'name': 'Preston Jordan',
    'address': '689 Carlos Drive Suite 216\nJasmineside, MT 72855',
},
    'key46177': 'value38119',
    'key20961': 'value97673',
    'key17588': 'value49242',
    'key53731': 'value65271',
    'key63006': 'value96585',
    'key39039': 'value68180',
    'key9549': 'value6371',
    'key53092': 'value75618',
    'key62955': 'value13673',
    'key56325': 'value17494',
},
    {
    'id': 17527489864630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Shelly Wu',
    'address': '5325 Ray Row Suite 570\nSouth Codyhaven, WI 32204',
    'text': 'Will politics where picture. Sign trouble change test name.\nSystem financial avoid. Although maintain thought land magazine case deal. Too respond easy woman left nation consider.',
    'email': 'kathryn59@example.com',
    'phone_number': '001-985-929-2741x30585',
    'json': {
    'name': 'Brian Hayes',
    'address': '3240 James View\nNorth Suzannebury, NC 49638',
},
    'key62948': 'value43303',
    'key67350': 'value85535',
    'key57624': 'value43843',
    'key69874': 'value15171',
    'key49873': 'value58582',
    'key83082': 'value45545',
    'key91519': 'value72415',
},
    {
    'id': 17527489864641,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Jody Cisneros',
    'address': '18483 Pacheco Lock Suite 979\nMonicachester, OK 23785',
    'text': 'Green Mr best meeting sell PM understand brother. Likely call whatever course put.\nChallenge fine well employee. Represent clear indeed.',
    'email': 'stephaniemartin@example.com',
    'phone_number': '+1-289-857-3632x7410',
    'json': {
    'name': 'Richard Stokes',
    'address': '05792 Anthony Common Apt. 801\nTuckershire, PW 19807',
},
    'key11763': 'value23965',
    'key54902': 'value22916',
    'key83366': 'value8746',
    'key19382': 'value38784',
    'key73413': 'value34180',
},
    {
    'id': 17527489864653,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Cody Alvarado',
    'address': '8672 Julie Mews Suite 527\nAmyport, OH 90282',
    'text': 'Company go whether always speak. Can early fire at mission.\nOfficer great book size. Boy member evidence player operation well finally.',
    'email': 'ericjones@example.com',
    'phone_number': '823.221.1268',
    'json': {
    'name': 'Diana Warner',
    'address': '9019 Hudson Landing Apt. 310\nDenisefurt, PA 64339',
},
    'key6788': 'value53475',
    'key70145': 'value80932',
    'key6620': 'value65966',
},
    {
    'id': 17527489864664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Frank Lee',
    'address': '242 Nicole Bridge Suite 570\nOconnorburgh, ND 11695',
    'text': 'See senior figure fear current feeling popular back. Movie hit Mrs surface home blue.\nCulture health total purpose force. Spend edge drop ago American because.',
    'email': 'jenniferharper@example.org',
    'phone_number': '+1-623-445-0326x39307',
    'json': {
    'name': 'Gina Mills',
    'address': '6972 King Road Suite 432\nPatrickview, NJ 87639',
},
    'key74892': 'value29431',
    'key25530': 'value41551',
    'key38790': 'value75207',
},
    {
    'id': 17527489864676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Thomas Garcia',
    'address': '3633 Clark Turnpike Suite 466\nKeyview, WI 62399',
    'text': 'Value quality eat art matter wife institution. Identify condition if skin of.',
    'email': 'jasonberry@example.net',
    'phone_number': '497-955-4427x59597',
    'json': {
    'name': 'Cole Rios',
    'address': 'Unit 5325 Box 7521\nDPO AP 52281',
},
    'key69858': 'value42502',
    'key96500': 'value2164',
    'key96929': 'value59785',
    'key13811': 'value19410',
    'key82487': 'value18327',
    'key23937': 'value30831',
    'key65110': 'value6588',
    'key34158': 'value40969',
    'key17785': 'value74524',
    'key44303': 'value16468',
},
    {
    'id': 17527489864686,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Daniel Kaiser',
    'address': '84356 Walter Curve\nJesseton, MP 31683',
    'text': 'Case music world organization. Management front ground PM culture. Raise agreement beautiful cut his.\nChance teacher but officer. Trip pull rise challenge though TV generation.',
    'email': 'hickslauren@example.org',
    'phone_number': '(226)824-5309x997',
    'json': {
    'name': 'Samantha Rodriguez',
    'address': '141 Natasha Park Apt. 009\nWest Amandaberg, OK 65420',
},
    'key75956': 'value86685',
    'key2650': 'value59400',
    'key92072': 'value60291',
    'key56993': 'value51428',
    'key1322': 'value63155',
    'key85785': 'value89591',
    'key10868': 'value24003',
    'key22980': 'value11853',
    'key5885': 'value15760',
},
    {
    'id': 17527489864696,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Kathryn Atkins',
    'address': '86965 Klein Harbor Suite 866\nNew Nathan, KS 52299',
    'text': 'Ask PM technology enter near. Fight land conference. Officer candidate third way oil.\nVarious decide answer and parent rise research. Fund behavior cover.',
    'email': 'pachecoraymond@example.com',
    'phone_number': '899.990.4525',
    'json': {
    'name': 'Christopher Reed',
    'address': '4883 Brown Track\nLynchburgh, MD 40856',
},
    'key23430': 'value99146',
    'key43768': 'value12517',
    'key84449': 'value98324',
    'key86187': 'value9707',
    'key55185': 'value12309',
    'key87778': 'value52153',
    'key67995': 'value66661',
},
    {
    'id': 17527489864708,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Jill Johnson',
    'address': '5762 Corey Oval Suite 952\nAndersonland, PW 04202',
    'text': 'Everybody color weight husband business. Attorney environment carry sure knowledge. Decide might involve measure federal environment page.',
    'email': 'matthewjohnson@example.net',
    'phone_number': '+1-401-474-5622x49533',
    'json': {
    'name': 'Christina Stein',
    'address': '542 Joseph Corner\nNew Christopher, LA 41797',
},
    'key18330': 'value24663',
    'key29843': 'value14542',
    'key98979': 'value83493',
    'key80180': 'value27348',
    'key59872': 'value403',
    'key34455': 'value42852',
    'key93650': 'value24028',
    'key77356': 'value20333',
},
    {
    'id': 17527489864720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Nicholas Mcdaniel',
    'address': '9647 Anderson Summit\nWest Natalie, PR 37100',
    'text': 'Pattern argue against detail represent minute hot. Often real state worry thousand prove lawyer free.',
    'email': 'jesse57@example.net',
    'phone_number': '(667)278-5482x90346',
    'json': {
    'name': 'Troy Williams',
    'address': '573 Craig Corner Apt. 251\nSouth Nicole, PR 02624',
},
    'key777': 'value1518',
    'key68617': 'value47558',
    'key90956': 'value65858',
    'key26441': 'value28190',
},
    {
    'id': 17527489864732,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Christopher Lee',
    'address': '397 Gary Island\nAnnhaven, WY 35476',
    'text': 'Score action wall trade heavy could buy. Boy change place modern culture. Take size anything spend message report hospital class.\nNow want beat water floor million. Require summer hand out.',
    'email': 'charvey@example.net',
    'phone_number': '6678763307',
    'json': {
    'name': 'Heather Morgan',
    'address': '568 Baker Walk Apt. 008\nNicholashaven, OR 38119',
},
    'key61158': 'value98768',
    'key12382': 'value73583',
},
    {
    'id': 17527489864744,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Michael Spence',
    'address': '414 Barber Fall\nNorth Amber, OH 06611',
    'text': 'Foreign wide bad hospital leg each he. Choice water letter. Window level training down husband.\nLeft allow in couple appear. Home idea appear wide itself share.',
    'email': 'stephaniescott@example.net',
    'phone_number': '(317)273-4500',
    'json': {
    'name': 'Linda Olsen',
    'address': '977 Stevens Mill\nSabrinastad, AZ 14108',
},
    'key33395': 'value59272',
    'key60627': 'value52549',
    'key53637': 'value69907',
    'key36382': 'value53929',
    'key68107': 'value71941',
    'key5097': 'value26755',
    'key56934': 'value45730',
    'key22833': 'value84311',
},
    {
    'id': 17527489864756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Meredith Beck',
    'address': '032 Lambert Mount\nElijahchester, WY 13024',
    'text': 'Down woman organization seven ten address. Interesting car anything long chair. Others five entire certainly true.',
    'email': 'youngjoseph@example.org',
    'phone_number': '732.457.6133x223',
    'json': {
    'name': 'Renee Lawson',
    'address': '0307 Wise Cliffs Suite 489\nNorth Matthew, PW 65167',
},
    'key16525': 'value91392',
    'key85738': 'value10617',
    'key2598': 'value52134',
    'key50113': 'value93989',
    'key28453': 'value20472',
    'key3298': 'value18462',
    'key54683': 'value23816',
    'key25639': 'value12424',
    'key55734': 'value59523',
},
    {
    'id': 17527489864769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Mark West',
    'address': 'USNS Rivera\nFPO AP 80434',
    'text': 'System east such small culture them. Defense move full staff. Everybody mind network policy line young especially.\nMuch as morning leg. Manage suddenly responsibility.',
    'email': 'lisa56@example.org',
    'phone_number': '788-709-8475x362',
    'json': {
    'name': 'Nathan Barry',
    'address': '37509 Alan Passage Suite 377\nCooperberg, MN 49392',
},
    'key93438': 'value34441',
},
    {
    'id': 17527489864780,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Gregg Guerra',
    'address': 'Unit 4760 Box 6568\nDPO AE 06340',
    'text': 'Carry most would. Decade research strong east. Huge truth drug experience modern buy try.',
    'email': 'qwarren@example.org',
    'phone_number': '898.384.6669',
    'json': {
    'name': 'Amber Grimes',
    'address': '9414 Nelson Oval Suite 027\nChapmanberg, ND 91511',
},
    'key58451': 'value40751',
    'key41716': 'value46461',
},
    {
    'id': 17527489864790,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Juan Williams',
    'address': '368 Shelia Harbors\nWest Teresaport, KY 06697',
    'text': 'In their give respond tax worker stock. Believe west south difference far business. Agency now machine many box without.',
    'email': 'cleach@example.net',
    'phone_number': '(585)436-9716',
    'json': {
    'name': 'Keith Bruce',
    'address': '3132 Williams Mall\nAndreabury, FL 68199',
},
    'key87270': 'value5751',
    'key20167': 'value64917',
},
    {
    'id': 17527489864805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Emily Maxwell',
    'address': '181 Tracey Roads Apt. 948\nEast Jacquelinebury, ME 92455',
    'text': 'Cold marriage create finish could after. Have fear TV vote. Room fish pressure hold ten themselves.\nGirl fast page. Our news adult report decision bag. Teacher relate new.',
    'email': 'brucekathy@example.org',
    'phone_number': '(849)531-7645x093',
    'json': {
    'name': 'David Olsen',
    'address': '56347 Weaver Alley\nNorth Jeffrey, MA 51214',
},
    'key95188': 'value73251',
    'key81315': 'value69035',
    'key801': 'value63376',
    'key57882': 'value71439',
    'key87081': 'value68515',
},
    {
    'id': 17527489864821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Teresa Johnson',
    'address': '8816 Miller Inlet Apt. 366\nWest Trevorburgh, OR 29688',
    'text': 'Degree strategy I meeting fine live. Edge view half under despite. Different eat whom outside reflect daughter shake. Accept important member hold security.',
    'email': 'osimpson@example.net',
    'phone_number': '813-542-1835x1863',
    'json': {
    'name': 'Jonathan Carpenter',
    'address': '8394 Baker Dam\nBakerside, CT 02939',
},
    'key22241': 'value72095',
    'key67925': 'value54541',
    'key58875': 'value35402',
    'key56168': 'value62439',
    'key18031': 'value63249',
    'key86848': 'value33373',
},
    {
    'id': 17527489864835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Julia Kramer',
    'address': '198 David Courts Apt. 034\nWest Paul, MO 79886',
    'text': 'Under line activity yes light everything house. Head personal also.\nForm various where project surface. Minute we parent detail toward senior trade.',
    'email': 'rebeccajackson@example.org',
    'phone_number': '5053559091',
    'json': {
    'name': 'Jennifer Collier',
    'address': '860 Cassie Pines Apt. 529\nPort Stephen, MS 86074',
},
    'key31372': 'value3175',
    'key91542': 'value82356',
    'key61868': 'value80475',
    'key86320': 'value65396',
    'key16679': 'value3488',
    'key46387': 'value74142',
},
    {
    'id': 17527489864850,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Rebecca Sutton',
    'address': '88789 Christian Roads\nSouth Drew, NC 97882',
    'text': 'Father father probably receive speech or win more. Within Republican authority large message.\nHot blood others hotel. Lawyer most policy.',
    'email': 'tlynn@example.net',
    'phone_number': '001-339-841-0462x488',
    'json': {
    'name': 'Mrs. Renee Nguyen',
    'address': '764 Michael Inlet Apt. 128\nWendyhaven, NJ 81461',
},
    'key92037': 'value59493',
    'key80185': 'value62326',
    'key50762': 'value66387',
    'key42173': 'value25097',
    'key4995': 'value77158',
    'key43492': 'value27033',
},
    {
    'id': 17527489864864,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Alison Hoover',
    'address': '477 Joshua Junction\nMunozmouth, FL 32092',
    'text': 'Hear when full heavy never old. View question debate range yourself. Official part number boy pass since report.',
    'email': 'dhanna@example.org',
    'phone_number': '597-491-4895x77879',
    'json': {
    'name': 'Allison Meyer',
    'address': '76595 Cody Ford\nAdriennestad, MS 55095',
},
    'key48178': 'value79760',
},
    {
    'id': 17527489864879,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Derek Chavez',
    'address': '25828 Forbes Valley Apt. 948\nKatieton, LA 20417',
    'text': 'Too research perhaps either maintain policy form role. Mention call surface market. Under pressure type near.\nCommunity system race.',
    'email': 'stephaniejohnson@example.com',
    'phone_number': '455-448-0944x695',
    'json': {
    'name': 'Larry Martin',
    'address': '17699 Davis Curve\nEast Robert, SD 77029',
},
    'key82389': 'value32835',
    'key4268': 'value39618',
    'key65944': 'value18932',
},
    {
    'id': 17527489864894,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Anthony Wu',
    'address': '7587 Byrd Forks Apt. 604\nDanieltown, VA 64088',
    'text': 'Agreement key door technology house. Sound bar ever your.\nBlood me behind situation a. Way see draw TV.\nHis act more change note month. Media everybody eight some.\nTelevision hard know middle.',
    'email': 'mendozapaul@example.net',
    'phone_number': '001-325-787-9342x57265',
    'json': {
    'name': 'Melissa Armstrong',
    'address': '14028 Ford Ways Apt. 217\nJessicaborough, NC 91977',
},
    'key92920': 'value81409',
    'key71317': 'value55212',
    'key39047': 'value4979',
    'key93232': 'value67728',
    'key83694': 'value8066',
    'key14166': 'value9012',
    'key32989': 'value50138',
},
    {
    'id': 17527489864909,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Susan Cruz',
    'address': '0387 Susan Loop Suite 414\nNew Kelly, TX 74078',
    'text': 'Third stuff could often tax. Energy environment yeah past rock sure.\nActivity call position his garden force. Modern son national live much concern edge.',
    'email': 'david52@example.com',
    'phone_number': '240.751.9548x8562',
    'json': {
    'name': 'Mark Orozco',
    'address': '242 Hunt Mountain\nRowlandview, HI 27698',
},
    'key39929': 'value65032',
    'key85694': 'value94301',
    'key19923': 'value3883',
},
    {
    'id': 17527489864921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Michael Estrada',
    'address': '327 Garcia Extension\nThomasfort, MH 45720',
    'text': 'Next senior life my order black. Person body imagine teacher party within than reason.\nLaw apply lead. Drive his nearly.',
    'email': 'helenallen@example.com',
    'phone_number': '(699)812-4124x76107',
    'json': {
    'name': 'Beverly Hoffman',
    'address': '672 Brown View Suite 503\nErikachester, CA 91904',
},
    'key48473': 'value20386',
    'key93054': 'value29538',
    'key14400': 'value90369',
    'key22359': 'value29596',
    'key81371': 'value88710',
    'key68318': 'value54278',
    'key5455': 'value19911',
    'key51781': 'value62131',
    'key71869': 'value95545',
},
    {
    'id': 17527489864933,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Tammy Weber',
    'address': '35274 Cooper Forge Apt. 031\nJoshuabury, CO 83173',
    'text': 'Consumer yes score off cell production real. Create successful civil someone eat myself high this. Example cut behind fill decade central miss.',
    'email': 'sreyes@example.org',
    'phone_number': '(412)632-2459',
    'json': {
    'name': 'Sharon Brown',
    'address': '755 Gina Locks Suite 075\nMaureenmouth, UT 89601',
},
    'key78628': 'value79203',
},
    {
    'id': 17527489864944,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Patricia Saunders',
    'address': '27298 Holly Hill\nNorth Patrickberg, CO 43641',
    'text': 'Activity behind natural reason reach. Entire market year score civil if. Public such position structure officer. Son moment order short.',
    'email': 'danielslydia@example.com',
    'phone_number': '661-547-4717x19524',
    'json': {
    'name': 'Angela Trujillo',
    'address': '5711 David Walks Suite 325\nGarciafort, LA 90252',
},
    'key18456': 'value94297',
    'key50704': 'value45151',
    'key5635': 'value8558',
},
    {
    'id': 17527489864955,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Carla Walker',
    'address': '98815 Jamie Tunnel Suite 544\nPaultown, SD 59355',
    'text': 'North recent everything relate forward. Learn million force deal focus once available. Water our section anyone husband daughter federal decision.',
    'email': 'larsonchelsea@example.org',
    'phone_number': '947.280.0013x71358',
    'json': {
    'name': 'Sydney Allen',
    'address': '82489 John Well\nCandicetown, TN 90869',
},
    'key66597': 'value80252',
    'key60724': 'value39207',
    'key40307': 'value20461',
},
    {
    'id': 17527489864967,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Justin Fisher',
    'address': '389 Long Neck Suite 127\nDavenportside, MH 69410',
    'text': 'Pass accept in. Real record assume nice music eat. Number itself body unit what.\nBefore number budget available born own. Mind believe page true everyone same spring.',
    'email': 'brandon21@example.org',
    'phone_number': '678-640-8897',
    'json': {
    'name': 'Taylor Chen',
    'address': '450 Barker Common Apt. 522\nSouth Adambury, IA 40168',
},
    'key84823': 'value72374',
    'key47632': 'value86852',
    'key97997': 'value44701',
    'key52333': 'value89080',
    'key13433': 'value35304',
    'key46599': 'value97038',
    'key19854': 'value22804',
    'key49298': 'value16376',
    'key68421': 'value71209',
},
    {
    'id': 17527489864978,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Ms. Patricia Collins',
    'address': '551 Cuevas Mall\nVincentmouth, PR 55045',
    'text': 'Herself to go walk store their whole. Since traditional cultural act factor discover.\nInteresting middle real threat whom protect. Lead think husband deal certainly.',
    'email': 'herrerajames@example.com',
    'phone_number': '973-762-0213',
    'json': {
    'name': 'Meghan Norris',
    'address': '9637 Yu Pines Suite 291\nDanielhaven, MO 64484',
},
    'key66822': 'value13183',
    'key42678': 'value22441',
    'key75488': 'value91852',
    'key57713': 'value18490',
    'key67701': 'value9996',
    'key29056': 'value70951',
    'key33599': 'value46093',
    'key58068': 'value81778',
    'key61866': 'value37014',
    'key61953': 'value43582',
},
    {
    'id': 17527489864990,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Brian White',
    'address': '48681 Mark Ville Suite 562\nStephaniechester, NE 26480',
    'text': 'One tell among article. Little doctor recent style. Type hour contain on may government around.',
    'email': 'taylormichael@example.com',
    'phone_number': '+1-256-592-7075x3480',
    'json': {
    'name': 'Christine Farley',
    'address': '4690 Patterson Mountain\nShawnmouth, VI 04655',
},
    'key41475': 'value55497',
    'key86372': 'value69531',
    'key88725': 'value83550',
    'key58517': 'value96423',
    'key77917': 'value36110',
    'key75840': 'value38245',
    'key31687': 'value91424',
},
    {
    'id': 17527489865002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Daniel Tucker',
    'address': '247 Jeffrey Route Suite 701\nEast Andrew, DC 69599',
    'text': 'Result none feeling vote leader issue sound. Sister year break.\nEasy production truth site candidate. Budget despite yet box long evidence check.',
    'email': 'sbradford@example.com',
    'phone_number': '516.534.2688x61303',
    'json': {
    'name': 'Donna Lester',
    'address': '23057 Duke Stravenue\nDariusfort, VA 53805',
},
    'key49683': 'value20631',
    'key48596': 'value79156',
    'key54374': 'value10959',
    'key51038': 'value93555',
    'key13334': 'value20418',
    'key69200': 'value70713',
    'key1459': 'value75017',
    'key97346': 'value42384',
    'key16820': 'value30710',
    'key91133': 'value14126',
},
    {
    'id': 17527489865013,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Carl Torres',
    'address': '209 Amanda Shore\nDianemouth, MN 67006',
    'text': 'Order despite tend so expect provide your. Those discuss lose consider. Every usually discover skin leave adult.\nPeople since establish truth. Do write message final. Often recently serve suddenly.',
    'email': 'seanwells@example.net',
    'phone_number': '9069610994',
    'json': {
    'name': 'David Haley',
    'address': '566 Russo Path Apt. 602\nAlexanderburgh, VT 98310',
},
    'key88867': 'value17155',
    'key12215': 'value14665',
    'key30075': 'value26317',
},
    {
    'id': 17527489865024,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'George King',
    'address': '63849 Gregory Isle\nSouth Ethantown, NV 62252',
    'text': 'Bed live skin full material tell. Crime section meeting break.\nInvestment star evidence explain. Can indicate huge performance employee board decide site. From receive employee a unit on prevent.',
    'email': 'william12@example.net',
    'phone_number': '332-399-1519',
    'json': {
    'name': 'Madison Phillips',
    'address': '241 Melissa Ford\nLake Danielfurt, TX 38622',
},
    'key39172': 'value64203',
    'key47759': 'value45480',
    'key42538': 'value70381',
},
    {
    'id': 17527489865034,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Ralph Hunt',
    'address': 'USCGC Leach\nFPO AA 00908',
    'text': 'Assume walk reality. Always answer magazine serve call discussion.\nChange carry question main. Off environment morning party edge mean meeting. Factor at include base.',
    'email': 'caitlynthompson@example.net',
    'phone_number': '(271)756-4454',
    'json': {
    'name': 'Scott Allen',
    'address': '368 Miller Spur Apt. 844\nTeresamouth, MN 54927',
},
    'key79988': 'value76026',
    'key21512': 'value26185',
    'key79566': 'value10860',
    'key15977': 'value56089',
    'key78004': 'value37511',
    'key93588': 'value38100',
},
    {
    'id': 17527489865045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Kathryn Montgomery',
    'address': '8218 Michelle Court Apt. 398\nNorth Chad, NE 45731',
    'text': 'Explain now here student. Business alone do build hospital develop officer. Voice large many majority knowledge reflect ahead. Quality those staff strategy safe.',
    'email': 'rodriguezjoshua@example.org',
    'phone_number': '600-996-9113',
    'json': {
    'name': 'Anthony Montgomery',
    'address': '6326 Crystal Motorway Suite 873\nSouth Yvetteborough, DE 87364',
},
    'key17015': 'value96206',
    'key35239': 'value57707',
    'key84250': 'value65613',
    'key75369': 'value30119',
    'key55449': 'value78058',
    'key4936': 'value9091',
    'key84495': 'value41946',
    'key81416': 'value7902',
    'key93803': 'value2',
},
    {
    'id': 17527489865057,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Daniel Adams',
    'address': '9761 Monique Lane\nSouth Cynthia, MA 26428',
    'text': 'Somebody democratic eight young order. Until method view story move list Mr around. Decide might leave product reflect worker fact.',
    'email': 'rebecca06@example.org',
    'phone_number': '734.733.3256x40298',
    'json': {
    'name': 'Benjamin Kelley',
    'address': 'Unit 3807 Box 2137\nDPO AA 46832',
},
    'key73833': 'value91080',
    'key67149': 'value38073',
},
    {
    'id': 17527489865066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Tiffany Horne',
    'address': '3778 Richard Mountain\nFloresshire, MI 51740',
    'text': 'Business him worry scientist. Truth soldier hand age. Industry scene major successful southern recognize.',
    'email': 'bryantrichard@example.org',
    'phone_number': '(469)524-1997',
    'json': {
    'name': 'Brittany Rice DDS',
    'address': '2099 James Summit\nLake Oscar, VA 59921',
},
    'key77328': 'value30902',
    'key90144': 'value9207',
    'key24880': 'value24276',
},
    {
    'id': 17527489865077,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Drew Singleton PhD',
    'address': '4005 Gonzalez Village\nNew Edward, MO 79743',
    'text': 'Yard people your hot present reveal. Talk same clearly. Attention hard conference claim along right.',
    'email': 'keychristopher@example.net',
    'phone_number': '7776765374',
    'json': {
    'name': 'Brenda Watts',
    'address': '32433 Julia Manor Apt. 697\nWest Ryan, OR 26672',
},
    'key49408': 'value26274',
},
    {
    'id': 17527489865089,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Leslie Perry',
    'address': '10807 Wayne Circle\nCindyberg, MT 62763',
    'text': 'Impact more under. Technology cell ability hope. Sport letter attention team ground debate public. Remember main consider lay popular of if.',
    'email': 'fjones@example.net',
    'phone_number': '(228)691-5164',
    'json': {
    'name': 'Michelle Moore',
    'address': '4081 Rebecca Views Apt. 068\nNorth Brendaland, KY 48775',
},
    'key25687': 'value79825',
    'key38230': 'value80191',
    'key2313': 'value29520',
    'key57297': 'value68662',
},
    {
    'id': 17527489865099,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Michael Norris',
    'address': 'PSC 6043, Box 5241\nAPO AE 97136',
    'text': 'Impact generation player west police. Decide nearly detail million movie. Really daughter our through look discover.',
    'email': 'julieford@example.com',
    'phone_number': '490-250-8307x387',
    'json': {
    'name': 'Michelle Wilson',
    'address': '13600 Martinez Court\nLake Russellville, AZ 61263',
},
    'key47815': 'value87696',
    'key8076': 'value1832',
    'key55805': 'value10721',
    'key90546': 'value28565',
    'key37460': 'value50569',
    'key57314': 'value4606',
    'key16002': 'value61275',
    'key36919': 'value96383',
},
    {
    'id': 17527489865110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Wendy Ray',
    'address': '207 Spencer Glens\nIsaiahmouth, ME 40528',
    'text': 'History author win future available. Kind write just.\nDiscover store action fire hotel space. Speech simple discussion natural. Friend face minute.',
    'email': 'guzmanjennifer@example.org',
    'phone_number': '213.678.5921',
    'json': {
    'name': 'Benjamin Higgins',
    'address': '371 Shannon Club\nNew Laurastad, TN 76557',
},
    'key33679': 'value65710',
    'key29693': 'value81516',
    'key93320': 'value4561',
    'key52382': 'value56602',
    'key15397': 'value17864',
    'key68390': 'value14289',
    'key22982': 'value19500',
    'key32714': 'value12525',
    'key75054': 'value3404',
    'key78138': 'value31146',
},
    {
    'id': 17527489865124,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Anna Carr',
    'address': '10565 Miller Motorway\nMelissachester, CA 16105',
    'text': 'Join near water floor system. Certain management have catch institution finally. Create wrong discover son various.',
    'email': 'kristinafranklin@example.com',
    'phone_number': '200-599-6707x9624',
    'json': {
    'name': 'Vanessa Goodman',
    'address': '616 Elizabeth Pike Suite 048\nGonzalezfurt, HI 97606',
},
    'key45989': 'value84497',
    'key77811': 'value93561',
    'key62994': 'value95441',
    'key72124': 'value63814',
    'key30489': 'value40903',
    'key44088': 'value83452',
    'key10980': 'value81913',
},
    {
    'id': 17527489865139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Kaitlyn Wilson',
    'address': '37613 Martinez Trafficway\nSouth Teresa, GU 77246',
    'text': 'Assume own term partner.\nFederal value create leg woman. Us finish effect season floor. Vote leader now offer. Production camera way successful somebody.',
    'email': 'bjuarez@example.net',
    'phone_number': '001-245-795-4995x08249',
    'json': {
    'name': 'William Lee',
    'address': '34300 Anderson Lakes Apt. 875\nWest Laura, TN 56910',
},
    'key94341': 'value74486',
    'key73076': 'value64675',
    'key95598': 'value68014',
    'key99805': 'value21345',
    'key71905': 'value34120',
    'key55524': 'value18608',
},
    {
    'id': 17527489865153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Laura Jackson',
    'address': '536 Kelly Hills\nEast Brandonborough, NY 92332',
    'text': 'Rock suggest everything almost west. Structure agree ago key American. Say goal fine record eat when course candidate. West picture car performance me.',
    'email': 'trevor77@example.net',
    'phone_number': '888-740-9725',
    'json': {
    'name': 'Albert Newton',
    'address': '586 Monique Trail\nVeronicafort, AK 04744',
},
    'key76782': 'value22594',
    'key40185': 'value35199',
    'key35240': 'value72531',
    'key5525': 'value74180',
    'key5317': 'value49095',
    'key85158': 'value753',
    'key31408': 'value11426',
    'key41151': 'value71839',
    'key3521': 'value51474',
    'key20531': 'value62136',
},
    {
    'id': 17527489865166,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Courtney Johnson',
    'address': '59302 Samuel Burgs\nPaulafort, UT 61262',
    'text': 'Color morning issue film. Democrat identify wife pull argue. Big around teach anything fish more.',
    'email': 'suzanne32@example.net',
    'phone_number': '+1-574-707-7336x22865',
    'json': {
    'name': 'Donald Lewis',
    'address': '5677 Julia Track Suite 431\nLake Jeanette, SC 01701',
},
    'key37410': 'value51858',
    'key88395': 'value81372',
    'key88745': 'value84056',
},
    {
    'id': 17527489865179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Stephen Flores',
    'address': '021 Emily Ferry Apt. 003\nCraigmouth, ME 45328',
    'text': 'Test detail air husband traditional picture. Although positive himself war begin because else. Just specific particularly ok.\nRequire leader out. Tv Democrat product. Someone child war.',
    'email': 'michellekennedy@example.net',
    'phone_number': '609-401-7364x193',
    'json': {
    'name': 'Gabrielle Walker',
    'address': '17623 Gail Mountains\nPort Robert, PR 47031',
},
    'key4334': 'value95904',
    'key21057': 'value18663',
    'key16018': 'value20291',
    'key32531': 'value27421',
    'key16322': 'value19697',
    'key36379': 'value82609',
    'key88910': 'value4710',
    'key68553': 'value38977',
},
    {
    'id': 17527489865193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Brandi Hanson',
    'address': '3011 Young Mount\nGibbsmouth, DC 13711',
    'text': 'Finally prevent whether evening nature attack five.\nWhite style happy research just executive. Huge forward look among. Apply could civil message only treatment floor.',
    'email': 'tkelly@example.com',
    'phone_number': '4712442328',
    'json': {
    'name': 'Erica Kramer',
    'address': '45623 Mark Rest\nNew Joshua, LA 18307',
},
    'key10962': 'value59593',
},
    {
    'id': 17527489865207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Shane Walsh',
    'address': '9365 Holder Village\nSouth Jillport, NM 17226',
    'text': 'During process administration field record live baby. Sea within attention student according someone letter be. Find better if imagine management southern girl country.',
    'email': 'dana21@example.com',
    'phone_number': '5356079523',
    'json': {
    'name': 'Amber Griffin',
    'address': '1767 Johnny Cove Suite 119\nPort Bill, MI 75123',
},
    'key95975': 'value90853',
    'key22085': 'value6487',
    'key2515': 'value44121',
    'key67695': 'value33577',
},
    {
    'id': 17527489865220,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'April Marquez',
    'address': '56989 Rubio Greens\nWest Jacquelinestad, AK 13315',
    'text': 'Within couple theory increase growth stuff carry. Record expert sound visit. South statement fear special memory book.',
    'email': 'cabreradustin@example.org',
    'phone_number': '466.388.3689',
    'json': {
    'name': 'Alexandria Yoder',
    'address': '5288 Miller Turnpike Suite 913\nCastroberg, RI 64331',
},
    'key25026': 'value46734',
    'key40041': 'value28247',
    'key37095': 'value45477',
    'key51334': 'value56260',
    'key81954': 'value80156',
    'key22485': 'value76862',
    'key7292': 'value49103',
},
    {
    'id': 17527489865232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Mrs. Sarah Davila',
    'address': '3626 Katie Islands Apt. 451\nChristopherchester, UT 71256',
    'text': 'Draw produce language majority investment. House check six ever. Do offer great. Sign technology reflect approach within however with.\nGreen thought east lead. Movie often bad seem.',
    'email': 'gregory87@example.org',
    'phone_number': '(719)846-1371',
    'json': {
    'name': 'Shannon Wilson',
    'address': 'USS Jacobs\nFPO AP 22434',
},
    'key34872': 'value35122',
    'key10939': 'value89126',
    'key82748': 'value48935',
    'key56690': 'value67784',
    'key44434': 'value23985',
    'key29571': 'value17499',
    'key28917': 'value18601',
    'key3914': 'value85611',
    'key10583': 'value53125',
    'key88784': 'value75780',
},
    {
    'id': 17527489865242,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Jennifer Sanford',
    'address': '9104 Grace Flats\nNew Samuelbury, UT 84861',
    'text': 'Hard hard activity write hit five. Three appear likely responsibility degree evening.\nHim difference great eye today and.',
    'email': 'michaelharris@example.org',
    'phone_number': '619.738.4823',
    'json': {
    'name': 'James Nelson',
    'address': '1107 Taylor Motorway\nSouth Gloria, OK 36881',
},
    'key40197': 'value20384',
    'key44217': 'value96029',
    'key77393': 'value3100',
    'key88935': 'value86321',
    'key8289': 'value28965',
},
    {
    'id': 17527489865253,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Alexandria Henry',
    'address': '52619 Williams Burg Suite 745\nBrowningshire, PW 18607',
    'text': 'Feeling reality court. Movement theory class possible meeting drop. Debate significant learn amount something Mrs clearly.\nTask plan expect.',
    'email': 'vodonnell@example.com',
    'phone_number': '737-296-6945',
    'json': {
    'name': 'Kimberly Rice',
    'address': '4049 Thompson Lake\nSharonborough, NY 18316',
},
    'key85268': 'value93185',
    'key51534': 'value21184',
    'key90747': 'value27565',
    'key45111': 'value57209',
    'key86956': 'value46005',
    'key2252': 'value3611',
},
    {
    'id': 17527489865263,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Mario Lowe',
    'address': '2863 Antonio Orchard Suite 457\nNorth Edwardbury, IN 06435',
    'text': 'Customer various song table always animal. Lot book project. Series forget threat determine raise report.',
    'email': 'normanchristian@example.com',
    'phone_number': '282-593-4165',
    'json': {
    'name': 'Brian Ramos',
    'address': '8937 Robert Gardens Apt. 081\nNorth Amandashire, DC 58325',
},
    'key45344': 'value18780',
    'key39812': 'value69144',
    'key52210': 'value460',
    'key95005': 'value35520',
    'key42191': 'value25827',
},
    {
    'id': 17527489865275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Sara Mccann',
    'address': '9813 Benjamin Shore\nKelseytown, MO 28593',
    'text': 'Listen relate reach should consumer determine his. Teach themselves collection move threat scene smile.\nLess need though development start defense. Bring often office audience prepare well Democrat.',
    'email': 'tward@example.com',
    'phone_number': '279.777.9966x93043',
    'json': {
    'name': 'Donna Scott',
    'address': '64821 Jason Valley\nMelissaberg, OR 54580',
},
    'key48355': 'value45227',
    'key84407': 'value4368',
    'key139': 'value76726',
    'key39379': 'value57835',
},
    {
    'id': 17527489865285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Dan Cross',
    'address': '14356 Sanchez Well Apt. 454\nEast Ashleyborough, NE 30221',
    'text': 'Put white despite. Power family follow Democrat significant operation painting.\nHope him risk analysis. Under big her certain music. Program well not claim suggest anything.',
    'email': 'waltondaniel@example.com',
    'phone_number': '404-862-3427x603',
    'json': {
    'name': 'Cody Hernandez',
    'address': '189 Pamela Mill\nBrockland, FL 72814',
},
    'key14768': 'value65259',
    'key80678': 'value40657',
    'key16905': 'value42614',
    'key64544': 'value24193',
    'key46100': 'value37268',
    'key35921': 'value52203',
    'key41311': 'value42068',
},
    {
    'id': 17527489865297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Ruben Butler',
    'address': '57964 Stephanie Parks Apt. 845\nJerryland, MP 97805',
    'text': 'Somebody mean beyond half enough strong. Keep certain organization month pretty spring radio.',
    'email': 'benjamin59@example.org',
    'phone_number': '(451)361-3266x12727',
    'json': {
    'name': 'Rachel Robinson',
    'address': '01379 Marissa Center Apt. 540\nGallegosburgh, TN 07792',
},
    'key36219': 'value24839',
    'key65805': 'value49245',
},
    {
    'id': 17527489865307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Fred Harris',
    'address': 'USS Perry\nFPO AA 12415',
    'text': 'Forward development whom popular plant maintain.\nLay quality run fire.',
    'email': 'kpeters@example.net',
    'phone_number': '+1-673-834-9435',
    'json': {
    'name': 'Erik Trujillo',
    'address': '006 Andrew Camp Apt. 733\nJasonberg, NM 25855',
},
    'key12868': 'value70024',
    'key76928': 'value99882',
    'key37690': 'value2087',
    'key35366': 'value22720',
    'key22189': 'value15528',
    'key17864': 'value96912',
    'key2354': 'value10129',
    'key28910': 'value64559',
},
    {
    'id': 17527489865317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Nathan Ryan',
    'address': '81018 Henson Crossroad Suite 131\nNorth Aaronmouth, NH 41294',
    'text': 'Prevent team audience. Lot first some available similar. Themselves just least son game pick draw. Look sound husband dream window even wonder.',
    'email': 'daniel07@example.net',
    'phone_number': '839.503.5207x89274',
    'json': {
    'name': 'Cynthia Estes DVM',
    'address': 'PSC 1019, Box 6962\nAPO AP 37627',
},
    'key54093': 'value54180',
    'key99108': 'value48583',
    'key63588': 'value61055',
},
    {
    'id': 17527489865326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Steven Warner',
    'address': 'USNS Guzman\nFPO AE 59871',
    'text': 'Teacher consider mission marriage. Many step issue receive before practice keep break. Town marriage usually stop friend standard her.\nTen not sister yard economy despite only.',
    'email': 'tasha07@example.net',
    'phone_number': '+1-561-556-8572x980',
    'json': {
    'name': 'Gregory Navarro',
    'address': '0511 Alexander Rue\nLake Aprilport, AK 89932',
},
    'key51392': 'value13876',
    'key87272': 'value58395',
    'key87907': 'value23816',
    'key82215': 'value56694',
    'key69626': 'value44601',
    'key7153': 'value51774',
    'key81409': 'value96861',
    'key54164': 'value52893',
},
    {
    'id': 17527489865335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Sonya Howell',
    'address': '3648 Kerr Spur\nJamesfurt, CO 23087',
    'text': 'Central chance total speak try defense anyone. Explain federal leader expert treatment throughout degree. Room decade we sell trip order different.',
    'email': 'michael58@example.net',
    'phone_number': '530.894.9714',
    'json': {
    'name': 'John Sanders',
    'address': 'Unit 4066 Box 4501\nDPO AP 66233',
},
    'key79953': 'value18798',
    'key89674': 'value53215',
    'key25550': 'value36007',
    'key6102': 'value20077',
    'key14914': 'value5484',
    'key20834': 'value16295',
    'key85412': 'value42300',
},
    {
    'id': 17527489865344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Ashley Taylor',
    'address': '735 Thompson Glens Apt. 098\nNorth John, KY 26860',
    'text': 'Leg wrong still old study. Appear character task top prove middle start.',
    'email': 'rodriguezmichael@example.net',
    'phone_number': '462-285-8825x8642',
    'json': {
    'name': 'Andrew Nguyen',
    'address': '659 Morton Ports\nPort Peterberg, SD 63444',
},
    'key13663': 'value62955',
    'key91398': 'value70824',
    'key21814': 'value46834',
    'key25077': 'value94184',
    'key71755': 'value44772',
},
    {
    'id': 17527489865355,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Larry Park',
    'address': '4663 Christopher Parkway\nSouth Dannyland, KY 80224',
    'text': 'Open benefit glass start consider energy. I true professional.\nFriend firm maintain top big professor. Nice item after public.',
    'email': 'pamelapowell@example.com',
    'phone_number': '+1-557-855-4984x21388',
    'json': {
    'name': 'Matthew Fitzgerald',
    'address': '0502 David Falls Apt. 524\nLake Joshua, IL 55024',
},
    'key17797': 'value59931',
    'key91': 'value57762',
    'key68040': 'value45152',
    'key3747': 'value2959',
    'key64678': 'value86255',
},
    {
    'id': 17527489865367,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Joseph Singh',
    'address': '283 Melvin Fork\nJonesview, MN 30044',
    'text': 'Though cup she anyone research. Over from organization really food instead kid.\nDream young clearly hair. Customer early these wide.',
    'email': 'iparrish@example.net',
    'phone_number': '632.903.8070',
    'json': {
    'name': 'Erin Keller',
    'address': 'USNS Pierce\nFPO AP 49708',
},
    'key1289': 'value87657',
    'key50988': 'value26095',
    'key85334': 'value35502',
    'key90713': 'value82327',
    'key72276': 'value58737',
    'key27149': 'value88994',
    'key45605': 'value62870',
    'key46284': 'value52301',
},
    {
    'id': 17527489865376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Nancy Fields',
    'address': '181 Brian Roads Suite 390\nWest Karenport, NJ 49600',
    'text': 'Must million data. Yard them high miss she its. Else cultural best hope.\nNetwork coach view drug. Lawyer section nature investment range protect.\nParent clearly production despite perhaps two.',
    'email': 'jonathanlong@example.net',
    'phone_number': '001-897-477-6881x2489',
    'json': {
    'name': 'Ronald Jones',
    'address': 'Unit 6546 Box 6697\nDPO AE 37793',
},
    'key86613': 'value82919',
    'key12347': 'value81996',
    'key17372': 'value25683',
    'key99499': 'value36358',
    'key90897': 'value25239',
    'key64025': 'value36410',
    'key7637': 'value46616',
    'key42221': 'value37566',
    'key64894': 'value4627',
},
    {
    'id': 17527489865386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Kristen Soto',
    'address': '1768 Jasmine Station Suite 816\nBriggsside, VI 30334',
    'text': 'Along and east end cover generation. Report pattern such myself table.\nInvestment success protect organization safe. Ability rock my soon.',
    'email': 'michelle91@example.net',
    'phone_number': '741-885-7525',
    'json': {
    'name': 'Cynthia Hernandez',
    'address': 'Unit 5254 Box 9198\nDPO AA 89921',
},
    'key33089': 'value24666',
    'key54009': 'value29433',
    'key40979': 'value52162',
    'key43101': 'value91833',
    'key20461': 'value98831',
    'key80811': 'value96274',
},
    {
    'id': 17527489865395,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Amanda Parrish',
    'address': 'Unit 0248 Box 8911\nDPO AP 59917',
    'text': 'Cultural necessary environment of attorney price after. Sometimes cause several less clearly difference skill. Suffer cold similar worker realize.',
    'email': 'rachellloyd@example.net',
    'phone_number': '001-226-924-5767x52362',
    'json': {
    'name': 'Kelly Morse',
    'address': '369 Berg Ford\nPort Maryfort, MD 42805',
},
    'key99018': 'value28608',
},
    {
    'id': 17527489865404,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Lindsay Davidson',
    'address': '7644 Javier Turnpike\nPort Angelaburgh, ME 06429',
    'text': 'Buy democratic consider focus recent security purpose. Get decide movie decision ten never.',
    'email': 'ryan27@example.com',
    'phone_number': '001-634-303-3241',
    'json': {
    'name': 'Holly Osborne',
    'address': '8528 Franklin Manors Apt. 536\nDonaldland, TX 05058',
},
    'key73987': 'value85914',
    'key43113': 'value35115',
    'key62861': 'value18636',
    'key99923': 'value55351',
    'key91815': 'value51955',
    'key44494': 'value34814',
    'key10396': 'value78336',
},
    {
    'id': 17527489865414,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Christopher Ross',
    'address': '74654 John Via\nMcfarlandburgh, IA 60768',
    'text': 'Institution require no choice fast understand important. Popular compare spend speech prevent hold top.\nAttorney send night each lose. Even none skill.\nMusic high street explain building social case.',
    'email': 'eyoung@example.net',
    'phone_number': '301-252-0003x27035',
    'json': {
    'name': 'Patrick Morton',
    'address': '924 Davies Underpass\nEast Theresaview, VT 83882',
},
    'key98664': 'value77457',
    'key41019': 'value16080',
    'key53573': 'value49029',
    'key64378': 'value77597',
    'key71095': 'value3671',
},
    {
    'id': 17527489865425,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Erin Dillon',
    'address': '3252 Murphy Wells Suite 253\nDarylport, GA 52260',
    'text': 'Force record member age evening. Relationship name although.\nWonder start military since begin line thing if. Policy receive knowledge traditional peace.',
    'email': 'joseruiz@example.com',
    'phone_number': '(689)642-7901x89302',
    'json': {
    'name': 'David Morgan',
    'address': '833 Mcbride Forks Apt. 703\nNorth Brittneyfort, PR 92191',
},
    'key34586': 'value42214',
    'key62792': 'value37905',
    'key23259': 'value64525',
    'key98053': 'value25572',
    'key88856': 'value68251',
},
    {
    'id': 17527489865437,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Joshua Newman',
    'address': '043 Sanders Spurs\nEast Robinfort, OK 53642',
    'text': 'Soldier agree role course. Debate itself ability cause continue receive bit.\nDeal discussion their Mr. Tv agency find plant.\nTrouble box nearly reduce need common. Would various full.',
    'email': 'sharonparker@example.org',
    'phone_number': '(266)321-8938x242',
    'json': {
    'name': 'Tonya Griffin',
    'address': '788 Webster Valley\nPort Hayley, ME 52586',
},
    'key88959': 'value57670',
    'key82014': 'value52803',
    'key32964': 'value62681',
    'key13074': 'value9888',
    'key56369': 'value15404',
    'key81124': 'value97261',
    'key77042': 'value69',
    'key44364': 'value5498',
    'key77212': 'value61996',
},
    {
    'id': 17527489865449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Bonnie Sloan',
    'address': '8624 Torres Roads\nPort Robertton, WV 16460',
    'text': 'Trouble improve seven describe husband. Color kind throughout bill wind.\nSmall start anyone. Commercial professor president organization.',
    'email': 'davidwarren@example.net',
    'phone_number': '+1-828-729-1886x85374',
    'json': {
    'name': 'Jeffery Saunders',
    'address': '230 Escobar Extensions Apt. 845\nBrendafurt, NV 41665',
},
    'key25974': 'value40428',
    'key61060': 'value69626',
    'key82582': 'value37691',
    'key21838': 'value5778',
    'key34767': 'value58055',
},
    {
    'id': 17527489865460,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Michael Terrell',
    'address': '30174 Krause Crescent Suite 548\nWest Christymouth, NV 50927',
    'text': 'Statement system compare lead bill form. Generation story system point see hear clear.\nLeft fund summer. Building service relate development. Music drop condition later produce.',
    'email': 'bettyreynolds@example.com',
    'phone_number': '+1-467-870-3781',
    'json': {
    'name': 'Erin Lee',
    'address': '7276 Allen Summit\nNorth Kevinport, MS 81934',
},
    'key21193': 'value80164',
    'key29645': 'value85533',
    'key6674': 'value75816',
},
    {
    'id': 17527489865478,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Warren Sawyer',
    'address': 'USNV Rowe\nFPO AA 17874',
    'text': 'Receive push reveal activity may may. Sure reality special.\nType order western personal value artist issue rock. Six begin cover the nor decision thought.',
    'email': 'acook@example.net',
    'phone_number': '646-684-8102x12487',
    'json': {
    'name': 'Diana Hodge',
    'address': 'USCGC Graham\nFPO AE 11375',
},
    'key99446': 'value8416',
    'key30038': 'value66189',
    'key40664': 'value76858',
    'key16467': 'value10888',
    'key14550': 'value48753',
    'key75816': 'value53626',
    'key1240': 'value58810',
    'key54978': 'value93642',
},
    {
    'id': 17527489865487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Carla Doyle',
    'address': '180 Justin Extension Apt. 490\nNorth Linda, SD 81801',
    'text': 'Special describe discuss authority agreement job discover. House next community should both. Be long word hospital paper.',
    'email': 'kellyford@example.org',
    'phone_number': '+1-373-895-3415',
    'json': {
    'name': 'Wayne Sheppard',
    'address': '0875 Christine Harbor\nNew Anthonyland, MO 72947',
},
    'key12219': 'value27795',
    'key62783': 'value89312',
    'key35039': 'value29096',
    'key4995': 'value714',
    'key1178': 'value35533',
    'key74096': 'value88995',
    'key27959': 'value42077',
    'key50464': 'value30285',
    'key59284': 'value16917',
    'key16808': 'value83528',
},
    {
    'id': 17527489865498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Courtney Dickson MD',
    'address': '9862 Parks Streets\nNew Patricia, WY 30558',
    'text': 'Difficult natural senior. Now program investment thus manage better.\nLast fight senior catch measure anyone. Although interesting appear against new others.\nWish interview fill other.',
    'email': 'fredkelly@example.org',
    'phone_number': '690.904.7945x070',
    'json': {
    'name': 'Vanessa Johnston',
    'address': 'Unit 8937 Box 5323\nDPO AE 56995',
},
    'key6524': 'value27284',
    'key42099': 'value25214',
    'key89654': 'value53714',
    'key42371': 'value95905',
    'key41558': 'value82877',
    'key50326': 'value6214',
    'key60399': 'value21037',
    'key8711': 'value63437',
},
    {
    'id': 17527489865507,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Sharon Anderson',
    'address': '45131 Jeffrey Fort Suite 059\nLake Michaelshire, SC 17120',
    'text': 'Small final away. Enjoy teach explain building.\nStatement travel outside those marriage enjoy describe company. Care by animal out. Away in cultural charge center environmental difficult however.',
    'email': 'nathanrobinson@example.net',
    'phone_number': '7989498186',
    'json': {
    'name': 'Sandra Scott',
    'address': '420 Elizabeth Turnpike\nMortonside, MT 83164',
},
    'key82735': 'value5675',
    'key20101': 'value7607',
    'key42388': 'value78465',
    'key52151': 'value17195',
    'key72317': 'value28677',
    'key46769': 'value18396',
    'key13059': 'value86858',
},
    {
    'id': 17527489865518,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Arthur James',
    'address': '6467 Kimberly Field\nPort Logan, AZ 16524',
    'text': 'Cost policy boy challenge officer. Near factor foreign yard whose. Garden child level say from within concern young.',
    'email': 'kperez@example.org',
    'phone_number': '+1-754-409-9841x58758',
    'json': {
    'name': 'Kirsten Wilson',
    'address': '8501 Christian Valleys\nWest Wandashire, NY 41000',
},
    'key91242': 'value44389',
    'key73741': 'value49510',
    'key38373': 'value44928',
},
    {
    'id': 17527489865529,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Monica Cobb',
    'address': '21997 Vanessa Parkway\nCharlesfort, NJ 28194',
    'text': 'Discuss one true. End owner entire. Recently bit want major food hospital.\nHuman unit whole will. Hope rate pattern it goal kid country.',
    'email': 'brianspencer@example.net',
    'phone_number': '001-991-459-5431x8247',
    'json': {
    'name': 'David Johns',
    'address': '346 Melissa Branch Suite 430\nNorth Kyle, VT 62048',
},
    'key11589': 'value44563',
    'key82748': 'value31616',
    'key27885': 'value22758',
    'key21330': 'value10953',
    'key92515': 'value79566',
    'key13158': 'value1077',
    'key66574': 'value86022',
    'key69943': 'value98267',
},
    {
    'id': 17527489865540,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Mary Mcbride',
    'address': 'USNV Cunningham\nFPO AA 27420',
    'text': 'Thank apply commercial phone. Nearly business we woman north. Under answer exist enjoy by own.',
    'email': 'brandyperez@example.com',
    'phone_number': '349.548.2434x3777',
    'json': {
    'name': 'Erica Hunter',
    'address': 'PSC 4344, Box 5775\nAPO AA 76836',
},
    'key6021': 'value97288',
    'key46196': 'value21458',
    'key2036': 'value60316',
},
    {
    'id': 17527489865548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Mrs. Morgan Kelly DVM',
    'address': '43520 Ortega Manors Apt. 137\nKarenstad, IN 53652',
    'text': 'Our student young yes. Central report night why top office visit. Sport often security memory key. Sure yet all Republican prepare agree gas.',
    'email': 'jeffhenderson@example.org',
    'phone_number': '001-372-220-2455x37832',
    'json': {
    'name': 'Bianca Lopez',
    'address': '5572 Brady Glens Suite 791\nParkerside, OK 78407',
},
    'key33667': 'value32049',
    'key69079': 'value84688',
    'key10256': 'value5094',
    'key3433': 'value58922',
    'key19076': 'value38569',
    'key29146': 'value88866',
    'key10924': 'value64676',
    'key20870': 'value26547',
},
    {
    'id': 17527489865560,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Kathryn Hurst',
    'address': '514 Collins Gardens\nWest Nicholas, NM 05315',
    'text': 'Series data usually almost only cut nor environment. Floor old suddenly force. Reach group least score.',
    'email': 'eric26@example.org',
    'phone_number': '001-311-902-9603x364',
    'json': {
    'name': 'William Smith',
    'address': '765 Mckenzie Course\nPort Madisonshire, AK 59308',
},
    'key87241': 'value98027',
    'key54708': 'value96377',
    'key49603': 'value39637',
},
    {
    'id': 17527489865570,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Mr. David Bell',
    'address': '66465 Valencia Plaza\nPort Annmouth, MI 34602',
    'text': 'Modern one deep than international result student. Finish letter offer institution feeling ever than. He popular become soldier really. Chair enjoy between able color.',
    'email': 'williamsamanda@example.com',
    'phone_number': '001-767-611-0733x4856',
    'json': {
    'name': 'Jonathan Thomas',
    'address': '20132 Sanders Trafficway\nPhillipburgh, NH 63647',
},
    'key27000': 'value30963',
    'key97956': 'value25040',
    'key51418': 'value28560',
    'key91845': 'value37327',
    'key59649': 'value71369',
    'key84410': 'value19323',
},
    {
    'id': 17527489865582,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Mary Adams',
    'address': '3774 Schultz Villages Suite 546\nGriffinfurt, DE 58829',
    'text': 'Fear story any care. Old professor who report share create kid. Charge tax agreement week.\nScene specific finish after. Institution together third area listen. Sort each military.',
    'email': 'jesus87@example.com',
    'phone_number': '(555)505-2166x4718',
    'json': {
    'name': 'Rhonda Austin',
    'address': '33553 Deanna Cliff Suite 857\nNew Alyssa, OK 39733',
},
    'key14650': 'value85884',
    'key15680': 'value94228',
    'key54113': 'value63818',
    'key20285': 'value6926',
    'key49000': 'value18748',
    'key31788': 'value39130',
},
    {
    'id': 17527489865593,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Benjamin Chavez',
    'address': '8431 Butler Green\nSouth Kristinaville, LA 71131',
    'text': 'Team treatment next authority garden as fire. Training trip it become because about.',
    'email': 'tylermills@example.net',
    'phone_number': '+1-696-279-4786x30604',
    'json': {
    'name': 'Robert Payne',
    'address': '9284 Bradley Turnpike\nWatsonberg, IN 72043',
},
    'key61599': 'value26105',
    'key67229': 'value76777',
    'key4130': 'value56025',
    'key8640': 'value97',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
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
    'filter': 'name like \'Ka%\'',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
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
    'RequestId': 'cf027a64-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_43_00_291950OYTpwyTJ',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_varchar_filter[True-name like "placeholder%"]_1752748989.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithVarcharFilterTrueNameLikePlaceholder1752748989Json()
    test.run_tests()
