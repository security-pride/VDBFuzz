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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestDeleteVector_test_delete_vector_by_filter_pk_field[one]_1752749248_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[one]_1752749248.json"
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



class AllmilvusLogtestdeletevectorTestDeleteVectorByFilterPkFieldOne1752749248Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[one]_1752749248.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[one]_1752749248.json"
        self.test_count = 10  # 测试方法数量
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
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
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
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
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
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
    'data': [
    {
    'id': 17527492317215,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Patricia Crosby',
    'address': '686 Forbes Summit Suite 463\nJefferyfort, MH 13056',
    'text': 'Activity hope player. Exist your material hospital wife page. Tonight land remember prepare today morning gun.\nNewspaper enter sing eye. Technology economy rock clear identify fly for.',
    'email': 'marshalljoseph@example.net',
    'phone_number': '696-671-4552x6268',
    'json': {
    'name': 'Calvin Cook',
    'address': 'USCGC Beck\nFPO AA 40182',
},
    'key56511': 'value39789',
    'key68634': 'value37086',
    'key49929': 'value83944',
    'key15597': 'value90306',
    'key93888': 'value7840',
    'key5865': 'value53027',
    'key43456': 'value17534',
},
    {
    'id': 17527492317232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Bradley Thomas DVM',
    'address': '8931 Tina Cape Suite 216\nPort Ryanstad, OR 15554',
    'text': 'Fund thousand likely bring. Indeed movie new example nearly once health.\nImportant economic beautiful under. Owner say early one. Choose home learn anyone allow hospital.',
    'email': 'jamesbrown@example.com',
    'phone_number': '+1-340-739-9187x484',
    'json': {
    'name': 'Nicole Lambert',
    'address': '512 Johnson Way\nJohnland, IL 83574',
},
    'key72194': 'value88742',
    'key44481': 'value28044',
    'key5967': 'value13546',
    'key83681': 'value53419',
    'key10095': 'value23135',
    'key97861': 'value96125',
    'key92675': 'value3643',
    'key50440': 'value63815',
},
    {
    'id': 17527492317247,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Matthew Wright',
    'address': '1814 Arellano Avenue\nSouth Brittney, IA 72341',
    'text': 'Play budget safe main like. Save also of together us travel. Size other eight.\nThink cup important thousand. Stay just remember to.',
    'email': 'cordovatracy@example.org',
    'phone_number': '(955)384-4614x2452',
    'json': {
    'name': 'Scott Vaughn',
    'address': '646 Tara Ports Apt. 208\nChristinaburgh, DC 87607',
},
    'key13480': 'value97293',
    'key30252': 'value98595',
    'key58890': 'value12087',
    'key77360': 'value97886',
    'key69634': 'value12780',
},
    {
    'id': 17527492317261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Ryan Fuller',
    'address': '34218 Calhoun Divide\nHollyburgh, NC 62501',
    'text': 'Matter it the audience their economy attention. Parent let American area manage arrive.\nPopular write official himself long sense assume. Agent conference car professional foot next.',
    'email': 'craig59@example.com',
    'phone_number': '(477)554-9087x93682',
    'json': {
    'name': 'Ricky Porter',
    'address': '04051 Parker Hills\nWest Crystal, AS 74042',
},
    'key45321': 'value86924',
    'key92753': 'value18418',
    'key2277': 'value27847',
    'key3309': 'value71318',
    'key7911': 'value54926',
    'key81541': 'value91329',
    'key71550': 'value18425',
    'key98294': 'value18073',
    'key15347': 'value72397',
    'key11047': 'value57447',
},
    {
    'id': 17527492317275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Lisa Ochoa',
    'address': '417 Allen Manors\nMelissastad, NM 74364',
    'text': 'Perform field town write yard else center. Impact staff heart bad must help plant.\nRock fact bit firm those dog laugh. Wrong year morning smile our control think. Firm prepare good whole coach.',
    'email': 'kellyjessica@example.org',
    'phone_number': '8262891972',
    'json': {
    'name': 'Ryan Combs',
    'address': '18217 Bryant Ville\nMeganfurt, MS 61024',
},
    'key79047': 'value38155',
    'key84692': 'value45034',
    'key5786': 'value69959',
    'key6098': 'value74130',
    'key69581': 'value5724',
    'key86965': 'value83592',
    'key53625': 'value58515',
    'key46109': 'value56317',
    'key71354': 'value85713',
},
    {
    'id': 17527492317290,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Spencer Wise',
    'address': '947 Howell Points Apt. 774\nAmandahaven, MO 09013',
    'text': 'Various citizen final. Ability north quality build life speech risk. Suddenly tax skill.\nSave least address appear old sure. Democratic like police within.',
    'email': 'lawrencevalerie@example.org',
    'phone_number': '212-312-5120x65116',
    'json': {
    'name': 'Donald Peterson',
    'address': '1577 Choi Canyon\nNew Ashlee, MH 04219',
},
    'key41049': 'value711',
    'key57629': 'value88941',
    'key10718': 'value63978',
    'key70264': 'value10392',
},
    {
    'id': 17527492317304,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Todd Webster',
    'address': '579 Rebecca Gardens Suite 302\nNorth Troy, OK 82834',
    'text': 'Care moment pull. My nation travel name.\nLittle down hour once how tree behavior general. Learn century great call. Look down top though rate others senior unit.',
    'email': 'heather00@example.net',
    'phone_number': '+1-596-847-6775x1043',
    'json': {
    'name': 'Xavier Jones',
    'address': '87937 Bowers Passage Suite 373\nEstesstad, CO 58808',
},
    'key55779': 'value65320',
    'key98006': 'value66918',
    'key96088': 'value97376',
    'key80261': 'value42692',
    'key52089': 'value60704',
    'key69787': 'value18978',
    'key98198': 'value96750',
    'key44109': 'value68643',
},
    {
    'id': 17527492317317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Karen Myers',
    'address': '9269 Gallagher Shoal Apt. 982\nNew John, MA 81951',
    'text': 'Million officer church. Reason throughout six onto sign unit.\nKey around then owner week reduce. Quality center third.\nFather toward sea. Various many option reduce. Range pretty usually let before.',
    'email': 'ricardowatts@example.com',
    'phone_number': '+1-757-746-0250x0865',
    'json': {
    'name': 'Henry Mendoza',
    'address': '54748 King Run Suite 093\nNorth Aliciaburgh, SD 33986',
},
    'key57293': 'value48585',
    'key53047': 'value85579',
    'key24167': 'value34045',
    'key80028': 'value21240',
    'key37369': 'value33665',
    'key30075': 'value10844',
    'key62036': 'value53495',
},
    {
    'id': 17527492317332,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jennifer Johnson',
    'address': '1706 Schwartz Forge\nStephanieton, TX 85225',
    'text': 'Military accept which interview hand song. Arrive respond party create note.\nCheck short song under end.\nMuch color tell everyone. Win week the outside agent study. Product threat manage human.',
    'email': 'aprilmendoza@example.com',
    'phone_number': '001-486-608-6017x5937',
    'json': {
    'name': 'Bryan Wong',
    'address': '1592 John Wells Suite 079\nPort Vickieborough, CO 20971',
},
    'key82696': 'value98573',
    'key41291': 'value28870',
    'key88776': 'value76933',
    'key61546': 'value36015',
    'key91709': 'value12856',
    'key78398': 'value42769',
    'key48119': 'value60518',
    'key65486': 'value81731',
    'key65041': 'value81511',
},
    {
    'id': 17527492317344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Adam Logan',
    'address': '050 Williams Meadows Apt. 496\nLake Justin, NM 64583',
    'text': 'Space as herself body test. Rest picture government again ok. Prevent theory thus think dream different.\nNews weight ahead consider law benefit.',
    'email': 'sydney44@example.com',
    'phone_number': '+1-661-762-0574',
    'json': {
    'name': 'Bradley Jones',
    'address': '7182 Tiffany Parkway Suite 614\nWest Lindsey, TX 98709',
},
    'key30027': 'value98021',
    'key39359': 'value12035',
    'key15176': 'value28287',
    'key65538': 'value31861',
    'key47791': 'value33807',
},
    {
    'id': 17527492317354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Lee Hall',
    'address': '975 Stephens Lake\nMichaelfort, GU 37369',
    'text': 'Machine music Democrat small could no.\nWatch individual three good. Sign same Mrs listen.\nAvailable assume maintain Republican billion professor develop speak. Coach above outside commercial one.',
    'email': 'rmercer@example.com',
    'phone_number': '+1-313-586-2801x2366',
    'json': {
    'name': 'Nicole Howard',
    'address': '9657 Jacob Divide Suite 883\nHendersonmouth, ME 02413',
},
    'key79894': 'value38000',
    'key70055': 'value70546',
    'key69507': 'value99951',
},
    {
    'id': 17527492317365,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Ann Hubbard',
    'address': '602 Lindsey Curve\nJosephland, MT 74296',
    'text': 'Material reason your society edge. Still available day officer skin situation range.\nChair finish away hospital. Trip until capital several clearly step.',
    'email': 'torresscott@example.org',
    'phone_number': '361-801-4267x402',
    'json': {
    'name': 'Maria Gregory',
    'address': '016 Molina Well Suite 559\nAndrewbury, WA 03425',
},
    'key72795': 'value13227',
    'key5058': 'value9793',
    'key73241': 'value64269',
    'key73418': 'value41409',
    'key93635': 'value55460',
},
    {
    'id': 17527492317377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Patricia Gutierrez MD',
    'address': '25932 Laura Glens Apt. 482\nNew Jamesside, MS 87771',
    'text': 'Training glass year church whose body.\nWrite now wait shake able. See lead serve. Establish none central month no.',
    'email': 'richardsonamy@example.org',
    'phone_number': '+1-672-262-7464x704',
    'json': {
    'name': 'Cynthia Grimes',
    'address': '37984 Natasha Drive Apt. 737\nJosephhaven, DC 20620',
},
    'key14531': 'value2730',
    'key49314': 'value84336',
    'key21133': 'value17778',
    'key89106': 'value37429',
    'key22798': 'value8592',
    'key17349': 'value28306',
    'key61305': 'value89917',
    'key69274': 'value34470',
    'key65169': 'value22442',
},
    {
    'id': 17527492317389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Deborah White',
    'address': '411 Garcia Forest\nNorth Jonathanside, FM 46040',
    'text': 'Theory later beautiful. East apply figure position. Loss source which fact everyone. Big break growth network.\nGame ability see American. Thing air look you also center network.',
    'email': 'harrisdustin@example.org',
    'phone_number': '6096563108',
    'json': {
    'name': 'Andrew Dixon',
    'address': '729 Johnson Junctions\nPort Daniel, CO 28407',
},
    'key43957': 'value3448',
    'key6644': 'value99256',
    'key2947': 'value55885',
    'key61639': 'value17958',
    'key25071': 'value36873',
    'key89429': 'value30451',
    'key62272': 'value16204',
},
    {
    'id': 17527492317401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Ann Gill',
    'address': '69059 Kimberly Lakes Suite 908\nJessicaside, PA 18182',
    'text': 'Value training fill attack recent main.\nNone thing election group police detail. Generation field local everything international director into. So subject many. Like hundred Democrat.',
    'email': 'asullivan@example.org',
    'phone_number': '607.523.3369x61424',
    'json': {
    'name': 'Aaron Davidson',
    'address': '30973 Rodriguez Crossroad Suite 432\nLake Anthony, DE 60913',
},
    'key95603': 'value58224',
    'key96692': 'value27425',
    'key70922': 'value57795',
    'key97466': 'value33804',
},
    {
    'id': 17527492317412,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Heather Lucas',
    'address': '3643 Mary Mount Apt. 840\nRobertshire, UT 62505',
    'text': 'Road book which prevent wife his gun boy. Strong detail daughter happy politics design. Picture hold local series direction.',
    'email': 'regina83@example.org',
    'phone_number': '+1-396-262-5563x082',
    'json': {
    'name': 'Dr. Adrienne Thompson DVM',
    'address': '79791 Stephanie Forest\nDuncanberg, NE 81640',
},
    'key81420': 'value71242',
    'key69449': 'value40957',
},
    {
    'id': 17527492317422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kelsey Williams',
    'address': '952 Thomas Crescent\nEast Davidmouth, PA 67655',
    'text': 'Ground between nearly debate. Eye bit home prove catch significant cause.\nGuy much writer great. Would per table thousand. Hit glass pass challenge avoid available.',
    'email': 'teresafowler@example.org',
    'phone_number': '001-966-212-7532x03413',
    'json': {
    'name': 'Kelly Williams',
    'address': '187 Roberts Via\nNatalieshire, FL 50661',
},
    'key58824': 'value58738',
    'key98433': 'value17273',
    'key17109': 'value72518',
    'key73771': 'value41642',
    'key83538': 'value27918',
    'key60321': 'value84',
    'key93729': 'value64358',
},
    {
    'id': 17527492317434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Katrina Jones',
    'address': '7656 Robinson Trafficway Suite 090\nJosephview, AR 61588',
    'text': 'Wait road total resource local. North book real. Interest professional or hit.\nInterest focus candidate reflect camera hundred hour everyone.',
    'email': 'anna81@example.org',
    'phone_number': '+1-903-417-5457x218',
    'json': {
    'name': 'Anita Powell',
    'address': '04889 Joshua Vista Suite 019\nJohnsonmouth, TN 41687',
},
    'key32010': 'value8859',
    'key37962': 'value53315',
    'key36968': 'value95028',
    'key92144': 'value82497',
    'key90564': 'value67844',
    'key42927': 'value40996',
    'key35505': 'value3733',
},
    {
    'id': 17527492317445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Marie Gillespie',
    'address': '26897 Kennedy Mountain Apt. 991\nPort Mitchellfort, AL 12589',
    'text': 'Evidence between special office theory. Station follow this some return wear whatever Mr.\nNow car least. Pass six stock company. Network Democrat toward almost.\nSoon whose current article.',
    'email': 'norma21@example.org',
    'phone_number': '+1-864-581-6270',
    'json': {
    'name': 'John Green',
    'address': 'PSC 7423, Box 9094\nAPO AA 42358',
},
    'key10256': 'value51524',
    'key3269': 'value96577',
    'key47494': 'value20943',
    'key70585': 'value60262',
    'key82765': 'value60388',
    'key8586': 'value95326',
    'key93809': 'value66619',
},
    {
    'id': 17527492317454,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Christopher Cole',
    'address': '730 Ray Summit Suite 329\nNew Mariashire, NY 19693',
    'text': 'Test office follow cause network. Democrat thought better such happy teach not wonder. Amount pay site particularly major leave. Region style property almost under.',
    'email': 'amandagonzalez@example.net',
    'phone_number': '878-516-5733x66769',
    'json': {
    'name': 'Kelsey Velazquez',
    'address': '18498 Nicole Ramp Suite 155\nSouth Margaret, MA 52969',
},
    'key34372': 'value78616',
},
    {
    'id': 17527492317465,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Cody Jordan',
    'address': '904 Coleman Village Suite 045\nWest Davidton, IL 09920',
    'text': 'Become that and level other floor player. Energy result book space. General pattern anyone professional ever sport drive.',
    'email': 'erinking@example.org',
    'phone_number': '213-332-6512x129',
    'json': {
    'name': 'Charles Campbell',
    'address': '615 Carr Wells Apt. 322\nSouth Jodi, MH 32901',
},
    'key60361': 'value96526',
    'key35280': 'value49702',
    'key8623': 'value45973',
    'key9132': 'value27083',
    'key76420': 'value16764',
    'key25471': 'value75394',
    'key91125': 'value77630',
    'key49135': 'value89244',
    'key49559': 'value34808',
},
    {
    'id': 17527492317477,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Veronica Alvarez',
    'address': '81837 Escobar Estate Apt. 941\nEast Brandon, OR 86533',
    'text': 'Soon establish including executive smile each. Opportunity just response job leader stock beautiful learn. Idea station herself important wait.',
    'email': 'bho@example.org',
    'phone_number': '956-789-3640',
    'json': {
    'name': 'Susan Stevenson',
    'address': '6698 Shane Ferry\nWest Miranda, GA 04277',
},
    'key91207': 'value76122',
    'key62491': 'value27971',
    'key93980': 'value24416',
    'key94009': 'value92347',
    'key35390': 'value6979',
    'key41626': 'value69107',
    'key67950': 'value5772',
    'key41355': 'value50991',
    'key40770': 'value18656',
    'key99403': 'value32784',
},
    {
    'id': 17527492317487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Lauren Perry',
    'address': '708 Joseph Junctions\nHensonport, ND 08077',
    'text': 'Listen four want federal move ago until light. Onto expert administration charge little these. Take decade quite future southern dog peace.',
    'email': 'kathleenstafford@example.org',
    'phone_number': '498-945-9669',
    'json': {
    'name': 'Kathleen Jones',
    'address': '6316 Trujillo Highway\nSouth Ryan, MA 40782',
},
    'key13015': 'value94678',
    'key9123': 'value98835',
    'key11': 'value3148',
    'key69268': 'value14270',
    'key60017': 'value90776',
    'key11799': 'value30590',
    'key41033': 'value7512',
},
    {
    'id': 17527492317499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Nathan Elliott',
    'address': '828 Joseph Mews Suite 520\nNew Kathrynborough, WV 89367',
    'text': 'Dark against people cell subject trouble political. System former material crime marriage image standard.\nLocal seven prove least entire.',
    'email': 'alexander85@example.com',
    'phone_number': '+1-395-845-7016',
    'json': {
    'name': 'Kayla Murphy',
    'address': '369 Bird Hills Apt. 270\nWalkermouth, MH 60815',
},
    'key58951': 'value97063',
    'key68909': 'value77309',
    'key33442': 'value92231',
},
    {
    'id': 17527492317509,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Melissa Ramos',
    'address': '71821 Paige Parkway Suite 155\nSusanchester, KY 05609',
    'text': 'Get democratic couple cost research other. Specific air positive series cell.\nEach girl rather grow story truth. School suddenly me happen sport rather song.',
    'email': 'thomas74@example.org',
    'phone_number': '370-214-1998x255',
    'json': {
    'name': 'Debra Rodriguez',
    'address': '96893 Anderson Squares\nJodishire, AK 04103',
},
    'key21600': 'value7848',
    'key70082': 'value1764',
    'key7247': 'value22554',
    'key33906': 'value71307',
    'key14356': 'value3896',
    'key84660': 'value8322',
    'key65103': 'value9582',
},
    {
    'id': 17527492317520,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Madison Collins',
    'address': '545 Travis Extension Suite 081\nArmstrongville, NM 03505',
    'text': 'Organization into measure home. Know you than commercial spring newspaper prepare enjoy. Enjoy up address suffer. Month civil data someone occur.',
    'email': 'lfuentes@example.com',
    'phone_number': '205-776-0045',
    'json': {
    'name': 'Logan Orozco',
    'address': '0592 Smith Burg Apt. 374\nWest Vickieside, LA 90608',
},
    'key88758': 'value55698',
    'key41121': 'value74757',
    'key94171': 'value17195',
    'key96042': 'value49502',
    'key38190': 'value11629',
    'key66126': 'value37697',
    'key20975': 'value35569',
    'key14226': 'value45935',
},
    {
    'id': 17527492317531,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Crystal Hill',
    'address': '0182 David Corners Apt. 103\nLake Morgan, AK 73654',
    'text': 'Watch picture institution. Instead parent force require mention. Believe expert house condition design able black east.',
    'email': 'nmelton@example.com',
    'phone_number': '(837)587-8546',
    'json': {
    'name': 'Corey Melton',
    'address': '846 Brown Pike Apt. 372\nPort Nicoleberg, MO 98637',
},
    'key83733': 'value82603',
    'key5410': 'value7024',
    'key13715': 'value5464',
    'key75631': 'value88925',
    'key70480': 'value65830',
    'key68750': 'value54967',
    'key54137': 'value67071',
    'key24712': 'value70760',
    'key10051': 'value98324',
},
    {
    'id': 17527492317541,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Phillip Clark',
    'address': '758 Terry Lane Suite 909\nPort Juanstad, MN 78656',
    'text': 'He figure start quite check front during. Defense sometimes away decide behavior job. Leader by give entire occur degree.',
    'email': 'michele58@example.com',
    'phone_number': '001-529-726-9926x3662',
    'json': {
    'name': 'Roberta Sanchez',
    'address': 'USNS Pearson\nFPO AE 22768',
},
    'key89514': 'value27283',
    'key8731': 'value72026',
    'key31493': 'value62578',
    'key60180': 'value84362',
    'key84455': 'value30091',
},
    {
    'id': 17527492317551,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Dustin Miller',
    'address': '84327 Davis Parks\nMichaelside, DE 59693',
    'text': 'Cost hundred true how television agent pattern.\nChild cover our organization professional data. Phone provide figure draw nation. Institution left much determine.',
    'email': 'saraalexander@example.com',
    'phone_number': '(573)865-2029',
    'json': {
    'name': 'Joshua Graves',
    'address': '7699 Tina Mountain Suite 902\nSmithstad, DC 65196',
},
    'key63595': 'value85074',
    'key92772': 'value19647',
    'key5544': 'value30445',
},
    {
    'id': 17527492317561,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Reginald Garcia',
    'address': '714 Krueger Brooks\nKennedyfurt, AL 10043',
    'text': 'Test generation move glass quickly peace. Pressure author other before available arm.\nMost reveal up before. Your audience cost what.',
    'email': 'ajacobs@example.com',
    'phone_number': '791-623-6115x511',
    'json': {
    'name': 'Lindsay Brown',
    'address': '385 Blair Rest Suite 857\nNew Matthewville, HI 43406',
},
    'key77082': 'value62866',
},
    {
    'id': 17527492317572,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jordan Young',
    'address': 'PSC 8338, Box 2658\nAPO AA 81170',
    'text': 'Lose good member coach success off them. Long hold Republican cultural him summer. Certain history early fast a level voice.',
    'email': 'maloneanna@example.com',
    'phone_number': '8656000472',
    'json': {
    'name': 'Nancy Wang',
    'address': 'PSC 3087, Box 3566\nAPO AA 78773',
},
    'key75566': 'value59227',
    'key46047': 'value75707',
    'key87614': 'value91256',
    'key40442': 'value23824',
    'key14512': 'value90190',
    'key29069': 'value26873',
    'key68709': 'value9626',
    'key20371': 'value16465',
    'key13259': 'value26248',
    'key30829': 'value55388',
},
    {
    'id': 17527492317580,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Joshua Lopez',
    'address': '41638 Smith Points\nNicholsstad, ME 55393',
    'text': 'Plan machine security only trial senior me product. Allow matter follow home.',
    'email': 'diazgwendolyn@example.com',
    'phone_number': '+1-299-231-9571x455',
    'json': {
    'name': 'Patricia Wilkerson',
    'address': '2505 Shelley Street\nEast Arthur, WV 37419',
},
    'key32028': 'value95142',
    'key40272': 'value58525',
    'key93250': 'value1578',
    'key39681': 'value39569',
    'key68911': 'value90289',
},
    {
    'id': 17527492317591,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Jeffrey Mcclure',
    'address': '37489 Catherine Points Suite 698\nWilsonville, MS 28455',
    'text': 'Light late report perhaps wind pretty. Him must suffer physical attorney.\nAccording easy example nation. Record total program action another although conference.',
    'email': 'sbanks@example.net',
    'phone_number': '802.319.9894x696',
    'json': {
    'name': 'Molly Carter',
    'address': '7706 Nathan Junction\nSouth Leahmouth, MT 26670',
},
    'key15101': 'value49844',
    'key64232': 'value58884',
    'key74871': 'value83164',
    'key60307': 'value64084',
    'key19176': 'value60560',
    'key54311': 'value57456',
    'key59985': 'value64725',
    'key18867': 'value43326',
},
    {
    'id': 17527492317602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kenneth Haney',
    'address': '441 Gregory Fall\nEast Nancyhaven, KS 52845',
    'text': 'Rest along us firm himself believe. Third later throw the anyone somebody. Exist decade the everyone cell wide. Second occur current air mouth.',
    'email': 'andreagarcia@example.org',
    'phone_number': '(960)777-0934',
    'json': {
    'name': 'Jeffrey Lam',
    'address': '3836 Wanda Flats\nLake Karen, KS 12787',
},
    'key64426': 'value9988',
    'key61081': 'value55872',
    'key79764': 'value52102',
    'key79976': 'value99422',
    'key88681': 'value379',
    'key2688': 'value75496',
    'key52839': 'value70814',
    'key73866': 'value67628',
    'key61435': 'value96406',
    'key49075': 'value13256',
},
    {
    'id': 17527492317613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Christian Phelps',
    'address': '984 Rivera Camp Suite 328\nMeganbury, MD 16552',
    'text': 'Soon threat develop across yet. Ready those matter customer audience.\nTeach bad top receive mention. Cup science then others kind trouble.',
    'email': 'nancy23@example.com',
    'phone_number': '+1-604-824-3982x2744',
    'json': {
    'name': 'Samantha Ortiz',
    'address': '61664 Brian Burg Apt. 533\nSouth Annettetown, NJ 57995',
},
    'key23942': 'value86953',
    'key55443': 'value93915',
    'key95967': 'value23901',
    'key89336': 'value5160',
    'key68826': 'value43447',
    'key91989': 'value67221',
    'key88060': 'value90752',
    'key88284': 'value12680',
    'key82914': 'value25271',
},
    {
    'id': 17527492317623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Dawn Richards',
    'address': '197 Benjamin Pine\nAnnetteville, NC 81897',
    'text': 'Evidence stop dog.\nMonth next national let two ground. House himself result loss. Analysis draw budget five field turn skill.',
    'email': 'william47@example.com',
    'phone_number': '+1-811-208-2117x4579',
    'json': {
    'name': 'Keith Guerrero',
    'address': 'USS Johnson\nFPO AA 99527',
},
    'key7810': 'value40333',
    'key22259': 'value17135',
    'key69143': 'value74928',
    'key33722': 'value75209',
    'key17185': 'value18950',
    'key71607': 'value89283',
    'key23932': 'value23403',
    'key5712': 'value13420',
    'key16856': 'value49386',
},
    {
    'id': 17527492317633,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Taylor Lee',
    'address': 'Unit 7077 Box 5455\nDPO AE 06185',
    'text': 'Brother summer road step treatment manager. Class room wall western lead. Ten customer role start throughout hotel those finish. Decision official power affect.',
    'email': 'qwilliams@example.com',
    'phone_number': '219.732.8434',
    'json': {
    'name': 'Edgar Harris',
    'address': '0476 West Shores Apt. 482\nLake Patricia, PR 19941',
},
    'key34562': 'value44781',
    'key1430': 'value85840',
    'key28103': 'value98674',
    'key45454': 'value14937',
    'key90675': 'value57791',
    'key20103': 'value96279',
},
    {
    'id': 17527492317642,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Christopher Davis',
    'address': '06538 Ware Islands\nSouth Robert, MO 30392',
    'text': 'Evening staff attention. Line analysis around try. Enough too read peace type.\nImagine according window information office. Production another court political environment hundred front.',
    'email': 'flowerstimothy@example.net',
    'phone_number': '(440)277-7695x3822',
    'json': {
    'name': 'Heather Garrison',
    'address': '0292 David Ports Suite 710\nRonaldburgh, NV 24402',
},
    'key4405': 'value14067',
    'key99677': 'value48472',
    'key67847': 'value48586',
    'key89662': 'value29364',
    'key54048': 'value51755',
    'key92141': 'value80194',
    'key43976': 'value15652',
    'key67667': 'value78991',
},
    {
    'id': 17527492317653,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kimberly King',
    'address': '6645 Sweeney Locks\nBrianchester, MA 74879',
    'text': 'Protect leave political teacher since hospital she. Since rest full skin minute leader edge.\nLay traditional interview each fish accept. Century lot book enjoy. Design production sense will.',
    'email': 'kingmichelle@example.org',
    'phone_number': '001-577-441-1826x9922',
    'json': {
    'name': 'Briana Nelson',
    'address': '37353 Gary Canyon\nEast Taraborough, ME 99208',
},
    'key76036': 'value6658',
    'key87794': 'value45802',
    'key95937': 'value67916',
    'key22707': 'value75902',
    'key81094': 'value1076',
    'key36561': 'value27040',
    'key3962': 'value82428',
    'key32842': 'value71345',
    'key96060': 'value19610',
},
    {
    'id': 17527492317665,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'David Kemp',
    'address': '82792 Scott Tunnel\nJohnfurt, UT 16149',
    'text': 'Stage who treat mean model low. Show fact artist share seat.\nFinally technology president drop. Center power off fund fill pass stock. Same popular generation player test.',
    'email': 'shannonkelley@example.org',
    'phone_number': '5143611144',
    'json': {
    'name': 'Maria Wilkinson',
    'address': '5955 Bryan Vista\nNealtown, DC 50449',
},
    'key81014': 'value82364',
    'key25250': 'value75781',
    'key40710': 'value22234',
    'key28741': 'value93824',
    'key31045': 'value24722',
    'key70154': 'value8827',
    'key75811': 'value12224',
    'key74016': 'value6294',
    'key78879': 'value47885',
},
    {
    'id': 17527492317676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Lisa Tucker MD',
    'address': '4907 Jessica Walks Suite 286\nPort Ariana, NH 53686',
    'text': 'Drive officer opportunity whether deal station. Game again together lot. Report carry hour resource exist write chance. Chair yet main land sometimes better meeting.',
    'email': 'ryanmaria@example.net',
    'phone_number': '001-511-730-0230x60073',
    'json': {
    'name': 'Michael Todd',
    'address': '6744 Seth Fields Apt. 321\nSotomouth, ME 02661',
},
    'key24058': 'value70840',
    'key68565': 'value72207',
    'key3835': 'value22289',
    'key11290': 'value64016',
    'key36044': 'value4684',
    'key18827': 'value81911',
    'key20064': 'value47490',
    'key42204': 'value83170',
},
    {
    'id': 17527492317688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Barbara Bell',
    'address': '20544 Julie Haven\nAndersonchester, WI 44527',
    'text': 'Arrive international term something somebody plan. Than green various born memory million.\nPosition music season before continue. Very fund day method lead energy.',
    'email': 'cmaynard@example.net',
    'phone_number': '001-699-313-0599x50902',
    'json': {
    'name': 'Robert Taylor',
    'address': '28828 Aguilar Summit\nNew Christie, AL 98976',
},
    'key13868': 'value25584',
    'key24037': 'value7832',
    'key21178': 'value24454',
    'key44363': 'value61107',
},
    {
    'id': 17527492317699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Brandon Reed',
    'address': '167 Daniel Road\nNorth Eric, SC 90534',
    'text': 'Growth specific so federal effect star. Side leg young pass charge. Mission soldier cause pass control knowledge large. Environment model point collection beyond candidate society.',
    'email': 'morrisdaniel@example.com',
    'phone_number': '507-875-7132x5605',
    'json': {
    'name': 'James Villegas',
    'address': '6049 Michele Corners\nLake Marc, NC 18614',
},
    'key51092': 'value12379',
    'key90005': 'value18319',
    'key76644': 'value75961',
    'key34142': 'value38386',
},
    {
    'id': 17527492317710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Amanda Gonzalez',
    'address': '6082 Rodriguez Plains Suite 458\nEast Timothy, PR 39059',
    'text': 'Per bit audience practice respond ready miss remain. Discussion everything million but just. Sure parent where ok result beautiful.',
    'email': 'pburns@example.net',
    'phone_number': '(460)409-6183x4963',
    'json': {
    'name': 'Jordan Wright',
    'address': '00108 Howard Flat Apt. 654\nTorresview, FL 28024',
},
    'key26991': 'value24384',
    'key81800': 'value87132',
    'key23232': 'value47731',
    'key56489': 'value43649',
    'key40162': 'value8001',
    'key75147': 'value79750',
    'key7392': 'value14930',
    'key26801': 'value36132',
    'key30357': 'value12860',
    'key19380': 'value64653',
},
    {
    'id': 17527492317721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Carol Moore',
    'address': 'USS Gonzalez\nFPO AP 30912',
    'text': 'Fall same decision dinner. Friend scientist air more. Describe news choice pay chair myself economic.\nMove now wish level. Could whom home win. International star effort leg mind range hotel.',
    'email': 'thomasapril@example.org',
    'phone_number': '2399570463',
    'json': {
    'name': 'Michelle Bowman',
    'address': '47257 Kristi Land\nWest Laurafurt, WA 55437',
},
    'key17051': 'value80225',
},
    {
    'id': 17527492317731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Lindsey Brewer',
    'address': '3345 Melanie Extensions Apt. 216\nDavisport, PA 77393',
    'text': 'Surface language to carry. Prove laugh could they sister. Understand third officer town.\nWeight imagine create ahead. Chance forget trip attack measure large later. Material every remain follow.',
    'email': 'diane97@example.org',
    'phone_number': '200.620.7395',
    'json': {
    'name': 'Donald Rich',
    'address': '5137 Hensley Fall\nWiseport, SD 67509',
},
    'key12979': 'value29184',
    'key61994': 'value40092',
    'key1516': 'value23561',
    'key29616': 'value38734',
    'key68509': 'value94702',
    'key73242': 'value52245',
    'key87195': 'value27643',
    'key27893': 'value33541',
    'key8919': 'value43293',
},
    {
    'id': 17527492317742,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Brian Kelley',
    'address': 'USNS Price\nFPO AA 57946',
    'text': 'None sing success mission eat. Stage large foreign west citizen ask.',
    'email': 'ashleythompson@example.net',
    'phone_number': '282.406.5728x0785',
    'json': {
    'name': 'Tara Young',
    'address': '6737 Brock Views Apt. 918\nEast Erinfort, TX 76680',
},
    'key55018': 'value54526',
    'key3937': 'value26285',
    'key53288': 'value91740',
    'key55880': 'value38205',
    'key97340': 'value76327',
    'key85914': 'value8068',
    'key11475': 'value57803',
},
    {
    'id': 17527492317753,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'David Martinez',
    'address': '1739 Moore Haven Suite 397\nSouth Juanfurt, TX 39538',
    'text': 'Old old official give attention it. Method once past ten its manage. Wife huge change will.\nRoad miss final would wife.',
    'email': 'kimberly70@example.org',
    'phone_number': '4268762938',
    'json': {
    'name': 'Samuel Hall',
    'address': '498 Carla Fords\nSouth Michelleport, NY 96808',
},
    'key60901': 'value71818',
    'key73239': 'value11306',
    'key50466': 'value55724',
    'key74358': 'value60534',
    'key23643': 'value13182',
    'key18054': 'value89717',
    'key27541': 'value27460',
    'key99436': 'value57450',
    'key78111': 'value52935',
    'key28098': 'value34088',
},
    {
    'id': 17527492317763,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christopher Delgado',
    'address': '36193 Estes Crossroad\nWhiteview, AZ 33033',
    'text': 'Strategy show off beyond southern produce. Edge off stock.\nFeel certain American local. Possible language other produce trial.\nYeah suddenly Congress drive. Plan method finish coach live.',
    'email': 'davisdeborah@example.org',
    'phone_number': '(443)547-8891',
    'json': {
    'name': 'Joseph Miller',
    'address': 'Unit 3978 Box 6181\nDPO AE 49777',
},
    'key73270': 'value39620',
    'key28498': 'value96683',
    'key36038': 'value66889',
    'key17460': 'value90673',
    'key4490': 'value76317',
    'key59716': 'value97688',
},
    {
    'id': 17527492317773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Barbara Hernandez',
    'address': '46014 Jacqueline Mission Apt. 782\nTylerborough, IN 05881',
    'text': 'Government exist radio policy college him. Line laugh front seat third. General civil may young.\nPresident former unit hear suggest. Money executive long.',
    'email': 'lopezbrandy@example.net',
    'phone_number': '513.786.5892',
    'json': {
    'name': 'Crystal Clark',
    'address': 'USCGC Collins\nFPO AA 68434',
},
    'key4978': 'value74648',
    'key41987': 'value38173',
    'key44433': 'value47636',
    'key86324': 'value48422',
    'key90691': 'value81381',
    'key99924': 'value99388',
    'key65334': 'value9591',
    'key26331': 'value52637',
},
    {
    'id': 17527492317783,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Cassandra Perez',
    'address': '12196 Jackson Passage\nDuncantown, UT 14179',
    'text': 'Future likely security be street behind serve. Light east go. Pass meeting affect include term.',
    'email': 'sheila63@example.com',
    'phone_number': '500-376-9948x845',
    'json': {
    'name': 'Raymond Allen',
    'address': '64827 Perkins Terrace Apt. 896\nMcguirestad, GA 04676',
},
    'key50145': 'value8858',
    'key64920': 'value12457',
    'key76826': 'value85846',
    'key6149': 'value2606',
    'key23506': 'value40879',
    'key72613': 'value59283',
    'key60048': 'value2698',
    'key40828': 'value55937',
    'key23487': 'value47151',
},
    {
    'id': 17527492317795,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Terri Smith',
    'address': '545 Bartlett Trail\nLake Jose, DE 70687',
    'text': 'Rate change such southern gun national firm.\nDrug truth administration reality. Low government want shoulder road. Organization its raise chair per. Find body staff official money could long unit.',
    'email': 'timothy68@example.com',
    'phone_number': '859-376-5528',
    'json': {
    'name': 'Kathy Mitchell',
    'address': '201 Ball Manor\nSaraside, MI 18888',
},
    'key54448': 'value25902',
    'key42404': 'value99191',
    'key44643': 'value79784',
    'key13829': 'value50067',
    'key87416': 'value42129',
    'key33563': 'value6796',
    'key45436': 'value59838',
    'key12301': 'value2274',
    'key44187': 'value29124',
    'key99074': 'value62515',
},
    {
    'id': 17527492317805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Melissa Lee',
    'address': '08978 Terri Groves\nLake Tracyfort, FL 89004',
    'text': 'Air feel whose protect heavy. Girl whom develop air necessary. Program medical near news main impact feeling. See set toward home put.',
    'email': 'zimmermanwilliam@example.com',
    'phone_number': '466.226.8818',
    'json': {
    'name': 'Arthur Mclaughlin',
    'address': '1320 Carla Dam\nAndrewton, AR 27587',
},
    'key15139': 'value46905',
    'key347': 'value73410',
    'key2970': 'value53739',
    'key66780': 'value55900',
    'key46517': 'value61527',
    'key76371': 'value95566',
    'key5512': 'value71901',
    'key56840': 'value16477',
},
    {
    'id': 17527492317816,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Tracy Espinoza',
    'address': '899 Dustin Knolls\nNorth Kyle, AK 33641',
    'text': 'Choice store example society. Write in feeling sport check professional. Service always third foot five. Whether pressure animal street.',
    'email': 'ghamilton@example.org',
    'phone_number': '797-990-1659x26260',
    'json': {
    'name': 'Tina Webb',
    'address': '8755 Green Highway\nEast Joyce, WY 97221',
},
    'key69584': 'value68126',
    'key23249': 'value13763',
    'key17035': 'value77595',
    'key36993': 'value78917',
    'key12909': 'value91489',
    'key44270': 'value21540',
    'key40498': 'value31623',
    'key61160': 'value17258',
},
    {
    'id': 17527492317827,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Carolyn Taylor',
    'address': 'PSC 5969, Box 8457\nAPO AP 29968',
    'text': 'At get executive on often seven. Short analysis future their notice thought. Turn because reveal community and.',
    'email': 'johnmartinez@example.net',
    'phone_number': '389-622-3836',
    'json': {
    'name': 'Jennifer Brown',
    'address': '78386 Jeffrey Way Suite 914\nSouth Lisashire, NM 08995',
},
    'key19735': 'value47931',
    'key35746': 'value24512',
    'key9881': 'value13200',
    'key80552': 'value77682',
    'key46576': 'value10392',
    'key45195': 'value19497',
    'key5741': 'value29016',
    'key48426': 'value37782',
    'key4310': 'value78472',
},
    {
    'id': 17527492317836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Anna Reyes',
    'address': '2144 Monique Hill\nPort Susanstad, NH 56789',
    'text': 'Should skill that manage want play. Could follow explain instead in positive.\nLeft in these how student enjoy officer. Listen raise sign finish threat. Industry TV available action or represent.',
    'email': 'stacey38@example.com',
    'phone_number': '+1-573-727-4379x966',
    'json': {
    'name': 'John Bass',
    'address': '5330 Jenkins Inlet Suite 990\nGilmorebury, VA 12740',
},
    'key97222': 'value68012',
    'key14960': 'value11518',
    'key33198': 'value87064',
    'key17290': 'value17469',
    'key1003': 'value1639',
    'key914': 'value87721',
    'key43089': 'value42657',
},
    {
    'id': 17527492317846,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Dennis Johnson',
    'address': 'Unit 7882 Box 7840\nDPO AA 76788',
    'text': 'Word sense reflect traditional save door guess push. Fight work involve institution leader reduce. Surface factor grow sister.\nSame chance land give. Attorney point heavy pretty financial.',
    'email': 'fraziertimothy@example.com',
    'phone_number': '431.372.9622x27543',
    'json': {
    'name': 'Valerie Diaz',
    'address': '254 Welch Hollow Apt. 329\nNorth Shannon, NV 10917',
},
    'key17363': 'value78281',
},
    {
    'id': 17527492317856,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Kelly Fuentes',
    'address': '26822 Alvarez Green Apt. 843\nWoodardshire, KY 02912',
    'text': 'Network member I green. Window young according worker subject. Opportunity little for your consumer.',
    'email': 'nicolejohnson@example.com',
    'phone_number': '962-297-9773x017',
    'json': {
    'name': 'Teresa Horne',
    'address': '87756 White Run Suite 752\nScotttown, AL 95140',
},
    'key30407': 'value52361',
    'key3283': 'value10105',
    'key76256': 'value87510',
    'key54247': 'value60865',
    'key90000': 'value18465',
    'key9939': 'value13312',
    'key90683': 'value33622',
    'key8110': 'value10059',
},
    {
    'id': 17527492317867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Kevin Stanton',
    'address': '32840 Savannah Grove Apt. 103\nPort Matthew, RI 65972',
    'text': 'Technology like thing commercial whatever. At travel culture defense state everything pay. Important training seek direction generation add team. Course you professor ground.',
    'email': 'ortizjay@example.org',
    'phone_number': '+1-633-840-1350x5684',
    'json': {
    'name': 'Robert Robbins',
    'address': '2395 Davis Brook Apt. 302\nWest Timothyport, AZ 19922',
},
    'key522': 'value10864',
    'key29251': 'value27335',
    'key20056': 'value2280',
    'key73149': 'value86483',
},
    {
    'id': 17527492317879,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'James Smith',
    'address': '500 Fuller Port Suite 733\nEast Bobby, ME 55792',
    'text': 'Morning former director middle free safe. Design pull certain standard vote partner certain. Compare rather agent.',
    'email': 'pharrison@example.com',
    'phone_number': '744-935-5187x321',
    'json': {
    'name': 'Susan Haynes',
    'address': '201 Hall Walk\nEast Isabel, CT 03714',
},
    'key4079': 'value98911',
    'key88726': 'value62920',
    'key33635': 'value93228',
    'key71034': 'value28663',
},
    {
    'id': 17527492317889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Christina Carroll',
    'address': '93762 Collins Oval Apt. 780\nJamesfurt, KS 77313',
    'text': 'Western follow all evidence peace just reality. Election finally remain save another.\nEffect so professional send. Billion all event statement no should lead.',
    'email': 'joseph47@example.com',
    'phone_number': '001-864-592-9716x7961',
    'json': {
    'name': 'Kelly Patterson',
    'address': '782 Eric Drive Suite 557\nWest Michael, VT 84649',
},
    'key73138': 'value10142',
    'key10416': 'value12877',
},
    {
    'id': 17527492317900,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Alicia Barr',
    'address': '45102 Matthew Mills\nWilliamsonview, VI 37672',
    'text': 'Body relate key nothing media be. Popular social through. Small director animal several them share commercial success.\nWest nice man quite itself law. Ball project maybe pattern.',
    'email': 'thomas44@example.com',
    'phone_number': '862.549.3224x70098',
    'json': {
    'name': 'Kathryn Matthews',
    'address': '3762 Hughes Ridge\nLake Carlyborough, WY 85696',
},
    'key40634': 'value76106',
    'key63729': 'value90244',
    'key80061': 'value66072',
    'key29475': 'value68720',
    'key44849': 'value3949',
},
    {
    'id': 17527492317911,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'John Lee',
    'address': '84629 Hill Gateway\nVaughantown, FM 83285',
    'text': 'Physical check church nothing main. Remember class nor pay country between.\nTend speak team stock. If section her city individual. Consumer business different peace few.',
    'email': 'johngutierrez@example.org',
    'phone_number': '220-654-7793x716',
    'json': {
    'name': 'Benjamin Bowman',
    'address': '40719 Annette Turnpike Apt. 965\nPort Kimberlyville, ME 34421',
},
    'key74117': 'value47653',
    'key45365': 'value14951',
    'key6002': 'value83756',
    'key49544': 'value87634',
    'key98019': 'value67095',
    'key36049': 'value31834',
},
    {
    'id': 17527492317923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mindy Gardner',
    'address': '153 Martinez Loop Apt. 665\nMorganside, ME 18744',
    'text': 'Dog number direction. Join above many probably. Seat eight reveal talk feeling general blood left.\nResearch exist car probably know. Their long loss appear. Cell who Mrs city leave one kitchen.',
    'email': 'vhernandez@example.com',
    'phone_number': '(793)442-1127x512',
    'json': {
    'name': 'Theresa Goodman',
    'address': '51877 Brian Road Apt. 582\nLake Markland, WI 41037',
},
    'key78939': 'value31254',
    'key92930': 'value21395',
    'key87851': 'value10072',
    'key91471': 'value70815',
    'key72371': 'value7545',
    'key78684': 'value30276',
    'key82326': 'value4551',
    'key11030': 'value59900',
    'key15478': 'value40589',
    'key75727': 'value69883',
},
    {
    'id': 17527492317934,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Jennifer Hall',
    'address': '017 Gavin Springs Suite 251\nSethville, WI 67717',
    'text': 'Magazine she not continue together into while yourself. Feeling ok rise happy no appear. Hundred she thank close because some free.',
    'email': 'cookdawn@example.com',
    'phone_number': '(754)545-3510',
    'json': {
    'name': 'Stephanie Jenkins',
    'address': 'USS Stout\nFPO AP 65902',
},
    'key39927': 'value5050',
    'key28460': 'value51261',
},
    {
    'id': 17527492317944,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Donald Tucker',
    'address': '1487 Yvonne Summit\nLake Matthewside, IN 16072',
    'text': 'Example bit four challenge build. Focus board decision. Listen practice daughter sell rich term his goal.\nHow tend born I our including news. Effort truth physical mean begin enjoy.',
    'email': 'stevensalyssa@example.org',
    'phone_number': '001-505-222-8051',
    'json': {
    'name': 'Crystal Wallace',
    'address': 'USS Blankenship\nFPO AP 46666',
},
    'key8136': 'value70040',
    'key73557': 'value86102',
    'key4466': 'value18431',
    'key88107': 'value59006',
    'key14251': 'value66001',
    'key64295': 'value31744',
    'key51259': 'value17163',
    'key55805': 'value33862',
    'key17395': 'value53783',
},
    {
    'id': 17527492317954,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Matthew Hernandez',
    'address': '8967 Jessica Haven Suite 249\nPort Veronica, HI 25469',
    'text': 'Hotel than nothing himself raise soon gas. Military figure late spring reason we. Rich model foot social around fact.',
    'email': 'xthompson@example.org',
    'phone_number': '8723065697',
    'json': {
    'name': 'Whitney Henderson',
    'address': '6279 Parker Valley Suite 199\nLake Aaron, DE 60063',
},
    'key56101': 'value98321',
    'key62638': 'value15901',
    'key93575': 'value36089',
    'key26234': 'value46665',
    'key97227': 'value93267',
    'key30102': 'value1025',
},
    {
    'id': 17527492317964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Mr. Andrew Heath',
    'address': '13381 Lamb Ville Apt. 153\nChavezbury, RI 33169',
    'text': 'Matter rock during political street glass. End key future follow military. Wife player rise score.\nHope carry somebody it.',
    'email': 'duranoscar@example.com',
    'phone_number': '562-898-5467x227',
    'json': {
    'name': 'Jay Price',
    'address': '083 Kristin Manors Apt. 428\nCatherinemouth, MD 52882',
},
    'key71516': 'value66635',
    'key65935': 'value4326',
    'key94064': 'value3014',
    'key74217': 'value23379',
    'key17912': 'value40669',
    'key81760': 'value61212',
    'key90391': 'value23244',
    'key99980': 'value15628',
    'key27665': 'value80492',
},
    {
    'id': 17527492317976,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Andrew Ward',
    'address': '79167 Olsen River Suite 509\nWest Robinbury, CO 40322',
    'text': 'Central occur although agreement. Score late respond share ever represent kind.\nFather with significant strategy administration ok poor. Church water alone billion bag free board safe.',
    'email': 'galvanemily@example.com',
    'phone_number': '(976)516-0433x9407',
    'json': {
    'name': 'Heidi Bird',
    'address': '77368 Murray Meadows Suite 874\nRobinsonchester, DE 93178',
},
    'key71905': 'value24143',
    'key38787': 'value52702',
    'key62516': 'value78111',
    'key80570': 'value44317',
    'key87846': 'value42470',
    'key30181': 'value41798',
},
    {
    'id': 17527492317988,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Amanda Edwards',
    'address': '7651 Nguyen Trace Apt. 021\nStevenberg, AS 41524',
    'text': 'Capital blue ten detail store base moment. Why decade natural money leader sit heavy. After goal style.\nResource kid someone since.',
    'email': 'dandersen@example.org',
    'phone_number': '5996664440',
    'json': {
    'name': 'Michelle Ramos',
    'address': '815 Campbell Centers Apt. 336\nKevinfort, MT 45883',
},
    'key51271': 'value67387',
    'key29200': 'value17976',
    'key10742': 'value87419',
    'key5751': 'value74179',
    'key25292': 'value89743',
    'key87593': 'value46999',
    'key72389': 'value33588',
    'key55983': 'value84176',
},
    {
    'id': 17527492317999,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Samuel Spears',
    'address': '758 Campbell Parks\nBrentfurt, TN 86207',
    'text': 'What them particularly recognize ahead.\nSuccessful recognize charge tax real left quality. Argue man history necessary bag. President artist your car avoid him suffer player.',
    'email': 'raymond82@example.com',
    'phone_number': '+1-239-452-0830x3799',
    'json': {
    'name': 'Jennifer Dennis',
    'address': '410 Dawn Heights Apt. 027\nEast Maryburgh, HI 14844',
},
    'key48117': 'value40722',
    'key98069': 'value21781',
    'key8256': 'value69541',
    'key32404': 'value54624',
    'key91737': 'value67376',
    'key29342': 'value43548',
    'key85332': 'value48816',
    'key25376': 'value45365',
    'key95573': 'value45115',
},
    {
    'id': 17527492318010,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Matthew Jones',
    'address': '5204 Christina Junctions\nMarissafort, LA 73191',
    'text': 'Company capital billion. Action common investment team. Picture activity capital admit little our daughter.\nMeeting wind once wife including reveal. Any election five mean down if.',
    'email': 'droberson@example.org',
    'phone_number': '220-423-9081',
    'json': {
    'name': 'Edward Carter',
    'address': '07986 Pineda Ways Suite 654\nAdammouth, PA 65095',
},
    'key3306': 'value10827',
},
    {
    'id': 17527492318021,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Michael Rivera',
    'address': '6522 Meghan Haven\nWilsontown, WV 64978',
    'text': 'No already food blood teach. Thank moment professor believe.\nGuess population turn choose material.',
    'email': 'andrew71@example.net',
    'phone_number': '+1-508-732-1697x329',
    'json': {
    'name': 'Kimberly Carrillo',
    'address': '7920 Joseph Landing\nNew Cindyshire, NH 50363',
},
    'key61150': 'value80181',
    'key8656': 'value40060',
    'key71430': 'value44900',
    'key5394': 'value56648',
    'key96599': 'value8288',
    'key7824': 'value5990',
},
    {
    'id': 17527492318031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jeffrey Villarreal',
    'address': '236 Connie Gateway Apt. 828\nLake Calebmouth, VI 42683',
    'text': 'Through gun beyond word. Nice model rate system land face. Admit race other collection seem the safe.',
    'email': 'josborne@example.net',
    'phone_number': '325.992.4814x4016',
    'json': {
    'name': 'Charles Melendez',
    'address': '58447 Mike Shoals Suite 361\nBonillaberg, NC 12845',
},
    'key1605': 'value56280',
    'key61154': 'value4402',
    'key26483': 'value22450',
    'key41609': 'value43393',
    'key55576': 'value90750',
    'key16791': 'value72309',
},
    {
    'id': 17527492318042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Amanda Walker',
    'address': '0852 Alvarez Lights Suite 390\nNorth Jonathonside, UT 13199',
    'text': 'Moment soon fight up even. Common either southern glass. Couple wonder industry feeling read chair.\nBuilding speech hotel begin smile option. Character before feeling organization.',
    'email': 'donna52@example.com',
    'phone_number': '885-855-3279x1164',
    'json': {
    'name': 'Elijah Stanley',
    'address': '9376 Phillips Station Apt. 909\nBarrettmouth, AS 93253',
},
    'key28352': 'value81285',
},
    {
    'id': 17527492318053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Sara Herrera',
    'address': '81769 Paul Avenue Suite 588\nSouth Jeremy, DC 23842',
    'text': 'Security attention perform decide myself stock. Language do close represent question yes.\nTreatment enough win him. Small yes everything international fish up what several. East life role point easy.',
    'email': 'mstephens@example.com',
    'phone_number': '(465)569-8559x36983',
    'json': {
    'name': 'Tammy Cardenas',
    'address': '0199 Heather Corners\nEast Jamesport, TN 24427',
},
    'key60604': 'value85039',
},
    {
    'id': 17527492318064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Daisy Brady',
    'address': 'USS Smith\nFPO AA 28649',
    'text': 'Truth although ask house paper heart. Give force quickly theory arrive other.\nEasy magazine particular threat person eight. Significant you believe.',
    'email': 'rubenwright@example.com',
    'phone_number': '454.733.0933x542',
    'json': {
    'name': 'Jose Lee',
    'address': '510 Pedro Springs Apt. 809\nKendratown, IA 31610',
},
    'key24060': 'value1179',
    'key47903': 'value42903',
    'key5006': 'value21244',
    'key12861': 'value27582',
    'key95898': 'value78385',
    'key58109': 'value68035',
    'key62459': 'value26807',
},
    {
    'id': 17527492318074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Meghan Hart',
    'address': '5898 Gross Passage Apt. 590\nSouth Jeffreytown, MS 61018',
    'text': 'Need hear miss beyond bit true. Front movement do green page body. Pick matter improve discussion focus.',
    'email': 'daniel43@example.com',
    'phone_number': '958.462.7148x007',
    'json': {
    'name': 'Thomas Paul',
    'address': '448 Terry Manor\nWaltonstad, AR 64711',
},
    'key74024': 'value2433',
    'key19887': 'value1086',
    'key2588': 'value30679',
    'key83779': 'value3533',
},
    {
    'id': 17527492318084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'James Knox',
    'address': '9055 Garcia Crescent Apt. 097\nLake Jamesborough, TN 71045',
    'text': 'Bring serious student expect term. Not wrong trade stuff appear leg wind.\nUnit plant various chance. Probably future class executive line pull represent.',
    'email': 'glendapatterson@example.com',
    'phone_number': '001-612-960-3285x061',
    'json': {
    'name': 'Caitlin Cook',
    'address': '867 Martin Walks Suite 673\nErikland, KS 82123',
},
    'key83716': 'value89007',
    'key67409': 'value63370',
    'key58571': 'value70818',
    'key83953': 'value66914',
    'key61479': 'value78690',
    'key93427': 'value66446',
},
    {
    'id': 17527492318096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Ashley Wells',
    'address': '532 John Knolls Apt. 073\nPort Hollyborough, CO 07636',
    'text': 'Shoulder phone father begin week. Less gas six up. Pressure enjoy evidence after.',
    'email': 'xgomez@example.com',
    'phone_number': '(963)350-0336x182',
    'json': {
    'name': 'Abigail Chapman',
    'address': '82148 Jill Creek Suite 915\nWilliamstown, MD 40606',
},
    'key76909': 'value73572',
    'key87975': 'value45213',
},
    {
    'id': 17527492318107,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Jennifer Parker',
    'address': '47008 Thompson Stravenue Suite 324\nLake Amberside, MP 77377',
    'text': 'Us center image early. Hand real wind drive manage room.\nDiscover maintain try organization hand message sit. Rather occur out despite figure place.',
    'email': 'brivera@example.net',
    'phone_number': '001-284-666-3689',
    'json': {
    'name': 'Leslie Williams',
    'address': '38585 Taylor Forks\nPort Diana, NY 97639',
},
    'key28020': 'value49156',
    'key77533': 'value39297',
    'key54246': 'value69093',
    'key51996': 'value55011',
    'key96998': 'value4972',
    'key21718': 'value56757',
    'key31205': 'value59652',
    'key65699': 'value10950',
    'key56747': 'value62407',
    'key11760': 'value54381',
},
    {
    'id': 17527492318118,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Richard Moore',
    'address': '0492 Marvin Ports Apt. 543\nLake Gregoryport, VA 49221',
    'text': 'Anyone participant tend view.\nLast many let. Movie great guess entire.\nHuge nothing manage short return majority ever. Wide fast fund on might with station.',
    'email': 'robertsdavid@example.org',
    'phone_number': '+1-815-467-6299x134',
    'json': {
    'name': 'Jade Cannon',
    'address': '58453 Gavin Pines Apt. 250\nLake Jasonmouth, AZ 63170',
},
    'key75457': 'value74035',
    'key50747': 'value14779',
    'key16835': 'value13544',
    'key44243': 'value84821',
    'key59000': 'value13778',
    'key76542': 'value93749',
    'key27457': 'value5161',
    'key11083': 'value17262',
    'key80420': 'value47024',
},
    {
    'id': 17527492318129,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Robert Oconnor',
    'address': '922 Stevens Estate\nRiggsside, SD 92266',
    'text': 'Including there power it explain compare treatment. Occur rock north cell wait.\nGovernment firm quickly great.',
    'email': 'angela01@example.org',
    'phone_number': '222.734.8061x93082',
    'json': {
    'name': 'Andrew Blanchard',
    'address': '876 Smith Ranch Apt. 241\nLongfort, TN 99851',
},
    'key2920': 'value56903',
    'key22831': 'value90780',
    'key25385': 'value50731',
    'key53216': 'value93496',
    'key7223': 'value1520',
    'key68331': 'value1208',
    'key8244': 'value3345',
},
    {
    'id': 17527492318140,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Cynthia Sheppard',
    'address': '9904 Shawna Track Suite 315\nNorth Brandonbury, ND 56309',
    'text': 'Form say there section sister all walk left. Them dinner authority six candidate couple.\nExpert some south wife road range. Effort television future economic so popular vote. Order foreign base.',
    'email': 'sandra18@example.com',
    'phone_number': '4119161228',
    'json': {
    'name': 'Mike Smith',
    'address': '011 Jonathan Key Suite 106\nEast Colleenview, NM 19223',
},
    'key69052': 'value40807',
    'key48431': 'value19177',
},
    {
    'id': 17527492318151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Anthony Farmer',
    'address': '3303 Kylie Knolls\nEast Julieberg, CO 67443',
    'text': 'White society wall space my security fire. Point place he science strategy discussion. Current someone democratic reality operation light.',
    'email': 'michaelschmidt@example.net',
    'phone_number': '(693)511-6253x26750',
    'json': {
    'name': 'Gregg Moore',
    'address': 'USNS Hawkins\nFPO AE 03083',
},
    'key85899': 'value78459',
    'key95145': 'value58292',
    'key7230': 'value39410',
    'key69824': 'value78003',
    'key68246': 'value63062',
    'key59301': 'value26605',
    'key52060': 'value14031',
    'key17833': 'value50910',
},
    {
    'id': 17527492318161,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Amanda Pineda',
    'address': '834 Cruz Village\nNew Derrick, NM 87033',
    'text': 'Wear full list minute majority executive. Soldier other main item list. Even record various strong mouth really already.',
    'email': 'sylvia77@example.net',
    'phone_number': '001-743-307-1037x699',
    'json': {
    'name': 'Nancy Gutierrez',
    'address': '282 Rodriguez Station\nSouth Katelyn, VI 68280',
},
    'key82044': 'value54984',
    'key96145': 'value71630',
    'key94687': 'value25523',
    'key44800': 'value59138',
    'key48260': 'value5367',
    'key31731': 'value83966',
    'key56893': 'value25977',
    'key98600': 'value50937',
    'key96691': 'value22705',
},
    {
    'id': 17527492318171,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Doris Davidson',
    'address': '178 Mcdonald Island\nNew Josephberg, IA 05498',
    'text': 'Area although parent deal. Weight in seven lawyer window mission. Help carry fund. Kind or safe financial cultural.',
    'email': 'steven16@example.org',
    'phone_number': '(236)866-2241',
    'json': {
    'name': 'Jill Weaver',
    'address': '5511 Norman Gateway\nSouth Craigtown, OK 20689',
},
    'key13918': 'value52297',
    'key81501': 'value62244',
    'key10059': 'value60629',
    'key34371': 'value81365',
    'key92789': 'value67745',
},
    {
    'id': 17527492318181,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Anne Martin',
    'address': '38963 Paul Street\nJacksonborough, MH 18091',
    'text': 'Lay town as support ago. Their maintain what week. Husband while choose society data perform.',
    'email': 'patricklong@example.net',
    'phone_number': '791.559.6770',
    'json': {
    'name': 'Heather Crawford',
    'address': '60226 Wood Keys Apt. 387\nEast Joelfort, DE 99643',
},
    'key2127': 'value82818',
    'key3510': 'value49575',
    'key99065': 'value91830',
    'key97891': 'value58022',
    'key20724': 'value38885',
    'key52638': 'value76815',
    'key33702': 'value28817',
    'key49627': 'value69176',
    'key65669': 'value43379',
    'key32086': 'value55267',
},
    {
    'id': 17527492318192,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Dawn Mccann',
    'address': '241 Jeff Island Apt. 511\nJosephland, GU 63011',
    'text': 'Water center present remember fast. Long reveal make have reach safe without enough. Identify light old true whole need. Occur east marriage suffer go personal perhaps matter.',
    'email': 'yperez@example.com',
    'phone_number': '551.598.7755x7319',
    'json': {
    'name': 'Carmen Williams',
    'address': '0189 Murphy Parkway\nCarpentermouth, CO 40652',
},
    'key80497': 'value61729',
    'key20354': 'value363',
    'key69788': 'value41108',
    'key62905': 'value41555',
    'key16031': 'value9336',
    'key23915': 'value4346',
    'key24865': 'value43518',
    'key21714': 'value23151',
    'key97502': 'value16648',
},
    {
    'id': 17527492318203,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Chloe Hopkins',
    'address': '7471 Kathy Crest Apt. 828\nNorth Jamesmouth, AK 72415',
    'text': 'Today medical key bank base account son challenge. Charge maintain toward situation alone. Economic understand pass control outside because. Reason lose including look move.\nDoor reach fine assume.',
    'email': 'abbotttiffany@example.com',
    'phone_number': '322-733-0722x69090',
    'json': {
    'name': 'Tony Roberts',
    'address': '801 Nicholas Centers Apt. 802\nErikamouth, RI 26467',
},
    'key94368': 'value53773',
    'key95016': 'value88852',
    'key54955': 'value90030',
    'key77964': 'value19048',
},
    {
    'id': 17527492318214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Valerie Russell',
    'address': '885 Bradley Causeway Suite 554\nHudsonmouth, AL 67865',
    'text': 'Note operation worker send check table Mr. Recognize board foreign responsibility. Turn movement early act actually travel.\nMyself every voice direction director. Writer scientist analysis pattern.',
    'email': 'kevin32@example.com',
    'phone_number': '+1-714-589-1422x9190',
    'json': {
    'name': 'Rodney Johnson',
    'address': 'PSC 0847, Box 1329\nAPO AA 99538',
},
    'key67356': 'value66181',
    'key25648': 'value61420',
    'key75109': 'value23687',
},
    {
    'id': 17527492318223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Holly Floyd',
    'address': '2603 Heidi Curve Apt. 644\nPort Katherine, OH 50665',
    'text': 'Language recognize task site your response defense. Behavior be simply word weight among fall. Science always task.',
    'email': 'wellslinda@example.org',
    'phone_number': '218.215.6645',
    'json': {
    'name': 'Dustin Hill',
    'address': '823 Hinton Drive\nBeasleyland, NY 87243',
},
    'key29172': 'value87934',
    'key13903': 'value19626',
    'key76359': 'value1835',
    'key76302': 'value43869',
    'key41731': 'value9759',
    'key42891': 'value11857',
    'key48163': 'value93707',
    'key66963': 'value76940',
    'key94767': 'value14762',
},
    {
    'id': 17527492318234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Brendan Ryan',
    'address': '08473 Emily Divide Suite 183\nPort Nathaniel, NY 27165',
    'text': 'How sound social the action. Fact discover national while.\nSignificant result sound player citizen nature. Make lawyer wife real ok. Who daughter while morning.',
    'email': 'burnsedward@example.org',
    'phone_number': '959.940.5452x738',
    'json': {
    'name': 'Kelly White',
    'address': '53653 Lopez Squares\nMatthewland, IN 35638',
},
    'key2673': 'value19631',
},
    {
    'id': 17527492318246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kevin Strickland',
    'address': '2417 Walsh Dam\nWest Ashley, IA 25225',
    'text': 'Focus concern police skill both. Professor its figure much. Ever many government lay system.',
    'email': 'ksmith@example.net',
    'phone_number': '(321)824-0588x6409',
    'json': {
    'name': 'Robert Smith',
    'address': '59823 Donna Squares\nStevensonville, LA 56401',
},
    'key93111': 'value61990',
    'key36786': 'value66917',
    'key74955': 'value54423',
    'key52795': 'value61276',
    'key95882': 'value81705',
    'key31285': 'value39564',
    'key45824': 'value79602',
    'key24934': 'value70236',
    'key6632': 'value7259',
},
    {
    'id': 17527492318256,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Wayne Summers',
    'address': '114 Dustin Courts Suite 174\nLake Tiffany, FM 39629',
    'text': 'Natural student simple feeling stock use company. Travel sister choose always event total moment cut. Ball toward party former.\nMajor green rise push brother his never. Know hour when.',
    'email': 'kcardenas@example.org',
    'phone_number': '6125138235',
    'json': {
    'name': 'John Kirby',
    'address': '9966 Robert Cove\nBrownburgh, PW 97432',
},
    'key26405': 'value76532',
    'key57082': 'value65232',
    'key80177': 'value31304',
    'key14326': 'value46507',
    'key65269': 'value72060',
    'key39137': 'value92810',
    'key86235': 'value48056',
    'key99658': 'value80614',
},
    {
    'id': 17527492318267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Lydia Tucker',
    'address': '108 Burgess Turnpike Apt. 382\nLake Markchester, ME 58409',
    'text': 'Treatment win alone physical responsibility. Nor wide all reflect avoid treat. Ready worker president glass open.',
    'email': 'melanie64@example.org',
    'phone_number': '001-448-250-9249x949',
    'json': {
    'name': 'Jesse Green',
    'address': '386 Zamora Summit\nTapiamouth, PR 26890',
},
    'key92886': 'value80103',
    'key33000': 'value86251',
    'key10341': 'value89180',
    'key23331': 'value47583',
    'key50295': 'value94685',
    'key96287': 'value11724',
    'key21114': 'value67031',
    'key87167': 'value66074',
},
    {
    'id': 17527492318278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'James Cook',
    'address': '652 Peter Branch Apt. 234\nMurphyberg, NJ 15959',
    'text': 'Foreign piece against town improve property. Condition often significant attention.',
    'email': 'robertgraves@example.com',
    'phone_number': '372-394-3725x530',
    'json': {
    'name': 'Alexis Roberts',
    'address': 'PSC 8525, Box 4255\nAPO AA 91896',
},
    'key88038': 'value57850',
    'key7598': 'value70889',
    'key28261': 'value37726',
    'key91976': 'value12272',
    'key56682': 'value86041',
    'key70773': 'value12593',
    'key34996': 'value60046',
    'key3031': 'value38561',
    'key62538': 'value65376',
    'key95933': 'value61039',
},
    {
    'id': 17527492318288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Wayne Smith',
    'address': 'USNS Herrera\nFPO AA 69803',
    'text': 'Protect news reduce yeah Mrs become president. Only career dream social area. Safe four compare letter girl south.',
    'email': 'marcus96@example.org',
    'phone_number': '866.980.6947x689',
    'json': {
    'name': 'James Young',
    'address': '581 Danielle Dam Apt. 978\nHernandezchester, IA 19147',
},
    'key46803': 'value48139',
},
    {
    'id': 17527492318297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Matthew Perez DDS',
    'address': '20983 Bates Islands Suite 941\nCarlachester, CT 63970',
    'text': 'Law available mouth end a. Another nation whose knowledge role sea minute age.\nDegree test total decade move step man. Meeting cost book stand financial teacher want rich.',
    'email': 'markbailey@example.org',
    'phone_number': '(650)421-6164x6616',
    'json': {
    'name': 'Nancy Bailey',
    'address': '5763 Richardson Unions Apt. 164\nStevensonton, OH 95878',
},
    'key4368': 'value1763',
    'key97663': 'value4938',
    'key11682': 'value81031',
    'key19995': 'value32088',
    'key68305': 'value80566',
    'key12914': 'value38646',
    'key7025': 'value93110',
    'key71432': 'value9956',
},
    {
    'id': 17527492318309,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Janice Wilkins',
    'address': '03796 Richard Roads\nWest Christopherside, OK 61677',
    'text': 'Relate meet stuff investment cause consumer use. Anything firm commercial get radio. Voice author create consumer population food quite card.',
    'email': 'joshuaryan@example.net',
    'phone_number': '(291)669-9396x91627',
    'json': {
    'name': 'Mark Shelton',
    'address': '103 Timothy Walk\nNew Michelle, AK 08464',
},
    'key93403': 'value52495',
    'key50438': 'value37979',
    'key96446': 'value98736',
    'key65066': 'value43879',
    'key25427': 'value37436',
    'key60285': 'value49664',
    'key56574': 'value49085',
},
    {
    'id': 17527492318320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Vickie Shea',
    'address': '2531 Everett Port\nSouth Brandonberg, NJ 42489',
    'text': 'Trial candidate sing democratic so reason we.\nOil relationship series probably to. Impact party summer. Help might perhaps.',
    'email': 'vdaniels@example.net',
    'phone_number': '(906)826-1500',
    'json': {
    'name': 'Sean Drake',
    'address': '36284 Kristin Highway\nJenkinston, CA 22454',
},
    'key67310': 'value89830',
    'key94888': 'value77607',
    'key28718': 'value45415',
    'key98129': 'value3928',
    'key21921': 'value79681',
},
    {
    'id': 17527492318331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Douglas Taylor',
    'address': '112 Harper Greens\nNorth Ryanmouth, MA 52400',
    'text': 'Skill street however method hear television include physical. Natural bring table focus. Somebody quite whether task.',
    'email': 'jessica16@example.org',
    'phone_number': '(455)465-4492',
    'json': {
    'name': 'Linda Day',
    'address': '486 Flores Knolls\nFaulknerland, MH 40529',
},
    'key85735': 'value27528',
    'key38573': 'value38090',
    'key44324': 'value2684',
    'key72823': 'value13449',
    'key15905': 'value44307',
},
    {
    'id': 17527492318341,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'William Moore',
    'address': '5002 Stephanie Court\nWest Linda, WI 25938',
    'text': 'From bar according usually. Deep between reality animal involve work not.\nLearn door our teacher catch answer. Rule loss worker kid attention. Herself field rock.',
    'email': 'frankharvey@example.com',
    'phone_number': '(270)278-2448x6113',
    'json': {
    'name': 'Thomas Jackson',
    'address': '64645 Walter Run Suite 407\nCharlesburgh, MH 93181',
},
    'key89742': 'value36905',
},
    {
    'id': 17527492318352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Alan Alexander',
    'address': '5725 Regina Meadows Suite 130\nSalazarfort, OR 62384',
    'text': 'Star way development site. Cell above old old address bit.\nI land whole record. Field fight far media.',
    'email': 'michellestewart@example.net',
    'phone_number': '(244)299-8357x00382',
    'json': {
    'name': 'Jonathan Beard',
    'address': 'PSC 5542, Box 7514\nAPO AE 15035',
},
    'key83606': 'value18911',
    'key98670': 'value65522',
    'key22165': 'value5835',
    'key40733': 'value19136',
    'key37721': 'value33180',
    'key97628': 'value78786',
    'key16188': 'value2101',
    'key5813': 'value85333',
    'key77931': 'value99115',
    'key8337': 'value74782',
},
    {
    'id': 17527492318362,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Thomas Shaffer',
    'address': '83377 Amy Bridge Suite 250\nNorth Jennifer, MO 15390',
    'text': 'Recent work character still throw. Report language step real single pay argue million. Professor city those say international woman.',
    'email': 'fuentessean@example.com',
    'phone_number': '8047146016',
    'json': {
    'name': 'Blake Wilson',
    'address': '28946 Elizabeth Glen Apt. 151\nRodrigueztown, WY 45846',
},
    'key72091': 'value37049',
    'key54128': 'value85337',
    'key24158': 'value89740',
    'key38815': 'value1332',
    'key46365': 'value43531',
    'key22168': 'value57677',
    'key34865': 'value1205',
},
    {
    'id': 17527492318373,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Mark Miller',
    'address': '05538 Wells Rapids Apt. 365\nNew Williammouth, VT 11038',
    'text': 'Bill accept audience charge federal data wear. Everybody say reduce role station floor lawyer. Thought interest or leader realize edge difference.',
    'email': 'jasonhess@example.com',
    'phone_number': '779.776.7503',
    'json': {
    'name': 'Daniel Holmes',
    'address': '5111 Caleb Fields Apt. 165\nPort Heatherland, NC 06024',
},
    'key28887': 'value67981',
    'key44074': 'value62100',
    'key95272': 'value53359',
    'key54715': 'value90997',
    'key62880': 'value58170',
    'key4604': 'value40246',
    'key60408': 'value66875',
},
    {
    'id': 17527492318385,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Mark Rogers',
    'address': '13970 Park Extension\nWest Charlesbury, MP 37054',
    'text': 'Matter spring reflect show improve necessary. Fast side article form.\nEvening single bit process thought member close. Guess man word painting. Structure push decade laugh style home difference.',
    'email': 'kathleen47@example.com',
    'phone_number': '+1-476-333-5119x2256',
    'json': {
    'name': 'Joanna Sellers',
    'address': 'Unit 9779 Box 8214\nDPO AA 91873',
},
    'key37884': 'value89146',
    'key90192': 'value7556',
    'key10269': 'value8988',
    'key74781': 'value99541',
    'key11207': 'value99959',
},
    {
    'id': 17527492318394,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Mark Scott',
    'address': '01292 Olson Lakes\nNew Jenniferhaven, VA 01214',
    'text': 'My effect section house say everybody. When true produce give system Republican. Heart manage herself myself. Establish gas into wish.',
    'email': 'hsanchez@example.com',
    'phone_number': '458.210.9560x2977',
    'json': {
    'name': 'Joseph Barrett',
    'address': '8075 Mendez Manor\nHeatherport, AK 92358',
},
    'key46549': 'value41631',
    'key15587': 'value52965',
    'key4765': 'value62744',
    'key5991': 'value68276',
},
    {
    'id': 17527492318404,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Angela Smith',
    'address': '87156 David Court Suite 361\nBrownton, OH 13492',
    'text': 'Happen whether close small high push. Might garden college night box face check.\nCell machine force every remember. Soldier operation wrong once.',
    'email': 'whenry@example.com',
    'phone_number': '(609)514-4022',
    'json': {
    'name': 'Julian Clark',
    'address': '19465 Adam Stream\nNew Janestad, AS 52437',
},
    'key47867': 'value46681',
    'key7899': 'value33925',
    'key27977': 'value58466',
},
    {
    'id': 17527492318415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Danny Patton',
    'address': '16619 Jackson Radial Suite 901\nCampbellfort, AZ 77559',
    'text': 'Artist require rock herself sister recognize. Himself concern American walk then.',
    'email': 'walshjonathan@example.net',
    'phone_number': '627-795-5035x46638',
    'json': {
    'name': 'Brandon Gutierrez',
    'address': '30941 Kidd Vista\nWest Edward, CA 26390',
},
    'key37621': 'value37406',
    'key77713': 'value11405',
    'key58995': 'value91354',
    'key15928': 'value71770',
    'key50154': 'value34027',
    'key17513': 'value74027',
},
    {
    'id': 17527492318426,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Cynthia Thompson',
    'address': '942 English Island\nCarterburgh, DC 16300',
    'text': 'Likely compare recognize hear assume employee. Spend begin best option.\nCompany land long less. Audience sit hour feel each service. Office director tough go past gun off.',
    'email': 'rwheeler@example.org',
    'phone_number': '(377)711-7448',
    'json': {
    'name': 'Anthony Cox',
    'address': '04739 Sanchez Mews\nRubiochester, IL 30291',
},
    'key291': 'value4630',
    'key6755': 'value63441',
},
    {
    'id': 17527492318437,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'David Ward',
    'address': '18201 Kenneth Stravenue Suite 267\nSouth Nicholas, WY 87091',
    'text': 'Guess whom middle he seven commercial material.\nRegion produce light raise. Second eight audience six.\nDinner laugh degree door. Reality eat receive. Which it relate fast idea choice real there.',
    'email': 'ehernandez@example.com',
    'phone_number': '6533064893',
    'json': {
    'name': 'Joseph Griffin',
    'address': '922 Jonathan Falls Apt. 996\nLynnland, WV 60490',
},
    'key23757': 'value14131',
    'key37189': 'value75883',
    'key91144': 'value27520',
    'key55625': 'value51896',
    'key68543': 'value61277',
    'key18720': 'value86787',
},
    {
    'id': 17527492318448,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Ruth Lawson',
    'address': '63320 Clayton Throughway Suite 795\nJakeville, PA 68821',
    'text': 'Under per cause fire report low. Activity your measure note improve let up place.',
    'email': 'jeremychaney@example.org',
    'phone_number': '387.455.0051',
    'json': {
    'name': 'Steven Peck',
    'address': '3204 Priscilla Brook\nDavidborough, KS 97002',
},
    'key17092': 'value32702',
    'key60146': 'value70497',
},
    {
    'id': 17527492318459,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Bethany Trujillo',
    'address': 'PSC 0952, Box 9289\nAPO AA 47382',
    'text': 'Late something through behavior. Plant between big. Along inside full listen American not.\nShake bed age since. Rather practice speech effort player life mind. Old subject cut world discover.',
    'email': 'hjuarez@example.com',
    'phone_number': '205-305-4443x65909',
    'json': {
    'name': 'Anthony Chavez',
    'address': '87940 Richard Field Apt. 764\nMoorefurt, WV 46118',
},
    'key18328': 'value53236',
    'key32236': 'value57170',
    'key6772': 'value69317',
},
    {
    'id': 17527492318468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'David Castillo',
    'address': '39714 Davis Corners\nMichaelfort, AK 44888',
    'text': 'Power subject get letter involve mention important. Hotel these trouble parent today beat interest. Million animal nothing feel billion may.',
    'email': 'moorejonathan@example.com',
    'phone_number': '864-703-9778x1157',
    'json': {
    'name': 'Michael Mendoza',
    'address': '97054 Joseph Locks\nPort Jeff, NH 66242',
},
    'key76965': 'value70832',
},
    {
    'id': 17527492318479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Brian Miller',
    'address': '89754 Susan Common Apt. 988\nLake Peterton, LA 34985',
    'text': 'Political father report at. Medical report kid. Green soon campaign attack.\nLetter change keep indicate to.\nNow physical attorney create. Peace any wide somebody worker ahead Democrat property.',
    'email': 'paula97@example.org',
    'phone_number': '+1-562-661-2802x47847',
    'json': {
    'name': 'Kristine Torres',
    'address': '0443 Haley Creek\nLake Kennethport, KY 97465',
},
    'key72222': 'value59847',
    'key1089': 'value17724',
    'key71516': 'value56710',
    'key52697': 'value86042',
    'key70198': 'value81118',
    'key63254': 'value54335',
    'key74488': 'value51314',
    'key68556': 'value56945',
    'key71627': 'value17042',
    'key70132': 'value47554',
},
    {
    'id': 17527492318489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Kerry Gibson',
    'address': '0027 Anthony Alley Apt. 856\nFernandezburgh, AL 73099',
    'text': 'Tree kitchen field. Yourself dinner sit name science per teach want. Third government think.',
    'email': 'josephgrant@example.org',
    'phone_number': '001-461-271-7941x985',
    'json': {
    'name': 'Angel Parker',
    'address': '3738 Trevor Knolls Suite 747\nMathewtown, MA 18359',
},
    'key78118': 'value76127',
    'key2787': 'value98009',
    'key66372': 'value68232',
    'key26576': 'value83769',
    'key35970': 'value77885',
},
    {
    'id': 17527492318501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Elizabeth Wheeler',
    'address': '68309 Fitzpatrick Points Apt. 721\nMullinston, MD 76791',
    'text': 'Tv today leave must team particularly hope dark. Left southern writer record. Traditional activity month will. Purpose read line rule tend buy.',
    'email': 'royjuarez@example.net',
    'phone_number': '001-625-409-6173x0084',
    'json': {
    'name': 'Scott Hernandez',
    'address': 'USNS Jordan\nFPO AP 30926',
},
    'key99141': 'value63908',
    'key51773': 'value60331',
    'key73207': 'value12669',
    'key67': 'value90999',
    'key9730': 'value29963',
    'key98963': 'value56260',
    'key55382': 'value85031',
    'key81541': 'value31627',
    'key3106': 'value72962',
},
    {
    'id': 17527492318511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Brandon Palmer',
    'address': '4002 Duncan Green\nGoodmanborough, TN 91248',
    'text': 'Improve answer thank. Cover finish thought better stage away south blue.\nFind development beautiful. Hard social miss expect value positive require.',
    'email': 'sullivandouglas@example.org',
    'phone_number': '(399)799-5289',
    'json': {
    'name': 'Jonathan Barrera',
    'address': '6408 Miller Square Apt. 278\nSouth Danielville, MD 56147',
},
    'key72712': 'value34882',
    'key5961': 'value47806',
    'key69170': 'value78180',
    'key53361': 'value63521',
    'key93873': 'value62414',
    'key49612': 'value55881',
},
    {
    'id': 17527492318523,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Kevin Lamb',
    'address': '80648 Henry Walks Apt. 116\nTaylorchester, VT 09152',
    'text': 'Amount star pass. Guess method without Democrat hold.\nMovie huge protect cut. Pattern baby from field.',
    'email': 'oyoung@example.org',
    'phone_number': '001-877-826-8055x1508',
    'json': {
    'name': 'Jason Hamilton',
    'address': '889 King Passage Suite 601\nLake David, MO 04627',
},
    'key14372': 'value13121',
    'key37583': 'value38605',
},
    {
    'id': 17527492318535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Melvin Gibbs',
    'address': '73197 Christine Crossroad Suite 545\nSouth Tammy, GA 32368',
    'text': 'Fall shoulder miss beyond. Type deep few animal trade six push.\nForward data draw. Manager student son tree. Laugh style parent religious increase.',
    'email': 'kellie60@example.org',
    'phone_number': '862-224-9404',
    'json': {
    'name': 'Nathan Brown',
    'address': '110 Arias Canyon Suite 414\nNorth Michaelaville, HI 19609',
},
    'key1136': 'value55978',
},
    {
    'id': 17527492318545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Elizabeth Tucker',
    'address': '71339 Jackson Tunnel\nNew Marialand, AZ 26384',
    'text': 'Wall too still white impact nor. Movement subject run. Prevent improve field watch wonder. Fund radio save reach world.\nNation matter wait radio man. Development mean last ask strong.',
    'email': 'jeanette86@example.net',
    'phone_number': '554-562-1172',
    'json': {
    'name': 'Andrew Osborne',
    'address': 'USNV Schultz\nFPO AA 71925',
},
    'key65515': 'value14384',
    'key97326': 'value65676',
    'key14820': 'value75540',
    'key25922': 'value45101',
    'key74172': 'value6314',
    'key63871': 'value84125',
    'key68702': 'value79696',
},
    {
    'id': 17527492318555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Kimberly Rogers',
    'address': '011 Myers Harbor\nNathanielchester, VA 48386',
    'text': 'Rate source throughout research example face.\nLeg call authority range. Unit away both hospital that recent population thing.',
    'email': 'rreynolds@example.com',
    'phone_number': '376.476.7206x4693',
    'json': {
    'name': 'Brenda Oliver',
    'address': '680 Misty Spur Apt. 589\nClintontown, IN 62874',
},
    'key19604': 'value60239',
    'key95044': 'value91905',
    'key43605': 'value83038',
},
    {
    'id': 17527492318565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Christie Castro',
    'address': '7385 Samantha Manor\nNew Jessicafurt, IN 67048',
    'text': 'Of partner political friend feeling. Between soldier leave relate into former expert.\nEat surface they image. Book seven fast measure statement mouth. Away free speak reason recently name fund.',
    'email': 'stuart02@example.org',
    'phone_number': '(221)677-6087',
    'json': {
    'name': 'Kari Lopez',
    'address': '2231 Shannon Centers Apt. 455\nNew Johnshire, DC 40745',
},
    'key7620': 'value3392',
    'key61999': 'value91735',
    'key33767': 'value18792',
    'key95590': 'value70148',
},
    {
    'id': 17527492318575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Aaron Smith',
    'address': '5574 Montgomery Drives\nMoniqueville, MH 98336',
    'text': 'Value once employee friend improve official. Full impact get whole.\nWhich moment summer seat. Break research other instead wish machine under. Accept southern all check to choose although.',
    'email': 'turnerleslie@example.org',
    'phone_number': '238-671-7073x6511',
    'json': {
    'name': 'Jose Paul',
    'address': '9052 Leon Fords Apt. 696\nAdamstad, NY 03629',
},
    'key36307': 'value29262',
},
    {
    'id': 17527492318586,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Joshua Meyer',
    'address': '9602 Gabriel Mission Suite 421\nSchroederberg, MP 59712',
    'text': 'Among me able kitchen everybody. Attorney your it work add on. Able high word special.\nEvidence shake rather room.',
    'email': 'crobinson@example.com',
    'phone_number': '+1-964-364-7851x2404',
    'json': {
    'name': 'Jerry Love',
    'address': '679 Pierce Creek Suite 336\nGlennshire, RI 05920',
},
    'key87418': 'value95816',
    'key83658': 'value44895',
},
    {
    'id': 17527492318597,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Cheryl Park',
    'address': '4510 Sarah Station Apt. 013\nNew Carol, WV 86177',
    'text': 'Air hard minute current voice here one. Culture song paper new forget for better feel.\nBe instead information remain hot.',
    'email': 'lmeyer@example.com',
    'phone_number': '398.765.9233',
    'json': {
    'name': 'Stacy Lyons',
    'address': 'Unit 3850 Box 6742\nDPO AA 19533',
},
    'key50468': 'value43884',
    'key54896': 'value49502',
    'key5692': 'value88633',
    'key80408': 'value46638',
    'key9833': 'value63911',
    'key7710': 'value22329',
    'key86129': 'value34644',
    'key72767': 'value17312',
},
    {
    'id': 17527492318606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Trevor Gutierrez',
    'address': '8083 Finley Ford Apt. 157\nBrownport, RI 68012',
    'text': 'Per half program rule business. Find impact sure brother perform.\nTechnology worker society million. Possible medical itself establish quickly.',
    'email': 'gonzaleznancy@example.org',
    'phone_number': '(316)533-0564x39009',
    'json': {
    'name': 'Keith Wallace',
    'address': '02987 Steven Junctions Apt. 176\nLake Ginafurt, RI 35115',
},
    'key67540': 'value20087',
    'key72597': 'value43455',
},
    {
    'id': 17527492318617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Courtney Simpson',
    'address': '003 Juan Plains\nFlowersland, VT 93740',
    'text': 'Among security first system wife later. Consumer trial executive defense its.',
    'email': 'nathaniel58@example.net',
    'phone_number': '798-312-6483x2706',
    'json': {
    'name': 'Rickey Cooke',
    'address': '597 Tara Terrace Suite 762\nLake Williamstad, UT 02092',
},
    'key32204': 'value95043',
    'key35158': 'value43211',
    'key38921': 'value15080',
    'key90423': 'value22386',
},
    {
    'id': 17527492318627,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Johnny Cole',
    'address': '256 Austin Port Apt. 772\nGrahammouth, HI 64048',
    'text': 'National reveal affect really service.\nTop yet dream expert. Stuff Mr hot fund. Peace option mind thing million study.',
    'email': 'alyssa88@example.net',
    'phone_number': '+1-789-530-0320',
    'json': {
    'name': 'Christopher Matthews',
    'address': '79535 John Causeway\nEast Danielview, KY 17124',
},
    'key41277': 'value61290',
    'key61524': 'value12569',
},
    {
    'id': 17527492318638,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Angela Turner',
    'address': '502 Daniel Brook\nDianebury, WA 12318',
    'text': 'Behavior memory help design. Different case hundred attack traditional ten set. Who continue after discover.\nBoard billion sound opportunity.\nInclude we join player central citizen type experience.',
    'email': 'qforbes@example.com',
    'phone_number': '807.912.7735x02213',
    'json': {
    'name': 'Kaitlin Leon',
    'address': '55164 Sherry Trail\nNorth Toddfurt, MD 10680',
},
    'key16326': 'value55710',
    'key51067': 'value78142',
    'key36142': 'value69206',
},
    {
    'id': 17527492318648,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Allen Shields',
    'address': '0632 Cain Center Suite 996\nLake Catherine, AK 07380',
    'text': 'Suffer off argue likely next above performance. Image child some. Choose Mr home town.\nEver friend single fund. Senior third minute stand sign.',
    'email': 'thenderson@example.org',
    'phone_number': '8866016497',
    'json': {
    'name': 'Crystal Jones',
    'address': '63832 Kimberly Ways\nGregorybury, SD 21624',
},
    'key82646': 'value38499',
    'key10848': 'value79900',
},
    {
    'id': 17527492318659,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Chad Leach',
    'address': '32815 Carl Crossing\nPaulside, NV 11753',
    'text': 'Hard process hand style. Reason prepare garden name someone wrong kitchen believe. Prove point current me challenge build top.',
    'email': 'francislaurie@example.net',
    'phone_number': '(381)665-6746x6464',
    'json': {
    'name': 'Shannon Stanton',
    'address': '5026 Harmon Loaf Suite 060\nWest Nathan, WY 95733',
},
    'key55245': 'value78644',
    'key67476': 'value5836',
    'key38128': 'value26014',
    'key26092': 'value59111',
    'key40907': 'value83573',
    'key2685': 'value54476',
    'key55481': 'value63344',
    'key20634': 'value12748',
},
    {
    'id': 17527492318670,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Heather Hampton',
    'address': '57525 Victoria Courts Apt. 401\nMichaelville, VA 15077',
    'text': 'Individual tell property perform street run. Push how set class town. Believe dog sister decade.',
    'email': 'srobinson@example.com',
    'phone_number': '905.506.7390x07742',
    'json': {
    'name': 'Jason Hall',
    'address': '3876 Christian Parks\nGonzalezport, MO 43508',
},
    'key55385': 'value56296',
    'key21562': 'value10730',
    'key80767': 'value30097',
    'key14938': 'value13986',
    'key27967': 'value23558',
    'key52009': 'value57601',
    'key80765': 'value39377',
    'key37301': 'value44353',
    'key45384': 'value88343',
    'key79395': 'value563',
},
    {
    'id': 17527492318681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Monica Hampton PhD',
    'address': '022 Patricia Expressway\nPort Richardmouth, DE 57405',
    'text': 'Ball leave keep provide religious father. Then concern administration finish federal occur.',
    'email': 'phillipscharles@example.org',
    'phone_number': '739.843.5256',
    'json': {
    'name': 'Jeffrey Roberts',
    'address': '5207 James Lane\nEricksonmouth, AZ 43587',
},
    'key62904': 'value47402',
    'key31215': 'value57993',
    'key422': 'value42100',
    'key77420': 'value27251',
    'key87127': 'value64829',
    'key61377': 'value14787',
    'key57620': 'value2672',
    'key24446': 'value70670',
    'key35584': 'value49912',
},
    {
    'id': 17527492318693,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Patrick Thompson',
    'address': '84934 Lee Prairie\nRobertstown, KY 94914',
    'text': 'Across partner toward economic. Major yet our left son stop.\nThemselves ahead thousand. Image two long myself. Writer they player ready hope. Deep hospital beyond hope piece through.',
    'email': 'terryjack@example.org',
    'phone_number': '850-814-7812x27058',
    'json': {
    'name': 'Joshua Haley',
    'address': '11601 Davis Mission Suite 005\nLake Kimberly, MA 99772',
},
    'key76949': 'value83330',
    'key18280': 'value55575',
    'key67437': 'value95858',
    'key16706': 'value98209',
    'key98566': 'value34589',
    'key6182': 'value68577',
    'key38430': 'value13379',
    'key1077': 'value94107',
},
    {
    'id': 17527492318705,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Ryan Guerrero',
    'address': '18352 Fischer Rapid\nNew Chad, NV 83177',
    'text': 'Whatever Democrat get note father. Should community those exist baby like often evening.\nOr fact beautiful claim idea across. Determine image standard agency design task fish local.',
    'email': 'qsimmons@example.net',
    'phone_number': '599-903-8307',
    'json': {
    'name': 'David Wright',
    'address': '013 Malone Curve Suite 683\nNorth Michealchester, ND 01803',
},
    'key77379': 'value97095',
},
    {
    'id': 17527492318715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Jesse Brewer',
    'address': '027 Lisa Rapid\nEast Kerryshire, ID 34999',
    'text': 'Very system night someone issue coach. Popular crime picture modern stand. Require whole but pull long detail.',
    'email': 'luisroberts@example.org',
    'phone_number': '(676)668-4992x96970',
    'json': {
    'name': 'Richard Coleman',
    'address': 'USNS Mitchell\nFPO AA 28909',
},
    'key85846': 'value5185',
    'key63054': 'value10284',
    'key31216': 'value19609',
    'key53434': 'value94577',
    'key31922': 'value60652',
    'key29487': 'value35376',
},
    {
    'id': 17527492318725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Amy White',
    'address': '4176 Megan Junctions Suite 124\nWest Deanna, FL 71064',
    'text': 'Away dream all out work entire future. Join then require be protect eight.\nAsk argue painting expect room successful. Suffer cut good practice source continue financial. Consumer positive daughter.',
    'email': 'espinozadavid@example.net',
    'phone_number': '(405)757-1983x47111',
    'json': {
    'name': 'Peter Carter',
    'address': '640 Griffin Path\nDanielleville, WV 70303',
},
    'key64959': 'value24473',
},
    {
    'id': 17527492318736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'James Mccarthy',
    'address': '3677 Jones Ranch Suite 967\nEast Sonyafort, ND 34666',
    'text': 'Thus across west turn PM play expect. Never like wish scientist entire simple forward.\nWeek first nor turn but including light. Case wait image must tend only support voice.',
    'email': 'kristymay@example.net',
    'phone_number': '793-523-2753x40983',
    'json': {
    'name': 'Peter Smith',
    'address': '64197 Kimberly Centers Apt. 793\nChristopherhaven, AR 39751',
},
    'key34583': 'value92892',
    'key41176': 'value50766',
    'key25845': 'value99235',
},
    {
    'id': 17527492318747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Stephanie Olson',
    'address': 'PSC 8355, Box 6789\nAPO AE 63767',
    'text': 'Say common try best. Force or security economic. Theory owner listen performance statement. Might quite computer lose factor gun this.',
    'email': 'jonesgarrett@example.org',
    'phone_number': '6782502337',
    'json': {
    'name': 'Brittany Lopez',
    'address': '701 Richard Pass\nHughesport, PW 37464',
},
    'key3177': 'value33591',
    'key28724': 'value60104',
    'key16133': 'value28715',
    'key32502': 'value59183',
    'key5422': 'value11856',
    'key70969': 'value65891',
    'key24693': 'value33321',
},
    {
    'id': 17527492318757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Amy Sanchez',
    'address': '34417 Whitney Ramp Suite 226\nJustinchester, MA 88906',
    'text': 'Traditional senior every edge dark. Price pay degree skin.\nThird prevent clear rule. Conference technology born short marriage. Course establish accept.',
    'email': 'christopherbarrett@example.com',
    'phone_number': '203.832.1106x90721',
    'json': {
    'name': 'Brian Barrett',
    'address': '029 Woods Inlet Apt. 026\nNorth Melissafurt, TN 93135',
},
    'key23305': 'value32972',
    'key82338': 'value46782',
    'key87112': 'value25118',
    'key80351': 'value1074',
    'key13928': 'value91911',
    'key36132': 'value34574',
},
    {
    'id': 17527492318768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Jennifer Moody',
    'address': '0435 Stephens Mills\nPort John, MD 65338',
    'text': 'Social food first discussion gas development forget language. Finally such suffer ability lose. Hold red feel what.',
    'email': 'samanthapope@example.org',
    'phone_number': '+1-680-928-4893x61687',
    'json': {
    'name': 'Jonathan Klein',
    'address': '27049 Kevin Freeway Suite 324\nEast Joshuaborough, OH 82637',
},
    'key27330': 'value27631',
    'key20805': 'value18500',
    'key47871': 'value50870',
    'key23975': 'value90305',
    'key60831': 'value52658',
    'key86502': 'value85438',
    'key54673': 'value99999',
    'key73213': 'value85097',
},
    {
    'id': 17527492318779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Christopher Bush',
    'address': '0983 Michele Ridge\nDouglashaven, PW 26058',
    'text': 'Name agent fish trouble. Born interesting shoulder full again role tough body.\nGet record professional fine. Business great once. Page there something popular.',
    'email': 'wheelerbrittany@example.org',
    'phone_number': '001-339-852-4189',
    'json': {
    'name': 'James Jordan PhD',
    'address': '585 Joseph Mountains Suite 836\nPatriciaton, WV 77145',
},
    'key24255': 'value94309',
    'key58341': 'value33144',
},
    {
    'id': 17527492318791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Jacqueline Hernandez',
    'address': '885 Amanda Island\nPort Stacyfurt, MT 92312',
    'text': 'Investment effect decision stock future pass. Town write laugh sit end statement letter act.\nLike nor after. Happen current source well development western. Strong gas pressure natural half.',
    'email': 'connie62@example.com',
    'phone_number': '623.733.4491x14470',
    'json': {
    'name': 'Martha Diaz',
    'address': '5551 Harmon Viaduct Apt. 294\nLake Christopherburgh, TX 38617',
},
    'key56227': 'value38514',
    'key14716': 'value14845',
},
    {
    'id': 17527492318801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Kyle Payne',
    'address': '190 Chad Row Apt. 216\nWest Janice, MD 69892',
    'text': 'Reduce system rise property daughter. Business serve seem. Face turn stock arrive develop.',
    'email': 'njohnson@example.org',
    'phone_number': '7467322433',
    'json': {
    'name': 'Keith Campbell',
    'address': 'USNS Cook\nFPO AP 55054',
},
    'key7575': 'value2540',
    'key94997': 'value11400',
    'key39323': 'value58439',
    'key73437': 'value52920',
    'key92029': 'value73784',
    'key38254': 'value12564',
    'key14952': 'value22193',
    'key50085': 'value33463',
},
    {
    'id': 17527492318810,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Dorothy Duffy',
    'address': '243 Ricky Isle\nPort Laurafurt, NY 77812',
    'text': 'Yard example itself. Bank item you sense happen. Under enjoy light hair hospital size.',
    'email': 'christopher45@example.com',
    'phone_number': '7528871987',
    'json': {
    'name': 'Christopher Leach',
    'address': '7509 Watkins Forest\nValdezmouth, MP 46099',
},
    'key94588': 'value54173',
    'key25694': 'value70876',
    'key64285': 'value14261',
},
    {
    'id': 17527492318821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Wendy Vang',
    'address': '79330 John Parkway Suite 181\nArnoldburgh, AS 18494',
    'text': 'Explain section bring teach than dream common. Detail candidate dream many. Future join just despite everything pattern sure.',
    'email': 'lauraosborne@example.net',
    'phone_number': '530.685.0417x0563',
    'json': {
    'name': 'Emily Woods',
    'address': '50241 Mayer Radial Apt. 368\nEast Levifort, PR 28772',
},
    'key66312': 'value8117',
    'key38639': 'value88627',
    'key32905': 'value39906',
    'key21935': 'value90458',
    'key12612': 'value27987',
    'key1020': 'value40303',
    'key35060': 'value74574',
},
    {
    'id': 17527492318832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Isaac Walter',
    'address': 'Unit 3613 Box 8856\nDPO AP 95519',
    'text': 'Reduce too environmental wonder difference. Against visit sister their operation reality explain. As need hear glass page management light.',
    'email': 'christineyoung@example.net',
    'phone_number': '694.958.3026',
    'json': {
    'name': 'Edward Rosales',
    'address': '12292 Deborah Tunnel\nShannonmouth, CO 58964',
},
    'key40912': 'value27001',
    'key81161': 'value20111',
},
    {
    'id': 17527492318841,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Mitchell Fry',
    'address': '20374 Jennifer Turnpike\nEast Ronaldside, AR 72437',
    'text': 'Space poor worry teacher spend quality. Whom build scientist.\nInvolve up color simply her himself ten. Right husband foreign language surface occur.',
    'email': 'michael33@example.com',
    'phone_number': '+1-948-715-5926x43353',
    'json': {
    'name': 'Donald Sanders',
    'address': '20399 Matthew Lakes Apt. 253\nPort Michaelbury, WY 06310',
},
    'key53285': 'value84385',
    'key72075': 'value1709',
    'key45616': 'value28397',
},
    {
    'id': 17527492318851,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Nicole Stokes',
    'address': '9197 Gregory Fords\nPort Jamesstad, PA 96271',
    'text': 'Several operation purpose agent. Be win available news actually seat force.\nAppear truth agree son bed national hair would. Process strong student. Whether care participant our option true.',
    'email': 'jamesadams@example.com',
    'phone_number': '(947)203-2191',
    'json': {
    'name': 'Jennifer Graham',
    'address': '21802 Nathaniel Causeway Apt. 428\nNew William, WA 95426',
},
    'key88531': 'value95926',
    'key62734': 'value55440',
    'key54558': 'value59036',
    'key90832': 'value3557',
},
    {
    'id': 17527492318863,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Sandra Jackson',
    'address': '168 Raymond Ports\nHunterchester, ME 42609',
    'text': 'Then fire condition those American address available. Doctor thousand matter Republican into tough parent position.\nAlone final born. Responsibility bit city contain.',
    'email': 'jeremychavez@example.net',
    'phone_number': '6775051646',
    'json': {
    'name': 'Michael Hernandez',
    'address': '882 Soto Heights\nWest Christina, ME 41300',
},
    'key75701': 'value9989',
    'key43810': 'value21730',
    'key7091': 'value34204',
    'key16911': 'value87',
},
    {
    'id': 17527492318873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Anthony Walker',
    'address': '83672 Christopher Valley\nSullivanport, FM 75957',
    'text': 'Make above treatment network several. Whatever check alone pressure line edge stage fight.\nLife star whether arm recently. Everyone build so young number protect.',
    'email': 'kiararoy@example.com',
    'phone_number': '693-893-4303',
    'json': {
    'name': 'Beth Gomez',
    'address': '1068 Hill Estate Apt. 097\nNew Heatherburgh, NM 40188',
},
    'key82762': 'value78592',
    'key78667': 'value46274',
    'key47379': 'value38283',
    'key96368': 'value95002',
    'key59605': 'value91008',
},
    {
    'id': 17527492318885,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Ashley Hunter',
    'address': '761 Allison Trail\nNataliefort, AK 77410',
    'text': 'Help base agreement TV affect better. Hundred only somebody product put. Sit director last section day evening political.',
    'email': 'lisa94@example.org',
    'phone_number': '(637)264-8017',
    'json': {
    'name': 'Brandy Garcia',
    'address': '55598 Jacob Turnpike Apt. 684\nEast Cindy, NC 65144',
},
    'key69016': 'value86662',
    'key52443': 'value71103',
},
    {
    'id': 17527492318895,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'David Smith',
    'address': '5626 Cynthia Drives\nShaneburgh, GU 74942',
    'text': 'Impact commercial action. Herself difference provide more brother teach business. Financial third four range return take.',
    'email': 'upeterson@example.com',
    'phone_number': '+1-206-748-0572',
    'json': {
    'name': 'Lee Williams',
    'address': '249 Shannon Groves Suite 278\nTanyahaven, TN 11877',
},
    'key62578': 'value38542',
    'key82925': 'value44497',
    'key74757': 'value18080',
    'key53898': 'value47844',
    'key8946': 'value89303',
    'key10910': 'value22313',
    'key31058': 'value62872',
    'key92028': 'value14282',
    'key93707': 'value2509',
    'key19823': 'value27542',
},
    {
    'id': 17527492318905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Brian Cooper',
    'address': 'PSC 6009, Box 1209\nAPO AE 64171',
    'text': 'Central few describe evidence represent.\nA open everyone suddenly court effect.\nTake determine around research now high interesting.',
    'email': 'ruizpamela@example.net',
    'phone_number': '(761)795-2634x23809',
    'json': {
    'name': 'Jennifer Farley',
    'address': '9593 Dale Valleys Apt. 260\nSouth Lauraside, WV 01214',
},
    'key33145': 'value61633',
    'key12623': 'value96111',
    'key7913': 'value1613',
    'key83869': 'value40158',
    'key63239': 'value62050',
    'key85596': 'value61444',
},
    {
    'id': 17527492318914,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Heather Boyle',
    'address': '16216 Katherine Isle\nSouth Johnborough, UT 38608',
    'text': 'Fact teacher although professional. Raise fact traditional week worker beautiful act. Fast role particularly beautiful take bad include.\nHelp second every poor true should economic subject.',
    'email': 'nicholasrodgers@example.org',
    'phone_number': '(903)900-0397',
    'json': {
    'name': 'Brian Wood',
    'address': '77582 Campbell Throughway\nCruzfort, VI 41408',
},
    'key36119': 'value7858',
    'key55318': 'value33036',
    'key36903': 'value22032',
    'key37209': 'value78578',
    'key37215': 'value49643',
    'key48826': 'value96968',
    'key64323': 'value40064',
    'key43422': 'value53897',
},
    {
    'id': 17527492318925,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'John Smith',
    'address': '21802 Fisher Curve\nPort Nicole, NE 82180',
    'text': 'Second admit more believe plant history in some. Significant wide friend guess nature both Mr. Say speak determine which.',
    'email': 'sandra11@example.com',
    'phone_number': '001-742-771-5532x2871',
    'json': {
    'name': 'Melissa Wang',
    'address': '4829 Thompson Islands\nLake Olivia, AS 65863',
},
    'key31021': 'value79318',
    'key81504': 'value18382',
    'key43461': 'value35673',
    'key56596': 'value24445',
    'key73020': 'value79739',
    'key98876': 'value48685',
    'key74692': 'value86579',
    'key44330': 'value7980',
    'key85928': 'value68207',
    'key62395': 'value63890',
},
    {
    'id': 17527492318936,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Adrian Gross',
    'address': '9273 Anthony Vista Suite 128\nRileyton, IL 46845',
    'text': 'Senior ability win move throw. Floor threat least yeah peace. Majority also Mrs food idea everyone move.',
    'email': 'montgomeryanthony@example.com',
    'phone_number': '001-524-878-3725x696',
    'json': {
    'name': 'Michael Gardner',
    'address': '735 Hall Shoals\nNew Kristenburgh, IL 10898',
},
    'key20406': 'value56529',
    'key66262': 'value1523',
},
    {
    'id': 17527492318948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Lucas Rodriguez',
    'address': '1381 Randy Highway Apt. 282\nLake Christopher, AZ 84339',
    'text': 'Technology spend include nearly every.\nProduct eye discover argue third evidence.\nSense six they politics drive some camera. Help produce serve above my hotel. I minute sound fill teach author.',
    'email': 'michelle11@example.net',
    'phone_number': '907-783-1144',
    'json': {
    'name': 'Cody Hill',
    'address': '9251 Valenzuela Courts\nLake Jennifer, PR 61402',
},
    'key76100': 'value34707',
    'key33511': 'value98568',
    'key47897': 'value9577',
    'key87802': 'value41282',
    'key60724': 'value96302',
    'key83284': 'value20293',
},
    {
    'id': 17527492318958,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Jennifer Smith',
    'address': '1332 Tanya Ways\nMichaelville, WV 31341',
    'text': 'Speak road lose street difficult eye affect. Series rate brother throughout occur. President staff foot charge month husband control. Street college floor will.',
    'email': 'johnsmary@example.org',
    'phone_number': '412.217.1717x7643',
    'json': {
    'name': 'Mark Nguyen',
    'address': '611 Cynthia Lights Apt. 118\nEast Jason, PA 60962',
},
    'key76807': 'value41477',
    'key39322': 'value94301',
    'key4312': 'value93606',
    'key84830': 'value16301',
    'key43926': 'value66597',
    'key14468': 'value34908',
    'key90453': 'value97259',
    'key26840': 'value24943',
},
    {
    'id': 17527492318969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Christine Clark',
    'address': '88571 Michael Wall Apt. 876\nPort Russellmouth, ID 73114',
    'text': 'Community significant listen this data. Argue box once begin.\nThink upon board candidate season style. Cause catch season success position.',
    'email': 'christopher53@example.com',
    'phone_number': '293-993-4319',
    'json': {
    'name': 'Melissa Myers',
    'address': '57128 Becker Light\nEast Kaitlyn, NH 23585',
},
    'key21801': 'value83727',
    'key9696': 'value85281',
    'key14734': 'value25773',
    'key55783': 'value73527',
    'key91004': 'value21205',
    'key45020': 'value52647',
},
    {
    'id': 17527492318979,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Joanne Hensley',
    'address': '98869 Johnston Plains Apt. 359\nLake Joshua, LA 31496',
    'text': 'Information hair growth give. White show draw land whose account ago. Sit always couple likely cause.\nShoulder source opportunity employee. Look most bag social open dark animal body.',
    'email': 'weissjennifer@example.org',
    'phone_number': '343.453.7452x09304',
    'json': {
    'name': 'Robert Sandoval',
    'address': '5151 Crane Glens Suite 747\nLake Renee, MT 30145',
},
    'key99573': 'value52488',
    'key55199': 'value9023',
    'key87074': 'value69759',
},
    {
    'id': 17527492318991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Riley Sherman',
    'address': '395 Bernard Heights\nNorth Lauren, SD 33787',
    'text': 'Cut spring treat modern evidence several. Role often north design interest how fund. Series them special relate arrive defense.',
    'email': 'keithhill@example.net',
    'phone_number': '001-230-570-6601',
    'json': {
    'name': 'Sara Jimenez',
    'address': 'Unit 7042 Box 6830\nDPO AA 98894',
},
    'key45167': 'value61696',
    'key80769': 'value16034',
    'key10834': 'value38103',
    'key42029': 'value86935',
    'key13141': 'value65971',
    'key90813': 'value51912',
    'key51328': 'value24356',
},
    {
    'id': 17527492319000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Thomas Flynn',
    'address': 'USNV Williams\nFPO AA 01629',
    'text': 'Throw ever I later born. Door around meet season.\nVery simply enough interest account. Exist bank language create. Assume organization environment look.\nWater defense product however natural.',
    'email': 'kimberly59@example.com',
    'phone_number': '+1-781-341-8995',
    'json': {
    'name': 'Matthew Brooks',
    'address': '137 Connor Island Apt. 932\nChristopherborough, WV 44177',
},
    'key16258': 'value14433',
    'key21963': 'value1393',
    'key8192': 'value26911',
},
    {
    'id': 17527492319009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Timothy Miller',
    'address': 'USS Williams\nFPO AE 20735',
    'text': 'Foot or go protect. Not half subject them year special forward. Side operation chair feel where foot the.\nMind best fight wife choose. Idea western physical.',
    'email': 'destiny71@example.org',
    'phone_number': '298-620-0181',
    'json': {
    'name': 'Christopher Chavez',
    'address': '515 Frey Creek\nVeronicaside, NE 62539',
},
    'key18893': 'value17880',
    'key26250': 'value97975',
    'key72973': 'value34868',
    'key56879': 'value5669',
    'key92881': 'value31227',
    'key43438': 'value76596',
    'key91513': 'value654',
    'key36684': 'value49071',
    'key73077': 'value45153',
    'key84615': 'value25659',
},
    {
    'id': 17527492319018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Mario Marks',
    'address': '9987 James Club Suite 314\nNorth Ruthmouth, OH 59102',
    'text': 'Risk response either media remember finally theory. Plan green economic participant mind. Fish capital suddenly focus. Culture rock reach major simple ability me.',
    'email': 'ocraig@example.org',
    'phone_number': '974.676.1248x067',
    'json': {
    'name': 'Paul Small',
    'address': 'Unit 5576 Box 1168\nDPO AE 79848',
},
    'key88944': 'value91767',
    'key64347': 'value45068',
    'key86046': 'value11642',
},
    {
    'id': 17527492319027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Debra Sanders',
    'address': '12188 Elizabeth Heights\nMaryburgh, VT 40174',
    'text': 'Marriage heart push performance act. Member professor low west floor article usually.',
    'email': 'yjackson@example.net',
    'phone_number': '001-712-586-2159',
    'json': {
    'name': 'Frank Floyd',
    'address': '319 Lin Cliffs\nMartinezview, VI 08587',
},
    'key22869': 'value20516',
    'key90042': 'value88271',
    'key47946': 'value46327',
    'key20649': 'value41977',
},
    {
    'id': 17527492319037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Matthew Williams',
    'address': 'USNV Dorsey\nFPO AA 14521',
    'text': 'Plant scene class nation industry opportunity role. Now nearly note again. Determine there near help. Mr final eat gas senior they.',
    'email': 'aliciamiller@example.net',
    'phone_number': '(875)729-6491',
    'json': {
    'name': 'Jacqueline Williams',
    'address': '826 Danielle Creek\nHarrishaven, FL 04966',
},
    'key54410': 'value68462',
    'key74734': 'value17246',
    'key73041': 'value70200',
    'key11239': 'value84473',
},
    {
    'id': 17527492319047,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Judy Davis',
    'address': '71118 Davis Plaza Suite 244\nRobertport, AS 45071',
    'text': 'Language president offer paper parent type author. House never cover.\nSomeone together modern training follow offer main. Local who threat specific available form.',
    'email': 'hughesbenjamin@example.org',
    'phone_number': '744.384.3214x97932',
    'json': {
    'name': 'Luke Barron',
    'address': '084 Theodore Glen Suite 280\nRobertsville, MA 59181',
},
    'key55011': 'value83662',
},
    {
    'id': 17527492319059,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Grace Meyer',
    'address': '06464 Molly Landing Suite 402\nSouth Matthewburgh, MA 45192',
    'text': 'Own cover whatever want. Consumer material argue cut while sea trouble accept. Provide really fall defense money management consumer.',
    'email': 'emurphy@example.com',
    'phone_number': '639.451.7950',
    'json': {
    'name': 'Erin Douglas',
    'address': '548 Hernandez Cove\nNew Williestad, NE 59950',
},
    'key28987': 'value73576',
    'key14803': 'value1268',
    'key56347': 'value86902',
    'key58624': 'value79434',
    'key41489': 'value47764',
    'key80493': 'value26186',
},
    {
    'id': 17527492319070,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Robert Gonzales',
    'address': '1059 Rodgers Via\nPort Hannahmouth, PA 84706',
    'text': 'Building start number stock not tell her bar. History walk compare fire.\nAppear indicate resource draw PM second build. Forward message action power.',
    'email': 'deanlaura@example.com',
    'phone_number': '5634801499',
    'json': {
    'name': 'Craig Fox',
    'address': '6833 Joseph Plains\nLopezhaven, VI 74432',
},
    'key39539': 'value73799',
    'key67750': 'value76562',
    'key62718': 'value26322',
    'key18725': 'value10804',
    'key33864': 'value93283',
    'key80209': 'value61721',
    'key96796': 'value36914',
    'key23674': 'value52804',
},
    {
    'id': 17527492319081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Mary Johnson',
    'address': '60897 Elizabeth Lodge Apt. 223\nPort Larry, DC 69076',
    'text': 'Suddenly since level any notice own land. Store sometimes mean join.\nArt bed particularly report admit. Friend establish time future.',
    'email': 'aprilthompson@example.net',
    'phone_number': '(447)501-2803',
    'json': {
    'name': 'Darryl Mcmillan',
    'address': '5188 Moore Loaf Apt. 105\nWest Nicolehaven, NE 32627',
},
    'key1835': 'value84799',
    'key74263': 'value72779',
    'key21864': 'value69715',
    'key21368': 'value71521',
    'key8909': 'value54185',
    'key7994': 'value45795',
    'key18720': 'value32163',
},
    {
    'id': 17527492319093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Rachael Frazier',
    'address': '936 Johnson Islands Apt. 375\nLake Tammy, KY 86943',
    'text': 'Speak then name produce benefit couple foot. Summer father law Congress blue personal senior smile.',
    'email': 'rdavis@example.net',
    'phone_number': '3742278511',
    'json': {
    'name': 'Emily Reynolds',
    'address': 'PSC 4642, Box 1273\nAPO AA 82434',
},
    'key9505': 'value7268',
    'key93007': 'value23527',
    'key26662': 'value60975',
    'key7876': 'value99492',
    'key98716': 'value91860',
    'key89963': 'value13828',
    'key98888': 'value35795',
    'key89252': 'value21499',
    'key53464': 'value19101',
    'key794': 'value12585',
},
    {
    'id': 17527492319102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Matthew Davis',
    'address': '78613 Graham Forge Apt. 304\nCynthiachester, CO 47266',
    'text': 'Expert no business nearly. Truth every environment politics.\nLanguage it meet whose however. Reach good line from who until what.',
    'email': 'thompsonjason@example.org',
    'phone_number': '242.952.6557x56141',
    'json': {
    'name': 'James Marquez',
    'address': '92396 Nunez Wall\nPort Juan, PA 17960',
},
    'key84695': 'value95304',
    'key18546': 'value63808',
    'key78315': 'value64807',
    'key39789': 'value47168',
},
    {
    'id': 17527492319113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Dr. Gregory Miller',
    'address': 'USCGC Zamora\nFPO AP 06117',
    'text': 'True book including another. Spring collection successful probably hour money knowledge.',
    'email': 'sboyd@example.org',
    'phone_number': '749.247.5324',
    'json': {
    'name': 'Kenneth Miller',
    'address': '4956 Travis Ridge Suite 502\nPort Craig, SD 21710',
},
    'key97791': 'value41842',
    'key19377': 'value62766',
    'key63194': 'value4891',
    'key41425': 'value68636',
    'key38982': 'value96563',
    'key95694': 'value29248',
    'key75078': 'value62227',
    'key86433': 'value85551',
    'key91580': 'value63499',
    'key92203': 'value20971',
},
    {
    'id': 17527492319122,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Jeff Patrick',
    'address': '861 Daniel Ports\nKingshire, AS 22462',
    'text': 'Owner catch deep. All while not TV plan behavior even.\nSell leg city by social. Each board production wonder until ahead field day. Let house improve throw green career. The one full their economy.',
    'email': 'eduncan@example.org',
    'phone_number': '+1-977-393-2096',
    'json': {
    'name': 'Christopher Frost',
    'address': '016 Nancy Crossroad Suite 276\nLake Leslie, MP 74103',
},
    'key65594': 'value30398',
    'key48229': 'value56465',
},
    {
    'id': 17527492319132,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Mario Wagner',
    'address': '206 Amy Forks Suite 698\nNancyberg, CT 78271',
    'text': 'Gun need morning plant range environmental. Everything voice thus can history real.\nAttack suffer system. Fight she main Congress these. Interest federal drop chair foreign security.',
    'email': 'boonejames@example.net',
    'phone_number': '(439)200-2141x421',
    'json': {
    'name': 'Jeffrey Murphy',
    'address': '574 Mitchell Tunnel\nTammytown, NJ 00825',
},
    'key84210': 'value11409',
    'key74917': 'value12042',
    'key52529': 'value90475',
    'key67709': 'value77654',
    'key46738': 'value16022',
    'key98842': 'value20113',
    'key21984': 'value74777',
    'key65779': 'value87892',
    'key44600': 'value12013',
    'key80632': 'value20998',
},
    {
    'id': 17527492319144,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Ryan Smith',
    'address': '3761 Linda Island\nPort Nicholas, PA 79702',
    'text': 'East understand behavior. Allow pick security trouble material painting magazine general.\nRecently consider almost beyond. Analysis reduce theory north resource yes. Include happy environment.',
    'email': 'millerdonald@example.net',
    'phone_number': '(616)235-9307x553',
    'json': {
    'name': 'Harold Luna',
    'address': '5819 Jessica Spurs\nWest Christopherhaven, MA 62656',
},
    'key83498': 'value63698',
    'key67092': 'value2912',
    'key37973': 'value45977',
    'key60908': 'value99766',
    'key99789': 'value82907',
},
    {
    'id': 17527492319155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Michael Carter',
    'address': '63714 Hodge Circle Apt. 293\nLawrencestad, SD 81796',
    'text': 'Cover mother here fly political mind learn.\nBecause second glass must. Box serve heart traditional.',
    'email': 'jenniferday@example.org',
    'phone_number': '4552297893',
    'json': {
    'name': 'Laura Reed',
    'address': '10535 Gomez Bridge Apt. 675\nWest Calvinborough, MT 88989',
},
    'key76374': 'value82246',
    'key22588': 'value61681',
    'key12393': 'value94818',
    'key67842': 'value52847',
},
    {
    'id': 17527492319167,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Mathew Floyd',
    'address': '1483 Katrina Terrace\nWest Cristian, NE 04881',
    'text': 'Officer several toward night hair. Let career himself business attention. Near level bed son picture may alone.',
    'email': 'ofloyd@example.org',
    'phone_number': '7693241396',
    'json': {
    'name': 'Henry Cruz',
    'address': '3148 Smith Hill\nKingmouth, VT 37435',
},
    'key8572': 'value62717',
},
    {
    'id': 17527492319177,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Stephanie Martin',
    'address': '78712 Victoria Mills\nWest Nina, AZ 91252',
    'text': 'Strategy political well drop. Fine prepare also suggest.\nTrue door what road believe leg. Truth show bed without eye.\nMe day away media three minute. Travel open send general rise.',
    'email': 'vmyers@example.com',
    'phone_number': '802.945.9423x553',
    'json': {
    'name': 'Gina Daugherty',
    'address': '73900 Sanchez Meadow Apt. 957\nWest Territon, NC 95686',
},
    'key27469': 'value51609',
    'key50211': 'value52664',
    'key4446': 'value97699',
    'key57355': 'value42918',
    'key48022': 'value87043',
    'key80070': 'value24866',
    'key10635': 'value49486',
},
    {
    'id': 17527492319188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Stephanie Santana',
    'address': '58835 Hardy Extensions\nGarciafort, AK 52785',
    'text': 'Table power six. Each generation sell amount forget authority. My wife kitchen bring.\nCertain your step modern create political fast seven. That history land down nearly rate great.',
    'email': 'zshepherd@example.com',
    'phone_number': '+1-840-838-9474',
    'json': {
    'name': 'Jennifer Davis',
    'address': '84197 Bradford Points\nWest Matthewstad, MI 46472',
},
    'key54816': 'value90949',
    'key14351': 'value54017',
    'key366': 'value41958',
    'key59895': 'value83205',
    'key98477': 'value63281',
    'key13605': 'value78431',
    'key41817': 'value98001',
    'key60493': 'value98453',
    'key3873': 'value44535',
    'key10339': 'value30215',
},
    {
    'id': 17527492319199,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Antonio Johnson',
    'address': '66609 Keller Passage\nDavisfurt, VT 56950',
    'text': 'Senior control might threat her many. Hope travel relationship. Start participant word. Series anyone now perform.',
    'email': 'mrusso@example.com',
    'phone_number': '+1-398-825-9402x1064',
    'json': {
    'name': 'Brandi Ingram',
    'address': '16127 Daniel Circles Suite 369\nLake Robertville, TN 05791',
},
    'key29498': 'value60207',
    'key41796': 'value87197',
    'key47115': 'value87101',
    'key59008': 'value61972',
    'key49625': 'value10779',
    'key27918': 'value44813',
},
    {
    'id': 17527492319210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Susan Peterson',
    'address': '846 Patterson Circle\nYvettebury, MO 59361',
    'text': 'Suggest measure data trial might next themselves.\nDrop fact watch. Budget pattern bring life.\nAny nice up meeting media. Majority performance including edge idea green.\nFactor deep carry read.',
    'email': 'nelsontonya@example.com',
    'phone_number': '001-953-741-9011x6732',
    'json': {
    'name': 'Theresa Sanchez',
    'address': 'USCGC Stephens\nFPO AP 45911',
},
    'key80675': 'value63653',
    'key66596': 'value36697',
    'key84534': 'value41709',
    'key60045': 'value75064',
    'key64602': 'value4833',
    'key88955': 'value38574',
    'key88700': 'value83547',
    'key52924': 'value9628',
},
    {
    'id': 17527492319221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Arthur Clark',
    'address': '703 April Ford Suite 660\nJasonberg, RI 57499',
    'text': 'Standard hold total answer trade month cause. Indeed view leave sure. Thought rich part field.\nTeam whom blue south bad although. Point majority government response best become.',
    'email': 'samanthaharper@example.org',
    'phone_number': '405-807-0974x8483',
    'json': {
    'name': 'Rachel Richardson',
    'address': 'Unit 4121 Box 7022\nDPO AP 02696',
},
    'key67440': 'value46029',
    'key20851': 'value40800',
    'key37220': 'value73345',
    'key85937': 'value84031',
},
    {
    'id': 17527492319231,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Johnny Gibson',
    'address': '53241 Ramirez Greens\nRossborough, MA 62913',
    'text': 'Add scene charge allow there when. Office action simple part war.\nSign speak spring.\nUs identify area look. Successful he hold necessary exist.',
    'email': 'megan37@example.com',
    'phone_number': '001-748-376-2079x217',
    'json': {
    'name': 'Nancy Moore',
    'address': '701 Nicholas Islands\nMegantown, ME 76156',
},
    'key82852': 'value46698',
    'key25147': 'value71995',
    'key91221': 'value20778',
    'key69007': 'value29956',
    'key70281': 'value42937',
    'key62041': 'value29640',
},
    {
    'id': 17527492319243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Patrick Davis',
    'address': '0575 Avery Inlet\nNorth Robert, ND 29517',
    'text': 'Edge he east central. Develop fire environmental whole many seek offer himself. White for fear.',
    'email': 'larsencarlos@example.com',
    'phone_number': '(774)681-5007x695',
    'json': {
    'name': 'Karen Padilla',
    'address': '6491 Clark Via\nDavidport, FL 74307',
},
    'key52688': 'value19643',
    'key38903': 'value76067',
    'key76812': 'value15159',
    'key66027': 'value17928',
    'key57163': 'value83165',
    'key47693': 'value57885',
},
    {
    'id': 17527492319255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Kelly Gutierrez',
    'address': '38620 Alexis Lakes Suite 764\nPort Brianland, PW 84470',
    'text': 'Decide law reduce training month. Owner run include when. Point next lose customer surface listen matter.\nCouple paper foot same most outside. Station career issue nearly for some.',
    'email': 'mcdonaldmarc@example.com',
    'phone_number': '+1-320-275-2239x51653',
    'json': {
    'name': 'Luke Anderson',
    'address': '7138 Michael Vista Suite 007\nAustinville, AR 85567',
},
    'key80407': 'value81387',
    'key73102': 'value28642',
    'key98300': 'value36062',
    'key94259': 'value48994',
    'key69858': 'value26590',
    'key56236': 'value26489',
    'key5843': 'value31153',
    'key46707': 'value45726',
    'key19969': 'value62139',
},
    {
    'id': 17527492319267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Kaylee Berry',
    'address': '1838 Finley Mountain\nSouth Donton, AR 69198',
    'text': 'Example story base action people. Energy require worry technology control. Spend senior even her character of adult.',
    'email': 'robertsjimmy@example.com',
    'phone_number': '344.424.9692',
    'json': {
    'name': 'Holly Brown',
    'address': '08311 Carroll Knolls Suite 724\nCarmenborough, MN 10770',
},
    'key86088': 'value38725',
    'key95533': 'value15471',
    'key96551': 'value25974',
    'key39450': 'value81912',
    'key389': 'value2077',
    'key37531': 'value46464',
    'key82753': 'value4759',
},
    {
    'id': 17527492319280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Rachel Henry',
    'address': '7001 Michelle Alley\nBryanberg, MT 91050',
    'text': 'Speak compare eight approach. Near unit should low.\nSeat create very threat physical space. With attention point relate across organization enter. East great here reduce.',
    'email': 'davenportashley@example.com',
    'phone_number': '(797)254-1933x440',
    'json': {
    'name': 'Anne Phillips',
    'address': '6588 Brandon Mount\nEast Jennifer, NC 40311',
},
    'key65916': 'value95126',
    'key52039': 'value52087',
    'key89039': 'value67294',
    'key77310': 'value261',
    'key79923': 'value83564',
    'key55342': 'value4794',
    'key98919': 'value20436',
},
    {
    'id': 17527492319296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Dana Martinez',
    'address': '89713 Jones Ferry\nAngelicamouth, AR 21447',
    'text': 'Threat speak attention cold staff can. Ever general direction event deep boy. Suffer way phone garden. Since policy person.\nNature situation walk dream key talk. Oil capital property stand.',
    'email': 'thompsonjohn@example.org',
    'phone_number': '+1-408-203-8491x1676',
    'json': {
    'name': 'Kathy Evans',
    'address': '6870 Jeremy Drives Suite 418\nWalkerside, OK 20177',
},
    'key33302': 'value39736',
},
    {
    'id': 17527492319308,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'John Hill',
    'address': 'PSC 4659, Box 6408\nAPO AE 77965',
    'text': 'Form discussion red be relationship argue. Any single body itself war.\nMaybe point box yourself hair. Enough book agency section cell focus strong.',
    'email': 'ijones@example.com',
    'phone_number': '(259)957-5880x8667',
    'json': {
    'name': 'David Lewis',
    'address': '36298 Traci Extension Apt. 454\nWest Fernando, IA 73318',
},
    'key79549': 'value58122',
    'key97652': 'value85629',
    'key62535': 'value91916',
    'key61300': 'value61726',
    'key38722': 'value29892',
    'key21854': 'value55233',
    'key14355': 'value59897',
    'key35095': 'value83282',
    'key21723': 'value43332',
    'key68986': 'value82905',
},
    {
    'id': 17527492319317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Jeremy Anderson',
    'address': '7486 Anderson Road\nWest Karenburgh, RI 12873',
    'text': 'Tend idea perhaps president husband know. Heavy allow know eat. Hand beautiful somebody single until choice. Class pull eight dinner old.',
    'email': 'samuel72@example.com',
    'phone_number': '001-216-852-0943x165',
    'json': {
    'name': 'Scott Yang',
    'address': '4639 Rodriguez Brooks\nHernandezport, NV 03400',
},
    'key975': 'value77114',
    'key57187': 'value41681',
    'key76198': 'value6385',
},
    {
    'id': 17527492319327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Brian Warren',
    'address': 'PSC 9474, Box 2656\nAPO AA 94621',
    'text': 'Range during hit specific yard born. Authority east just decide. Wide result tend lose now.\nArgue help word letter cause about. Program successful change impact. Allow me second my almost.',
    'email': 'kyle70@example.com',
    'phone_number': '+1-664-556-2668x612',
    'json': {
    'name': 'Rebecca Farley',
    'address': '59610 Anderson Loaf\nNorth Melissaberg, FL 50583',
},
    'key42098': 'value18592',
    'key33080': 'value60051',
    'key86604': 'value62832',
    'key37965': 'value72661',
    'key97237': 'value21305',
},
    {
    'id': 17527492319336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Christian Johnson',
    'address': '013 Smith Hills\nPort Mark, PW 15577',
    'text': 'Note above plan where public heavy floor party. Power think town child single. Choice door day decade from represent treat success.',
    'email': 'foleymichael@example.net',
    'phone_number': '454.261.2476',
    'json': {
    'name': 'Veronica Jackson',
    'address': '35630 Hicks Ramp\nAlanberg, UT 06207',
},
    'key44591': 'value36907',
    'key65083': 'value28790',
    'key39704': 'value30440',
    'key51193': 'value6857',
    'key39872': 'value21032',
    'key12955': 'value47754',
    'key96222': 'value27419',
    'key45673': 'value75724',
    'key23081': 'value91871',
    'key34097': 'value29087',
},
    {
    'id': 17527492319347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Michelle Smith',
    'address': '36936 Nathaniel Station\nNew Michelleburgh, UT 89613',
    'text': 'Rate teach actually nation far determine support weight. Wonder party character trial maybe born. Place indeed involve will.\nIncluding anyone simple within study. Vote always interesting remember.',
    'email': 'meyermarc@example.org',
    'phone_number': '+1-622-796-4405x5639',
    'json': {
    'name': 'Melinda Ford',
    'address': '49236 Kathleen Pass\nChristopherfurt, DC 49102',
},
    'key76996': 'value89633',
    'key97547': 'value94276',
    'key4243': 'value1025',
    'key62545': 'value86103',
    'key46592': 'value94782',
    'key49437': 'value59503',
    'key33597': 'value38005',
    'key90124': 'value59757',
},
    {
    'id': 17527492319358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Mary Adams',
    'address': '0567 Sullivan Brooks\nAaronfurt, MH 69122',
    'text': 'Agreement reveal Democrat. End sure bag.\nWhat become author top resource business. Hospital after mother fine establish religious east.\nAccount set public.',
    'email': 'peter75@example.com',
    'phone_number': '001-539-650-4174x9016',
    'json': {
    'name': 'William Kim',
    'address': '317 Bryan Knolls Apt. 234\nLake Justintown, DE 38465',
},
    'key68527': 'value10148',
    'key65386': 'value25316',
    'key59208': 'value92375',
    'key98897': 'value16011',
},
    {
    'id': 17527492319370,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Douglas Park',
    'address': 'Unit 8880 Box 8175\nDPO AE 45225',
    'text': 'With true reduce mission beautiful theory. Figure behind among machine lawyer still surface. Church according record.\nFactor long reflect magazine serious theory foreign.',
    'email': 'tfranklin@example.com',
    'phone_number': '733-256-7239',
    'json': {
    'name': 'Jill Hayes',
    'address': '577 Adams Wall Suite 756\nWendyfort, TX 90291',
},
    'key33908': 'value18537',
    'key63015': 'value44595',
    'key37464': 'value5098',
    'key78376': 'value90425',
    'key93814': 'value90739',
},
    {
    'id': 17527492319379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Shannon Elliott',
    'address': 'PSC 5589, Box 7263\nAPO AE 77670',
    'text': 'Site top miss radio then. Range possible director million same team close. Either popular policy can policy soon similar. Election never audience state near rest consider image.',
    'email': 'lcontreras@example.net',
    'phone_number': '683-772-7955x8893',
    'json': {
    'name': 'Lisa Ruiz',
    'address': '27746 James Station\nWilsonshire, ID 37049',
},
    'key96811': 'value20612',
    'key18987': 'value58166',
    'key27057': 'value71537',
    'key52013': 'value90626',
    'key49078': 'value46656',
    'key671': 'value21568',
    'key45708': 'value79803',
    'key19505': 'value63427',
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
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/delete"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/delete")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/delete'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
    'filter': 'id == 17527492317215',
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
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
    'filter': 'id in [17527492317215]',
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
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
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



    def test_request_7(self):
        """测试请求 7 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
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
        """测试请求 8 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
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



    def test_request_9(self):
        """测试请求 9 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6144d944-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_47_05_674035OvINBHqB',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestDeleteVector_test_delete_vector_by_filter_pk_field[one]_1752749248.json')
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
    test = AllmilvusLogtestdeletevectorTestDeleteVectorByFilterPkFieldOne1752749248Json()
    test.run_tests()
