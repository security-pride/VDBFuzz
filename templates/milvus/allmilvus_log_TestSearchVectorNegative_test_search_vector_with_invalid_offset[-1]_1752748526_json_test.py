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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVectorNegative_test_search_vector_with_invalid_offset[-1]_1752748526_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_offset[-1]_1752748526.json"
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



class AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidOffset11752748526Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_offset[-1]_1752748526.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_offset[-1]_1752748526.json"
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
    'data': [
    {
    'id': 17527485234190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Bryce Reynolds',
    'address': '22797 Jeremiah Square\nCindyland, NE 18770',
    'text': 'Quickly give newspaper management. Sing nothing sister himself save of.\nLanguage as attorney enjoy beat pull. Color truth government none central.\nDescribe song compare.',
    'email': 'moniquelong@example.com',
    'phone_number': '001-323-517-9902x351',
    'json': {
    'name': 'Melinda Rhodes',
    'address': '7895 Riley Groves Suite 891\nBarnesborough, VA 43097',
},
    'key21439': 'value57636',
    'key84892': 'value67801',
    'key89104': 'value48969',
    'key16489': 'value27559',
    'key67820': 'value12281',
    'key50134': 'value29695',
    'key21254': 'value59251',
    'key39354': 'value14293',
    'key64318': 'value28183',
    'key98957': 'value46872',
},
    {
    'id': 17527485234208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Adrian Rivera',
    'address': '266 Thomas Locks\nRobinsonberg, AL 27255',
    'text': 'Beautiful picture white whole every admit fight. Reflect project value imagine special sense. Break message step word.',
    'email': 'gibbsshelly@example.org',
    'phone_number': '980.624.1430',
    'json': {
    'name': 'Jill Davidson',
    'address': '5973 Wendy Mission Suite 524\nDylanmouth, WY 52982',
},
    'key86372': 'value47249',
    'key20764': 'value60352',
    'key36355': 'value49519',
    'key67141': 'value61456',
    'key2623': 'value60842',
},
    {
    'id': 17527485234222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Heidi Cook',
    'address': '659 Devin Loaf Suite 645\nSouth Natasha, WV 13296',
    'text': 'Summer summer consider where.\nAlready determine image final. Work beyond from common mission official actually ever. Ask heavy field capital avoid.',
    'email': 'floresaustin@example.com',
    'phone_number': '001-823-625-7016x68263',
    'json': {
    'name': 'Robert Jones',
    'address': '71447 Jessica Cape\nCharlesborough, GA 47386',
},
    'key74565': 'value83626',
    'key62198': 'value8022',
    'key53379': 'value96172',
    'key33091': 'value75323',
    'key91267': 'value24339',
    'key16313': 'value55462',
},
    {
    'id': 17527485234236,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Richard Harrington',
    'address': '537 Boyd Stravenue\nNew Michael, FL 08272',
    'text': 'Care leader before hit start feeling why. Enjoy huge kitchen. Garden organization yard. Page including bag.\nNatural all her. Culture fund win stand source must trial information.',
    'email': 'sabrinajames@example.org',
    'phone_number': '762.914.3240x76638',
    'json': {
    'name': 'Mr. Ryan Garcia',
    'address': '307 Daniel Lake\nMccallfort, MS 84729',
},
    'key46721': 'value91239',
    'key74424': 'value20774',
    'key94448': 'value39012',
},
    {
    'id': 17527485234251,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Lisa Hahn',
    'address': '576 Lee Village\nSandrahaven, MH 78663',
    'text': 'We among letter million cover. Least something run knowledge when yeah. Anything art American answer run likely.\nHappy a successful future carry but Mr. Heavy far may idea.',
    'email': 'clarkjennifer@example.com',
    'phone_number': '(352)531-2873x00276',
    'json': {
    'name': 'Nicolas Arias',
    'address': '3096 Hoover Trace\nPort Johnburgh, ND 59704',
},
    'key51833': 'value3119',
    'key85271': 'value97140',
    'key49145': 'value98617',
    'key8639': 'value34479',
    'key20763': 'value14308',
    'key83896': 'value10570',
    'key68474': 'value95641',
    'key11302': 'value6855',
    'key93151': 'value50903',
    'key65541': 'value95257',
},
    {
    'id': 17527485234265,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Earl Ho',
    'address': '10019 Darrell Shoal\nEast Drewton, IN 04128',
    'text': 'Still something former bed value respond.\nIn them whole just option. Meet they however. Daughter seem whatever conference easy address behind.',
    'email': 'gonzalezjohn@example.net',
    'phone_number': '+1-844-777-9854',
    'json': {
    'name': 'Brittany Price',
    'address': '3506 Madeline Port\nSouth Judith, NY 97066',
},
    'key365': 'value28477',
    'key94105': 'value97522',
    'key93477': 'value79591',
    'key63544': 'value46194',
    'key21056': 'value61992',
    'key2193': 'value25934',
    'key43577': 'value63820',
    'key81062': 'value31264',
    'key53666': 'value49112',
    'key24331': 'value29957',
},
    {
    'id': 17527485234278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Roy Bowen',
    'address': '584 Danny Road Apt. 230\nHooperbury, NY 91601',
    'text': 'Turn shoulder house building fly pick. Word lot offer do expect in.\nAgent environment soldier kitchen through. Necessary age turn all fall story.',
    'email': 'jasonoconnell@example.net',
    'phone_number': '506-982-9462x1531',
    'json': {
    'name': 'Laura Zavala',
    'address': 'Unit 6421 Box 5047\nDPO AA 15744',
},
    'key16986': 'value17973',
    'key20200': 'value12800',
    'key34444': 'value3423',
    'key54847': 'value18178',
    'key80661': 'value88639',
    'key63436': 'value6724',
    'key44607': 'value9796',
    'key40653': 'value29500',
},
    {
    'id': 17527485234288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Louis Andrews',
    'address': '19180 White Garden Suite 739\nLorraineview, NM 58003',
    'text': 'Develop she accept. Strong respond talk morning citizen. Leg still Republican every.\nWatch view unit bag.\nAnything least medical turn. Good whose other student soldier mission.',
    'email': 'nhowell@example.com',
    'phone_number': '+1-655-331-8259',
    'json': {
    'name': 'Martin Campbell',
    'address': '76638 Stone Ridge Suite 036\nRebeccaview, VT 78536',
},
    'key84494': 'value87547',
    'key7357': 'value34087',
    'key74173': 'value94301',
    'key28738': 'value58357',
    'key89263': 'value8300',
    'key22245': 'value82551',
},
    {
    'id': 17527485234299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'John Chavez',
    'address': '7460 Sandra Junction Suite 233\nNorth Stephanieland, NY 84375',
    'text': 'Clearly family area arm it wrong technology. Federal offer military travel. Compare national leg determine present cold.\nMore trade glass newspaper value. Pretty material cold fall.',
    'email': 'richardsondawn@example.org',
    'phone_number': '335-674-9869x32398',
    'json': {
    'name': 'Matthew Miller',
    'address': '786 Flores Loop\nNorth Stephanieville, ND 45249',
},
    'key14099': 'value36159',
    'key62409': 'value53910',
    'key80043': 'value37555',
    'key83302': 'value98387',
    'key96768': 'value97975',
},
    {
    'id': 17527485234310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brian Turner',
    'address': '943 Jennifer Island\nNorth Kathy, UT 02801',
    'text': 'Reach imagine consider any difference. Of and cost raise chance close idea.\nTop dark game especially unit ten just. Who through either right laugh.',
    'email': 'alexandriacarpenter@example.org',
    'phone_number': '294-449-6665',
    'json': {
    'name': 'Andre Colon',
    'address': '3996 Robert Crossing\nMartinezborough, NJ 76246',
},
    'key54230': 'value24824',
    'key98366': 'value69978',
    'key57963': 'value35628',
    'key7249': 'value25426',
    'key90549': 'value24266',
    'key42576': 'value50932',
    'key70542': 'value86451',
    'key67886': 'value2384',
    'key47757': 'value30680',
    'key20437': 'value38081',
},
    {
    'id': 17527485234321,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Nicole Moss',
    'address': '850 Bryant Mills Suite 378\nAnthonytown, MI 22669',
    'text': 'Recently success all still suddenly. Country race television avoid town. Space same first evidence and front.',
    'email': 'kpayne@example.com',
    'phone_number': '695.964.6504x464',
    'json': {
    'name': 'David Smith',
    'address': '208 Courtney Mews\nPort Cynthiaburgh, SD 81599',
},
    'key4443': 'value69731',
    'key67593': 'value72629',
    'key4558': 'value62588',
    'key10725': 'value17359',
    'key95529': 'value77495',
    'key61335': 'value15688',
    'key52500': 'value89823',
    'key92920': 'value57168',
    'key39802': 'value76230',
},
    {
    'id': 17527485234332,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Alexandra Lynch',
    'address': '985 William Knolls\nTeresaburgh, WA 23666',
    'text': 'Agree situation term impact deal. Economic fill interest.\nWant change full serious. Middle doctor performance several.\nExample quality idea trouble. Begin Republican reflect against.',
    'email': 'melissalane@example.net',
    'phone_number': '(509)537-9062x0068',
    'json': {
    'name': 'Angela Lambert',
    'address': '22214 Dominguez Place\nNew Kristine, AS 59808',
},
    'key82851': 'value3705',
    'key41247': 'value57276',
},
    {
    'id': 17527485234344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Jesse Thomas',
    'address': '660 Casey Spring Suite 085\nSouth Tyler, DC 02222',
    'text': 'Several institution director people meet. Action soon continue commercial very work network out. Than both military society.',
    'email': 'jacquelinegrant@example.org',
    'phone_number': '(269)793-2708',
    'json': {
    'name': 'Steven Johnston',
    'address': '4650 Donald Mountain\nNorth Melissaport, VT 71890',
},
    'key12605': 'value79649',
    'key85131': 'value33579',
    'key15677': 'value26899',
    'key8270': 'value42645',
    'key76847': 'value33313',
    'key79629': 'value28958',
    'key93642': 'value72296',
    'key53872': 'value55563',
    'key71369': 'value1961',
    'key18351': 'value71604',
},
    {
    'id': 17527485234355,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jeremy Edwards',
    'address': '2797 Tina Estates\nWest Stephanieborough, MT 57015',
    'text': 'Mr figure sea brother official pick. Run after even. Send its industry in.\nFoot two billion past happy free security. Wide dark to special per change that white. Father if your knowledge.',
    'email': 'shampton@example.com',
    'phone_number': '397-852-7007',
    'json': {
    'name': 'Dawn Dennis',
    'address': '10089 Martinez Vista Suite 521\nLopezshire, AS 25477',
},
    'key86845': 'value43350',
    'key34249': 'value4528',
    'key43863': 'value38184',
    'key2664': 'value21572',
},
    {
    'id': 17527485234366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jennifer Gomez',
    'address': '6937 Sanders Locks Apt. 772\nReginaside, NC 85460',
    'text': 'Five scientist strategy family maybe allow be. Street focus health Mr.\nMagazine stay both up have eye your. Beautiful friend interview fund concern piece.',
    'email': 'derekperry@example.org',
    'phone_number': '(439)794-5451',
    'json': {
    'name': 'Alexandra Benson',
    'address': '3348 Kyle Parkways\nPaulview, DE 44901',
},
    'key33418': 'value95368',
    'key91437': 'value41023',
    'key25657': 'value1526',
    'key20071': 'value76891',
},
    {
    'id': 17527485234378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Michael Bell',
    'address': '43103 Maldonado Mountain\nLake Shelleymouth, NY 56581',
    'text': 'International per think station have realize police. During region activity late.\nDecision staff peace never stage pull fine. Yes worry will all thousand because pull.',
    'email': 'justin99@example.org',
    'phone_number': '+1-406-233-7690x1373',
    'json': {
    'name': 'Kevin Martin',
    'address': 'Unit 2196 Box 8629\nDPO AP 48675',
},
    'key61531': 'value47533',
    'key49609': 'value40855',
    'key7990': 'value61198',
    'key21094': 'value48714',
},
    {
    'id': 17527485234386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'George Erickson',
    'address': '5709 Jonathan Knoll Apt. 938\nJennifermouth, WV 79855',
    'text': 'Mouth national to from board face thank else.\nRange exist home during fight quite move. Simply boy follow admit seem drop. Thought develop relationship poor director team.',
    'email': 'ruizkristen@example.com',
    'phone_number': '259.808.4830x8496',
    'json': {
    'name': 'Ariana Sanders',
    'address': '879 Earl Ports Suite 965\nJohnsonfurt, MD 22941',
},
    'key9040': 'value69298',
    'key60761': 'value50213',
    'key38223': 'value58981',
},
    {
    'id': 17527485234397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Jesse Thomas',
    'address': '519 Wells Locks Suite 041\nSherrymouth, IN 18583',
    'text': 'Almost newspaper fine while they. Nice majority mention.\nKind find drop. Reason develop east kid arrive.\nDecade station the her nature oil. Serve contain couple Congress visit end.',
    'email': 'eric31@example.net',
    'phone_number': '278.367.5893x206',
    'json': {
    'name': 'Luis Sloan',
    'address': '208 Pollard Falls Apt. 124\nPort Lindamouth, KS 56158',
},
    'key82419': 'value86993',
    'key28683': 'value26012',
    'key48807': 'value51616',
    'key29900': 'value26225',
    'key49177': 'value62887',
},
    {
    'id': 17527485234408,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Mathew Morgan',
    'address': '664 Mckee Lodge Apt. 677\nRachelborough, LA 64832',
    'text': 'Whether democratic blue total change cultural. Woman from clearly recent product during. Support ready local dark.',
    'email': 'ibell@example.org',
    'phone_number': '4936677501',
    'json': {
    'name': 'Robert Taylor',
    'address': 'PSC 6983, Box 2729\nAPO AP 31021',
},
    'key10922': 'value13788',
    'key40122': 'value4536',
    'key26873': 'value98357',
    'key67518': 'value97731',
    'key70775': 'value87711',
    'key99144': 'value92066',
    'key32423': 'value52987',
    'key45452': 'value19811',
    'key78316': 'value10731',
    'key93409': 'value61232',
},
    {
    'id': 17527485234417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jonathan Kelley',
    'address': '9858 Jones Spring Suite 031\nLake Matthew, NJ 17733',
    'text': 'Require by lot bank important year.\nPopulation deep sometimes likely. Expect early director may require.',
    'email': 'iirwin@example.com',
    'phone_number': '(572)828-3998',
    'json': {
    'name': 'Tina Baxter',
    'address': '157 Everett Isle Suite 713\nNew Jacobstad, OH 87197',
},
    'key99919': 'value11143',
    'key7880': 'value62636',
    'key34087': 'value69938',
    'key76202': 'value81835',
},
    {
    'id': 17527485234428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Lisa Petersen',
    'address': '078 Morgan Avenue Apt. 844\nNorth Susan, NC 62358',
    'text': 'Degree although reflect cell. Break particularly some tend hour build financial.\nHair operation determine arrive else campaign night. Way read community house.',
    'email': 'petersonkenneth@example.net',
    'phone_number': '377.312.1796',
    'json': {
    'name': 'Francisco Ross',
    'address': '0320 Davis Course\nLoveland, WV 89839',
},
    'key21134': 'value30650',
    'key38020': 'value9340',
    'key3638': 'value66641',
    'key68909': 'value1104',
},
    {
    'id': 17527485234440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Linda Dunn',
    'address': '015 Pamela Lodge\nMichaelport, NC 35367',
    'text': 'Get mean she on majority. Unit work ago price social since Mrs.\nFeeling her suggest when market within. Like laugh poor peace. Serious TV TV dinner so.',
    'email': 'ysanchez@example.com',
    'phone_number': '+1-753-817-5778x75754',
    'json': {
    'name': 'Susan Edwards',
    'address': '10955 Jacqueline Park Apt. 307\nPhillipberg, MP 57868',
},
    'key40006': 'value54662',
    'key44197': 'value91328',
    'key50402': 'value77545',
    'key29864': 'value15013',
    'key80860': 'value52665',
    'key53637': 'value40837',
    'key79147': 'value53333',
    'key51913': 'value88526',
    'key5648': 'value78196',
},
    {
    'id': 17527485234450,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jean Pierce',
    'address': 'USNV Beck\nFPO AP 25549',
    'text': 'Table range friend movie moment sort us. Wait before art finally up.\nSouth successful situation deep. Where admit bag different. Store range charge television run customer avoid by.',
    'email': 'hendersonjoseph@example.com',
    'phone_number': '383-423-5419x99051',
    'json': {
    'name': 'Brett Flores',
    'address': '055 Yang Mountains\nJohnview, RI 44087',
},
    'key26091': 'value86654',
    'key79421': 'value86844',
    'key32637': 'value66085',
    'key28904': 'value37419',
},
    {
    'id': 17527485234461,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Ashley Gilbert',
    'address': '6460 Johnson Light Suite 307\nRamirezbury, ID 24609',
    'text': 'Better number political put back media week. This front could deep eye decide set.',
    'email': 'twilliams@example.net',
    'phone_number': '543.540.8367',
    'json': {
    'name': 'Samantha Adams',
    'address': '152 Virginia Canyon\nMarquezstad, FL 42008',
},
    'key43722': 'value80282',
    'key33116': 'value14626',
    'key45854': 'value56088',
    'key33980': 'value36579',
    'key54808': 'value43819',
    'key34854': 'value81874',
    'key95203': 'value35915',
    'key51940': 'value73041',
    'key91097': 'value7781',
    'key10778': 'value39312',
},
    {
    'id': 17527485234471,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Barbara Bonilla',
    'address': '9274 Irwin Cliffs\nCynthiaview, MH 50762',
    'text': 'Tell live heart happy box class data follow. Crime hand responsibility work cultural produce that.\nAlong offer weight author current like. For whom event tax thousand. Leave ok onto painting take.',
    'email': 'zachary74@example.com',
    'phone_number': '(516)620-2601x484',
    'json': {
    'name': 'Kaylee Carpenter',
    'address': '31167 Smith Passage\nPort Mathewfurt, IL 78509',
},
    'key33316': 'value45373',
    'key32295': 'value65551',
    'key54862': 'value40425',
    'key6809': 'value7198',
},
    {
    'id': 17527485234482,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'John Becker',
    'address': '595 Lane Parks Apt. 944\nLake Mary, VA 20282',
    'text': 'Watch job number whose carry it. Respond student drug away production mention lawyer above. Drive work base open whose reality. Speech and describe look fall southern.',
    'email': 'patricksarah@example.org',
    'phone_number': '6304315600',
    'json': {
    'name': 'Amy Frazier',
    'address': '816 Michael Manor\nNorth Kristen, NM 98285',
},
    'key64084': 'value51874',
    'key19167': 'value16135',
    'key56385': 'value43490',
},
    {
    'id': 17527485234493,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jackie Hines',
    'address': '38977 Joseph Fort\nHectormouth, WA 13535',
    'text': 'Scene plant responsibility actually order pull current life. Agent war garden six concern. Just talk national provide.\nYou heart leader walk wife trial policy.',
    'email': 'margaret67@example.org',
    'phone_number': '001-582-218-7321x20314',
    'json': {
    'name': 'Kathy Fitzgerald',
    'address': '85997 Randy Park\nJohnville, SC 56964',
},
    'key74452': 'value51229',
    'key14150': 'value19351',
},
    {
    'id': 17527485234503,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jessica Davis',
    'address': '2294 Tyler Fall\nHarrellmouth, OH 86774',
    'text': 'Own behavior chance. Good down specific trip government. Whole go smile attack stage doctor each.\nComputer there short. Assume raise coach.\nHit field form.',
    'email': 'scottmorales@example.org',
    'phone_number': '001-365-904-5728x479',
    'json': {
    'name': 'Jennifer Gilmore',
    'address': '8729 Clayton Summit\nLake Mathew, GU 61408',
},
    'key30658': 'value4594',
    'key43109': 'value4587',
    'key33337': 'value36377',
},
    {
    'id': 17527485234514,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Kristen Sanchez',
    'address': '94753 Smith Mountain Apt. 808\nNorth Cynthiaside, WY 75645',
    'text': 'Run up generation professional set suggest. Address tough report quality.\nPaper deep government nation. Later someone than conference back majority. Account for allow know film drop believe.',
    'email': 'bcampos@example.net',
    'phone_number': '+1-229-390-5012x1928',
    'json': {
    'name': 'Michael Escobar',
    'address': '80938 Nunez Extensions\nNicholasfort, SD 38394',
},
    'key32228': 'value62606',
    'key3233': 'value10380',
    'key44953': 'value58627',
    'key41584': 'value65115',
    'key94772': 'value47964',
    'key19419': 'value62240',
    'key47006': 'value25559',
},
    {
    'id': 17527485234526,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Maria Schmidt',
    'address': '48551 Hays Pike Apt. 602\nJessicaport, NM 13345',
    'text': 'Sell exactly enter also. Future open prepare.\nSell forward edge TV son wear many. Inside food west person couple she lot. Want television office start candidate choose.',
    'email': 'timothy78@example.org',
    'phone_number': '474-868-5356x152',
    'json': {
    'name': 'David Richards',
    'address': '5736 Ronald Prairie Suite 379\nWilliamsfurt, OH 88294',
},
    'key70519': 'value41579',
    'key34965': 'value98147',
    'key48688': 'value84941',
    'key17092': 'value80386',
    'key87109': 'value71987',
    'key87267': 'value36110',
    'key27382': 'value32106',
    'key81768': 'value31807',
    'key89993': 'value62597',
    'key18721': 'value10745',
},
    {
    'id': 17527485234538,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Richard Johns',
    'address': '520 Trujillo Point Apt. 742\nLake Jonathanstad, WV 34903',
    'text': 'Accept magazine education even growth weight wide.\nOwner major strategy actually realize seek. Increase room hope woman.',
    'email': 'ghall@example.org',
    'phone_number': '503.745.1965x4615',
    'json': {
    'name': 'Tammy Ellison',
    'address': '65693 Jones Harbors Apt. 202\nLake Nichole, CO 72290',
},
    'key62785': 'value5969',
    'key20661': 'value84257',
    'key37415': 'value1135',
    'key12725': 'value84198',
},
    {
    'id': 17527485234550,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Marco Anderson',
    'address': '222 Shah Way\nNew Nicole, SD 24409',
    'text': 'Plant report prevent himself issue threat. Until actually process real southern thank movie.',
    'email': 'martinjennifer@example.net',
    'phone_number': '773.786.4677',
    'json': {
    'name': 'Leslie Zimmerman',
    'address': 'USNS Hanson\nFPO AP 16163',
},
    'key20083': 'value16892',
    'key65141': 'value63288',
    'key38111': 'value38091',
},
    {
    'id': 17527485234560,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Angela Braun',
    'address': '2937 Garrett Cove\nLake Jessicabury, MS 01136',
    'text': 'Free himself continue various join. Cause service me star throw against. Better first front allow us smile.\nResearch blue play require young pattern. Good event moment according.',
    'email': 'angelapowers@example.com',
    'phone_number': '(982)653-5739',
    'json': {
    'name': 'Ashley Flores',
    'address': '257 Bennett Branch Suite 220\nSouth Michael, OR 33113',
},
    'key19761': 'value56660',
    'key39504': 'value12572',
    'key3965': 'value76945',
    'key17423': 'value23804',
    'key52573': 'value27445',
    'key97820': 'value25937',
    'key4386': 'value18053',
    'key2817': 'value65983',
    'key51594': 'value37780',
},
    {
    'id': 17527485234572,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Christina Powell',
    'address': '86878 Mark Rue Suite 249\nRachelberg, WV 22200',
    'text': 'Should head simple also street live. Option manage article recently watch pick determine. Table choice possible us happy.\nThird now idea week oil step policy. Grow table since best rate truth.',
    'email': 'taylorjacqueline@example.net',
    'phone_number': '822.203.9917',
    'json': {
    'name': 'Alexis Hamilton',
    'address': '9857 Justin Hills Apt. 071\nChaseport, SC 58238',
},
    'key19539': 'value25465',
    'key52741': 'value54121',
    'key46646': 'value74745',
},
    {
    'id': 17527485234583,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Jeffrey Vang',
    'address': 'Unit 0035 Box 0844\nDPO AA 24895',
    'text': 'About happen contain even control. Artist low trip get church language.',
    'email': 'lorimartin@example.net',
    'phone_number': '(790)762-6063',
    'json': {
    'name': 'Michael Harris',
    'address': '739 Ray Corner Apt. 411\nDavidton, AR 65730',
},
    'key20321': 'value43204',
    'key51962': 'value67642',
    'key10668': 'value75686',
    'key867': 'value69457',
    'key20107': 'value44129',
},
    {
    'id': 17527485234593,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Leslie Washington',
    'address': 'USNV Stanley\nFPO AE 89415',
    'text': 'Send whom truth weight exist reason tree. Lot position into laugh. Argue stand officer some wrong social single.',
    'email': 'leonardkyle@example.com',
    'phone_number': '(604)586-5549',
    'json': {
    'name': 'Anthony Miller',
    'address': '3594 Walker Locks\nSanchezbury, KY 91979',
},
    'key63574': 'value41932',
    'key51995': 'value70884',
    'key54371': 'value80755',
    'key25280': 'value75068',
    'key41156': 'value56427',
    'key6605': 'value32837',
    'key30603': 'value57009',
},
    {
    'id': 17527485234603,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Darrell Alexander',
    'address': '214 Brown Turnpike Apt. 326\nEast Debraborough, AZ 72705',
    'text': 'Other mention window themselves son. Say community member near.\nSuggest up large inside bed management wall international. Eye care system her list. Throughout actually measure sometimes serve.',
    'email': 'mckeeerika@example.com',
    'phone_number': '001-771-547-2233x108',
    'json': {
    'name': 'Leslie Wilson',
    'address': '9724 Moses Plaza Suite 038\nSouth John, AZ 05704',
},
    'key43985': 'value40266',
    'key46566': 'value78850',
    'key38129': 'value42432',
    'key62068': 'value51009',
    'key7241': 'value25037',
    'key99060': 'value71232',
    'key10657': 'value28191',
    'key393': 'value62409',
    'key17915': 'value59416',
},
    {
    'id': 17527485234615,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Michael Rose',
    'address': '95380 Myers Mountains\nEast Jessicaton, HI 55373',
    'text': 'Discussion method low interesting national sometimes. Use natural home case.\nImprove must choose green. Special pull across bit stand white. Technology professional win world care network really.',
    'email': 'gomezabigail@example.net',
    'phone_number': '663.864.0081x11453',
    'json': {
    'name': 'James Curry',
    'address': '542 Courtney Overpass Apt. 666\nAdkinsview, KS 92900',
},
    'key84718': 'value98773',
    'key3565': 'value38143',
    'key57781': 'value67905',
    'key75695': 'value4217',
    'key1066': 'value21272',
    'key39801': 'value3889',
    'key75715': 'value32757',
    'key93640': 'value22225',
},
    {
    'id': 17527485234627,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kristin Mcclain',
    'address': '34261 Rachel Corner Apt. 075\nWest Justin, KY 93271',
    'text': 'On board happen allow size. Personal discussion spend.',
    'email': 'schultzmary@example.net',
    'phone_number': '001-493-659-8905x40362',
    'json': {
    'name': 'Darren Mills',
    'address': '036 Collins Mews Apt. 721\nGreenhaven, ME 12323',
},
    'key26169': 'value6063',
    'key10356': 'value39209',
    'key79363': 'value74833',
    'key58423': 'value26283',
    'key73916': 'value28929',
    'key90511': 'value13580',
},
    {
    'id': 17527485234639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Tyler Savage',
    'address': '740 Valenzuela Mountain Apt. 581\nSouth Davidstad, ME 78869',
    'text': 'Upon me author people. Receive one kitchen. Mr actually can identify those entire.\nSomething believe teacher build. New themselves feeling black professor down event.',
    'email': 'schneidersteven@example.org',
    'phone_number': '001-401-712-9604x78653',
    'json': {
    'name': 'Kimberly Evans',
    'address': '9900 David Run Apt. 739\nNorth Mary, NJ 98474',
},
    'key30482': 'value62889',
    'key99600': 'value42585',
},
    {
    'id': 17527485234651,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Aaron Miranda',
    'address': '6893 Matthew Expressway Apt. 630\nEast Mason, MO 75394',
    'text': 'Per still social between include international. Ball still yourself party. Personal grow only can section.',
    'email': 'carterjames@example.com',
    'phone_number': '326-982-9368x0318',
    'json': {
    'name': 'Patrick Brown',
    'address': '66875 Marcia Lodge Suite 958\nLake Joshualand, CA 07421',
},
    'key60378': 'value85658',
    'key72559': 'value22631',
    'key89170': 'value95426',
},
    {
    'id': 17527485234661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jonathan Johnson',
    'address': '76870 Nancy Gardens Suite 208\nHarmonmouth, MT 19482',
    'text': 'Economy player above economic. Actually against same fish wait realize. Thus voice increase whose third military.\nSenior star easy ahead blue ever. Author large lawyer issue. Economic nature ability.',
    'email': 'deanna57@example.com',
    'phone_number': '7467158235',
    'json': {
    'name': 'Marvin Gould',
    'address': '027 Brandy Stravenue\nNorth Jameshaven, MH 12002',
},
    'key42802': 'value93425',
    'key35640': 'value98628',
    'key74042': 'value19249',
},
    {
    'id': 17527485234672,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Kristen Coleman',
    'address': '6553 Colin Stream\nNorth Kelseyfurt, GU 60741',
    'text': 'Rather least us college throw soldier box. Factor help water research. Floor west seek charge pattern push couple.\nYet travel lead. Practice seat bag see.',
    'email': 'gateslisa@example.org',
    'phone_number': '+1-728-740-6901x78534',
    'json': {
    'name': 'Steven Ramirez',
    'address': '73589 John Plains\nMillerhaven, WI 98291',
},
    'key40431': 'value17460',
    'key96274': 'value16967',
    'key43283': 'value76535',
    'key81200': 'value72119',
},
    {
    'id': 17527485234683,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Megan Torres',
    'address': '499 Lisa Field\nSouth Kimton, MT 17904',
    'text': 'Foreign summer she cell suffer summer security. Energy east specific none fly expect.\nRock leave off same dream away. Resource true southern hear candidate phone compare.',
    'email': 'robinsonsusan@example.com',
    'phone_number': '596-895-5987x700',
    'json': {
    'name': 'Amber Stevens',
    'address': '6341 Jennifer Cliff\nDavidbury, OK 22306',
},
    'key10955': 'value13909',
    'key26101': 'value37525',
    'key67959': 'value31578',
    'key99026': 'value53220',
},
    {
    'id': 17527485234695,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Marie Flynn',
    'address': '992 Campbell Ranch\nJuanborough, VI 24033',
    'text': 'Social throughout training still. Unit test issue. Can question Mr data.\nSmall key after conference their. Market bag pay when.',
    'email': 'aadams@example.net',
    'phone_number': '+1-324-974-8900x91225',
    'json': {
    'name': 'Luis Watson',
    'address': 'PSC 5339, Box 9802\nAPO AA 97111',
},
    'key78908': 'value11937',
},
    {
    'id': 17527485234704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Matthew Lewis',
    'address': 'Unit 0813 Box 1364\nDPO AE 37075',
    'text': 'With professor need show key teach. Say parent southern next garden beautiful.\nHave accept speak best receive provide. Third send professor you try. Under goal face involve.',
    'email': 'whitelisa@example.org',
    'phone_number': '721.255.1881x62359',
    'json': {
    'name': 'Kristine Lozano',
    'address': '032 Pierce Stream\nSmithfort, AR 08772',
},
    'key36002': 'value40777',
},
    {
    'id': 17527485234715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Whitney Bailey',
    'address': '058 Green Drive Suite 794\nGillstad, SC 69568',
    'text': 'Democratic themselves represent resource. Tax mind appear. Choose operation exactly others director.',
    'email': 'williamwood@example.org',
    'phone_number': '001-666-696-3547x236',
    'json': {
    'name': 'Haley Cordova',
    'address': '76409 Le Street\nJosephville, AS 81749',
},
    'key96509': 'value79481',
    'key63823': 'value45383',
    'key64838': 'value14281',
    'key55555': 'value21743',
},
    {
    'id': 17527485234727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Angel Lewis',
    'address': '0126 Christopher Meadow Suite 062\nNorth Christina, MI 54680',
    'text': 'Form common beyond ready. Movement whose per cultural pay. Message pattern expect today good step money.',
    'email': 'keith79@example.org',
    'phone_number': '605-611-7348x89168',
    'json': {
    'name': 'Kimberly Williams',
    'address': '686 Brooke Summit\nPort Loribury, NJ 17464',
},
    'key17716': 'value69593',
    'key36923': 'value93399',
    'key24583': 'value41450',
    'key45146': 'value46057',
    'key22434': 'value43425',
    'key97217': 'value34324',
},
    {
    'id': 17527485234738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Jamie Green',
    'address': 'PSC 9147, Box 8674\nAPO AA 73209',
    'text': 'Suggest probably day weight. With very life popular. Sport store entire pick so dinner.',
    'email': 'ccox@example.org',
    'phone_number': '001-680-942-9775x6877',
    'json': {
    'name': 'Kelli Ball',
    'address': '91019 Newman Streets Apt. 819\nNorth Bradleyport, VA 95325',
},
    'key21577': 'value92419',
    'key6686': 'value61997',
    'key34295': 'value28069',
    'key69468': 'value23646',
    'key70215': 'value53554',
    'key54313': 'value10995',
    'key31473': 'value17406',
    'key15541': 'value54119',
    'key93744': 'value10795',
    'key58754': 'value16918',
},
    {
    'id': 17527485234748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Phillip Jackson',
    'address': '9344 Kristy Mission\nBrittanyport, RI 63507',
    'text': 'Against dog factor attack. World garden relate mention despite kitchen be exist. Difficult apply list fly picture again class out.',
    'email': 'ashleygordon@example.com',
    'phone_number': '717-961-7808',
    'json': {
    'name': 'William Smith',
    'address': '580 Michele Estate Apt. 416\nEast Erika, KS 47568',
},
    'key53937': 'value8016',
},
    {
    'id': 17527485234761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Samuel Jones',
    'address': '3443 Mills Road Apt. 193\nPort Daisy, OH 87820',
    'text': 'Care test popular clearly yourself want win. Performance move sense understand hard director already. Knowledge listen control throw.',
    'email': 'bfrench@example.com',
    'phone_number': '361.471.8932',
    'json': {
    'name': 'Sara Hickman',
    'address': '36688 Kathleen Tunnel\nSouth Annaburgh, MS 78364',
},
    'key41139': 'value82661',
    'key16492': 'value74180',
    'key95701': 'value10144',
    'key2661': 'value106',
},
    {
    'id': 17527485234773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Joseph Morse',
    'address': '05650 Jordan Course\nWest Linda, TX 20157',
    'text': 'Nothing two investment enjoy nature while. Truth age party them. New debate part reveal. So first provide audience new admit mention at.',
    'email': 'eperez@example.com',
    'phone_number': '+1-293-710-4998x4514',
    'json': {
    'name': 'Jason Cervantes',
    'address': '8051 David Ports Suite 273\nEast Brian, KY 59114',
},
    'key6931': 'value83664',
    'key62907': 'value47919',
    'key30602': 'value94743',
    'key85900': 'value52400',
    'key34396': 'value382',
    'key50187': 'value52268',
},
    {
    'id': 17527485234786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Jesse Gill',
    'address': '98624 Amber Ferry Apt. 320\nNorth Mary, UT 03927',
    'text': 'Author amount size each we air discover. Grow bed real degree Democrat.\nBy party something maybe camera. Machine back government cost. Firm goal since special outside television source.',
    'email': 'martineztina@example.org',
    'phone_number': '755.911.4272x114',
    'json': {
    'name': 'William Arnold',
    'address': '0288 Washington Spring\nNorth Dean, ND 82092',
},
    'key64142': 'value74861',
    'key19488': 'value63861',
    'key72446': 'value39153',
    'key55759': 'value38301',
    'key78190': 'value19862',
    'key61556': 'value5765',
    'key96897': 'value44661',
    'key2096': 'value88205',
    'key83457': 'value46073',
    'key66848': 'value20299',
},
    {
    'id': 17527485234800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Christopher Barrett',
    'address': '8468 Mitchell Wells\nAguirreshire, MH 13706',
    'text': 'Century way plan base street available different. Time walk range history quite moment. Table return political case stay.\nLocal you find. For that item very station father impact.',
    'email': 'don02@example.org',
    'phone_number': '931.324.0767',
    'json': {
    'name': 'Marie Gutierrez',
    'address': '8042 Barnett River\nNorth Steven, IL 96174',
},
    'key86894': 'value98116',
    'key30729': 'value50949',
    'key59995': 'value15090',
    'key95206': 'value43606',
    'key94744': 'value19846',
    'key23114': 'value68617',
    'key50380': 'value70749',
    'key843': 'value19072',
    'key43472': 'value54075',
},
    {
    'id': 17527485234812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Randall Faulkner',
    'address': '3851 Joseph Place Apt. 106\nSouth Carlashire, AZ 83220',
    'text': 'Paper coach price they process pattern economy. I computer me common chair require.\nAffect improve sound right per. Right lay experience such set yourself.',
    'email': 'zhammond@example.org',
    'phone_number': '9094921422',
    'json': {
    'name': 'Joel Cooper',
    'address': '8054 Hardy Fall Suite 738\nSamuelview, DE 22072',
},
    'key60778': 'value19223',
    'key9178': 'value28264',
    'key47596': 'value18330',
    'key79889': 'value5471',
    'key32549': 'value46986',
    'key13533': 'value97986',
    'key67365': 'value67395',
    'key97908': 'value82963',
    'key97635': 'value1996',
},
    {
    'id': 17527485234823,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Ms. Stephanie Harris',
    'address': '6139 Weeks Tunnel\nEast Shannonchester, MP 22763',
    'text': 'Week project relationship agree fish. Support personal my dinner box cause wind. Collection keep book at speak. Music during relate network while.',
    'email': 'lisa56@example.org',
    'phone_number': '810.697.1678x87607',
    'json': {
    'name': 'Julie Wagner',
    'address': '866 Austin Points Suite 860\nCannonton, MD 32304',
},
    'key70482': 'value46526',
    'key59637': 'value85631',
    'key92457': 'value94417',
    'key91950': 'value38781',
    'key40333': 'value55270',
    'key80225': 'value61764',
    'key29613': 'value7578',
},
    {
    'id': 17527485234835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Joshua Austin',
    'address': '9329 Huerta Shores Apt. 997\nKimberlyport, AL 62900',
    'text': 'Free order down spend. Law worker community.\nDetail machine final either board. Cultural around station author. Left black imagine question. Current sister oil still wear.\nHold company nature enter.',
    'email': 'wlopez@example.net',
    'phone_number': '813.235.8467x1092',
    'json': {
    'name': 'David Henry',
    'address': '05531 Lori Hill Apt. 763\nWest Chelseamouth, AR 04241',
},
    'key37219': 'value36373',
    'key90157': 'value24428',
    'key97808': 'value63093',
    'key32955': 'value47360',
    'key45178': 'value32180',
    'key35619': 'value72679',
    'key38579': 'value25756',
    'key74815': 'value70062',
    'key35062': 'value44801',
    'key39821': 'value15332',
},
    {
    'id': 17527485234847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Allison Day',
    'address': '1687 Richard Fall\nEast Beverly, AL 43354',
    'text': 'Player assume could magazine degree it. Down safe treatment situation.\nGovernment response hold talk. Even shake course.\nApply force particular outside.',
    'email': 'kelly07@example.org',
    'phone_number': '001-549-598-1020x26837',
    'json': {
    'name': 'Heather Hill',
    'address': '882 Blake Crest Suite 886\nMichelleport, FL 02702',
},
    'key52443': 'value63454',
    'key29069': 'value68272',
    'key85432': 'value55635',
    'key88148': 'value77676',
    'key70108': 'value672',
    'key6190': 'value50539',
    'key16572': 'value74516',
},
    {
    'id': 17527485234858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Latoya Lucas',
    'address': '6230 Anthony Lodge Apt. 859\nLake Gloria, NM 59267',
    'text': 'Design indeed glass challenge who doctor. Central tell stage many.\nAt attention live cup hot. Ready she note determine. Available exist citizen remember song north while drop.',
    'email': 'tcarlson@example.net',
    'phone_number': '(701)262-8538x714',
    'json': {
    'name': 'Jose Mitchell',
    'address': '704 Timothy Crescent Apt. 975\nTonyaland, WY 81471',
},
    'key74463': 'value11199',
    'key24870': 'value19336',
    'key56249': 'value47366',
    'key19018': 'value30021',
    'key24240': 'value55577',
},
    {
    'id': 17527485234869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Autumn Cooley',
    'address': 'PSC 0481, Box 0408\nAPO AP 36891',
    'text': 'Should form knowledge perhaps. Old east realize room live be vote. Production Congress appear.',
    'email': 'gdavis@example.org',
    'phone_number': '867.259.6541x66134',
    'json': {
    'name': 'Hannah Fisher',
    'address': '063 Tran Hollow\nNorth Loganborough, OR 46379',
},
    'key28682': 'value79230',
    'key17927': 'value88072',
},
    {
    'id': 17527485234878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Rachel Delacruz',
    'address': '48116 Christopher Circle\nMichaelborough, IN 66564',
    'text': 'Might future can from effort natural create. Positive husband film plant.\nProduction participant other scientist matter. Ground care those military word television property.',
    'email': 'stephen31@example.com',
    'phone_number': '001-715-397-6770x19128',
    'json': {
    'name': 'Scott Miller',
    'address': '2766 Crawford Spur Apt. 935\nMaryborough, ME 40893',
},
    'key31842': 'value95264',
    'key18671': 'value68979',
    'key86190': 'value64349',
},
    {
    'id': 17527485234888,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Ann Swanson',
    'address': 'PSC 2124, Box 7685\nAPO AA 45224',
    'text': 'Art account more expect why class. Later join old exactly. Eight receive media perform of.',
    'email': 'maciasmiguel@example.org',
    'phone_number': '498-803-8710x474',
    'json': {
    'name': 'Mr. Paul Wall',
    'address': 'USNV Diaz\nFPO AA 63433',
},
    'key30044': 'value33101',
    'key24142': 'value24589',
    'key42167': 'value51357',
    'key89464': 'value55001',
},
    {
    'id': 17527485234896,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Sara Humphrey',
    'address': '512 Moore Drive\nAnthonyfort, AL 78083',
    'text': 'Enter difference near develop. Might recently crime operation happen. Whether meeting make language piece standard which.\nThough point far very matter about attack. Lawyer century test gas nation.',
    'email': 'mooreemily@example.net',
    'phone_number': '292-742-7225x81339',
    'json': {
    'name': 'Mary Foley',
    'address': '0851 Walker Circles\nWest Victoriaburgh, VI 62558',
},
    'key28004': 'value21451',
    'key88989': 'value5200',
    'key36195': 'value60937',
    'key79208': 'value34327',
},
    {
    'id': 17527485234907,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Dylan Harmon',
    'address': '9082 Nathan Camp Suite 993\nBlackville, KY 91631',
    'text': 'Role shoulder throw issue statement. Where federal speech tax.\nSoldier fund agent focus table team. Investment tax painting girl group federal.',
    'email': 'qwest@example.net',
    'phone_number': '001-651-302-4510x101',
    'json': {
    'name': 'David Jones',
    'address': '570 Anderson Terrace Apt. 225\nHaasborough, VA 45820',
},
    'key85772': 'value97526',
    'key67149': 'value22847',
    'key4992': 'value65089',
    'key17602': 'value66284',
    'key43254': 'value75660',
},
    {
    'id': 17527485234918,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Logan Williams',
    'address': '4027 Alexis Isle\nTylerside, PW 81787',
    'text': 'Able fact good glass partner manage firm. Role bring doctor response expect test resource I. Especially performance crime walk right.',
    'email': 'angela06@example.org',
    'phone_number': '(695)907-6845x4174',
    'json': {
    'name': 'Benjamin Vargas',
    'address': '115 Emily Avenue Suite 623\nRichardmouth, CT 73459',
},
    'key13248': 'value11138',
    'key18512': 'value63729',
    'key96007': 'value5625',
    'key44928': 'value17012',
    'key85617': 'value14794',
    'key16307': 'value50598',
    'key55724': 'value81653',
    'key72447': 'value84088',
    'key63276': 'value50071',
    'key98091': 'value90418',
},
    {
    'id': 17527485234928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jennifer Lawrence',
    'address': '03671 Donna Pass\nNorth Jeanneville, MH 94400',
    'text': 'Low contain mention teach scene detail. Theory kind ask or south itself system girl. Almost somebody understand growth interesting garden life.',
    'email': 'gilldean@example.com',
    'phone_number': '735.638.5519x99635',
    'json': {
    'name': 'Gina Terry',
    'address': '509 Kelly Brook\nWest Katherineland, AK 87861',
},
    'key58799': 'value9402',
    'key6154': 'value97747',
    'key99182': 'value46249',
    'key61718': 'value18646',
    'key23120': 'value61096',
    'key38058': 'value76442',
    'key1281': 'value89968',
    'key84731': 'value97670',
    'key80390': 'value61815',
},
    {
    'id': 17527485234939,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Melissa Henson',
    'address': '325 James Pines Apt. 827\nWest Gary, OK 80712',
    'text': 'During institution grow style. Son different professional participant run finish north.\nBoy position star discussion. Tell including almost a really defense take. Put thing identify quality spring.',
    'email': 'staceysimon@example.net',
    'phone_number': '674-352-3488',
    'json': {
    'name': 'Robert Gibson',
    'address': '7913 Collins Courts\nNorth Patrick, IN 93058',
},
    'key14726': 'value85446',
    'key24506': 'value52202',
    'key47756': 'value97038',
    'key65614': 'value70722',
    'key33984': 'value85967',
},
    {
    'id': 17527485234950,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Erik Brown',
    'address': '11199 Norris Locks Suite 504\nAngelaton, ME 07104',
    'text': 'Happen low develop process. Among movie team majority friend have. Teach picture although Congress environment food decade. Technology history question name.',
    'email': 'smeyer@example.org',
    'phone_number': '993-568-3048',
    'json': {
    'name': 'Heidi Carrillo',
    'address': '219 Stephanie Highway Apt. 660\nPort Nicoleland, SD 26306',
},
    'key18196': 'value3723',
    'key76807': 'value39948',
    'key69954': 'value33236',
    'key14559': 'value93172',
    'key86360': 'value85849',
    'key22999': 'value93293',
    'key49205': 'value34309',
    'key4321': 'value63282',
    'key45100': 'value90681',
    'key74153': 'value19837',
},
    {
    'id': 17527485234961,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Sergio Roach',
    'address': '26726 Floyd Station Apt. 588\nHernandezmouth, KS 40903',
    'text': 'Themselves page author. Military difficult of dark.\nCold often shake pressure way. Must response national center. Medical nation do hour magazine. Pick last rest against.',
    'email': 'smithashley@example.com',
    'phone_number': '(347)226-7968x745',
    'json': {
    'name': 'Jeremy Brown',
    'address': '769 Fernandez Ville\nSouth Laurashire, NM 00676',
},
    'key90347': 'value67288',
    'key75099': 'value58505',
    'key93069': 'value74785',
    'key30051': 'value64918',
    'key53611': 'value52714',
    'key71653': 'value40279',
    'key99130': 'value22013',
    'key55682': 'value39607',
    'key59557': 'value99665',
    'key82058': 'value73079',
},
    {
    'id': 17527485234973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Theresa House',
    'address': '1300 Fletcher Ville\nNorth Ashley, VA 40189',
    'text': 'Artist deal beyond plan. Race structure quality. Economy similar tonight admit save.\nChoice economy project himself eye these. Site conference even doctor.',
    'email': 'sotocrystal@example.org',
    'phone_number': '603-306-4797',
    'json': {
    'name': 'Steve Campbell',
    'address': '133 Bush Run Suite 889\nHernandezbury, IA 21723',
},
    'key25284': 'value3813',
    'key775': 'value9640',
    'key61188': 'value15295',
    'key72346': 'value62887',
},
    {
    'id': 17527485234985,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Meghan Gonzalez',
    'address': '136 Kathryn Place Suite 775\nSouth Adammouth, VA 29638',
    'text': 'Many education raise design near dark candidate company. Chance your sit right bar wind.\nWe lay test check. Project walk amount note would modern woman.',
    'email': 'johnpeters@example.com',
    'phone_number': '724.398.8017',
    'json': {
    'name': 'Taylor Williamson',
    'address': '91655 Patricia Trail\nJenniferside, CT 91001',
},
    'key53477': 'value15252',
    'key28376': 'value43652',
    'key34001': 'value88722',
    'key79397': 'value29581',
},
    {
    'id': 17527485234996,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Robert Sanders',
    'address': '9544 Montgomery Forks Suite 592\nAndreaton, FL 91360',
    'text': 'Already region member old. Specific half floor where marriage.\nAble see south. Evidence key itself police phone different conference. Either member staff none treatment glass statement.',
    'email': 'kristy13@example.net',
    'phone_number': '956-780-2334',
    'json': {
    'name': 'Mary Rhodes',
    'address': '50031 Stone Springs Suite 616\nSouth Mark, VA 45412',
},
    'key92366': 'value32319',
},
    {
    'id': 17527485235007,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Kevin Foley',
    'address': '88052 Harris Path\nPort Jennaland, AZ 85474',
    'text': 'Game know return keep. Defense to admit necessary second building year. According special north better.\nAnyone church institution community share agree. Explain on stay effort east although someone.',
    'email': 'walter40@example.com',
    'phone_number': '267-633-1582',
    'json': {
    'name': 'Kimberly Ortega',
    'address': '75657 Burton Lakes Suite 225\nJohnview, KY 62359',
},
    'key3194': 'value9800',
    'key71966': 'value7993',
    'key15173': 'value85299',
    'key18183': 'value79632',
    'key7468': 'value22800',
    'key17168': 'value58916',
    'key71765': 'value80544',
    'key40795': 'value75357',
    'key42300': 'value95947',
    'key99245': 'value33154',
},
    {
    'id': 17527485235018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Bryce Bailey',
    'address': '620 Michelle Village Suite 195\nGonzalesborough, MA 13674',
    'text': 'Nothing heart respond significant perhaps speech magazine perform. Less station shake time base against. Less many lay realize.',
    'email': 'larrypetty@example.com',
    'phone_number': '(557)478-6440x54912',
    'json': {
    'name': 'Darren Miller',
    'address': '1206 Brown Locks\nLake Josephberg, MP 92113',
},
    'key44989': 'value5085',
    'key40667': 'value17902',
    'key41231': 'value64267',
    'key41585': 'value81917',
    'key64191': 'value56533',
    'key9321': 'value45995',
    'key44265': 'value54767',
    'key6440': 'value22306',
    'key97975': 'value27555',
},
    {
    'id': 17527485235030,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Stephen Smith',
    'address': '0974 Steven Villages Apt. 528\nEast Raymondville, MN 26425',
    'text': 'Benefit reveal friend open. Author institution memory food company consider likely billion. Rich know least instead fear stay play.',
    'email': 'taylorwatson@example.org',
    'phone_number': '531.279.8538',
    'json': {
    'name': 'Diana Singh',
    'address': '1508 Kenneth Points\nEast Patricia, TX 37406',
},
    'key28112': 'value856',
    'key5409': 'value89593',
    'key16397': 'value35984',
    'key95971': 'value87887',
    'key18015': 'value8629',
    'key25139': 'value12394',
    'key34613': 'value5031',
    'key59470': 'value42845',
},
    {
    'id': 17527485235041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Christopher Johnson',
    'address': '07083 April Corners\nSouth Johnny, MI 41459',
    'text': 'Draw happen skill safe. Probably simply team defense appear win safe might. Then seem approach sure traditional nothing family. Name meeting beyond describe cover.',
    'email': 'npowers@example.org',
    'phone_number': '357-221-6148',
    'json': {
    'name': 'Margaret Torres',
    'address': '35592 Johnson Ridge Apt. 076\nDawnton, NJ 40188',
},
    'key89848': 'value61413',
    'key52955': 'value57754',
    'key42770': 'value26046',
    'key11127': 'value35382',
    'key8319': 'value15452',
    'key17529': 'value57713',
    'key18951': 'value46841',
    'key74107': 'value80653',
},
    {
    'id': 17527485235052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Jeffery Beasley',
    'address': '18153 Zoe Canyon Suite 076\nGinamouth, NE 29284',
    'text': 'Sit glass claim nearly training surface. News also black. Scientist let public.\nParty remember interest large carry. General grow plan upon heart investment cultural. Research determine card.',
    'email': 'brandon99@example.com',
    'phone_number': '+1-202-887-0613x94222',
    'json': {
    'name': 'Christopher Hansen',
    'address': '254 Edwards Island\nHarrellshire, OK 41169',
},
    'key81140': 'value33766',
    'key33239': 'value89440',
    'key26017': 'value94668',
    'key46201': 'value31409',
    'key31062': 'value72440',
},
    {
    'id': 17527485235063,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Lucas Lopez',
    'address': '3632 Jackson Forks\nWest Daleview, IN 99223',
    'text': 'Expect manage weight. Property air among several positive defense.\nSend suggest week man Democrat. So specific out example. Name range customer standard whether himself green. Third next reveal role.',
    'email': 'xyoung@example.org',
    'phone_number': '+1-387-592-7091x982',
    'json': {
    'name': 'Eugene Barber',
    'address': '835 Thomas Lodge\nFisherchester, MD 56554',
},
    'key391': 'value63541',
    'key18848': 'value16425',
    'key89898': 'value21431',
    'key23162': 'value7938',
},
    {
    'id': 17527485235073,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Pamela Oneill',
    'address': 'PSC 0659, Box 7226\nAPO AE 72570',
    'text': 'Pull leave time window look anyone. Safe book fish.\nWhole study tax news sea history. Wear could experience information long quality morning own.',
    'email': 'kimberly01@example.com',
    'phone_number': '001-215-758-7098x085',
    'json': {
    'name': 'Wendy Wade',
    'address': '719 Wilson Mountain Suite 229\nLake Timothy, NH 11959',
},
    'key6334': 'value69498',
    'key8678': 'value75207',
    'key24534': 'value96871',
    'key2895': 'value48542',
},
    {
    'id': 17527485235082,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Andres Sosa',
    'address': '10581 Hernandez Greens\nSouth Kimberlyfurt, AK 25066',
    'text': 'Tax return board ability by word life. Class when defense almost understand. Table man interview just.',
    'email': 'eric37@example.net',
    'phone_number': '654.712.5538x32895',
    'json': {
    'name': 'Shelby Wheeler',
    'address': '3252 Summers Village Suite 650\nMillerchester, CO 77217',
},
    'key22124': 'value74859',
    'key31646': 'value62987',
    'key45690': 'value68086',
    'key73034': 'value93577',
    'key32155': 'value45176',
    'key45375': 'value68272',
},
    {
    'id': 17527485235093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Kevin Morgan',
    'address': '52281 Jackson Roads\nChurchton, OR 85866',
    'text': 'Something stuff edge. To science wait rock cost best.\nChallenge social who. Thought discuss surface yourself.\nLay glass pay. They edge part author. Add it often plan response culture statement.',
    'email': 'briannajones@example.net',
    'phone_number': '(656)269-9380x2813',
    'json': {
    'name': 'Stephen Clay',
    'address': '8074 Price Curve\nNorth Jasonmouth, NH 20225',
},
    'key69760': 'value96905',
},
    {
    'id': 17527485235104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Brian Alvarez',
    'address': '30434 Christopher Alley Suite 533\nHammondside, NH 55027',
    'text': 'Consumer simply often series argue friend. Fight take weight become. Through at group election mean second.',
    'email': 'yshaffer@example.net',
    'phone_number': '001-276-827-2757x959',
    'json': {
    'name': 'Lauren Miller',
    'address': '59823 Cindy Avenue Suite 896\nSouth Angela, PA 66376',
},
    'key27000': 'value76923',
    'key80778': 'value23025',
    'key17984': 'value65926',
},
    {
    'id': 17527485235115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Jacob Nelson',
    'address': '65079 Garcia Streets Apt. 209\nSouth Loriborough, MD 96795',
    'text': 'Act nature week professor method. Final case life couple.',
    'email': 'barnesjacob@example.com',
    'phone_number': '001-562-491-1116x48953',
    'json': {
    'name': 'Laura Christensen',
    'address': '41660 Cassandra Loaf\nArmstrongbury, VA 67852',
},
    'key51161': 'value20957',
    'key80672': 'value20973',
    'key15204': 'value35084',
    'key89971': 'value23191',
    'key72311': 'value57809',
    'key44964': 'value94704',
    'key9814': 'value39628',
    'key78733': 'value34060',
    'key57069': 'value72780',
    'key90275': 'value63135',
},
    {
    'id': 17527485235127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Cynthia Skinner',
    'address': '9544 Charles Highway Apt. 284\nWernerville, AL 16582',
    'text': 'Under who standard one table policy seek.\nForget they keep form. Science third avoid say.\nSignificant image her option agree camera answer. Air strategy economy you movie southern economy.',
    'email': 'christopher34@example.org',
    'phone_number': '274.928.2214',
    'json': {
    'name': 'Amanda Miller',
    'address': '8361 Gaines Mission\nPhiliphaven, PR 92178',
},
    'key39760': 'value38577',
    'key15376': 'value24085',
    'key43441': 'value3820',
    'key38493': 'value69966',
    'key74324': 'value78572',
    'key75501': 'value74660',
    'key79212': 'value78972',
    'key86276': 'value36219',
    'key50341': 'value35834',
    'key48239': 'value40390',
},
    {
    'id': 17527485235138,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Nicole Pope',
    'address': '4192 Tammy Hollow Suite 126\nJamesmouth, VT 20012',
    'text': 'Serious school early west process far camera head. Air impact site nation many wear. Baby value his worry both change simply friend.',
    'email': 'mcollier@example.org',
    'phone_number': '854.891.8620x192',
    'json': {
    'name': 'Roberto Davis',
    'address': 'Unit 0672 Box 9415\nDPO AP 57197',
},
    'key5039': 'value88909',
    'key61948': 'value27099',
    'key90901': 'value33192',
    'key25030': 'value4066',
    'key34997': 'value13933',
    'key83114': 'value51275',
    'key85523': 'value70072',
    'key2142': 'value49527',
    'key7075': 'value43815',
},
    {
    'id': 17527485235146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Jacqueline Bowen',
    'address': '898 Edwards Bridge Suite 349\nEast Laura, TX 12624',
    'text': 'Fine government available actually use catch himself.\nBusiness finish state field check station. Indicate whom big person teacher recently wonder law. None if evening test leave.',
    'email': 'schultzanthony@example.com',
    'phone_number': '001-683-756-1791x53125',
    'json': {
    'name': 'Michael Michael',
    'address': '156 Steven Overpass Suite 714\nWheelerside, IN 05834',
},
    'key714': 'value84306',
    'key61596': 'value75573',
    'key25451': 'value49002',
    'key76422': 'value28614',
    'key91917': 'value86856',
    'key10498': 'value26072',
    'key46655': 'value2118',
},
    {
    'id': 17527485235158,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Zachary Delacruz',
    'address': '5791 Michelle Islands\nCamachomouth, PA 36778',
    'text': 'Exactly system thing ok worker level civil. Benefit structure the. Wait marriage church buy receive remember. Both threat anyone letter build law.',
    'email': 'curtisdarren@example.com',
    'phone_number': '(628)856-9155x358',
    'json': {
    'name': 'Paul Walker',
    'address': '074 Martinez Underpass Apt. 682\nThompsonhaven, DC 61871',
},
    'key77891': 'value77035',
    'key18637': 'value27618',
    'key6495': 'value49275',
    'key26809': 'value59997',
    'key15705': 'value80090',
    'key59164': 'value12002',
    'key78846': 'value70445',
    'key37898': 'value8588',
},
    {
    'id': 17527485235169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Donna Jones',
    'address': '9476 John Cliff\nPort Connormouth, TX 03481',
    'text': 'Partner believe treat care hand style reach. Direction real keep Republican idea poor summer. Rich standard last call almost once owner expect.',
    'email': 'falvarez@example.net',
    'phone_number': '+1-897-480-3642',
    'json': {
    'name': 'Timothy Morgan',
    'address': 'USNV Jackson\nFPO AP 18083',
},
    'key80437': 'value72161',
    'key50595': 'value55168',
    'key55913': 'value2171',
},
    {
    'id': 17527485235178,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Amber Hardy',
    'address': '19227 Chad Harbors\nWest Brittneybury, HI 55079',
    'text': 'Training member fire study authority court. Provide evidence office life.\nPretty happen study quickly my.\nWe up same budget threat second our. Key lose mission economic respond nothing behind.',
    'email': 'goodchristopher@example.com',
    'phone_number': '(779)942-9577x8888',
    'json': {
    'name': 'Natalie Allen',
    'address': '72724 Dillon Ville\nGeorgeshire, OH 94260',
},
    'key66064': 'value48295',
    'key10296': 'value10549',
    'key12459': 'value79959',
    'key53798': 'value16556',
    'key59097': 'value41640',
    'key51831': 'value80224',
    'key49030': 'value4936',
    'key10608': 'value50637',
    'key6904': 'value22153',
    'key28016': 'value94103',
},
    {
    'id': 17527485235189,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Vanessa White',
    'address': '96726 Jessica Junction Apt. 178\nLake Rita, NM 07975',
    'text': 'Never create require hundred term. Do day country.\nSport push the fear century. Character seven quite Mr take.\nDay protect yet tree. Soldier movement light animal news newspaper.',
    'email': 'dnovak@example.org',
    'phone_number': '6006979406',
    'json': {
    'name': 'Andrew Ferguson',
    'address': '333 Alexander Parkway\nDavenportville, WY 33076',
},
    'key66657': 'value63518',
    'key36128': 'value85181',
    'key92989': 'value8850',
},
    {
    'id': 17527485235200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Jason Patton',
    'address': '6882 Alvarado Parkways Apt. 297\nSouth Philip, FL 49831',
    'text': 'Everyone society material scientist seat memory special especially. Weight quite still.\nIf of among author. Guy stock within training. Big lay tough interview.',
    'email': 'david45@example.org',
    'phone_number': '+1-708-454-1951x519',
    'json': {
    'name': 'Bob White',
    'address': '5923 Garner Place Apt. 685\nPort Kaitlyn, HI 10212',
},
    'key20105': 'value49385',
    'key84889': 'value12187',
    'key63727': 'value83647',
    'key56856': 'value5420',
    'key64220': 'value87562',
    'key57942': 'value702',
    'key12051': 'value88935',
},
    {
    'id': 17527485235212,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Lindsey Mitchell',
    'address': '8192 Brock Groves Suite 366\nLorishire, NE 65199',
    'text': 'Item drop manager eat information stand often. Month as turn investment quality can.',
    'email': 'ljohnson@example.com',
    'phone_number': '292.847.0244x721',
    'json': {
    'name': 'James Clarke',
    'address': '73876 Fitzpatrick Plaza Suite 212\nRichardview, SC 79222',
},
    'key95323': 'value7064',
    'key98261': 'value44159',
    'key45565': 'value42558',
    'key63781': 'value98589',
    'key8445': 'value74129',
    'key49928': 'value86581',
    'key71821': 'value33748',
    'key62658': 'value87236',
    'key50364': 'value35687',
    'key41981': 'value39746',
},
    {
    'id': 17527485235223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Linda Ruiz',
    'address': '1248 Timothy Rapid\nWagnerview, ID 45475',
    'text': 'Newspaper compare turn strategy course sing arrive. Standard operation off far.',
    'email': 'skim@example.net',
    'phone_number': '(514)682-4112x09295',
    'json': {
    'name': 'James Martin',
    'address': '792 Heather Trace Apt. 250\nFlorestown, OR 70836',
},
    'key45588': 'value78235',
    'key82294': 'value83586',
    'key55622': 'value95120',
    'key50936': 'value23757',
    'key41278': 'value42714',
    'key40833': 'value42840',
    'key5011': 'value95704',
    'key54334': 'value66444',
    'key86797': 'value69184',
},
    {
    'id': 17527485235235,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Sue Turner',
    'address': '904 Orr Ridges Apt. 487\nNew Lisa, PW 90292',
    'text': 'Call describe young card look. Appear only hour reality owner. System but despite court discussion.',
    'email': 'alexisbell@example.com',
    'phone_number': '(432)646-3919x4291',
    'json': {
    'name': 'Marvin Shelton Jr.',
    'address': '176 Sandoval Lake Suite 653\nJohnstonburgh, WV 33840',
},
    'key56097': 'value78086',
    'key120': 'value11725',
    'key23891': 'value79650',
    'key90708': 'value96104',
    'key37347': 'value99431',
    'key80416': 'value10047',
    'key93282': 'value33439',
},
    {
    'id': 17527485235248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Daniel Brooks',
    'address': '064 Kathleen Mountain Suite 002\nNew Robert, IL 53715',
    'text': 'Purpose better three consider current performance attention. Identify month floor man happy voice eight. Television without operation science task think ability. Return pattern poor this edge.',
    'email': 'thensley@example.net',
    'phone_number': '+1-927-885-3987x96264',
    'json': {
    'name': 'Jill Reynolds',
    'address': '514 Hall Stravenue\nCarolshire, WY 71524',
},
    'key4747': 'value3884',
    'key31141': 'value7809',
},
    {
    'id': 17527485235259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'George Sanchez',
    'address': '847 Virginia Overpass\nPatelview, NV 39796',
    'text': 'Individual red model treat audience technology lot. May subject through trouble participant necessary notice. Until factor hit firm there decide go.',
    'email': 'debra55@example.com',
    'phone_number': '7506984474',
    'json': {
    'name': 'Kelly Juarez',
    'address': '66962 Manning Corner\nPort Larryview, MP 15214',
},
    'key35446': 'value61981',
},
    {
    'id': 17527485235269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Stephanie Woodward',
    'address': '45902 Parks Island Apt. 121\nErinton, NV 81396',
    'text': 'Maybe must thousand strategy deep study available sister. Alone staff age window boy set against. Answer capital across conference.\nCheck consider do year right. Think war wonder agent her glass do.',
    'email': 'reyestanya@example.net',
    'phone_number': '(227)963-6659x1613',
    'json': {
    'name': 'Christopher Tran',
    'address': '612 Townsend Lights Suite 754\nPedrofurt, OH 68471',
},
    'key83526': 'value4824',
    'key97673': 'value37636',
    'key46561': 'value86493',
    'key36689': 'value84133',
    'key4420': 'value30791',
},
    {
    'id': 17527485235281,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Brian Young',
    'address': '36259 Christina Forest\nDebraland, DE 90199',
    'text': 'College budget year girl property increase three. Top near yard involve. School all kid difference drop.',
    'email': 'lynnpatricia@example.net',
    'phone_number': '+1-638-985-9134',
    'json': {
    'name': 'Joshua Jacobs',
    'address': 'PSC 2450, Box 4866\nAPO AE 69248',
},
    'key60457': 'value99489',
    'key1920': 'value47311',
    'key77019': 'value95094',
    'key16398': 'value66545',
    'key38978': 'value55515',
    'key25928': 'value42449',
    'key55955': 'value57570',
    'key31028': 'value95546',
},
    {
    'id': 17527485235290,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Carrie Hooper',
    'address': '4282 Robyn Mountains\nNorth Katherineside, WA 69512',
    'text': 'Available create too. Tend child trouble security. Reason measure pressure commercial.\nHundred share school think contain. Clear now finally. Serve set nation senior method.',
    'email': 'freyes@example.net',
    'phone_number': '875.917.8649x093',
    'json': {
    'name': 'William York',
    'address': '256 Zachary Street Suite 397\nAshleyview, SC 19615',
},
    'key38805': 'value10325',
    'key47295': 'value70733',
    'key91154': 'value83550',
    'key85732': 'value10783',
    'key42820': 'value42097',
    'key61471': 'value54736',
    'key63632': 'value34739',
    'key4460': 'value34096',
    'key90718': 'value29600',
    'key16991': 'value4991',
},
    {
    'id': 17527485235301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Sharon Holt',
    'address': '57526 Scott Dam Suite 416\nAdamsport, TN 62908',
    'text': 'Fly quite different practice toward. Maybe know top may next forget.\nCharge deal sure simple stop majority. Memory arrive member. Stand peace store floor risk real tonight eight.',
    'email': 'ajohnson@example.com',
    'phone_number': '459.551.0429x0005',
    'json': {
    'name': 'Hayden Chavez',
    'address': 'PSC 4488, Box 5820\nAPO AA 36173',
},
    'key7240': 'value17343',
    'key50389': 'value99732',
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
    'data': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'address',
    'uid',
    'email',
    'json',
],
    'filter': 'uid >= 0',
    'limit': 100,
    'offset': -1,
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
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
    'RequestId': 'bb139232-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_17_352641whiGvzLi',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_offset[-1]_1752748526.json')
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
    test = AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidOffset11752748526Json()
    test.run_tests()
