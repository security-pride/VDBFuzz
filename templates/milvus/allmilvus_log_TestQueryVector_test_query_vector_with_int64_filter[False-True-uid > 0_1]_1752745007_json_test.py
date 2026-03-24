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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 0_1]_1752745007_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 0_1]_1752745007.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid011752745007Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 0_1]_1752745007.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 0_1]_1752745007.json"
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
    'RequestId': '87d7869b-62f1-11f0-8e15-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_34_417336ioeFygWc',
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
    'RequestId': '8af4ffd8-62f1-11f0-b63d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_34_417336ioeFygWc',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Ashley Frederick',
    'address': '17240 White Common Apt. 679\nNew Georgestad, ID 30066',
    'text': 'Find music guy break kid. Cut source whom collection nothing wrong.\nCommon pressure condition structure author deep gun. Scientist shake often why chair. Per middle itself door event.',
    'email': 'angela95@example.org',
    'phone_number': '001-471-960-0524x121',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Neil King',
    'Daniel Graham',
    'Cassandra Griffin',
    'Kelly Pope',
    'Debra Davis',
    'Rebecca Sanders',
],
    'json': {
    'name': 'Marvin King',
    'address': '94452 Julie Meadow Suite 937\nMichaelshire, TN 30459',
},
    'key72973': 'value17567',
    'key62109': 'value78329',
    'key65884': 'value32293',
    'key5504': 'value93675',
    'key66573': 'value61831',
    'key75976': 'value2414',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Julie Lane',
    'address': '754 Isaac Meadow\nMcclureside, ME 20731',
    'text': 'Of blue chair both. Address be one body return beyond. Example look new performance must throw much.\nMonth future guess. Course score stop player agency color. Office item side heavy share situation.',
    'email': 'iphillips@example.com',
    'phone_number': '633-937-4498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Devin English',
    'Rebecca Glass',
],
    'json': {
    'name': 'Tiffany Goodwin',
    'address': 'PSC 3339, Box 7389\nAPO AE 67461',
},
    'key39611': 'value68359',
    'key18661': 'value62967',
    'key51752': 'value41814',
    'key94329': 'value21397',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Christine Morris',
    'address': '560 Knight Canyon\nRamostown, NV 59821',
    'text': 'Hundred either lose option drug.\nAgo suddenly newspaper task evening. Successful security hard enjoy still. Attention address life catch. Staff close traditional make people peace.',
    'email': 'jessicabradley@example.org',
    'phone_number': '948-416-4190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Richard Kaiser',
    'Thomas Carlson',
    'Ashley Jones',
    'William Anderson',
    'Allen Patton',
    'Jennifer Huerta',
    'Jessica Mathews',
    'Garrett Nunez MD',
],
    'json': {
    'name': 'Mrs. Mary Davis',
    'address': '377 Jonathan Parks Suite 770\nSandramouth, MD 21936',
},
    'key29207': 'value24737',
    'key40039': 'value10683',
    'key26915': 'value34229',
    'key24358': 'value23779',
    'key11283': 'value30599',
    'key57489': 'value83995',
    'key77545': 'value87589',
    'key44957': 'value74341',
    'key51148': 'value17614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Brandon Myers',
    'address': '00260 Patricia Village\nLake Margaret, UT 90283',
    'text': 'Light place set. Event best system strategy allow pretty because.\nAfter seven whom unit. Management our hear today physical Democrat imagine.',
    'email': 'xavila@example.com',
    'phone_number': '(919)574-7677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Walker',
    'Kelly Green',
    'George Anderson',
    'Linda Paul',
    'John Atkinson',
    'Diane Johnson',
    'Lori Johnson',
    'Julie Jones',
    'Lori Brewer',
],
    'json': {
    'name': 'William Miller',
    'address': '8648 Melton Way\nSanchezview, OR 36481',
},
    'key28675': 'value60170',
    'key85928': 'value79986',
    'key6595': 'value73554',
    'key64630': 'value24987',
    'key84662': 'value62518',
    'key55320': 'value72286',
    'key83186': 'value58742',
    'key88657': 'value83343',
    'key60040': 'value5622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Robert Montgomery',
    'address': '02221 Johnston Islands Suite 929\nCoreystad, CO 27889',
    'text': 'Body during responsibility character several agent. Music impact director among keep return. Name culture control thought.\nYet leg letter receive. Benefit rest whose seem understand dream.',
    'email': 'smithelizabeth@example.org',
    'phone_number': '(709)388-6493',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Hanson',
    'Melissa Avery',
    'David Warner',
    'Tony Scott',
    'Krystal Adams',
    'Amy Smith',
    'Alyssa Rogers',
    'Paul Johnson MD',
    'Nathaniel Ray',
    'Jimmy Burns',
],
    'json': {
    'name': 'David Alvarez',
    'address': '97414 Ross Corner\nEast Crystalburgh, AR 72961',
},
    'key36080': 'value64605',
    'key55886': 'value84586',
    'key69208': 'value37951',
    'key30585': 'value33834',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Christina Henderson',
    'address': '83564 Christopher Island\nRojasville, MN 86438',
    'text': 'Customer apply network magazine. City concern morning with table. Off boy professor small.',
    'email': 'johnsonkyle@example.com',
    'phone_number': '764.882.4564x7428',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gabriel White',
    'George Ortega',
    'Mr. Jacob Graham',
    'Sherry Stafford',
    'Laura Williams',
    'Christopher Riley',
],
    'json': {
    'name': 'Randall Evans',
    'address': '001 Wilkerson Street\nFreemanland, AL 91207',
},
    'key94160': 'value50233',
    'key7383': 'value99940',
    'key96169': 'value81278',
    'key77977': 'value37931',
    'key32715': 'value90568',
    'key50548': 'value3837',
    'key41618': 'value64766',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Lisa Thomas',
    'address': 'Unit 1266 Box 5141\nDPO AE 78141',
    'text': 'Almost season direction clearly wish great call. Large visit doctor success career.\nBlood group special develop sport. Fall region there item.',
    'email': 'nhall@example.net',
    'phone_number': '(765)793-7091x8999',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Avila',
    'Daniel Thornton',
    'Donna Santos',
    'Chad Allen',
    'Crystal Miller',
    'Michael Dalton',
],
    'json': {
    'name': 'Samuel Richards',
    'address': '661 Diaz River\nNorth Bradley, MI 54950',
},
    'key38473': 'value18467',
    'key14359': 'value98464',
    'key5957': 'value3051',
    'key68358': 'value19756',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Amber Andrade',
    'address': '7475 Julie Coves\nPort Michaelville, VA 36036',
    'text': 'Expert girl action near three both. View together American join fine institution. Piece life audience leg.',
    'email': 'fordtimothy@example.com',
    'phone_number': '2483098952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Penny Rodriguez',
    'Daniel Brewer',
    'Jennifer Campbell',
    'Joe Barrera',
],
    'json': {
    'name': 'Katelyn Jennings',
    'address': '8901 Haas Motorway\nAlexanderport, LA 68883',
},
    'key99772': 'value16245',
    'key77240': 'value86568',
    'key81990': 'value96489',
    'key36580': 'value21571',
    'key67411': 'value60224',
    'key22822': 'value84297',
    'key59691': 'value94059',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Emily Schwartz',
    'address': 'PSC 4738, Box 4899\nAPO AE 99378',
    'text': 'Green represent plant knowledge western laugh.\nIssue mouth travel energy help region future. Relationship participant ground official fear. Small girl turn turn however.',
    'email': 'lbaldwin@example.com',
    'phone_number': '826-220-6014x8066',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Gilbert Mclean',
    'Michael Harmon',
    'Amber White',
    'Kathryn Durham',
    'Abigail Byrd',
    'Jose Ruiz',
    'Joseph Scott DVM',
    'David Wilson',
    'Kelsey Salazar',
],
    'json': {
    'name': 'John Owens',
    'address': '494 Woods Junctions\nDaviston, TN 14660',
},
    'key12376': 'value40890',
    'key82148': 'value68799',
    'key55539': 'value47059',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Alicia Joseph',
    'address': '88864 Rodgers Cape\nTammyfurt, MA 76204',
    'text': 'Manage believe fly address assume woman. Unit another particularly president big. Claim right east cover until to.\nSure professor theory receive type. Participant issue know avoid receive rise.',
    'email': 'andersoncharles@example.com',
    'phone_number': '(780)281-8009',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'William Strong',
    'Travis Nielsen',
    'Sarah Hines',
    'Christina Christensen',
    'Casey Sampson',
    'Shannon Edwards',
    'Alicia Petersen',
    'Erica Nguyen',
    'Jennifer Morris',
],
    'json': {
    'name': 'Bradley Johnson',
    'address': '8758 Marcus Road\nLake Annette, ID 63319',
},
    'key77294': 'value61487',
    'key23728': 'value18563',
    'key7742': 'value37446',
    'key36793': 'value15534',
    'key29181': 'value92497',
    'key23541': 'value81042',
    'key73342': 'value93396',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Carol Park',
    'address': '165 Teresa Way Apt. 592\nRoberthaven, NJ 46452',
    'text': 'Wall guy any together bit behavior. Reach south improve state.\nAlone ask far within. Carry population where production offer. Many claim feeling later.',
    'email': 'bjacobs@example.net',
    'phone_number': '+1-833-742-2313x31049',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Anderson',
    'Breanna Harris',
],
    'json': {
    'name': 'Ronald Mendoza',
    'address': '326 Erika Grove Suite 818\nAmandashire, VA 58169',
},
    'key8698': 'value79781',
    'key37931': 'value77742',
    'key26528': 'value75960',
    'key80224': 'value70382',
    'key11681': 'value68400',
    'key2245': 'value48900',
    'key79576': 'value47909',
    'key28128': 'value54306',
    'key59434': 'value29885',
    'key43345': 'value88252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Matthew Johnson',
    'address': '2007 Hancock Passage\nGaryton, PR 38213',
    'text': 'Force themselves particularly difference instead condition production either. She threat as want. Those thing cold case.',
    'email': 'davidtaylor@example.org',
    'phone_number': '428-399-0642x174',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Sanchez',
    'Joseph Pham',
    'Shane Morrison',
    'Evan Williams',
    'Sylvia Little',
    'Angel Taylor',
],
    'json': {
    'name': 'James Brown',
    'address': '0818 Charlene Mountain\nErichaven, CT 87455',
},
    'key8728': 'value20235',
    'key72154': 'value26917',
    'key86098': 'value18435',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Caleb Park',
    'address': '1199 Zuniga Garden Suite 757\nSouth Michelebury, PR 00696',
    'text': 'Eight win reason learn enough indicate responsibility. Long company law crime.\nHear economic industry ago customer. Politics against me property without public. Head go center smile pressure.',
    'email': 'alisontaylor@example.net',
    'phone_number': '(742)381-8763',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Stephens',
    'Leah Pitts',
    'Sheryl Williams',
    'Morgan Rojas',
    'Terry Hendricks',
    'Michelle Conway',
    'Donald Curtis',
    'Kyle King',
    'Tracy Murphy',
    'Dominique Webb',
],
    'json': {
    'name': 'Roy Stephenson',
    'address': '0372 James Curve Apt. 048\nStephenmouth, VA 22858',
},
    'key50988': 'value59986',
    'key64000': 'value91871',
    'key71650': 'value8600',
    'key87198': 'value79228',
    'key36765': 'value33948',
    'key40129': 'value50743',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Eric Johnson',
    'address': '94506 Rachel Stravenue\nSouth Philipbury, NY 98585',
    'text': 'Letter build yard site big executive relate. Listen system price economy through civil save. Sort project every simple ten tend project walk. Family standard road light.',
    'email': 'marilyn86@example.com',
    'phone_number': '001-402-861-9870x1092',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Donna Thompson',
    'Heather Roberts',
    'Brian Stone',
    'Deborah Jones',
    'Tracy Jefferson',
],
    'json': {
    'name': 'Christina Henry',
    'address': '579 Rachel Crescent\nKarenburgh, SC 19246',
},
    'key99522': 'value78813',
    'key72884': 'value5143',
    'key26663': 'value86361',
    'key91941': 'value21230',
    'key59922': 'value90362',
    'key30903': 'value99257',
    'key94457': 'value62729',
    'key26928': 'value20073',
    'key77737': 'value72205',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Fernando Castro',
    'address': '0350 Diaz Heights Suite 239\nEast Christine, NC 01196',
    'text': 'My often open himself recently. Material method true hundred. Down speak option hand. Travel fall situation on since.',
    'email': 'jessicahunter@example.com',
    'phone_number': '830-947-0532',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Marvin Rice',
    'Kevin Davis',
    'Tyler Reynolds',
    'Jennifer Young',
    'Stacy Riddle',
],
    'json': {
    'name': 'Amanda Smith',
    'address': '33540 Long Manor\nChapmanmouth, SC 82467',
},
    'key74581': 'value16519',
    'key88498': 'value26716',
    'key41660': 'value69032',
    'key57390': 'value73922',
    'key15914': 'value16393',
    'key76037': 'value72381',
    'key42655': 'value58231',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Pamela Lee',
    'address': 'Unit 7988 Box 2524\nDPO AA 41485',
    'text': 'Finish bed others admit. Those change project bed these trip work song.\nWrong mission sort course. Author just network push.\nMyself cultural participant you media. All decide meet west.',
    'email': 'danielrussell@example.net',
    'phone_number': '438.237.9716x2433',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Misty Lee',
    'Ryan Rose',
    'Jeffrey Ware DDS',
    'Victor Smith',
    'Bethany Burgess',
    'Charlotte Clark',
    'Nicholas Hayden',
    'Robert Owen',
    'Todd Richardson DDS',
],
    'json': {
    'name': 'Carrie Hart',
    'address': 'PSC 0860, Box 6614\nAPO AA 95234',
},
    'key73819': 'value26478',
    'key93691': 'value82596',
    'key86078': 'value52884',
    'key1943': 'value48303',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kimberly Dunn',
    'address': '515 Riley Springs Suite 343\nDebbiehaven, OR 14178',
    'text': 'Allow dream agree suddenly least great chair. Brother generation concern. Toward health father agency series. Half hand law imagine middle authority.',
    'email': 'raymondmartin@example.com',
    'phone_number': '469.854.5633x39885',
    'array_int_dynamic': [
    86718,
],
    'array_varchar_dynamic': [
    'James Faulkner',
    'Brittany Tyler',
    'Matthew Jones',
    'Elizabeth Cox',
    'Tracy Hogan',
    'Laurie Caldwell',
    'David Harris',
],
    'json': {
    'name': 'David Henderson',
    'address': '7970 Rhodes Parkway\nEast Pamelashire, NM 40970',
},
    'key70287': 'value93130',
    'key82290': 'value16056',
    'key89584': 'value82569',
    'key44325': 'value78599',
    'key80330': 'value56779',
    'key54104': 'value177',
    'key61455': 'value70386',
    'key73447': 'value42985',
    'key41833': 'value93521',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Joshua Bailey',
    'address': '281 Hayes Lodge Apt. 172\nPort Michealshire, DC 40413',
    'text': 'Project action attack fine number can wall. Range game manage arrive.',
    'email': 'smithmichael@example.org',
    'phone_number': '377-267-0543',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Charles Watson',
    'Mary Miller',
    'John Garza',
    'Shelly Lester',
    'Leslie Hood',
    'Emily Meyers',
],
    'json': {
    'name': 'Janet Clark',
    'address': '484 Lauren Dam Apt. 202\nLake Michael, HI 58969',
},
    'key78150': 'value13549',
    'key46799': 'value71792',
    'key55998': 'value36424',
    'key97556': 'value19920',
    'key48194': 'value53667',
    'key54441': 'value40102',
    'key52571': 'value21637',
    'key72637': 'value1498',
    'key80948': 'value80977',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Tracy Dodson',
    'address': '27655 Diane Prairie\nCindychester, OR 44124',
    'text': 'Remain section civil hard international Mrs senior effect. Weight which its your rule within not.\nHis loss program few away. Popular brother financial. Section southern support school national.',
    'email': 'maria31@example.com',
    'phone_number': '+1-865-868-0902x3484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jimmy Peterson',
    'Michael Chapman',
    'James Wells',
    'Albert Castaneda',
    'Jeffrey Hurley',
    'Peter Smith',
    'Jennifer Lowe',
],
    'json': {
    'name': 'Elizabeth Johnson',
    'address': '0709 Ruiz Streets Suite 006\nLake Debbieton, AZ 36919',
},
    'key92424': 'value35526',
    'key45244': 'value61759',
    'key40003': 'value57204',
    'key30430': 'value33604',
    'key25910': 'value80666',
    'key72435': 'value2527',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Julia Brown',
    'address': '38053 Ariana Locks Suite 928\nAlvaradoport, KS 58745',
    'text': 'Effect least wind animal. Budget community table dark water build. Away painting believe determine black market environmental.',
    'email': 'belljoseph@example.org',
    'phone_number': '001-275-955-9816x968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Gregory',
    'Jessica Peterson',
    'James Rivera',
    'Renee Cardenas',
],
    'json': {
    'name': 'Debbie Simpson',
    'address': '93662 Cortez Port Suite 064\nNorth Patrick, GA 95273',
},
    'key79498': 'value22800',
    'key46709': 'value54380',
    'key22365': 'value21578',
    'key98023': 'value93766',
    'key63796': 'value61087',
    'key69139': 'value91489',
    'key7865': 'value86232',
    'key6697': 'value50147',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Cody Flynn',
    'address': '542 Jamie Drives\nLake Angelica, KY 83737',
    'text': 'Resource eight series billion test coach hour article. Blood friend pass song. Example smile election meeting speak treatment. Win against note.',
    'email': 'tmcgee@example.org',
    'phone_number': '001-711-346-9197x20457',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Morris',
    'Vanessa Spencer',
    'Steven Vaughan',
    'Jill Atkins',
    'Christopher Reyes',
],
    'json': {
    'name': 'Jennifer Neal',
    'address': '5111 Miller Drive Suite 805\nLake Jack, SC 16215',
},
    'key15087': 'value83789',
    'key18947': 'value97656',
    'key39356': 'value73948',
    'key1634': 'value33859',
    'key81869': 'value21243',
    'key82771': 'value58484',
    'key42640': 'value16253',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Rodney Morgan',
    'address': '7362 Smith Views Apt. 638\nJonestown, TN 15298',
    'text': 'Quality prevent lay owner improve well. Visit note size very appear financial to. Level build tonight interesting share.\nWeek toward to society.',
    'email': 'brasmussen@example.org',
    'phone_number': '001-962-705-1666x952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Walker',
],
    'json': {
    'name': 'Amanda Wolf',
    'address': '01351 Robert Stream Apt. 270\nYounghaven, OK 07197',
},
    'key84168': 'value86312',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Cindy Carrillo',
    'address': '6285 Clark Ports Suite 228\nWoodborough, FL 65125',
    'text': 'Wait wear off enter alone get share defense. Inside identify later else.\nUnder raise push share here for. Society per want space. Very look place book. Five moment short author.',
    'email': 'urodriguez@example.org',
    'phone_number': '(733)275-3061x031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joel Hinton',
    'Julie Ferrell',
],
    'json': {
    'name': 'Philip Frank',
    'address': '35377 Mark Shore\nMackenzieborough, AR 58225',
},
    'key5564': 'value4892',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Austin Jacobs',
    'address': '2587 Melanie Mountains\nMccarthyfurt, CT 28562',
    'text': 'Describe activity likely suddenly level reduce. Meet direction which prepare soldier meet. Figure woman field picture school enjoy represent walk.',
    'email': 'harrisonmary@example.org',
    'phone_number': '001-622-575-6147',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert Martin DDS',
    'Jennifer Bennett',
    'Meredith Kelly',
    'Shawn Hunt',
    'Kimberly Cameron',
    'Angelica Carpenter',
],
    'json': {
    'name': 'William Williams',
    'address': '83487 Paige Turnpike Suite 995\nEast Maryburgh, UT 46794',
},
    'key98549': 'value74453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Nicholas Stone',
    'address': '6344 Barber Mission Apt. 342\nLake Sherrystad, NY 48988',
    'text': 'Experience bring accept future ten individual yeah up. Create enter use student wide drop reach.\nEver remember base whose how media skill. That point generation whom want.',
    'email': 'lejacqueline@example.org',
    'phone_number': '6376340160',
    'array_int_dynamic': [
    99909,
],
    'array_varchar_dynamic': [
    'Angela Meyer',
    'Kelly Mason',
    'Mr. Andrew Lynch III',
    'Charlene Huff',
    'William Wilson',
    'Steven Howard',
    'Jeremy Berry',
    'Daniel Combs',
    'Diane Wilkinson',
    'Sandra Hurst',
],
    'json': {
    'name': 'Daniel Chapman',
    'address': '12693 Bell Fork\nVasquezview, NJ 62649',
},
    'key26782': 'value57465',
    'key35358': 'value35955',
    'key71257': 'value50990',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Elizabeth Nguyen',
    'address': 'PSC 6561, Box 2275\nAPO AE 64926',
    'text': 'Suddenly evening happen begin various particularly. Prevent address price enter.',
    'email': 'wcarlson@example.net',
    'phone_number': '8215472921',
    'array_int_dynamic': [
    79905,
],
    'array_varchar_dynamic': [
    'Tony Miller',
    'Richard Mcfarland',
    'Christopher Marquez',
    'Calvin Larson',
    'Sara Brown',
    'Michelle Travis',
    'Jesse Torres',
    'Albert Martinez',
    'Sergio Wilson',
    'Teresa Shields',
],
    'json': {
    'name': 'Kim Reyes',
    'address': '141 Jessica Rapids Suite 987\nPort Wendyborough, AR 56358',
},
    'key92555': 'value37701',
    'key7480': 'value63386',
    'key57622': 'value72916',
    'key37293': 'value92707',
    'key89141': 'value45287',
    'key31835': 'value79625',
    'key77473': 'value82659',
    'key80184': 'value93883',
    'key94367': 'value4269',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Kristy Harmon',
    'address': '0602 Vincent Inlet\nNew Phillip, TX 80095',
    'text': 'Others civil wife from wall fast. Together receive indeed air decision.\nGeneral build something top. Industry small around from mother economy total.',
    'email': 'adamsdebra@example.org',
    'phone_number': '694.758.2103x5133',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sierra Thomas',
    'Brittany Wong',
    'Marissa Adams',
    'Kathryn Martinez',
    'Matthew White',
    'Natalie Pearson',
    'Elizabeth Brown',
],
    'json': {
    'name': 'Denise Keith',
    'address': '02429 Rosario Cliffs Suite 435\nNorth Heatherbury, MH 93809',
},
    'key46971': 'value49742',
    'key44148': 'value84593',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Carla Anderson',
    'address': '5838 Strong Mall\nMarkland, AL 80145',
    'text': 'Current soldier event clearly. Help including rate decade best happen state. General better inside main free tax star class.\nWhat them officer. Decade sound world impact research laugh about.',
    'email': 'jodyfarmer@example.com',
    'phone_number': '238-630-1685x40643',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Delgado',
    'Jason Franklin',
    'Mary Wheeler',
    'Joshua Copeland',
    'Christopher Williams',
    'Andrea Payne',
],
    'json': {
    'name': 'Jessica Hayes',
    'address': '14541 Matthews Walk\nKelseyton, NV 98085',
},
    'key46286': 'value6779',
    'key39989': 'value58418',
    'key49091': 'value72507',
    'key45462': 'value16825',
    'key90349': 'value29183',
    'key78466': 'value69182',
    'key32068': 'value15803',
    'key98238': 'value64760',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Leslie Smith',
    'address': '197 Lisa Burg\nLake Sandra, HI 03595',
    'text': 'Feel turn them her prevent follow. Present young water participant about. High read bill give employee.',
    'email': 'sean45@example.org',
    'phone_number': '916.991.7069',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Burton',
    'Joshua Schmidt',
    'Kimberly Navarro',
    'Gary Meza',
    'Robert Green',
    'Melissa Lopez',
],
    'json': {
    'name': 'Brian Oliver',
    'address': '73095 Jack Curve\nWest Johnport, ME 25167',
},
    'key89394': 'value66221',
    'key21475': 'value81696',
    'key21746': 'value59888',
    'key10825': 'value92922',
    'key57405': 'value23706',
    'key76493': 'value27778',
    'key41064': 'value23602',
    'key12419': 'value11789',
    'key29039': 'value20109',
    'key35389': 'value93769',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Valerie Blanchard',
    'address': '7354 Christopher Inlet Suite 335\nLake Heatherborough, GA 88797',
    'text': 'Next itself voice price ready let. Investment service give we language simple surface officer. Region actually story leave view discover remember.\nMind treat contain four happen.',
    'email': 'wilsonmartin@example.com',
    'phone_number': '001-967-959-3015x639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'David Graham',
    'Jennifer Deleon',
    'Cindy Mcdaniel',
],
    'json': {
    'name': 'Kelsey Rosales PhD',
    'address': '0800 Burke Lock Apt. 460\nJerryville, AK 55345',
},
    'key55354': 'value10873',
    'key25535': 'value79441',
    'key50586': 'value48121',
    'key73392': 'value52564',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Stacy Castillo',
    'address': 'PSC 3581, Box 0279\nAPO AE 01740',
    'text': 'Out responsibility this Mr forward. Trip character condition trouble throw seat. Foreign knowledge throw debate discover. Firm bill involve face ok.',
    'email': 'adamwilson@example.com',
    'phone_number': '+1-222-783-0960x085',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'John Glass',
    'Sharon Smith',
    'Mr. Joseph Robinson',
    'Kathryn Moreno',
],
    'json': {
    'name': 'Margaret Willis',
    'address': '53860 Beth Glens\nPaulchester, MH 89701',
},
    'key16332': 'value78981',
    'key86028': 'value20182',
    'key744': 'value85514',
    'key31152': 'value3220',
    'key7399': 'value72396',
    'key2663': 'value66920',
    'key98856': 'value65660',
    'key56676': 'value38354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Jennifer Meadows',
    'address': '55024 Booker Shoals\nSandrashire, CA 89853',
    'text': 'Size sometimes as interest. Choose scene accept baby. Time Mrs many teach that.\nClear choice defense clearly give. East evidence interview record involve fund.',
    'email': 'oesparza@example.net',
    'phone_number': '001-994-768-6790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Hill',
    'Lori Moore',
    'Brenda Santiago',
    'Christopher Burns',
    'Alyssa Hickman',
    'Rachel Beard',
    'Christopher Jones',
    'Joshua Smith',
    'Timothy Phillips',
    'Nicole Russell',
],
    'json': {
    'name': 'Hayden Knight',
    'address': 'Unit 2505 Box 5886\nDPO AE 38404',
},
    'key38441': 'value40837',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kelli Brown',
    'address': 'PSC 3095, Box 6529\nAPO AP 40882',
    'text': 'Civil available policy kind across environment enter deep. Guess create according describe sport suffer. Alone method situation bit responsibility.',
    'email': 'ellenyork@example.net',
    'phone_number': '229-251-6654',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Lynch',
    'Nicole Jones MD',
    'Michael Johnson',
    'Stephen Brooks',
    'Sheryl Reyes MD',
    'Jose Walker',
    'Veronica Walters',
    'Elizabeth Lopez',
    'Debra Ortiz',
    'Lori Simon',
],
    'json': {
    'name': 'Connie Johnson',
    'address': '4783 Lozano Parks Apt. 189\nHeathertown, NE 82464',
},
    'key32507': 'value38496',
    'key17566': 'value11651',
    'key10626': 'value65312',
    'key16032': 'value79940',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Shawn Rowe',
    'address': 'USS Fox\nFPO AP 06439',
    'text': 'Reach set police force political. Then check degree fall within school.',
    'email': 'mjackson@example.net',
    'phone_number': '6376694103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole English',
    'Johnny Cunningham',
    'Andrew Stone',
    'Jacob Morrison',
    'Jeremy Gonzalez',
    'Eugene Moss',
    'Carlos Fernandez',
    'Holly Benson',
    'Michael Johnson',
    'Melanie Alexander',
],
    'json': {
    'name': 'Mitchell Mcintyre',
    'address': 'Unit 5449 Box 0695\nDPO AP 92617',
},
    'key72719': 'value50827',
    'key26439': 'value9818',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Kevin Jones',
    'address': '4294 Marshall Parkways\nNorth Christina, MA 58713',
    'text': 'Memory community particularly my star resource security. Style fight talk how dog serve. Source image head other guess strong south even.',
    'email': 'clambert@example.org',
    'phone_number': '(414)570-2112x344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Carrie Dixon',
],
    'json': {
    'name': 'Ashley Rogers',
    'address': '168 Cynthia Ramp Suite 050\nNew Clayton, FM 76821',
},
    'key2515': 'value86170',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Leslie Solis',
    'address': '9032 Munoz Pines\nDorseytown, NC 30974',
    'text': 'Like Congress people position create property case along. Your at fear not yes during. Expert grow actually media action watch head happen. Main here serious news.',
    'email': 'imartinez@example.net',
    'phone_number': '986-931-6240x91768',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Bridget Simpson',
    'Russell Williams',
    'Michael Andrews',
],
    'json': {
    'name': 'Michael Burns',
    'address': '7804 Smith River Suite 066\nGreentown, DE 15103',
},
    'key83602': 'value40127',
    'key34103': 'value8357',
    'key49372': 'value50928',
    'key7357': 'value98207',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Dr. Matthew Ho',
    'address': '06972 Cook Point\nCarrilloland, WA 11126',
    'text': 'Party year thousand over owner. Treat drop brother.\nReveal anyone public yet human. Nothing provide none letter war road look. Spend reflect chair picture phone no.',
    'email': 'brian04@example.net',
    'phone_number': '505.926.0257x7102',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Allen',
    'Sara Little',
    'Matthew Johnson',
    'Rebecca Tyler',
    'Benjamin Richards',
],
    'json': {
    'name': 'Amanda Frey',
    'address': 'PSC 2796, Box 1631\nAPO AA 10027',
},
    'key59867': 'value68918',
    'key74233': 'value22147',
    'key82973': 'value55668',
    'key3042': 'value62572',
    'key58368': 'value16162',
    'key87071': 'value8856',
    'key63443': 'value69415',
    'key50110': 'value3295',
    'key17995': 'value93456',
    'key68429': 'value48153',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Rebecca Robinson',
    'address': '7090 Samuel Locks\nSheenashire, UT 66594',
    'text': 'Plant visit opportunity hand prevent cell. Some left network budget enter cultural impact. Especially a door within.',
    'email': 'sally01@example.net',
    'phone_number': '(825)981-2596x204',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Logan Johnson',
    'April Ortiz',
    'John Hayes',
    'Dr. Matthew Cannon DDS',
    'Collin Meyer',
    'Karen Huff',
    'Barry Gross',
],
    'json': {
    'name': 'Jon Jones',
    'address': '82982 Richardson Hill Apt. 015\nNorth Jennifer, IN 29869',
},
    'key99813': 'value43760',
    'key733': 'value79925',
    'key74032': 'value52339',
    'key11237': 'value29540',
    'key7402': 'value51166',
    'key15625': 'value28393',
    'key41082': 'value99353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Karen Myers',
    'address': '583 Brandon Mountain Apt. 989\nPort Jessica, LA 08920',
    'text': 'Still such close career threat agreement. Seek stay role support.\nAccept size religious red cell. Mention against risk.\nBack spend information quality be again whom. Do risk give player personal leg.',
    'email': 'jwilliams@example.net',
    'phone_number': '4372300791',
    'array_int_dynamic': [
    30522,
],
    'array_varchar_dynamic': [
    'Erika Kelly',
    'Nancy Brown',
    'Kevin Morales',
    'Jamie Mason',
],
    'json': {
    'name': 'Kristen Torres',
    'address': '7141 Brian Haven Suite 967\nJosephborough, SC 53599',
},
    'key14135': 'value31910',
    'key17044': 'value61831',
    'key77108': 'value18827',
    'key9684': 'value84891',
    'key21261': 'value71675',
    'key3481': 'value51798',
    'key65763': 'value38535',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Kyle Cooper',
    'address': '038 Ramsey Expressway Apt. 372\nDavidstad, HI 11784',
    'text': 'Career draw industry suddenly can. Order professor lose those break.\nPoint surface quickly whether. Yes not success claim career perhaps wish beat.',
    'email': 'dianamaldonado@example.net',
    'phone_number': '338.809.8954x20097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Seth Snyder PhD',
    'Christopher Rodriguez',
    'James Green',
],
    'json': {
    'name': 'Erin Mcclure',
    'address': '76892 Perry Field\nLake Jenniferborough, FM 48988',
},
    'key38099': 'value80648',
    'key70705': 'value98747',
    'key4858': 'value11676',
    'key11723': 'value84485',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Shane Hernandez',
    'address': '6952 Sean Road\nPort Cynthiaberg, WV 76321',
    'text': 'Campaign talk wide investment hard policy case break. Spend particular population front development wait.',
    'email': 'carolynreyes@example.com',
    'phone_number': '878.815.3768x20877',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Ramirez',
    'Lauren Hart',
    'Robert Lopez',
],
    'json': {
    'name': 'Elizabeth Schneider',
    'address': '6982 Amanda Street\nSouth Nicole, DC 23445',
},
    'key42416': 'value64499',
    'key76001': 'value93833',
    'key15449': 'value99430',
    'key29826': 'value59304',
    'key4924': 'value29613',
    'key46499': 'value63427',
    'key16310': 'value17223',
    'key19285': 'value82084',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'David Lewis',
    'address': '8387 Perez Points Suite 737\nMitchellview, NE 94191',
    'text': 'Trouble political accept letter spring budget. Institution music support simply. Political me character past grow establish.',
    'email': 'edwardperry@example.org',
    'phone_number': '001-507-976-8118',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Beth Tucker',
    'Sara Warner',
    'Anthony Wagner',
    'Joshua Garza',
    'Dr. Alexander Brown',
    'Luis Young',
],
    'json': {
    'name': 'Ryan Wilson',
    'address': '10578 Taylor Roads\nPearsonmouth, NM 71433',
},
    'key42695': 'value77090',
    'key38215': 'value79219',
    'key22506': 'value94867',
    'key22785': 'value34854',
    'key54660': 'value706',
    'key20303': 'value99233',
    'key68756': 'value87160',
    'key88154': 'value61178',
    'key26881': 'value61644',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Joseph Oconnor',
    'address': '503 Corey Estates\nPort Kelsey, VA 59623',
    'text': 'Letter act arm sense fear read believe. Affect in adult fund.\nLarge tough picture name give.',
    'email': 'kellybenjamin@example.net',
    'phone_number': '001-489-348-2891x84736',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Cruz',
    'Jennifer Hopkins',
],
    'json': {
    'name': 'Charles Schneider',
    'address': '501 James Ports Apt. 011\nJessicahaven, UT 12897',
},
    'key80075': 'value50312',
    'key72532': 'value718',
    'key84252': 'value46475',
    'key60787': 'value78401',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Ashley Owens',
    'address': '7783 Monique Hills Apt. 258\nVanessaberg, NC 39713',
    'text': 'Contain such big stay imagine outside technology ok. Politics fish sign such watch.\nShake pay enjoy court our feeling development. Others expect mission structure step lot step. Try land bank.',
    'email': 'clarkstephanie@example.org',
    'phone_number': '+1-803-482-4551x113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Austin',
    'John Chen',
    'Daniel Montgomery',
    'Anna Hughes',
    'Cindy Clark',
],
    'json': {
    'name': 'Jermaine Peterson',
    'address': '2892 Mark Views\nLeetown, SD 89722',
},
    'key38065': 'value31236',
    'key10346': 'value97023',
    'key68876': 'value3717',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Earl Turner',
    'address': '666 Thompson Lodge Suite 838\nGlennside, MP 75416',
    'text': 'Current special military artist. Event today traditional. Nearly use behind brother their. Leg respond year training.\nAny what thought trial worker report radio. Administration citizen spring hear.',
    'email': 'jennifer08@example.net',
    'phone_number': '+1-542-831-3241x2529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Edwards',
    'Rachel Roberts',
    'Paul Petersen',
    'Cassandra Porter',
    'Regina Lopez',
],
    'json': {
    'name': 'Larry Kennedy',
    'address': '2608 Miller Fork\nDavidbury, NC 21236',
},
    'key25318': 'value77965',
    'key56759': 'value14040',
    'key98317': 'value58576',
    'key47913': 'value88047',
    'key95938': 'value81408',
    'key22136': 'value75011',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Thomas Dawson',
    'address': '7088 Bridges Causeway Suite 930\nBrianburgh, AZ 69391',
    'text': 'Consumer election process require account his. Music well member other professional.\nWithin friend sit. Report rock item record pay ever.',
    'email': 'farrelljeremy@example.org',
    'phone_number': '001-394-534-1318',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'David Thompson',
    'Jessica Jones MD',
    'Jeffery Mann',
    'Jerry Thomas',
    'Nicole Perry',
    'Diana Smith',
    'Nancy Palmer',
    'Richard Peterson',
    'Michael Garcia',
],
    'json': {
    'name': 'Holly Hernandez',
    'address': '87014 Ashley Coves\nEast David, IN 90782',
},
    'key31810': 'value72711',
    'key49181': 'value65351',
    'key37023': 'value95257',
    'key33855': 'value73796',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michael Armstrong',
    'address': '1032 Anderson Roads\nNorth Jacob, RI 88953',
    'text': 'Their man serious rule person finish. Hard bank really their every energy moment. Everything lawyer wall number force such too. High color traditional whole defense likely.',
    'email': 'michaellopez@example.net',
    'phone_number': '+1-771-318-3784x061',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Page',
    'Robin Petersen',
    'Nicholas Burke',
    'Kevin Camacho',
],
    'json': {
    'name': 'Melissa Hernandez DDS',
    'address': '9145 Parker Causeway Apt. 725\nJonesfort, CA 98543',
},
    'key46331': 'value69740',
    'key45698': 'value97920',
    'key37360': 'value47905',
    'key63312': 'value21343',
    'key84314': 'value15794',
    'key37201': 'value46683',
    'key88438': 'value49314',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Bradley Shaw',
    'address': 'Unit 8872 Box 8486\nDPO AE 39738',
    'text': 'Less represent mother despite. Evening board owner where defense agreement. Human tax attorney education adult free charge rate.',
    'email': 'joy66@example.net',
    'phone_number': '9142175285',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'David Mendoza',
    'Dawn Henderson',
    'Charles Huffman',
    'Jennifer Wilson',
    'Jason Russell MD',
    'Tammy Clark',
    'Timothy Suarez',
    'Mary Ruiz',
    'Jordan Harris',
    'Brian Bolton',
],
    'json': {
    'name': 'Thomas Mcintosh',
    'address': '401 Steven Lodge Suite 072\nNicholeview, IN 07319',
},
    'key7621': 'value92044',
    'key28301': 'value31970',
    'key4285': 'value39079',
    'key72539': 'value19759',
    'key53419': 'value88469',
    'key23236': 'value72864',
    'key6352': 'value58564',
    'key70870': 'value30313',
    'key59008': 'value47046',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Crystal Burns',
    'address': '99802 Adams Drives Apt. 064\nWernerchester, SD 74789',
    'text': 'Care Democrat front choice. Upon military like beautiful parent lawyer. Field ok environmental pattern Democrat rule.',
    'email': 'meganbrown@example.com',
    'phone_number': '(903)843-1258x17484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Rice',
    'Greg Rivera',
],
    'json': {
    'name': 'Casey Thomas',
    'address': '59854 Dennis Summit\nNew Davidmouth, SD 88587',
},
    'key86308': 'value41889',
    'key93494': 'value46507',
    'key54101': 'value9190',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Gail Smith',
    'address': '199 Stacy Harbors Suite 518\nAaronburgh, IA 51725',
    'text': 'Law whole make everyone hope relate. Away speak try.\nDebate difficult itself group choice even. Board mention usually factor lot.\nKey indicate miss economy respond.',
    'email': 'wcoleman@example.com',
    'phone_number': '+1-324-628-6706x17692',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Anderson',
    'Shari Lester',
    'Jaclyn Miller',
    'Emily Ellis',
    'Nicole Waters',
    'Steven Brandt',
    'Keith Bell',
    'Carly Thompson',
    'Leslie Wilson',
    'Joan Jones',
],
    'json': {
    'name': 'Melinda Chen',
    'address': '140 Rodgers Estate Suite 841\nNashtown, FM 91391',
},
    'key85891': 'value23567',
    'key87838': 'value58081',
    'key66767': 'value66814',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Valerie Dawson',
    'address': 'Unit 6512 Box 4434\nDPO AE 83723',
    'text': 'Show top chance cultural.\nTelevision talk news tend only box safe. Score project per image pattern evidence position. Effort husband set school although benefit student.',
    'email': 'jeanfowler@example.org',
    'phone_number': '432-492-8983',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Zhang',
    'Rachel Smith',
    'Stacie Morales',
    'Amber Brown',
    'Christy Rodriguez',
],
    'json': {
    'name': 'Andrea Hansen',
    'address': '6387 Hudson Drive Apt. 803\nLorettamouth, MD 62443',
},
    'key54387': 'value72999',
    'key33748': 'value87996',
    'key54199': 'value51954',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Walter Alvarado',
    'address': 'Unit 1592 Box 3184\nDPO AA 59979',
    'text': 'Why billion nature resource scene economy during. Draw family consumer of north need behavior. Stay size order.\nSuffer reality hand identify business. Writer though evidence win back.',
    'email': 'joneschristopher@example.net',
    'phone_number': '+1-485-512-1129x107',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Wanda Hansen',
    'Samantha Adams',
    'Laurie Mckay',
    'Joshua Lucas',
],
    'json': {
    'name': 'Samantha Warren',
    'address': '493 Brett Mill Suite 109\nRebeccahaven, NE 15071',
},
    'key10163': 'value99986',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Paul Johnson',
    'address': '1307 Paul Lodge Suite 888\nWest Julia, DE 02982',
    'text': 'Continue prepare campaign center about enter usually. Goal ready situation do. How together hit black its rule peace even.',
    'email': 'deanjose@example.org',
    'phone_number': '(878)227-8010',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Julia King',
    'David Snyder',
    'Jamie Stone',
    'Richard Wilson',
    'David Jones',
    'Hannah Flores',
    'Susan Rice',
    'Timothy Sims',
    'Katie Mathis',
],
    'json': {
    'name': 'Kent Lewis',
    'address': '53491 Campbell Glens\nSinghbury, RI 43234',
},
    'key86714': 'value42066',
    'key58601': 'value99718',
    'key75919': 'value10670',
    'key97804': 'value6246',
    'key12990': 'value23730',
    'key54620': 'value8163',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Erin Lucas',
    'address': '40027 Paul Manors Suite 766\nLake Patriciaborough, NM 23464',
    'text': 'Action stay pretty ball ask important. Near first wall throughout increase.\nNewspaper collection include section source. Against list hold point beautiful act peace.',
    'email': 'crystal79@example.com',
    'phone_number': '9672595979',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Paul Johnson',
    'Janice Garcia',
    'Benjamin Snyder',
    'Angela Campbell',
    'Debra Mcconnell',
    'Dana Watson',
    'William Branch',
],
    'json': {
    'name': 'Jasmine Johnson',
    'address': '585 Joshua Rapid\nJackmouth, MA 57836',
},
    'key85344': 'value77647',
    'key92075': 'value38959',
    'key94108': 'value11976',
    'key38406': 'value27068',
    'key17263': 'value38443',
    'key84573': 'value34269',
    'key84878': 'value99252',
    'key7585': 'value89907',
    'key42015': 'value27803',
    'key22263': 'value49453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Monica Phillips',
    'address': '722 Tran Crest\nNicolasport, NH 52109',
    'text': 'Accept general throw less early other find. Foreign thing best at address government. Its instead him long.\nEffort past inside above modern. Material value identify brother phone.',
    'email': 'danieljoshua@example.org',
    'phone_number': '762.453.7576',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Valdez',
    'Christopher Baldwin',
    'Jackie Ellis',
    'Gabriela Smith',
    'Lauren Long',
    'Phillip Morgan',
    'Janet Vega',
    'Thomas Webb',
    'Jeremy Dyer',
    'Karen Anthony',
],
    'json': {
    'name': 'Ariel Rogers',
    'address': '025 Smith Overpass Suite 447\nAriasmouth, IN 81425',
},
    'key54796': 'value71678',
    'key83403': 'value36583',
    'key52044': 'value15949',
    'key18060': 'value11616',
    'key6904': 'value57344',
    'key25957': 'value40877',
    'key24454': 'value83687',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Melissa Mitchell',
    'address': '17385 Laura Manors Apt. 575\nSouth Tamarashire, AR 87381',
    'text': 'Heart hospital around white item. Author method far. Also north every however.\nDevelopment improve look. Politics financial deep market student.',
    'email': 'nharris@example.com',
    'phone_number': '664.250.0974x978',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Holly Murillo',
    'Colin Miranda',
    'Emily Franco DVM',
],
    'json': {
    'name': 'Lindsay Mendoza',
    'address': '7151 Murphy Point\nNew Jade, NE 12339',
},
    'key79916': 'value42033',
    'key21293': 'value79833',
    'key47690': 'value48192',
    'key25194': 'value73892',
    'key33300': 'value27622',
    'key51460': 'value6258',
    'key29623': 'value68420',
    'key18906': 'value82733',
    'key70021': 'value71128',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Gabriel Lawson',
    'address': '8251 Frazier Ways Apt. 169\nSchultzmouth, NC 11381',
    'text': 'Course family food yeah rock surface. Smile discover short score music. Give security tax note stage discuss. Pay dream image positive away.',
    'email': 'simpsondaniel@example.com',
    'phone_number': '(239)856-6068',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mark Lopez',
],
    'json': {
    'name': 'Paul Miller',
    'address': '7277 Robin Junctions\nStonetown, MD 29830',
},
    'key902': 'value99454',
    'key91792': 'value93925',
    'key72224': 'value38906',
    'key79004': 'value83878',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Connie Bailey',
    'address': '5022 Murray Centers Apt. 817\nBrownchester, VI 80759',
    'text': 'Left usually part down which. However area finally factor beat serve because. Often rise southern official interest.',
    'email': 'judy22@example.com',
    'phone_number': '+1-561-260-6648x4221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jesus Myers',
    'Cheryl Noble',
    'Joseph Craig',
    'Lisa Giles',
    'Amanda Brown',
],
    'json': {
    'name': 'Rebecca Foster',
    'address': '2610 Gaines Mountain Apt. 197\nSouth Crystalmouth, DC 35701',
},
    'key47599': 'value24197',
    'key24568': 'value3655',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Keith Wright',
    'address': 'Unit 8671 Box 5220\nDPO AA 21821',
    'text': 'She chance yard. Throughout large enjoy involve worker teach professional.\nFeel eight some risk finally. Sing reveal same brother difficult central design.',
    'email': 'richardyoung@example.org',
    'phone_number': '001-248-633-2973x1090',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kristin Hill',
    'Kathleen Santiago',
    'Dwayne Doyle',
    'David Guzman',
    'Albert Ho',
    'Dr. Eddie Rush',
    'Patricia Lamb',
],
    'json': {
    'name': 'Matthew Schaefer',
    'address': '3576 Amber Fall\nPort Sarahbury, WA 76636',
},
    'key87679': 'value12834',
    'key63188': 'value8867',
    'key24465': 'value13954',
    'key41179': 'value50256',
    'key2711': 'value44846',
    'key99788': 'value50766',
    'key72637': 'value64474',
    'key54577': 'value12127',
    'key44812': 'value24116',
    'key84782': 'value43860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Wendy Wheeler',
    'address': '2388 Alexa Forges Suite 865\nNorth Laurafort, FM 57147',
    'text': 'Career lay industry each energy century particularly. Everything these run particular rest car me. Make politics this himself.\nGas Congress ready each family would. Fall recently agent church.',
    'email': 'michaelarmstrong@example.com',
    'phone_number': '888-473-7755',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Wendy Garcia',
    'Amber Lee',
    'Melissa Woods',
    'April Williams',
    'Linda Shah',
    'Brandon Klein',
    'Ashley West',
],
    'json': {
    'name': 'Dr. Eric Young',
    'address': '25844 Lisa Row\nNormanfort, KY 30478',
},
    'key68870': 'value87207',
    'key6299': 'value21295',
    'key89165': 'value27635',
    'key91700': 'value83144',
    'key96182': 'value13273',
    'key25574': 'value37107',
    'key4195': 'value63389',
    'key19353': 'value64099',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Matthew Wilson',
    'address': '9605 Michele Fork Suite 447\nLake Brandy, NC 58511',
    'text': 'Development among idea church eight whom. What best until claim military maintain beautiful.\nDinner I always avoid scientist allow performance. Long cause church daughter policy tax occur question.',
    'email': 'stacytucker@example.com',
    'phone_number': '(485)613-6789x85660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Peterson',
    'Mr. Robert Tanner III',
],
    'json': {
    'name': 'Lawrence Wallace',
    'address': 'PSC 4454, Box 8855\nAPO AE 94619',
},
    'key20317': 'value86026',
    'key30727': 'value84995',
    'key13425': 'value58275',
    'key79125': 'value69270',
    'key39078': 'value59257',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Nancy Bates',
    'address': '5821 Chris Well Suite 704\nNorth Kristinastad, OH 62089',
    'text': 'The blood friend. Hold statement participant yeah language thus fund.\nCommunity out decision control name than. Information over low bill music.',
    'email': 'savannahwilliamson@example.org',
    'phone_number': '5255314206',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Baker',
],
    'json': {
    'name': 'Erika Murillo',
    'address': 'Unit 3347 Box 8546\nDPO AP 79314',
},
    'key1479': 'value40578',
    'key50579': 'value25823',
    'key42068': 'value11372',
    'key47515': 'value1673',
    'key40951': 'value24783',
    'key7789': 'value79791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Zachary Maynard',
    'address': '9816 Hurst Plaza\nDawnbury, MP 27850',
    'text': 'Security learn provide investment draw. Structure whole happy support student laugh.\nEver author model indeed star star career. Side sort recognize lay own behavior.',
    'email': 'susan40@example.com',
    'phone_number': '+1-896-756-4665x821',
    'array_int_dynamic': [
    19189,
],
    'array_varchar_dynamic': [
    'Lisa Johnson',
    'Austin Bailey',
    'Miguel Mcgee',
],
    'json': {
    'name': 'Charles Dean',
    'address': '2609 Briana Crossing Suite 442\nRobertland, MP 12097',
},
    'key59708': 'value80309',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Jason Shaw',
    'address': '94396 Perez Wall Apt. 564\nNew Evelyn, CO 80988',
    'text': 'Small challenge under. Take election travel model budget discover interview. Structure position tax difficult.',
    'email': 'henry42@example.org',
    'phone_number': '001-523-391-3291',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Calvin Lyons',
    'Henry Nunez',
    'Erin Morgan',
    'Nathan Cameron',
    'Charlotte Hernandez',
    'Jeffrey Rodriguez',
    'Jane Patterson',
    'Danielle Curry',
    'Melissa Murray',
    'John Johnson',
],
    'json': {
    'name': 'Eric Carpenter',
    'address': '777 Haynes Mission\nCodyfort, ID 63440',
},
    'key74804': 'value96233',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Brent Gross',
    'address': '00146 Melissa Radial Suite 928\nWest Victorfurt, TN 89078',
    'text': 'Plant official room turn politics lawyer. Position vote debate traditional.\nEnter base possible follow sort degree center. Team whatever artist church hear write who.',
    'email': 'christopherrowe@example.org',
    'phone_number': '989-903-3845x7263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Robert Massey',
],
    'json': {
    'name': 'Sandra Morales',
    'address': '09691 Stewart Ville\nNew William, OH 25867',
},
    'key95884': 'value79430',
    'key97992': 'value97495',
    'key43449': 'value32352',
    'key83624': 'value49212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jordan Maldonado',
    'address': '6124 Carroll Drive Suite 439\nEast Dana, GU 05583',
    'text': 'Yeah with order oil treat. Detail reflect first.\nPractice near PM rate. Specific sound challenge road water. Mr fall class safe tax writer risk.',
    'email': 'crystal71@example.net',
    'phone_number': '001-201-799-3608x4092',
    'array_int_dynamic': [
    65943,
],
    'array_varchar_dynamic': [
    'Emily Clark',
],
    'json': {
    'name': 'Laura Robinson',
    'address': '5797 Gonzales Common Apt. 628\nNorth Samantha, NJ 96755',
},
    'key40149': 'value29016',
    'key93479': 'value27794',
    'key1241': 'value8808',
    'key62941': 'value38236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Carl Blair',
    'address': '204 Joseph Fall Apt. 896\nBrittanybury, AS 10008',
    'text': 'Trouble maybe own likely.\nLeg on off player by. Through learn discuss first. And yet security same however project then TV.',
    'email': 'vthompson@example.org',
    'phone_number': '836.369.4055x41542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Benjamin',
    'Kenneth Webb',
    'Kathleen King',
    'Bradley Kim',
    'Billy Ho',
    'Margaret Stephens',
    'Isabella Garcia',
    'Kendra Patrick',
    'Nicole Velez',
    'Brianna Hogan',
],
    'json': {
    'name': 'Kristine Robinson',
    'address': '750 Colin Key\nSmithville, AR 73562',
},
    'key46974': 'value56659',
    'key64667': 'value54857',
    'key65148': 'value86367',
    'key62516': 'value81104',
    'key71109': 'value83423',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Nicholas Mora',
    'address': '701 Paul Court\nKellyfort, NM 93670',
    'text': 'From report analysis method race. Day later view let down stay yard. Position whole yet everybody.',
    'email': 'nathansoto@example.com',
    'phone_number': '7237358816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Jones',
    'Elizabeth Weber',
    'Jason Dunn',
    'Pamela Lopez',
    'Linda Coffey',
    'Janet Hunter',
    'Matthew Benjamin',
    'Kristie Morgan',
    'Gina Patterson',
    'Kerry Collins',
],
    'json': {
    'name': 'Samuel Schwartz',
    'address': 'PSC 9360, Box 5050\nAPO AP 99328',
},
    'key54697': 'value37562',
    'key17050': 'value23635',
    'key81542': 'value10070',
    'key15671': 'value9754',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Erin Garcia',
    'address': '404 Benjamin Harbors Suite 184\nLake Patriciashire, LA 64164',
    'text': 'Bill truth hour hear term friend draw. Voice blood minute course force activity. Campaign kid forget eight so.\nMovie fire left. Find at edge exactly central read.',
    'email': 'danielstrickland@example.net',
    'phone_number': '001-509-478-4397x49053',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Hodge',
    'Mark Perez',
    'Jeremy Wang',
    'Christopher Phillips',
    'Thomas Scott',
    'Melissa Washington',
    'Leah Esparza',
    'Mary Warren',
],
    'json': {
    'name': 'Mr. Michael Calderon',
    'address': '880 Tina Cliffs Apt. 515\nSouth Juliestad, DC 02320',
},
    'key53416': 'value28500',
    'key13064': 'value79117',
    'key3756': 'value37166',
    'key6393': 'value18605',
    'key39992': 'value64083',
    'key55023': 'value92417',
    'key76412': 'value63928',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Scott Sampson',
    'address': '8773 Guerrero Burgs\nGinastad, MD 84478',
    'text': 'Certainly well away close heavy.\nRole return care. Especially health receive positive movie third.\nWatch strategy without kitchen fall. Himself magazine sell.',
    'email': 'mthomas@example.org',
    'phone_number': '856-643-6861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Allison Olson',
    'Heather Giles DDS',
    'Dawn Washington',
],
    'json': {
    'name': 'Brian Mcdonald',
    'address': '9937 Lindsey Loop\nNew Brianburgh, FM 52545',
},
    'key76266': 'value4898',
    'key27187': 'value91750',
    'key86735': 'value89770',
    'key97552': 'value99141',
    'key31561': 'value38985',
    'key29825': 'value30680',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jeffrey Bray',
    'address': '41239 Hamilton Square Suite 489\nDavidburgh, NY 92487',
    'text': 'Agency cup billion I management yourself. With money public Democrat new.\nWhat world role sense actually. Above foreign before go tell identify place.',
    'email': 'elizabethmiller@example.org',
    'phone_number': '001-342-231-1128x539',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Diana Smith',
    'Julia Brown',
    'William Farrell',
    'David Hanna Jr.',
    'Steven Weber',
    'Kayla Hill',
    'Douglas Anderson',
    'Jeremy Rivera',
    'Vanessa Garcia',
    'John Harris',
],
    'json': {
    'name': 'Mark Garcia',
    'address': 'PSC 9371, Box 3420\nAPO AA 30578',
},
    'key53058': 'value66172',
    'key98376': 'value6417',
    'key72055': 'value81025',
    'key10223': 'value42372',
    'key42988': 'value85973',
    'key30277': 'value70563',
    'key67684': 'value70093',
    'key44255': 'value27243',
    'key34247': 'value68364',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jennifer Smith',
    'address': '1710 Robin Alley Suite 545\nNorth Ronaldberg, MS 10970',
    'text': 'Stage action along sometimes program itself. Power near soldier century. Partner least education walk country seven radio. Inside else within bag.',
    'email': 'veronica30@example.net',
    'phone_number': '(463)365-3141x9271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Stokes',
    'Ashley Bridges',
    'James Strickland',
    'Whitney Mendoza',
    'Jessica Le',
    'Matthew Baker',
    'Sean Hamilton',
    'Mrs. Terri Scott',
],
    'json': {
    'name': 'Joanne Smith',
    'address': '581 Roberts Well Apt. 917\nGarciachester, DC 20304',
},
    'key72822': 'value52067',
    'key49562': 'value87546',
    'key8958': 'value78858',
    'key58994': 'value79453',
    'key62919': 'value4042',
    'key77417': 'value91569',
    'key18936': 'value93803',
    'key10287': 'value54758',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Sandra Knight',
    'address': '5749 Allen Hill\nLake Tracy, CA 19707',
    'text': 'Management financial something act. Item reduce become local sit everyone country. Report modern manager try respond air.\nDark project car reach ability. Learn old arm either war consumer that.',
    'email': 'kathleenpierce@example.org',
    'phone_number': '+1-527-995-6329x890',
    'array_int_dynamic': [
    26850,
],
    'array_varchar_dynamic': [
    'Jennifer Maldonado',
    'Andrew Ford',
    'Philip Salazar',
    'Jeffery Wells',
    'Leslie Smith',
    'Justin Hendrix',
    'Amanda Ellis',
],
    'json': {
    'name': 'Alicia Mcdowell',
    'address': '723 Logan Trace\nFullerville, MD 09525',
},
    'key29415': 'value62160',
    'key32444': 'value3960',
    'key85411': 'value35006',
    'key79810': 'value52632',
    'key67123': 'value52902',
    'key75611': 'value20787',
    'key93674': 'value45890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Antonio Rhodes',
    'address': '6205 Wilson Roads Suite 709\nBaileytown, MD 09676',
    'text': 'Today green act follow grow population. Yourself reason interview know financial.\nOur first teach bar. Behind quickly next sort. Affect work thus know also prepare push.',
    'email': 'justin59@example.org',
    'phone_number': '(634)683-4916',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Elliott',
    'Timothy Black',
    'Steven Walters',
    'Elizabeth Barnes',
    'Tina Navarro',
    'Christopher Cook',
    'Natalie Bailey',
    'Wayne Larsen',
    'Mary Garner',
    'Emily Galvan',
],
    'json': {
    'name': 'James Leach',
    'address': '8814 Jennifer Ways\nFoxburgh, NH 82380',
},
    'key44261': 'value39305',
    'key79122': 'value12893',
    'key32400': 'value35777',
    'key54383': 'value12264',
    'key68539': 'value68423',
    'key95502': 'value94660',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Timothy Garcia',
    'address': '229 Alex Course Suite 493\nKhanland, AZ 20737',
    'text': 'From health peace brother outside wrong sport remember. Visit sure same apply. Part accept oil end.\nCommon across when age down. Reduce remain easy memory experience material deal.',
    'email': 'keithbarber@example.com',
    'phone_number': '562.386.0281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christian Hill',
    'Autumn Obrien',
    'Robert Rivera',
],
    'json': {
    'name': 'Debbie Duran',
    'address': '91372 Davis Expressway\nLake Douglas, NH 77227',
},
    'key19014': 'value90177',
    'key20614': 'value14938',
    'key22510': 'value43060',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Robert Ortiz PhD',
    'address': 'Unit 6005 Box 5946\nDPO AE 54996',
    'text': 'Program establish move gas. Cup per building moment.\nCountry almost safe picture doctor film between. Fire real defense sure almost least. Vote such market region talk but kid.',
    'email': 'leonardashley@example.net',
    'phone_number': '357-384-9267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Patrick',
    'Heather Walker',
    'Barbara Miller DDS',
    'Danielle Spears',
    'Michele Jenkins',
    'Deborah Miller',
],
    'json': {
    'name': 'Michael Wilson',
    'address': '689 Cooper Light Apt. 340\nWest Laurie, OR 78376',
},
    'key7655': 'value69601',
    'key53457': 'value87158',
    'key84334': 'value42649',
    'key80812': 'value13114',
    'key15356': 'value60477',
    'key55546': 'value89604',
    'key43911': 'value11310',
    'key969': 'value85629',
    'key99960': 'value39881',
    'key83680': 'value43214',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Ronald Burns',
    'address': '75026 Burke Courts\nBrownshire, SC 10057',
    'text': 'Window all heart school just wall. Build put must large.\nQuestion each morning live ball. Cost success across drive remain political. Much agent worker little pay hit.',
    'email': 'huffmanjohn@example.net',
    'phone_number': '585-996-0904x29164',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Marshall',
    'Monica Adams',
    'Patricia Shaw',
    'Joshua Pineda',
    'Jasmine Elliott',
    'William Cook',
],
    'json': {
    'name': 'Jason Gonzalez',
    'address': '2876 Green Cliffs Apt. 263\nPort Anthony, AK 89349',
},
    'key92453': 'value88281',
    'key38140': 'value90365',
    'key43605': 'value20719',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Luis Bowen',
    'address': '639 Osborne Forest\nWest Nancy, CO 54865',
    'text': 'Speech reveal wrong spend statement film. Check we focus development. Early per whose trade. Lead support enter participant benefit energy.',
    'email': 'melissa73@example.org',
    'phone_number': '270.404.8765',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Chapman',
    'Daniel Hines',
],
    'json': {
    'name': 'Mary Wells',
    'address': 'PSC 9876, Box 9796\nAPO AE 87260',
},
    'key57956': 'value41363',
    'key54723': 'value27334',
    'key62164': 'value79371',
    'key31302': 'value61051',
    'key220': 'value59878',
    'key5218': 'value13103',
    'key89935': 'value38963',
    'key49114': 'value53826',
    'key534': 'value17840',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Jeffrey Kane',
    'address': '31229 Jennifer Drives Apt. 925\nLake Rachel, AL 19977',
    'text': 'At energy include through. Mouth left mention continue new relate.\nGarden everything song product employee save. Also station daughter free cost among among.',
    'email': 'andrewibarra@example.org',
    'phone_number': '696.203.2323x63770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Cooper',
    'Justin Barton',
],
    'json': {
    'name': 'Carrie Gould',
    'address': '7853 Anderson Keys\nEast Brian, MS 25983',
},
    'key63587': 'value88161',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Andrew Hughes',
    'address': '955 Pena Courts\nLake Brooke, UT 60883',
    'text': 'Whom western bag will blue significant. Relate rate enter place travel seek. Every ask wind best she get.\nLine ground wide effect. Them pattern measure exist different individual.',
    'email': 'amandaowens@example.net',
    'phone_number': '323-442-1646x2949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Khan',
    'Michael Snyder',
    'Austin Evans',
    'Edward Aguilar',
    'John Miranda',
    'Julia Duncan',
    'Dominique Sanchez',
    'Christopher Gordon',
],
    'json': {
    'name': 'Sandra Burnett',
    'address': '089 Tiffany Harbors Suite 391\nLaurenberg, NV 26578',
},
    'key45913': 'value16616',
    'key54477': 'value9604',
    'key34965': 'value94583',
    'key91109': 'value56411',
    'key50981': 'value21433',
    'key52380': 'value4887',
    'key65107': 'value90565',
    'key32864': 'value95889',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Peter Tran',
    'address': '1382 Dustin Ville\nWest Tiffany, VA 64469',
    'text': 'Condition group focus site education company entire. Beyond citizen allow car exist he physical. More nation party past body majority country.',
    'email': 'sjarvis@example.org',
    'phone_number': '+1-345-793-9486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Williams',
    'Monica Harris',
    'Ashley Anderson',
    'Kevin Gross',
],
    'json': {
    'name': 'Lisa Barker',
    'address': '9577 Cook Pine\nSophiachester, FM 15110',
},
    'key92233': 'value86540',
    'key72172': 'value29552',
    'key86787': 'value157',
    'key60993': 'value6909',
    'key39499': 'value91560',
    'key62624': 'value74044',
    'key11422': 'value65304',
    'key4837': 'value41437',
    'key86211': 'value31308',
    'key60478': 'value27483',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Brian Buck',
    'address': '13375 Terry Lock Suite 956\nLake Kaylashire, MA 81119',
    'text': 'Itself skill impact watch. Hot go several better popular black evidence. Vote letter cold common.\nProfessor language property trip relationship blue. Worry become wait.',
    'email': 'turnerthomas@example.net',
    'phone_number': '001-765-988-3709x60151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marie Miller',
    'Jamie Richards',
    'Paul Hall',
],
    'json': {
    'name': 'Cynthia Adkins',
    'address': '584 Becker Glens\nLake Denisefort, WA 17526',
},
    'key41600': 'value50000',
    'key41257': 'value78516',
    'key86489': 'value24302',
    'key91891': 'value92520',
    'key9357': 'value63070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Alexa Herrera',
    'address': '96257 Cabrera Villages\nSouth Kim, NC 47845',
    'text': 'Prove including serve as occur. Wait Democrat door more figure to rock.',
    'email': 'ibarker@example.org',
    'phone_number': '572.617.1924',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Johnson',
    'Barbara Chan',
    'Erin Stuart',
    'Kevin Olson',
    'Dustin Rodriguez',
    'Anthony Krueger',
    'Isaiah Lawson',
    'Dr. April Franklin',
    'Joshua Tucker',
],
    'json': {
    'name': 'Dr. Hector Ward',
    'address': '45822 Bryan Loaf\nSouth Elizabethview, ME 84726',
},
    'key77665': 'value17193',
    'key70443': 'value84300',
    'key68048': 'value94525',
    'key27510': 'value91403',
    'key20106': 'value59737',
    'key66941': 'value54784',
    'key51525': 'value39206',
    'key49730': 'value76080',
    'key85782': 'value4052',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Greg Bryant',
    'address': '480 Cynthia Mill\nEast Tracytown, NH 40610',
    'text': 'Woman yeah without common. Key design local class more purpose. Some nature first heavy expert. Crime less finish mind spend.\nRich within painting food full.',
    'email': 'treeves@example.org',
    'phone_number': '001-898-652-7682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Meyers',
    'Sarah Garcia',
],
    'json': {
    'name': 'Teresa Meyer',
    'address': '038 Hutchinson Walks Apt. 757\nNorth Jonathan, TX 61646',
},
    'key95969': 'value98554',
    'key659': 'value19982',
    'key36859': 'value34329',
    'key75824': 'value16474',
    'key69601': 'value22066',
    'key53205': 'value72091',
    'key89249': 'value14435',
    'key22580': 'value53785',
    'key7761': 'value53996',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Scott George',
    'address': '871 Timothy Glen\nSouth Timothyfurt, NH 06109',
    'text': 'Fast wish stock mission eat. We training generation. Return high watch pretty nation always.\nStandard small everyone civil. Call side former find couple peace ground.',
    'email': 'derrickperry@example.net',
    'phone_number': '+1-999-889-5782x819',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Gonzalez',
    'Stephanie Williams',
    'Mark Hart',
    'Elizabeth Brown',
    'Jennifer Wells',
],
    'json': {
    'name': 'Lindsey Johnson',
    'address': '825 Kramer Crossroad\nGraystad, AK 10072',
},
    'key99711': 'value70747',
    'key45955': 'value96274',
    'key11817': 'value75779',
    'key58621': 'value33032',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Marcus Washington',
    'address': '1855 Robert Radial Apt. 602\nMatthewburgh, ID 38434',
    'text': 'Hold community high visit kitchen. Trial action hospital. Life would administration all buy. Value building establish quite raise training rate.',
    'email': 'williamwoods@example.com',
    'phone_number': '+1-596-369-2785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Scott Krause',
],
    'json': {
    'name': 'Mary Wilkerson',
    'address': '93629 Charles Mission\nKatrinaland, KS 58614',
},
    'key39984': 'value13482',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Brian Duran',
    'address': '7664 Alyssa Harbors\nNorth Taylor, OR 43258',
    'text': 'Look its store mouth mother if. Increase treatment enjoy factor.\nWithin finally market member find. Defense food great quite age foreign spend.',
    'email': 'traciewilliams@example.com',
    'phone_number': '694.756.2472x2909',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Olson',
    'Jennifer Welch',
    'Kirsten Harris',
    'Brandi Christensen',
    'Matthew Clark',
    'William Marsh',
    'Ryan Ford',
    'Patricia Brown',
    'Mark Curtis',
    'Michaela Cantu',
],
    'json': {
    'name': 'Tiffany Chan',
    'address': '238 Fischer Roads\nLake Christine, NJ 18071',
},
    'key60748': 'value29110',
    'key58855': 'value87004',
    'key17622': 'value44279',
    'key92781': 'value89001',
    'key74665': 'value6705',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Lucas Brown',
    'address': '9400 Adam Trail Apt. 091\nKellyborough, FL 66849',
    'text': 'Quickly turn standard argue itself American. Nearly civil seek remember visit campaign.\nMust form various reveal research increase. Forget believe never star unit member. Name short late strong door.',
    'email': 'toddprice@example.org',
    'phone_number': '(605)610-3298',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Francisco Fritz',
    'Barbara Wallace',
    'Diana Stafford',
    'James Stokes',
    'Laura Weaver',
],
    'json': {
    'name': 'Andrew Shelton',
    'address': '8781 Simmons Run\nNew Brandon, CA 24827',
},
    'key78129': 'value33433',
    'key70671': 'value13412',
    'key29753': 'value72091',
    'key27758': 'value77175',
    'key61607': 'value33814',
    'key78231': 'value78122',
    'key63417': 'value32450',
    'key31911': 'value7027',
    'key61138': 'value57779',
    'key68544': 'value33539',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Elizabeth Wong',
    'address': 'Unit 2994 Box 8430\nDPO AP 86210',
    'text': 'Respond concern father fight. Health story current oil budget pattern.\nRate machine central final. Set here season appear future.',
    'email': 'christinamendez@example.net',
    'phone_number': '2759835886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Vicki Kennedy',
    'William Vincent',
    'Sharon Mccullough',
    'Robert Figueroa',
    'Jeffrey Garcia',
    'Todd Boone',
],
    'json': {
    'name': 'David Sanders',
    'address': '26356 Sherman Ports\nOlivialand, MP 01261',
},
    'key91545': 'value10663',
    'key81169': 'value90456',
    'key30040': 'value9511',
    'key99074': 'value47755',
    'key91065': 'value86193',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Patricia Nichols',
    'address': '58836 Tammy Orchard\nPort Anthony, IL 08894',
    'text': 'Court style young rate remain level. Live score current fill culture. Operation throw recently whose.',
    'email': 'jessica76@example.com',
    'phone_number': '252.233.4491x1549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Eric Keith',
],
    'json': {
    'name': 'Kenneth Moreno',
    'address': 'Unit 7319 Box 7057\nDPO AE 65233',
},
    'key75173': 'value4637',
    'key73842': 'value25557',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Raymond Cole',
    'address': '017 Jose Glen\nSouth Michelleville, AS 80537',
    'text': 'Team professor expert fish simply base entire. Magazine quickly design decide product hard use.\nProgram institution than measure. Voice similar letter knowledge month. Talk world morning southern.',
    'email': 'tony04@example.org',
    'phone_number': '(344)822-9823x11710',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Mitchell',
],
    'json': {
    'name': 'Tony Gray',
    'address': '487 Ricky Valley\nLake Donaldbury, AL 48207',
},
    'key13218': 'value80180',
    'key791': 'value46440',
    'key2669': 'value30123',
    'key2771': 'value66183',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Melissa Conley',
    'address': '383 Jose Valleys Suite 088\nWest Carlos, UT 13532',
    'text': 'Throw century security pattern quite social sea. Road though represent attorney billion this method business. Must statement quickly year if sister strategy challenge.',
    'email': 'crystal42@example.org',
    'phone_number': '+1-781-947-2873',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kelsey Lam',
    'Vincent Norris',
    'Mary Sims',
    'Gary Graham',
],
    'json': {
    'name': 'Kevin Hernandez',
    'address': '604 David Crescent\nSouth Brittany, KS 34860',
},
    'key61902': 'value45222',
    'key57004': 'value74820',
    'key3591': 'value94670',
    'key60368': 'value6151',
    'key4852': 'value72656',
    'key6247': 'value79771',
    'key31697': 'value72009',
    'key14320': 'value77936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Beth Clarke',
    'address': '80389 Griffin Lodge\nSherryborough, CT 74866',
    'text': 'Ability bill water dog by. Owner crime machine ever character mind. You somebody soon draw artist.\nSomebody or despite can. Economic home site rise reduce. All everybody green why.',
    'email': 'ericamills@example.org',
    'phone_number': '7108347852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Santiago',
    'Shirley Taylor',
    'Alicia Martin',
    'Nicholas Griffin',
    'Sheila Sharp DVM',
    'Michele Cantu',
    'Elizabeth Hubbard',
    'Wayne Brooks',
],
    'json': {
    'name': 'Jennifer Mcdonald',
    'address': '020 Dennis Cliffs Apt. 747\nMarkland, KY 36101',
},
    'key42322': 'value17189',
    'key36209': 'value86408',
    'key91848': 'value32496',
    'key42868': 'value70345',
    'key42585': 'value42164',
    'key58890': 'value63121',
    'key19282': 'value71331',
    'key83300': 'value62713',
    'key49029': 'value77446',
    'key57058': 'value9037',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Chelsea Cortez',
    'address': '69113 Underwood Mountains\nAnnland, OH 41529',
    'text': 'Painting boy although office travel fight brother.\nDinner food particularly black sit painting range. Congress end radio Democrat list.\nExecutive present rich while concern all.',
    'email': 'michaelfoster@example.com',
    'phone_number': '286-466-2013',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Underwood',
    'Jennifer Johnson',
    'Marcus Sutton',
    'Kim Hoffman',
    'Paul Meyer',
    'Paula Russell',
    'Timothy Li DDS',
    'Vincent Roberts MD',
    'Kimberly Villarreal',
    'Matthew Schroeder',
],
    'json': {
    'name': 'Alan Diaz',
    'address': 'USS Ellis\nFPO AE 13854',
},
    'key15943': 'value88978',
    'key13446': 'value70041',
    'key96221': 'value79283',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Paul Lee',
    'address': '633 Peterson Summit\nAndersonstad, VA 22539',
    'text': 'Treat remember seven race. Everybody remember eye plan true find other join.\nCapital anything follow Congress find realize. Television argue most entire difficult.',
    'email': 'wendyhogan@example.org',
    'phone_number': '+1-235-268-7380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James White',
    'Michael Kelley',
    'Donald Sullivan',
    'Lauren Clark',
    'Erin Byrd',
    'Samuel Jackson',
],
    'json': {
    'name': 'Daniel Garcia',
    'address': '9505 Jennings Viaduct Suite 647\nSouth Nicolestad, DE 32343',
},
    'key71503': 'value78840',
    'key58963': 'value92183',
    'key54742': 'value31759',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Tyrone Morales',
    'address': '408 Jennifer Expressway Apt. 871\nLake Curtisview, NH 22946',
    'text': 'Cup base discussion better discover happy toward. Community seven food ago.',
    'email': 'vmurphy@example.com',
    'phone_number': '2092514499',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ana Sherman',
    'Joshua Pearson',
    'Ryan Farmer',
    'Ricky Dorsey',
    'Leah Hodges',
    'Johnny Brown',
    'Evan Hoffman',
    'Donna Miller',
],
    'json': {
    'name': 'Michael Rosario',
    'address': 'USNV Kelley\nFPO AA 24097',
},
    'key64637': 'value28409',
    'key36929': 'value28442',
    'key66942': 'value48193',
    'key84925': 'value69360',
    'key18976': 'value4135',
    'key76324': 'value69906',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Catherine Lee',
    'address': '985 Sean Flats Suite 543\nThomasview, MN 10297',
    'text': 'Deal security keep how see source. Gas evening nature despite simple through.\nSystem line scene crime unit trade. Yet on hand ahead fish. Data program find question success hour vote.',
    'email': 'gonzalezbrian@example.net',
    'phone_number': '(480)644-8015',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Eric Wang',
    'Valerie Smith',
    'Jeffrey Johnson MD',
    'Michael Obrien',
    'Ronnie Mcclure',
    'Ana Reed',
    'Dustin Kirk',
    'Robert Kennedy',
],
    'json': {
    'name': 'Arthur Evans',
    'address': 'PSC 0191, Box 0149\nAPO AA 42671',
},
    'key41452': 'value32648',
    'key70232': 'value50977',
    'key79522': 'value64615',
    'key85062': 'value25495',
    'key12918': 'value53438',
    'key10167': 'value18963',
    'key42415': 'value57272',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Janice Martin',
    'address': '61076 Terri Way Apt. 768\nEast Kevin, CA 97162',
    'text': 'Member nation together speak. Fact article protect money be. Us represent call technology.\nLoss back effort toward card expect present.',
    'email': 'tammy50@example.net',
    'phone_number': '001-366-363-6088x738',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Nguyen',
],
    'json': {
    'name': 'Michael Holland',
    'address': '4105 Daniel Courts\nNorth Robert, MD 36243',
},
    'key86746': 'value54778',
    'key91461': 'value97703',
    'key90926': 'value5865',
    'key9859': 'value42223',
    'key72429': 'value42588',
    'key99213': 'value12631',
    'key70007': 'value8734',
    'key53173': 'value92302',
    'key13029': 'value13578',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'William Osborn',
    'address': '00553 John Crossing Suite 853\nPort Dawnbury, SC 34943',
    'text': 'Account spend protect protect share. Especially build year investment western available baby.\nVote human pattern yet radio.',
    'email': 'kathyhernandez@example.org',
    'phone_number': '+1-630-649-8651x93409',
    'array_int_dynamic': [
    69744,
],
    'array_varchar_dynamic': [
    'Timothy Moore',
    'James Krueger',
],
    'json': {
    'name': 'Steven Taylor',
    'address': '2344 Perez Fords\nNorth Zachary, SC 23156',
},
    'key80769': 'value35945',
    'key7635': 'value94227',
    'key97071': 'value88528',
    'key91167': 'value75208',
    'key15600': 'value27282',
    'key94282': 'value97887',
    'key91189': 'value65839',
    'key94084': 'value6297',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Amanda Figueroa',
    'address': '83311 Mckinney Mountain\nEast Kevin, NJ 71293',
    'text': 'Arm north young seem ball. Federal sure court media much analysis recently on.\nOil same trade serve who. Mr family size.',
    'email': 'tcampbell@example.org',
    'phone_number': '908.592.0836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mark Clark',
    'Timothy Davis',
    'Robert Warner',
    'Mrs. Adriana Snyder DVM',
    'Douglas Tucker',
    'Kristin Williams DVM',
    'Leslie Patterson',
],
    'json': {
    'name': 'Clarence Gray',
    'address': '1478 Carlos Harbor\nNorth Carolyn, MT 83791',
},
    'key75222': 'value53362',
    'key56213': 'value87078',
    'key57452': 'value68840',
    'key60156': 'value60637',
    'key88467': 'value21682',
    'key9770': 'value14423',
    'key96793': 'value45889',
    'key49969': 'value77469',
    'key7128': 'value98731',
    'key33145': 'value22086',
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
    'RequestId': '8e8ef6bd-62f1-11f0-8233-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_34_417336ioeFygWc',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'phone_number',
    'name',
    'email',
    'json',
    'uid',
    'array_varchar_dynamic',
    'address',
    'text',
    'vector',
    'array_int_dynamic',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '8f3289e0-62f1-11f0-a735-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_34_417336ioeFygWc',
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
    'RequestId': '87d7869b-62f1-11f0-8e15-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_34_417336ioeFygWc',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 0_1]_1752745007.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid011752745007Json()
    test.run_tests()
