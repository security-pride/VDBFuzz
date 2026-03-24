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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752748792_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752748792.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUidIn12341752748792Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752748792.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752748792.json"
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
    'data': [
    {
    'id': 17527487844256,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Karen Holland',
    'address': '23891 Timothy Drives\nEast Maria, SD 60674',
    'text': 'Drive writer instead full side him very. Give safe green note. Agree sport indicate.\nPay treat onto describe too. History nor take station mind least.\nMaybe mission western guy federal travel.',
    'email': 'kaitlyn52@example.com',
    'phone_number': '+1-590-581-9108x822',
    'json': {
    'name': 'Alexander Peters',
    'address': 'PSC 2282, Box 9018\nAPO AE 44029',
},
    'key91316': 'value50695',
    'key74089': 'value3965',
    'key18916': 'value4365',
    'key52657': 'value42244',
    'key39215': 'value64052',
    'key87725': 'value8169',
    'key56196': 'value158',
    'key16332': 'value94008',
},
    {
    'id': 17527487844269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sharon Young',
    'address': '687 Kaitlyn Streets\nWest Lisa, PR 60015',
    'text': 'Dinner speak social page. Attorney person consumer but.\nMessage professor right institution. Exactly article boy age employee. Not huge property argue security go fly.',
    'email': 'colegood@example.com',
    'phone_number': '958.977.6929x12429',
    'json': {
    'name': 'Jesse Moore',
    'address': '3021 Robert Greens Apt. 484\nPetersenchester, MN 14626',
},
    'key84598': 'value45842',
    'key32422': 'value50578',
    'key48143': 'value58331',
    'key17663': 'value88559',
    'key98361': 'value86651',
    'key78893': 'value48743',
    'key85910': 'value49905',
    'key33392': 'value4949',
},
    {
    'id': 17527487844282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'James Glover',
    'address': '71394 Lopez Gardens Apt. 396\nNew Kerryview, WI 12144',
    'text': 'Thousand media into. Table next evening attorney single factor by.\nCampaign job model foot now same. Continue church person her moment south maintain usually. Reach discuss popular arm.',
    'email': 'robinthomas@example.net',
    'phone_number': '307.844.7002x2574',
    'json': {
    'name': 'Donna Sullivan',
    'address': '549 Kimberly Vista Apt. 480\nPort Derek, ID 96541',
},
    'key94353': 'value68804',
},
    {
    'id': 17527487844295,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Lauren Cook',
    'address': '111 Kramer Isle Suite 191\nWarrentown, MP 86435',
    'text': 'Out she off deal responsibility. Nothing body happy management society.\nKitchen beautiful top fact. Relationship let watch reason yourself along system.',
    'email': 'troberts@example.com',
    'phone_number': '001-560-526-4004',
    'json': {
    'name': 'Kenneth Gibson Jr.',
    'address': '431 Hunter Island Apt. 355\nMarkport, SC 12302',
},
    'key41252': 'value78427',
    'key43355': 'value91207',
},
    {
    'id': 17527487844307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Joshua Knox',
    'address': '007 Malone Brooks\nWendytown, VI 96566',
    'text': 'Education see call nearly good also success. Dream gun change police. Weight surface message chance this give.\nHit lawyer wife own prepare. Maintain lose able measure instead bad.',
    'email': 'kevinconner@example.net',
    'phone_number': '(703)556-6594',
    'json': {
    'name': 'Diane Scott',
    'address': '4466 Lewis Center\nEast Vanessa, AS 58394',
},
    'key38589': 'value98895',
    'key60277': 'value3277',
    'key75143': 'value10311',
    'key70501': 'value60006',
    'key39935': 'value92945',
    'key54931': 'value59253',
    'key72970': 'value19815',
    'key40052': 'value56937',
    'key79642': 'value71787',
},
    {
    'id': 17527487844319,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jeanette Rosales',
    'address': '8024 Pamela Loaf\nBeverlybury, NC 72832',
    'text': 'Least stock several in worker.\nSeries Republican particular choose morning. That treat run there skill claim. Cell sense generation room.\nWant any vote. Energy until compare.',
    'email': 'natashakennedy@example.net',
    'phone_number': '001-590-565-9097x861',
    'json': {
    'name': 'Joseph Harrell',
    'address': '9226 Stark Crescent Apt. 916\nEast Brianburgh, DC 30679',
},
    'key71606': 'value12906',
    'key12686': 'value8638',
    'key23212': 'value75662',
    'key18268': 'value88383',
},
    {
    'id': 17527487844331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Patricia Fleming',
    'address': '774 Lewis Square\nDebbiehaven, LA 83950',
    'text': 'Audience majority water. Like job kitchen what.\nWho spend morning. Keep evidence affect baby star decision. Life fall also determine.',
    'email': 'taylorcaleb@example.org',
    'phone_number': '732.868.3005x77387',
    'json': {
    'name': 'Rhonda Johnson',
    'address': '8257 Dennis Parks Apt. 290\nDavidchester, NM 10792',
},
    'key33042': 'value15092',
},
    {
    'id': 17527487844343,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Samantha Chavez',
    'address': '732 Jonathan Village\nLake Walter, NE 81879',
    'text': 'Soon hope performance few hold computer explain. Cup sign edge stand. Talk policy physical hospital both until event. Focus child more write do gas.',
    'email': 'leejenna@example.org',
    'phone_number': '674.815.0324',
    'json': {
    'name': 'Danielle Stephens',
    'address': '228 Parker Gateway Apt. 806\nNew Thomas, ME 65783',
},
    'key63293': 'value21460',
    'key74302': 'value81109',
    'key12299': 'value77563',
    'key85674': 'value44685',
    'key13124': 'value94588',
    'key49812': 'value63212',
},
    {
    'id': 17527487844354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Maria Sanchez',
    'address': '381 Jesse Hill\nPagestad, ME 31937',
    'text': 'Financial to difference across. Medical offer American high.\nAround walk result ability send. Project either laugh management. Realize seven meet artist occur capital trial.',
    'email': 'kimberlystewart@example.com',
    'phone_number': '2997642420',
    'json': {
    'name': 'Carol Mack',
    'address': '3154 Melvin Loaf\nKatieburgh, MO 53085',
},
    'key71834': 'value79357',
},
    {
    'id': 17527487844366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Betty Brown',
    'address': '6388 Marshall Unions\nSouth Brenda, ID 18554',
    'text': 'Pressure particular through which federal. Big four family field adult blue pay. Trial so fine chair property identify behind.',
    'email': 'carlos84@example.net',
    'phone_number': '459-426-2142',
    'json': {
    'name': 'Megan Miller',
    'address': '426 Garcia Parkway Apt. 289\nRobertfort, ND 07425',
},
    'key65626': 'value56862',
    'key18428': 'value56809',
    'key86394': 'value8901',
    'key91491': 'value59271',
    'key72914': 'value10107',
    'key41961': 'value26412',
    'key90170': 'value67263',
    'key47036': 'value54865',
},
    {
    'id': 17527487844377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Jacob Bautista',
    'address': '576 Jacobson Green Suite 183\nTeresaland, NM 79805',
    'text': 'Before line worker range tonight. Pattern common thought prove. Serve thank example own cultural according. Attorney out red road including.',
    'email': 'sreynolds@example.org',
    'phone_number': '+1-767-293-4549x04085',
    'json': {
    'name': 'Edward Thompson',
    'address': 'Unit 1942 Box 0702\nDPO AE 83016',
},
    'key78971': 'value28119',
    'key26816': 'value77280',
    'key52692': 'value29459',
    'key16298': 'value8005',
    'key18995': 'value82328',
},
    {
    'id': 17527487844386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Jeremiah Whitehead',
    'address': '8251 Thomas Points\nOrtizburgh, LA 29251',
    'text': 'Affect pressure despite floor example. Degree forward through keep. Agent identify house attorney style measure.',
    'email': 'alisha71@example.org',
    'phone_number': '806-446-0382',
    'json': {
    'name': 'Laurie Harding',
    'address': '48609 Richards Forges\nEast Jenniferport, PR 54282',
},
    'key47529': 'value36859',
    'key27185': 'value5886',
    'key50522': 'value38253',
    'key82953': 'value14152',
    'key32982': 'value46187',
    'key63518': 'value15833',
    'key90790': 'value33162',
    'key37654': 'value95361',
    'key4277': 'value74607',
},
    {
    'id': 17527487844396,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Peter Rowland',
    'address': '5112 Michael Valleys Apt. 927\nSeanhaven, MO 16451',
    'text': 'According step have least lose. Control return agency military hot sea. Three wonder thought here position owner realize.',
    'email': 'uhill@example.net',
    'phone_number': '(396)244-9861x15078',
    'json': {
    'name': 'Maria Young',
    'address': '6753 Brown Mills Suite 333\nPort Zoeborough, TN 72706',
},
    'key79586': 'value93639',
    'key19838': 'value9658',
    'key4150': 'value19971',
    'key14824': 'value94626',
    'key10811': 'value79739',
},
    {
    'id': 17527487844407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jeffrey White',
    'address': '646 Jamie Points Apt. 634\nDustinberg, NH 21992',
    'text': 'Green deep product recently level likely. Quite country situation among writer. Through question fish.',
    'email': 'reneeclark@example.org',
    'phone_number': '+1-899-393-7456',
    'json': {
    'name': 'Debbie Hoffman',
    'address': '1810 Tonya Valley\nPort Richard, IA 96209',
},
    'key52060': 'value47367',
    'key6053': 'value33607',
    'key99351': 'value58201',
},
    {
    'id': 17527487844419,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jean Sharp',
    'address': '177 William Radial Suite 538\nSouth Marioland, NE 01130',
    'text': 'Off the accept fact method oil card. Six process discuss senior. Heavy require example hotel get.\nWell evening kitchen describe candidate improve. Leg on article effect.',
    'email': 'brandonsmith@example.org',
    'phone_number': '(551)290-2330x676',
    'json': {
    'name': 'Michelle Rivers',
    'address': '98224 Gardner Points\nChristinaland, FM 04557',
},
    'key69767': 'value40666',
    'key14494': 'value34959',
    'key7189': 'value52257',
    'key57927': 'value15251',
},
    {
    'id': 17527487844430,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Lindsey Bryant',
    'address': '6134 Charles Rapid Apt. 591\nDonnahaven, IN 56850',
    'text': 'Sure apply important early red door. Others institution bank least attention store.\nStation happen produce remember enjoy. Discover against foot tell teach.',
    'email': 'sonya06@example.org',
    'phone_number': '(276)526-8427x63928',
    'json': {
    'name': 'David Conley',
    'address': '90967 Erica Ridge Suite 204\nSouth Vincentport, MO 02239',
},
    'key96063': 'value58289',
    'key98899': 'value9561',
    'key36743': 'value78611',
    'key72741': 'value76478',
    'key13540': 'value5117',
    'key13989': 'value56196',
    'key72585': 'value5723',
    'key81663': 'value28670',
    'key74774': 'value79217',
},
    {
    'id': 17527487844441,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Miss Mary Perez',
    'address': '79874 Joel Manors Apt. 621\nMatthewtown, CO 34332',
    'text': 'Media style attention yard. Approach hold project all nice use save while.\nBest direction soon pass. Out second benefit politics church.',
    'email': 'julie25@example.com',
    'phone_number': '(870)561-9695x580',
    'json': {
    'name': 'James Rodriguez',
    'address': '4866 Matthew Isle\nNew Stephanie, AZ 04589',
},
    'key55092': 'value29981',
    'key268': 'value37469',
    'key3311': 'value21999',
},
    {
    'id': 17527487844451,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'William Patton',
    'address': '236 Anthony Point\nNorth Elizabethfurt, MS 53416',
    'text': 'Big man civil realize article change total.\nMiss five under choose certainly south friend happen. Commercial food player cell owner.',
    'email': 'holtsandra@example.net',
    'phone_number': '581.768.3547',
    'json': {
    'name': 'Renee Saunders',
    'address': '3764 Thompson Viaduct\nWest Anthony, NE 56763',
},
    'key21876': 'value30167',
    'key28314': 'value67073',
    'key36955': 'value1669',
    'key1659': 'value72220',
    'key26623': 'value80609',
    'key55907': 'value62227',
    'key89624': 'value56069',
    'key76605': 'value90246',
    'key505': 'value85376',
},
    {
    'id': 17527487844463,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Robert Mcdaniel',
    'address': 'Unit 8078 Box 8973\nDPO AE 85650',
    'text': 'Possible leg head painting face assume pattern. Evening increase discuss candidate lead.\nSong leave teach man as. Send get role body turn difficult career. Animal event break.',
    'email': 'codyrivera@example.net',
    'phone_number': '862.451.5008',
    'json': {
    'name': 'Andrew Cox',
    'address': '666 Amy Crossing Suite 710\nDylanmouth, MH 70544',
},
    'key27144': 'value79464',
    'key61129': 'value26075',
    'key39527': 'value69858',
    'key40627': 'value97333',
    'key10950': 'value77431',
    'key76172': 'value93200',
    'key85262': 'value51286',
    'key77239': 'value56913',
    'key3062': 'value79446',
    'key10679': 'value85066',
},
    {
    'id': 17527487844472,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Donald Carpenter',
    'address': '86862 Evans Street Suite 909\nChavezfurt, MO 18502',
    'text': 'Country suddenly you mention very outside spring.\nWalk always sense. Hand message wind community. Stock rest teacher imagine thing main.',
    'email': 'znielsen@example.net',
    'phone_number': '001-844-449-5571',
    'json': {
    'name': 'Amy Banks',
    'address': '15360 Nicole Rapids Apt. 719\nJuliehaven, FL 12867',
},
    'key54382': 'value60406',
    'key49485': 'value52332',
    'key55679': 'value13653',
    'key64987': 'value40591',
    'key26718': 'value96205',
},
    {
    'id': 17527487844483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Connie Solomon',
    'address': '722 Keith Mall\nWest Nathanmouth, MI 12573',
    'text': 'Piece goal past no it eight road. High whether law industry show pattern care some. Rather provide reveal always. Standard short how meeting back consider certain she.',
    'email': 'ekaufman@example.net',
    'phone_number': '207-679-2173',
    'json': {
    'name': 'Jeffrey Contreras',
    'address': '25540 Brown Flat Suite 378\nSouth Rebecca, UT 33427',
},
    'key82456': 'value17063',
    'key99872': 'value80637',
    'key88687': 'value60776',
    'key7459': 'value24657',
    'key14523': 'value7205',
    'key67554': 'value34648',
    'key72031': 'value3767',
    'key41528': 'value49050',
    'key23656': 'value51586',
    'key36637': 'value64007',
},
    {
    'id': 17527487844494,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Melissa Higgins',
    'address': '63927 Jessica Estate\nLake Heather, AK 33508',
    'text': 'Finally begin personal church. Investment concern inside likely discuss. College no produce happen drug degree option.',
    'email': 'mckenzieashley@example.com',
    'phone_number': '867-955-2505x4178',
    'json': {
    'name': 'James Giles DDS',
    'address': '500 William Summit\nSouth Patrick, AR 34203',
},
    'key50392': 'value63730',
    'key18218': 'value98353',
    'key43805': 'value32616',
    'key27065': 'value69581',
    'key12848': 'value69507',
    'key50687': 'value61619',
    'key44230': 'value14839',
    'key53270': 'value63799',
},
    {
    'id': 17527487844505,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Victor Morris',
    'address': '29551 Antonio Drives Apt. 983\nNorth Kerry, OH 92244',
    'text': 'Event wide network kind. Baby decide red option teach see style.\nJoin customer blue rather water amount trip manage. Late serve each value. While beautiful day sense group resource.',
    'email': 'nwashington@example.org',
    'phone_number': '303.293.1856',
    'json': {
    'name': 'Gavin Williams',
    'address': '8763 Robert Mountains Suite 124\nHaneytown, ND 50088',
},
    'key67442': 'value11404',
    'key96871': 'value43488',
    'key25056': 'value61347',
    'key80014': 'value45125',
    'key12983': 'value69514',
},
    {
    'id': 17527487844516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Juan Ewing',
    'address': '71615 Villegas Landing\nNorth Jenniferfurt, RI 48741',
    'text': 'Defense ahead response. Evidence onto garden campaign. Democratic little long service expert.',
    'email': 'abrooks@example.net',
    'phone_number': '(489)554-4039',
    'json': {
    'name': 'Jasmine Zamora',
    'address': '0815 Heidi Junctions Apt. 033\nBauerborough, VA 19134',
},
    'key29482': 'value55177',
    'key45176': 'value68853',
    'key64377': 'value99169',
    'key39427': 'value60501',
    'key83127': 'value22581',
    'key99689': 'value32442',
},
    {
    'id': 17527487844527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Dr. Cheryl Hammond',
    'address': '286 Joshua Plaza Suite 792\nWest Cameron, AZ 07055',
    'text': 'War fact fund Mrs occur enjoy coach. Tv notice best approach. Share price professor.\nRate Mr cold house eight. Person management around carry nice sound.',
    'email': 'brian06@example.net',
    'phone_number': '(839)453-9525x6345',
    'json': {
    'name': 'Megan Odom',
    'address': 'Unit 7109 Box 0592\nDPO AE 00817',
},
    'key13675': 'value10986',
    'key55666': 'value54613',
    'key83176': 'value69279',
    'key66400': 'value23336',
    'key96336': 'value30534',
    'key34768': 'value72079',
    'key79509': 'value967',
    'key19684': 'value82219',
},
    {
    'id': 17527487844536,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Christopher Moore',
    'address': '93196 Holly Trail Suite 221\nNorth Amanda, VI 90576',
    'text': 'Organization address together use inside order. Call according morning window reality determine.\nPay why dream gun save. Fear quite team.',
    'email': 'lukeevans@example.com',
    'phone_number': '937-640-9257',
    'json': {
    'name': 'Stacey James',
    'address': '9571 Jamie Route\nMacdonaldmouth, NH 31492',
},
    'key79099': 'value69862',
    'key18869': 'value76751',
    'key77904': 'value69156',
    'key35316': 'value58050',
    'key44128': 'value96592',
    'key82245': 'value13146',
    'key45112': 'value78137',
    'key46795': 'value97976',
},
    {
    'id': 17527487844547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Kathy Cabrera',
    'address': 'USCGC White\nFPO AE 25470',
    'text': 'Decide short onto trouble. Cultural only answer tell way either. Travel attack clearly bill evening population administration.',
    'email': 'duranwilliam@example.org',
    'phone_number': '360.962.6652x89087',
    'json': {
    'name': 'Thomas Bird',
    'address': '4928 Smith Squares Suite 639\nNew Kenneth, OH 45304',
},
    'key26311': 'value91013',
    'key70099': 'value76288',
    'key73249': 'value37918',
},
    {
    'id': 17527487844557,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Mary Bryant',
    'address': '33655 Kimberly Alley Suite 313\nLake Peter, ID 04160',
    'text': 'Program agent each allow. Democrat here stand.\nWithin research beautiful successful space.\nAttention hair effect learn machine five. And quickly watch operation name.',
    'email': 'xmoore@example.com',
    'phone_number': '+1-296-754-1536x17860',
    'json': {
    'name': 'April Evans',
    'address': 'Unit 5460 Box 9529\nDPO AE 93519',
},
    'key56157': 'value33972',
    'key15862': 'value91178',
    'key48569': 'value94323',
    'key76164': 'value21629',
    'key37521': 'value87998',
    'key41578': 'value47569',
    'key96789': 'value94122',
    'key25107': 'value80493',
},
    {
    'id': 17527487844567,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jacob Ward',
    'address': '04017 Yoder Overpass Suite 175\nLake Laura, FL 02782',
    'text': 'Back computer strategy stage dark tough. Issue I some rule executive position fine.',
    'email': 'tylerblair@example.com',
    'phone_number': '(843)305-8465x17401',
    'json': {
    'name': 'Patrick Clayton',
    'address': '814 Nelson Knolls Apt. 320\nNorth Robertview, GU 56329',
},
    'key46067': 'value19169',
    'key76574': 'value88477',
    'key39682': 'value76389',
    'key10185': 'value27791',
    'key24537': 'value76634',
    'key59169': 'value71726',
    'key69814': 'value77339',
    'key48894': 'value57688',
},
    {
    'id': 17527487844578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Jasmine Carrillo',
    'address': '806 Ruth Square Apt. 860\nNew Christopher, FM 03280',
    'text': 'If since recognize speech. Fire dog work happen six cup ready.\nShould away economy friend one. Time science red common spring.\nName star cell form. Hair music six rule table in situation born.',
    'email': 'thorntonelizabeth@example.net',
    'phone_number': '239.282.3506x193',
    'json': {
    'name': 'Austin Duran',
    'address': '094 Moore Isle Suite 686\nLake Danielport, HI 67961',
},
    'key7810': 'value68415',
    'key57800': 'value9780',
    'key94426': 'value42530',
},
    {
    'id': 17527487844590,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Vincent Owens',
    'address': '765 Powers Motorway Apt. 518\nPowellton, ME 85313',
    'text': 'Hope best water husband. Congress often cost always wrong.',
    'email': 'wilsoncrystal@example.net',
    'phone_number': '394.375.1549x963',
    'json': {
    'name': 'Tracy Shields',
    'address': '9725 Jessica Port Apt. 153\nNew Karenville, MO 56750',
},
    'key46215': 'value66229',
    'key31429': 'value2977',
    'key26165': 'value27478',
    'key90216': 'value79290',
    'key90847': 'value38220',
},
    {
    'id': 17527487844602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Lori Carter',
    'address': '5087 Gregory Islands\nNorth Alexandraton, TX 81279',
    'text': 'Commercial development local add within. Live account deep film employee man. Challenge single organization finally project lot.\nWhole early consumer toward maybe require. Draw Mrs third begin.',
    'email': 'millerryan@example.com',
    'phone_number': '001-307-788-7009x24831',
    'json': {
    'name': 'Ashley Mendoza',
    'address': '3446 Karen Stravenue Suite 973\nEast Jenniferport, MD 26265',
},
    'key94582': 'value56076',
    'key24726': 'value74089',
},
    {
    'id': 17527487844613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Michael Jensen',
    'address': '695 Gabriel Points\nNorth Jacobtown, VT 63734',
    'text': 'Short model between guy reduce through federal. Baby remember because water animal seem good. Painting attention develop physical onto.',
    'email': 'sheena11@example.net',
    'phone_number': '823-582-3874',
    'json': {
    'name': 'Kathryn Velez',
    'address': '341 Holly Grove\nSouth Robert, FM 82015',
},
    'key18071': 'value18325',
    'key86909': 'value84476',
    'key38882': 'value9939',
},
    {
    'id': 17527487844623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Stacy Ellis',
    'address': '86893 Khan Mall\nGlennburgh, AS 60465',
    'text': 'No teacher way hold offer attorney dog. Strong machine owner life.\nFinal yard government lot themselves talk. Across responsibility reason quickly relate.',
    'email': 'yuapril@example.net',
    'phone_number': '798.841.7508',
    'json': {
    'name': 'Olivia Cook',
    'address': '97321 Dustin Ports\nEast Joseland, IN 62392',
},
    'key85510': 'value35821',
    'key54032': 'value89458',
    'key30472': 'value84461',
    'key76791': 'value75033',
    'key8685': 'value2317',
},
    {
    'id': 17527487844634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Paula Osborne',
    'address': '9434 Tammy Forest Suite 570\nEast Elizabeth, HI 44867',
    'text': 'Cup challenge smile industry. Road then science pretty.\nLevel high scientist. Less small property quickly health camera sense.\nBoard word policy.',
    'email': 'jwilliams@example.org',
    'phone_number': '(335)270-8373x0475',
    'json': {
    'name': 'Matthew Harris',
    'address': '8592 Davis Street\nLewisfort, WI 84861',
},
    'key53251': 'value5023',
    'key70998': 'value68881',
    'key90611': 'value68179',
    'key70534': 'value54343',
    'key35021': 'value87282',
    'key52475': 'value38407',
    'key57202': 'value48630',
    'key98663': 'value31576',
},
    {
    'id': 17527487844645,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Anna Anderson',
    'address': '840 King Port Suite 727\nSouth James, DC 86902',
    'text': 'Southern better shoulder want culture one return. View college stock again standard them.',
    'email': 'jennycastro@example.net',
    'phone_number': '490.267.4883x24566',
    'json': {
    'name': 'Michael Patrick',
    'address': '2242 Brittany Groves Suite 249\nTylerbury, AR 08296',
},
    'key71481': 'value77903',
    'key82139': 'value47845',
    'key91724': 'value64821',
    'key7195': 'value14903',
    'key83093': 'value67884',
    'key87352': 'value34098',
},
    {
    'id': 17527487844656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Alexander Marshall',
    'address': '083 Teresa Tunnel Apt. 611\nNorth Olivia, MS 99236',
    'text': 'Wife put most score. Religious fly everybody recognize expert indeed number.\nRisk force source. Bar produce four them guess.',
    'email': 'melindabrown@example.com',
    'phone_number': '+1-238-342-4598x38982',
    'json': {
    'name': 'Tammy Bryan',
    'address': '3896 Joshua Crossroad Suite 195\nWest Isabel, NM 18114',
},
    'key70275': 'value13472',
    'key76963': 'value70932',
    'key78512': 'value5334',
    'key15815': 'value10095',
    'key15112': 'value63012',
    'key14462': 'value33972',
    'key54077': 'value77556',
    'key9504': 'value15097',
    'key50697': 'value48463',
    'key81657': 'value63551',
},
    {
    'id': 17527487844668,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Janice Jones',
    'address': '044 Seth Park\nEast Michaelmouth, WA 98081',
    'text': 'Guess plan director. Suddenly agency a recognize necessary rock yard since.\nSpace all include really defense. Fine again moment any professional car.\nSuddenly network down surface evidence reach.',
    'email': 'charlesburns@example.com',
    'phone_number': '+1-422-248-4313',
    'json': {
    'name': 'Grace Evans',
    'address': '1966 Lewis Stream Suite 373\nMorrisside, AS 71141',
},
    'key32407': 'value93078',
    'key87741': 'value54880',
    'key98069': 'value84456',
    'key41851': 'value44383',
    'key23759': 'value14812',
    'key13563': 'value99906',
    'key28083': 'value26468',
    'key81501': 'value29229',
    'key79241': 'value43850',
    'key20633': 'value20183',
},
    {
    'id': 17527487844680,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kayla Cortez',
    'address': '05270 Mark Creek\nNorth Manuelhaven, NH 38996',
    'text': 'Weight range at. Network walk own determine positive everyone medical. Civil rate color recognize.\nKeep Republican trouble eye entire economy main never.\nKid laugh quite.',
    'email': 'craigkelley@example.net',
    'phone_number': '(677)794-5756x80271',
    'json': {
    'name': 'Christina Taylor',
    'address': '1571 Phillips Extensions\nNew Emilyville, KY 13610',
},
    'key89893': 'value77891',
    'key8318': 'value13127',
    'key67972': 'value57183',
    'key36156': 'value37735',
    'key1925': 'value35334',
    'key27208': 'value48774',
    'key13891': 'value48010',
    'key67618': 'value86127',
},
    {
    'id': 17527487844691,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Tammy Potter',
    'address': '9973 Contreras Dale Suite 246\nJamiemouth, SC 06213',
    'text': 'Pattern senior sense situation course especially. Seem drop public water central resource.',
    'email': 'vincent37@example.org',
    'phone_number': '(208)812-6811',
    'json': {
    'name': 'Christie Hall',
    'address': '531 Jonathon Shoals Apt. 432\nTorresstad, FM 80895',
},
    'key39122': 'value27123',
},
    {
    'id': 17527487844702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Gerald Marshall',
    'address': '9950 Taylor Parks\nWrightmouth, KY 16405',
    'text': 'Like boy us produce best. Commercial role account break me myself. Table safe natural always if close position.',
    'email': 'wilkinsdana@example.org',
    'phone_number': '001-470-665-1441x4390',
    'json': {
    'name': 'Andrea King',
    'address': '5835 Barnes Stravenue\nNew Anthonyberg, NC 46333',
},
    'key18222': 'value64530',
    'key16879': 'value35242',
    'key30562': 'value8622',
    'key28445': 'value77302',
    'key2533': 'value58453',
    'key63213': 'value68051',
    'key83311': 'value37362',
    'key54510': 'value18065',
},
    {
    'id': 17527487844714,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Walter Lopez',
    'address': '9931 Judy Ridge Suite 216\nMontgomerymouth, ME 42322',
    'text': 'Southern agent exist study. Former happen let loss. Pattern perform reflect wrong network wonder. Task other letter avoid both simply door church.',
    'email': 'fparks@example.org',
    'phone_number': '+1-803-571-1786x9458',
    'json': {
    'name': 'Dr. Timothy Lawrence Jr.',
    'address': '21763 Johnson Plaza\nEast Michael, NC 99437',
},
    'key68714': 'value74318',
    'key13229': 'value760',
    'key44290': 'value48609',
},
    {
    'id': 17527487844725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Jeremy Pratt',
    'address': '380 Mark Valley\nLake Melissatown, NE 27483',
    'text': 'Unit less tree. Black require billion now quality certainly teach. Event whole energy performance data yeah during hotel.\nMission check force sure alone here plan best.',
    'email': 'courtneybrown@example.com',
    'phone_number': '+1-746-575-6571x085',
    'json': {
    'name': 'Jordan King',
    'address': '85308 Kelli Divide\nNorth Kathyfort, NH 55438',
},
    'key45058': 'value74160',
    'key59719': 'value91738',
    'key20073': 'value41431',
    'key36274': 'value18205',
    'key77195': 'value4280',
    'key28912': 'value68860',
    'key66978': 'value68667',
    'key27666': 'value34088',
    'key8754': 'value80466',
},
    {
    'id': 17527487844736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Aimee Mcneil',
    'address': '3365 Webb Shoal Suite 400\nWest Brian, MI 06598',
    'text': 'Issue share admit manager blood. Culture use ever reduce.\nTraining issue worker standard born performance capital. Fine long price want size health land.',
    'email': 'laura57@example.org',
    'phone_number': '210-230-2581x8102',
    'json': {
    'name': 'Daniel Gonzalez',
    'address': '1601 Wheeler Hills Apt. 530\nValerieshire, GU 68150',
},
    'key84471': 'value55040',
    'key79123': 'value95497',
},
    {
    'id': 17527487844747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Laurie Stark',
    'address': '4336 Christine Loaf Suite 365\nWest Kelly, FL 99365',
    'text': 'Vote smile civil rise market.\nConsider add go probably window teacher. Man officer above term about.\nTelevision yeah various thought majority. Perhaps every mention.',
    'email': 'annesanchez@example.net',
    'phone_number': '795.541.2671x534',
    'json': {
    'name': 'Courtney Daniels',
    'address': '8790 Kathleen Manor\nNew Jose, NC 04987',
},
    'key27590': 'value6614',
},
    {
    'id': 17527487844759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Michael Pruitt',
    'address': '657 Tracy Village Apt. 324\nNew Ricardoborough, WY 92860',
    'text': 'Current college during ahead whole.\nGarden training easy the. Fish customer stop. Exist majority million current send join benefit.',
    'email': 'thomasmatthew@example.com',
    'phone_number': '001-830-954-9279x2670',
    'json': {
    'name': 'Dennis Gomez',
    'address': '787 Stephanie Dam\nEast Kathleenville, NE 65840',
},
    'key39873': 'value50338',
    'key40634': 'value99782',
    'key39077': 'value48449',
    'key65436': 'value99070',
    'key71210': 'value99206',
    'key62809': 'value51682',
},
    {
    'id': 17527487844770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Lisa Kelly',
    'address': '839 Wilson Ridges Apt. 689\nKeithchester, WA 71714',
    'text': 'Staff answer traditional wait. National majority save next.\nEither fish popular wonder. Occur under himself employee store dream.\nMethod north detail care. Why four dog letter Republican.',
    'email': 'chloehughes@example.com',
    'phone_number': '623.866.8129x1672',
    'json': {
    'name': 'Brad Cantrell',
    'address': '7858 Tyler Roads\nLake Sandra, PA 34735',
},
    'key11291': 'value85399',
},
    {
    'id': 17527487844781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Marissa Ellis',
    'address': '321 Grant Creek Suite 173\nMicheleburgh, MA 13434',
    'text': 'Very focus today next. Bank will meet away.\nCampaign perhaps mission hot. Build any short forward be might plant. Suffer customer morning total standard participant.',
    'email': 'karenjohnson@example.net',
    'phone_number': '(345)971-1108',
    'json': {
    'name': 'Anna Ross',
    'address': '85925 Vanessa Common Suite 422\nKennethhaven, NM 59641',
},
    'key22608': 'value67084',
    'key46995': 'value67373',
    'key67691': 'value11059',
},
    {
    'id': 17527487844793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Jennifer Smith',
    'address': '30129 Gonzalez Camp\nAndradefort, NC 73131',
    'text': 'Reason meet ago drop explain. Black section fund morning lot. Trouble with bank her teach tell degree.',
    'email': 'djohnson@example.com',
    'phone_number': '450-582-9712x62226',
    'json': {
    'name': 'Robert Davidson',
    'address': '9791 Calvin Terrace Suite 221\nNew Ronaldchester, LA 68795',
},
    'key81210': 'value57771',
    'key51177': 'value87171',
    'key43943': 'value89645',
    'key49565': 'value46213',
    'key23711': 'value10220',
    'key31852': 'value62952',
    'key20601': 'value23602',
    'key68097': 'value72963',
},
    {
    'id': 17527487844805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Charles Kemp',
    'address': '093 Gabriel Road Suite 846\nJacobport, MH 01376',
    'text': 'Or deep while during body cut. Else situation determine unit possible parent down. Style art final involve.\nPainting region run interest. Idea picture ago.',
    'email': 'goldenchristopher@example.org',
    'phone_number': '+1-530-850-4278x86912',
    'json': {
    'name': 'Jessica Lee',
    'address': '940 Nelson Orchard Apt. 854\nTrujillotown, WV 36124',
},
    'key7576': 'value61490',
    'key46549': 'value30235',
    'key31755': 'value36618',
    'key67713': 'value86723',
    'key92499': 'value36150',
    'key82162': 'value7703',
},
    {
    'id': 17527487844817,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Miguel Lewis',
    'address': 'Unit 9135 Box 5217\nDPO AE 66248',
    'text': 'She politics your doctor safe any full. Agreement meet mouth alone administration talk.\nComputer federal decade across. Mr article cover lay address. Deal assume less happen across stock.',
    'email': 'pramos@example.org',
    'phone_number': '613-622-3514x782',
    'json': {
    'name': 'Timothy Young',
    'address': '64653 Trevor Haven\nJustinshire, VA 08611',
},
    'key96789': 'value56852',
    'key86322': 'value68189',
},
    {
    'id': 17527487844827,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Rhonda Bryant',
    'address': '44063 Gray Parkways\nJenniferville, TX 33841',
    'text': 'Watch defense much blood age election staff in. Magazine lawyer letter participant industry happen resource.',
    'email': 'pbaker@example.com',
    'phone_number': '918-358-5384x188',
    'json': {
    'name': 'James Klein',
    'address': '340 Walker Bypass\nCourtneymouth, ME 90783',
},
    'key35072': 'value88473',
    'key35083': 'value63125',
    'key67778': 'value890',
    'key32579': 'value82541',
    'key4157': 'value77299',
    'key92086': 'value944',
    'key22955': 'value61489',
    'key1038': 'value11238',
    'key20952': 'value5596',
    'key80150': 'value60826',
},
    {
    'id': 17527487844839,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Jeremy Simmons',
    'address': 'Unit 1547 Box 6373\nDPO AA 29708',
    'text': 'Different fall arrive area poor program. Day because watch whose.\nHeart plan chair expect.\nPoor often daughter note. Impact wish establish black make.',
    'email': 'michelesellers@example.net',
    'phone_number': '(656)567-9464x463',
    'json': {
    'name': 'Andrew Walls',
    'address': '199 Alvin Village Apt. 684\nStricklandburgh, MH 33026',
},
    'key94159': 'value27066',
    'key96825': 'value13666',
    'key22572': 'value58654',
    'key27441': 'value73588',
},
    {
    'id': 17527487844849,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Timothy Chen',
    'address': '882 Jonathan Ford\nDevonmouth, MT 92472',
    'text': 'Loss magazine fight. Occur dinner occur start picture everything. Expect treatment lay quality where in put.',
    'email': 'torresandrew@example.org',
    'phone_number': '(787)940-8214',
    'json': {
    'name': 'Mr. Stephen Robles',
    'address': '574 Tyler Hollow\nNorth Heather, KY 43363',
},
    'key2666': 'value78929',
    'key12761': 'value49642',
    'key61031': 'value48372',
    'key5394': 'value30058',
    'key36883': 'value59408',
    'key25399': 'value57755',
    'key21388': 'value25617',
    'key50564': 'value69150',
    'key6011': 'value56908',
    'key72714': 'value91652',
},
    {
    'id': 17527487844861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Nathan Anderson',
    'address': '5539 Bailey Square Apt. 312\nNorth Elizabethburgh, MS 26479',
    'text': 'Treatment law account because. Yeah meeting conference remain. Explain woman sure sing within give hope travel.',
    'email': 'kkim@example.net',
    'phone_number': '+1-240-621-7412x9804',
    'json': {
    'name': 'William Ruiz',
    'address': '2732 Jesse Divide\nJosephhaven, NM 02423',
},
    'key91966': 'value52352',
    'key40142': 'value44653',
    'key6206': 'value95567',
    'key6952': 'value46821',
    'key24519': 'value89856',
},
    {
    'id': 17527487844873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'James Johnson',
    'address': '6484 Jennifer River\nJennifershire, RI 65713',
    'text': 'Source son interest car once. Range something teach you defense interview born.\nOwner a Democrat. Study fund end idea information. Quality true start there.',
    'email': 'sharonnelson@example.org',
    'phone_number': '(457)233-0099x3086',
    'json': {
    'name': 'Steve Mitchell',
    'address': '6874 Clayton Trace\nLopezbury, CT 50660',
},
    'key59150': 'value54318',
    'key82514': 'value10166',
    'key52858': 'value89133',
    'key81684': 'value80476',
    'key37082': 'value72735',
    'key76345': 'value98915',
    'key75000': 'value37161',
},
    {
    'id': 17527487844886,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mrs. Mary Brown',
    'address': '6607 Rodriguez Inlet\nShawnton, NM 79868',
    'text': 'Never him situation necessary hope able. Final environmental return. Choice stuff food enough.\nStar seven true point pull if treatment.',
    'email': 'lynn27@example.org',
    'phone_number': '001-421-380-9877x8488',
    'json': {
    'name': 'Anthony Miller',
    'address': '6882 Jennings Highway\nRiosland, CT 56658',
},
    'key95198': 'value32930',
    'key65328': 'value62177',
    'key84442': 'value97953',
    'key93835': 'value60399',
    'key1008': 'value87949',
    'key21965': 'value54267',
},
    {
    'id': 17527487844900,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Sarah Hood',
    'address': '5914 Stephen Row Suite 409\nDuncantown, ID 05336',
    'text': 'Near able sometimes yet lot who. Miss simple four executive go budget. Technology hot toward white themselves after consumer leg.\nOfficial few reduce trial.',
    'email': 'jhart@example.com',
    'phone_number': '+1-403-669-2919x355',
    'json': {
    'name': 'Lance Dunn',
    'address': '9369 Jacob Trafficway Suite 717\nMitchellstad, WV 28064',
},
    'key90674': 'value6450',
    'key14206': 'value82066',
    'key1551': 'value84979',
    'key83818': 'value98726',
    'key71377': 'value8663',
    'key95861': 'value4029',
},
    {
    'id': 17527487844912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Alison Nash',
    'address': '7946 Michelle Estate\nSouth Hannah, OH 12079',
    'text': 'Store today edge my industry. Your two address opportunity. Red country parent do plant speech.',
    'email': 'melindaharrison@example.net',
    'phone_number': '299.864.2125',
    'json': {
    'name': 'Alexis Davidson',
    'address': '28746 Davis Ways Apt. 179\nNorth Mercedes, CO 75253',
},
    'key22970': 'value39989',
    'key52914': 'value73438',
    'key85147': 'value58109',
    'key59163': 'value61323',
    'key58723': 'value83405',
    'key55194': 'value67853',
},
    {
    'id': 17527487844923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Joseph Parsons',
    'address': '34197 Natasha View\nLake Daniel, IA 50993',
    'text': 'Along reality it imagine make her right. Growth economy tell bed pay radio eye.\nSituation mind over nation far. Always near if nature picture.',
    'email': 'martingarrett@example.org',
    'phone_number': '903-451-5252x57703',
    'json': {
    'name': 'Ms. Christina Evans',
    'address': '5371 Jennifer Cliffs\nGarretttown, NM 92936',
},
    'key50878': 'value9861',
    'key53998': 'value37370',
    'key23044': 'value23416',
},
    {
    'id': 17527487844933,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Kenneth Richards',
    'address': '85819 Dana Place\nLake Robert, PW 42564',
    'text': 'Consumer everybody table town lose respond involve. Coach their religious day throughout. Place may reveal away start when everybody.\nPlant Mr radio how avoid. Huge pass head around.',
    'email': 'davidwilliams@example.net',
    'phone_number': '001-455-667-3525x20534',
    'json': {
    'name': 'Kristi Miller',
    'address': '56336 Williams Vista\nMcconnellside, NH 11831',
},
    'key4631': 'value81425',
    'key10826': 'value4866',
},
    {
    'id': 17527487844946,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Hector Nguyen',
    'address': '138 Beverly Roads Suite 827\nMccarthyville, NJ 41024',
    'text': 'Inside know officer change discussion. Yes among plant perhaps contain wear.\nCongress professional near threat no apply. Quality move new experience usually. Bed prove often.',
    'email': 'vayers@example.net',
    'phone_number': '466-341-6387',
    'json': {
    'name': 'Kristen Reese',
    'address': 'USCGC Walton\nFPO AE 56967',
},
    'key10197': 'value55104',
    'key32802': 'value16917',
    'key82210': 'value56847',
},
    {
    'id': 17527487844956,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Heather Jones',
    'address': '538 Barry Harbor Apt. 023\nEast Toddstad, PA 60332',
    'text': 'Make eight design truth something. Traditional them cold responsibility become PM.',
    'email': 'nathanwhite@example.org',
    'phone_number': '252.427.1313',
    'json': {
    'name': 'John Wood',
    'address': '8823 Samantha Crescent Apt. 753\nMeganton, WV 79289',
},
    'key36806': 'value5976',
    'key90623': 'value8290',
    'key490': 'value56946',
    'key67281': 'value72366',
    'key59496': 'value37555',
    'key3386': 'value64839',
    'key75747': 'value53963',
    'key58963': 'value27386',
    'key70433': 'value23241',
},
    {
    'id': 17527487844968,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Joseph Turner',
    'address': '50045 West Flat Apt. 638\nNew Patrickton, AS 13483',
    'text': 'Individual them draw thought trade along attorney. Strategy arrive hot test member town present. Southern let floor gun.\nAsk I job vote indeed until lose. Field behavior watch wife.',
    'email': 'stephensmith@example.com',
    'phone_number': '(453)808-8353',
    'json': {
    'name': 'Laura Davis',
    'address': '032 Joseph Camp\nSmithmouth, IN 63348',
},
    'key77427': 'value16746',
    'key33206': 'value38375',
    'key51975': 'value70652',
},
    {
    'id': 17527487844981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Melissa Harmon',
    'address': '42168 Barnes Burg Suite 875\nRobertsonstad, NM 22557',
    'text': 'Century note way time student color. Require new represent win cover brother.\nPart rock conference. Laugh including black whose agreement. Home rich kind movement.',
    'email': 'yswanson@example.org',
    'phone_number': '415.454.6420',
    'json': {
    'name': 'Paul Weaver',
    'address': 'Unit 3082 Box 1234\nDPO AP 09072',
},
    'key22035': 'value90813',
    'key54590': 'value58707',
    'key93591': 'value32658',
    'key47513': 'value25895',
    'key18226': 'value37444',
    'key81805': 'value69447',
},
    {
    'id': 17527487844991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Eric Juarez',
    'address': '543 Sara Gateway\nEast Laurenborough, NE 79243',
    'text': 'Member drop school young world beautiful address computer. Respond move whether see article win source.',
    'email': 'paulagray@example.org',
    'phone_number': '(231)436-0287x92559',
    'json': {
    'name': 'Trevor Miller',
    'address': '998 Brittany Hill Suite 149\nLake Christopher, NE 36191',
},
    'key57632': 'value10000',
},
    {
    'id': 17527487845002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jessica Stewart',
    'address': '8825 Rachel Court Suite 725\nEast Christopherburgh, DC 57773',
    'text': 'Group production value. Use want pressure fly.\nDescribe stand never his ten just night include.\nFace choice article second hard trip man. Ask leave child.',
    'email': 'laurencollins@example.com',
    'phone_number': '+1-217-651-7194x272',
    'json': {
    'name': 'Deborah Harris PhD',
    'address': '2175 Kevin Fork Suite 722\nMarilynchester, AK 95287',
},
    'key39095': 'value12161',
    'key35790': 'value61210',
    'key99123': 'value44750',
    'key75875': 'value59017',
    'key32723': 'value39088',
    'key47525': 'value32854',
    'key55272': 'value15603',
    'key52585': 'value50420',
},
    {
    'id': 17527487845014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Melissa Howard',
    'address': 'USCGC Doyle\nFPO AA 55835',
    'text': 'Employee movie money message economic past car. Fund red win keep it happen.\nBuild clear kind few himself worker others improve. Power color level them media safe. Man class citizen clearly.',
    'email': 'rossleslie@example.org',
    'phone_number': '345.821.5901x896',
    'json': {
    'name': 'Victoria Hawkins',
    'address': '1397 Villa Turnpike\nNew Benjaminfurt, OK 72552',
},
    'key88660': 'value22260',
    'key97521': 'value62258',
},
    {
    'id': 17527487845025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Emily Mathis',
    'address': '577 Roger Flat\nNew Diane, VI 70150',
    'text': 'Guess read southern action receive make question another.\nMatter enter Mrs reflect.',
    'email': 'whobbs@example.com',
    'phone_number': '297.478.9112x8243',
    'json': {
    'name': 'Kevin Gaines',
    'address': '364 Timothy Drives\nWest Jack, TX 28611',
},
    'key26601': 'value90634',
},
    {
    'id': 17527487845036,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Brandy Taylor',
    'address': '7223 Rangel Route Apt. 704\nEast Tiffany, NJ 50766',
    'text': 'Leader game show left within part. Pay however factor arm daughter. Check far data teach any order.\nThousand lay property. Paper section less.',
    'email': 'tommy60@example.org',
    'phone_number': '826-891-8178x68975',
    'json': {
    'name': 'Alison Mercado',
    'address': '706 Michelle Meadow Suite 147\nMichaelstad, AS 12523',
},
    'key63008': 'value21977',
    'key3696': 'value59570',
    'key80850': 'value2290',
    'key39896': 'value38757',
    'key35575': 'value23178',
    'key79543': 'value59387',
},
    {
    'id': 17527487845047,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Katherine Jones',
    'address': '8277 Jonathan Circles Apt. 656\nLake Joyce, CA 20964',
    'text': 'Industry far fear television including manager face or. Art bit herself forget sing step.',
    'email': 'jeffrey42@example.net',
    'phone_number': '598.594.8692x579',
    'json': {
    'name': 'James Hawkins',
    'address': '9191 Cassie Groves\nNew Johnshire, NJ 83746',
},
    'key95939': 'value80467',
    'key98208': 'value13112',
    'key57141': 'value89766',
    'key90031': 'value98752',
    'key12278': 'value27057',
    'key91080': 'value20488',
},
    {
    'id': 17527487845057,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Courtney Brandt',
    'address': '97343 Hunt Plains Suite 485\nLake Hayley, AZ 70672',
    'text': 'Worry stuff show stay. Property letter finish understand. Help also agent success task. Issue occur exactly Mrs those.',
    'email': 'jeffreyross@example.net',
    'phone_number': '588.333.4362x77173',
    'json': {
    'name': 'Kimberly Boyd',
    'address': '091 Mark Shores\nEast Paul, HI 85652',
},
    'key50209': 'value11701',
    'key31223': 'value49378',
    'key93041': 'value36709',
    'key65247': 'value97669',
    'key40145': 'value12502',
    'key2362': 'value29384',
    'key54988': 'value81257',
    'key7102': 'value97445',
    'key24427': 'value92243',
},
    {
    'id': 17527487845069,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Brian Porter',
    'address': '338 Jose Drives\nSouth Elizabeth, SD 25954',
    'text': 'Hand baby run last relate morning. Behavior machine especially onto final stop onto.',
    'email': 'baxterrichard@example.org',
    'phone_number': '6335711857',
    'json': {
    'name': 'Pamela Vaughn',
    'address': '4257 John Rapid Apt. 547\nJoseland, AK 28405',
},
    'key60459': 'value52154',
},
    {
    'id': 17527487845080,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Shannon Cervantes',
    'address': '23559 Fuller Light Apt. 268\nWest Tamara, AS 72552',
    'text': 'Their bank democratic blood. Decade test operation hundred represent west management successful. Article difficult process may body seven.\nRelationship machine minute. News deep present response.',
    'email': 'kmurray@example.org',
    'phone_number': '636-507-7628x266',
    'json': {
    'name': 'Kyle Clark',
    'address': '6432 Nicole Points\nJeffreyfurt, OH 16425',
},
    'key18647': 'value32746',
    'key22610': 'value31856',
    'key56348': 'value2076',
    'key83419': 'value85047',
    'key17350': 'value99851',
    'key57391': 'value80838',
    'key29280': 'value33570',
},
    {
    'id': 17527487845091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Sandra Elliott',
    'address': '1426 Ortega Ways\nPort Robertburgh, AK 02412',
    'text': 'Watch cover feel organization see put law. Century coach source remain energy. Network include man face voice.',
    'email': 'marcusmeyer@example.com',
    'phone_number': '(666)960-6447x1051',
    'json': {
    'name': 'Ruth Henderson',
    'address': '939 Cassidy Road\nSouth Elizabethfort, LA 15254',
},
    'key98247': 'value23956',
    'key45996': 'value98321',
    'key61057': 'value73656',
    'key11896': 'value71031',
    'key61974': 'value39304',
    'key85952': 'value4885',
    'key62514': 'value21232',
    'key90869': 'value49582',
},
    {
    'id': 17527487845102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Christian Lopez',
    'address': 'Unit 1597 Box 5839\nDPO AP 00796',
    'text': 'Positive truth together Democrat. Military occur single feeling although clear.\nUsually medical structure. He easy establish health feel six able. Fast near there poor.',
    'email': 'stewarttroy@example.org',
    'phone_number': '610.366.2056x198',
    'json': {
    'name': 'Hannah Bailey',
    'address': '446 Cynthia Islands Suite 157\nLake David, AR 97374',
},
    'key25232': 'value51345',
    'key4410': 'value86653',
    'key81611': 'value41041',
    'key25445': 'value63247',
    'key60484': 'value97152',
    'key61110': 'value33064',
    'key16335': 'value21461',
},
    {
    'id': 17527487845112,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Janet Santiago',
    'address': '5960 Bryan Mission\nCynthiabury, NE 29486',
    'text': 'Window see finally speak soon. Condition nature ready fly century put.\nMessage ever without address society box. Decade thank water. Movement safe buy involve begin give.\nAnything fight debate star.',
    'email': 'taylorlindsay@example.net',
    'phone_number': '(471)535-7555',
    'json': {
    'name': 'Elizabeth Booth',
    'address': 'Unit 9072 Box 2282\nDPO AP 10895',
},
    'key52454': 'value9428',
    'key98621': 'value54056',
    'key25189': 'value75965',
    'key70987': 'value96187',
    'key94726': 'value22724',
    'key49823': 'value64328',
},
    {
    'id': 17527487845121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Cameron Guzman',
    'address': 'PSC 8213, Box 2431\nAPO AA 07796',
    'text': 'Tax organization west material produce. Imagine finish church anything project operation church short. Though civil guy about.',
    'email': 'tmassey@example.com',
    'phone_number': '716.663.2284x529',
    'json': {
    'name': 'Christina Garrison',
    'address': '2260 Cohen Ports\nJacksonton, FM 22769',
},
    'key13949': 'value66538',
    'key5339': 'value93318',
    'key58413': 'value18897',
    'key3524': 'value1134',
    'key92655': 'value50705',
    'key88647': 'value74566',
},
    {
    'id': 17527487845130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Anthony Young',
    'address': '489 Laura Parkways Apt. 757\nBrownview, KY 14563',
    'text': 'Woman what nearly better eat. Interview somebody feeling affect today. Democrat system dog human such pay know.\nMouth east structure even lose development. Foreign politics line simply.',
    'email': 'vasquezkathryn@example.com',
    'phone_number': '485.337.3755x8308',
    'json': {
    'name': 'Bryan Lopez',
    'address': '3908 Dorothy Valleys\nChristophermouth, ME 09905',
},
    'key36935': 'value26745',
    'key43858': 'value53793',
    'key67216': 'value68769',
    'key13229': 'value56071',
    'key91198': 'value66517',
},
    {
    'id': 17527487845141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jennifer Galvan',
    'address': '94176 David Route Apt. 889\nWest Yvonne, AS 08064',
    'text': 'Sell physical reality area. End name woman service who save TV still.',
    'email': 'randolphjohn@example.org',
    'phone_number': '+1-890-336-7589x6040',
    'json': {
    'name': 'Elizabeth Johnson',
    'address': '0249 Karen Crossing\nOrozcotown, NE 48618',
},
    'key1251': 'value89852',
    'key42835': 'value93913',
    'key43020': 'value53149',
    'key30157': 'value3710',
    'key30568': 'value16667',
    'key15502': 'value94002',
    'key59304': 'value56544',
},
    {
    'id': 17527487845153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Cynthia Holland',
    'address': '687 Allen Flat Apt. 396\nWandamouth, WI 75550',
    'text': 'Support draw point key production heavy Republican. Imagine by firm form anything result series. Event test dinner term message become any blood.',
    'email': 'gbailey@example.com',
    'phone_number': '933-620-7443',
    'json': {
    'name': 'Douglas Davidson',
    'address': '77896 Young Centers Suite 882\nWrightfurt, OK 48977',
},
    'key77239': 'value95037',
    'key17143': 'value76085',
    'key91704': 'value21994',
    'key33521': 'value65853',
    'key63166': 'value85369',
},
    {
    'id': 17527487845164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Laura Williams',
    'address': 'PSC 3700, Box 6454\nAPO AE 37824',
    'text': 'No what box. Perform question by argue rule once break. Difference try sport evidence argue team. Tell number leave western response resource.',
    'email': 'kimberly88@example.org',
    'phone_number': '790-387-6476x30188',
    'json': {
    'name': 'Brandon Vance',
    'address': '9905 Williams Lake\nJohnchester, GU 42726',
},
    'key28919': 'value7526',
    'key57236': 'value40099',
    'key98668': 'value61493',
    'key71968': 'value78953',
    'key80472': 'value30046',
    'key31010': 'value90885',
    'key9412': 'value37768',
    'key91148': 'value57027',
    'key59363': 'value86036',
},
    {
    'id': 17527487845173,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Cindy Adams',
    'address': '913 Ellen Glens\nDanielshire, TX 91421',
    'text': 'Doctor board need true successful hotel catch.\nThem different field leader push floor particularly especially. Music travel require fine. Perhaps itself decade right. Term world she be always.',
    'email': 'asmith@example.org',
    'phone_number': '379-703-0634x88520',
    'json': {
    'name': 'Shane Davis',
    'address': '0239 Simpson Green\nPort Peterfurt, OR 78059',
},
    'key64222': 'value50990',
    'key33369': 'value49412',
    'key82055': 'value20158',
    'key3335': 'value85268',
    'key8584': 'value78440',
},
    {
    'id': 17527487845183,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jill Santana',
    'address': '5318 Gabriel Crescent Suite 327\nGrossfort, NJ 31881',
    'text': 'Treat hair marriage main. Deep truth specific represent. Tough view possible color learn worker.',
    'email': 'angelajones@example.net',
    'phone_number': '(624)896-2161x111',
    'json': {
    'name': 'Jack Pacheco',
    'address': '374 Morton Turnpike\nMitchellville, MH 11522',
},
    'key25112': 'value27493',
    'key75952': 'value33614',
    'key44678': 'value27802',
    'key68268': 'value89053',
    'key45749': 'value43681',
    'key22098': 'value60914',
    'key21275': 'value80299',
    'key24037': 'value47920',
    'key85054': 'value17094',
    'key66684': 'value37590',
},
    {
    'id': 17527487845195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Miss Samantha Allen MD',
    'address': '77241 Martinez Lock Suite 834\nJamesmouth, UT 24292',
    'text': 'Though parent big single official of expert deal. Cold speech trial power exactly.',
    'email': 'walshjoseph@example.com',
    'phone_number': '+1-787-662-7083x022',
    'json': {
    'name': 'Sean Reyes',
    'address': '7062 Gregory Flats Suite 392\nLoriport, MT 95454',
},
    'key93311': 'value7750',
    'key60884': 'value41372',
    'key70775': 'value37793',
    'key57134': 'value18277',
    'key70990': 'value28651',
    'key5293': 'value99439',
    'key82320': 'value35593',
},
    {
    'id': 17527487845207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Rachel Woods',
    'address': '8254 Bob Rue Apt. 370\nNelsonmouth, PW 07714',
    'text': 'Sound decision final million deal page to rather. Marriage amount bag own everybody government society.',
    'email': 'brian73@example.net',
    'phone_number': '9148427337',
    'json': {
    'name': 'Ashley Pineda',
    'address': 'PSC 2911, Box 3810\nAPO AA 21863',
},
    'key73509': 'value5994',
    'key65096': 'value30302',
},
    {
    'id': 17527487845215,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Bonnie Hill',
    'address': '04565 Johnson Brooks\nAmberchester, SC 19336',
    'text': 'Day grow evidence clear property budget. Return notice sort speak notice. Scientist door important improve.\nRich fast paper marriage fast.',
    'email': 'ichavez@example.net',
    'phone_number': '(227)329-6018',
    'json': {
    'name': 'Derek Richard',
    'address': '0106 Wilson Squares\nMuellerbury, ME 51846',
},
    'key14545': 'value23727',
    'key60020': 'value29749',
    'key92952': 'value15348',
    'key44861': 'value68292',
    'key93440': 'value45868',
    'key26448': 'value64048',
},
    {
    'id': 17527487845226,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Cynthia Wells',
    'address': '16478 Johnson Gateway Suite 210\nLewisville, WY 94227',
    'text': 'Enough claim but defense suddenly. Bag discuss country necessary knowledge cost phone middle. Beat ok view brother really.',
    'email': 'ericajohnson@example.org',
    'phone_number': '690.377.4558x2188',
    'json': {
    'name': 'Teresa Cummings',
    'address': 'Unit 9840 Box 0533\nDPO AA 27991',
},
    'key32850': 'value94635',
    'key4949': 'value8646',
    'key30903': 'value19389',
},
    {
    'id': 17527487845236,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Tyler Berry',
    'address': '65556 Thomas River\nWest Lindsay, CA 18053',
    'text': 'Thus Congress or enjoy. Least customer just measure fast nature.\nNature student language pull ok. Board hard above hit deal from result. Poor I lot should model have career.',
    'email': 'maciastara@example.net',
    'phone_number': '407-394-0240',
    'json': {
    'name': 'Jorge Williams',
    'address': '89162 Brian Via\nSnyderland, OK 18976',
},
    'key93646': 'value98879',
    'key90983': 'value25194',
    'key8736': 'value76790',
    'key38578': 'value6227',
    'key64778': 'value74859',
    'key85459': 'value41434',
    'key52899': 'value93417',
    'key12423': 'value96673',
    'key39238': 'value84744',
},
    {
    'id': 17527487845246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Christopher Cardenas',
    'address': '584 Alexandra Junction\nNew Duaneland, DC 50133',
    'text': 'Within free ever relate he leave reduce.\nLeg which those. Choose number watch with source better money expect.',
    'email': 'stephanie33@example.com',
    'phone_number': '581-861-9101',
    'json': {
    'name': 'Jill Norman',
    'address': '77997 Boyd Common Suite 987\nLake Lesliefurt, TX 07584',
},
    'key15469': 'value75097',
    'key51275': 'value59096',
    'key86002': 'value8042',
    'key3879': 'value63133',
    'key87291': 'value60037',
    'key17011': 'value69542',
    'key2625': 'value39976',
},
    {
    'id': 17527487845257,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Daniel Mahoney',
    'address': '424 Clark Drive Apt. 463\nRandyborough, MP 65332',
    'text': 'Boy American kitchen natural.\nAble smile building according control court here. Something nothing Mrs sit. Drug election born recently.',
    'email': 'caseydean@example.org',
    'phone_number': '710.784.7765',
    'json': {
    'name': 'Rebecca Harris',
    'address': '42939 Shepherd Row\nWest Lindsay, VT 99792',
},
    'key31698': 'value91550',
    'key38732': 'value14684',
    'key65919': 'value90079',
    'key10001': 'value61680',
    'key18865': 'value34582',
    'key40409': 'value81736',
},
    {
    'id': 17527487845268,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Nicole Jones',
    'address': '38268 Cox Wall\nHallstad, TN 20967',
    'text': 'Receive myself unit her view stage. Yet wall building agency true young fly. Yet treat garden this soon culture why.',
    'email': 'debranguyen@example.com',
    'phone_number': '534-711-8599',
    'json': {
    'name': 'Dale Barrera',
    'address': '640 Thomas Brook Suite 223\nLake Alyssaberg, NY 90186',
},
    'key65986': 'value24186',
    'key95303': 'value60112',
    'key19723': 'value80492',
    'key25478': 'value72111',
    'key22958': 'value17641',
    'key27352': 'value21321',
},
    {
    'id': 17527487845280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Cynthia Wagner',
    'address': '843 Norris Stream\nMoniqueport, AR 47246',
    'text': 'Thousand court view leave own like politics mention. Change order purpose office good through accept. Company great citizen house red wear truth.',
    'email': 'ygonzalez@example.org',
    'phone_number': '618.756.7545',
    'json': {
    'name': 'Benjamin Moreno',
    'address': '395 Flores Street\nEast Jennifer, PW 77826',
},
    'key38387': 'value20697',
    'key29739': 'value13088',
    'key90645': 'value31043',
    'key8511': 'value68927',
},
    {
    'id': 17527487845291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Thomas Wilson',
    'address': '391 Moore Courts\nWayneborough, MS 73473',
    'text': 'See cause participant let. Experience why make and.\nExpect record or air physical rich. Wrong treatment event affect better. Through piece use administration away wait agency.',
    'email': 'kristenellison@example.net',
    'phone_number': '(788)525-9717',
    'json': {
    'name': 'Mrs. Jade Jefferson',
    'address': '85712 Ford Groves\nKristinville, NE 86610',
},
    'key12073': 'value73743',
    'key60420': 'value33137',
    'key98861': 'value45263',
},
    {
    'id': 17527487845303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jessica Bailey',
    'address': '42308 Hill Gateway Apt. 949\nGarrettshire, OH 86991',
    'text': 'Argue return to. Care practice my fill add.',
    'email': 'patrickkeith@example.com',
    'phone_number': '964-734-6670x866',
    'json': {
    'name': 'Robert Lane',
    'address': '3935 Jessica Crossing\nNorth Kathy, AZ 51507',
},
    'key57839': 'value85908',
    'key83170': 'value94896',
    'key11346': 'value42404',
    'key62918': 'value88332',
    'key63861': 'value47724',
    'key83907': 'value4346',
    'key90921': 'value11053',
    'key60784': 'value18465',
    'key30202': 'value97553',
    'key92511': 'value55342',
},
    {
    'id': 17527487845314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Michael Jackson',
    'address': '155 Bryan Tunnel\nPort Melissaport, MO 93609',
    'text': 'Culture west process dog security. Red current old how per. Or kitchen back song toward line organization coach.\nInformation nature old. Among yes relationship class these arm.',
    'email': 'joseph50@example.org',
    'phone_number': '+1-291-813-9564',
    'json': {
    'name': 'James Petty',
    'address': '755 Lynn Drive\nJamesfort, WA 99291',
},
    'key99283': 'value60869',
    'key15289': 'value425',
    'key96811': 'value77476',
    'key86508': 'value16142',
    'key23846': 'value48098',
    'key64390': 'value68134',
    'key20297': 'value8336',
},
    {
    'id': 17527487845324,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Miss Cynthia Sanchez DDS',
    'address': '333 Justin Manor Apt. 811\nPort James, AZ 79657',
    'text': 'Development leave amount significant final you. Eight church see money. Believe avoid campaign exist claim.',
    'email': 'olivia42@example.org',
    'phone_number': '001-491-529-9343',
    'json': {
    'name': 'Joshua Martinez',
    'address': '8339 James Plaza\nNorth Dustin, NC 23028',
},
    'key50085': 'value813',
    'key48729': 'value61534',
    'key87161': 'value84513',
    'key2028': 'value22105',
    'key15119': 'value2237',
    'key54315': 'value5051',
    'key74988': 'value24547',
    'key64776': 'value67628',
},
    {
    'id': 17527487845334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Dustin Morales',
    'address': 'PSC 9134, Box 2677\nAPO AP 32739',
    'text': 'World might small reality. Those eye us officer board nature.\nView why customer store assume chair continue.',
    'email': 'kristina24@example.com',
    'phone_number': '888-708-3210',
    'json': {
    'name': 'Mary Lopez',
    'address': '501 Dwayne Tunnel Suite 648\nSmithfurt, AL 59744',
},
    'key88266': 'value60031',
    'key9179': 'value65513',
    'key34141': 'value96382',
    'key37132': 'value54760',
    'key18658': 'value25551',
    'key34660': 'value4280',
    'key13536': 'value77712',
    'key3054': 'value49683',
    'key71205': 'value9591',
},
    {
    'id': 17527487845342,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Janice Thomas',
    'address': '813 Angela Plaza Suite 730\nNorth Denise, MA 85722',
    'text': 'Expect body actually stay deep. Try recently glass feel. Book foreign not threat network.\nUse explain play performance add. Performance they owner share.\nForm fish may.',
    'email': 'nancyperez@example.org',
    'phone_number': '+1-931-212-5507x332',
    'json': {
    'name': 'Rodney Wallace',
    'address': '583 Werner Parkways Suite 986\nJacksonmouth, MT 77236',
},
    'key59393': 'value2485',
    'key81517': 'value60775',
    'key85271': 'value6740',
    'key77833': 'value31209',
    'key43463': 'value8784',
    'key45965': 'value2690',
},
    {
    'id': 17527487845354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Laura Campbell',
    'address': '2159 Woods Camp Apt. 290\nEast Kristen, MH 31083',
    'text': 'Day series rock water never performance true. Third fact collection world write something bar. Lawyer follow wide piece.\nPresent idea address billion. Law color model first final those adult.',
    'email': 'christina38@example.net',
    'phone_number': '9447247621',
    'json': {
    'name': 'Whitney Williams',
    'address': 'Unit 4420 Box 5451\nDPO AE 66165',
},
    'key8960': 'value24827',
    'key31743': 'value52077',
    'key285': 'value65768',
    'key40929': 'value10602',
    'key77434': 'value79727',
    'key76741': 'value50433',
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
    'filter': 'uid in [1,2,3,4]',
    'limit': 100,
    'offset': 0,
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
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
    'RequestId': '56aa7bfc-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_38_388636vEKaVphP',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752748792.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUidIn12341752748792Json()
    test.run_tests()
