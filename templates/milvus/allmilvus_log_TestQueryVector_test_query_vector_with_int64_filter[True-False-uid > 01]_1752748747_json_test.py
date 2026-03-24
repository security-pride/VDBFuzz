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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 01]_1752748747_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 01]_1752748747.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid011752748747Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 01]_1752748747.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 01]_1752748747.json"
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
    'RequestId': '3c96e836-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_54_639409UXgxaMDZ',
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
    'RequestId': '3c96e836-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_54_639409UXgxaMDZ',
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
    'RequestId': '3c96e836-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_54_639409UXgxaMDZ',
    'data': [
    {
    'id': 17527487406731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Daniel Brown',
    'address': '2603 Kelsey Well\nGrantside, NE 65267',
    'text': 'Step stand son into agency. Bring address amount.\nPoint everyone think black writer economic instead. Standard imagine modern say.',
    'email': 'odonnelljustin@example.com',
    'phone_number': '778.654.8959',
    'json': {
    'name': 'Anne Bradford',
    'address': '9395 Robert Stream\nSteelestad, TX 43715',
},
    'key15564': 'value42724',
    'key91725': 'value87244',
    'key62491': 'value12461',
    'key84485': 'value74994',
    'key11637': 'value37385',
},
    {
    'id': 17527487406748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Melissa Rice',
    'address': '87710 Thomas Valleys Apt. 738\nWalkerborough, NE 44610',
    'text': 'Purpose point morning perform. Actually paper most prove teach pick. Write song happen seat particularly commercial.\nUnder film early director item game. Continue name station sure say.',
    'email': 'jessica37@example.org',
    'phone_number': '(627)336-0236x579',
    'json': {
    'name': 'Katherine Dalton',
    'address': 'Unit 3841 Box 7558\nDPO AE 46719',
},
    'key80064': 'value76254',
    'key71812': 'value67854',
    'key7703': 'value81072',
    'key78086': 'value438',
},
    {
    'id': 17527487406758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jeffrey Snyder',
    'address': '1337 Cook Stream Apt. 298\nSouth Kennethside, AK 18179',
    'text': 'Six send recent official moment century activity.\nEffect seek decide customer campaign consider watch material. Affect under which standard.\nThis business five news. Building respond fast share live.',
    'email': 'allenstacey@example.net',
    'phone_number': '427-847-0828',
    'json': {
    'name': 'Lauren Chavez',
    'address': '36282 Kelley Glens Apt. 040\nJeffreyport, NE 60833',
},
    'key57106': 'value74754',
    'key62631': 'value95969',
    'key63656': 'value53033',
    'key3584': 'value23861',
},
    {
    'id': 17527487406772,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Allison Smith',
    'address': '94914 Kathy Hollow Apt. 280\nClinetown, IA 06100',
    'text': 'Wall around break political value serve public.\nTend international employee year letter old specific. New teach early care east officer figure. Against then meeting maybe.',
    'email': 'rhill@example.com',
    'phone_number': '(366)440-5689',
    'json': {
    'name': 'Roger Snyder',
    'address': '8213 Kimberly Stream\nSpencestad, AS 44631',
},
    'key87110': 'value53411',
    'key98753': 'value31119',
    'key5685': 'value15930',
    'key68693': 'value17054',
    'key63197': 'value42517',
    'key91047': 'value6164',
    'key50460': 'value68109',
    'key96332': 'value94570',
},
    {
    'id': 17527487406784,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Anna Villa',
    'address': '42650 Martinez Crossroad\nBarbarabury, OR 75149',
    'text': 'Whose tend environment join what performance card. Late new television participant school. Long go house cover soldier ever.',
    'email': 'parrishjacqueline@example.org',
    'phone_number': '(508)254-0789x65852',
    'json': {
    'name': 'Frances Fox',
    'address': '7396 Bradley Cove\nBonniemouth, KY 91864',
},
    'key70192': 'value39438',
    'key15918': 'value53625',
    'key37217': 'value20881',
    'key778': 'value97252',
    'key58553': 'value54743',
    'key15586': 'value78077',
    'key63557': 'value79555',
    'key29144': 'value16792',
    'key50563': 'value29878',
    'key7144': 'value67706',
},
    {
    'id': 17527487406798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Tracy Hall',
    'address': '576 Galvan Walk\nNew Brianhaven, AR 71323',
    'text': 'Water across wait. Talk I support able common. Discussion future order center identify cause example.',
    'email': 'gregorypatrick@example.net',
    'phone_number': '592.961.1006x55088',
    'json': {
    'name': 'Paul Morris',
    'address': '22389 Robin Lodge\nNorth Dianaton, DE 99401',
},
    'key51482': 'value33331',
    'key19369': 'value76452',
    'key98646': 'value97614',
    'key37004': 'value43279',
    'key79644': 'value23872',
    'key98387': 'value76087',
    'key89988': 'value53617',
    'key1915': 'value19241',
    'key86444': 'value78561',
    'key84218': 'value19848',
},
    {
    'id': 17527487406812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Melissa Melendez',
    'address': '03807 Reyes Rest\nEast Joshuastad, NC 63043',
    'text': 'Effect pay commercial property. Wonder of people two.\nPartner dog decide mission sit return product. Opportunity effort talk many food year change.',
    'email': 'vanessa48@example.com',
    'phone_number': '9532246368',
    'json': {
    'name': 'James Shaw',
    'address': '12729 Maria Isle\nMullenmouth, NV 55899',
},
    'key32020': 'value63533',
    'key30893': 'value12172',
    'key36059': 'value96561',
},
    {
    'id': 17527487406825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joseph Clarke',
    'address': '94257 Drake Corner\nLynnfort, NV 41623',
    'text': 'Year thousand head hospital.\nClass cost claim provide. Situation cell cost environment. Move his court term risk.',
    'email': 'johnathan00@example.org',
    'phone_number': '276.897.9368x024',
    'json': {
    'name': 'David Rivers',
    'address': 'PSC 6803, Box 4743\nAPO AE 22776',
},
    'key89407': 'value37906',
    'key84370': 'value89044',
    'key99941': 'value28398',
    'key53327': 'value11198',
    'key82494': 'value42254',
    'key3458': 'value48978',
    'key20481': 'value81458',
    'key63525': 'value77724',
},
    {
    'id': 17527487406836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Desiree Mcintyre',
    'address': '232 Heather Junction\nRandallberg, TN 18543',
    'text': 'Determine difference well low guy. While page room someone cost strong grow.\nTrue foreign firm force she.',
    'email': 'dhayden@example.org',
    'phone_number': '315-414-2485x404',
    'json': {
    'name': 'Stephanie Valdez',
    'address': '5592 Lisa Mission\nPort Antonio, PW 36235',
},
    'key20057': 'value59426',
    'key6617': 'value79519',
    'key81057': 'value30855',
    'key69399': 'value78100',
},
    {
    'id': 17527487406849,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Dr. Angela Powell',
    'address': 'Unit 7593 Box 8210\nDPO AE 67180',
    'text': 'Stand evidence around billion ahead law wish.\nFine new including police. Read should near begin democratic word.\nFirst individual indicate example any.',
    'email': 'rodriguezshannon@example.org',
    'phone_number': '754.861.1005x44565',
    'json': {
    'name': 'Patricia Malone',
    'address': '47130 Melissa Trail Apt. 432\nBakerland, CA 24189',
},
    'key28202': 'value30224',
    'key21794': 'value66924',
    'key9100': 'value92279',
    'key58217': 'value13823',
    'key11424': 'value70829',
    'key52328': 'value30889',
    'key55727': 'value94767',
    'key63837': 'value79725',
    'key35209': 'value64814',
    'key89453': 'value43533',
},
    {
    'id': 17527487406861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Nicole Leach',
    'address': '237 Sarah Village\nDonaldburgh, TX 45181',
    'text': 'Moment receive particularly voice recently. From end it. Time security call represent fact state simple.',
    'email': 'hannahwhite@example.org',
    'phone_number': '577.369.2356',
    'json': {
    'name': 'Shane Sloan',
    'address': '7782 Dickson Fords\nPort Karenland, NJ 06183',
},
    'key58402': 'value13619',
    'key32310': 'value19256',
    'key77873': 'value37247',
    'key51754': 'value37952',
    'key21290': 'value29546',
    'key91348': 'value72794',
    'key66560': 'value34184',
    'key62993': 'value47966',
},
    {
    'id': 17527487406875,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Richard Wilson',
    'address': '9919 Sara Street\nAcevedoview, CO 15825',
    'text': 'Computer after institution describe. Example garden good size long. Best road career prevent family offer.\nSuggest stuff important chance old sit. Right indicate official fill.',
    'email': 'steven75@example.com',
    'phone_number': '735.345.4382x8499',
    'json': {
    'name': 'Jessica Lewis',
    'address': '1717 Rich Drives Apt. 685\nFaulknershire, WA 52249',
},
    'key14251': 'value53759',
    'key11143': 'value18434',
    'key49939': 'value89899',
    'key82343': 'value103',
    'key30289': 'value83532',
    'key79283': 'value53536',
    'key328': 'value69635',
    'key40352': 'value17983',
},
    {
    'id': 17527487406888,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Robert Coleman',
    'address': '748 Espinoza Mountains Suite 060\nSouth Susan, IN 33940',
    'text': 'Stuff improve common mother deal.\nSafe score age will memory grow. Unit organization expect nice wall hour. When concern line note like.',
    'email': 'benjamin95@example.org',
    'phone_number': '(260)363-9055x52351',
    'json': {
    'name': 'Jonathan Long',
    'address': '73073 April Summit\nNew Richardchester, SD 74204',
},
    'key94937': 'value17676',
    'key82072': 'value17452',
    'key63671': 'value41119',
    'key53492': 'value54595',
},
    {
    'id': 17527487406900,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Matthew Wolf',
    'address': '4128 Holder Green\nEast Meganview, CT 77501',
    'text': 'Or plan while significant question. War security friend right along executive answer discover.',
    'email': 'paynekimberly@example.net',
    'phone_number': '001-249-419-2375x512',
    'json': {
    'name': 'David Whitehead',
    'address': 'Unit 9594 Box 9064\nDPO AP 36093',
},
    'key70551': 'value65598',
    'key53453': 'value88117',
},
    {
    'id': 17527487406910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Andre Perez',
    'address': '07798 Pamela Passage Apt. 272\nSouth Michael, TN 59380',
    'text': 'Democrat game nothing worker card pretty simple. Care all price carry. Report identify clear with blood develop various. Feeling space travel including.',
    'email': 'ipace@example.com',
    'phone_number': '415-931-3391x3565',
    'json': {
    'name': 'Mr. Michael Garcia',
    'address': '20619 Hernandez Wells Suite 544\nErinberg, FM 73951',
},
    'key12249': 'value56915',
    'key23321': 'value76142',
    'key89320': 'value47313',
    'key33387': 'value37642',
    'key5018': 'value62207',
    'key26637': 'value66782',
    'key43691': 'value85496',
    'key70924': 'value40608',
},
    {
    'id': 17527487406920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Brittany Hall',
    'address': '076 Ryan Forge\nEast Nancy, FL 20447',
    'text': 'One seek from live. Else ahead within practice strong. Music money ball somebody report well interesting. Arm want seek alone state.',
    'email': 'thomas37@example.net',
    'phone_number': '847-731-7813',
    'json': {
    'name': 'Heather Erickson',
    'address': '4146 Michael Locks\nWest Stephanie, MD 38753',
},
    'key81163': 'value46215',
    'key8051': 'value14650',
},
    {
    'id': 17527487406931,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Diana Molina',
    'address': '54911 Mitchell Park Suite 874\nLouisville, CA 62554',
    'text': 'Life detail measure customer know north painting. Eight idea hear whether.\nSummer plan rather. Individual other she man.',
    'email': 'icarr@example.org',
    'phone_number': '+1-436-577-2567x847',
    'json': {
    'name': 'Tyler Williams',
    'address': '9923 Robert Cliffs Suite 901\nPort Erica, SC 77308',
},
    'key85249': 'value80411',
    'key94790': 'value60253',
    'key98541': 'value28999',
    'key24703': 'value20735',
    'key73751': 'value53650',
    'key20764': 'value61453',
    'key63858': 'value78906',
    'key29880': 'value13104',
    'key51668': 'value63675',
    'key94190': 'value11363',
},
    {
    'id': 17527487406942,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Jessica Martinez',
    'address': 'Unit 0520 Box 2699\nDPO AA 35099',
    'text': 'Cause keep wish environment box behind away. Truth debate fly a study any. Lot perhaps pretty.\nEnvironmental human as agree authority. Food than large. Large nice people although rise.',
    'email': 'lisamcdaniel@example.net',
    'phone_number': '+1-908-977-8907',
    'json': {
    'name': 'Michelle Gonzalez',
    'address': '29256 Carlson Mountain Apt. 916\nNorth Christopherside, OH 03005',
},
    'key92049': 'value42534',
    'key67622': 'value42344',
    'key86397': 'value80388',
    'key55200': 'value17104',
    'key32407': 'value55202',
    'key19869': 'value20514',
    'key49078': 'value35433',
},
    {
    'id': 17527487406952,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Evan Martinez',
    'address': '90391 Amanda Shoals Apt. 366\nPort Cole, RI 23012',
    'text': 'Foreign front we.\nCover per past wear.\nUsually arrive sure work possible look. Arm order effort.\nSupport operation happen religious.\nHit play dinner billion.',
    'email': 'victorbridges@example.org',
    'phone_number': '5754110809',
    'json': {
    'name': 'Michelle Jordan',
    'address': '05765 Finley Track Suite 838\nSouth Robertbury, NM 51891',
},
    'key34770': 'value79521',
},
    {
    'id': 17527487406963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Caitlin Hughes',
    'address': '711 Gonzales Canyon Suite 971\nNew Thomaschester, HI 01562',
    'text': 'Sport wife very.\nNews help describe cultural. What join arm vote tax. Indicate interesting everyone until act.',
    'email': 'ymoore@example.org',
    'phone_number': '891-305-9498x6298',
    'json': {
    'name': 'Adam Castro',
    'address': 'USNS Wilson\nFPO AE 01446',
},
    'key43082': 'value56028',
    'key44943': 'value26163',
    'key74801': 'value44387',
    'key87394': 'value70913',
    'key92110': 'value46913',
},
    {
    'id': 17527487406973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Cassandra Combs',
    'address': '3452 Lewis Turnpike\nLake Michael, GA 91979',
    'text': 'Growth world last official give sea when.\nAssume effect attention see card five. Avoid deep reduce miss federal road yard his.',
    'email': 'ana77@example.com',
    'phone_number': '509-547-6955x5264',
    'json': {
    'name': 'Jason Vaughan',
    'address': '4021 Kimberly Shoals\nSouth Katie, TN 41351',
},
    'key35952': 'value74061',
    'key60504': 'value73016',
    'key30990': 'value76074',
    'key11885': 'value24351',
},
    {
    'id': 17527487406983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Tracey Avila',
    'address': '9708 Bean Pass Apt. 141\nPort Samantha, FM 39225',
    'text': 'Fear white sort wish material sell reflect. Education within when someone quite action property technology.',
    'email': 'zmcdowell@example.org',
    'phone_number': '291-762-9299',
    'json': {
    'name': 'Peter Elliott',
    'address': '760 Holmes Cliff Suite 582\nVangfurt, NC 77321',
},
    'key80478': 'value7224',
    'key95191': 'value62958',
    'key48151': 'value66949',
    'key50028': 'value67149',
},
    {
    'id': 17527487406995,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Lisa Roberts',
    'address': '8586 Jones Rest\nAngelaberg, MD 85427',
    'text': 'Remain left current knowledge message card. Feeling image hear. These rich area little peace. Later else car put.',
    'email': 'shane16@example.net',
    'phone_number': '+1-526-812-6194x651',
    'json': {
    'name': 'Reginald Sanchez',
    'address': '7881 Walker Land\nMontoyaview, SD 91858',
},
    'key22052': 'value30254',
    'key21576': 'value41801',
    'key71167': 'value26470',
    'key67238': 'value89245',
    'key57670': 'value34160',
    'key78837': 'value79136',
    'key17356': 'value99221',
    'key64614': 'value2889',
    'key13603': 'value83110',
},
    {
    'id': 17527487407006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Leah Watson',
    'address': '10656 Daniels Divide Suite 764\nPatelview, ME 27032',
    'text': 'Body why various morning.\nThis thousand ahead view piece girl time. Rock professional participant language party soldier everyone. Color success turn student just now interesting area.',
    'email': 'icole@example.com',
    'phone_number': '001-244-801-8272x633',
    'json': {
    'name': 'Melanie Moore',
    'address': 'PSC 2381, Box 0881\nAPO AP 22720',
},
    'key11631': 'value30093',
},
    {
    'id': 17527487407015,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Rebecca Olson',
    'address': '3507 Matthew Ridge\nNew Patricia, WI 88278',
    'text': 'Air enjoy enjoy such admit thought establish. Change arrive kind successful perhaps natural.\nWhose particular true just however remember away if.',
    'email': 'paullee@example.com',
    'phone_number': '001-364-809-3610x2588',
    'json': {
    'name': 'Jennifer Landry',
    'address': '0913 Richard View\nEast Josephside, MN 55056',
},
    'key79693': 'value17342',
    'key34611': 'value91970',
    'key50956': 'value32464',
    'key13210': 'value64241',
    'key37278': 'value74699',
    'key90647': 'value27930',
    'key19304': 'value15089',
    'key41646': 'value34197',
    'key65092': 'value79349',
},
    {
    'id': 17527487407026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Samantha Acosta',
    'address': '718 Hernandez Isle\nAllenside, WY 91286',
    'text': 'Image her concern listen would weight consumer.\nGeneral put land health only use recent. Always the certainly tend detail.\nSend city travel ahead forward sort compare. House three main also maybe.',
    'email': 'oevans@example.net',
    'phone_number': '(494)710-3658x8807',
    'json': {
    'name': 'Danielle Mcintosh',
    'address': '962 Terrell Brook Apt. 024\nFrederickville, IL 02355',
},
    'key66788': 'value66320',
    'key41101': 'value34286',
    'key53684': 'value97550',
    'key20349': 'value10971',
    'key93410': 'value81914',
    'key97097': 'value79440',
    'key35898': 'value74146',
    'key88147': 'value65527',
    'key84626': 'value30730',
    'key43514': 'value42399',
},
    {
    'id': 17527487407037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Laurie Scott',
    'address': '07261 Jonathan Estates\nClarkport, DC 83837',
    'text': 'Any onto could student really take. Hair deal send newspaper. Within put charge number community.\nPositive player agree ago future already stand. Throughout own live weight word idea later become.',
    'email': 'sbutler@example.com',
    'phone_number': '001-962-280-1724',
    'json': {
    'name': 'Richard Guerrero',
    'address': '3947 Griffin Parkways Apt. 588\nSouth Cynthiaborough, ME 25877',
},
    'key64083': 'value57784',
    'key83020': 'value57765',
},
    {
    'id': 17527487407048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Sarah Smith',
    'address': '842 Hayes Garden\nEast Thomas, AR 29189',
    'text': 'Travel rule exactly young. Bring range husband administration key response pressure.\nFoot per human pattern general traditional program. Case another forget need nation.',
    'email': 'hamiltonchristopher@example.net',
    'phone_number': '223-638-8195',
    'json': {
    'name': 'Eric Matthews',
    'address': '807 Smith Keys Apt. 122\nLake Madelinehaven, VI 01353',
},
    'key71107': 'value80998',
    'key25079': 'value59419',
    'key50736': 'value176',
    'key49688': 'value1535',
    'key13682': 'value4190',
    'key44017': 'value97063',
    'key2000': 'value93267',
    'key64844': 'value11969',
    'key66876': 'value59524',
    'key28691': 'value19415',
},
    {
    'id': 17527487407060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Brandon Miller',
    'address': '67116 Blankenship Turnpike Suite 637\nNew Tyler, ME 26249',
    'text': 'Accept skill sit successful who. Other democratic crime performance deal. Class case forward image executive up history.',
    'email': 'daleprince@example.org',
    'phone_number': '+1-909-250-2091x596',
    'json': {
    'name': 'Christine Wilson',
    'address': '36355 Regina Forest\nEast Stephenhaven, VT 39103',
},
    'key75760': 'value18907',
    'key78228': 'value63206',
    'key25579': 'value46652',
    'key18977': 'value56444',
},
    {
    'id': 17527487407072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Scott Fisher',
    'address': '5096 Lori Spur Apt. 550\nHarryville, LA 71459',
    'text': 'Every its action employee. Radio back purpose former. Choice level place.\nKnow gun buy painting Mrs perform. Maintain include within good. Standard remember bank we mouth down.',
    'email': 'mlamb@example.org',
    'phone_number': '9657506760',
    'json': {
    'name': 'John Lee',
    'address': 'PSC 3113, Box 1271\nAPO AA 21049',
},
    'key10561': 'value20944',
    'key38455': 'value23130',
    'key45875': 'value77329',
    'key88124': 'value92353',
    'key84895': 'value44901',
    'key40065': 'value20156',
},
    {
    'id': 17527487407080,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Marcia Smith',
    'address': '07146 Brenda Fall Apt. 076\nBarryshire, UT 79937',
    'text': 'Listen could start gas court. Couple little amount free. Father short true rather three. Modern stop word project also meet long.',
    'email': 'xdavis@example.net',
    'phone_number': '7613004475',
    'json': {
    'name': 'Donna Lee',
    'address': '91965 Felicia Forks Apt. 539\nLeefort, PR 12919',
},
    'key52226': 'value50787',
    'key97675': 'value37814',
    'key636': 'value93880',
    'key6140': 'value33384',
    'key96653': 'value2058',
    'key19491': 'value88078',
},
    {
    'id': 17527487407091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Deborah Harris',
    'address': '242 Williams Mill Suite 900\nEast Andrewfort, IA 20101',
    'text': 'Address stage wear they general treatment everybody billion. Discussion generation campaign.\nFace after with too model not move. Mr long state face foot camera nation sing.',
    'email': 'jonathanprice@example.org',
    'phone_number': '+1-236-283-6699x2783',
    'json': {
    'name': 'Martha Young',
    'address': '7059 Steele Station Suite 535\nBradleyborough, OH 40737',
},
    'key78651': 'value10862',
    'key48029': 'value36906',
    'key91359': 'value46923',
    'key60669': 'value39632',
    'key72119': 'value2894',
    'key23586': 'value58988',
    'key6008': 'value21609',
    'key42523': 'value38492',
    'key14937': 'value52142',
},
    {
    'id': 17527487407103,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Nicholas Diaz',
    'address': '5654 Kevin Falls\nWilliamsland, WI 07666',
    'text': 'Foot bill management often gun approach nearly. Around amount ago heavy begin side.',
    'email': 'jacksonronald@example.com',
    'phone_number': '639.645.3345x23714',
    'json': {
    'name': 'Patty Brown',
    'address': '188 Wilson Dale\nNorth Lauraberg, FL 07087',
},
    'key41265': 'value89504',
    'key37103': 'value24803',
    'key72324': 'value93705',
    'key29282': 'value51122',
    'key57667': 'value6302',
    'key16673': 'value89802',
},
    {
    'id': 17527487407115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kristina Mooney',
    'address': '69776 Paul Orchard\nNorth Cynthiachester, IL 63217',
    'text': 'Loss democratic must history science because.\nInstitution general including despite mean hospital. Firm take scene.',
    'email': 'garybates@example.org',
    'phone_number': '+1-422-837-7067x95914',
    'json': {
    'name': 'Robert Yang',
    'address': '91269 Maria Flats Suite 902\nNorth Amyview, TX 42229',
},
    'key85900': 'value8507',
    'key29217': 'value13822',
    'key65323': 'value19785',
    'key41233': 'value85724',
    'key51189': 'value33568',
    'key35381': 'value5252',
    'key32459': 'value91513',
    'key49510': 'value30267',
    'key40919': 'value68812',
    'key26905': 'value6311',
},
    {
    'id': 17527487407126,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Mrs. Angela Taylor',
    'address': '7679 Robert Junctions\nPort Stephanieshire, WA 70183',
    'text': 'Include nature these move remember big sense. Major it trouble no a writer. Safe reveal seek significant me both.\nSure young rather. Customer end stage especially.',
    'email': 'angela44@example.net',
    'phone_number': '(262)379-8322x241',
    'json': {
    'name': 'Timothy Keith',
    'address': '069 Marie Terrace Suite 473\nTraceyville, IN 82036',
},
    'key82790': 'value10891',
    'key81067': 'value67778',
    'key8261': 'value47956',
    'key55299': 'value37862',
    'key583': 'value22273',
    'key29337': 'value15622',
    'key59796': 'value75346',
},
    {
    'id': 17527487407137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Samuel Lee',
    'address': '461 Christensen Shores\nMicheleview, GU 45091',
    'text': 'Them develop cup prove without decade million. Myself let audience note way cold condition. Response cold seek blood.\nAnswer court school listen imagine. Agreement region future skin on look prepare.',
    'email': 'kenneth21@example.net',
    'phone_number': '001-466-965-3426x4151',
    'json': {
    'name': 'Curtis Larson',
    'address': '083 Marissa Brook Suite 768\nMarymouth, MD 65914',
},
    'key45071': 'value11861',
    'key48160': 'value15886',
    'key16932': 'value11505',
    'key60553': 'value93111',
    'key36757': 'value71089',
    'key18818': 'value25506',
    'key97856': 'value79205',
},
    {
    'id': 17527487407148,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Melissa Miranda',
    'address': '55897 Watts Circles\nLake Cherylland, LA 53479',
    'text': 'Knowledge ball for every forget customer. Away offer consider step.\nWhen keep level him could. Form foreign onto me hair say town political.\nWhose always major will. Worry region travel paper.',
    'email': 'owhite@example.net',
    'phone_number': '312-936-7508x0069',
    'json': {
    'name': 'Tracy Jordan',
    'address': '4340 Rich Stravenue\nNew Andrew, WI 35554',
},
    'key1015': 'value66735',
    'key66251': 'value64072',
},
    {
    'id': 17527487407158,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Brittany Hughes',
    'address': '464 Cathy Parkways Suite 316\nPort Connie, MD 35067',
    'text': 'Wife worry stage pass consider reality thing history. White daughter approach prove.\nTeam interesting hit. Vote receive specific probably police. Box shoulder avoid foot sort.',
    'email': 'michaelcook@example.net',
    'phone_number': '(372)723-4251',
    'json': {
    'name': 'Mr. Ryan Edwards',
    'address': 'Unit 8215 Box 9589\nDPO AA 12449',
},
    'key71309': 'value20942',
    'key93820': 'value66796',
},
    {
    'id': 17527487407168,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kimberly Anthony',
    'address': 'Unit 4420 Box 0565\nDPO AE 83112',
    'text': 'Happy budget available with.\nAs whose prove task back. Shake sort few them boy daughter. Become store toward produce window conference industry.\nClearly land ahead money right. With even seek.',
    'email': 'jessica21@example.net',
    'phone_number': '405-631-9315',
    'json': {
    'name': 'Andrew Chang',
    'address': '10637 Strong Brooks\nPort Mariahburgh, NE 14724',
},
    'key13053': 'value98982',
    'key7327': 'value36045',
    'key9985': 'value89112',
    'key55987': 'value76318',
},
    {
    'id': 17527487407176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Katelyn Anthony',
    'address': '489 Amanda Club\nSouth Danielmouth, ND 79712',
    'text': 'News season activity wrong.\nWord board next end nation product protect. Require result leave share cell. Once recognize me deep class. Seven international bed only rather high.',
    'email': 'jessemartinez@example.net',
    'phone_number': '(786)576-8110',
    'json': {
    'name': 'Lucas Hardin',
    'address': '960 Newman Mountains Suite 763\nLesliefurt, VA 09148',
},
    'key60980': 'value66283',
    'key19237': 'value68027',
    'key71490': 'value2601',
},
    {
    'id': 17527487407188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Cameron Fischer',
    'address': '050 Morris Inlet\nBergerview, LA 74373',
    'text': 'Box project main poor. Court American miss.\nSummer wait agreement know. Choose animal central use go. Third ahead mind red. Represent nothing enough begin its game.',
    'email': 'robert66@example.org',
    'phone_number': '696-709-0383',
    'json': {
    'name': 'Mrs. Emily Davis',
    'address': '73551 Stuart Viaduct\nNew Luke, CA 56455',
},
    'key74460': 'value64352',
    'key53978': 'value52278',
    'key37117': 'value56054',
    'key21137': 'value59350',
    'key40778': 'value45278',
    'key97249': 'value78788',
    'key18410': 'value92003',
    'key43035': 'value48833',
    'key55153': 'value32757',
},
    {
    'id': 17527487407199,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jorge Rodriguez',
    'address': 'USNS Reese\nFPO AA 61997',
    'text': 'Task force through. Decision here onto bit sense. Hour deal agency project professor.\nTask this deal significant radio property. Cover admit sea student man grow forward.',
    'email': 'charlene69@example.org',
    'phone_number': '392.534.5873x8080',
    'json': {
    'name': 'Aaron Gardner',
    'address': '652 Bishop Trail\nJohnsonchester, IL 33371',
},
    'key56982': 'value22775',
    'key67991': 'value90497',
    'key1052': 'value19950',
    'key76455': 'value9145',
    'key79674': 'value55041',
    'key56210': 'value48126',
    'key61389': 'value66874',
    'key18747': 'value11887',
    'key52894': 'value487',
    'key10078': 'value85050',
},
    {
    'id': 17527487407209,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Dillon Robinson',
    'address': '419 Kimberly Pines\nBrentborough, PR 24185',
    'text': 'Shake else arm issue what. Ask past ever fire huge control born.\nWriter medical poor right stage. Even around despite take air family. Cultural arrive answer ahead machine room dark.',
    'email': 'benjamin05@example.org',
    'phone_number': '600.858.7594',
    'json': {
    'name': 'Valerie Mckinney',
    'address': '074 Amanda Key Apt. 753\nBrittneymouth, VA 99359',
},
    'key793': 'value39451',
    'key15264': 'value92418',
    'key71695': 'value62237',
    'key464': 'value63610',
    'key73370': 'value53804',
    'key42159': 'value41456',
    'key77819': 'value53860',
    'key5088': 'value69542',
    'key26511': 'value81915',
    'key62718': 'value1966',
},
    {
    'id': 17527487407219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kenneth Barnes',
    'address': '53733 Mendoza Plains Apt. 039\nRyanshire, MO 93021',
    'text': 'Society heart near.\nMrs when shoulder pay Mr strong. Community really popular evening difference certainly run. Positive attack receive. Attorney national trial continue house total.',
    'email': 'raymond51@example.org',
    'phone_number': '898.558.6989x48378',
    'json': {
    'name': 'Misty Ross',
    'address': '879 Jones Pines\nCarlosstad, DC 15400',
},
    'key70893': 'value27310',
    'key48678': 'value67013',
    'key32814': 'value88617',
    'key97809': 'value62151',
    'key20199': 'value44798',
    'key7270': 'value74934',
    'key17577': 'value68753',
    'key35113': 'value90167',
    'key11786': 'value87635',
},
    {
    'id': 17527487407230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Taylor Jones',
    'address': '22196 Alexander Spring\nRalphburgh, SC 65393',
    'text': 'What method chair until year. Concern find order foot behavior heart customer. Radio adult keep fly practice off defense detail.',
    'email': 'gregoryannette@example.net',
    'phone_number': '(617)299-9444x986',
    'json': {
    'name': 'Anthony Clark',
    'address': '003 Washington Glens Suite 974\nSouth Barbara, PW 96704',
},
    'key76457': 'value54936',
    'key75019': 'value14986',
    'key24361': 'value79831',
    'key79092': 'value50660',
    'key30122': 'value8847',
},
    {
    'id': 17527487407241,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'George Brown',
    'address': '060 Lowe Spurs\nPatrickchester, GU 65161',
    'text': 'Sure professor whatever child country.\nServe success firm old strong civil doctor.',
    'email': 'zdavis@example.org',
    'phone_number': '001-773-796-6885x779',
    'json': {
    'name': 'Samantha Hodge',
    'address': '29242 Murphy Passage\nNew Amyfort, AS 94666',
},
    'key65983': 'value38144',
    'key16400': 'value44406',
    'key14874': 'value33080',
    'key70463': 'value59041',
    'key50559': 'value12332',
    'key9240': 'value92171',
    'key10330': 'value26323',
},
    {
    'id': 17527487407252,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michael French',
    'address': '543 Rodriguez Ridge\nWest Joseph, MI 92414',
    'text': 'Because consider yard lay possible mother summer. Black mother science firm. Responsibility everybody evening sign nature. Whole big single end.',
    'email': 'katelyn63@example.net',
    'phone_number': '+1-938-637-2048x393',
    'json': {
    'name': 'Jordan Mckinney',
    'address': '9645 Baldwin Islands Apt. 967\nWest Michael, KS 41860',
},
    'key13797': 'value78135',
    'key91247': 'value72613',
    'key72292': 'value41168',
    'key37294': 'value57347',
    'key20965': 'value20267',
    'key8641': 'value61562',
    'key98256': 'value60897',
    'key23571': 'value51480',
    'key2693': 'value29961',
},
    {
    'id': 17527487407262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Amanda Jacobs',
    'address': '919 Clark Fort\nMitchellmouth, KS 69911',
    'text': 'Record how five hit unit any either. Various watch daughter attack find ready. Lead little would fish head pattern authority.',
    'email': 'lawsonmelissa@example.net',
    'phone_number': '436.392.8008x6880',
    'json': {
    'name': 'Jared Brandt',
    'address': '31724 Tyler Prairie Apt. 418\nMaryview, AK 17788',
},
    'key27000': 'value68395',
    'key78499': 'value75311',
    'key52604': 'value74591',
    'key93973': 'value60139',
    'key99898': 'value73307',
    'key83441': 'value80116',
    'key93166': 'value50296',
    'key93346': 'value32332',
},
    {
    'id': 17527487407274,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Douglas Castaneda',
    'address': '7536 Kenneth Dale Suite 989\nLake Tylerbury, WY 54096',
    'text': 'Senior see half box sometimes seem brother everybody. Behavior sport pay song continue home. Value per old.\nMemory draw fear the. Probably technology various develop though.',
    'email': 'donna61@example.org',
    'phone_number': '742-434-8401x1663',
    'json': {
    'name': 'Rachel Henderson',
    'address': 'PSC 1717, Box 1194\nAPO AP 94820',
},
    'key2283': 'value23665',
    'key61491': 'value82781',
    'key21636': 'value28070',
    'key5692': 'value62347',
    'key58925': 'value83992',
},
    {
    'id': 17527487407283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Tiffany Friedman',
    'address': '49485 Beth Mission Suite 347\nJenniferhaven, NY 68668',
    'text': 'Yard decision the on. Pm section occur but short.\nShare write shake through. Instead range nation this whose.',
    'email': 'murphydavid@example.com',
    'phone_number': '570.332.8057',
    'json': {
    'name': 'Kathryn Hamilton',
    'address': '9499 John Key Apt. 443\nStevenmouth, AS 96784',
},
    'key33022': 'value17982',
    'key61785': 'value49355',
    'key74318': 'value93727',
    'key6722': 'value81107',
    'key40919': 'value14991',
    'key27251': 'value8379',
},
    {
    'id': 17527487407294,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Heather Bennett',
    'address': '38008 Campbell Mount Apt. 103\nTurnerhaven, WA 49866',
    'text': 'Structure company Republican message. Herself citizen enter sign.\nDemocrat tax opportunity bill him.\nCondition use measure interest my. Deep place reality decade itself.',
    'email': 'ronaldrodriguez@example.net',
    'phone_number': '844.214.5250',
    'json': {
    'name': 'Jennifer Morales DVM',
    'address': '3234 Williams Flat Suite 677\nEast Isaacport, ND 82183',
},
    'key98686': 'value22722',
    'key6158': 'value70033',
},
    {
    'id': 17527487407305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Andrea Miller',
    'address': '30391 Peter Circles Apt. 186\nKingport, AL 92055',
    'text': 'Prepare music travel more. Professional smile goal top exactly. Term own order once expect.\nDirector degree natural. Look also level film ability protect choose.',
    'email': 'dwayne44@example.com',
    'phone_number': '728-471-2021x8572',
    'json': {
    'name': 'Michelle Archer',
    'address': '55696 April Pine Apt. 980\nChristopherland, MS 44054',
},
    'key30756': 'value13264',
},
    {
    'id': 17527487407316,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'John Kennedy',
    'address': 'Unit 8622 Box 5942\nDPO AP 67221',
    'text': 'Art but Congress case. Film learn guess than theory who. Raise large rise hand ability.\nTable her by impact tough. Interesting like space near great three family possible. Financial tell stop become.',
    'email': 'harrisonnicole@example.org',
    'phone_number': '001-851-895-7355',
    'json': {
    'name': 'George Allen',
    'address': '672 Douglas Alley\nBradleyfurt, MP 29580',
},
    'key3648': 'value70546',
    'key64986': 'value92041',
    'key8254': 'value65915',
    'key56183': 'value39780',
    'key77739': 'value15726',
    'key18070': 'value76754',
    'key74549': 'value2396',
    'key93176': 'value52115',
    'key64995': 'value66258',
},
    {
    'id': 17527487407326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Jason Martin',
    'address': 'PSC 6443, Box 4151\nAPO AP 77836',
    'text': 'Trip last wrong different above exist. Lot agent general article send what. Important factor measure audience. Scientist many nor instead cup view.',
    'email': 'torresandrew@example.com',
    'phone_number': '(808)735-4151x9182',
    'json': {
    'name': 'Crystal Delacruz',
    'address': '8051 Bullock Orchard\nLeeport, VT 72081',
},
    'key45479': 'value64501',
    'key67648': 'value36981',
    'key30610': 'value51559',
    'key56750': 'value49630',
    'key66777': 'value13343',
},
    {
    'id': 17527487407335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Alexis Lee',
    'address': '03850 Stephanie Manor\nEast Cynthiastad, FM 04554',
    'text': 'Scene hope white conference main. Toward impact expert establish conference author country seem. His begin them friend control. Blue of home practice industry.',
    'email': 'millerjerry@example.net',
    'phone_number': '7934468695',
    'json': {
    'name': 'Rebecca Morgan',
    'address': '5798 Gary Greens\nGarciaberg, CT 42363',
},
    'key60135': 'value69919',
    'key29261': 'value76488',
},
    {
    'id': 17527487407346,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Candice Klein',
    'address': '18651 Campbell Inlet\nWest Tonymouth, WI 64148',
    'text': 'Ever senior allow these. Fire success else five with.\nArt will claim former project data.\nSoon discover box face. Entire break grow paper you add.',
    'email': 'johnsonsusan@example.net',
    'phone_number': '001-890-727-3383x73606',
    'json': {
    'name': 'Joel Jackson',
    'address': '38670 Nicole Motorway\nFuentesport, AZ 46507',
},
    'key20791': 'value31104',
    'key48714': 'value17770',
    'key96982': 'value71431',
    'key98097': 'value55717',
    'key19301': 'value82930',
    'key21353': 'value37374',
    'key94789': 'value35430',
    'key67268': 'value92869',
    'key538': 'value86830',
    'key8885': 'value31798',
},
    {
    'id': 17527487407358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Jacqueline Castillo',
    'address': '80200 Nicole Lake\nLewismouth, MO 65542',
    'text': 'Science within money through site choice those. Itself trial food sea into three firm. Know process eight choose.\nSame her by dinner hotel accept. Late prepare city sit. Paper major line clear yard.',
    'email': 'brookserin@example.net',
    'phone_number': '227.471.4805x33364',
    'json': {
    'name': 'Donald Hicks MD',
    'address': '726 Bradford Plaza Apt. 171\nWest Jessicatown, MH 66836',
},
    'key12676': 'value52479',
    'key42578': 'value47601',
    'key95997': 'value12655',
},
    {
    'id': 17527487407370,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Victoria Gray',
    'address': 'Unit 4264 Box 1197\nDPO AE 28008',
    'text': 'Listen husband amount western. Investment member beautiful important everything note. Evidence always country around nation.\nKitchen heavy feel newspaper. Beautiful ball world perhaps morning.',
    'email': 'asmith@example.net',
    'phone_number': '(258)980-1662',
    'json': {
    'name': 'Mrs. Zoe Anderson',
    'address': '0170 Jill Club Apt. 892\nNew Amandabury, UT 22204',
},
    'key36845': 'value92514',
    'key74258': 'value97303',
    'key86028': 'value70188',
    'key10421': 'value50279',
    'key53041': 'value5028',
    'key68523': 'value53067',
    'key23805': 'value69561',
    'key90295': 'value22720',
},
    {
    'id': 17527487407379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jodi Dunn',
    'address': '2920 Farmer Branch Apt. 463\nBradleymouth, MP 79447',
    'text': 'Defense water contain real. Task wish choose arm discover. Billion rock meet successful seat top probably.\nCell himself discuss respond turn energy.',
    'email': 'nortonjason@example.com',
    'phone_number': '(681)594-0319',
    'json': {
    'name': 'Caitlin Cruz',
    'address': '45029 Katelyn Extensions\nNew Kathy, SC 91368',
},
    'key39689': 'value17507',
    'key99640': 'value64318',
    'key94601': 'value95320',
    'key74444': 'value47640',
},
    {
    'id': 17527487407390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Loretta Schmitt',
    'address': '30294 David Stravenue\nEast Roymouth, LA 13289',
    'text': 'Happy pressure risk present during. Seem paper fight allow claim test drug. Voice knowledge something local summer involve.',
    'email': 'richardstonya@example.org',
    'phone_number': '4626802744',
    'json': {
    'name': 'Amanda Pittman',
    'address': '590 Mary Dam\nBrowntown, SC 99090',
},
    'key97335': 'value56636',
    'key78171': 'value68750',
    'key8765': 'value73369',
    'key10143': 'value4588',
    'key75736': 'value42413',
    'key3493': 'value82716',
    'key90111': 'value52356',
    'key77154': 'value91281',
},
    {
    'id': 17527487407401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Elizabeth Davila',
    'address': '794 Meghan Neck Suite 880\nSmithshire, MI 62014',
    'text': 'Name morning bed he. Less fine staff sense.\nThree task live green body. Loss within production group involve perhaps design able.',
    'email': 'gdavidson@example.com',
    'phone_number': '(723)495-4852',
    'json': {
    'name': 'Gloria Taylor',
    'address': '761 Brianna Fork Suite 947\nElizabethville, WV 31799',
},
    'key8651': 'value79070',
    'key89675': 'value61046',
    'key18673': 'value67167',
    'key57459': 'value55503',
},
    {
    'id': 17527487407411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Terry Howard',
    'address': '15381 Guerrero Stream\nDavishaven, MT 13754',
    'text': 'Fine citizen drive find send. Chance knowledge eight trade. Nature heart message movie before Congress nor.',
    'email': 'roythomas@example.org',
    'phone_number': '(386)947-8790x014',
    'json': {
    'name': 'Lauren Little',
    'address': 'USCGC Foley\nFPO AA 10122',
},
    'key64566': 'value65732',
    'key22685': 'value21880',
    'key20134': 'value44200',
    'key22692': 'value55280',
    'key99610': 'value5451',
    'key15635': 'value2182',
    'key17983': 'value15804',
    'key34854': 'value9175',
},
    {
    'id': 17527487407422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'John Cobb',
    'address': '68829 Courtney Junction Suite 506\nLaurabury, GU 24628',
    'text': 'Water high listen knowledge religious bill college. Teach certainly management per of lead. Sport unit cover huge your government style.\nUpon simply pass.',
    'email': 'vaughnheather@example.com',
    'phone_number': '+1-679-976-7594x149',
    'json': {
    'name': 'Jamie Rose',
    'address': '89696 Valerie Place Suite 029\nKlineside, AL 27595',
},
    'key55019': 'value16307',
    'key31045': 'value33305',
    'key54139': 'value87536',
},
    {
    'id': 17527487407434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Frank Bond',
    'address': '2582 Whitney Mall\nPowellfurt, UT 51840',
    'text': 'Interview others movie suddenly high single. Reason since able order staff yard brother. City better night plan amount organization.',
    'email': 'lewisdawn@example.net',
    'phone_number': '+1-330-362-6032x392',
    'json': {
    'name': 'Christopher Fuller',
    'address': '88919 Garcia Brook Apt. 239\nNew Kenneth, KS 22776',
},
    'key57015': 'value35122',
    'key95494': 'value64196',
    'key83149': 'value19333',
    'key12463': 'value7689',
    'key93107': 'value91991',
    'key95960': 'value5018',
    'key98094': 'value84438',
    'key18512': 'value93941',
    'key43269': 'value82222',
    'key71115': 'value49284',
},
    {
    'id': 17527487407446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'David Gutierrez',
    'address': '04868 Jones Rapids\nDeborahfurt, NJ 32923',
    'text': 'Eight bed news again. Sometimes suggest training perhaps attention nice. Push for need short.',
    'email': 'andrea44@example.org',
    'phone_number': '+1-374-771-6584',
    'json': {
    'name': 'James Hood',
    'address': '498 Phillips Point Apt. 010\nEast Thomasburgh, MA 30182',
},
    'key32105': 'value25712',
    'key16119': 'value68098',
    'key28618': 'value30944',
    'key34412': 'value39121',
    'key30891': 'value19964',
    'key22847': 'value95341',
    'key84504': 'value69153',
    'key73081': 'value11401',
    'key34914': 'value84672',
},
    {
    'id': 17527487407457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Emily Delgado',
    'address': '029 Simpson Row\nChristyburgh, CT 47067',
    'text': 'Window agree set growth quite trip nice. Draw movie believe head human cost.\nShort herself time media those possible impact. This movement vote ability idea apply partner. Example skin all unit.',
    'email': 'shannonhoward@example.com',
    'phone_number': '758.720.5913x83339',
    'json': {
    'name': 'Charles Perez',
    'address': '1561 Paul Roads Apt. 546\nNew Eddieberg, TN 10872',
},
    'key98385': 'value28162',
    'key69161': 'value81614',
},
    {
    'id': 17527487407468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Matthew Wu',
    'address': 'PSC 7746, Box 8094\nAPO AA 20329',
    'text': 'Style mother source learn rate. Nor represent itself carry center Republican information. Hand mention offer will.\nTrial compare key practice old. Tonight according source hit rather above plan.',
    'email': 'rodriguezbrad@example.net',
    'phone_number': '(376)325-8331',
    'json': {
    'name': 'Jennifer Fields',
    'address': '374 Little Mill\nPort Kristen, UT 09476',
},
    'key24908': 'value24327',
    'key78183': 'value780',
    'key21199': 'value81788',
    'key89281': 'value4418',
    'key19207': 'value44831',
    'key91457': 'value62425',
    'key19930': 'value6554',
    'key46504': 'value32872',
    'key33133': 'value81441',
    'key48615': 'value96698',
},
    {
    'id': 17527487407478,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'David Maxwell',
    'address': '7523 Amber Lock\nEast Elizabeth, HI 34778',
    'text': 'Film stock guess throw west.\nMe tell leader affect anyone about participant talk. Officer especially personal read against discover. Culture lawyer put popular get suggest.',
    'email': 'rlowery@example.com',
    'phone_number': '(213)238-9609x3550',
    'json': {
    'name': 'Alexander Hines',
    'address': '43482 Donald View\nPort Elizabeth, MN 01874',
},
    'key33280': 'value8500',
    'key31005': 'value33868',
    'key52676': 'value13256',
    'key68313': 'value35302',
    'key53207': 'value47476',
    'key49224': 'value60915',
    'key69244': 'value59501',
    'key21140': 'value16710',
    'key84023': 'value71543',
    'key54569': 'value13747',
},
    {
    'id': 17527487407488,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Kimberly Gillespie',
    'address': '78012 April Causeway Suite 370\nPattonhaven, MO 92945',
    'text': 'Move put prevent do contain. Like figure arm.\nPretty never ten over personal ask key political. Building tax one prepare drop civil push stuff. Option generation issue truth movement society fast.',
    'email': 'mgarcia@example.com',
    'phone_number': '453.908.8353',
    'json': {
    'name': 'Luis Anderson',
    'address': '3860 Stephen Cove\nNorth Brandyhaven, IA 92864',
},
    'key51605': 'value55893',
    'key13183': 'value1181',
    'key76986': 'value64727',
    'key19819': 'value97225',
    'key52387': 'value52246',
},
    {
    'id': 17527487407498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Robert Jones',
    'address': '236 Saunders Throughway\nNorth Julie, LA 75485',
    'text': 'Present hospital character responsibility. Job production policy society.\nBecome nature actually. Feel pass act risk during. Close light office raise break.',
    'email': 'banderson@example.net',
    'phone_number': '978.421.3395',
    'json': {
    'name': 'Dakota Adkins',
    'address': '89216 Moore Squares\nMatthewborough, SC 75819',
},
    'key86787': 'value21949',
    'key20675': 'value54172',
    'key26698': 'value91810',
    'key53268': 'value52864',
    'key64247': 'value30835',
    'key43746': 'value65981',
    'key91533': 'value24154',
    'key91429': 'value53652',
},
    {
    'id': 17527487407509,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Donna Ross',
    'address': '763 Haynes Ford Suite 711\nNew Joshuashire, VI 64598',
    'text': 'Young until population wait author toward. Often another quality visit animal religious really. Enough people itself ask.',
    'email': 'sheriballard@example.net',
    'phone_number': '733.422.1176',
    'json': {
    'name': 'Rodney Curtis',
    'address': '31092 Andrew Shoal Apt. 977\nEast Conniechester, LA 80389',
},
    'key50913': 'value8023',
},
    {
    'id': 17527487407521,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'William Reynolds',
    'address': '5802 Andrew Mountain Apt. 881\nLake Kevin, IL 37977',
    'text': 'Result interest between different blood. Listen guess modern throughout series discuss soldier.\nPrice wide local increase of. Particular one cultural by walk then. House writer stay music.',
    'email': 'wshaw@example.net',
    'phone_number': '425-318-2460x561',
    'json': {
    'name': 'Andrew Gilbert',
    'address': '74988 Taylor Park Apt. 489\nPort Scott, OR 86534',
},
    'key80084': 'value63497',
    'key60293': 'value34386',
    'key41488': 'value97716',
},
    {
    'id': 17527487407531,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Donna Taylor',
    'address': '4042 Bray Park\nPort Markmouth, PR 24763',
    'text': 'Wish collection development chance ever much.\nTelevision along specific test prepare foot. Anyone interesting wish service. Care enter north despite amount.',
    'email': 'susanmiller@example.org',
    'phone_number': '(395)697-4814x875',
    'json': {
    'name': 'Brad Bryant',
    'address': '717 Adam Valleys Apt. 711\nCharlesmouth, AZ 98418',
},
    'key34939': 'value41523',
    'key30670': 'value79811',
    'key93600': 'value77946',
    'key6302': 'value92041',
    'key9087': 'value15130',
    'key78369': 'value79293',
    'key61774': 'value85188',
    'key33428': 'value46289',
    'key14136': 'value75178',
},
    {
    'id': 17527487407543,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Charlotte Martinez',
    'address': '679 Sanders Overpass Apt. 026\nBrownhaven, NE 79376',
    'text': 'Window usually should since force threat chance.\nSense task activity defense. Window much deal war song air medical. Run evening article while increase simple.',
    'email': 'gutierrezjustin@example.org',
    'phone_number': '972.871.4728',
    'json': {
    'name': 'Carla Griffin',
    'address': '14459 Christopher Burgs\nWalkerburgh, DC 62911',
},
    'key78546': 'value6528',
    'key31855': 'value95156',
    'key71193': 'value49502',
    'key62048': 'value35284',
    'key23168': 'value74663',
    'key23642': 'value1295',
    'key64066': 'value31227',
},
    {
    'id': 17527487407555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Sydney Franklin',
    'address': '9223 Flores Springs Suite 928\nPeggyville, NH 68000',
    'text': 'New blood you theory administration opportunity. Relate gas out hospital.\nHope street suddenly. Recognize hundred physical leg pick.\nYoung explain every cost.',
    'email': 'ambercooper@example.net',
    'phone_number': '9206395090',
    'json': {
    'name': 'Jason Perkins',
    'address': '485 Julie Extension\nEast Anthony, DC 75794',
},
    'key76222': 'value17008',
    'key92062': 'value35759',
},
    {
    'id': 17527487407566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Kayla Johnson',
    'address': '8369 Cunningham Ridges\nWest Kimberlyport, MT 36626',
    'text': 'Movement smile degree something others. Seat everything wrong individual woman sense notice.',
    'email': 'katherine27@example.com',
    'phone_number': '941-363-2132',
    'json': {
    'name': 'John Martin',
    'address': '52445 Eddie Ferry\nNorth Jackson, WI 68455',
},
    'key44327': 'value19848',
    'key33245': 'value96837',
    'key34192': 'value43979',
    'key6344': 'value92035',
    'key17132': 'value82573',
    'key93036': 'value22107',
    'key43465': 'value2621',
    'key66927': 'value28620',
    'key91110': 'value63112',
},
    {
    'id': 17527487407576,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Amber Garcia',
    'address': '3856 Erika Drives Suite 369\nSchwartztown, MO 41002',
    'text': 'Citizen already executive reason already contain. Major term trade to.\nDream cold thank fear bit carry bad away. Sort condition nature particular.',
    'email': 'ireed@example.org',
    'phone_number': '+1-396-214-7371x679',
    'json': {
    'name': 'Andrew Rodriguez',
    'address': '058 Cynthia Views\nSouth Erik, NJ 58237',
},
    'key73457': 'value32414',
    'key61822': 'value17055',
    'key81893': 'value6644',
    'key73775': 'value73970',
    'key27140': 'value37759',
    'key73802': 'value14305',
    'key46644': 'value57798',
    'key51588': 'value76983',
},
    {
    'id': 17527487407587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Sheila Allen',
    'address': '8600 Gray Pine Suite 121\nLake Frederick, MN 89634',
    'text': 'American all explain raise central.\nMy Republican send attention ok hospital. Go none citizen tell television.\nSuch send quality sure general culture.',
    'email': 'rachaelbonilla@example.net',
    'phone_number': '+1-407-371-8259x4639',
    'json': {
    'name': 'Michael Meyers',
    'address': '14093 Cody Path\nLake Jennifer, HI 51412',
},
    'key51151': 'value24726',
    'key30079': 'value24717',
    'key56756': 'value58756',
    'key18396': 'value11579',
    'key74625': 'value71446',
    'key6080': 'value45477',
},
    {
    'id': 17527487407599,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Brenda Reed',
    'address': '309 Larsen Burg Suite 377\nBrandontown, UT 43275',
    'text': 'Full know better task so into. Floor and center fine term left account soon. Across red song mention grow girl.',
    'email': 'joseph38@example.net',
    'phone_number': '+1-336-796-2273x976',
    'json': {
    'name': 'Kendra Contreras',
    'address': '7693 Stephanie Common\nSouth Christine, MO 83591',
},
    'key8959': 'value80789',
},
    {
    'id': 17527487407609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Bryan Harris',
    'address': '56273 Todd Village Suite 488\nScottburgh, HI 58856',
    'text': 'Television magazine for along political. Box think personal third thus.',
    'email': 'hrodriguez@example.net',
    'phone_number': '+1-407-212-7751x8957',
    'json': {
    'name': 'Anna Scott',
    'address': '171 Clark Islands\nPort Rileyport, WY 35462',
},
    'key38132': 'value30792',
    'key88386': 'value44439',
    'key75244': 'value66004',
    'key61033': 'value13244',
    'key52070': 'value24065',
    'key29817': 'value35781',
    'key68169': 'value41678',
    'key53688': 'value94185',
    'key52976': 'value20775',
    'key91244': 'value1425',
},
    {
    'id': 17527487407620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Kenneth Welch',
    'address': '008 Debbie Spurs\nMelissastad, KS 22755',
    'text': 'Partner early party page kid if. Management sport college recently. Seat tough recognize.',
    'email': 'jwu@example.net',
    'phone_number': '001-915-576-8602',
    'json': {
    'name': 'Tanner Allen',
    'address': '57776 Rich Brook\nEast Justinton, NM 49128',
},
    'key29401': 'value59451',
    'key45397': 'value62231',
    'key16137': 'value75598',
    'key84733': 'value72535',
    'key78588': 'value42029',
    'key37708': 'value10160',
    'key47664': 'value93987',
    'key23721': 'value17433',
    'key25994': 'value6201',
},
    {
    'id': 17527487407630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Kathleen Gilmore',
    'address': '6960 Shaw Land\nEast Jason, OH 36127',
    'text': 'Set specific style almost. Military despite his game point especially mission. Development here course could peace. Build fine capital fish toward.',
    'email': 'jyoung@example.com',
    'phone_number': '923.249.3268x0781',
    'json': {
    'name': 'Felicia Mcintyre',
    'address': '81247 John Flat\nBarnesbury, AZ 30551',
},
    'key90730': 'value80301',
    'key1061': 'value49040',
    'key52609': 'value82641',
    'key65885': 'value19356',
    'key30653': 'value15565',
    'key69168': 'value65587',
    'key47383': 'value20527',
    'key68038': 'value51510',
    'key84920': 'value68048',
},
    {
    'id': 17527487407641,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Raven Swanson',
    'address': '040 Stanton Cliff\nToddfurt, IA 46421',
    'text': 'Police key of building design. Officer stop of rock management what. Reach civil face bill majority offer.\nLanguage exactly media trip. Relationship western simply.',
    'email': 'ricky06@example.com',
    'phone_number': '(308)234-3246x3419',
    'json': {
    'name': 'Kenneth Wright',
    'address': 'USNS Smith\nFPO AP 39351',
},
    'key62404': 'value8533',
    'key64388': 'value5815',
    'key12672': 'value99112',
    'key76267': 'value85475',
    'key93633': 'value72731',
    'key95816': 'value49',
    'key20935': 'value79987',
    'key73896': 'value78236',
    'key11244': 'value16502',
    'key99897': 'value13716',
},
    {
    'id': 17527487407651,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Brittany Roberts',
    'address': '7362 Brock Greens Suite 372\nHamiltonville, WA 01222',
    'text': 'Whom discuss the popular individual conference still order. Benefit also or example.',
    'email': 'evaughn@example.org',
    'phone_number': '425.748.3782x4587',
    'json': {
    'name': 'Billy Erickson',
    'address': 'USS Carter\nFPO AE 20158',
},
    'key90781': 'value28113',
    'key11634': 'value7503',
    'key65630': 'value40100',
    'key12381': 'value71062',
    'key33993': 'value13007',
    'key37971': 'value22392',
    'key66570': 'value54299',
    'key53105': 'value91605',
    'key94661': 'value81603',
    'key66121': 'value92032',
},
    {
    'id': 17527487407661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Andrea Williams',
    'address': '2296 Richards Mills\nYolandaberg, WA 38622',
    'text': 'Course spend artist together community base certainly beyond. Fact while push.\nDrug town choose hundred ready. Bit should answer whatever deal.',
    'email': 'carrchristopher@example.com',
    'phone_number': '(716)233-1220x35553',
    'json': {
    'name': 'Kevin Hogan',
    'address': '9225 Tamara Streets\nNew Wendyshire, OK 35575',
},
    'key45788': 'value34154',
    'key37219': 'value4939',
    'key5451': 'value65574',
    'key53012': 'value48151',
},
    {
    'id': 17527487407673,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Stephanie Carpenter',
    'address': 'PSC 8815, Box 0594\nAPO AA 42859',
    'text': 'Red grow according attack organization. Front remain notice from big company student. Range husband blood property describe realize billion. Food trial military job south ability.',
    'email': 'christinaforbes@example.org',
    'phone_number': '001-572-750-7875x704',
    'json': {
    'name': 'Jessica Bean',
    'address': '2023 Moss Forest Suite 820\nMullenport, KS 51818',
},
    'key61315': 'value72480',
    'key88840': 'value8569',
    'key77721': 'value22573',
    'key49268': 'value63776',
    'key17589': 'value90272',
    'key7702': 'value97707',
    'key14986': 'value77087',
    'key61345': 'value86075',
},
    {
    'id': 17527487407683,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Justin Clark',
    'address': '7965 Smith Ranch Apt. 259\nAarontown, PA 60443',
    'text': 'This plan soldier half office. That among social indicate assume it. Recent office west fill body.\nSure serious something position bring peace save.',
    'email': 'castillochristina@example.org',
    'phone_number': '001-883-793-5767x2091',
    'json': {
    'name': 'Jason Morales',
    'address': '431 William Pines Suite 382\nNorth Jacqueline, NH 38353',
},
    'key97625': 'value14456',
    'key63356': 'value4830',
    'key74615': 'value26694',
    'key7762': 'value52329',
    'key84880': 'value83499',
    'key24378': 'value76294',
    'key3016': 'value38484',
    'key52654': 'value49464',
},
    {
    'id': 17527487407695,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Brian Jones',
    'address': 'PSC 2587, Box 3704\nAPO AE 71767',
    'text': 'Especially generation follow century weight deep public.\nHimself should three agent leave opportunity. Speech too occur law window. Science suggest describe fish.',
    'email': 'gregorychaney@example.net',
    'phone_number': '884.631.6763',
    'json': {
    'name': 'John Mcclure',
    'address': '00595 Mercedes Track Apt. 484\nValeriefurt, OR 05604',
},
    'key31148': 'value20277',
    'key33716': 'value60365',
    'key15768': 'value668',
    'key67181': 'value11529',
    'key75806': 'value43684',
    'key36991': 'value40130',
    'key34284': 'value87309',
    'key40888': 'value95684',
},
    {
    'id': 17527487407704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Amy Gardner',
    'address': '649 Carter Square\nBondchester, OH 03774',
    'text': 'Risk sit seat usually majority assume choice. East consumer forward range be beautiful. Door her too thing around policy throughout.',
    'email': 'wilkinsonalicia@example.org',
    'phone_number': '855-862-7783x49033',
    'json': {
    'name': 'Michael Lee',
    'address': '65126 Brown Canyon\nStaceyshire, MO 61987',
},
    'key65258': 'value25432',
    'key60231': 'value96274',
    'key28243': 'value43135',
    'key68010': 'value32067',
    'key26091': 'value65420',
    'key69127': 'value9480',
    'key21922': 'value94035',
    'key29266': 'value53357',
    'key66106': 'value88489',
},
    {
    'id': 17527487407715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Barbara Schneider',
    'address': '131 Robert Island Suite 727\nGutierrezfort, KY 52808',
    'text': 'Individual explain grow throw involve trial. Structure social huge. Try play information stuff sell.\nBusiness direction federal herself fire book sea. Time wear office book enough offer student.',
    'email': 'tonya38@example.com',
    'phone_number': '(435)607-3101x211',
    'json': {
    'name': 'Victoria Mckenzie',
    'address': '516 Stein Camp\nSouth Joseph, GU 40599',
},
    'key18696': 'value66969',
    'key1039': 'value81089',
    'key14946': 'value64409',
    'key26358': 'value47637',
    'key11352': 'value95273',
    'key53471': 'value32608',
    'key66520': 'value32993',
    'key84133': 'value8122',
    'key61864': 'value61392',
    'key79124': 'value44913',
},
    {
    'id': 17527487407726,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Lori Foster',
    'address': '2799 Ward Drive\nPort Paulchester, MS 78465',
    'text': 'President adult story very. Information job ball rise assume dinner record resource.\nMachine do player generation. Those whose think staff major recent instead thus.',
    'email': 'ybennett@example.com',
    'phone_number': '360.644.9009',
    'json': {
    'name': 'Kathleen Tyler',
    'address': '0483 Sanchez Gardens Suite 496\nWest Coletown, SD 94686',
},
    'key83905': 'value4195',
    'key77621': 'value63292',
    'key70427': 'value56808',
    'key56918': 'value17134',
    'key25346': 'value97041',
    'key53412': 'value9945',
    'key87346': 'value20453',
    'key11281': 'value74326',
},
    {
    'id': 17527487407737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'John Collins',
    'address': '966 Robert River Suite 206\nChristopherfort, OR 72494',
    'text': 'Me two discover represent food effect style. Improve prove result adult action civil street.',
    'email': 'stevenedwards@example.com',
    'phone_number': '(701)749-6999x3577',
    'json': {
    'name': 'Debra Roberts',
    'address': '5659 Ellen Orchard Apt. 659\nLake Terrenceton, WV 26818',
},
    'key68840': 'value87748',
    'key92718': 'value65197',
    'key73125': 'value92285',
    'key31809': 'value94965',
    'key64207': 'value569',
    'key72314': 'value14476',
},
    {
    'id': 17527487407749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Michael Hanson',
    'address': '8143 Schaefer Springs\nCaseburgh, DE 11760',
    'text': 'National write father family including part ten. Check or each natural leg upon turn.\nCompany open nor character. Environment relationship we program part crime hit.\nGame these their this.',
    'email': 'ppetty@example.net',
    'phone_number': '4296310276',
    'json': {
    'name': 'David Davies',
    'address': '307 Charles Route\nChristianhaven, OR 78118',
},
    'key51786': 'value5181',
},
    {
    'id': 17527487407760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kendra Hall',
    'address': 'USNV Gordon\nFPO AA 16785',
    'text': 'Answer media available century chance. Head all design under. Purpose compare not rate give friend cut technology. Try something opportunity floor enough.',
    'email': 'katherinekane@example.net',
    'phone_number': '001-537-459-3930x416',
    'json': {
    'name': 'Glenn Gill',
    'address': '710 Willie Springs Apt. 267\nHahnmouth, AK 55187',
},
    'key59042': 'value64575',
    'key32541': 'value80188',
    'key73766': 'value64258',
    'key88771': 'value82769',
    'key68871': 'value75448',
    'key19678': 'value41462',
    'key70733': 'value25761',
    'key51491': 'value40655',
    'key79416': 'value66626',
    'key96639': 'value76698',
},
    {
    'id': 17527487407770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Keith Donaldson',
    'address': '741 Brooks Plains\nPort Aaronville, KY 46071',
    'text': 'Fight thank trouble serious also water. Organization back in win serious. Machine live writer management.\nThink meet benefit hard school. Bad agreement scene mouth. Air approach wind production.',
    'email': 'jonathan82@example.org',
    'phone_number': '+1-325-257-0263x137',
    'json': {
    'name': 'Jimmy Arnold',
    'address': '932 Munoz Mountain Suite 115\nMikebury, MI 78968',
},
    'key92548': 'value72002',
    'key45791': 'value41810',
    'key66369': 'value63839',
    'key87622': 'value10346',
    'key22053': 'value49612',
    'key37639': 'value7779',
    'key2350': 'value35761',
    'key42429': 'value88410',
},
    {
    'id': 17527487407781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Heidi Stark',
    'address': '53560 Snyder Prairie Apt. 212\nHernandezport, NE 65156',
    'text': 'Summer rise big exactly science process laugh. Magazine city reduce worry whom.\nThose fly her drive out reality.\nProve include trial room boy range need. Else reach product drive year their.',
    'email': 'angela72@example.com',
    'phone_number': '327-873-1060x6804',
    'json': {
    'name': 'Carlos Smith',
    'address': 'USNS Johnson\nFPO AE 88097',
},
    'key81921': 'value81533',
},
    {
    'id': 17527487407791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Lauren Baker',
    'address': '349 Henry Locks\nTurnershire, MO 08959',
    'text': 'Last person reveal it protect set. Work in throw win we table community. Difficult name building first free seem.',
    'email': 'changdiane@example.net',
    'phone_number': '001-598-658-6147x973',
    'json': {
    'name': 'Carlos Thompson',
    'address': '719 Williamson Keys\nChristophermouth, KS 09077',
},
    'key33356': 'value44646',
},
    {
    'id': 17527487407803,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Jonathan Carter',
    'address': '8984 Garcia Parks Apt. 595\nSouth Adamstad, MP 00552',
    'text': 'Operation almost wind scientist turn program. System many long early them.\nItself information partner radio.',
    'email': 'ndavis@example.org',
    'phone_number': '(437)369-0523x218',
    'json': {
    'name': 'Leah Peters',
    'address': '1368 Robin Ranch Apt. 985\nSharonhaven, WA 40556',
},
    'key76694': 'value10463',
},
    {
    'id': 17527487407814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Kyle Wu',
    'address': 'Unit 9675 Box 8208\nDPO AE 19684',
    'text': 'Mr subject age statement happen.\nAttorney yeah although. Grow assume free material its.\nTake political close computer. Generation left around.',
    'email': 'ucarter@example.com',
    'phone_number': '001-266-570-2132x0016',
    'json': {
    'name': 'Dennis Malone',
    'address': '068 David Stravenue\nLake Jasminechester, AZ 95918',
},
    'key92474': 'value75569',
    'key66548': 'value10360',
},
    {
    'id': 17527487407822,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jacqueline Gonzalez',
    'address': '440 Norman Isle Suite 321\nLake Dennismouth, MS 39165',
    'text': 'Baby crime current stuff wife. Girl total on adult. Seven yeah agency stop heart.\nMouth authority mouth other.\nSuddenly tree light affect free respond. Want million however how daughter continue.',
    'email': 'pgarcia@example.net',
    'phone_number': '656.688.1064x771',
    'json': {
    'name': 'Kathy Morrison',
    'address': 'PSC 2852, Box 7006\nAPO AP 63705',
},
    'key86281': 'value22269',
    'key79110': 'value75050',
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
    'RequestId': '3c96e836-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_54_639409UXgxaMDZ',
    'filter': 'uid > 0',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '3c96e836-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_54_639409UXgxaMDZ',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 01]_1752748747.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid011752748747Json()
    test.run_tests()
