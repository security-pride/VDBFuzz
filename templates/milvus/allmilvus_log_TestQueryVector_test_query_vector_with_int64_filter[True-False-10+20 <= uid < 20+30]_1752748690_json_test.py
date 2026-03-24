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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752748690_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752748690.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalse1020Uid20301752748690Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752748690.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752748690.json"
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
    'data': [
    {
    'id': 17527486822106,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Marcus Wagner',
    'address': '0081 Lin Forest\nLake Michaelmouth, PA 82244',
    'text': 'Administration though table star across black onto. Each marriage leader. Push there more American boy.',
    'email': 'rmorse@example.net',
    'phone_number': '659-682-1492x41241',
    'json': {
    'name': 'Jamie Adams',
    'address': '40551 Hodges Landing\nDanielmouth, ND 91948',
},
    'key50667': 'value45222',
    'key86038': 'value67557',
    'key73197': 'value56114',
    'key16021': 'value12298',
    'key21412': 'value98807',
},
    {
    'id': 17527486822121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Joseph Powell',
    'address': '7185 Taylor Orchard Apt. 607\nSmithhaven, MT 24209',
    'text': 'Which control suggest development. Film reveal character party only hospital owner.\nBehavior out listen along simply. Job authority fire public with onto road. Feel rather however way.',
    'email': 'gina03@example.net',
    'phone_number': '392.622.9011x957',
    'json': {
    'name': 'William Mcbride',
    'address': '0090 Travis Forge Suite 665\nPayneport, VA 32140',
},
    'key79049': 'value41324',
    'key43283': 'value63994',
},
    {
    'id': 17527486822134,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Melinda Jones',
    'address': '2552 Garcia Isle Suite 838\nBrownport, ME 70338',
    'text': 'Even laugh manager cover. Could bit there than. Professional note clear truth carry body.\nBig series benefit dream ready attack even. War both traditional day fire effect.',
    'email': 'itrevino@example.org',
    'phone_number': '001-770-564-3498x47147',
    'json': {
    'name': 'Kent Williams',
    'address': 'USCGC Logan\nFPO AA 27212',
},
    'key61234': 'value75611',
},
    {
    'id': 17527486822146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Megan Mccoy',
    'address': '83265 Allison Freeway Suite 094\nWarrenmouth, PA 92895',
    'text': 'Page room sign. Our cover bring fire want hour now.\nStill recognize fear drive else interesting. Student charge career question. Several remain together would edge reason.',
    'email': 'thubbard@example.net',
    'phone_number': '804-822-1791x7448',
    'json': {
    'name': 'James Rodriguez',
    'address': 'Unit 7165 Box 6501\nDPO AE 20372',
},
    'key99622': 'value93686',
    'key53312': 'value81223',
    'key16204': 'value6681',
    'key70478': 'value44760',
    'key10372': 'value49517',
    'key99488': 'value10758',
    'key74693': 'value72765',
    'key47101': 'value16065',
},
    {
    'id': 17527486822156,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Jack Castaneda',
    'address': '401 Richard Rapids\nSamanthachester, MO 58594',
    'text': 'Play marriage today way project right throughout. Only the arrive call to common. Significant after administration surface.',
    'email': 'jennifer51@example.com',
    'phone_number': '845.376.9108x69854',
    'json': {
    'name': 'Michelle Hayes',
    'address': '7300 Anne Falls\nDanielland, PW 37256',
},
    'key28123': 'value79741',
},
    {
    'id': 17527486822167,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joseph Smith',
    'address': '32649 Barnett Inlet Apt. 127\nSouth Tammyland, WV 39060',
    'text': 'Sit some idea across. Month recognize prove.\nLow challenge attack little push performance. Conference his boy appear.\nProfessor very site bit. Card front concern box truth order.',
    'email': 'melanie52@example.com',
    'phone_number': '(713)384-6328x6016',
    'json': {
    'name': 'Brian Decker',
    'address': '3409 Mark Forges\nEricberg, MT 79559',
},
    'key23325': 'value70308',
    'key31378': 'value13865',
    'key91688': 'value42587',
    'key77422': 'value99406',
    'key90694': 'value33690',
    'key62727': 'value37238',
    'key78406': 'value80252',
},
    {
    'id': 17527486822178,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kelli Wells',
    'address': '14047 Debra Radial\nLake Dwayne, OK 40067',
    'text': 'Music government three begin. Center information seek member threat. Mother world office its particularly.\nPower argue almost away into. Itself dream final effort she bit.',
    'email': 'mitchell83@example.net',
    'phone_number': '936-976-3790',
    'json': {
    'name': 'Jonathan Farmer',
    'address': '52419 Jones Lake\nNorth Kelliberg, ID 08811',
},
    'key35779': 'value81178',
},
    {
    'id': 17527486822189,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jeffrey Mills',
    'address': '03668 Baker Villages Apt. 841\nAnthonyville, CT 97359',
    'text': 'Discover billion itself child six middle maybe. Science live better like good option way. Away choice each sit box answer campaign sometimes.',
    'email': 'bmartin@example.net',
    'phone_number': '(891)558-9526x62892',
    'json': {
    'name': 'Jessica Tucker',
    'address': '983 Hill Run\nCostaport, MP 87021',
},
    'key98356': 'value13148',
    'key96004': 'value88899',
    'key1933': 'value94653',
    'key94469': 'value63743',
    'key156': 'value10231',
    'key98351': 'value6543',
},
    {
    'id': 17527486822201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Richard Lindsey',
    'address': '66845 Smith Alley\nSmithtown, AZ 16973',
    'text': 'Deep recognize strategy establish again. Feeling good cup race politics far.\nDecide sometimes lose car star. Example popular fall. Board son college chance.',
    'email': 'brandythompson@example.net',
    'phone_number': '(979)763-3075x81263',
    'json': {
    'name': 'Kathy Levine',
    'address': 'Unit 9380 Box 7989\nDPO AP 77347',
},
    'key74747': 'value14064',
    'key94019': 'value73106',
    'key48596': 'value20033',
    'key55308': 'value16019',
    'key86993': 'value82518',
    'key87283': 'value8386',
    'key26459': 'value99136',
},
    {
    'id': 17527486822211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Maria Jackson',
    'address': '421 Brooks Turnpike Suite 121\nNew Samuelside, MT 52773',
    'text': 'Add prevent party develop reason course own air. Outside subject effect. Story listen reduce chance.\nSection although finally rate process. Fill important seem.',
    'email': 'wsimmons@example.org',
    'phone_number': '628.459.6859x9861',
    'json': {
    'name': 'John Reilly',
    'address': 'PSC 5563, Box 4295\nAPO AP 08184',
},
    'key97900': 'value90355',
    'key83950': 'value72299',
    'key83835': 'value43885',
    'key38176': 'value85083',
},
    {
    'id': 17527486822220,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Shawn Edwards',
    'address': '38645 Frank Pine Suite 069\nWilliamport, DC 76682',
    'text': 'Big teacher knowledge similar research participant. Run tonight age owner mention.\nStrategy subject raise life. Nice quickly civil player poor. Knowledge rich simply prepare material.',
    'email': 'rlewis@example.com',
    'phone_number': '+1-953-757-3397x66022',
    'json': {
    'name': 'Amanda Mitchell',
    'address': 'PSC 7005, Box 9381\nAPO AA 03828',
},
    'key39102': 'value15585',
    'key11763': 'value4144',
    'key33290': 'value73391',
    'key23269': 'value21963',
    'key60498': 'value32093',
    'key67074': 'value76858',
},
    {
    'id': 17527486822229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Sarah Long',
    'address': '231 James Tunnel\nNorth Nancyton, WA 14550',
    'text': 'Pm this hear. Raise cultural so. Step serve wall can.\nSimilar event near blood forget mind. Join local friend wait compare age. At dark sometimes need.',
    'email': 'vcruz@example.com',
    'phone_number': '819.665.7290x294',
    'json': {
    'name': 'Jeremy Kaufman',
    'address': '33457 Christopher Islands\nJonesborough, MI 78081',
},
    'key44337': 'value92452',
    'key97725': 'value77203',
    'key90917': 'value99918',
    'key55305': 'value2637',
},
    {
    'id': 17527486822239,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Michael Franklin',
    'address': '25399 Tate Dam Apt. 562\nWest Amberberg, VA 31242',
    'text': 'Quite those could shake skin of. Put which fall where house itself.\nProve family not firm sign. Fast eight future. Main hit month rate apply.',
    'email': 'anthony03@example.org',
    'phone_number': '403-526-4949x265',
    'json': {
    'name': 'Frederick Walker',
    'address': '2260 Stephanie Mission Suite 628\nHudsonton, OR 88337',
},
    'key77294': 'value28994',
},
    {
    'id': 17527486822250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Tammy Adams',
    'address': '3440 David Rest\nMichaelland, AZ 65804',
    'text': 'Him evidence sure name avoid doctor development.\nNew final side various. Control great group drop loss.',
    'email': 'fnelson@example.org',
    'phone_number': '001-890-746-1009x2892',
    'json': {
    'name': 'Erika Sims',
    'address': '600 Lisa Mission\nNorth Brian, MD 26163',
},
    'key9628': 'value74597',
    'key41954': 'value7012',
    'key73204': 'value38426',
    'key74317': 'value85149',
    'key91945': 'value34002',
    'key18407': 'value90394',
    'key70893': 'value2620',
    'key51946': 'value87313',
    'key20449': 'value66547',
},
    {
    'id': 17527486822260,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jeffrey Graves',
    'address': '314 Conner Haven Apt. 188\nNorth Jasonstad, VT 91450',
    'text': 'As safe town individual. Artist find report everything. Place population exist citizen buy.\nMovement director community age item later. Growth pull full hit.',
    'email': 'tiffany92@example.com',
    'phone_number': '+1-687-555-5248',
    'json': {
    'name': 'Robin Russell',
    'address': '958 Tina Mews\nStevensfurt, KY 91689',
},
    'key88942': 'value77241',
    'key39377': 'value36922',
    'key90658': 'value5628',
    'key66385': 'value24251',
},
    {
    'id': 17527486822271,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Ian Fields',
    'address': '5047 Larry Rapid\nCaitlinshire, TN 75004',
    'text': 'They ask vote whose drive campaign can. Page best between finish. Line line mission buy natural.',
    'email': 'melendezbrenda@example.com',
    'phone_number': '001-298-258-8137x6792',
    'json': {
    'name': 'John Watson',
    'address': '493 Amy Rest\nEast Jennifer, FM 64105',
},
    'key63405': 'value35407',
    'key54761': 'value14473',
},
    {
    'id': 17527486822282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Randall Shepherd',
    'address': '109 Page Turnpike Suite 805\nHodgesbury, NM 94732',
    'text': 'Project lawyer cost student top. With rest environment expert discussion worry. Minute term carry walk early evening heavy one.',
    'email': 'kbowman@example.org',
    'phone_number': '001-396-302-4940',
    'json': {
    'name': 'Kristen Hart',
    'address': '60216 Julie Forest Suite 157\nJamieville, FM 10404',
},
    'key48783': 'value71421',
    'key8929': 'value85582',
    'key25372': 'value95696',
    'key6997': 'value43433',
    'key30508': 'value15776',
    'key79017': 'value25215',
    'key20077': 'value56965',
    'key56987': 'value15597',
},
    {
    'id': 17527486822292,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Janet Olson',
    'address': '044 Kaylee Plains Suite 353\nGordonborough, ND 34098',
    'text': 'For man draw design old tell threat. Part rather watch because final employee include. Person firm season person yard.',
    'email': 'wtaylor@example.org',
    'phone_number': '420.329.2654x3741',
    'json': {
    'name': 'Ana Berry',
    'address': '20865 Hannah Terrace Suite 714\nReedtown, MS 83278',
},
    'key43659': 'value70151',
    'key22540': 'value76738',
    'key86664': 'value60106',
    'key17831': 'value50345',
},
    {
    'id': 17527486822304,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Erika Ross',
    'address': '4623 Stephenson Green\nSouth Danielberg, VT 42701',
    'text': 'Ball type action less least bar decide. Show new bad. Decade without material instead.\nSort allow maybe class. Machine fill together figure floor director. Begin price answer very teach listen.',
    'email': 'laurenhaney@example.com',
    'phone_number': '(468)864-2445',
    'json': {
    'name': 'Sherry Jackson',
    'address': '55790 Claudia Corners\nSouth Kathleen, PR 23270',
},
    'key49530': 'value83181',
    'key92842': 'value76547',
    'key90945': 'value31070',
    'key15012': 'value53757',
},
    {
    'id': 17527486822315,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Larry Andrade',
    'address': '27615 Smith Crescent\nPort Marctown, AL 48051',
    'text': 'Film sure lot hospital best fight second. Production crime administration ability. Work including enjoy still perform.',
    'email': 'floresjessica@example.com',
    'phone_number': '949-369-5633',
    'json': {
    'name': 'Suzanne Murphy',
    'address': '60854 Adam Wells Suite 224\nTorresland, WY 21505',
},
    'key38792': 'value42478',
    'key55187': 'value76309',
    'key44385': 'value71646',
    'key38662': 'value17850',
},
    {
    'id': 17527486822327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Casey Jackson',
    'address': '172 Joshua Camp Suite 098\nPadillaberg, MT 05125',
    'text': 'Month well pick vote television ever international. Too kitchen attention plant hospital she camera.',
    'email': 'kingkevin@example.org',
    'phone_number': '+1-209-326-2029',
    'json': {
    'name': 'Abigail Thomas',
    'address': '595 Bell Brooks Apt. 230\nNew Tracytown, NY 27553',
},
    'key75096': 'value81651',
    'key47326': 'value49787',
},
    {
    'id': 17527486822338,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Rodney Brooks',
    'address': 'USCGC Henderson\nFPO AE 59666',
    'text': 'Fire player spring participant responsibility save computer well. Learn control hair world something. House around party someone whole fire.',
    'email': 'estanley@example.net',
    'phone_number': '2359104072',
    'json': {
    'name': 'Matthew Mccoy',
    'address': '3962 Green Landing\nEast Ashleyhaven, AZ 33618',
},
    'key40817': 'value2730',
    'key80891': 'value74076',
    'key30278': 'value32902',
    'key10054': 'value45095',
    'key8660': 'value86649',
    'key6012': 'value47742',
    'key63135': 'value80562',
    'key24397': 'value18285',
    'key47824': 'value42498',
    'key8459': 'value5218',
},
    {
    'id': 17527486822348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Robin Young',
    'address': '00564 Lee Vista\nEast Donaldstad, ID 11899',
    'text': 'Then detail whom actually alone goal popular from. Pattern inside yard cause part. Force phone performance another.',
    'email': 'gcooper@example.org',
    'phone_number': '+1-518-263-2373',
    'json': {
    'name': 'Dawn Griffith',
    'address': '5895 Cathy Well Suite 031\nHoltchester, CT 74366',
},
    'key1445': 'value63169',
    'key43707': 'value71753',
    'key2873': 'value34164',
    'key13385': 'value27830',
    'key41195': 'value92015',
},
    {
    'id': 17527486822359,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Victoria Parker',
    'address': '6125 Shaw Well\nRodriguezshire, MA 98024',
    'text': 'Without result scientist left by. Media beat front never mouth anyone gun.\nFigure ten share accept. Together put believe some. Along do call goal main major.',
    'email': 'jennifercombs@example.com',
    'phone_number': '363.414.3230',
    'json': {
    'name': 'Joshua Wheeler',
    'address': 'PSC 9676, Box 6711\nAPO AA 77743',
},
    'key35278': 'value70893',
    'key50105': 'value60497',
    'key64507': 'value59597',
    'key88927': 'value22291',
    'key82115': 'value7582',
    'key74879': 'value11992',
    'key22375': 'value84108',
    'key21125': 'value71054',
    'key74629': 'value25176',
},
    {
    'id': 17527486822368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Thomas Bailey',
    'address': '2702 Donald Course Suite 291\nNew John, MS 41536',
    'text': 'Your executive purpose south soldier alone same. Crime building music top race decide. So career present class wall worker feel next.',
    'email': 'eflores@example.org',
    'phone_number': '672-498-4735x615',
    'json': {
    'name': 'Angela May',
    'address': '95066 Brown Ranch Apt. 832\nNorth Kimtown, CO 31007',
},
    'key30093': 'value25508',
    'key52253': 'value51846',
    'key45731': 'value87523',
    'key77703': 'value83155',
    'key18466': 'value37309',
    'key4531': 'value25887',
    'key18474': 'value92919',
    'key55209': 'value70307',
    'key90235': 'value71809',
    'key9052': 'value80939',
},
    {
    'id': 17527486822379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'James Flowers',
    'address': '1090 Gail Keys Apt. 979\nWest William, GU 97041',
    'text': 'Idea necessary remain at raise cut floor. Remain common wish rate daughter reflect adult.\nInformation only develop president western. Term ago put recently news often.',
    'email': 'watsonemily@example.com',
    'phone_number': '(271)620-7660',
    'json': {
    'name': 'Michael Nelson',
    'address': '9152 Pruitt Spur Suite 611\nNorth Matthew, AS 33086',
},
    'key87195': 'value47232',
    'key21777': 'value66412',
    'key20317': 'value23195',
    'key88370': 'value87913',
    'key41567': 'value54498',
    'key5316': 'value39755',
    'key13566': 'value32266',
    'key17237': 'value4062',
    'key39237': 'value73078',
},
    {
    'id': 17527486822391,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Brady Rivers',
    'address': '8945 Edwards Forks\nSouth Gregoryfurt, MO 26714',
    'text': 'Way factor still machine then visit dark. Population miss month color responsibility ok. Better maintain onto old field well. Agency company hundred beat.',
    'email': 'daniel48@example.org',
    'phone_number': '711.567.1858x300',
    'json': {
    'name': 'Tammy Colon',
    'address': 'USNV Suarez\nFPO AP 06124',
},
    'key37552': 'value70037',
    'key80146': 'value1848',
    'key88674': 'value97168',
    'key57747': 'value92260',
    'key61598': 'value88497',
    'key74736': 'value86932',
    'key97358': 'value8968',
},
    {
    'id': 17527486822401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Mrs. Deborah Mckee',
    'address': '358 Vazquez Path\nLake Jacob, WI 56164',
    'text': 'Ready game cover.\nImprove anything knowledge month thus. Who man election most claim green open. Station value range must agency whom situation.',
    'email': 'robinsuarez@example.org',
    'phone_number': '(549)664-9675x014',
    'json': {
    'name': 'Jeremy Sullivan',
    'address': '773 Brown Well\nHoganburgh, MH 02967',
},
    'key87913': 'value98116',
},
    {
    'id': 17527486822412,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jason Garcia',
    'address': '3140 Castillo Drive\nCervanteston, MT 45976',
    'text': 'Respond factor why such. Over someone film behind very attack nature.\nMouth seek investment method. Go agent civil responsibility indeed picture impact. Next value finally tonight.',
    'email': 'ysantos@example.com',
    'phone_number': '+1-618-350-5487',
    'json': {
    'name': 'Kathryn Allen',
    'address': '97862 Charles Branch Apt. 420\nMooreton, CT 18065',
},
    'key72820': 'value49077',
    'key36318': 'value28923',
    'key35408': 'value88582',
    'key35555': 'value76266',
},
    {
    'id': 17527486822423,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Jessica Francis',
    'address': '276 Mary Land Suite 024\nRobertshire, WA 27490',
    'text': 'Simple happy staff serve. Record wish recently under finally.\nBack country occur participant increase. Plan whom your tend threat. Professional idea high drive medical end defense.',
    'email': 'mooresophia@example.net',
    'phone_number': '529.909.3963',
    'json': {
    'name': 'Keith Wall',
    'address': '22160 Haas Ways Suite 432\nMillerview, GA 12493',
},
    'key90249': 'value43821',
    'key62220': 'value93839',
    'key6087': 'value44090',
    'key77248': 'value78034',
},
    {
    'id': 17527486822434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Tiffany Jefferson',
    'address': '31918 Cox Track Suite 338\nJudystad, IL 46443',
    'text': 'Believe west focus especially serve activity training. Analysis order why science he kid.\nMoment perform Democrat accept not. Customer nearly issue line both. Sing bar born effect total race peace.',
    'email': 'wagneralyssa@example.net',
    'phone_number': '297-289-5614x397',
    'json': {
    'name': 'Linda Perry',
    'address': '3180 Christine Mews Apt. 977\nPort Jeffreytown, RI 20358',
},
    'key40610': 'value73668',
    'key90539': 'value31798',
    'key17189': 'value18740',
    'key60365': 'value7158',
    'key89034': 'value50048',
    'key39821': 'value46786',
    'key45226': 'value3291',
    'key31808': 'value81483',
},
    {
    'id': 17527486822446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Miss Tonya Mills DVM',
    'address': '3917 Allen Via Apt. 749\nWesleyshire, PR 43149',
    'text': 'Result former member how later. Pattern student matter thus. This yeah anyone administration large.\nExplain pattern wonder single message give difference.',
    'email': 'hurleyjames@example.com',
    'phone_number': '640-398-1968',
    'json': {
    'name': 'Patricia Henson',
    'address': '3373 Smith Loop Apt. 527\nDonaldhaven, MT 80616',
},
    'key5050': 'value75337',
    'key38744': 'value47354',
    'key15215': 'value45723',
},
    {
    'id': 17527486822458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Lisa Schultz',
    'address': '5889 Lisa Streets\nKimburgh, UT 04425',
    'text': 'Say sort question so research share those notice. Kind enter American benefit possible very present. Particular wife build and firm. Tend race gun.',
    'email': 'williamsbreanna@example.net',
    'phone_number': '001-899-321-8729x3587',
    'json': {
    'name': 'Mary Garcia',
    'address': '43263 Lisa Vista\nNorth Frank, MD 89504',
},
    'key43343': 'value44772',
    'key95920': 'value90091',
    'key75531': 'value34082',
    'key92856': 'value70595',
    'key32760': 'value87887',
},
    {
    'id': 17527486822469,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Gregory Morrison',
    'address': '3899 Erin Road\nSouth Mollyborough, LA 68898',
    'text': 'Hospital personal speech Mr however. Everyone professor kid baby. Occur program matter this successful seem.\nLikely pretty enter report impact art. Allow heavy enjoy ok.',
    'email': 'alexanderwilliamson@example.org',
    'phone_number': '936-747-7658x348',
    'json': {
    'name': 'Robert Johnson',
    'address': '378 Jennifer Fords\nMichaelfurt, AL 95986',
},
    'key86723': 'value85151',
},
    {
    'id': 17527486822480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Miguel Ward',
    'address': '38851 Gonzalez Courts\nNorth Markview, MI 12054',
    'text': 'Production protect determine course civil need. Themselves provide hard state.\nHelp point not rather pass charge necessary. Same officer loss training.',
    'email': 'ychoi@example.net',
    'phone_number': '+1-982-554-8936x445',
    'json': {
    'name': 'David Townsend',
    'address': '0204 Blankenship Crest\nJeremiahtown, IA 27081',
},
    'key56576': 'value58594',
    'key12824': 'value85591',
    'key88087': 'value64756',
    'key75113': 'value20547',
    'key14993': 'value71144',
    'key8546': 'value86982',
    'key42783': 'value12473',
    'key53314': 'value5748',
    'key1907': 'value38015',
    'key59312': 'value62872',
},
    {
    'id': 17527486822491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Joe Smith',
    'address': 'PSC 2446, Box 4583\nAPO AA 24411',
    'text': 'Piece side improve guy same I more. Trouble pass production industry. Mention pass design ok former range.',
    'email': 'edwarddaniel@example.net',
    'phone_number': '9593736693',
    'json': {
    'name': 'Jessica Davis',
    'address': '5301 Jones River\nAshleymouth, PA 88363',
},
    'key86010': 'value71968',
},
    {
    'id': 17527486822501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Kayla Hayden',
    'address': '0389 Caldwell Estates Apt. 556\nSouth Whitney, OR 39102',
    'text': 'Onto face audience leader quality. Possible yeah summer fish which travel possible pay. Water save knowledge field.\nBeyond cup hear win off.',
    'email': 'shannon99@example.com',
    'phone_number': '686.535.3470x85336',
    'json': {
    'name': 'Sarah Christensen',
    'address': '09761 Bennett Knolls\nStevenbury, LA 54770',
},
    'key58958': 'value79012',
    'key61825': 'value52292',
    'key53381': 'value83292',
    'key36499': 'value46898',
},
    {
    'id': 17527486822511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Raymond Johnston',
    'address': '218 Carroll Island\nNew Louis, FM 60441',
    'text': 'Learn activity know case business. Their commercial property although allow. My matter cold ball individual Republican ask.\nContinue mean better herself however. Blood surface reveal spend.',
    'email': 'wsandoval@example.net',
    'phone_number': '001-263-341-7845x47310',
    'json': {
    'name': 'William Miller',
    'address': '895 Carr Streets\nLake Michael, OH 95444',
},
    'key61843': 'value96529',
    'key65435': 'value80293',
},
    {
    'id': 17527486822522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Shane Steele',
    'address': '82961 Murphy Turnpike\nCooperchester, OR 33387',
    'text': 'Develop run election option imagine do. Surface especially large color remember something because blood.\nAlways it history force agent.\nWithout data sometimes check. Teach family seat measure.',
    'email': 'lawrencebaxter@example.org',
    'phone_number': '486.591.6273x798',
    'json': {
    'name': 'Michael Archer',
    'address': '804 Daniel Way Suite 799\nPachecoborough, WA 60933',
},
    'key83925': 'value37232',
    'key32596': 'value35124',
},
    {
    'id': 17527486822534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jessica Brown',
    'address': '29021 Adkins Tunnel Apt. 072\nLake Kendra, DC 74224',
    'text': 'Set assume between author huge.\nCareer race bit likely. Professor down television benefit road thousand information most.',
    'email': 'glynch@example.com',
    'phone_number': '+1-296-789-7428x9520',
    'json': {
    'name': 'Connor Gilbert',
    'address': '32505 Melissa Squares Apt. 116\nCarriefort, MS 79841',
},
    'key76412': 'value17996',
},
    {
    'id': 17527486822545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jacob Becker',
    'address': '4470 Suzanne Glens\nRushmouth, WI 71761',
    'text': 'Whether customer middle agency medical from action. Probably require appear think. Rock lot answer local never woman.\nFinish third operation knowledge past. Find response power store continue travel.',
    'email': 'michael26@example.com',
    'phone_number': '253.990.5037x90807',
    'json': {
    'name': 'Richard King',
    'address': '5484 Rachael Mountain\nBowenstad, MD 36220',
},
    'key32393': 'value5948',
    'key67652': 'value86345',
    'key86976': 'value27153',
    'key70269': 'value84771',
    'key12856': 'value72598',
    'key166': 'value53928',
    'key74297': 'value24717',
},
    {
    'id': 17527486822555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Christopher Reyes',
    'address': '92241 Robertson Lakes\nGordonview, NY 33675',
    'text': 'Way when population himself. Then leader bad produce pass avoid.\nEnough similar control throughout play capital. Total Mrs letter situation.',
    'email': 'rlopez@example.org',
    'phone_number': '715-572-1093x5150',
    'json': {
    'name': 'Laurie Gonzalez',
    'address': '5843 Sanders Green\nPort Dawn, MS 39080',
},
    'key56540': 'value35572',
    'key63955': 'value54373',
    'key93315': 'value31603',
    'key64334': 'value20045',
    'key70787': 'value25351',
    'key75042': 'value17705',
    'key48107': 'value57844',
    'key43597': 'value75177',
    'key90012': 'value21657',
},
    {
    'id': 17527486822566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Stephanie Garcia',
    'address': '85144 Lee Harbor\nRiosborough, OR 34208',
    'text': 'Practice arrive data produce catch civil themselves. Marriage article material who realize company. Brother begin oil lead wonder risk one.',
    'email': 'evansnathan@example.org',
    'phone_number': '408-261-6469x62670',
    'json': {
    'name': 'Wayne Barrera',
    'address': '5292 Pineda Camp\nBrownbury, OK 40111',
},
    'key33025': 'value60384',
    'key52354': 'value46318',
    'key62579': 'value1682',
    'key278': 'value68766',
    'key94238': 'value70922',
    'key67176': 'value93083',
    'key88034': 'value8440',
    'key56674': 'value28794',
    'key94210': 'value96930',
},
    {
    'id': 17527486822578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Nancy Lara',
    'address': '8923 Francis Mountains Suite 423\nButlerstad, OR 57728',
    'text': 'Fall rather game sometimes room. Imagine executive indeed take final.',
    'email': 'erica74@example.net',
    'phone_number': '420.487.1820',
    'json': {
    'name': 'Latoya Allen',
    'address': '2403 Latoya Falls Apt. 691\nWest Jamesside, WY 63747',
},
    'key76844': 'value40782',
},
    {
    'id': 17527486822589,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Tamara Wilson',
    'address': '5179 Martin Streets\nHallside, IL 35739',
    'text': 'Example chair finally middle community. Some bill best.',
    'email': 'cheryl98@example.org',
    'phone_number': '2252613851',
    'json': {
    'name': 'Christopher Flowers',
    'address': '25639 Murray Plain\nTroystad, AZ 32674',
},
    'key75960': 'value97459',
    'key61474': 'value70117',
    'key56208': 'value22911',
    'key64892': 'value74368',
    'key90427': 'value34760',
},
    {
    'id': 17527486822600,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Patrick Gonzalez',
    'address': 'USNV Hill\nFPO AP 57268',
    'text': 'Side night order produce including state own billion. Game write deal step great talk present. Republican it become line boy. Prevent later month figure ago increase successful.',
    'email': 'martinezrebecca@example.org',
    'phone_number': '742.620.1003x9113',
    'json': {
    'name': 'Thomas Rojas',
    'address': 'USNS Valencia\nFPO AP 22869',
},
    'key53397': 'value42400',
    'key3449': 'value8532',
    'key75747': 'value75984',
},
    {
    'id': 17527486822609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Lauren Taylor',
    'address': '462 Richardson Mountain Apt. 889\nNew Yolandaside, DC 28636',
    'text': 'Opportunity fire late music strong.\nModern north share prepare blood some work. Child have left might sometimes recently. Subject energy box senior art then figure.',
    'email': 'morrowalan@example.org',
    'phone_number': '+1-979-386-3375x74231',
    'json': {
    'name': 'Derrick Wallace',
    'address': '9744 Harold River Apt. 613\nNew Teresafurt, NM 78206',
},
    'key79470': 'value51238',
    'key18930': 'value145',
    'key49008': 'value60207',
    'key33606': 'value47175',
    'key15484': 'value82469',
},
    {
    'id': 17527486822620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Johnathan Edwards',
    'address': 'PSC 4118, Box 5676\nAPO AP 07895',
    'text': 'Condition his meet cup wide few. Age watch among clearly improve agree.\nHot out member community ago matter. Way bill five season evening.',
    'email': 'jessicabuckley@example.net',
    'phone_number': '(786)662-0047',
    'json': {
    'name': 'Thomas Williams',
    'address': '09716 Williams Flats Apt. 693\nStonetown, WA 69724',
},
    'key59557': 'value24124',
    'key44316': 'value18652',
    'key15351': 'value5407',
    'key48064': 'value26797',
    'key93083': 'value15380',
    'key97368': 'value10254',
    'key34615': 'value72845',
    'key4807': 'value41125',
    'key61525': 'value48272',
},
    {
    'id': 17527486822630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Daniel Barker',
    'address': '55929 Mckenzie Forest Apt. 668\nNorth Deannabury, ND 37670',
    'text': 'Difference form run outside heart play western. High field none really cover hour political. East none nor night report interesting join.',
    'email': 'egeorge@example.net',
    'phone_number': '3546353246',
    'json': {
    'name': 'Nancy Blanchard',
    'address': '849 Julie Squares\nJonesstad, OK 11399',
},
    'key24329': 'value47231',
    'key96388': 'value8934',
    'key40346': 'value53759',
},
    {
    'id': 17527486822640,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Robert Macdonald',
    'address': 'Unit 0952 Box 4641\nDPO AE 79815',
    'text': 'Cold scene will he. Push PM method get land. Peace close state everything rise crime.\nFree direction yet morning consumer usually modern. Out drive nothing drug group.',
    'email': 'shawn78@example.com',
    'phone_number': '254.800.6088x351',
    'json': {
    'name': 'Sarah Mcmillan',
    'address': 'Unit 3757 Box 4032\nDPO AE 29691',
},
    'key99519': 'value59360',
    'key29791': 'value56807',
    'key66088': 'value53972',
    'key42771': 'value31484',
    'key51493': 'value27310',
    'key16262': 'value14573',
    'key66505': 'value17398',
    'key77863': 'value33368',
    'key46038': 'value30704',
},
    {
    'id': 17527486822647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Ruben Yoder',
    'address': '94900 Virginia Avenue Suite 319\nMeganbury, FL 17922',
    'text': 'Authority door on. Painting relationship claim store management. Loss ok heavy blue receive.',
    'email': 'debra18@example.com',
    'phone_number': '849.588.4066x8794',
    'json': {
    'name': 'Carrie Terry',
    'address': '74277 Williams Ports\nNorth Markmouth, PA 76834',
},
    'key11787': 'value86102',
    'key55924': 'value59584',
    'key9208': 'value30183',
},
    {
    'id': 17527486822657,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Mark Yu',
    'address': '837 Woods Forges\nChristineburgh, CO 70930',
    'text': 'Community physical question thank whether. Yard side gun.\nLight man tax fine enter. Decide beyond program cut. Source war activity college market.\nEnough seat tough defense fish.',
    'email': 'moorecarly@example.net',
    'phone_number': '001-204-684-1622x5523',
    'json': {
    'name': 'Bianca Williams',
    'address': '37478 Lewis Stravenue Suite 920\nPort Ryanfurt, KS 24124',
},
    'key97506': 'value7701',
    'key31946': 'value11620',
    'key2460': 'value3910',
    'key82492': 'value63987',
    'key65025': 'value14421',
    'key45509': 'value52879',
    'key6117': 'value62810',
    'key39410': 'value53781',
    'key2547': 'value13191',
    'key84966': 'value67230',
},
    {
    'id': 17527486822669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Nancy Howard',
    'address': '2574 Dylan Hills Suite 666\nJameston, NM 62915',
    'text': 'Event enter expert oil size lose beautiful gun. Huge pattern next produce. List hour audience morning take.\nUpon attention yet word impact husband. Never cut dark scene dog.',
    'email': 'inovak@example.org',
    'phone_number': '214.963.7172',
    'json': {
    'name': 'Luke Luna',
    'address': '5408 Barbara Groves\nLake Nicole, KS 23365',
},
    'key28488': 'value20084',
    'key16846': 'value5317',
    'key35351': 'value64165',
    'key24163': 'value18078',
    'key92866': 'value67522',
    'key54837': 'value85608',
},
    {
    'id': 17527486822680,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Erik Adams',
    'address': '0613 Tim Terrace\nLake Ruth, MH 78901',
    'text': 'Hear close person happy we employee require. Land subject year trip whether.\nWant fine investment again station. Far benefit doctor. Evening throughout stock them alone difference.',
    'email': 'williamschristopher@example.org',
    'phone_number': '001-566-365-0891x2407',
    'json': {
    'name': 'Charles Brown',
    'address': '003 Anthony Point Apt. 779\nChelseatown, MI 12236',
},
    'key7780': 'value15903',
    'key81114': 'value79232',
    'key95731': 'value61006',
},
    {
    'id': 17527486822691,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Natalie West',
    'address': '46954 Kristen Plains\nVictoriaberg, WV 91500',
    'text': 'Quality such training imagine role. Too second condition fight offer anyone peace. Prevent act mean identify stock add.\nSoon no difference close tree call movement. Wear space good yeah report still.',
    'email': 'margaretmyers@example.org',
    'phone_number': '790-960-2678x2087',
    'json': {
    'name': 'Joseph Cooper',
    'address': '2480 Clark Lock Apt. 596\nPort Gary, CT 42613',
},
    'key99650': 'value6250',
    'key69920': 'value7060',
},
    {
    'id': 17527486822703,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Thomas Glass',
    'address': '4695 Brianna Mission\nWest Justinberg, MS 33575',
    'text': 'Woman one structure anything increase opportunity. Involve begin risk take cost law least. Born however view parent protect song what.',
    'email': 'jeremiahpadilla@example.net',
    'phone_number': '526-670-1882x735',
    'json': {
    'name': 'Joe Jones',
    'address': '277 Pratt Ford\nStevensberg, PA 95337',
},
    'key89013': 'value64961',
    'key96513': 'value15208',
    'key5965': 'value37739',
    'key95546': 'value10726',
    'key51060': 'value92097',
    'key64566': 'value92988',
},
    {
    'id': 17527486822714,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Amy Brown',
    'address': 'USNS Harris\nFPO AP 89035',
    'text': 'Can her occur. Other often better professor cold. Involve direction born race discuss center reveal.',
    'email': 'mark73@example.net',
    'phone_number': '256-349-6955x309',
    'json': {
    'name': 'Heather Jones',
    'address': '99011 Alexander Shoal Apt. 761\nEast Jasmine, WA 12532',
},
    'key85310': 'value77156',
    'key39421': 'value77359',
    'key9077': 'value93626',
    'key9157': 'value30694',
    'key80975': 'value94386',
    'key34699': 'value77816',
    'key83264': 'value99518',
    'key93671': 'value1349',
    'key11624': 'value61826',
    'key89270': 'value44757',
},
    {
    'id': 17527486822724,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Christopher Gray',
    'address': 'Unit 5114 Box 7606\nDPO AE 94602',
    'text': 'Scene fear training claim side various significant professor. Up prepare impact site animal. Eye weight wait.',
    'email': 'tcruz@example.org',
    'phone_number': '001-926-778-0822x314',
    'json': {
    'name': 'Erik Garcia',
    'address': '373 Thornton Prairie Suite 458\nHollandside, MO 22463',
},
    'key3650': 'value20393',
    'key16645': 'value16649',
    'key29950': 'value72846',
    'key11852': 'value73032',
    'key7039': 'value28660',
    'key91754': 'value5897',
    'key91100': 'value25117',
    'key72613': 'value4860',
    'key95440': 'value99962',
    'key61373': 'value31105',
},
    {
    'id': 17527486822733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Mr. Samuel Brown',
    'address': '3683 Barnes Shoal\nPort Anneton, ME 21382',
    'text': 'Work deep fall ready national leader wife. Start true yard six.\nDifficult person away civil pick explain expect oil.\nHit about avoid interest. Best wonder more sometimes Mrs.',
    'email': 'hollylopez@example.net',
    'phone_number': '001-991-658-6362x821',
    'json': {
    'name': 'Andrew Griffith',
    'address': '030 Andrea Roads\nChristopherborough, AL 72494',
},
    'key85172': 'value68239',
    'key42651': 'value3184',
    'key17435': 'value92007',
    'key73299': 'value67142',
    'key40771': 'value99665',
    'key31913': 'value9052',
    'key64296': 'value13286',
},
    {
    'id': 17527486822744,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Theresa Cole',
    'address': '765 Bishop Wells Suite 289\nMillerbury, ND 68736',
    'text': 'System value as be health. Suffer treat against. Operation no team water turn whom.\nNetwork sound according rest college change. Across watch trip allow produce artist upon.',
    'email': 'sarah15@example.org',
    'phone_number': '3463060563',
    'json': {
    'name': 'Travis Barrera',
    'address': '4790 Smith Glen\nKimberlyberg, WA 48274',
},
    'key72140': 'value65245',
    'key75154': 'value23518',
    'key17940': 'value21844',
    'key70444': 'value91219',
    'key66923': 'value24361',
    'key67588': 'value86369',
    'key25313': 'value73351',
    'key53851': 'value48122',
},
    {
    'id': 17527486822756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'John Gutierrez',
    'address': '517 Mullen Prairie\nAngelicaland, AK 35963',
    'text': 'Agent involve economic page they. Network in indicate move. Letter song my spring.',
    'email': 'cassandra45@example.net',
    'phone_number': '248-228-2667x0944',
    'json': {
    'name': 'James Moses',
    'address': '03818 Julie Heights\nJohnshire, NV 36129',
},
    'key81803': 'value61032',
    'key57928': 'value18661',
    'key7091': 'value94467',
    'key14011': 'value97800',
    'key80545': 'value10983',
},
    {
    'id': 17527486822765,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Kimberly Dawson DDS',
    'address': '3310 Collins Radial Apt. 063\nNorth Kellyshire, MS 54182',
    'text': 'Institution special low. Quickly read themselves.\nSystem media always drive remember. Join natural state enjoy other that. Person design language time.',
    'email': 'ahenry@example.net',
    'phone_number': '678-253-9643',
    'json': {
    'name': 'Shane Fernandez',
    'address': '23399 Thomas Burg\nPort Angelaville, FL 33671',
},
    'key73874': 'value84737',
    'key11438': 'value33043',
    'key51056': 'value23787',
    'key51202': 'value53425',
    'key80397': 'value71236',
    'key28159': 'value4838',
},
    {
    'id': 17527486822776,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Holly Haley',
    'address': '6729 Jason Greens\nNew Craigmouth, IA 71330',
    'text': 'Sing age thus. Fall prepare value pick. Work star as people.\nHouse development than raise. Feeling successful clear its.',
    'email': 'sylvia66@example.com',
    'phone_number': '(276)593-4438x188',
    'json': {
    'name': 'Marilyn Winters',
    'address': '90572 Wilkerson Plaza\nAlvarezmouth, TX 21389',
},
    'key94709': 'value79340',
    'key56975': 'value92977',
},
    {
    'id': 17527486822786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Nicole Gray',
    'address': '1084 Moore Bypass Suite 557\nNew Shannonville, NJ 69756',
    'text': 'However just much official.\nToday federal see fill. Admit ability city. Last ask baby allow spring great final. Any television deal PM east product.',
    'email': 'vargasjennifer@example.com',
    'phone_number': '(625)358-3539x8915',
    'json': {
    'name': 'Scott Sexton',
    'address': '350 Wall Place Suite 705\nPort Renee, ME 69905',
},
    'key28402': 'value35976',
    'key78852': 'value72090',
},
    {
    'id': 17527486822799,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Destiny Mueller',
    'address': '627 Scott River Suite 152\nWilsonport, PA 69870',
    'text': 'Woman compare field skin somebody off stand. Reason yourself hard reveal better beyond name brother. Reason mouth beyond opportunity together.',
    'email': 'cwilliams@example.com',
    'phone_number': '496-501-8929',
    'json': {
    'name': 'Brian Haynes',
    'address': '3737 Kevin Rapid\nKimberlyborough, MI 14149',
},
    'key99393': 'value52429',
    'key59932': 'value75056',
    'key84459': 'value52566',
    'key82864': 'value88221',
    'key67603': 'value3879',
    'key43436': 'value35922',
    'key67526': 'value40034',
},
    {
    'id': 17527486822810,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jennifer Wilson',
    'address': '99934 Martinez Alley Suite 211\nNorth Jeffreybury, KS 71657',
    'text': 'Hear official crime production close democratic scientist.\nCut win society. Cultural difficult happy section tend service or bad. Seem yet nature use strong.',
    'email': 'michaelfisher@example.org',
    'phone_number': '+1-339-515-7489',
    'json': {
    'name': 'David Jenkins',
    'address': '474 Smith Road\nEast Shannon, MS 16559',
},
    'key64003': 'value15241',
    'key21741': 'value77207',
    'key81836': 'value96490',
    'key13925': 'value98507',
    'key8106': 'value93863',
},
    {
    'id': 17527486822822,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'David Frazier',
    'address': '7983 Sarah Underpass Apt. 714\nSouth Jessebury, MH 38498',
    'text': 'Want exist international. Member raise safe century. Fund condition central lot example here. Inside meeting catch authority lead role.\nSign population almost.',
    'email': 'morenojared@example.org',
    'phone_number': '+1-205-512-7487x72188',
    'json': {
    'name': 'Jacob Thomas',
    'address': '79913 Michele Port\nPort Kellyton, OR 62164',
},
    'key43207': 'value78017',
    'key4620': 'value66666',
    'key82497': 'value55950',
    'key54146': 'value12148',
    'key87708': 'value49279',
    'key24710': 'value73855',
    'key85476': 'value59771',
    'key4903': 'value8948',
},
    {
    'id': 17527486822834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Pamela Brown',
    'address': '4445 Black Turnpike Suite 938\nRobertmouth, NM 46365',
    'text': 'Include daughter but point rock unit senior. Buy best actually.\nRate action plant right billion. Event audience yard hope most develop case.',
    'email': 'angelawallace@example.com',
    'phone_number': '625.769.7436x605',
    'json': {
    'name': 'Michelle Evans',
    'address': '65510 Michael Canyon Suite 616\nRiveraberg, SD 98783',
},
    'key7624': 'value39868',
    'key38729': 'value55835',
    'key65549': 'value66301',
    'key43871': 'value61721',
    'key84049': 'value48762',
    'key77768': 'value64221',
},
    {
    'id': 17527486822846,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Karen Li',
    'address': '7187 Sharon Centers Apt. 913\nSouth Laurenshire, WV 81378',
    'text': 'Mr article before such everyone control. Control visit arm themselves political. Ago skill understand available blue available.',
    'email': 'bfisher@example.org',
    'phone_number': '956.315.1497',
    'json': {
    'name': 'Todd Nelson MD',
    'address': '22255 Brooke Roads Apt. 718\nLake Tamarastad, ME 56161',
},
    'key80406': 'value39474',
},
    {
    'id': 17527486822856,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Tami Brown',
    'address': '1760 Norma Estate Suite 334\nSouth Gregory, NM 73512',
    'text': 'Activity perform center develop everything certain trial minute. Could discuss condition government.\nKind serve administration door through himself. Wrong join recent matter get by.',
    'email': 'gperkins@example.net',
    'phone_number': '945.339.9324x1625',
    'json': {
    'name': 'Martha Bradley',
    'address': '0918 John Loop\nLake James, GU 99936',
},
    'key27989': 'value52152',
    'key22899': 'value6158',
    'key48034': 'value46709',
},
    {
    'id': 17527486822867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Devon Chang',
    'address': '6541 Nathan Hills Apt. 984\nReyesfurt, LA 24927',
    'text': 'Say consumer policy across store evening perhaps bit. Media individual admit pressure west stand officer it. Significant box learn until audience role situation.',
    'email': 'qpatrick@example.org',
    'phone_number': '(987)984-4189',
    'json': {
    'name': 'John Robinson',
    'address': '46204 Phelps River Apt. 073\nEast Bethanyberg, DE 48680',
},
    'key61171': 'value68982',
    'key10951': 'value21736',
    'key35176': 'value14239',
    'key68778': 'value10058',
},
    {
    'id': 17527486822878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jessica Bishop',
    'address': '810 Reyes Inlet Suite 098\nGriffinchester, MI 23614',
    'text': 'Look care of heart road arm system impact. Young mean marriage seek drop box example. Student several plan street as administration play.',
    'email': 'nelsonjacqueline@example.com',
    'phone_number': '678-535-9680x68561',
    'json': {
    'name': 'Nicholas Wade',
    'address': '658 Amy Plain Suite 040\nPort Markchester, WA 05363',
},
    'key94232': 'value99372',
    'key43305': 'value90674',
    'key12389': 'value59261',
    'key84292': 'value69049',
    'key94179': 'value59935',
},
    {
    'id': 17527486822889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Kevin Cruz',
    'address': '92680 Henderson Light Suite 043\nNorth Tiffanyville, IA 20614',
    'text': 'Example build power whose yourself catch offer. Already always start.\nEat bill upon would. Thus movement market finally my early.\nEasy mouth safe director company to stuff. Trouble out including.',
    'email': 'karendean@example.net',
    'phone_number': '001-251-983-0496x948',
    'json': {
    'name': 'Elizabeth Lucas',
    'address': '49282 Christine Estate\nPort Jessicashire, PW 26056',
},
    'key60934': 'value30913',
    'key52013': 'value6562',
    'key85452': 'value5099',
},
    {
    'id': 17527486822901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Charles Smith',
    'address': '30842 Buck Mount\nAmandaside, DC 69771',
    'text': 'Song else enter defense. Program tax culture walk into late.\nCourse fear modern laugh certainly. Staff return until common number. Big into budget somebody seek.',
    'email': 'qblack@example.org',
    'phone_number': '854.349.7879x06628',
    'json': {
    'name': 'Joshua Thomas',
    'address': '6510 Holloway Rest\nNorth Davidstad, OR 87749',
},
    'key29282': 'value39519',
},
    {
    'id': 17527486822912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Mr. Jesse Walker',
    'address': '036 King River\nEast Howardburgh, WV 18189',
    'text': 'Audience nearly social Democrat. Matter from name relate here.\nToo traditional certain about. Hospital describe structure consumer support bar. College score president you program analysis bag.',
    'email': 'millererica@example.net',
    'phone_number': '3106681237',
    'json': {
    'name': 'Bryan Parsons',
    'address': '483 Deborah Point\nWest Mckenziehaven, MA 58161',
},
    'key57138': 'value78630',
    'key4605': 'value58877',
    'key34376': 'value70511',
    'key9346': 'value99966',
    'key83287': 'value48659',
    'key31738': 'value35380',
},
    {
    'id': 17527486822923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Bryan Williams',
    'address': '44724 Jennifer Light Apt. 417\nKingland, AL 52419',
    'text': 'Movement beat this fish. How century chance few forward collection. Physical exactly finish on.\nPolice more exactly understand outside individual east.\nCan debate sometimes majority father red least.',
    'email': 'barkerscott@example.net',
    'phone_number': '775-991-8233x08875',
    'json': {
    'name': 'Sonya Colon',
    'address': '70083 Christina Meadow Suite 003\nLanceville, OK 83890',
},
    'key23573': 'value48518',
},
    {
    'id': 17527486822935,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Heidi Wagner',
    'address': '8972 Downs Cape Apt. 233\nWest Crystalland, RI 72328',
    'text': 'Experience now spring mission. The stop politics off wife shoulder.\nThan author return foreign degree. Environment return single east. Here cold throughout magazine market. Book customer write seven.',
    'email': 'oliverkristin@example.org',
    'phone_number': '548-778-3410x331',
    'json': {
    'name': 'Krista Daniel',
    'address': '2285 Green Ferry\nNew Sethtown, ND 70145',
},
    'key3532': 'value26524',
    'key79334': 'value59290',
    'key86892': 'value71311',
    'key74529': 'value74311',
    'key61387': 'value65929',
    'key81765': 'value48868',
    'key83403': 'value56497',
},
    {
    'id': 17527486822947,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Ana Mack',
    'address': '24753 Camacho Mountains Apt. 759\nGarzaport, NV 57031',
    'text': 'Station couple season rule stuff. Blood apply argue maintain. Bit kid far Congress team station. Well hear page resource city too blood.',
    'email': 'tanya82@example.org',
    'phone_number': '(727)784-9399x1431',
    'json': {
    'name': 'Deborah Bass',
    'address': '3563 Samantha Avenue Apt. 611\nGarciaview, SD 00528',
},
    'key41463': 'value57117',
    'key38678': 'value52795',
    'key75028': 'value60737',
    'key88121': 'value90882',
    'key49854': 'value76496',
},
    {
    'id': 17527486822958,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Ronald Johnson',
    'address': 'PSC 9618, Box 6701\nAPO AA 19453',
    'text': 'Former central drug travel field. Last a back. Area authority ok. Contain up strategy ok point.\nMaterial low worker simply various often. Often stop thousand other.\nBefore time audience.',
    'email': 'rebecca88@example.com',
    'phone_number': '(710)311-7104x385',
    'json': {
    'name': 'Michael Roman',
    'address': '65764 Palmer Burg Suite 077\nEmilymouth, PR 59959',
},
    'key62763': 'value32801',
    'key72029': 'value27180',
    'key6072': 'value20839',
    'key97211': 'value33198',
},
    {
    'id': 17527486822967,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Mark Roberts',
    'address': '955 Goodwin Mills Suite 953\nPaynestad, MS 09182',
    'text': 'Place impact assume. Service air together idea then. Religious part write break.\nRate turn line western. Of money benefit test evening door.',
    'email': 'williamsjennifer@example.net',
    'phone_number': '001-605-847-3238',
    'json': {
    'name': 'Hannah Glover',
    'address': '93166 Emily Harbor\nNew Michael, NY 96126',
},
    'key89119': 'value43602',
},
    {
    'id': 17527486822978,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Shannon Summers',
    'address': '76880 Ward Bypass\nIantown, IL 01863',
    'text': 'Day blue artist. Order whether entire foreign without to talk.\nCulture run policy deal his. Join another could say program beautiful.\nDesign when skin across. Same federal study western figure.',
    'email': 'kelli54@example.com',
    'phone_number': '(699)491-5222x992',
    'json': {
    'name': 'James Coffey',
    'address': '2385 Brown Walk Apt. 049\nNorth Johnborough, IA 28637',
},
    'key759': 'value48532',
    'key66805': 'value5341',
    'key1512': 'value49222',
    'key2353': 'value84285',
    'key9047': 'value34207',
    'key25870': 'value39884',
},
    {
    'id': 17527486822989,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Tara Gonzales',
    'address': '33232 Waters Rapid Apt. 352\nButlermouth, NY 34722',
    'text': 'Seven next some exactly. Old fish attention yourself quite so pretty. Senior huge everybody find thought.\nThus sell explain two success customer. Ever decision building north attorney.',
    'email': 'rogerspriscilla@example.org',
    'phone_number': '613-417-8132',
    'json': {
    'name': 'Jared Adams',
    'address': '811 Rodriguez Flats Suite 706\nGreenburgh, CO 95106',
},
    'key61949': 'value16844',
    'key70014': 'value92565',
    'key58362': 'value14331',
    'key58368': 'value59865',
    'key18153': 'value15470',
    'key14399': 'value54193',
    'key88680': 'value79163',
    'key97448': 'value36318',
    'key51054': 'value15868',
    'key65581': 'value42790',
},
    {
    'id': 17527486823001,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Peter Blake',
    'address': '919 Johnson Meadow Apt. 903\nPort Charles, VA 29433',
    'text': 'Really better with spring whole I way. Wind agree include occur modern girl.\nChange whole manager result. Bit food property.\nMinute scientist network in specific sit. Memory want region main act.',
    'email': 'brian72@example.com',
    'phone_number': '001-813-780-5106x4391',
    'json': {
    'name': 'Paul White',
    'address': '87781 Nicole Manor Suite 132\nSouth Josephchester, SC 70256',
},
    'key38754': 'value15665',
    'key50194': 'value64092',
    'key73800': 'value77517',
    'key92397': 'value69027',
    'key44997': 'value57467',
},
    {
    'id': 17527486823012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Danielle Berger MD',
    'address': '297 Rice Rue\nSouth Anthonyburgh, AR 77776',
    'text': 'Tree actually land take few. Top first next avoid beautiful name.\nCharacter artist American skin. Civil become before huge later woman turn. Million others before well boy end standard.',
    'email': 'dharris@example.org',
    'phone_number': '(392)523-5762',
    'json': {
    'name': 'Andrew Bowers',
    'address': '7470 Mejia Key\nJeanetteberg, FM 56156',
},
    'key53771': 'value86964',
    'key41108': 'value71637',
    'key72085': 'value32859',
    'key88985': 'value47414',
    'key52217': 'value55321',
},
    {
    'id': 17527486823023,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Kelly Young',
    'address': '972 Robert Glen\nEast Jordantown, FL 87119',
    'text': 'Create hour half style important often go cover. Green early order finish medical message.',
    'email': 'melissagarcia@example.net',
    'phone_number': '+1-513-603-0643',
    'json': {
    'name': 'Clinton Perez',
    'address': '362 Jonathan Throughway\nJonesfurt, IA 77069',
},
    'key70631': 'value40497',
    'key31661': 'value82844',
},
    {
    'id': 17527486823034,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'William Cruz',
    'address': '104 Dixon Field\nMelissashire, MS 21301',
    'text': 'Test recently rate blood alone dinner push between. Space have behavior positive every young green.\nResponse business fine. Drive participant determine fill station pull.',
    'email': 'smithpatrick@example.com',
    'phone_number': '001-872-529-3957x29661',
    'json': {
    'name': 'Kim Whitehead',
    'address': 'USS Sherman\nFPO AP 47609',
},
    'key23685': 'value47463',
    'key70420': 'value26540',
    'key87521': 'value86324',
},
    {
    'id': 17527486823045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Michael Miller',
    'address': '63179 Paul Squares\nHeidibury, GA 08954',
    'text': 'Responsibility spring report still successful.\nAgainst role side onto soldier responsibility skin. As anyone part white language source play.',
    'email': 'johnsonbrandon@example.net',
    'phone_number': '478-925-0916',
    'json': {
    'name': 'Jessica Walton',
    'address': '4689 Bobby Underpass\nSouth Brianchester, NV 64676',
},
    'key82968': 'value14963',
    'key7311': 'value25084',
    'key8031': 'value30018',
    'key3261': 'value53638',
    'key92550': 'value64712',
    'key34993': 'value8488',
    'key51606': 'value96430',
    'key75173': 'value95553',
    'key94635': 'value27237',
},
    {
    'id': 17527486823056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Monica Holloway',
    'address': '7312 Jones Spurs\nBlakeview, KY 61890',
    'text': 'Huge become interesting able take. Almost authority world never. Small million go clear buy stop experience.\nEconomy whose protect. Act sure source expect study learn election.',
    'email': 'syork@example.com',
    'phone_number': '001-202-231-6328x095',
    'json': {
    'name': 'Miranda Graham',
    'address': '49148 Evans Summit Suite 224\nLake Tracyfurt, NC 67939',
},
    'key5237': 'value89911',
    'key80837': 'value47953',
    'key54443': 'value63962',
    'key59351': 'value64696',
},
    {
    'id': 17527486823067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Mr. Scott Rojas',
    'address': '51355 Deleon Harbors\nBeckertown, WY 07808',
    'text': 'Get customer campaign must drug himself. Sell toward necessary American cold treatment south. Sort happy receive customer.',
    'email': 'phillipschultz@example.com',
    'phone_number': '+1-276-943-7100x98250',
    'json': {
    'name': 'Kevin Weeks',
    'address': '0834 Horton Flat\nLake Cynthia, PR 34952',
},
    'key14768': 'value46365',
    'key8159': 'value5844',
    'key84472': 'value61547',
    'key18359': 'value72007',
},
    {
    'id': 17527486823079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'David Shaw',
    'address': '66449 Jason Crossroad Suite 294\nThomashaven, CA 30224',
    'text': 'Maintain including really action certain. Develop travel item bed. With drug star start daughter.\nPressure believe another growth fear appear of.',
    'email': 'currytina@example.net',
    'phone_number': '9938704991',
    'json': {
    'name': 'Bruce Best',
    'address': '6317 Moon Field Suite 962\nSmithside, AS 82023',
},
    'key4881': 'value62992',
    'key59604': 'value55381',
    'key37371': 'value10712',
    'key96066': 'value27225',
    'key38942': 'value62176',
    'key12522': 'value90434',
    'key30740': 'value49156',
    'key2418': 'value90023',
    'key32722': 'value57968',
},
    {
    'id': 17527486823091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Robert Frye',
    'address': '0704 Farley Street Apt. 265\nPort Emmaport, VI 14771',
    'text': 'Able interest although blood walk. Deep religious easy nothing turn dream order trial. Share good able green us.',
    'email': 'ricardo92@example.org',
    'phone_number': '981-822-8042',
    'json': {
    'name': 'Jessica Page',
    'address': '9250 Melissa Crossroad Apt. 908\nTimothyside, MN 88662',
},
    'key16513': 'value60854',
    'key24003': 'value22835',
    'key23692': 'value7357',
    'key14139': 'value305',
},
    {
    'id': 17527486823101,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Rick Chase',
    'address': '1573 Boyer Field\nNorth Nicolechester, FL 65262',
    'text': 'Democratic fill store he red allow. After can herself change personal. Computer hand sit apply health.',
    'email': 'haysfaith@example.net',
    'phone_number': '4065594319',
    'json': {
    'name': 'Elizabeth Pierce',
    'address': '275 Franklin Pine Apt. 301\nDawnview, MO 24888',
},
    'key50343': 'value1031',
    'key22973': 'value34886',
    'key80582': 'value50219',
    'key8871': 'value97171',
    'key27719': 'value83775',
    'key55550': 'value72666',
},
    {
    'id': 17527486823113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Charles Payne',
    'address': '86772 Mcclure Mill Suite 128\nEast Rodney, IN 74071',
    'text': 'Money already claim tough art community mention. Assume including choose open I husband.\nRoom understand indicate subject. Itself all several. Discussion tax explain especially.',
    'email': 'davisbrandy@example.com',
    'phone_number': '359-788-1393x31665',
    'json': {
    'name': 'Kenneth Bennett',
    'address': 'USNV Garcia\nFPO AE 04742',
},
    'key31080': 'value15533',
    'key13925': 'value91366',
    'key1266': 'value34393',
    'key58552': 'value21814',
    'key16864': 'value66381',
    'key24012': 'value23404',
    'key87093': 'value52692',
    'key95683': 'value80883',
    'key71733': 'value37382',
},
    {
    'id': 17527486823123,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Crystal Smith',
    'address': '0878 Castaneda Lights\nSamanthaton, FM 56916',
    'text': 'Life consider could something indicate executive. Between future outside second. Stay attention second cover. There employee maintain argue theory such tough take.',
    'email': 'andrewwalker@example.org',
    'phone_number': '+1-316-439-5385x403',
    'json': {
    'name': 'Mr. Keith Walter',
    'address': '95108 Hunter Neck Suite 000\nRobertsonburgh, NH 78041',
},
    'key31911': 'value49324',
    'key73945': 'value97270',
    'key80603': 'value75670',
    'key99294': 'value91047',
    'key36173': 'value13800',
    'key87596': 'value52295',
    'key9122': 'value86987',
    'key68941': 'value41781',
    'key83926': 'value31218',
    'key65642': 'value96769',
},
    {
    'id': 17527486823136,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Colton Schneider',
    'address': '21505 Robert Summit\nHallchester, UT 13526',
    'text': 'Popular role long worker option all. Where whatever order full college. Local smile develop more.\nHouse bill film since expert animal. Find not behavior per yeah. War interest director range.',
    'email': 'svaughn@example.org',
    'phone_number': '+1-598-984-1311',
    'json': {
    'name': 'Jeffrey Dorsey',
    'address': '3839 Kristen Hollow\nAmandaside, VA 88945',
},
    'key61884': 'value9820',
    'key41022': 'value18500',
},
    {
    'id': 17527486823146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Kimberly Brennan',
    'address': '76275 Angelica Mews\nJamesshire, FM 48928',
    'text': 'News must standard. Business point design dog first past describe.\nTax candidate and by. Radio somebody do statement total everything. Low manager American certain hot not character happen.',
    'email': 'julianash@example.net',
    'phone_number': '001-593-660-9018x419',
    'json': {
    'name': 'Jenna Benton',
    'address': '4175 Murphy Rue\nGregoryborough, IN 70994',
},
    'key3894': 'value56835',
    'key44946': 'value79487',
    'key72878': 'value46874',
    'key66132': 'value39853',
    'key73303': 'value24645',
},
    {
    'id': 17527486823158,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Mark Rodriguez',
    'address': '757 Lauren Gateway Apt. 978\nJessicamouth, UT 91803',
    'text': 'Change still effort social share.\nFace foot both water value hotel. Bed consider part we together collection run performance.',
    'email': 'huntsusan@example.com',
    'phone_number': '655-346-9681',
    'json': {
    'name': 'Doris Perez',
    'address': '619 Stephanie Inlet\nLake John, VI 88822',
},
    'key65474': 'value48359',
},
    {
    'id': 17527486823168,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Sarah Phillips',
    'address': '8302 Michael Haven Suite 322\nHowardbury, FM 08108',
    'text': 'Attorney by Congress success.\nThan amount science note month trouble type. West morning a fall let task sit debate.',
    'email': 'brendandixon@example.com',
    'phone_number': '919-790-1752x167',
    'json': {
    'name': 'Corey Richmond',
    'address': '003 Francis Camp\nWalkerport, AR 80365',
},
    'key11276': 'value1807',
    'key17242': 'value96914',
    'key53899': 'value49966',
    'key30708': 'value35473',
    'key12291': 'value51163',
    'key53473': 'value20809',
    'key6990': 'value70205',
    'key329': 'value88409',
},
    {
    'id': 17527486823180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Heather Garcia',
    'address': '792 Silva Forks Apt. 633\nEast Michael, TN 21160',
    'text': 'Now various action guess center. Nice good claim.\nSmall remember military pretty. Congress eat edge fact range century hospital.',
    'email': 'johnjacobson@example.net',
    'phone_number': '663-313-4556',
    'json': {
    'name': 'Jessica Williams',
    'address': '795 Heather Street Suite 992\nEast Matthew, IA 84720',
},
    'key80546': 'value73929',
    'key86237': 'value90785',
},
    {
    'id': 17527486823192,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Michele Wagner',
    'address': '48465 Levine Forks Apt. 149\nCharlesfurt, MP 30848',
    'text': 'Little dark number staff work.\nNear everyone popular discuss along how. Economy standard every all just common.',
    'email': 'daniellewallace@example.com',
    'phone_number': '291.548.7492',
    'json': {
    'name': 'Vanessa Dodson',
    'address': '7997 Adam Inlet Apt. 052\nLake Jessicatown, AZ 66267',
},
    'key36122': 'value28043',
    'key80237': 'value89627',
    'key52404': 'value32666',
    'key43694': 'value29280',
    'key18784': 'value87010',
    'key4834': 'value87329',
    'key15772': 'value4074',
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
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



    def test_request_4(self):
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
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
    'RequestId': '19bdea80-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_56_174794KEljrfkg',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-10+20 <= uid < 20+30]_1752748690.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalse1020Uid20301752748690Json()
    test.run_tests()
