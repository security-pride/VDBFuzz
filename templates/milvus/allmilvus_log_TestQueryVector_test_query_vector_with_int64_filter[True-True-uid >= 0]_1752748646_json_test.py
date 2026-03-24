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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752748646_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752748646.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid01752748646Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752748646.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752748646.json"
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
    'data': [
    {
    'id': 17527486382110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Patricia Mitchell',
    'address': '19579 Raymond Mountains Apt. 596\nNew Susanberg, OK 96426',
    'text': 'Small fear himself fall mouth produce return. Set away change determine paper ready. Public skill able customer all letter floor.',
    'email': 'gonzalezchristopher@example.org',
    'phone_number': '967-990-8966x875',
    'json': {
    'name': 'Katelyn Wade',
    'address': '81492 Sean Forge\nDanielsfort, NH 32472',
},
    'key6696': 'value38079',
    'key17746': 'value66409',
},
    {
    'id': 17527486382128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'William Horton',
    'address': '2033 Smith Lodge Suite 885\nWest Steven, DE 19839',
    'text': 'Occur study learn quality. Study offer state day always learn.\nUsually start production test need paper yet about. Notice find serious name.',
    'email': 'cwheeler@example.com',
    'phone_number': '(477)232-9994',
    'json': {
    'name': 'Jennifer Russo',
    'address': '424 Sarah Manors\nEast George, AR 38340',
},
    'key72872': 'value63868',
    'key46486': 'value99453',
    'key24327': 'value39752',
},
    {
    'id': 17527486382141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Elizabeth Beck',
    'address': '7217 Randy Estates\nRiddleport, PR 81220',
    'text': 'Bring including color simply. Since race within send process such charge floor.\nTreatment remain glass floor message democratic picture.\nGovernment mouth deal than. Message feel sense protect lead.',
    'email': 'louis75@example.org',
    'phone_number': '+1-364-398-6759',
    'json': {
    'name': 'Amanda Mitchell',
    'address': '4098 Gross Lakes Suite 060\nPhillipsburgh, GU 94735',
},
    'key64203': 'value78423',
    'key16079': 'value52307',
    'key71747': 'value65526',
    'key74672': 'value39756',
    'key67445': 'value47063',
    'key16861': 'value39615',
    'key87849': 'value62456',
    'key62232': 'value76774',
    'key44808': 'value81019',
},
    {
    'id': 17527486382155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Regina Wilson',
    'address': '795 Jackson Course\nNew Sandra, DC 68109',
    'text': 'Simply never certainly whole.\nYet news poor life. Among yet avoid against send usually education between. Individual work whose water rule themselves. Black service successful chair difference.',
    'email': 'jenniferwatts@example.com',
    'phone_number': '851-330-3520x56502',
    'json': {
    'name': 'Andrea Johnson',
    'address': '2368 Douglas Ramp\nFernandezport, ID 55393',
},
    'key49663': 'value6567',
    'key62714': 'value48021',
    'key44585': 'value12933',
    'key33049': 'value4696',
    'key27737': 'value84906',
    'key19597': 'value48117',
    'key83886': 'value33793',
    'key57751': 'value88052',
    'key90219': 'value71396',
    'key19874': 'value28069',
},
    {
    'id': 17527486382170,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Kristin Ellis',
    'address': '01384 Holland Turnpike Suite 415\nRaymondhaven, MA 80782',
    'text': 'According class senior test avoid family shake look. Build anything tax guess. Alone cultural support sort current by tree able. Imagine strategy miss yeah rate.',
    'email': 'kinglinda@example.com',
    'phone_number': '751-600-0180',
    'json': {
    'name': 'Taylor Suarez',
    'address': '367 Troy Lake Apt. 975\nSouth Victoria, SD 25719',
},
    'key54874': 'value49382',
    'key67613': 'value65138',
    'key46891': 'value32400',
    'key21596': 'value13175',
    'key94916': 'value9313',
    'key34991': 'value12442',
    'key18453': 'value97257',
    'key90439': 'value56184',
    'key68398': 'value25691',
},
    {
    'id': 17527486382184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Stacey Parks',
    'address': '746 Murphy Tunnel Apt. 746\nLake Amandamouth, AK 97583',
    'text': 'Dark pick win news as where. Movement although after agency your car. That argue day affect friend.\nShake drop live college. Also matter guess nearly business.',
    'email': 'christopherroberts@example.net',
    'phone_number': '682-233-4928',
    'json': {
    'name': 'John Thompson',
    'address': '66927 Lindsey Stravenue\nBeverlychester, OK 69135',
},
    'key48370': 'value54677',
    'key86002': 'value92995',
},
    {
    'id': 17527486382197,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Pamela Perez',
    'address': 'PSC 2612, Box 8236\nAPO AA 62430',
    'text': 'Do time apply lose more parent movie. Green whatever foreign professor child rate opportunity. Medical end book resource worker account. At edge bit.',
    'email': 'amber42@example.net',
    'phone_number': '727.889.4070x3277',
    'json': {
    'name': 'David Wells',
    'address': '0438 Julia Prairie\nWest Jacobview, NH 61331',
},
    'key45233': 'value19578',
    'key4174': 'value81521',
    'key85958': 'value59639',
    'key18453': 'value77449',
},
    {
    'id': 17527486382207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Howard Brown',
    'address': '54120 Jose Trace\nLake Ericview, MS 56423',
    'text': 'Knowledge cover happen tax build detail around compare. Daughter dark page quite drug. Information tough accept power likely citizen size.',
    'email': 'danielgreen@example.com',
    'phone_number': '(353)775-8081x46498',
    'json': {
    'name': 'Jessica Cook',
    'address': '53140 Megan Land\nKaylafort, WY 49207',
},
    'key27530': 'value21442',
    'key86581': 'value9080',
    'key84377': 'value17083',
    'key39711': 'value31709',
    'key43335': 'value34537',
    'key39443': 'value3558',
    'key96640': 'value22295',
},
    {
    'id': 17527486382217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kimberly Williams',
    'address': '448 Patrick Keys Apt. 546\nSouth Dana, MA 39906',
    'text': 'Deep girl likely test dark. Time event impact out. Follow glass arm bill.\nShake usually seven race wall goal lose just. Network room newspaper power. Style though everyone.',
    'email': 'tuckerchristopher@example.org',
    'phone_number': '486.852.9300x36408',
    'json': {
    'name': 'Steven Chapman',
    'address': '7581 Graham Plaza Apt. 136\nJoshuaport, ME 27167',
},
    'key82854': 'value74005',
    'key3403': 'value99896',
},
    {
    'id': 17527486382229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Kaitlyn Jackson',
    'address': '234 Miller Land Apt. 442\nMichaelbury, AK 17989',
    'text': 'Again sometimes us mouth factor purpose. More character speak girl little.\nThemselves price stuff low. Enjoy skin American career. City heavy strong hospital.',
    'email': 'wbraun@example.org',
    'phone_number': '+1-906-927-8047x754',
    'json': {
    'name': 'Amber Phillips',
    'address': '9910 Jessica Terrace Apt. 041\nWatkinsfort, DE 97740',
},
    'key90179': 'value88826',
    'key90853': 'value87256',
},
    {
    'id': 17527486382240,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Patricia Howard',
    'address': '355 Robert Harbors Suite 930\nLake Deanna, VA 81689',
    'text': 'Strategy attention lose country current into development. Appear drive glass tree fast people site. Wait above join policy unit parent.\nSister project range very once possible including.',
    'email': 'kyle41@example.org',
    'phone_number': '526-729-4185x4041',
    'json': {
    'name': 'Nicholas Rogers',
    'address': '74045 Amber Radial\nEast Cherylmouth, TX 84665',
},
    'key48042': 'value94811',
    'key67401': 'value83605',
},
    {
    'id': 17527486382251,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Kathy Coleman',
    'address': '596 Ronald Unions Apt. 199\nGrahamton, TN 28885',
    'text': 'Personal factor resource writer possible.\nSite owner news education never nice model front. Win case campaign cut.',
    'email': 'brett30@example.com',
    'phone_number': '(421)940-4505x97215',
    'json': {
    'name': 'Scott Novak',
    'address': '9413 Morales Heights Suite 468\nTateland, MA 36108',
},
    'key70127': 'value8319',
    'key77419': 'value43347',
    'key37924': 'value65232',
    'key82051': 'value29584',
    'key24863': 'value53650',
},
    {
    'id': 17527486382262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Julie Hammond',
    'address': '433 Mosley Knolls Apt. 414\nJohnsonville, ND 47509',
    'text': 'First page challenge think key could nothing. Poor add according skin over. Authority central son relationship. Foot us continue.',
    'email': 'lisamorris@example.com',
    'phone_number': '(498)209-4024x977',
    'json': {
    'name': 'Stephen Booker',
    'address': '71837 Mark Parkways\nEast Rebecca, WY 04830',
},
    'key15558': 'value64569',
    'key40127': 'value47119',
    'key79880': 'value76539',
    'key2841': 'value4542',
    'key85925': 'value62407',
},
    {
    'id': 17527486382273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'John Hill',
    'address': '6760 Gary Center Apt. 309\nLake Brandonfurt, AZ 27892',
    'text': 'Side this and appear. Gas support begin make yeah event out all. Toward cold lay help.\nOften act course clearly for. Affect truth hot west people. More everyone worry recently plan care democratic.',
    'email': 'khayes@example.net',
    'phone_number': '+1-473-846-0460x60950',
    'json': {
    'name': 'Barry Vasquez',
    'address': '01671 Williams Shoals\nHuntertown, AL 63012',
},
    'key69693': 'value18267',
    'key2245': 'value99382',
    'key48178': 'value96768',
    'key37192': 'value90329',
},
    {
    'id': 17527486382285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Michael Morton',
    'address': '3301 Boyd Ridges Apt. 963\nPort Diana, KY 99899',
    'text': 'Well choose for role generation decision. Range during natural until wait cut if short.\nNetwork hot soldier crime research. Century oil trade parent option. First tonight must development practice.',
    'email': 'emily28@example.net',
    'phone_number': '828-330-6917x575',
    'json': {
    'name': 'Tammy Smith',
    'address': '492 Rush Heights\nNew Anthonyberg, MA 72824',
},
    'key73038': 'value69268',
    'key64688': 'value46380',
    'key92115': 'value60249',
},
    {
    'id': 17527486382296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Christina Mack',
    'address': '7743 Ryan Stravenue Suite 210\nKevinfurt, MT 42130',
    'text': 'Foot board none several. Describe year responsibility hair. Imagine series information store can. Worry man make major party join myself.',
    'email': 'tmacias@example.org',
    'phone_number': '+1-450-692-2483x6466',
    'json': {
    'name': 'Colleen Garcia',
    'address': '8417 Cordova Meadow\nSusanton, HI 24713',
},
    'key53024': 'value65552',
},
    {
    'id': 17527486382306,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Joshua Hill',
    'address': '09871 Rodriguez Shore Suite 118\nSouth Ericton, CO 36188',
    'text': 'Here miss seem camera note operation real discussion. Significant out but drop hit score. Religious produce subject speak.',
    'email': 'jenna08@example.net',
    'phone_number': '+1-922-574-3474x9835',
    'json': {
    'name': 'Jeffrey Blake',
    'address': '956 Russell Wall Apt. 413\nGabrielleton, MH 47247',
},
    'key94390': 'value99164',
    'key2485': 'value51250',
    'key11769': 'value63624',
    'key15348': 'value86728',
    'key39038': 'value84968',
    'key25282': 'value81576',
    'key86264': 'value30216',
    'key40592': 'value79330',
    'key89665': 'value67044',
},
    {
    'id': 17527486382317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'James Moore',
    'address': '40814 Bennett Glen\nEast Ashley, GA 14459',
    'text': 'Cell case firm risk court movement. Boy kind rule. Rate clear follow record.\nShow to gun control.\nFinal along military.\nFederal state effort security. Build Republican special new.',
    'email': 'wheelerjessica@example.com',
    'phone_number': '+1-896-583-4152x502',
    'json': {
    'name': 'Nicholas Nicholson',
    'address': '865 Nguyen Stravenue\nRiosport, NJ 82997',
},
    'key87274': 'value11564',
    'key88653': 'value35695',
    'key33653': 'value91499',
    'key14744': 'value72856',
    'key31008': 'value52804',
    'key59570': 'value96087',
    'key68916': 'value92937',
    'key30987': 'value433',
    'key35631': 'value79926',
    'key40676': 'value40839',
},
    {
    'id': 17527486382329,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Kathryn Peters',
    'address': 'Unit 1135 Box 9882\nDPO AP 93570',
    'text': 'Term prove stay can artist which. Participant believe area evening cut ball themselves pattern.',
    'email': 'chavezbarbara@example.org',
    'phone_number': '(261)387-6958x436',
    'json': {
    'name': 'Alicia Wiggins',
    'address': 'PSC 2568, Box 7232\nAPO AE 23006',
},
    'key24256': 'value6515',
},
    {
    'id': 17527486382337,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Maria Stevens',
    'address': '8055 Colleen Club Apt. 162\nNew Annette, MD 68471',
    'text': 'About spend opportunity these majority peace year. Peace argue along by change.\nThose maybe allow term space crime.\nDeal yes policy. Population most foot standard among through fly.',
    'email': 'robert52@example.org',
    'phone_number': '(642)932-4977x1923',
    'json': {
    'name': 'Michael Mueller',
    'address': '5978 Thomas Hill Apt. 122\nPort Bradley, MD 48551',
},
    'key48284': 'value81210',
    'key55711': 'value59981',
    'key80282': 'value2870',
    'key60427': 'value794',
    'key48006': 'value45809',
    'key72007': 'value77518',
    'key19777': 'value25712',
    'key33428': 'value17756',
    'key84162': 'value50490',
},
    {
    'id': 17527486382347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'David Andrews',
    'address': '73788 David Via Suite 682\nNorth John, WV 80530',
    'text': 'Movie organization beyond between pull. Address event consumer no through. Author dog home yourself.\nGo bed response fund production agency model. Government local series power degree ready their.',
    'email': 'jeremy13@example.org',
    'phone_number': '001-844-870-2293x318',
    'json': {
    'name': 'Nicole Foster',
    'address': '69552 Meyer Union Apt. 673\nNew Philip, WI 06916',
},
    'key58965': 'value1895',
},
    {
    'id': 17527486382358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Michele Lin',
    'address': '73720 Montgomery Springs Suite 503\nRebeccaton, WY 28351',
    'text': 'Music half sea life. Candidate popular share agree rich suddenly. Across trial left important.',
    'email': 'hurstmariah@example.com',
    'phone_number': '280-649-1220',
    'json': {
    'name': 'Sheri Velazquez',
    'address': '2409 Kathy Road Apt. 485\nSeanfort, PR 80813',
},
    'key7028': 'value17721',
    'key8356': 'value66816',
    'key2399': 'value43386',
    'key63231': 'value4115',
    'key69376': 'value83049',
    'key75754': 'value49794',
    'key54098': 'value49129',
},
    {
    'id': 17527486382370,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Stephanie Bailey',
    'address': '5259 West Spring\nHuntside, OR 62379',
    'text': 'Environmental strong stuff never run. Church south large day environment spring.\nSize face high detail. Clearly boy gun picture.\nAudience four hit build piece. Nice forward popular.',
    'email': 'castromichael@example.net',
    'phone_number': '+1-653-777-2849x635',
    'json': {
    'name': 'Anthony Tran',
    'address': '36332 Hughes Brook\nNelsonchester, HI 77275',
},
    'key78783': 'value57679',
},
    {
    'id': 17527486382382,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Anna Serrano',
    'address': '70226 Lin Rue Apt. 338\nEvansport, PW 60787',
    'text': 'Serious item red million provide interesting hospital serious. Black deal street important no environment.',
    'email': 'mmorton@example.com',
    'phone_number': '391-644-1757x5656',
    'json': {
    'name': 'Troy Hill DDS',
    'address': '2112 Allen Via Suite 148\nRichardfort, IN 95161',
},
    'key20589': 'value66989',
    'key15436': 'value89791',
    'key81196': 'value37739',
    'key55402': 'value84461',
    'key69337': 'value16798',
    'key27459': 'value71633',
    'key52906': 'value23166',
    'key73198': 'value66322',
    'key62563': 'value67608',
    'key45794': 'value51143',
},
    {
    'id': 17527486382393,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Kimberly Harrison',
    'address': 'PSC 3568, Box 1153\nAPO AE 63817',
    'text': 'Listen boy edge view. Economy rise attack summer different.\nSociety economic fire add. Girl in call. Respond college lot before art.\nEasy step can power.',
    'email': 'martinchristine@example.com',
    'phone_number': '(811)779-7888',
    'json': {
    'name': 'Clinton Hill',
    'address': '842 Rebecca Way\nKaramouth, OH 83294',
},
    'key55131': 'value67903',
    'key17444': 'value8978',
},
    {
    'id': 17527486382402,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jennifer Brady',
    'address': '209 Richard River Suite 555\nNew Heidi, AR 93604',
    'text': 'Begin arm father ball next popular. Week low entire arm author up. Quickly start page either.\nEver song work alone majority personal possible trouble. Tough child officer.',
    'email': 'xmason@example.com',
    'phone_number': '614.690.4947',
    'json': {
    'name': 'Paul Holmes',
    'address': 'USCGC Estes\nFPO AA 56109',
},
    'key5214': 'value510',
    'key86137': 'value64821',
    'key24446': 'value53304',
    'key41324': 'value76248',
    'key81722': 'value2924',
    'key79848': 'value17333',
    'key14174': 'value76230',
    'key99097': 'value69474',
},
    {
    'id': 17527486382411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Heather Barnes',
    'address': '6389 Webb Land\nLake Richard, MO 82158',
    'text': 'Perform tough success plan similar then test as. List Mrs thought already none.\nReduce ground the system ground view know single. Bed trip son north law.',
    'email': 'bauersamuel@example.org',
    'phone_number': '+1-295-309-5406x42273',
    'json': {
    'name': 'Lori Wilson',
    'address': '1488 Garcia Throughway Suite 130\nWest Juanview, DC 43208',
},
    'key24326': 'value32041',
    'key75723': 'value64311',
    'key16563': 'value12348',
    'key41650': 'value18170',
},
    {
    'id': 17527486382423,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jeffrey Jackson',
    'address': '813 Wesley Cove\nCynthiaside, CA 14494',
    'text': 'Hair close development blood.\nAbove or standard society director. Drive necessary surface office participant magazine. Alone standard blood just.',
    'email': 'mark30@example.net',
    'phone_number': '739.244.4776x71199',
    'json': {
    'name': 'Edward Miller',
    'address': '618 Moss Isle Apt. 538\nNorth Amyport, SC 77638',
},
    'key81165': 'value40146',
    'key98153': 'value67510',
    'key52946': 'value87140',
    'key14946': 'value51449',
    'key80330': 'value93337',
    'key6859': 'value76287',
    'key17361': 'value24305',
},
    {
    'id': 17527486382433,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Lauren Palmer',
    'address': 'PSC 9085, Box 2165\nAPO AE 14656',
    'text': 'Various use generation might provide rock. Lay source beyond arrive he far big oil.\nNext analysis statement Republican field education. Kitchen let daughter in. Side build drug toward.',
    'email': 'johndavis@example.org',
    'phone_number': '(477)409-5844',
    'json': {
    'name': 'Sue Gamble',
    'address': '531 David Overpass\nDraketown, TX 37030',
},
    'key41806': 'value93013',
    'key95746': 'value15962',
},
    {
    'id': 17527486382443,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Jacob Vega',
    'address': '6398 Johnson Summit\nIsaacmouth, RI 04423',
    'text': 'Network price create else state. Blue different rock great rise rest director nice. Significant lawyer role bad pressure group whatever message.',
    'email': 'ramireznancy@example.com',
    'phone_number': '7123323660',
    'json': {
    'name': 'Valerie Sullivan',
    'address': '9923 Ian Circles Suite 786\nDavisfurt, SC 21178',
},
    'key89305': 'value92242',
},
    {
    'id': 17527486382454,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Victoria Mcdonald',
    'address': '641 Patrick Squares Apt. 044\nVargasbury, PR 52938',
    'text': 'Some image society rise many military grow. Mission several start home available though small. Argue fall because environmental as include.',
    'email': 'anncosta@example.org',
    'phone_number': '(894)625-8437',
    'json': {
    'name': 'Abigail Faulkner',
    'address': '563 Anthony Grove\nGarciafurt, TX 75369',
},
    'key61321': 'value39236',
    'key89190': 'value54884',
    'key22998': 'value10783',
    'key22055': 'value7645',
},
    {
    'id': 17527486382465,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Bryan Powers',
    'address': '0655 Vega Canyon\nPort Daniellestad, PR 96266',
    'text': 'Live carry letter will happen hit. Attention company evening current possible since. Such message among reveal. Computer what film short base.',
    'email': 'garygriffin@example.net',
    'phone_number': '399.628.5502x809',
    'json': {
    'name': 'Todd Reed',
    'address': '815 Perez Roads\nLake Nathanstad, AK 53453',
},
    'key34779': 'value33363',
    'key70673': 'value75465',
    'key23411': 'value12944',
    'key79677': 'value55630',
    'key52066': 'value58471',
    'key94553': 'value37449',
    'key84796': 'value66591',
    'key16188': 'value18676',
    'key83722': 'value26096',
    'key67697': 'value28288',
},
    {
    'id': 17527486382477,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kevin Washington',
    'address': 'Unit 8372 Box 8294\nDPO AP 08506',
    'text': 'Politics charge billion red my physical cold. Local crime set single left consumer itself. Term plant radio car open.',
    'email': 'kingleslie@example.org',
    'phone_number': '648.438.5454x40523',
    'json': {
    'name': 'Patrick Norton',
    'address': '866 Hubbard Union\nTylerberg, VA 73753',
},
    'key38568': 'value89950',
    'key28849': 'value4770',
    'key94326': 'value24310',
    'key951': 'value18868',
    'key54233': 'value76460',
    'key32668': 'value83331',
    'key54576': 'value70619',
    'key84353': 'value29172',
    'key4797': 'value8921',
},
    {
    'id': 17527486382487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Andrew Torres',
    'address': '632 Maria Manors Apt. 185\nStaceyton, TN 27575',
    'text': 'Performance foreign arrive control. Decide soon source that role continue who try.\nForget imagine soon. Yard just red people.',
    'email': 'heathermartinez@example.org',
    'phone_number': '372.326.2088',
    'json': {
    'name': 'James Barker',
    'address': '741 Anne Center Apt. 895\nSouth Sean, AR 07411',
},
    'key56814': 'value87158',
    'key58297': 'value87839',
    'key40124': 'value4663',
},
    {
    'id': 17527486382497,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Elizabeth Ford',
    'address': '798 Rojas Divide\nWelchborough, IA 39598',
    'text': 'Clear nice him company. On easy sing just claim trip draw example.\nSomebody wind recent. Father relate shake.\nPractice why watch dinner professional daughter. Soon morning civil every economy ever.',
    'email': 'amyerickson@example.org',
    'phone_number': '9606290009',
    'json': {
    'name': 'Steven Hernandez',
    'address': '5364 Luis Summit Suite 020\nSouth Amyland, VA 48842',
},
    'key96515': 'value14082',
    'key43225': 'value67528',
    'key21564': 'value40051',
    'key54766': 'value39588',
    'key46915': 'value11267',
    'key2704': 'value38679',
    'key12181': 'value67304',
    'key11091': 'value59563',
},
    {
    'id': 17527486382509,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Amy Jones',
    'address': '02414 April Ranch\nLake Kristen, NJ 12434',
    'text': 'Address indeed cell box tree project. Skin carry chair how standard blood. Page everyone skin standard still send.',
    'email': 'matthew50@example.org',
    'phone_number': '001-536-788-3728x68503',
    'json': {
    'name': 'Theresa Baker',
    'address': '32516 Duran Passage Suite 525\nNew Anthony, PR 45317',
},
    'key76170': 'value25764',
    'key63592': 'value81009',
    'key43013': 'value80719',
    'key86990': 'value70373',
    'key67251': 'value83972',
    'key35096': 'value12461',
},
    {
    'id': 17527486382519,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Cameron Robinson',
    'address': 'Unit 5174 Box 0149\nDPO AP 10323',
    'text': 'Chance prevent while among should many add news.\nSide hear network any. We indeed success remember. Avoid want time management offer west.',
    'email': 'nadams@example.org',
    'phone_number': '+1-690-478-4150x4199',
    'json': {
    'name': 'Paula Willis',
    'address': '5511 Christopher Groves Suite 923\nJacksonchester, DE 73618',
},
    'key2524': 'value52964',
    'key50478': 'value5372',
    'key18299': 'value8319',
    'key12960': 'value8129',
    'key83832': 'value82805',
    'key23364': 'value16197',
    'key43464': 'value91555',
},
    {
    'id': 17527486382529,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Nicholas Herrera',
    'address': '9939 Cynthia Crossing Suite 510\nGreenside, ME 80524',
    'text': 'Career operation degree. Toward expert television rule.\nUnder arrive information herself next. Stand leave politics control behind.',
    'email': 'ahughes@example.org',
    'phone_number': '(993)223-8367x201',
    'json': {
    'name': 'Traci Hess',
    'address': '40664 Cassandra Mews\nVeronicashire, GU 93863',
},
    'key8930': 'value50986',
},
    {
    'id': 17527486382539,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'William Brown',
    'address': '780 Michelle Summit Apt. 150\nLake Billymouth, MA 90914',
    'text': 'Film technology book best. Their project measure finish land here.\nDifficult cause game term cut pick newspaper way. Method fish boy either southern.',
    'email': 'holmesalyssa@example.net',
    'phone_number': '+1-584-721-8162',
    'json': {
    'name': 'Julie Jones',
    'address': 'PSC 8555, Box 5439\nAPO AP 92313',
},
    'key98457': 'value5495',
},
    {
    'id': 17527486382548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Peter Melendez',
    'address': '9623 Shawn Walk Apt. 007\nWangview, IA 78049',
    'text': 'Their use cause war. Everyone example dream gun above fly treatment hot. Degree health lead American.\nDetermine would exactly with learn floor. Today media moment middle enjoy.',
    'email': 'johnsonjulie@example.net',
    'phone_number': '3204853662',
    'json': {
    'name': 'Juan Fisher',
    'address': 'USS Mathis\nFPO AE 55528',
},
    'key30222': 'value41615',
    'key22792': 'value86358',
    'key55939': 'value7591',
    'key41678': 'value44389',
    'key54472': 'value26965',
    'key20024': 'value2412',
    'key87074': 'value72976',
    'key38684': 'value24602',
    'key69618': 'value84487',
    'key39381': 'value11095',
},
    {
    'id': 17527486382558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Megan Lee',
    'address': '8829 Johnson Path Suite 922\nWest John, AS 20973',
    'text': 'Traditional beat miss for difficult fish. More thank including south bit.\nReturn authority speech down manager. Top why guess future success.',
    'email': 'mallory19@example.com',
    'phone_number': '001-576-486-0941',
    'json': {
    'name': 'James Pollard',
    'address': '770 Gerald Garden Suite 820\nHawkinsport, NV 10698',
},
    'key22616': 'value51397',
    'key28032': 'value93894',
    'key90247': 'value92354',
    'key27753': 'value73774',
    'key49206': 'value59445',
},
    {
    'id': 17527486382569,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Douglas Trujillo',
    'address': '871 Molly Plaza Suite 228\nEast Carolstad, GA 42419',
    'text': 'Fill act company. Example include audience perform. Five maybe close three same.\nJust amount few individual. Maybe road improve face. Administration think meeting only road natural.',
    'email': 'morrowjacqueline@example.org',
    'phone_number': '965-695-9006x13044',
    'json': {
    'name': 'Caleb Bailey Jr.',
    'address': '9908 Stone Landing Suite 391\nWest Brian, NE 92192',
},
    'key38948': 'value90048',
    'key5213': 'value99837',
    'key17038': 'value56178',
    'key97978': 'value32418',
    'key44649': 'value54068',
    'key48304': 'value31772',
    'key2854': 'value68776',
    'key29545': 'value61010',
    'key39769': 'value17686',
},
    {
    'id': 17527486382581,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Joel West',
    'address': '391 Brian Divide Suite 133\nPamelafort, WI 19264',
    'text': 'Number story series establish this. Street game draw foreign yard fact simply. Ever ahead from religious maybe standard production.',
    'email': 'yreynolds@example.com',
    'phone_number': '001-964-259-8754x63458',
    'json': {
    'name': 'William Quinn',
    'address': '16865 Park Plaza\nSouth Louis, AZ 89523',
},
    'key67692': 'value57415',
    'key3525': 'value29117',
    'key68510': 'value8626',
    'key94080': 'value11252',
    'key25989': 'value83062',
    'key11945': 'value89201',
    'key84402': 'value26220',
    'key23869': 'value49124',
    'key66129': 'value87817',
    'key85952': 'value95134',
},
    {
    'id': 17527486382591,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Melanie Dixon',
    'address': '2898 Wolf Center\nNorth Lynn, NE 01447',
    'text': 'Loss answer deal when general nation look. College name miss water work development cause. Team compare debate move international.',
    'email': 'ashley54@example.net',
    'phone_number': '001-472-909-9361x21533',
    'json': {
    'name': 'Karen Olson',
    'address': '01967 Mays Stream\nLake Janiceport, VA 04976',
},
    'key78947': 'value28278',
    'key76404': 'value988',
},
    {
    'id': 17527486382602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Dustin Jones',
    'address': '479 Simmons Walk Suite 776\nPamelaton, HI 28941',
    'text': 'Particularly method hand hand view analysis billion it. Five apply cultural billion unit break should however. Agency seven by part themselves behind feeling.',
    'email': 'martinezlaura@example.org',
    'phone_number': '+1-978-450-3792x25465',
    'json': {
    'name': 'Dr. Nicholas Ferguson',
    'address': '752 Kristin Branch Apt. 447\nKimberlymouth, WI 61683',
},
    'key23744': 'value1352',
    'key71904': 'value49081',
    'key82920': 'value30311',
    'key21685': 'value42606',
    'key86492': 'value12826',
    'key54907': 'value51187',
},
    {
    'id': 17527486382614,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'David Ayers',
    'address': '27340 Berger Field Suite 992\nEmilyhaven, PA 04405',
    'text': 'Tonight letter start benefit dark free. Visit thing space worry give body fear onto.\nProve choose force develop question anyone open. Rule need quickly authority Democrat international.',
    'email': 'nguyenbrian@example.net',
    'phone_number': '2614253610',
    'json': {
    'name': 'Gilbert Rivera',
    'address': '8798 Paul River\nPort Dana, ME 61590',
},
    'key32179': 'value71842',
    'key95042': 'value48726',
    'key17982': 'value23892',
    'key23379': 'value10239',
    'key30638': 'value9352',
    'key39626': 'value24449',
},
    {
    'id': 17527486382625,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michael Harrison',
    'address': '429 Mckee Street\nNew Ryan, NC 29830',
    'text': 'Court card development public. Technology worker improve than.\nSomeone provide stop clear dark read. Within necessary recently improve.\nTelevision what more our memory. Safe north number station.',
    'email': 'simmonsnathaniel@example.org',
    'phone_number': '+1-787-751-5120x723',
    'json': {
    'name': 'Susan Rowland',
    'address': '43030 Lee Valleys Apt. 343\nWaltonborough, PA 43419',
},
    'key91851': 'value6184',
    'key5961': 'value50497',
    'key89030': 'value47094',
    'key27352': 'value33609',
    'key59154': 'value46376',
    'key96708': 'value90605',
    'key82738': 'value21155',
    'key99906': 'value97197',
    'key66131': 'value74338',
},
    {
    'id': 17527486382637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Tina Torres',
    'address': '93539 Madison Spurs\nRickychester, OR 90889',
    'text': 'Eat and with against job. Need view player smile open recognize central.\nPass feel present religious machine economy.\nWe score fact former civil. Provide family trade plant much protect Mrs poor.',
    'email': 'scott96@example.org',
    'phone_number': '844-666-4883',
    'json': {
    'name': 'Dr. Seth Elliott Jr.',
    'address': '3507 Lisa Terrace\nEast Debbie, MT 71019',
},
    'key51386': 'value55971',
    'key96398': 'value91226',
},
    {
    'id': 17527486382647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Troy Fischer',
    'address': '841 William Lane\nEast Peterstad, MN 65655',
    'text': 'More million rule thing opportunity policy. Recognize safe forget even.\nCare agreement action reality operation your likely.',
    'email': 'theresa60@example.com',
    'phone_number': '655-546-6182',
    'json': {
    'name': 'Scott Williams',
    'address': '6663 Henry Alley\nWest Tristan, LA 64040',
},
    'key89706': 'value52403',
    'key49553': 'value24781',
    'key77223': 'value47703',
    'key49518': 'value19923',
    'key23967': 'value63142',
    'key83764': 'value57072',
},
    {
    'id': 17527486382657,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Samantha Hall',
    'address': '85118 Melinda Lakes\nEast Margaret, WY 26714',
    'text': 'Whatever thousand image writer paper culture realize single.\nBase land drug and international send.',
    'email': 'yguerra@example.net',
    'phone_number': '963-215-7824',
    'json': {
    'name': 'Rebecca Mckinney',
    'address': '8614 Garcia Forest\nStarkhaven, DC 20688',
},
    'key56058': 'value47653',
    'key62685': 'value87277',
    'key8330': 'value75869',
},
    {
    'id': 17527486382667,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Breanna Todd',
    'address': '7786 Perez Meadows\nLake Linda, MA 49888',
    'text': 'Avoid natural cost hotel control hand grow fire. Expect marriage result.\nExpert trouble public music. Mention forward chair senior factor.\nSociety add it particularly.',
    'email': 'dustin54@example.net',
    'phone_number': '001-217-519-0249',
    'json': {
    'name': 'Anthony Salas',
    'address': '99201 Ruiz Keys Apt. 515\nJaniceville, ME 89402',
},
    'key70477': 'value58290',
    'key14445': 'value85579',
    'key90708': 'value74102',
    'key69305': 'value83464',
    'key86034': 'value67701',
    'key23159': 'value44096',
    'key80373': 'value82647',
    'key52564': 'value85174',
    'key14810': 'value92197',
    'key8647': 'value32935',
},
    {
    'id': 17527486382678,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Denise Green',
    'address': '20321 Cameron Shoals Apt. 769\nLake Rachel, AS 14925',
    'text': 'All amount religious not. Plan space season reach cost image talk.\nExperience civil son modern on hundred.\nNot week office people tree writer carry we. Week answer fish born full.',
    'email': 'julie67@example.net',
    'phone_number': '(374)849-4912',
    'json': {
    'name': 'Jeffery Brandt',
    'address': '88225 Garcia Place Apt. 253\nKathleenchester, TN 28280',
},
    'key73606': 'value22660',
    'key37192': 'value46498',
    'key62499': 'value17991',
    'key55509': 'value41250',
},
    {
    'id': 17527486382689,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'James Moore',
    'address': '912 Arthur Pines Apt. 608\nEllisberg, RI 51904',
    'text': 'Follow financial north share nation western address. Full attorney director true. Professional task firm prove leave. Rise admit generation out family PM.',
    'email': 'tonypotter@example.org',
    'phone_number': '+1-273-532-9286x089',
    'json': {
    'name': 'Steve Wiggins',
    'address': '60614 Thomas Creek\nWest Bryan, OH 67332',
},
    'key9997': 'value62166',
    'key32324': 'value18236',
    'key35476': 'value9617',
    'key1727': 'value88252',
    'key17689': 'value26389',
},
    {
    'id': 17527486382701,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Allison Nguyen',
    'address': '815 Stephen Park Suite 391\nSouth Phillipberg, MA 30970',
    'text': 'May family identify rather. Bring father lead sing glass. Treat degree official career blue.\nWant any end finally discussion take just positive. Hospital available without spring.',
    'email': 'ksmith@example.net',
    'phone_number': '513-867-6475',
    'json': {
    'name': 'John Smith',
    'address': '019 Saunders Estates\nJohnsonberg, NH 87961',
},
    'key36714': 'value55831',
    'key88510': 'value25639',
    'key18038': 'value16879',
    'key55394': 'value87750',
    'key71876': 'value28453',
    'key54624': 'value1626',
    'key4321': 'value61949',
    'key32026': 'value85815',
    'key64833': 'value8703',
    'key19937': 'value57815',
},
    {
    'id': 17527486382712,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jeffery Nolan',
    'address': '720 David Shores Suite 014\nJorgefurt, IN 85853',
    'text': 'Bill right guess family guy director employee. Responsibility view side actually war culture own those.\nMr wide century lead husband.\nKey my happen. Office teach film year like.',
    'email': 'rferrell@example.com',
    'phone_number': '717-293-9830x65028',
    'json': {
    'name': 'Elizabeth Jennings',
    'address': '13934 Mcclain Trafficway\nTaylorshire, MP 12011',
},
    'key60626': 'value98993',
    'key27467': 'value5975',
    'key68159': 'value59692',
    'key84470': 'value10040',
    'key22990': 'value2748',
},
    {
    'id': 17527486382723,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Judy Wilson',
    'address': '498 Delgado Drives\nLake Austinburgh, OR 02328',
    'text': 'Else activity collection popular benefit what until. Own step even phone hear good. Focus piece best employee image series.\nWar or professor state. Break catch safe fly far.',
    'email': 'laurencisneros@example.org',
    'phone_number': '7586274167',
    'json': {
    'name': 'Raven Kelley',
    'address': '0027 Gerald Lock\nPort Juliemouth, LA 13758',
},
    'key61684': 'value31679',
    'key39986': 'value43136',
    'key16424': 'value53493',
    'key2824': 'value65524',
    'key14873': 'value15596',
    'key55252': 'value39755',
},
    {
    'id': 17527486382735,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Ashley Willis',
    'address': '60876 Jessica Road\nSouth Sean, CT 78951',
    'text': 'Into inside section way main let. Choose people environmental hope already.\nEnter identify often agent. Green report reach or society strategy. Cut real mean strong southern.',
    'email': 'nhopkins@example.com',
    'phone_number': '326-243-1238x322',
    'json': {
    'name': 'Lisa Johnson',
    'address': '0989 Shannon Estate\nEugeneshire, MI 20780',
},
    'key42113': 'value66922',
    'key79021': 'value66636',
    'key73943': 'value74993',
    'key4509': 'value92161',
    'key43064': 'value81038',
    'key843': 'value52541',
},
    {
    'id': 17527486382746,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Douglas Gardner',
    'address': 'Unit 3272 Box 3722\nDPO AP 43421',
    'text': 'Social career coach bar whose change specific. Dark so sing far close win. Beyond simply whole southern.',
    'email': 'cynthiaoconnor@example.com',
    'phone_number': '001-264-576-1514x05579',
    'json': {
    'name': 'Lauren Butler',
    'address': '1866 Tracy Prairie\nJenniferville, OK 71124',
},
    'key79397': 'value13213',
    'key42023': 'value71809',
},
    {
    'id': 17527486382757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Yvonne Vasquez',
    'address': '34554 Tricia Port\nBrewerland, MI 79778',
    'text': 'Free during music choice stock. Likely cup what action.\nLike top radio action.\nPlan pay agreement pick ten leader key. Any every heart its establish.',
    'email': 'pcarter@example.org',
    'phone_number': '001-675-407-0586x404',
    'json': {
    'name': 'Carol Watson',
    'address': '081 Thompson Ways\nCarterborough, WY 71853',
},
    'key14344': 'value57408',
    'key33215': 'value50074',
    'key96382': 'value9590',
    'key99640': 'value78854',
    'key95830': 'value68464',
    'key1125': 'value84497',
    'key21750': 'value83142',
    'key39275': 'value13716',
},
    {
    'id': 17527486382771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Robert Fowler',
    'address': '159 Mccann Falls\nPort Kimberly, IN 18861',
    'text': 'Number entire price professional. Ten meet keep trip. Professor bar mother hope south stock.\nFrom plan more.\nOccur prevent professor lay realize. Arrive population Congress owner or.',
    'email': 'larrythompson@example.org',
    'phone_number': '429.270.2973x56261',
    'json': {
    'name': 'Mark Oneill',
    'address': '03276 Bowen Land Apt. 215\nSouth Amy, NJ 47154',
},
    'key33676': 'value19617',
    'key58846': 'value42573',
    'key89937': 'value66141',
    'key9966': 'value46656',
    'key62635': 'value15035',
},
    {
    'id': 17527486382786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Melanie Sutton',
    'address': '2630 Rivers Wall Suite 548\nPort Jeremiah, TX 04051',
    'text': 'Result free work hotel check store western. Service her want.\nBrother thus indeed each join campaign play. More how get dog drive. Source consumer someone go style sport human.',
    'email': 'laura53@example.com',
    'phone_number': '001-364-568-3253x198',
    'json': {
    'name': 'Kelsey Clark',
    'address': '327 Jessica Mews Suite 068\nMillsland, KS 48030',
},
    'key50470': 'value77150',
    'key75734': 'value25649',
    'key21603': 'value21227',
    'key42560': 'value8333',
    'key54438': 'value70544',
    'key67249': 'value13887',
    'key48569': 'value51361',
    'key37435': 'value69876',
    'key94238': 'value67145',
},
    {
    'id': 17527486382800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Crystal Higgins',
    'address': '66124 Ross Shores Apt. 256\nLake Ashleytown, SC 50917',
    'text': 'Continue only anyone treatment remain police matter half. Beat already summer news drive serious. Politics method performance rock spring.\nThrough food consider fact.',
    'email': 'jose61@example.com',
    'phone_number': '574-833-2218',
    'json': {
    'name': 'Erik Hayes MD',
    'address': '359 Gary Landing\nWest Martinfurt, SD 41512',
},
    'key85464': 'value86569',
},
    {
    'id': 17527486382812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Pamela Fox',
    'address': '3093 Taylor Circle Apt. 128\nKeithmouth, DE 63000',
    'text': 'Wear should accept sure main people throughout. Girl local center anyone carry contain. Four short opportunity have support have.\nCall kid safe before. Music yourself just mind.',
    'email': 'gduncan@example.com',
    'phone_number': '(380)400-2756',
    'json': {
    'name': 'Carol Mitchell',
    'address': '0155 Watkins Lock Apt. 965\nCallahanview, MN 37274',
},
    'key82111': 'value88036',
    'key3610': 'value99581',
    'key88003': 'value63761',
    'key3204': 'value54016',
    'key43338': 'value73303',
},
    {
    'id': 17527486382825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Carolyn Armstrong',
    'address': '29823 Chad Greens Suite 077\nNew Veronicaton, GA 40892',
    'text': 'Win by include test gun fast. Small under walk. Travel ask suddenly produce plant hit particularly black. Democrat nation try million few.',
    'email': 'michaelcollins@example.org',
    'phone_number': '8942975531',
    'json': {
    'name': 'Beverly Wright',
    'address': '43777 Caldwell Cove Apt. 018\nWatsonmouth, CA 36994',
},
    'key88980': 'value77793',
    'key77584': 'value85722',
    'key98451': 'value33548',
    'key84104': 'value51974',
    'key52146': 'value20539',
},
    {
    'id': 17527486382840,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Michael Young',
    'address': '87586 Anne Center\nGarzaberg, WA 47421',
    'text': 'Goal very box great attention heart practice lose. Less create at no ever instead color.\nLong finish degree teacher week between respond. Point institution check style.',
    'email': 'turnertiffany@example.org',
    'phone_number': '+1-941-610-4299x9135',
    'json': {
    'name': 'Jodi Campbell',
    'address': '14397 Christopher Village\nEast April, NH 62389',
},
    'key84933': 'value67738',
    'key99358': 'value92130',
    'key86634': 'value21617',
    'key59291': 'value48008',
    'key88316': 'value57636',
    'key16650': 'value97257',
    'key10668': 'value13104',
    'key58308': 'value64794',
    'key29715': 'value12490',
    'key554': 'value35471',
},
    {
    'id': 17527486382854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Crystal Nguyen',
    'address': '42896 Garcia Ranch Suite 018\nChanside, IA 31270',
    'text': 'Fly in field leader. Including our several hit difference sometimes generation. Member property deal suddenly image main claim bring. Six tree how color officer medical.',
    'email': 'sarah24@example.org',
    'phone_number': '464-559-4765x3125',
    'json': {
    'name': 'Joseph Little',
    'address': '5617 Hill Rapid\nWest Ericside, WV 13904',
},
    'key6768': 'value28664',
},
    {
    'id': 17527486382865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Gregory Henry',
    'address': '929 Erickson Cliff\nKaylachester, WV 08311',
    'text': 'During TV anyone wall history treatment. Main record ability send care exist over.\nTown family hope design. Less condition improve brother today this Republican fall.',
    'email': 'frodriguez@example.com',
    'phone_number': '923.818.6373x938',
    'json': {
    'name': 'Eric Conrad',
    'address': '90142 Shane Parkways Apt. 913\nNorth Amandaberg, ID 53776',
},
    'key87529': 'value59280',
    'key7804': 'value44008',
    'key62646': 'value75734',
    'key23278': 'value72397',
    'key91386': 'value23898',
    'key93348': 'value48510',
},
    {
    'id': 17527486382876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Richard Stevenson',
    'address': '23969 Courtney Shoals Apt. 084\nJenniferchester, RI 93823',
    'text': 'Give live begin hair public hot center. Believe only cover loss heavy. Summer kid main up miss its some. Ago teach wife.',
    'email': 'katherine13@example.org',
    'phone_number': '339.262.8583',
    'json': {
    'name': 'Zachary Holt',
    'address': '9367 Duffy Burg Apt. 286\nShawnbury, CO 55110',
},
    'key37821': 'value61702',
    'key71523': 'value77596',
    'key53972': 'value93478',
    'key499': 'value29774',
    'key1391': 'value60185',
    'key42412': 'value17883',
    'key27091': 'value72249',
    'key3070': 'value49173',
    'key23322': 'value57690',
    'key95664': 'value23531',
},
    {
    'id': 17527486382886,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Joshua Taylor',
    'address': '022 Jeremy Corners\nSouth George, LA 96721',
    'text': 'Bag now recently clearly. Reality during behind main town base amount.\nWind car too kind ten collection subject. Type hear physical right person. Blood remain bill ability whatever help.',
    'email': 'zpugh@example.net',
    'phone_number': '(884)234-1656',
    'json': {
    'name': 'Kelsey Reeves',
    'address': '01954 Murphy Route Apt. 165\nRebekahview, RI 39642',
},
    'key91831': 'value94645',
    'key99182': 'value94535',
},
    {
    'id': 17527486382897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Gerald Bennett',
    'address': 'USNS Miller\nFPO AP 93819',
    'text': 'Experience reach player control.\nCharacter painting place knowledge ahead capital ground most. Edge cell mission.\nReally hold present authority. Or mind however present.',
    'email': 'justin86@example.org',
    'phone_number': '825-738-4803x4415',
    'json': {
    'name': 'Kyle Frank',
    'address': '9693 Wendy Well Apt. 897\nEast Danny, HI 76062',
},
    'key89170': 'value16704',
    'key10461': 'value8023',
    'key97543': 'value15691',
    'key72646': 'value91297',
    'key71006': 'value98866',
    'key1755': 'value97911',
    'key36716': 'value26505',
    'key69062': 'value24024',
},
    {
    'id': 17527486382907,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Kelly Pearson',
    'address': '4318 Elizabeth Village\nLake Anthonyfurt, MH 72060',
    'text': 'Pay site program in executive western. Final cell government truth popular whatever determine.\nFinancial become area home why. Citizen year who box. Degree article until dog south carry stock.',
    'email': 'yclay@example.org',
    'phone_number': '832.371.2247x62713',
    'json': {
    'name': 'Heather Miranda',
    'address': '7595 Paula Lodge Apt. 521\nTeresashire, NH 56863',
},
    'key80439': 'value15699',
    'key42284': 'value35959',
    'key15798': 'value86409',
    'key49356': 'value44828',
    'key18786': 'value57337',
},
    {
    'id': 17527486382917,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Heather Cohen',
    'address': '1452 Clarence Neck Suite 139\nHallfort, ID 75816',
    'text': 'Box method again politics fight not wife. Road later moment music think himself.',
    'email': 'mariawilkins@example.com',
    'phone_number': '(888)630-7428x35425',
    'json': {
    'name': 'Henry Roberts',
    'address': '025 Carlos Harbors Suite 317\nNorth Samuelshire, AZ 15444',
},
    'key43797': 'value62114',
    'key37242': 'value94990',
    'key62734': 'value12357',
    'key57404': 'value60754',
    'key23149': 'value20951',
    'key27674': 'value59349',
    'key63677': 'value363',
    'key83128': 'value65478',
    'key77354': 'value44030',
    'key74323': 'value67119',
},
    {
    'id': 17527486382929,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jamie Mccarthy',
    'address': '4785 Logan Port Suite 988\nEast Angela, UT 68875',
    'text': 'Recent data coach start new. Lead best government good.\nExpert close degree business. Pull company concern trip mission word nature.',
    'email': 'mikegates@example.org',
    'phone_number': '476.371.6726x44643',
    'json': {
    'name': 'Kristie Richardson',
    'address': '5864 Penny Harbors\nNew Matthewview, AK 65594',
},
    'key40760': 'value74039',
    'key35040': 'value50716',
    'key73081': 'value56214',
    'key97226': 'value85793',
    'key36296': 'value24182',
    'key54586': 'value77761',
},
    {
    'id': 17527486382940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Melissa Dean',
    'address': '87883 Samantha Springs Suite 640\nKristinaville, MI 03449',
    'text': 'Door might herself though ago main past space. Court we someone mouth take hold activity. Think want true rise.',
    'email': 'coxjacob@example.net',
    'phone_number': '303.282.5183',
    'json': {
    'name': 'Jon Bennett',
    'address': '10740 Galvan Haven\nSamanthaland, WI 07025',
},
    'key17039': 'value54484',
    'key61147': 'value94196',
    'key426': 'value72646',
    'key33295': 'value40553',
    'key78581': 'value64365',
    'key51658': 'value15437',
},
    {
    'id': 17527486382951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Henry Goodwin',
    'address': '09192 Wood Center\nStevenbury, NJ 68871',
    'text': 'Perform dream even. Same coach other worry expert as. Notice myself international simple kind action. Moment ability eat fine magazine more.\nThought red large star. By crime analysis.',
    'email': 'cwatson@example.net',
    'phone_number': '(838)846-4500x084',
    'json': {
    'name': 'Emma Hoover',
    'address': 'PSC 8195, Box 9480\nAPO AP 35997',
},
    'key18402': 'value77356',
    'key44002': 'value36105',
    'key58141': 'value2884',
    'key83128': 'value39795',
    'key69097': 'value95655',
    'key11218': 'value27164',
    'key75473': 'value52355',
    'key4433': 'value64938',
    'key81399': 'value24438',
},
    {
    'id': 17527486382961,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Abigail Morgan',
    'address': '696 Padilla Trace Suite 248\nSusanton, VI 71637',
    'text': 'Foreign forget personal various attack. Participant article network religious choice south old. Beyond involve station few.\nAct nature expect message for. Keep attention author impact leg nearly.',
    'email': 'rebeccaquinn@example.net',
    'phone_number': '501-874-9852x2513',
    'json': {
    'name': 'Devin Villarreal',
    'address': 'Unit 0879 Box 4079\nDPO AE 97998',
},
    'key79736': 'value32391',
    'key97117': 'value73449',
    'key98766': 'value54454',
    'key15862': 'value59568',
    'key23060': 'value32328',
    'key59620': 'value46029',
    'key14535': 'value75427',
},
    {
    'id': 17527486382970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Troy Ball',
    'address': '243 Gomez Shore Suite 149\nJohnstad, RI 36056',
    'text': 'City help not camera rest. Although wife natural number officer call student. Kid miss medical.',
    'email': 'cbrown@example.net',
    'phone_number': '7617360143',
    'json': {
    'name': 'Kelly Gross',
    'address': '77521 Deanna Garden Apt. 218\nSouth Jasminehaven, WI 82121',
},
    'key49666': 'value63978',
    'key23510': 'value5815',
    'key55197': 'value63165',
    'key3557': 'value9550',
    'key55689': 'value40719',
    'key4582': 'value64159',
},
    {
    'id': 17527486382981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Nicole Dunn',
    'address': '9753 Morton Ranch\nEast Samantha, DC 85287',
    'text': 'Lose eight senior tax material writer. Community trouble particularly edge race laugh. Pick effect three.',
    'email': 'tallen@example.org',
    'phone_number': '+1-229-391-2128x8225',
    'json': {
    'name': 'David Griffith',
    'address': '035 Jerry Orchard Apt. 198\nNew Melissa, ID 59906',
},
    'key13748': 'value97153',
    'key83371': 'value59114',
    'key64148': 'value81739',
},
    {
    'id': 17527486382991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Renee Walsh',
    'address': '0636 Dawn Shoal Suite 455\nNew Corymouth, AK 90674',
    'text': 'Entire professor line occur special prove. Close pattern foreign. Me discuss ahead last writer. Wide bad technology remain it miss lot.',
    'email': 'xhughes@example.com',
    'phone_number': '614-814-5059',
    'json': {
    'name': 'Robert Park',
    'address': '79686 Rebecca Causeway\nEast Jeremy, NE 51731',
},
    'key77752': 'value50903',
    'key11729': 'value82994',
    'key56864': 'value60701',
    'key27199': 'value75709',
    'key94798': 'value54094',
    'key50441': 'value38255',
    'key69320': 'value35301',
},
    {
    'id': 17527486383002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Kristen Stanley',
    'address': 'Unit 4002 Box 9884\nDPO AA 81327',
    'text': 'Car politics nor vote conference. Rather end unit produce easy be left.\nWish mouth set. Go laugh four girl week science. Produce travel food middle body although dog.',
    'email': 'kelly65@example.net',
    'phone_number': '3268205220',
    'json': {
    'name': 'Matthew Stevens',
    'address': '553 Nichole Trace Apt. 768\nPort Jenniferport, CO 70686',
},
    'key17846': 'value81862',
},
    {
    'id': 17527486383011,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Veronica Flores',
    'address': '26480 Carter Plaza Apt. 614\nMarshport, ME 68525',
    'text': 'Reduce ago professor point similar same director. Coach music listen article recognize back act. Growth interest fish especially.',
    'email': 'xsmith@example.com',
    'phone_number': '752.238.7479x47095',
    'json': {
    'name': 'Christopher Campbell',
    'address': '56437 Amy Ports\nNew Christinaborough, NE 85849',
},
    'key17562': 'value96247',
    'key96306': 'value75832',
    'key73713': 'value90699',
    'key65138': 'value9440',
    'key57881': 'value78647',
    'key50398': 'value49684',
},
    {
    'id': 17527486383021,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Kimberly Smith',
    'address': '154 Perez Row Apt. 121\nWillisbury, MO 32871',
    'text': 'Its describe present amount watch. Position stand responsibility child sense add. Grow keep parent only certain yeah indicate soldier. Husband woman air learn real pattern.',
    'email': 'nhall@example.com',
    'phone_number': '001-772-659-0838x940',
    'json': {
    'name': 'Brittany Benjamin',
    'address': '050 Wilson Station\nBrownport, GU 52142',
},
    'key76159': 'value22907',
    'key4930': 'value57140',
    'key35667': 'value79509',
},
    {
    'id': 17527486383032,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Patrick Fuller',
    'address': '0892 Cassidy Brooks\nNathanton, SD 66885',
    'text': 'Treatment at local eat car manager west. Operation three our image central ability. Send order use billion.\nBase can old level board we page. Role role role adult.',
    'email': 'ucollins@example.net',
    'phone_number': '+1-848-621-7691x263',
    'json': {
    'name': 'David Andrews',
    'address': '1269 Tonya Rest\nDownsborough, NC 69680',
},
    'key61891': 'value42640',
    'key93513': 'value94708',
    'key21389': 'value77983',
    'key36692': 'value91847',
    'key68809': 'value33803',
},
    {
    'id': 17527486383043,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Ronald Taylor',
    'address': '7457 Michelle Brooks Suite 554\nNelsonborough, TX 35676',
    'text': 'Born ask wish. My conference region include feel difference way. Attack almost suffer because most.\nPhone nearly theory want person human. Whom left nation could water particular exactly.',
    'email': 'martinbarry@example.org',
    'phone_number': '+1-749-596-5001',
    'json': {
    'name': 'Marcus Mitchell',
    'address': 'PSC 8254, Box 0303\nAPO AE 92052',
},
    'key28752': 'value96347',
    'key85368': 'value30066',
    'key15710': 'value47843',
    'key11811': 'value39093',
    'key94306': 'value15049',
    'key59362': 'value80253',
    'key42626': 'value62828',
    'key37959': 'value85837',
    'key49239': 'value9813',
},
    {
    'id': 17527486383053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Crystal Watson',
    'address': '297 Lisa Orchard Suite 839\nMelanieborough, IN 19697',
    'text': 'Safe product produce just such support listen beyond. Though evening later then yard.\nTraining close artist thus together account.\nSize recent affect the. Paper often fall avoid.',
    'email': 'cristianthompson@example.net',
    'phone_number': '209.891.3508',
    'json': {
    'name': 'Zachary Williamson',
    'address': '8871 Roberts Bypass\nSanfordchester, AS 64477',
},
    'key72632': 'value76124',
    'key75975': 'value41328',
    'key71853': 'value7629',
    'key25588': 'value69538',
    'key62811': 'value48928',
    'key67082': 'value67729',
    'key80981': 'value51309',
    'key13047': 'value6986',
},
    {
    'id': 17527486383064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Mason Gregory',
    'address': 'PSC 2318, Box 2984\nAPO AE 45130',
    'text': 'Still candidate watch although class truth. Arm machine color fall both seat.',
    'email': 'romerokelsey@example.net',
    'phone_number': '930-223-6439x71178',
    'json': {
    'name': 'Michael Jimenez',
    'address': '564 Dean Island Suite 404\nCunninghamchester, ID 43442',
},
    'key46986': 'value79386',
},
    {
    'id': 17527486383074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Margaret Brown',
    'address': '317 Andrew Fork Apt. 347\nDonaldside, OK 85913',
    'text': 'Money whether hundred memory quality use begin. Collection investment forget marriage politics.',
    'email': 'danielcollins@example.org',
    'phone_number': '757.571.1936x21323',
    'json': {
    'name': 'Joshua Johnson',
    'address': '1478 Maxwell Hills\nHernandezberg, DE 28722',
},
    'key56813': 'value2225',
    'key77357': 'value56763',
},
    {
    'id': 17527486383085,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Brandon Daniels',
    'address': '9693 Kim Trace\nSmithberg, ND 42684',
    'text': 'Will always conference who identify. Might rock yard anything animal mind his administration. Financial meet dog stage weight stay under.',
    'email': 'ahernandez@example.com',
    'phone_number': '8898703075',
    'json': {
    'name': 'Natalie Larsen',
    'address': 'PSC 4014, Box 3052\nAPO AE 80814',
},
    'key18450': 'value99310',
    'key49627': 'value23898',
    'key7340': 'value73700',
},
    {
    'id': 17527486383093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Jacob Mullins',
    'address': '51342 Ryan Station\nNorth Paulside, NH 49461',
    'text': 'Decade heavy size particularly low hour late stage. Talk discussion effect personal. Push explain leader hotel task.',
    'email': 'collinssamuel@example.com',
    'phone_number': '8703699349',
    'json': {
    'name': 'Brittany Stephens',
    'address': '862 Lopez Village\nAcevedoton, AR 33542',
},
    'key36255': 'value18954',
},
    {
    'id': 17527486383104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Mark Carter',
    'address': '4637 William Grove Suite 343\nOconnorhaven, ME 95353',
    'text': 'Information our low third modern American red. Himself land of speak moment yeah cause. Democratic high act require thank.',
    'email': 'ronaldbarrett@example.org',
    'phone_number': '001-597-847-6900x71570',
    'json': {
    'name': 'Andres Reed',
    'address': '4576 Christine Junctions\nEdwardschester, MP 07644',
},
    'key6455': 'value87023',
    'key92022': 'value77548',
},
    {
    'id': 17527486383116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Shirley Olsen',
    'address': '9318 Reid Rest Apt. 431\nNorth Terrance, CO 84244',
    'text': 'Attention relate general child. Group senior office town culture begin white.\nWho apply offer much must discuss. Country investment floor chair yard learn. Cover identify rock main last.',
    'email': 'dking@example.com',
    'phone_number': '624.620.7514x235',
    'json': {
    'name': 'Shane Garcia',
    'address': '82068 Wu Harbors Suite 649\nWest Nathan, PA 47201',
},
    'key6946': 'value73076',
    'key17479': 'value58502',
    'key21043': 'value62576',
    'key81197': 'value9225',
    'key77090': 'value13008',
},
    {
    'id': 17527486383127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Shawn Mendoza',
    'address': '8992 Obrien Place Suite 248\nPort Christine, IA 99816',
    'text': 'Amount sister individual business agreement involve set. Reveal return become knowledge no beat.\nBase majority tell care generation. Special book area feeling east no item.',
    'email': 'cameronthompson@example.net',
    'phone_number': '284-885-5092',
    'json': {
    'name': 'David Diaz',
    'address': 'Unit 9980 Box 0744\nDPO AP 28225',
},
    'key31023': 'value6472',
    'key11086': 'value30224',
    'key84274': 'value80794',
    'key28083': 'value6900',
    'key86306': 'value70720',
    'key13528': 'value94258',
    'key30107': 'value5579',
    'key19018': 'value17829',
},
    {
    'id': 17527486383137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Linda Kent',
    'address': '2562 John Cliffs Apt. 452\nLake Brittney, VT 88193',
    'text': 'Base child out stage medical establish. Catch machine include change step no certain. Return book hour such know.',
    'email': 'zrichard@example.com',
    'phone_number': '(868)528-5325x3257',
    'json': {
    'name': 'April Bradley',
    'address': '622 Timothy Point Suite 819\nEast Nicoleville, AK 20160',
},
    'key46502': 'value37741',
},
    {
    'id': 17527486383147,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Elizabeth Brown',
    'address': '15038 Vega Mission\nTiffanystad, MD 08110',
    'text': 'Century need site bad case. Chair per pattern ground another.',
    'email': 'qroberts@example.org',
    'phone_number': '659-383-6105x512',
    'json': {
    'name': 'Robert Washington',
    'address': '64779 Santiago Meadows Apt. 587\nLake Lindaport, NY 32306',
},
    'key25355': 'value35692',
    'key55991': 'value26363',
    'key21803': 'value16846',
    'key37104': 'value17294',
},
    {
    'id': 17527486383158,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Linda Bauer',
    'address': '812 Blackburn Corners\nNorth Carla, WA 27352',
    'text': 'Audience its performance through wide then general. Prepare interest perhaps mention suffer glass agreement.\nYet all past chance here mouth run.',
    'email': 'joshuamcdonald@example.com',
    'phone_number': '+1-659-776-7806x61502',
    'json': {
    'name': 'Sean Doyle',
    'address': '3443 Heather Route Apt. 271\nMartinland, MI 99194',
},
    'key84440': 'value42414',
    'key66275': 'value64673',
    'key21776': 'value28496',
    'key47442': 'value27225',
    'key11343': 'value80962',
    'key68150': 'value28537',
    'key84539': 'value79894',
    'key49737': 'value75896',
    'key91062': 'value10431',
    'key82437': 'value68825',
},
    {
    'id': 17527486383169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Shelly Weiss',
    'address': '71738 Kristin Freeway\nJessicaside, MO 96943',
    'text': 'Finally spring surface eat difficult. End month structure up determine material recognize. Financial stop which style head daughter among.',
    'email': 'robertrusso@example.net',
    'phone_number': '(287)867-0892x010',
    'json': {
    'name': 'James Miller',
    'address': '0918 Dodson Hollow Apt. 751\nSouth Jason, DE 55481',
},
    'key86285': 'value15019',
    'key53419': 'value53219',
    'key60520': 'value86848',
    'key29009': 'value51500',
    'key2612': 'value76666',
},
    {
    'id': 17527486383180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Stephanie Werner',
    'address': '238 Clark Fords Suite 482\nMyersmouth, MT 33532',
    'text': 'Yard heart education rise themselves. Information guess discussion floor. Hit admit want watch quality this small focus.\nHappen truth course sometimes consider. Within natural common minute man bill.',
    'email': 'fitzpatrickmegan@example.net',
    'phone_number': '+1-667-966-4803',
    'json': {
    'name': 'Sandra Wells MD',
    'address': '824 Yates Ferry Apt. 532\nBrianfurt, VI 86884',
},
    'key66613': 'value37443',
    'key15922': 'value71614',
    'key69664': 'value61867',
    'key2581': 'value8325',
    'key5999': 'value56214',
    'key81261': 'value7125',
    'key44668': 'value44084',
    'key66684': 'value90266',
    'key90074': 'value78898',
},
    {
    'id': 17527486383193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Monique Mcclure',
    'address': 'Unit 0826 Box 6535\nDPO AA 30507',
    'text': 'Move road bar my. Positive choice laugh wonder serious middle.\nAuthority international prevent amount. Without data among sense real by second. Southern stock garden look would rest woman such.',
    'email': 'youngkara@example.org',
    'phone_number': '+1-817-978-7849x28258',
    'json': {
    'name': 'Sandra Franklin',
    'address': 'Unit 2993 Box 7594\nDPO AP 26681',
},
    'key93881': 'value50119',
    'key55468': 'value70742',
    'key61539': 'value98223',
    'key94765': 'value85670',
    'key42073': 'value54788',
    'key59652': 'value57765',
    'key24543': 'value59436',
    'key56327': 'value973',
},
    {
    'id': 17527486383200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Michael Parks',
    'address': '2907 Judy Road\nAshleytown, PR 34642',
    'text': 'Deal education alone collection card. How election me use.\nSince wear kid police stay early he. Network throughout time south little always under. Reality coach responsibility science.',
    'email': 'moodyjacob@example.net',
    'phone_number': '+1-333-802-0270',
    'json': {
    'name': 'Billy Roberts',
    'address': '0115 Whitaker Wells Suite 406\nSouth Sydneyville, PW 06007',
},
    'key76444': 'value2928',
    'key99424': 'value13837',
    'key57466': 'value98379',
},
    {
    'id': 17527486383211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jeffrey Lee',
    'address': '93948 Johnny Forge Apt. 699\nLisaland, VI 44944',
    'text': 'Wonder sense each environmental movement certainly certain. Husband store despite western.',
    'email': 'guzmancaleb@example.com',
    'phone_number': '(450)513-1088x921',
    'json': {
    'name': 'Troy Hooper',
    'address': '86868 Reeves Stravenue Apt. 399\nGregoryland, NY 91297',
},
    'key50756': 'value35799',
    'key34562': 'value52929',
    'key6094': 'value63951',
    'key74253': 'value57770',
    'key54243': 'value21325',
    'key13389': 'value59038',
    'key32809': 'value54256',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
    'filter': 'uid >= 0',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
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
    'RequestId': 'ff84014a-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_12_174976iGHxROwj',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752748646.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid01752748646Json()
    test.run_tests()
