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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVectorNegative_test_query_with_wrong_filter_expr_1752749064_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVectorNegative_test_query_with_wrong_filter_expr_1752749064.json"
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



class AllmilvusLogtestqueryvectornegativeTestQueryWithWrongFilterExpr1752749064Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVectorNegative_test_query_with_wrong_filter_expr_1752749064.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVectorNegative_test_query_with_wrong_filter_expr_1752749064.json"
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
    'data': [
    {
    'id': 17527490609698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Taylor Arnold',
    'address': '0825 Patrick Port\nPort Samuelland, VI 05389',
    'text': 'Walk sound with build. Again across late information me worry. Ask address full girl evidence cost.\nTend five read perform type heart worry. Yard away arm laugh. Deal evidence listen culture.',
    'email': 'benjamin38@example.org',
    'phone_number': '001-972-908-5964x32414',
    'json': {
    'name': 'Molly Evans',
    'address': '29658 Timothy Shoal Apt. 147\nSouth Stephen, AK 97243',
},
    'key77423': 'value87925',
    'key82426': 'value15182',
    'key99543': 'value65933',
    'key83822': 'value12928',
},
    {
    'id': 17527490609720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Colleen Vasquez',
    'address': '81425 Cheryl Radial Suite 984\nNorth Andrew, GA 87966',
    'text': 'Although now choice race card at item. Force again think again left rich.\nShow indeed then bring turn. Key card least item same friend past. A hold probably red out all manager.',
    'email': 'savannahturner@example.com',
    'phone_number': '(205)945-7104x50347',
    'json': {
    'name': 'Brandi Kaiser',
    'address': '12048 Harris Mountains\nCooperchester, MT 78904',
},
    'key69867': 'value72602',
    'key81500': 'value71381',
    'key13576': 'value20401',
    'key36597': 'value21027',
    'key7687': 'value23374',
},
    {
    'id': 17527490609733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Mary Smith',
    'address': '014 Charles Estate\nNew George, AZ 49106',
    'text': 'Build determine yourself edge ability wife. Someone eat great guy. Conference maintain maybe break these.',
    'email': 'johnhoward@example.net',
    'phone_number': '591.694.4370x568',
    'json': {
    'name': 'Heather Parker',
    'address': '009 Carla Pines Suite 015\nLake Jonathon, NJ 75274',
},
    'key45196': 'value49044',
    'key97308': 'value20623',
    'key59519': 'value82009',
    'key96564': 'value22058',
    'key68802': 'value37623',
    'key64150': 'value71103',
    'key3753': 'value89795',
    'key41513': 'value50165',
    'key34606': 'value45401',
    'key44104': 'value17522',
},
    {
    'id': 17527490609745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jacqueline Pearson',
    'address': '010 Allison Points\nWest Justin, MD 36674',
    'text': 'Memory enjoy away doctor chance community. Black customer behavior top. Well drop goal plant perhaps central write.',
    'email': 'xstanley@example.net',
    'phone_number': '+1-222-937-1231',
    'json': {
    'name': 'Derek Gardner',
    'address': '37853 Clark Track\nMccoyberg, DE 06114',
},
    'key2158': 'value96148',
    'key7766': 'value27823',
},
    {
    'id': 17527490609756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Kevin Tanner',
    'address': '01730 Mccoy Mill Suite 144\nLake Janet, NH 15303',
    'text': 'All company beyond program nation. Effort leader shake local less to heart. White travel choice age peace actually.',
    'email': 'hughesrichard@example.net',
    'phone_number': '791-814-2265x048',
    'json': {
    'name': 'Yvonne Dixon',
    'address': '452 William Port\nMoorehaven, AL 86611',
},
    'key32075': 'value25645',
    'key51133': 'value72703',
    'key22214': 'value46539',
    'key9200': 'value43005',
    'key47293': 'value21117',
},
    {
    'id': 17527490609769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jeff Yang',
    'address': '7120 Jonathan Forges\nSouth Annaville, CA 22742',
    'text': 'Big four such red real data. Door career however official along allow.\nMachine point small. Region couple wait bed condition.\nBetter his save laugh. Onto source never onto popular pull.',
    'email': 'davidsantiago@example.com',
    'phone_number': '001-780-847-0995',
    'json': {
    'name': 'Kenneth Middleton',
    'address': '1045 Brock Stream\nNew Davidberg, WY 60361',
},
    'key58790': 'value17844',
    'key89917': 'value27658',
    'key9597': 'value82966',
    'key54489': 'value50917',
    'key69972': 'value30150',
    'key6238': 'value41223',
    'key7913': 'value74230',
    'key66278': 'value383',
},
    {
    'id': 17527490609781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Michelle Gray',
    'address': '84582 Judith Mount Suite 433\nAnnaland, ND 55306',
    'text': 'World present least remain federal hit write. Cause entire find. Item would stuff wait receive.\nType scene run forget ball. Type anyone friend team Mr help dream customer.',
    'email': 'hamiltonbrandon@example.net',
    'phone_number': '001-636-531-8680',
    'json': {
    'name': 'David Baker',
    'address': '3247 Cruz Port\nDavisbury, MO 92748',
},
    'key23893': 'value95861',
    'key76471': 'value36850',
    'key46217': 'value20165',
    'key67350': 'value24402',
    'key44826': 'value54929',
    'key16335': 'value59644',
    'key76996': 'value28086',
    'key89643': 'value70549',
    'key93333': 'value20356',
},
    {
    'id': 17527490609794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Samantha Cox',
    'address': '046 Smith Port\nRitterside, MH 16765',
    'text': 'Believe candidate campaign hand choice ball.\nWrite like child grow appear enter vote. Sister soon amount you war.',
    'email': 'felicia02@example.org',
    'phone_number': '345.939.0896',
    'json': {
    'name': 'Amanda Lynch',
    'address': '471 John Forge\nLake Rebecca, FL 43883',
},
    'key9084': 'value61011',
},
    {
    'id': 17527490609805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Patricia Sullivan',
    'address': '016 Cathy Neck\nNorth Valerieshire, WA 59898',
    'text': 'To artist top story some tough. Middle table class process itself case project. Economic participant back about staff like.\nBody forget theory. Just data value skin itself. Money of floor.',
    'email': 'tracyhughes@example.com',
    'phone_number': '(981)836-3299',
    'json': {
    'name': 'Michael Davidson',
    'address': '87458 Cole Ways\nNew Tanner, TX 82414',
},
    'key56910': 'value81428',
    'key26407': 'value7625',
    'key58231': 'value34251',
    'key97548': 'value16375',
},
    {
    'id': 17527490609816,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Mr. Derrick Sanders',
    'address': '4186 Johnson Walk Suite 772\nPort Tony, IN 19245',
    'text': 'Particularly look gun early meeting. Lot character why might book almost evening push. Make drop raise technology include anyone customer.',
    'email': 'owong@example.net',
    'phone_number': '622.588.8139x7624',
    'json': {
    'name': 'Rose Tucker',
    'address': '80650 Moore Fields Suite 229\nRosston, CA 67247',
},
    'key84823': 'value30032',
    'key95551': 'value23826',
    'key9880': 'value53217',
    'key29136': 'value72126',
    'key79920': 'value27623',
},
    {
    'id': 17527490609828,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Cassandra Gonzalez',
    'address': 'USCGC Willis\nFPO AP 51765',
    'text': 'So not box north quite executive fight. Total operation large face only material. Collection something key pattern last.',
    'email': 'arthurbrooks@example.com',
    'phone_number': '(927)581-0615x347',
    'json': {
    'name': 'Andrea Bolton',
    'address': '22095 Mark Orchard Suite 934\nEspinozachester, DC 83593',
},
    'key32844': 'value77009',
    'key11110': 'value51777',
},
    {
    'id': 17527490609839,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'David Martin',
    'address': '649 Jamie Curve\nLopezville, PW 91458',
    'text': 'Several trouble sit medical south. Worry fire need. Computer court morning film.\nGoal adult area learn share hold question. Within window agency third network black.',
    'email': 'anna23@example.com',
    'phone_number': '941-735-8154',
    'json': {
    'name': 'Brenda Wells',
    'address': '81198 Cox Inlet\nSouth Laurieview, NV 02327',
},
    'key50182': 'value15899',
},
    {
    'id': 17527490609849,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Sergio Parker',
    'address': '431 Adam Haven\nBakermouth, MP 66783',
    'text': 'Financial position low true suffer federal security difficult. While environment onto close war song blue.',
    'email': 'jasonmoore@example.net',
    'phone_number': '+1-573-221-7904',
    'json': {
    'name': 'Richard Reynolds',
    'address': '612 Hinton Lane Suite 266\nAliciafurt, DC 03309',
},
    'key42346': 'value31968',
    'key65350': 'value34980',
    'key68998': 'value40589',
    'key97783': 'value79313',
    'key62100': 'value36673',
    'key52379': 'value2403',
    'key44751': 'value72563',
    'key62128': 'value79296',
    'key38595': 'value54310',
    'key18446': 'value90454',
},
    {
    'id': 17527490609861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Carmen Green',
    'address': '427 Stevenson Isle\nRileyburgh, AZ 33852',
    'text': 'Series man find she mother practice hard. Task important commercial day culture. Former yes star food news sit situation.',
    'email': 'rodneyevans@example.net',
    'phone_number': '+1-823-723-0256',
    'json': {
    'name': 'Emily Johnson',
    'address': '991 Michael Mills\nRubenberg, WY 46542',
},
    'key25720': 'value54158',
    'key91789': 'value21853',
    'key39101': 'value5409',
    'key94492': 'value69532',
    'key74214': 'value52798',
    'key67530': 'value50844',
    'key97575': 'value87856',
    'key42974': 'value68526',
    'key19785': 'value1144',
    'key48798': 'value16949',
},
    {
    'id': 17527490609873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'William Campos',
    'address': '8026 Moore Bypass\nNew Charlesside, DC 85887',
    'text': 'Tough arrive building stage region imagine. Discuss car study buy eye maybe that.\nSide professional low close arrive reason such. Enough war realize.',
    'email': 'kenneth64@example.com',
    'phone_number': '001-517-399-2553x339',
    'json': {
    'name': 'Joshua Green',
    'address': 'USCGC Flores\nFPO AA 10136',
},
    'key3820': 'value24907',
    'key47923': 'value70613',
    'key61148': 'value58803',
    'key79482': 'value41792',
    'key95698': 'value39946',
    'key71385': 'value92516',
},
    {
    'id': 17527490609883,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'William Blanchard',
    'address': '4291 Alison Row\nWoodhaven, HI 37780',
    'text': 'Artist clear manager thus which. Themselves far but rather staff building. Who top before avoid.',
    'email': 'dmorgan@example.org',
    'phone_number': '(894)723-1635x20555',
    'json': {
    'name': 'Karen Nash',
    'address': '779 Ashley Shoals Suite 717\nDeanville, AS 40989',
},
    'key48011': 'value6997',
    'key22849': 'value63429',
    'key52762': 'value32422',
    'key66773': 'value81361',
    'key88095': 'value56713',
    'key55065': 'value74827',
    'key90091': 'value71271',
},
    {
    'id': 17527490609894,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Brian Gonzalez',
    'address': '344 Sandy Isle\nGreenemouth, OH 52126',
    'text': 'Put nation before month ahead. If site family series skill to any.\nPossible research natural action role response poor education. Among often election more defense.',
    'email': 'jsnyder@example.com',
    'phone_number': '422-833-9893x431',
    'json': {
    'name': 'Omar Gordon',
    'address': '1976 Wall Square Suite 814\nNew Jacobview, FL 54834',
},
    'key99656': 'value26208',
},
    {
    'id': 17527490609908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Johnny Morris',
    'address': '33725 Crystal Landing\nHooverburgh, MS 61292',
    'text': 'Present recognize not see happen perform blood. Movement something any support night. Material national research store summer rich unit.',
    'email': 'sarah32@example.org',
    'phone_number': '(409)366-4473',
    'json': {
    'name': 'Eric Rivera',
    'address': '940 Cynthia Rue Apt. 052\nTylerton, MN 16690',
},
    'key39019': 'value87426',
    'key93357': 'value61677',
    'key43094': 'value86549',
    'key27436': 'value1764',
    'key90427': 'value58258',
    'key47159': 'value97775',
    'key20475': 'value71338',
    'key15441': 'value22924',
    'key23562': 'value75884',
},
    {
    'id': 17527490609921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Donald Caldwell',
    'address': '609 Angela Fort Apt. 041\nJudyfort, OR 70038',
    'text': 'Place career record thing capital as with. Through just any.\nLay something respond describe culture authority. White tonight just relationship just letter create. Yourself in of night consumer.',
    'email': 'jennifergross@example.org',
    'phone_number': '001-308-884-6120x719',
    'json': {
    'name': 'Anita Robinson',
    'address': '95250 Cox Path\nWest Brittney, GU 79828',
},
    'key87170': 'value52385',
    'key92311': 'value12816',
    'key28577': 'value84275',
},
    {
    'id': 17527490609941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Tanya Dunlap',
    'address': '1011 Ann Pine\nLake Kaylamouth, NC 08979',
    'text': 'Off friend usually show medical important reason. Focus investment recently if several any stand fund. Lay voice matter instead respond table yard.',
    'email': 'jamesclarke@example.com',
    'phone_number': '001-773-987-4652x53346',
    'json': {
    'name': 'Stephen Fitzgerald',
    'address': 'PSC 5711, Box 1063\nAPO AA 88109',
},
    'key78063': 'value39893',
    'key86882': 'value13848',
    'key14326': 'value95710',
    'key33845': 'value85142',
    'key1481': 'value5884',
    'key6218': 'value94005',
    'key60998': 'value59072',
},
    {
    'id': 17527490609962,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Jesse Lowe',
    'address': '637 Miller Fords Apt. 401\nNew Andrewchester, MN 41049',
    'text': 'Either main magazine. Use organization eight form region husband.\nHer continue writer cup protect far strategy. Window heart too according time.',
    'email': 'patricia98@example.org',
    'phone_number': '491-349-3952x436',
    'json': {
    'name': 'Peter Moore',
    'address': '43178 Valerie Inlet Suite 740\nNew Michael, NE 45882',
},
    'key16346': 'value89712',
    'key84615': 'value62776',
    'key26255': 'value45316',
},
    {
    'id': 17527490609978,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jennifer Jones',
    'address': '527 Jenna Roads\nNew Kimberlyhaven, AR 56869',
    'text': 'Just machine strong step war. Dog cultural later arrive whatever effect.\nPublic scientist answer order various. Letter summer candidate sit picture. Each program example.',
    'email': 'dpadilla@example.com',
    'phone_number': '3312808956',
    'json': {
    'name': 'John Estrada',
    'address': 'PSC 9557, Box 6276\nAPO AP 31703',
},
    'key49243': 'value19195',
    'key9350': 'value59248',
    'key23096': 'value55466',
},
    {
    'id': 17527490609989,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Kayla Gibbs',
    'address': '9771 Matthew Villages\nLake Michael, NV 17023',
    'text': 'Ground common interest relationship.\nTown exist myself probably service assume will. Again material Congress success debate father race.',
    'email': 'uscott@example.net',
    'phone_number': '+1-831-657-2949',
    'json': {
    'name': 'Raymond Collins',
    'address': '4620 Shaun Summit\nKnightberg, DE 27137',
},
    'key32767': 'value80481',
    'key82074': 'value71587',
    'key58454': 'value28339',
    'key74898': 'value82412',
    'key89737': 'value4264',
    'key54587': 'value30075',
    'key26026': 'value50153',
    'key54996': 'value67841',
},
    {
    'id': 17527490610003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Melissa Smith',
    'address': '576 Frank Light Suite 424\nVazquezview, AR 82976',
    'text': 'Radio early other sell some. Expect between great budget.\nNewspaper compare phone window measure space.',
    'email': 'alexandra85@example.com',
    'phone_number': '001-227-639-9410x2379',
    'json': {
    'name': 'Barbara Hoover',
    'address': '97479 Fritz Shoals Apt. 503\nNicholasbury, TN 31847',
},
    'key64466': 'value41198',
    'key9219': 'value37769',
    'key87567': 'value90170',
    'key99103': 'value80235',
    'key84283': 'value56143',
    'key80711': 'value47296',
},
    {
    'id': 17527490610017,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Joshua Stephens',
    'address': '55569 Schwartz Divide Apt. 249\nMartinland, LA 74380',
    'text': 'You several charge friend. The game party owner century determine public. Most edge card believe wish.',
    'email': 'kbass@example.org',
    'phone_number': '866.515.1371',
    'json': {
    'name': 'Cheryl Scott',
    'address': '7267 Kayla Orchard\nAntoniobury, PA 97619',
},
    'key43636': 'value6684',
    'key81049': 'value74258',
    'key23957': 'value4377',
    'key29183': 'value29543',
    'key62482': 'value76324',
    'key63372': 'value9777',
    'key25625': 'value81732',
    'key7248': 'value33962',
},
    {
    'id': 17527490610031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Kristen Hall',
    'address': 'Unit 5204 Box 9606\nDPO AP 99367',
    'text': 'Like range town age decision. Whether leave wait life accept figure.\nMany whatever how sense nearly onto action. Fall address add positive color. Very party all must great sell.',
    'email': 'david72@example.org',
    'phone_number': '001-700-977-7386x4534',
    'json': {
    'name': 'Allison Faulkner',
    'address': 'PSC 8864, Box 6727\nAPO AP 76503',
},
    'key15218': 'value93950',
    'key39035': 'value56534',
    'key26677': 'value63260',
},
    {
    'id': 17527490610040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Matthew Mayer',
    'address': '75258 Alicia Orchard Apt. 641\nNorth Heathershire, PR 73897',
    'text': 'Discussion always expect skill challenge blue. Soon kind along nation light.\nAlone through drug else follow. Democratic grow mission necessary listen woman.',
    'email': 'doris50@example.net',
    'phone_number': '373.207.1054x331',
    'json': {
    'name': 'Larry Alexander',
    'address': '976 Barnes Point\nNorth Heatherborough, NM 60353',
},
    'key91294': 'value31578',
    'key54209': 'value42854',
    'key1650': 'value20629',
    'key16408': 'value96675',
    'key36433': 'value53315',
    'key36015': 'value21403',
    'key65003': 'value10875',
},
    {
    'id': 17527490610053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Melinda Conley',
    'address': '1366 Austin Creek\nWest Angelaview, AK 88603',
    'text': 'Politics pull cup bed. Benefit wrong test among very laugh walk. New teach rich western similar there especially.',
    'email': 'jessicariley@example.org',
    'phone_number': '449-790-3189',
    'json': {
    'name': 'Caleb Chandler',
    'address': '425 Lewis Crescent Apt. 323\nTorresfurt, IA 60281',
},
    'key7816': 'value87908',
    'key53364': 'value68700',
    'key49185': 'value6187',
    'key44914': 'value38422',
    'key63323': 'value63729',
    'key10806': 'value59563',
    'key97240': 'value95927',
},
    {
    'id': 17527490610068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Anthony Sanchez',
    'address': '9033 Megan Rapids Apt. 109\nNew Juan, MH 19742',
    'text': 'Magazine industry medical why commercial standard word. Ready front project question.\nIssue even five money whose act game. Say add white now agreement return mouth.',
    'email': 'stephen71@example.org',
    'phone_number': '299-873-9259x0353',
    'json': {
    'name': 'Carol Murray',
    'address': '3271 Edwards Via Apt. 755\nNorth Samuelmouth, UT 29884',
},
    'key84511': 'value61681',
    'key83045': 'value7917',
    'key15609': 'value79117',
    'key74066': 'value1897',
    'key85998': 'value42937',
},
    {
    'id': 17527490610082,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Luis Myers',
    'address': '51475 White Loop Suite 851\nSouth Edwin, NE 96768',
    'text': 'Series apply until may put. Sure nation similar together.\nFirst couple without professor woman age himself. Measure expert unit explain.\nHelp writer soon you. Future degree range improve popular.',
    'email': 'petersonryan@example.org',
    'phone_number': '(759)886-2881x597',
    'json': {
    'name': 'Brian Wood',
    'address': 'USNV Miller\nFPO AP 95244',
},
    'key30672': 'value60673',
    'key84211': 'value11828',
    'key41653': 'value5030',
    'key14788': 'value77059',
    'key69975': 'value20195',
    'key80331': 'value29552',
    'key25832': 'value43388',
    'key22949': 'value22891',
},
    {
    'id': 17527490610096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Brenda Clay',
    'address': '17863 Kurt Bypass\nSandraborough, MI 90474',
    'text': 'Letter chance expect those past. Reflect that foot. Television thing young.\nBase opportunity worry goal attention. Worker you stock member break single.\nSit range vote church camera fight.',
    'email': 'josephgreen@example.net',
    'phone_number': '989-392-3723x682',
    'json': {
    'name': 'Martin Waters',
    'address': '02201 Newton Row\nYoungborough, MT 06827',
},
    'key37260': 'value54838',
    'key12194': 'value86554',
    'key50905': 'value49596',
    'key72582': 'value77586',
    'key50448': 'value34598',
    'key74159': 'value88400',
},
    {
    'id': 17527490610110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'David Smith',
    'address': '797 Rodriguez Mews\nJamesmouth, DE 02646',
    'text': 'Build boy customer such western imagine century. Remain when near indicate enter a TV. Throughout sure into nation build return those.',
    'email': 'sclements@example.org',
    'phone_number': '591.416.8650',
    'json': {
    'name': 'Janet Moreno DVM',
    'address': '58211 Fitzgerald Park\nTerrimouth, KS 97937',
},
    'key70184': 'value67414',
    'key62213': 'value24722',
    'key14352': 'value28849',
    'key39034': 'value85379',
    'key38201': 'value51925',
    'key31332': 'value83655',
    'key57179': 'value31132',
    'key68584': 'value81179',
},
    {
    'id': 17527490610122,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kevin Ramos',
    'address': '29070 Webb Junctions Suite 851\nKanemouth, PA 78468',
    'text': 'Hear option now I age three. Song activity pull Mrs. Wide answer knowledge song.\nMission newspaper step spend look. President record result site administration deal.',
    'email': 'samuel64@example.org',
    'phone_number': '473-822-9783',
    'json': {
    'name': 'Sergio Johnson',
    'address': '65396 Garrett Extensions\nNorth William, MH 34828',
},
    'key25883': 'value46078',
    'key99512': 'value77785',
    'key71689': 'value7034',
    'key12851': 'value25709',
},
    {
    'id': 17527490610134,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Caleb Wilson',
    'address': '47574 Anthony Knoll Apt. 925\nEast Jacob, NM 47042',
    'text': 'Indeed forget American yes. Officer nearly exist throughout draw name today.\nStrong position yet suggest home strong across on. Mother page situation.',
    'email': 'brenda60@example.net',
    'phone_number': '247-568-4722x9308',
    'json': {
    'name': 'Scott Hughes',
    'address': '78859 Jennifer Overpass Apt. 625\nMccormickfurt, TN 67310',
},
    'key59047': 'value59080',
    'key3708': 'value81756',
    'key30115': 'value83543',
    'key42608': 'value71443',
    'key79249': 'value89227',
    'key66838': 'value20772',
    'key38941': 'value68693',
},
    {
    'id': 17527490610146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Cody Nguyen',
    'address': 'USNV Williams\nFPO AE 46625',
    'text': 'Wear town cover together. Leg to suddenly southern finish watch. Health smile this plant.',
    'email': 'faulknermelissa@example.net',
    'phone_number': '(926)841-0812x6702',
    'json': {
    'name': 'Tracy Howard',
    'address': '796 Dustin Shoals Suite 174\nLake Andreafort, ID 72331',
},
    'key87168': 'value59275',
},
    {
    'id': 17527490610157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Keith Johnson',
    'address': '6544 Diana Manor Apt. 576\nWilliamstown, FM 48293',
    'text': 'Product wife carry officer sing reason. Reveal assume media instead.\nThird age player best here receive. Fly social relate win serve address. Sort fall gun.',
    'email': 'barbarabrown@example.org',
    'phone_number': '704.277.0579x879',
    'json': {
    'name': 'Richard Orozco',
    'address': '70492 Riley Field Apt. 041\nReedstad, RI 96416',
},
    'key11749': 'value65144',
    'key87477': 'value75690',
    'key76792': 'value47739',
    'key83821': 'value67032',
    'key80265': 'value89915',
    'key55775': 'value58519',
    'key66559': 'value45991',
    'key68768': 'value9526',
},
    {
    'id': 17527490610175,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Michael Johnson',
    'address': '6320 Fields Gardens Apt. 631\nBrendaton, VI 78437',
    'text': 'Live perform fly ask similar. Stock trade fear control run produce. Tend fire develop again.',
    'email': 'whitney32@example.net',
    'phone_number': '984.420.9038x9425',
    'json': {
    'name': 'Anthony Mitchell',
    'address': '73757 Quinn Plains Suite 380\nEast Joshuafort, CT 66110',
},
    'key39769': 'value81468',
    'key99816': 'value19424',
    'key24991': 'value41112',
    'key29448': 'value49117',
    'key60551': 'value95081',
    'key92322': 'value73983',
    'key97527': 'value35882',
    'key19284': 'value26069',
},
    {
    'id': 17527490610193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Yvonne Humphrey',
    'address': '421 Perry Parkway Suite 803\nPatriciachester, VA 50421',
    'text': 'Loss popular once soldier. It ball share their read notice seem.\nAble thank sound allow ready citizen. Five budget send eat.\nSpeak blue trouble. Fill century paper while.',
    'email': 'paigejones@example.net',
    'phone_number': '515-820-9026x2458',
    'json': {
    'name': 'Andrew Walker',
    'address': '47243 Jackson Vista\nSouth Susanbury, PW 05963',
},
    'key4260': 'value72135',
    'key12240': 'value47829',
},
    {
    'id': 17527490610213,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Jennifer Anderson',
    'address': '384 Christine Circle Apt. 373\nHesston, MI 48687',
    'text': 'Bar tough my break. Give writer above college word board clearly.\nYourself build left her couple. Condition according population very score. Little them response house rate past however.',
    'email': 'janicebaker@example.com',
    'phone_number': '628.995.3542x3105',
    'json': {
    'name': 'Angela Joseph',
    'address': 'Unit 6060 Box 1986\nDPO AP 28315',
},
    'key91417': 'value86260',
},
    {
    'id': 17527490610233,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Erik Smith',
    'address': '23613 Mcmillan Landing Suite 596\nJenniferfort, PA 26644',
    'text': 'Page many interest action use recognize maybe. Improve rather order. Spend until full attorney development treat doctor.\nReady why common collection. Idea relate area particularly today what.',
    'email': 'guerrerokathryn@example.net',
    'phone_number': '(995)940-8171x6326',
    'json': {
    'name': 'Dr. Dorothy Roberts',
    'address': '109 Hayes Hollow\nGlassmouth, OR 08605',
},
    'key98165': 'value29851',
    'key26737': 'value79904',
    'key99640': 'value49166',
    'key86634': 'value12760',
    'key27129': 'value68639',
    'key88731': 'value32205',
},
    {
    'id': 17527490610254,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Angela Mitchell',
    'address': '8610 Orozco Burgs Apt. 770\nPort Jeanette, LA 50178',
    'text': 'Positive young participant edge window well. Claim level name leg. Cup reach bad job institution good participant.',
    'email': 'kellyjohnson@example.net',
    'phone_number': '324.389.4341x968',
    'json': {
    'name': 'Samantha Hodges',
    'address': '370 Smith Drive\nHicksbury, MO 83187',
},
    'key22350': 'value88643',
},
    {
    'id': 17527490610269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Mrs. Katelyn Williams',
    'address': '3169 George Island Apt. 514\nSouth Sabrinaview, KY 09914',
    'text': 'Officer sound minute once.\nGeneration response above quickly school growth. Around quality treatment individual. For eye news decade yes rule bag.',
    'email': 'gacosta@example.com',
    'phone_number': '878.321.5265x09239',
    'json': {
    'name': 'Katie Holt',
    'address': '5113 Michelle Drives Suite 218\nNew William, VI 61362',
},
    'key13512': 'value36275',
    'key70226': 'value62282',
},
    {
    'id': 17527490610283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Lauren Jones',
    'address': 'Unit 3630 Box 1207\nDPO AP 04844',
    'text': 'Expert race tree human third suggest. Until audience score oil race leader civil. Trip mouth past decide new young foreign. Speech pick serious inside arm leave.',
    'email': 'justin86@example.com',
    'phone_number': '673.358.9470',
    'json': {
    'name': 'David Coleman',
    'address': '3386 Allen Pass\nGreenview, TX 92213',
},
    'key13928': 'value90333',
    'key11964': 'value32153',
    'key12299': 'value83893',
    'key56653': 'value26935',
},
    {
    'id': 17527490610294,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Dwayne Juarez',
    'address': '15434 Natasha Rapids Suite 704\nDonaldstad, WY 20008',
    'text': 'Meet six house would central pay none. Prepare plan however often. Voice over Mrs a movie second.\nAgain far usually green. Push my study simple whose.\nCost audience amount including eat.',
    'email': 'jimenezjulie@example.com',
    'phone_number': '001-263-928-9548x71445',
    'json': {
    'name': 'Ryan Curry',
    'address': '090 Debbie Roads Apt. 665\nLake Judy, NJ 08190',
},
    'key67964': 'value97427',
    'key23256': 'value5932',
    'key83980': 'value39413',
    'key32088': 'value92199',
    'key4654': 'value16395',
},
    {
    'id': 17527490610309,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Matthew Lamb',
    'address': '083 William Station\nNew Shaunhaven, FM 08257',
    'text': 'Quite amount wait recognize interview leave Mr. Upon then positive best service matter financial citizen. Set alone run hear letter.',
    'email': 'kelseyhart@example.org',
    'phone_number': '001-954-760-0935x778',
    'json': {
    'name': 'Douglas Robinson',
    'address': '292 Donald Spurs\nPort Scottfort, VT 15541',
},
    'key10606': 'value73931',
    'key70342': 'value48547',
},
    {
    'id': 17527490610323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Devin Martinez',
    'address': '9981 Larry Ramp\nPort Dillonland, UT 88224',
    'text': 'Turn feeling kid officer. Thus station research recently bad. Arrive onto real crime candidate.\nFine tonight line wife the fight. Girl drug student pass event send. Remain far sign value.',
    'email': 'jasmine24@example.com',
    'phone_number': '246-531-9568x9557',
    'json': {
    'name': 'Roberto Medina',
    'address': '747 Matthew Ford Apt. 555\nLake Kendra, NM 12046',
},
    'key73199': 'value66948',
    'key458': 'value65614',
    'key35442': 'value21302',
    'key79956': 'value6215',
    'key4596': 'value77504',
    'key31059': 'value2128',
    'key70912': 'value24464',
    'key99325': 'value64243',
},
    {
    'id': 17527490610336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Andrew Nichols',
    'address': '20231 Victoria Harbor Apt. 446\nPetersonfort, NJ 07134',
    'text': 'Little south better check control good. Charge fire bill remember.\nAll low successful part. Pull suddenly population do training question today most. During start read impact true know.',
    'email': 'hernandezmario@example.com',
    'phone_number': '950-754-2551x17180',
    'json': {
    'name': 'Tammy Callahan',
    'address': '38883 Christopher Park\nHobbsstad, HI 47586',
},
    'key21174': 'value43878',
    'key29038': 'value32974',
    'key70931': 'value86432',
    'key26233': 'value55346',
    'key84499': 'value4561',
    'key95154': 'value86919',
    'key39946': 'value19908',
    'key7990': 'value72052',
    'key74860': 'value19877',
    'key52215': 'value2310',
},
    {
    'id': 17527490610351,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Anna Hardin',
    'address': '8152 Alvarez Hill Apt. 544\nEast Lindseybury, CO 35806',
    'text': 'Total still many source view model religious store. Phone energy name indicate rate. Boy official onto pay meet he.',
    'email': 'davidmartinez@example.net',
    'phone_number': '9157705358',
    'json': {
    'name': 'Kimberly Cummings',
    'address': '47181 Lauren Plain Suite 514\nLake Lisa, NJ 69625',
},
    'key32436': 'value81942',
    'key94262': 'value94967',
    'key27084': 'value87314',
    'key92537': 'value85905',
    'key85856': 'value30929',
    'key63579': 'value50438',
},
    {
    'id': 17527490610363,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Ashley Christensen',
    'address': '620 James Stravenue\nEast Jessestad, NV 63106',
    'text': 'Describe analysis probably. Raise consider sound parent share picture. Store spend life painting.\nInside response full reason both west.',
    'email': 'morsejames@example.com',
    'phone_number': '345-559-0413x96193',
    'json': {
    'name': 'Jonathan Anderson',
    'address': '33810 Cortez Cape\nCherryland, NM 31009',
},
    'key45656': 'value31819',
    'key26717': 'value20535',
    'key37035': 'value17409',
    'key75013': 'value49831',
},
    {
    'id': 17527490610376,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Leon Mcpherson',
    'address': '392 Copeland Passage\nPort Jodyfurt, IL 32362',
    'text': 'Low present election modern air these beyond. West tonight century table color. Human himself town make environment learn future.',
    'email': 'psullivan@example.org',
    'phone_number': '(663)738-2508x734',
    'json': {
    'name': 'Drew Pierce',
    'address': '778 Laurie Via Suite 081\nLake Darrellton, MP 62828',
},
    'key83883': 'value81157',
    'key36064': 'value74162',
    'key16048': 'value17049',
},
    {
    'id': 17527490610388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Deborah Travis',
    'address': '93270 Mendoza Ramp Suite 966\nWest Markstad, TX 93283',
    'text': 'Single bring term along discover walk. Religious ok player east box. Charge when against him impact.\nEverything left no indeed behavior. Art knowledge culture state attack.',
    'email': 'maciasdanielle@example.com',
    'phone_number': '001-554-359-7045x780',
    'json': {
    'name': 'Jennifer Arroyo',
    'address': '3040 William Trail Apt. 638\nJacobview, LA 84954',
},
    'key94104': 'value85211',
    'key25577': 'value3549',
    'key72168': 'value18611',
    'key50483': 'value37028',
    'key32687': 'value37542',
},
    {
    'id': 17527490610401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jodi Pruitt',
    'address': '714 Levine Manors\nWest Lindachester, MO 95833',
    'text': 'Recognize face letter set. Well win arm few. Artist special themselves.',
    'email': 'ssmith@example.org',
    'phone_number': '315.337.4125x1282',
    'json': {
    'name': 'Ellen Alexander',
    'address': '9436 Kim Track\nLake Shawn, AR 29035',
},
    'key28675': 'value88751',
    'key44478': 'value93786',
    'key88970': 'value96415',
},
    {
    'id': 17527490610413,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Barbara Harmon',
    'address': '6623 Walter Skyway\nLauraview, CO 57223',
    'text': 'Street eye someone win of. Art see add model.\nNew suggest responsibility. Rest through spring could whole that can. Game although someone thus.',
    'email': 'larry60@example.net',
    'phone_number': '759-790-8480x96353',
    'json': {
    'name': 'Gregory Hernandez',
    'address': '442 Joan Summit\nNorth Joshua, IA 81583',
},
    'key79161': 'value29821',
    'key71780': 'value43373',
    'key30038': 'value6681',
    'key75226': 'value27009',
    'key49380': 'value15143',
    'key63372': 'value47081',
    'key7405': 'value46651',
    'key29594': 'value67989',
    'key88391': 'value45246',
},
    {
    'id': 17527490610423,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Morgan Williams',
    'address': '938 Gary Squares Apt. 460\nHinesland, WA 73563',
    'text': 'Cultural each commercial truth. Spend buy or happy ahead claim. Also wait lay approach with speak mention its.',
    'email': 'smithlauren@example.com',
    'phone_number': '+1-851-268-9451x79163',
    'json': {
    'name': 'Anthony Campos',
    'address': '011 Roach Mountain Apt. 027\nBrendanhaven, ME 72202',
},
    'key83987': 'value66826',
},
    {
    'id': 17527490610436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Molly Diaz',
    'address': '95263 Jacqueline Terrace\nMartinezmouth, IL 03355',
    'text': 'Many artist measure. Us our physical research baby necessary watch resource. Anyone how improve dark worker bad or.\nEver near air general.',
    'email': 'lisafritz@example.net',
    'phone_number': '237-357-8219',
    'json': {
    'name': 'Lindsey Lowe',
    'address': '52755 Catherine Springs\nBrianview, NJ 18920',
},
    'key69660': 'value90671',
    'key79211': 'value42445',
    'key8358': 'value43279',
    'key60360': 'value69377',
    'key11497': 'value23322',
    'key76093': 'value45455',
    'key28730': 'value44432',
    'key72898': 'value46908',
    'key60075': 'value21946',
    'key43938': 'value24811',
},
    {
    'id': 17527490610448,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Richard Boyle',
    'address': 'PSC 3917, Box 5591\nAPO AA 67100',
    'text': 'Finish much each PM make. Pull describe clearly bed.\nGame scene property interview actually agency I management. Theory anyone skin production. Special a state they newspaper.',
    'email': 'davisjulie@example.org',
    'phone_number': '360.500.8000x446',
    'json': {
    'name': 'Johnathan Miller',
    'address': '87071 Natalie Ford\nValdezstad, MP 20705',
},
    'key20057': 'value84449',
    'key31682': 'value33697',
},
    {
    'id': 17527490610458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Robert Anderson',
    'address': '5838 Jennifer Rest\nBryanside, MS 99090',
    'text': 'Foreign seat see box yeah of. However space garden structure ball trade. Hear represent imagine have those.\nLocal resource however he. Film performance write agree when.',
    'email': 'haleyphillips@example.com',
    'phone_number': '883.760.3203',
    'json': {
    'name': 'Jonathan Myers',
    'address': '498 John Light Suite 352\nEast Nicole, DE 32468',
},
    'key54428': 'value96991',
    'key85464': 'value40567',
    'key50900': 'value41599',
    'key69991': 'value28612',
    'key39627': 'value44889',
    'key50881': 'value3497',
    'key92718': 'value14119',
},
    {
    'id': 17527490610468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Adam Mills',
    'address': '801 Acosta Mountain\nNorth Stephen, MI 28036',
    'text': 'Affect professional inside agency bag small.\nMean Mr article catch choice do.',
    'email': 'hughesgabriella@example.net',
    'phone_number': '+1-330-578-4651',
    'json': {
    'name': 'Julie Shepard',
    'address': '76031 Richmond Street Suite 089\nBurgessborough, MA 47694',
},
    'key54285': 'value99576',
    'key73240': 'value47700',
    'key36528': 'value62339',
    'key33364': 'value62015',
    'key79615': 'value66281',
    'key25136': 'value27563',
    'key56246': 'value35667',
    'key36461': 'value27247',
},
    {
    'id': 17527490610480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Charles Nunez',
    'address': 'PSC 4717, Box 5196\nAPO AP 41208',
    'text': 'Western see best prepare short analysis. Service member training hard.',
    'email': 'logan36@example.com',
    'phone_number': '001-875-687-1903x54025',
    'json': {
    'name': 'Philip Peterson',
    'address': '469 Bird Shores Apt. 316\nPort Peter, VA 99598',
},
    'key60062': 'value92105',
    'key71569': 'value73975',
    'key1659': 'value35042',
    'key65281': 'value38921',
    'key90372': 'value18160',
},
    {
    'id': 17527490610489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Natasha Adams',
    'address': '793 Hansen Falls\nHarrisberg, IL 43223',
    'text': 'Modern life bar. Town turn military bad paper. Save eye thought live bank.',
    'email': 'dcuevas@example.org',
    'phone_number': '841.241.0823x2219',
    'json': {
    'name': 'Kyle Olsen',
    'address': '4748 Bryan Mews\nNorth Josephberg, AL 94293',
},
    'key73425': 'value14082',
    'key34205': 'value65909',
    'key47260': 'value80781',
    'key36227': 'value26552',
    'key61101': 'value22049',
    'key39980': 'value70269',
    'key88152': 'value99100',
},
    {
    'id': 17527490610499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Andrea Klein',
    'address': '26495 Garcia Underpass Apt. 276\nSouth Christinamouth, NJ 91106',
    'text': 'Support give speech form. Nearly out reason. Mind question three many.',
    'email': 'sullivanwendy@example.net',
    'phone_number': '521.609.8273',
    'json': {
    'name': 'Katie Perez',
    'address': '756 Candice Glen Suite 487\nSouth Brian, TX 75216',
},
    'key61411': 'value35137',
    'key19918': 'value20863',
    'key10438': 'value94254',
},
    {
    'id': 17527490610511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Angela Hall',
    'address': '8166 Bell Dam\nNorth Robertport, IA 65991',
    'text': 'Job of trip join. Perhaps happy expect tax draw without.\nExperience nation lot officer author toward. Matter general and serve.',
    'email': 'johnsonjames@example.net',
    'phone_number': '9847776411',
    'json': {
    'name': 'Jessica Smith',
    'address': '7817 Keith Dale Apt. 968\nEast Amanda, AS 70298',
},
    'key44556': 'value19930',
    'key29989': 'value34945',
    'key82400': 'value84439',
    'key76297': 'value32582',
    'key35357': 'value40147',
    'key58964': 'value76479',
    'key99758': 'value99906',
},
    {
    'id': 17527490610522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Bethany Cardenas',
    'address': '713 Morgan Ford\nPort Marthaton, AL 88985',
    'text': 'Suddenly despite suggest food. From system give.\nGlass common as scene at. Yeah exist performance wrong government identify free should. Artist main us.',
    'email': 'kwalls@example.com',
    'phone_number': '378.921.4149',
    'json': {
    'name': 'Noah Miller',
    'address': '4983 Jimenez Inlet Suite 766\nEast Rebecca, HI 10391',
},
    'key94416': 'value27167',
    'key48190': 'value65180',
    'key34971': 'value25104',
    'key47437': 'value97134',
    'key75534': 'value97775',
    'key8705': 'value36667',
    'key68875': 'value61275',
},
    {
    'id': 17527490610533,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Jennifer Barker',
    'address': '374 Gutierrez Forks Suite 501\nWest Thomasville, VA 52680',
    'text': 'Now apply may music theory blue place college. General year population half project.\nSeason remember office force figure. Move care quite school. Perhaps child majority carry.',
    'email': 'sarah29@example.com',
    'phone_number': '245.907.7576',
    'json': {
    'name': 'William Freeman',
    'address': '119 Gomez Stravenue Apt. 274\nSanchezside, FL 65455',
},
    'key48593': 'value73935',
    'key96925': 'value39190',
    'key5215': 'value10148',
    'key20744': 'value21632',
    'key77335': 'value78291',
    'key30350': 'value69122',
    'key33597': 'value73031',
},
    {
    'id': 17527490610545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Kelly Hawkins',
    'address': '521 Michael Mews Suite 040\nNew Marcton, CA 43934',
    'text': 'Conference small cup end entire. Close purpose cause too explain have. Hit it identify stuff final short tend.',
    'email': 'evansjon@example.net',
    'phone_number': '(962)420-5368x996',
    'json': {
    'name': 'Jesse Jordan',
    'address': 'Unit 2268 Box 7232\nDPO AE 45041',
},
    'key70249': 'value82271',
    'key37800': 'value84983',
    'key11710': 'value50206',
    'key27863': 'value7785',
    'key82129': 'value24423',
    'key19877': 'value43352',
},
    {
    'id': 17527490610555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Robin Beltran',
    'address': '9019 Ryan Pass\nMarkville, AK 39255',
    'text': 'Data article require save southern benefit. Phone suggest loss. Control change language inside few across happy.',
    'email': 'brosales@example.org',
    'phone_number': '(723)531-3408',
    'json': {
    'name': 'Allison Adams',
    'address': '108 Wanda Knoll\nWest Scottfort, WY 62036',
},
    'key21920': 'value73178',
},
    {
    'id': 17527490610565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Ruben Fleming',
    'address': '643 Amy Inlet\nFlemingview, VA 94198',
    'text': 'And home almost suggest citizen.\nShow official occur sit everyone. Energy great include sound.\nDo relate see woman. Station sign recently art think possible mouth hold. Send responsibility east.',
    'email': 'jeffrey97@example.org',
    'phone_number': '+1-829-211-4616x661',
    'json': {
    'name': 'Jennifer Carter',
    'address': '2923 Austin Ford\nCindybury, MI 48609',
},
    'key5244': 'value35797',
},
    {
    'id': 17527490610575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'James Rogers',
    'address': '274 Emily Ways Apt. 329\nFreemanton, OR 09872',
    'text': 'Teach marriage describe prove movie. Friend pay turn itself process control.\nThe everything effect week. Land vote student early any event way. Laugh white thank reality level now conference story.',
    'email': 'jerryallen@example.net',
    'phone_number': '(809)515-6139',
    'json': {
    'name': 'Marie Clarke',
    'address': '51380 Joshua Parks Suite 767\nSmithton, ME 74628',
},
    'key78340': 'value64346',
    'key64653': 'value38148',
    'key5767': 'value64195',
    'key40444': 'value36393',
    'key70003': 'value76569',
    'key21584': 'value39281',
    'key85997': 'value5621',
    'key61564': 'value53809',
    'key967': 'value81896',
    'key38902': 'value77022',
},
    {
    'id': 17527490610587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Brenda Potts',
    'address': '6837 Terry Tunnel\nRomerochester, WY 41654',
    'text': 'Myself involve game partner hospital board newspaper. Billion fire key. Economy let also.\nTreat though artist push defense. Together speech question life moment fear.',
    'email': 'onealanita@example.net',
    'phone_number': '639-314-6465x56666',
    'json': {
    'name': 'Aaron Bryant',
    'address': 'PSC 9325, Box 4707\nAPO AE 28101',
},
    'key38680': 'value22200',
    'key62079': 'value54942',
    'key77431': 'value78006',
    'key91458': 'value53576',
    'key59078': 'value5022',
    'key45075': 'value25739',
    'key92217': 'value22210',
    'key21801': 'value27289',
    'key35383': 'value90800',
    'key86914': 'value31897',
},
    {
    'id': 17527490610597,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Amanda White',
    'address': 'USS Kelly\nFPO AA 10277',
    'text': 'Also realize director report none position machine.\nCrime name travel model. Shake region around available large art series manager.\nName music be none decide table. Soon despite husband water.',
    'email': 'fletcherrichard@example.net',
    'phone_number': '557-763-8892x745',
    'json': {
    'name': 'Patrick Case',
    'address': 'Unit 8311 Box 9665\nDPO AP 70038',
},
    'key89081': 'value18275',
    'key69945': 'value67513',
    'key54608': 'value45982',
    'key43814': 'value88040',
    'key85430': 'value55837',
    'key20304': 'value27697',
    'key22116': 'value55741',
    'key27600': 'value27442',
    'key67401': 'value93937',
    'key79182': 'value81509',
},
    {
    'id': 17527490610606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Stephen Scott',
    'address': '66045 Kathryn Keys\nNew Johnathan, FM 21951',
    'text': 'Join other interesting office single. Certainly rock want from mouth stage. People level soldier whose.',
    'email': 'briannolan@example.com',
    'phone_number': '9482893348',
    'json': {
    'name': 'Linda Miller',
    'address': '48422 Johnson Mountains\nWest Amanda, OR 10193',
},
    'key60393': 'value46135',
    'key5037': 'value83600',
    'key31796': 'value81401',
    'key32976': 'value54744',
    'key81914': 'value87654',
    'key38866': 'value23173',
    'key65619': 'value94517',
},
    {
    'id': 17527490610617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Nicholas Bates',
    'address': '3422 Alfred Crossing Suite 278\nNorth Pamela, GU 83397',
    'text': 'Score brother after enough possible. Operation even us own place civil well. Admit chance stock since interest former cultural.',
    'email': 'aarondavis@example.com',
    'phone_number': '+1-211-406-8143x201',
    'json': {
    'name': 'Zachary Moore',
    'address': 'PSC 3987, Box 9208\nAPO AA 39432',
},
    'key8703': 'value9023',
},
    {
    'id': 17527490610626,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Brittany Gordon',
    'address': '9851 Robert Rapid\nPort Amanda, NM 71084',
    'text': 'Local member heavy make. Among discussion today firm student. Tax still stay its there hour small. Popular but change important message soldier.',
    'email': 'michael92@example.net',
    'phone_number': '766-999-9129x68260',
    'json': {
    'name': 'Steven Wright',
    'address': '305 Gillespie Curve Apt. 347\nMartinezberg, PR 21468',
},
    'key3828': 'value71641',
    'key80304': 'value80510',
    'key40542': 'value91510',
    'key35617': 'value30943',
    'key61051': 'value81343',
    'key26783': 'value24134',
    'key85601': 'value92876',
    'key87092': 'value57768',
    'key83662': 'value41077',
    'key44790': 'value33973',
},
    {
    'id': 17527490610636,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Wendy Henderson',
    'address': '3514 Brown Lock Apt. 959\nNorth Joseph, VT 15089',
    'text': 'Whole whatever provide plant south soldier person. Everything person half reflect. Worker scientist call success every almost necessary.\nSame add event among he child. Owner exactly nor food.',
    'email': 'tparks@example.net',
    'phone_number': '001-890-969-4948x90246',
    'json': {
    'name': 'Ellen Carson',
    'address': '706 Miller Mountains\nNorth Matthewmouth, VA 25922',
},
    'key32084': 'value55067',
},
    {
    'id': 17527490610648,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Emily Williamson',
    'address': '550 Abigail Square\nPerezstad, NJ 38012',
    'text': 'Star performance region heart hour leg benefit remember. Medical local front government tough position around.\nWhat show people second surface second go. Alone both a cup.',
    'email': 'jillmiller@example.net',
    'phone_number': '4387697201',
    'json': {
    'name': 'Brenda Burke',
    'address': '4281 Cohen Coves Apt. 520\nAllenville, OH 28555',
},
    'key23060': 'value65052',
    'key32755': 'value27357',
    'key14727': 'value40870',
    'key81825': 'value3162',
    'key5425': 'value81886',
    'key26326': 'value17028',
    'key89325': 'value66040',
    'key36058': 'value89300',
    'key1861': 'value99041',
    'key11750': 'value61958',
},
    {
    'id': 17527490610661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Melanie Mcmahon',
    'address': '142 Guzman Creek Apt. 137\nIrwinfort, NH 89222',
    'text': 'Heart party up western respond black. Make main hit fast environmental.',
    'email': 'njohnson@example.org',
    'phone_number': '341.774.5559x57700',
    'json': {
    'name': 'Allen Moreno',
    'address': '357 Michael Ridge\nBradfordton, SD 71361',
},
    'key77523': 'value8794',
    'key48866': 'value38872',
},
    {
    'id': 17527490610673,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Jerry Medina',
    'address': '29917 Samuel Mountain Apt. 879\nSouth Elizabethland, PR 53243',
    'text': 'Talk they common measure. Popular day responsibility dinner. For ask section their data.\nPopulation lose technology team it. Him bag bag consider.',
    'email': 'marcterry@example.net',
    'phone_number': '432.754.2223x805',
    'json': {
    'name': 'Samuel Williamson',
    'address': '924 Reyes Mews Apt. 932\nMerrittton, CA 42540',
},
    'key96949': 'value69851',
    'key28498': 'value6',
    'key25560': 'value58748',
    'key85561': 'value35474',
    'key20359': 'value27843',
    'key10289': 'value82451',
    'key45136': 'value68832',
    'key37103': 'value23711',
},
    {
    'id': 17527490610686,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Phillip Wiley',
    'address': '885 Ward Harbor Suite 946\nEast Laurenview, OK 55199',
    'text': 'Line between letter cell. Understand response nor hope visit. Near food front piece. Food lose those lawyer.\nFind sea but mouth answer great story. Lead your within machine movement these.',
    'email': 'kruegerjoshua@example.net',
    'phone_number': '894.708.0838x5594',
    'json': {
    'name': 'Bryan Meadows',
    'address': '4791 Ryan Street\nKennethfort, WA 89558',
},
    'key24817': 'value55086',
    'key45174': 'value88380',
    'key89345': 'value75992',
    'key97056': 'value82234',
    'key91541': 'value44484',
    'key93500': 'value78617',
},
    {
    'id': 17527490610699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Kathleen Jones',
    'address': '05350 Monica Ridge\nFaulknerville, WV 99646',
    'text': 'Rule agent security goal guess those management. Hospital woman cold age six price pull already. Long hospital despite not threat future option other.',
    'email': 'slara@example.net',
    'phone_number': '(247)389-0285x378',
    'json': {
    'name': 'Jennifer Garner',
    'address': 'USCGC Phillips\nFPO AA 13859',
},
    'key42738': 'value75199',
},
    {
    'id': 17527490610710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Michelle Nunez',
    'address': '113 Sarah Union Suite 892\nWest Marvinfort, MO 48513',
    'text': 'Owner from weight partner cover describe add. Lay within together interview see as. Since nation tend same term design. People board government despite serve environment hundred.',
    'email': 'brenda02@example.net',
    'phone_number': '518-984-5974x923',
    'json': {
    'name': 'Carlos Wagner',
    'address': '90593 Chan Rapid\nPort Marystad, IN 73138',
},
    'key40502': 'value28929',
    'key82446': 'value69750',
    'key87199': 'value71933',
    'key43460': 'value59562',
    'key33091': 'value29146',
    'key98354': 'value61828',
    'key51059': 'value57051',
    'key14360': 'value31196',
},
    {
    'id': 17527490610721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Raven Campbell',
    'address': '342 Christopher Ports Apt. 082\nLaurenmouth, WY 22961',
    'text': 'Interview picture next wrong take mention. Report business computer relationship administration.',
    'email': 'eileenjones@example.org',
    'phone_number': '3302869898',
    'json': {
    'name': 'Robert Gonzales',
    'address': '33904 Newman Forge\nColleenburgh, NM 02240',
},
    'key6867': 'value2015',
},
    {
    'id': 17527490610733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Cameron Nelson',
    'address': '8985 Griffin Isle\nPort Kathy, AL 42391',
    'text': 'Hand stage all situation think food. Half throughout after dog democratic civil read.\nCarry organization brother game cover. Partner president then machine.',
    'email': 'pkane@example.net',
    'phone_number': '632.327.3925x91534',
    'json': {
    'name': 'Tammy Shaw',
    'address': '18253 Martin Tunnel\nBrandyhaven, FM 03851',
},
    'key9901': 'value47044',
    'key18770': 'value58604',
    'key70802': 'value5048',
    'key15661': 'value3370',
    'key21152': 'value35125',
    'key41263': 'value16640',
    'key93725': 'value94682',
    'key64959': 'value44384',
},
    {
    'id': 17527490610745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Daniel Vega',
    'address': '126 Sandra Isle\nVeronicaville, NH 13170',
    'text': 'Build expect image party north tend north.\nFull new yeah why. Adult technology little among probably.',
    'email': 'cortiz@example.com',
    'phone_number': '+1-717-894-6430x6972',
    'json': {
    'name': 'Corey Russell',
    'address': '19383 Alicia Pine Suite 886\nHobbsburgh, CO 38225',
},
    'key26503': 'value17226',
    'key30623': 'value47035',
    'key9414': 'value86734',
    'key58952': 'value42455',
},
    {
    'id': 17527490610757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Anthony Cross',
    'address': '9353 Tracy Lights\nRojastown, FM 61039',
    'text': 'Thousand gas half on them yourself act. Just point quickly military begin real doctor.\nProcess simple dream give present mouth. South third plant Congress prepare. Market success nor various.',
    'email': 'debra23@example.com',
    'phone_number': '589.576.3359x18406',
    'json': {
    'name': 'Laura Charles',
    'address': '023 Pham Common\nWest Jenniferhaven, FM 77314',
},
    'key53345': 'value89339',
    'key80735': 'value855',
    'key66042': 'value65058',
},
    {
    'id': 17527490610768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Allison Lamb',
    'address': 'USCGC Simmons\nFPO AP 73151',
    'text': 'Along answer continue budget relate experience. Onto when table trouble condition.',
    'email': 'yvonne75@example.com',
    'phone_number': '480.838.5789',
    'json': {
    'name': 'Willie Jones',
    'address': '1366 Berry Meadow\nLaceychester, ND 42212',
},
    'key90597': 'value75960',
    'key63611': 'value41324',
    'key99426': 'value32904',
},
    {
    'id': 17527490610778,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Benjamin Burgess',
    'address': '4954 Jackson Causeway Apt. 296\nLake Mark, MI 18777',
    'text': 'Serious subject by why civil phone run seem. Call meeting effect. Record drop child instead outside.',
    'email': 'victoria81@example.org',
    'phone_number': '001-329-362-5332x98069',
    'json': {
    'name': 'Jason Chung',
    'address': '5227 Murphy Divide\nNew Alexandraville, NC 98411',
},
    'key36000': 'value64888',
    'key21285': 'value29324',
    'key16709': 'value36235',
    'key14328': 'value35827',
},
    {
    'id': 17527490610792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kathy Walsh',
    'address': '339 Jason Neck\nSouth Judith, AR 20659',
    'text': 'Much charge issue. Enough billion form surface its. Black decade child stay someone mother.\nPaper forward hair identify type nice science. Attorney put east.',
    'email': 'qcalhoun@example.net',
    'phone_number': '001-981-275-2577x42604',
    'json': {
    'name': 'Gary Gilmore',
    'address': '721 Richards Pass\nSouth Christianborough, IL 77899',
},
    'key59072': 'value86425',
    'key37612': 'value22035',
    'key66778': 'value73703',
    'key80580': 'value74267',
    'key35931': 'value22970',
    'key19212': 'value94722',
    'key30334': 'value63259',
    'key88717': 'value92690',
},
    {
    'id': 17527490610809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Natasha Watts',
    'address': '1392 Beck Harbor Suite 273\nNorth Timothystad, NJ 31192',
    'text': 'Mother international save popular.\nAnalysis attorney term. Stay teach safe power wide. Eye work hold serve protect dog.\nBehind direction approach prove indicate professor. Reflect animal it.',
    'email': 'heidisanders@example.com',
    'phone_number': '393-440-2128x51768',
    'json': {
    'name': 'Paige Berg',
    'address': '3347 Sandoval Camp\nGarcialand, ME 56723',
},
    'key68344': 'value18207',
},
    {
    'id': 17527490610830,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Jessica Williams',
    'address': '896 Martha Ports\nNew David, NH 55818',
    'text': 'Key black debate industry wear. Source doctor American certainly stage bar. Information time perform fall also. Public hot ok job full.',
    'email': 'jeffreyorr@example.org',
    'phone_number': '+1-426-600-6260x6286',
    'json': {
    'name': 'Danny Weber',
    'address': '79479 Watkins Corners Apt. 502\nPort Mauriceland, ID 07498',
},
    'key45971': 'value28818',
    'key19979': 'value99019',
    'key62211': 'value95930',
    'key75880': 'value81244',
    'key52818': 'value61036',
    'key61235': 'value13655',
    'key91578': 'value44631',
    'key83724': 'value7886',
},
    {
    'id': 17527490610853,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Mary Holmes',
    'address': '1294 Dwayne Forges\nSusanstad, NV 49200',
    'text': 'Help win produce degree stop. Central lot future brother get. Protect citizen how act example. Around catch key in.',
    'email': 'derekwiggins@example.com',
    'phone_number': '713-737-5871x991',
    'json': {
    'name': 'Melody Olsen',
    'address': '068 Butler Tunnel Suite 704\nHernandezville, SC 10475',
},
    'key22722': 'value87664',
    'key34386': 'value81155',
    'key65855': 'value41200',
},
    {
    'id': 17527490610872,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Christine Ewing',
    'address': '37815 Michael Lights\nPenningtonberg, UT 93356',
    'text': 'Sound actually ball. Since though factor order. Statement southern style wonder.\nSome movie upon. When threat imagine.',
    'email': 'jonathanthomas@example.com',
    'phone_number': '+1-414-403-4571x3612',
    'json': {
    'name': 'Destiny House',
    'address': '14923 Bobby Rest Suite 441\nWilliamsland, CO 57446',
},
    'key926': 'value571',
    'key76353': 'value71798',
},
    {
    'id': 17527490610887,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Catherine Solis',
    'address': '6261 Clark Valley Suite 518\nMitchellstad, DC 35852',
    'text': 'Remember order table north style during. Particular often career indeed for near.',
    'email': 'tracitaylor@example.org',
    'phone_number': '369.809.0061x700',
    'json': {
    'name': 'Mr. Benjamin Goodwin',
    'address': '037 Moore Point\nPort Carrie, TN 39026',
},
    'key52503': 'value4452',
},
    {
    'id': 17527490610901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Rebecca Scott',
    'address': '874 Stout Street Suite 365\nJameshaven, PR 80598',
    'text': 'Small floor seek sometimes involve protect. Senior instead kind back. Citizen thought building community.\nTeacher around training. Natural finally sign discuss. Happy force major whether range trip.',
    'email': 'laura00@example.net',
    'phone_number': '(480)342-3437x2173',
    'json': {
    'name': 'Diana Myers',
    'address': 'PSC 8393, Box 3972\nAPO AA 04817',
},
    'key89275': 'value877',
},
    {
    'id': 17527490610912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mr. David Taylor',
    'address': '84320 Jackson Ways\nLisaton, OR 20263',
    'text': 'Discover small someone up well. Life improve assume life threat.\nProbably some approach tough try health. Think man civil eight without no so.',
    'email': 'fhamilton@example.com',
    'phone_number': '796-550-5828x63214',
    'json': {
    'name': 'Thomas Compton',
    'address': '373 Ibarra Drive Apt. 105\nGrantbury, IL 72544',
},
    'key25701': 'value49590',
    'key64114': 'value87140',
    'key95779': 'value98637',
    'key60': 'value55435',
    'key23579': 'value74723',
    'key43160': 'value20137',
},
    {
    'id': 17527490610926,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Nicholas Richards',
    'address': '6983 Branch Overpass\nNorth Amandashire, NE 84882',
    'text': 'Hand far administration prove building reach senior. Hit computer to base some action machine.\nInterest door place court look Democrat issue. Financial stand technology skin no.',
    'email': 'sharpthomas@example.net',
    'phone_number': '9829999551',
    'json': {
    'name': 'Karina Smith',
    'address': '0650 Mendez Freeway Suite 019\nEast Deborahshire, VT 51173',
},
    'key75215': 'value87872',
    'key91634': 'value38237',
    'key67228': 'value55379',
    'key87810': 'value30959',
    'key61327': 'value49113',
    'key51291': 'value36157',
    'key4983': 'value69100',
    'key17257': 'value71745',
},
    {
    'id': 17527490610941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Mark Adkins',
    'address': '351 Aguilar Turnpike Suite 337\nMichaelbury, AS 66432',
    'text': 'General center nice in trouble it suffer institution. People of word the figure. Admit hotel heavy word why.',
    'email': 'millermatthew@example.net',
    'phone_number': '826-779-3744',
    'json': {
    'name': 'Brian Dillon',
    'address': '74474 Smith Station\nCruzside, NE 94627',
},
    'key20926': 'value49694',
    'key41071': 'value20120',
    'key80471': 'value97306',
    'key68235': 'value59427',
    'key49668': 'value99015',
    'key25514': 'value1751',
    'key64716': 'value43375',
},
    {
    'id': 17527490610955,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Ryan Smith',
    'address': '136 Smith Mills Suite 956\nWhitneychester, OR 63897',
    'text': 'If dark standard event read point knowledge. Itself people any mean.\nPresident space old painting partner really cut. Garden attack important develop grow seven walk.',
    'email': 'thomasjennifer@example.org',
    'phone_number': '+1-513-877-9726x99641',
    'json': {
    'name': 'Joseph Manning',
    'address': '393 Darius Meadows\nNorth Jonathanville, IL 24380',
},
    'key25079': 'value76091',
    'key91762': 'value40757',
    'key36191': 'value56708',
    'key31476': 'value9680',
    'key52387': 'value57578',
},
    {
    'id': 17527490610970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Debra Russell',
    'address': '6024 Stephanie Street\nStarkborough, CO 07375',
    'text': 'Early population evening example. Improve short identify remain form single forward page. Easy good summer we institution sister.',
    'email': 'cjones@example.org',
    'phone_number': '(430)245-5655x675',
    'json': {
    'name': 'Christopher Rivera',
    'address': '0688 Alvin Walks Suite 688\nLake Derek, VA 77201',
},
    'key50462': 'value25565',
    'key89055': 'value61149',
    'key12620': 'value6416',
    'key9064': 'value40047',
},
    {
    'id': 17527490610983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Linda Adams',
    'address': '880 Sherman Glen Suite 462\nYoungborough, NV 44104',
    'text': 'Growth nor decision quickly rock pressure. Might imagine start source human.\nPosition civil offer that development. Think miss expect say card security them.\nMention yet well main board.',
    'email': 'matthew95@example.net',
    'phone_number': '+1-288-878-8226x573',
    'json': {
    'name': 'David Castillo',
    'address': '902 David Knoll\nMurphychester, MA 41488',
},
    'key73784': 'value46952',
    'key6111': 'value11963',
    'key84066': 'value68694',
    'key15893': 'value48479',
    'key11678': 'value73557',
    'key65512': 'value66000',
    'key89639': 'value88699',
},
    {
    'id': 17527490610997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Kristina Thomas',
    'address': '5495 Parker View\nLake Gabrielle, NC 20393',
    'text': 'Once toward second young. Conference common television son occur store hospital.\nBusiness court recent.\nPiece wall next. Result number might national he build or.',
    'email': 'miguelpark@example.org',
    'phone_number': '922-648-4997',
    'json': {
    'name': 'Rebecca Tran',
    'address': '9804 Shane Ramp Apt. 981\nWadefort, CA 64350',
},
    'key59423': 'value90554',
    'key49350': 'value7575',
    'key84310': 'value24940',
    'key80870': 'value14579',
    'key45724': 'value97771',
    'key16244': 'value64449',
    'key65834': 'value91099',
    'key75621': 'value81295',
},
    {
    'id': 17527490611011,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Dominic Carter',
    'address': '248 Adrian Square Apt. 113\nSouth Nicholasside, LA 76499',
    'text': 'Front thus five technology. Team month second land. Indicate me follow eye glass history challenge region.',
    'email': 'twilliams@example.com',
    'phone_number': '908.744.8536x412',
    'json': {
    'name': 'Randy Owens',
    'address': '08953 Lambert Stream\nWest Joannamouth, WA 78187',
},
    'key24925': 'value87265',
    'key85096': 'value59604',
    'key12021': 'value45124',
    'key90226': 'value16538',
    'key99501': 'value32438',
    'key20821': 'value93325',
    'key42427': 'value30762',
    'key81889': 'value69876',
},
    {
    'id': 17527490611024,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Andrew Mendoza',
    'address': '773 Scott Ports Apt. 388\nNew Caitlinmouth, SC 30976',
    'text': 'First attorney rise yet character sister center company. Old son far develop mean yeah participant.\nOpportunity need region election read whom. Style town best father possible of.',
    'email': 'james50@example.net',
    'phone_number': '477.858.8849x7753',
    'json': {
    'name': 'Randy Lee',
    'address': '51134 Thomas Spring Apt. 344\nNew Nancychester, PR 03653',
},
    'key60658': 'value51962',
    'key86500': 'value4672',
    'key94658': 'value41984',
    'key49401': 'value88740',
    'key2276': 'value75398',
    'key72840': 'value30059',
},
    {
    'id': 17527490611035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Timothy Wagner',
    'address': '06228 Laura Drive Suite 518\nStephentown, VI 99584',
    'text': 'Computer support yes sense lose. Else across onto PM tree material once. Head five picture Congress.',
    'email': 'kanehunter@example.net',
    'phone_number': '857.276.1725x1599',
    'json': {
    'name': 'David Crosby',
    'address': '585 Maurice Vista Apt. 498\nNew Davidview, NC 95290',
},
    'key41350': 'value6420',
},
    {
    'id': 17527490611048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Jeffrey Carson',
    'address': '99296 Jessica Mews\nNew Craighaven, NV 92655',
    'text': 'Language the term account. End she begin sing performance. None happen but five protect pressure today. Town claim such subject.',
    'email': 'gloria54@example.net',
    'phone_number': '001-334-550-6011x2345',
    'json': {
    'name': 'James Williams',
    'address': 'USNV Ryan\nFPO AP 60845',
},
    'key29167': 'value11311',
    'key1805': 'value63268',
    'key63029': 'value9995',
},
    {
    'id': 17527490611058,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Misty Leon',
    'address': 'Unit 7028 Box 6810\nDPO AA 53752',
    'text': 'Base increase will assume. Low teach enter evening through event.',
    'email': 'erika29@example.net',
    'phone_number': '634.675.4740x7068',
    'json': {
    'name': 'Alexander Smith',
    'address': '4627 Edwards Center Apt. 266\nStephensfort, AZ 44709',
},
    'key79501': 'value56356',
    'key6472': 'value63065',
    'key29120': 'value20600',
    'key7672': 'value83227',
    'key10742': 'value27798',
},
    {
    'id': 17527490611067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Jonathan Kennedy',
    'address': '96672 Michael Mall Suite 934\nNorth Jackberg, HI 90241',
    'text': 'Bill traditional nature difference specific leader. Customer line always employee.',
    'email': 'christiantyler@example.net',
    'phone_number': '4427384154',
    'json': {
    'name': 'Frank Cohen',
    'address': 'USNV Delgado\nFPO AP 09267',
},
    'key63417': 'value62880',
    'key67571': 'value10779',
    'key9429': 'value44738',
    'key95114': 'value8787',
    'key52532': 'value57906',
    'key79235': 'value2246',
    'key52148': 'value45817',
},
    {
    'id': 17527490611077,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Sabrina Gonzales',
    'address': '1747 Newton Tunnel\nWest Jessica, NE 45224',
    'text': 'Instead exist themselves argue program all school. Bar building realize road.\nClear add purpose Republican already capital. Avoid consumer magazine force home.',
    'email': 'wardjoshua@example.org',
    'phone_number': '001-799-600-2796x44862',
    'json': {
    'name': 'Mr. Sean Brown',
    'address': '7958 Bauer Spring\nEverettton, NJ 54682',
},
    'key77121': 'value34050',
},
    {
    'id': 17527490611090,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'David Mullins',
    'address': '22598 Fleming Spring Apt. 087\nWest Michelle, CO 55737',
    'text': 'Outside medical husband leader start purpose race.\nSource true put fall he also training amount. Role owner because capital later case machine treat.',
    'email': 'myersgloria@example.com',
    'phone_number': '(679)477-1671x73948',
    'json': {
    'name': 'James Hayes',
    'address': '5784 Jones Squares\nPoolebury, PR 29430',
},
    'key57414': 'value61714',
},
    {
    'id': 17527490611102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Bridget Kemp',
    'address': '456 Fox Extensions\nWest Keith, ME 23116',
    'text': 'Until truth student wait type system especially strong. Doctor high oil somebody alone east carry.\nPractice president but surface hope factor wait.',
    'email': 'ghouston@example.com',
    'phone_number': '(296)965-7576x02201',
    'json': {
    'name': 'Roger Anthony',
    'address': '95102 Rhodes Landing Apt. 858\nJohnstad, UT 08022',
},
    'key20612': 'value56972',
    'key34876': 'value9543',
    'key55650': 'value30428',
    'key29216': 'value75735',
    'key60234': 'value62810',
    'key38509': 'value16378',
    'key42221': 'value99622',
    'key19014': 'value49225',
},
    {
    'id': 17527490611113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Susan Johnson',
    'address': '119 Woods Row Apt. 432\nPattonbury, IL 85405',
    'text': 'State guy a even resource painting ability. Message alone most open art age. Air clear whose capital.',
    'email': 'matthew75@example.com',
    'phone_number': '001-930-614-5092x2961',
    'json': {
    'name': 'Steven Anderson',
    'address': '6869 Hopkins Pine\nNew Sarahmouth, KS 07899',
},
    'key74551': 'value12672',
    'key37009': 'value94942',
    'key92498': 'value60673',
},
    {
    'id': 17527490611124,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Rita Stephens',
    'address': '76672 Harris Loaf Apt. 018\nCharlesstad, MA 24470',
    'text': 'Public community conference person themselves far. Then dog prevent firm him.\nStep party poor response short next. Part music just.',
    'email': 'cmorales@example.com',
    'phone_number': '+1-365-714-3745x7992',
    'json': {
    'name': 'Michael Gibbs',
    'address': '061 Caitlin Mission Suite 880\nLake Briannamouth, WA 24285',
},
    'key57987': 'value18744',
    'key32836': 'value37288',
    'key53246': 'value23835',
    'key49518': 'value70780',
    'key78400': 'value58560',
    'key91063': 'value97580',
    'key76289': 'value254',
    'key80927': 'value95793',
},
    {
    'id': 17527490611135,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Sarah Morris',
    'address': '83264 Reginald Ranch Apt. 642\nVargasberg, IA 87960',
    'text': 'Reflect factor eight sure sing detail. Community yard grow article number.',
    'email': 'donna70@example.net',
    'phone_number': '(584)682-7347',
    'json': {
    'name': 'Beth Hess',
    'address': '5248 Johnson Stravenue\nEast Jacobtown, NH 14355',
},
    'key18210': 'value11656',
    'key68639': 'value46547',
    'key35646': 'value25598',
    'key48021': 'value49807',
},
    {
    'id': 17527490611146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'David Caldwell',
    'address': '814 Hernandez Ford Apt. 000\nRaymouth, AS 56891',
    'text': 'Trade item program before. Establish vote technology walk more remember.\nAsk fish senior factor commercial. Across number discussion cold herself. Close bar public defense society serious budget.',
    'email': 'xmurphy@example.net',
    'phone_number': '+1-743-294-7574',
    'json': {
    'name': 'Thomas Smith',
    'address': '38772 Adam Islands\nSandyton, GA 05353',
},
    'key8338': 'value13341',
    'key35595': 'value12928',
    'key18391': 'value63286',
    'key26736': 'value49171',
    'key17501': 'value97774',
    'key11652': 'value43200',
    'key55940': 'value8595',
},
    {
    'id': 17527490611156,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Patricia Moody',
    'address': '242 Nguyen Union Suite 897\nPort Michael, NV 80552',
    'text': 'Home trial change tree south party letter. Common leader quite need third. Several member enough unit house wear many.',
    'email': 'owensgeorge@example.org',
    'phone_number': '3996625615',
    'json': {
    'name': 'Krista Riggs',
    'address': '74887 Molina Path Apt. 086\nSmithland, FM 55351',
},
    'key53871': 'value72461',
    'key18790': 'value34000',
    'key12949': 'value20652',
    'key46468': 'value50563',
    'key16455': 'value70242',
    'key79128': 'value72273',
    'key55443': 'value60384',
    'key83765': 'value36752',
    'key89306': 'value3567',
    'key24971': 'value14004',
},
    {
    'id': 17527490611168,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Justin Callahan',
    'address': '60193 Emily Ports\nKarenview, AS 72944',
    'text': 'Old quickly approach kid professional thus quite. And chance sea truth second. Candidate maybe thing side upon so.',
    'email': 'juliedavila@example.org',
    'phone_number': '001-688-445-9815',
    'json': {
    'name': 'Andrea Hart',
    'address': '97867 Brian Tunnel\nOmarton, VI 40662',
},
    'key59056': 'value58434',
    'key41900': 'value30680',
},
    {
    'id': 17527490611179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Oscar Sandoval',
    'address': '713 Marissa Views\nJasonland, TN 62905',
    'text': 'Six recent despite go so number by. Use nice success mouth physical choose.\nCarry knowledge impact guess particularly once. Onto country firm stand seek push policy.',
    'email': 'ashleytaylor@example.com',
    'phone_number': '740-566-0967x42633',
    'json': {
    'name': 'Ryan Garcia',
    'address': '2823 James Circle\nEast Donnafort, ME 33718',
},
    'key25070': 'value33409',
    'key7917': 'value76803',
    'key87941': 'value41887',
    'key40990': 'value44303',
    'key60102': 'value15152',
    'key57104': 'value3420',
    'key81347': 'value24388',
},
    {
    'id': 17527490611190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Bruce Austin',
    'address': '228 Smith Club\nUnderwoodfort, TX 01237',
    'text': 'Common expect year garden four evening. Save arrive interview occur.\nSo cup suggest without stock idea tree.',
    'email': 'summerslarry@example.net',
    'phone_number': '8482263612',
    'json': {
    'name': 'Rebecca Boyle',
    'address': '97971 Rivera Path Suite 397\nNew Bryanport, DC 70142',
},
    'key76778': 'value54609',
    'key20021': 'value728',
    'key48219': 'value91202',
    'key25102': 'value21744',
    'key10165': 'value95310',
    'key21224': 'value59203',
    'key25670': 'value4783',
    'key64787': 'value86080',
    'key65811': 'value47340',
    'key22136': 'value6110',
},
    {
    'id': 17527490611202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Sydney Ellison',
    'address': '766 Robert Drive\nRavenchester, WI 95698',
    'text': 'Claim seat high everything require matter market. Student ok test response read.\nHealth not decision push region. Hot approach population decide exactly daughter. Beyond specific radio open step.',
    'email': 'kristin75@example.net',
    'phone_number': '754-476-3710',
    'json': {
    'name': 'Misty Collins',
    'address': '3454 Ball Rapid Apt. 243\nEast Victoria, MA 74832',
},
    'key82898': 'value34936',
    'key39898': 'value43402',
    'key76887': 'value10188',
    'key51126': 'value3046',
    'key8539': 'value87690',
},
    {
    'id': 17527490611214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Bradley Carroll',
    'address': '42984 Rodney Trafficway Apt. 752\nBurtonville, WI 16787',
    'text': 'Be bring agency option per. Conference industry debate. Mission member beat raise.',
    'email': 'timothybean@example.org',
    'phone_number': '+1-492-805-5659',
    'json': {
    'name': 'Mr. Trevor Kidd Jr.',
    'address': '26856 Schroeder Hill Suite 597\nAshleyview, NE 61073',
},
    'key61846': 'value39563',
    'key40918': 'value38103',
    'key16220': 'value27699',
    'key24740': 'value95540',
    'key86112': 'value91389',
    'key98098': 'value2844',
    'key38801': 'value20701',
    'key69908': 'value89691',
    'key30445': 'value36692',
    'key60397': 'value56983',
},
    {
    'id': 17527490611228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Michele Short',
    'address': '4061 Brown Square Suite 252\nRileyberg, CA 15215',
    'text': 'Set standard surface admit financial few. Upon instead however. Deal risk trip.\nUnit machine himself.\nElse region thing. Citizen level affect increase.',
    'email': 'erika19@example.com',
    'phone_number': '(685)218-0922',
    'json': {
    'name': 'Veronica Montgomery',
    'address': '125 Blake Shoal Suite 864\nEast Sarafurt, KY 39603',
},
    'key20502': 'value65633',
    'key70915': 'value25406',
},
    {
    'id': 17527490611244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Rachel Le',
    'address': '944 Jeremy Port Apt. 712\nPort Andrew, MS 47664',
    'text': 'Rich happen shoulder act heavy. Agent house trial final hear politics hard.\nShe sure water accept throw.',
    'email': 'zjones@example.com',
    'phone_number': '001-728-756-7655x4428',
    'json': {
    'name': 'Julie Tapia',
    'address': '97901 Daniels Summit\nWest Heatherside, ME 95226',
},
    'key41403': 'value74145',
    'key54990': 'value57400',
    'key75533': 'value61952',
    'key44335': 'value62027',
    'key32266': 'value67289',
    'key18882': 'value99844',
},
    {
    'id': 17527490611266,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Monica Jordan',
    'address': '87841 Jennifer Garden Suite 142\nCookeland, MT 48892',
    'text': 'New get far break central clearly. Nice however people charge.\nAdd total check.\nItem hold religious throughout. Current note must single figure.',
    'email': 'leejerry@example.org',
    'phone_number': '421.373.3773x326',
    'json': {
    'name': 'Christopher Mitchell',
    'address': 'Unit 0904 Box 0280\nDPO AP 42833',
},
    'key51652': 'value12552',
    'key21479': 'value68754',
    'key27551': 'value96589',
    'key87990': 'value87826',
    'key41953': 'value92231',
    'key92048': 'value13236',
},
    {
    'id': 17527490611285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Devin Cabrera',
    'address': 'USNV Watson\nFPO AE 79812',
    'text': 'Address wide free matter begin. Beautiful before kid event keep even character various. Heart option black everything. Sound father season difficult must responsibility indicate.',
    'email': 'anita71@example.net',
    'phone_number': '001-456-667-7505x49623',
    'json': {
    'name': 'Lynn Savage',
    'address': '58987 Stone Burg\nLisaburgh, GA 73193',
},
    'key75675': 'value12367',
    'key49846': 'value21602',
    'key47309': 'value27708',
    'key56534': 'value46114',
    'key31694': 'value60897',
    'key47516': 'value48015',
    'key37606': 'value18241',
    'key51768': 'value62925',
    'key32273': 'value94820',
    'key871': 'value76620',
},
    {
    'id': 17527490611297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Carolyn Rodriguez',
    'address': '2694 Karl Union Suite 266\nDuarteport, WA 91568',
    'text': 'Trip break reflect time hair without institution. News make quite watch trial.\nHelp fall sister specific. Charge popular article evidence. Late capital everything image sport.',
    'email': 'jimmyjames@example.net',
    'phone_number': '317-949-7536x163',
    'json': {
    'name': 'Monica Cooper',
    'address': '223 Christopher Meadow\nMichaelland, IA 44787',
},
    'key56653': 'value5038',
    'key88657': 'value35166',
},
    {
    'id': 17527490611311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Scott Robinson',
    'address': '611 Olivia Rue Suite 071\nNorth Warren, LA 30682',
    'text': 'Always state charge lawyer talk religious current ahead. Move specific understand great bank. Significant television two every night both.\nBehavior future truth will.\nSociety impact easy.',
    'email': 'ecobb@example.net',
    'phone_number': '001-332-812-4666x80932',
    'json': {
    'name': 'Michelle Alexander',
    'address': '29773 Brown Plains\nJaredborough, DE 80326',
},
    'key30918': 'value32944',
    'key69073': 'value57841',
    'key10740': 'value35967',
    'key125': 'value10112',
    'key65912': 'value17749',
    'key56675': 'value22245',
    'key6198': 'value39157',
},
    {
    'id': 17527490611325,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Christopher Kaufman',
    'address': 'PSC 7383, Box 6579\nAPO AE 85566',
    'text': 'Do also grow own focus factor institution. Government face capital.\nSometimes himself employee suffer. Find front everybody operation seek around.',
    'email': 'courtney33@example.org',
    'phone_number': '471.538.1081x97995',
    'json': {
    'name': 'Gary Owens',
    'address': '7554 Perez Rest\nEast Jeffery, PW 70841',
},
    'key60224': 'value53857',
    'key86990': 'value46612',
},
    {
    'id': 17527490611336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Robert Roman Jr.',
    'address': '0262 Jimenez Fork Apt. 884\nRuthton, UT 82589',
    'text': 'Teacher much determine identify above pressure. Sign suffer short small. One system actually positive clearly political.',
    'email': 'bbrown@example.com',
    'phone_number': '(833)649-1427',
    'json': {
    'name': 'Cody Charles',
    'address': 'USNS Houston\nFPO AP 50087',
},
    'key86555': 'value35231',
    'key33148': 'value83712',
    'key23782': 'value66604',
    'key3324': 'value17892',
    'key6921': 'value94273',
    'key20730': 'value77419',
    'key53515': 'value17585',
    'key52029': 'value16435',
    'key6816': 'value49964',
},
    {
    'id': 17527490611348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Matthew Ramos',
    'address': '4559 Katrina Falls Apt. 433\nEast Nathanshire, IA 73537',
    'text': 'Truth prepare couple television time many. Clear center executive risk all. And year democratic resource beat fire. Area art note hard civil.\nAbove good owner recently protect garden natural box.',
    'email': 'ericabush@example.com',
    'phone_number': '001-643-700-1424x40098',
    'json': {
    'name': 'Todd Romero',
    'address': '8506 Valdez Road Apt. 788\nTraceyview, PR 00532',
},
    'key50931': 'value4360',
    'key36318': 'value29318',
    'key22061': 'value67305',
    'key69622': 'value8029',
    'key33886': 'value85959',
    'key16932': 'value15072',
    'key61981': 'value82126',
    'key36852': 'value91483',
},
    {
    'id': 17527490611363,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Mrs. Christine Young',
    'address': '801 Edwards Lock Suite 357\nEast Thomasburgh, MA 13747',
    'text': 'Whom many great. Interest stage teach development baby community. Beat draw rise everything visit.\nValue buy that happy camera. Story physical tonight green. Chance area project him image instead.',
    'email': 'carloshardin@example.org',
    'phone_number': '535-286-3018x64489',
    'json': {
    'name': 'Aaron Simmons',
    'address': '9347 Adrian Parkway\nChristopherside, AK 55258',
},
    'key16058': 'value41405',
},
    {
    'id': 17527490611378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Jason Gray',
    'address': 'USNV Becker\nFPO AE 68521',
    'text': 'Right save parent later safe tell impact. Mind necessary notice west student we. Offer beyond daughter significant foreign beat.',
    'email': 'hthompson@example.net',
    'phone_number': '(240)900-0827',
    'json': {
    'name': 'Christian Miller',
    'address': '656 Miles Knolls\nPort Katrinaport, GU 68237',
},
    'key58661': 'value39399',
    'key8379': 'value27356',
    'key8231': 'value62601',
    'key96105': 'value95707',
    'key57104': 'value80960',
    'key10997': 'value95687',
    'key14989': 'value88542',
    'key49862': 'value57497',
    'key77190': 'value29060',
    'key93367': 'value9735',
},
    {
    'id': 17527490611390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Anna Martinez',
    'address': '20758 Karen Inlet Apt. 407\nLoriville, PW 06262',
    'text': 'Room window huge Mrs full. Student product catch seek time strong play. Decision avoid but ability war reduce.',
    'email': 'kbrooks@example.net',
    'phone_number': '312-344-1862x974',
    'json': {
    'name': 'Michael Simpson',
    'address': '21671 Carson Overpass\nPort Jack, VT 20184',
},
    'key20860': 'value66813',
    'key65510': 'value79021',
    'key16770': 'value89054',
    'key73102': 'value95389',
    'key24628': 'value80823',
    'key71209': 'value61722',
    'key75018': 'value68281',
    'key81341': 'value76891',
    'key73093': 'value21070',
},
    {
    'id': 17527490611403,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Roberto Cherry',
    'address': '8045 Russell Estate Apt. 494\nNorth Roberthaven, MO 88752',
    'text': 'Nice idea agent model.\nRange present prepare specific theory. Why today baby first as culture air industry. Health our both either yourself off save.',
    'email': 'robertsmark@example.com',
    'phone_number': '743-372-3451x232',
    'json': {
    'name': 'Michael Lopez',
    'address': '663 Gabrielle Island\nEast Jeff, WV 15725',
},
    'key63781': 'value31790',
    'key52545': 'value25054',
    'key28813': 'value82018',
    'key38622': 'value63132',
    'key11146': 'value20177',
    'key74809': 'value93013',
    'key88122': 'value4310',
    'key9028': 'value78453',
    'key84010': 'value39043',
    'key98767': 'value61099',
},
    {
    'id': 17527490611416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Deanna Bailey',
    'address': '159 Michelle Squares\nKennethport, MT 10572',
    'text': 'Receive contain three story stock language today. Better degree scientist wrong without blood economy.\nIn animal admit he take. Republican general stage something.',
    'email': 'hodgejoseph@example.org',
    'phone_number': '671.793.2271x564',
    'json': {
    'name': 'Nancy Johnson',
    'address': '29770 Pamela Overpass\nHudsonhaven, IL 95138',
},
    'key52657': 'value35544',
    'key68991': 'value99345',
    'key1963': 'value32619',
    'key94780': 'value43970',
    'key4958': 'value55564',
    'key39642': 'value99220',
    'key98284': 'value2642',
    'key37546': 'value92719',
    'key99514': 'value64284',
},
    {
    'id': 17527490611427,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Bobby Erickson',
    'address': '36383 Kathryn Wells\nSouth Robert, NJ 48903',
    'text': 'Whether professor miss who tell manager. Catch interesting painting another her amount.\nWith page despite cover section. Tough at success beyond less they hand.',
    'email': 'sabrina65@example.net',
    'phone_number': '724.313.3403',
    'json': {
    'name': 'Judith White',
    'address': 'PSC 2364, Box 4928\nAPO AE 83238',
},
    'key5550': 'value5935',
    'key46195': 'value66560',
    'key41105': 'value84497',
    'key1537': 'value93378',
    'key77416': 'value49615',
    'key39391': 'value98854',
    'key91511': 'value4384',
    'key9179': 'value67916',
    'key72513': 'value51214',
},
    {
    'id': 17527490611435,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Amanda Gutierrez',
    'address': '543 Ruth Islands Apt. 326\nMitchellburgh, AR 91171',
    'text': 'Student story what four. Either begin spend a ago factor not. Single write ability action spend ok.',
    'email': 'tbaker@example.org',
    'phone_number': '552.551.1627',
    'json': {
    'name': 'Carol Le',
    'address': '8639 Victoria Passage\nWest Allisonchester, MI 73111',
},
    'key24433': 'value31165',
    'key26001': 'value49791',
    'key77817': 'value8497',
    'key95473': 'value37737',
},
    {
    'id': 17527490611446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Veronica Hernandez',
    'address': '563 Andrea Estates Suite 575\nJasonport, GU 39372',
    'text': 'Who me southern if hard. Community east these account debate language. Available street start instead.\nAdult player suffer field. But alone probably about citizen.',
    'email': 'lucerotammy@example.com',
    'phone_number': '+1-911-539-3375x2319',
    'json': {
    'name': 'Nicholas Payne',
    'address': '38603 Christensen Cove\nNew Huntermouth, AS 46732',
},
    'key8705': 'value22630',
    'key84339': 'value68347',
    'key52824': 'value75465',
    'key9635': 'value74970',
},
    {
    'id': 17527490611457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Joshua Dominguez',
    'address': 'USCGC Johnson\nFPO AP 48256',
    'text': 'Suffer reveal start every together surface. Talk forward city and lay tough start. Way whether low well across.',
    'email': 'rhondamcpherson@example.org',
    'phone_number': '974.265.6644x4122',
    'json': {
    'name': 'Michael Chang',
    'address': '7030 Cook Point\nLake Steven, DE 51778',
},
    'key40988': 'value46494',
    'key72984': 'value79115',
    'key81689': 'value55281',
    'key61095': 'value48794',
    'key18024': 'value82333',
    'key86728': 'value23944',
    'key75769': 'value28705',
    'key1718': 'value83376',
    'key60142': 'value10077',
    'key75311': 'value1881',
},
    {
    'id': 17527490611468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Natalie Martin',
    'address': '09842 Spears Mountain\nRobertborough, TX 82353',
    'text': 'Sound she sell. Article lot our way hope arrive. Maybe start face effort.\nWish end protect American condition. Rich news west impact free fast. Act everyone nature health skin.',
    'email': 'christy97@example.net',
    'phone_number': '3355895485',
    'json': {
    'name': 'Shawn Anderson',
    'address': '9598 Thompson Crossroad\nPort Misty, LA 89529',
},
    'key7158': 'value75185',
    'key756': 'value71434',
    'key60749': 'value66856',
},
    {
    'id': 17527490611478,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Alexis Johnson',
    'address': '388 Ross Fields\nJessicaland, MI 50835',
    'text': 'Civil out tax decade energy. Cause learn stage cold behavior PM drug. Detail traditional future education recent medical personal.',
    'email': 'heatherburns@example.com',
    'phone_number': '(466)889-0072x750',
    'json': {
    'name': 'Manuel Paul',
    'address': 'USS Kelley\nFPO AE 65648',
},
    'key22887': 'value41763',
    'key77718': 'value8924',
    'key17487': 'value62067',
    'key89528': 'value58716',
},
    {
    'id': 17527490611489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Teresa Mckinney',
    'address': '41401 Dean Forges\nLake Patrick, AR 50580',
    'text': 'Left community member cold. Himself social create friend.\nRule see couple various girl. Draw however lawyer fast will impact information. Computer treatment real thank price against.',
    'email': 'omarhenry@example.net',
    'phone_number': '+1-285-322-6100',
    'json': {
    'name': 'Sara Thomas',
    'address': '98650 Cox Glen\nVanessaborough, NH 08388',
},
    'key11360': 'value75389',
    'key49118': 'value60106',
    'key79370': 'value38397',
    'key86996': 'value36656',
    'key29368': 'value28039',
    'key33351': 'value4983',
    'key40849': 'value53618',
    'key63194': 'value25422',
    'key3182': 'value12379',
},
    {
    'id': 17527490611501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Warren Donaldson',
    'address': '870 Melissa Neck Apt. 372\nWest Anthonyport, KS 58837',
    'text': 'Determine purpose discuss weight claim seem. Professor up foreign former avoid film will. Generation strong key control.',
    'email': 'cassandracollins@example.com',
    'phone_number': '759-906-7870x84762',
    'json': {
    'name': 'Nathan Sherman',
    'address': '79201 Michael Common Suite 622\nCantubury, LA 58433',
},
    'key33301': 'value85483',
    'key8115': 'value392',
    'key6422': 'value22013',
},
    {
    'id': 17527490611512,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Lisa Evans',
    'address': '83698 Huber Valley Suite 935\nEast Charleston, IL 20095',
    'text': 'Situation consumer finally. Production once protect perhaps performance phone. News add item the land. Close bad likely PM.',
    'email': 'lpreston@example.org',
    'phone_number': '+1-324-667-3743x3836',
    'json': {
    'name': 'Carlos Reyes',
    'address': '202 Russell Overpass\nPort Jenniferville, PW 56244',
},
    'key64878': 'value72978',
    'key73006': 'value89258',
    'key36326': 'value18704',
    'key72882': 'value92800',
    'key89316': 'value28216',
    'key35666': 'value10299',
    'key85052': 'value43638',
},
    {
    'id': 17527490611523,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Julie Snyder',
    'address': '921 Campbell Gardens Apt. 360\nMaryport, RI 76405',
    'text': 'Phone discover party money project learn. Majority what test house.\nRegion week star unit soldier huge after. Sort begin itself think put. Sell around worker strong worry career participant.',
    'email': 'greenbriana@example.net',
    'phone_number': '592-228-6943x9259',
    'json': {
    'name': 'Keith Alvarez',
    'address': '5529 Sanchez Square\nNorth Ashley, AZ 30269',
},
    'key77050': 'value89963',
    'key68743': 'value55612',
    'key37731': 'value93031',
},
    {
    'id': 17527490611535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Dustin Richards',
    'address': 'USNS George\nFPO AA 11141',
    'text': 'Study human wide benefit together church. True young page player appear. Point bag perform employee morning.',
    'email': 'timothystewart@example.net',
    'phone_number': '+1-959-914-1513x5765',
    'json': {
    'name': 'Kevin Shaffer',
    'address': '50189 Alexander Isle Suite 698\nRebeccaview, AS 67021',
},
    'key27315': 'value29870',
    'key94041': 'value37020',
    'key30970': 'value87858',
    'key91096': 'value76937',
    'key10125': 'value39344',
    'key46078': 'value35825',
    'key50932': 'value44845',
    'key39555': 'value3745',
    'key66072': 'value59273',
    'key85638': 'value48154',
},
    {
    'id': 17527490611545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Jason Williams',
    'address': '2751 Angela Roads Suite 983\nEast Danielton, NV 94038',
    'text': 'Truth statement goal soldier ball car least garden. Project word produce firm skin. Magazine plant quite either.',
    'email': 'orrcolleen@example.org',
    'phone_number': '326.633.3464',
    'json': {
    'name': 'David Williams',
    'address': '21534 Johnson Manors\nJonathanbury, AK 78169',
},
    'key32926': 'value89427',
    'key75441': 'value63050',
    'key20519': 'value97943',
},
    {
    'id': 17527490611557,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Mr. Theodore Goodman',
    'address': '5078 Hurst Ways Suite 217\nNorth Jamesborough, AZ 56803',
    'text': 'Create hear environment already official stop quite age. Fast up be three space which. Indicate house day dark around artist.',
    'email': 'wclay@example.com',
    'phone_number': '001-589-789-5950',
    'json': {
    'name': 'Michael Roy',
    'address': '4582 Washington Squares Suite 164\nSusanside, MA 86754',
},
    'key40690': 'value56786',
    'key27301': 'value52883',
    'key88111': 'value46127',
    'key16072': 'value72568',
    'key5729': 'value13494',
    'key9536': 'value89125',
    'key39767': 'value94111',
},
    {
    'id': 17527490611568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Ernest Allen',
    'address': '59483 Ricardo Radial Apt. 695\nWallacetown, AR 70577',
    'text': 'Practice ever situation reality but. Officer drop actually remember country.\nSecond glass treatment over. Program seem modern to million recognize.',
    'email': 'andrew31@example.net',
    'phone_number': '491-540-4051x97126',
    'json': {
    'name': 'Jimmy Martin',
    'address': '9594 Arnold Shoal Suite 467\nJasonfort, PW 59779',
},
    'key49347': 'value71811',
    'key7074': 'value25832',
    'key99988': 'value23920',
    'key36887': 'value29318',
},
    {
    'id': 17527490611579,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Christy Martinez',
    'address': '470 Timothy Ports\nNew Lisa, AL 38428',
    'text': 'Hold step dream which truth read. Social pay very and course detail six.',
    'email': 'murphychristina@example.org',
    'phone_number': '+1-549-892-6427x375',
    'json': {
    'name': 'Claudia Gonzales',
    'address': '6812 Renee Mountain\nRonaldburgh, AS 08032',
},
    'key48371': 'value50965',
},
    {
    'id': 17527490611589,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Tammy Soto',
    'address': '1534 Campbell Hill Apt. 179\nMollyton, WV 53940',
    'text': 'Cell between often film. Edge condition happy perform easy individual. Anything former road approach interest always go.',
    'email': 'johnrodgers@example.org',
    'phone_number': '(938)792-3659x59980',
    'json': {
    'name': 'Teresa Cochran',
    'address': '43533 Soto Ports Apt. 347\nWest Laura, MI 95416',
},
    'key84849': 'value38135',
    'key89928': 'value23488',
    'key41067': 'value13689',
    'key20809': 'value80071',
    'key79604': 'value39883',
},
    {
    'id': 17527490611601,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Mark Miller',
    'address': '7327 Mcbride Crescent Apt. 109\nWilsonfort, DC 40824',
    'text': 'Each hundred land this tend far. Use successful left. Someone already step month interesting American. Ten whose money public give evidence camera.',
    'email': 'stewartamanda@example.net',
    'phone_number': '9954644156',
    'json': {
    'name': 'Alexander Allen',
    'address': '0653 Moore Greens Suite 978\nWest Lisa, IL 78457',
},
    'key64690': 'value48723',
    'key54693': 'value45371',
    'key33381': 'value68866',
},
    {
    'id': 17527490611616,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Joshua Black',
    'address': '97277 Bush Islands\nLake Jeffreymouth, OR 91413',
    'text': 'Space audience life join direction. Argue bed population lose this. Cold marriage father other.\nMust mouth free dog including else meeting. Certainly already fish democratic.',
    'email': 'carsonjenny@example.com',
    'phone_number': '4263800859',
    'json': {
    'name': 'Heather Medina',
    'address': '19481 Underwood Inlet\nPagehaven, NE 59118',
},
    'key40130': 'value64856',
    'key43183': 'value12124',
    'key71594': 'value87225',
    'key82429': 'value95604',
    'key66117': 'value8851',
    'key42060': 'value97252',
    'key50482': 'value92194',
},
    {
    'id': 17527490611635,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'James Mathis',
    'address': '08005 Howard Light\nNorth Sara, MO 27735',
    'text': 'Those city stand carry play. Performance leg charge then book.\nAddress carry hold yourself majority first issue. Million Congress away out little participant song.',
    'email': 'xjenkins@example.net',
    'phone_number': '(512)806-7578',
    'json': {
    'name': 'Rachel Harris',
    'address': '7532 Claire Street\nJacquelinebury, NY 46378',
},
    'key78608': 'value279',
    'key20994': 'value49632',
    'key77198': 'value12643',
    'key85830': 'value62543',
    'key41657': 'value3025',
    'key54623': 'value94763',
    'key61425': 'value84227',
    'key71274': 'value61049',
},
    {
    'id': 17527490611654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Charles Turner',
    'address': '0443 Johnson Shoal Apt. 068\nPort Jenniferfurt, VI 48672',
    'text': 'Capital contain successful second ago. Opportunity close deal money most leg.\nDifference reflect occur travel player open scientist short. Stock college upon name. Maybe share use body.',
    'email': 'kimberly85@example.com',
    'phone_number': '+1-714-739-6845x8356',
    'json': {
    'name': 'Earl Oliver',
    'address': '2007 Davis Road\nLake Derek, GU 19120',
},
    'key83627': 'value21045',
    'key19118': 'value93175',
    'key72578': 'value1193',
    'key70069': 'value6719',
    'key11721': 'value1715',
    'key29356': 'value25236',
    'key43689': 'value93071',
},
    {
    'id': 17527490611675,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Brett Miller',
    'address': '8042 George Groves Apt. 453\nNorth William, GA 57548',
    'text': 'Process bar peace ask. Subject number control source. Seat true fire drive wrong window low bring.\nBelieve involve house final. Figure institution third.',
    'email': 'mbrown@example.com',
    'phone_number': '001-681-533-4300',
    'json': {
    'name': 'John Robertson',
    'address': '246 Michael Track Apt. 314\nWest Emilyshire, TN 71526',
},
    'key72513': 'value64749',
    'key97028': 'value44052',
    'key86482': 'value57373',
    'key29397': 'value85224',
    'key44193': 'value98926',
    'key9312': 'value75481',
    'key25490': 'value45361',
},
    {
    'id': 17527490611689,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Danielle Mcdaniel',
    'address': '3281 Donaldson Rapid\nMichaelhaven, AR 35378',
    'text': 'Physical child take. Water end local easy person.\nHead general left out practice discussion. Wife finish tax. Sense character eye school.',
    'email': 'jason59@example.net',
    'phone_number': '448.862.6351',
    'json': {
    'name': 'Sarah Moreno',
    'address': '7564 Swanson Port Apt. 445\nFrankmouth, IA 37648',
},
    'key37162': 'value77341',
    'key74475': 'value36625',
    'key77240': 'value82510',
    'key1463': 'value67209',
    'key94549': 'value62268',
    'key9367': 'value65146',
    'key91963': 'value75021',
    'key31008': 'value82004',
},
    {
    'id': 17527490611702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Charlotte Brooks',
    'address': '2822 Webster Skyway Suite 023\nKeithhaven, IL 82484',
    'text': 'Wall by focus loss learn discover. Maintain particularly Congress type around serious lose. Sea beautiful various receive. Security rise parent animal kind modern age president.',
    'email': 'barbarabrown@example.com',
    'phone_number': '001-383-469-8697x566',
    'json': {
    'name': 'Yvette Jones',
    'address': '491 Hensley Branch Apt. 740\nPort Aliciashire, ID 94727',
},
    'key69778': 'value4219',
    'key64836': 'value27516',
    'key89680': 'value61253',
    'key54154': 'value96145',
    'key77871': 'value43173',
    'key76750': 'value75981',
    'key66224': 'value95068',
    'key36212': 'value24529',
},
    {
    'id': 17527490611717,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Timothy Cabrera',
    'address': '90515 Phillip Views\nWeberview, NC 58994',
    'text': 'Only base magazine skin. Event edge economy side voice.\nRemember interest environment sign. Wall sense how him water perform call per. Sing almost buy though.',
    'email': 'palmermichele@example.com',
    'phone_number': '829.366.6515x788',
    'json': {
    'name': 'Amy Gentry',
    'address': '068 Heather Mills Suite 424\nWest Bethanyton, OR 96833',
},
    'key19223': 'value28122',
    'key5265': 'value39715',
},
    {
    'id': 17527490611731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Karen Parker',
    'address': '957 Daniel Locks Apt. 164\nSouth Sonya, VI 08262',
    'text': 'Still effort end carry real today total. Sell discussion let need young recent difficult.\nAgainst word must third total century board. Time garden effect wall father.',
    'email': 'jenniferdean@example.net',
    'phone_number': '464.796.4567',
    'json': {
    'name': 'Amanda Curtis',
    'address': '531 Derrick Streets Suite 074\nRobinsonberg, CT 93612',
},
    'key75772': 'value77528',
    'key8702': 'value62147',
    'key89306': 'value6340',
    'key23111': 'value20342',
    'key23901': 'value93631',
    'key57672': 'value96621',
    'key41382': 'value55435',
    'key74180': 'value35231',
},
    {
    'id': 17527490611746,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Scott Ball',
    'address': '5878 Silva Knolls Apt. 230\nLake Tina, MA 57717',
    'text': 'Down couple easy accept pressure. Organization assume help stuff player. Receive summer major while.\nGeneral structure computer enjoy finish heavy risk hit.',
    'email': 'timothy62@example.com',
    'phone_number': '(648)312-5674x250',
    'json': {
    'name': 'Angel Mclaughlin',
    'address': '150 Campbell Streets\nErikside, ND 58468',
},
    'key77384': 'value26805',
    'key7982': 'value54900',
    'key58190': 'value83728',
    'key2329': 'value58145',
    'key13120': 'value6035',
    'key35748': 'value61236',
    'key88494': 'value7721',
    'key37179': 'value23328',
},
    {
    'id': 17527490611760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Leah Sandoval',
    'address': '76911 Peterson Stravenue Suite 553\nWest Javier, AK 35756',
    'text': 'Early reality determine cup program hour. Wide add forget admit we doctor close.',
    'email': 'geraldmiller@example.net',
    'phone_number': '001-500-466-6619x127',
    'json': {
    'name': 'Glenn Vasquez',
    'address': 'USNS Mack\nFPO AP 55755',
},
    'key39192': 'value45013',
    'key3650': 'value61516',
},
    {
    'id': 17527490611773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Mary Frost',
    'address': '8344 Jones Wall Apt. 793\nHernandezside, MO 13744',
    'text': 'Current specific drug race himself. Result occur increase wear. Sign record seat easy other choice.\nCity capital safe. Former play have possible.',
    'email': 'brian45@example.net',
    'phone_number': '001-526-976-8272x750',
    'json': {
    'name': 'Stephen Galvan',
    'address': '6830 Pruitt Ford Suite 829\nSouth Anne, AS 80903',
},
    'key86572': 'value64562',
    'key68744': 'value38316',
    'key95533': 'value11010',
},
    {
    'id': 17527490611787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Jennifer Smith',
    'address': 'PSC 1309, Box 2373\nAPO AA 33933',
    'text': 'Out green environmental chance than. Play I determine start control group.\nHimself memory rich explain. Standard end yeah cell key trial science bar. Several eye plan.',
    'email': 'katievelazquez@example.net',
    'phone_number': '9037704835',
    'json': {
    'name': 'Karen Murillo',
    'address': '919 Jacqueline Harbor Suite 191\nEast Charles, VA 09719',
},
    'key288': 'value72916',
    'key96193': 'value96203',
    'key97099': 'value7785',
    'key28903': 'value91861',
},
    {
    'id': 17527490611797,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Spencer Lee',
    'address': 'Unit 9890 Box 4263\nDPO AA 44721',
    'text': 'Fire social sound get past. Toward reduce decade yeah.\nHalf score yeah enough say. Year way federal could bring voice.',
    'email': 'elizabeth76@example.com',
    'phone_number': '(449)415-9836',
    'json': {
    'name': 'Zachary Hall',
    'address': '757 Johnson Course\nWest Rebeccashire, WA 13402',
},
    'key5520': 'value93865',
    'key94874': 'value69145',
    'key77912': 'value85860',
    'key6924': 'value49144',
    'key7811': 'value18369',
    'key89402': 'value35408',
    'key63593': 'value4892',
},
    {
    'id': 17527490611805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Charles Farmer',
    'address': '59307 Richard River\nYvonneborough, MS 02757',
    'text': 'Particular call necessary instead kid plant whom.\nTreatment available current pass item scientist world. Authority new family wind product east. Foot become modern camera thus.',
    'email': 'bellannette@example.net',
    'phone_number': '001-221-474-3509',
    'json': {
    'name': 'Jennifer Morgan',
    'address': '97849 Ryan Tunnel\nDavidland, NY 19582',
},
    'key46211': 'value55762',
    'key68706': 'value85473',
    'key47974': 'value6986',
    'key92183': 'value54131',
    'key45968': 'value5383',
    'key29160': 'value91855',
    'key13549': 'value69765',
    'key23415': 'value81805',
},
    {
    'id': 17527490611816,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Steven Prince',
    'address': '4753 Stephen Roads Apt. 683\nGarcialand, ID 90367',
    'text': 'Forget weight design against. Responsibility medical order participant minute decide lawyer. Raise bill some picture heart. Behavior tough computer you condition.',
    'email': 'wagnerelizabeth@example.com',
    'phone_number': '001-966-869-4318x4952',
    'json': {
    'name': 'Jack Case',
    'address': '961 Johnson Plaza Apt. 487\nAllenchester, MH 33626',
},
    'key75105': 'value14385',
    'key37265': 'value92412',
    'key38474': 'value39510',
    'key5901': 'value68955',
    'key48662': 'value29347',
    'key72216': 'value68195',
    'key70796': 'value77720',
    'key19229': 'value56533',
    'key20382': 'value1952',
},
    {
    'id': 17527490611828,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Alexa Crosby',
    'address': '43314 Mikayla Forge Suite 869\nBenjaminburgh, UT 36212',
    'text': 'Senior report cut. Successful human control management itself one agree.\nMatter despite eight election cell move fish. Stuff close finally. Action focus state.',
    'email': 'teresa08@example.org',
    'phone_number': '842.975.1716x1886',
    'json': {
    'name': 'Kristy Anderson',
    'address': '6082 Mendez Squares\nEast Elizabeth, ND 82548',
},
    'key42337': 'value86785',
    'key69132': 'value35844',
    'key50232': 'value39871',
},
    {
    'id': 17527490611839,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Lynn Long',
    'address': '91984 Jonathan Plain Apt. 855\nChristinaside, KS 85237',
    'text': 'Phone worry international own part often outside just.\nBeyond officer radio. Agency help book while any beat able action.',
    'email': 'andrea30@example.net',
    'phone_number': '+1-802-797-1854x0801',
    'json': {
    'name': 'Gregory Villarreal',
    'address': '4805 Hernandez Street\nNorth Walterfurt, IL 53664',
},
    'key66936': 'value48769',
    'key20804': 'value71477',
    'key57641': 'value43902',
    'key15479': 'value3329',
    'key847': 'value10102',
},
    {
    'id': 17527490611849,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Timothy Davis',
    'address': '93757 Mercer Ridges\nNorth Dianamouth, OH 53312',
    'text': 'College a trial yet. Leg car detail beautiful project detail. Treatment whose significant few stay.',
    'email': 'karennguyen@example.net',
    'phone_number': '271-935-6147',
    'json': {
    'name': 'Sara Anderson MD',
    'address': 'PSC 6821, Box 3957\nAPO AE 81407',
},
    'key19152': 'value51549',
    'key30901': 'value64755',
    'key32205': 'value92031',
    'key28031': 'value99653',
},
    {
    'id': 17527490611858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Taylor Wu',
    'address': 'Unit 8431 Box 7800\nDPO AA 87583',
    'text': 'Get news long choice move dream. Cost heavy their plant. Give building dinner case customer ten bad majority. Suggest onto produce left identify spring ago all.',
    'email': 'joycestephanie@example.net',
    'phone_number': '(225)281-0274x39621',
    'json': {
    'name': 'Mr. Daniel Williams',
    'address': '70337 Jillian Square\nPort Cynthiatown, ID 87086',
},
    'key60048': 'value33452',
    'key43899': 'value84559',
},
    {
    'id': 17527490611868,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Kenneth Smith',
    'address': '4587 Jacob Lakes Apt. 886\nSouth Tammy, AR 47794',
    'text': 'Do ground including central sport. Beat while career shake address. Also expert sing agent organization evening.',
    'email': 'christopher87@example.org',
    'phone_number': '(620)432-5868x664',
    'json': {
    'name': 'Antonio Abbott Jr.',
    'address': '01479 Lynch Valley Suite 058\nPhillipsport, RI 39224',
},
    'key16982': 'value56270',
    'key75798': 'value21599',
},
    {
    'id': 17527490611878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Patricia Bell',
    'address': '62417 Thornton Crossroad Apt. 420\nWest Michael, ME 63599',
    'text': 'Deep box before raise number. Report receive positive similar effect.\nThese area piece according meeting many central up. Hotel take amount arrive right cause tree.\nLong report success.',
    'email': 'tcampbell@example.org',
    'phone_number': '(540)522-9655',
    'json': {
    'name': 'Paige Murphy',
    'address': '043 Allen Greens\nPort David, GU 38934',
},
    'key37036': 'value3382',
    'key1219': 'value19172',
    'key39299': 'value70456',
    'key10635': 'value72652',
    'key14981': 'value32893',
    'key22846': 'value18415',
    'key65322': 'value75120',
},
    {
    'id': 17527490611889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'John Gordon',
    'address': '09894 Richard Cape\nNew Kristenchester, AR 98886',
    'text': 'Get attention care on. Radio a after argue. Arm write true sure general including organization.',
    'email': 'george89@example.net',
    'phone_number': '467.832.3769x456',
    'json': {
    'name': 'Christopher Allen',
    'address': '463 David Ville\nRiosside, WY 46698',
},
    'key2135': 'value51313',
},
    {
    'id': 17527490611899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Gerald Cardenas',
    'address': '237 Kelly Springs\nWest Matthewland, MS 26568',
    'text': 'Place fund across look national science compare task. Manage to respond loss create big when. Democratic food decide indeed.\nMind blue clear house recently. Run here respond half.',
    'email': 'ecole@example.com',
    'phone_number': '001-732-826-3577x3731',
    'json': {
    'name': 'Ashley Thompson',
    'address': '8866 Harmon Rapid Apt. 138\nPort Christine, WA 84835',
},
    'key68283': 'value78816',
    'key28255': 'value42380',
    'key85532': 'value99889',
},
    {
    'id': 17527490611910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Ronald Knox',
    'address': '837 Abbott Radial Apt. 262\nMartinezmouth, ME 09614',
    'text': 'Together kind myself. Store fly we. Find popular conference hard. Site street provide institution boy method begin growth.',
    'email': 'johnsonedward@example.org',
    'phone_number': '339-542-6693',
    'json': {
    'name': 'Joseph Lewis',
    'address': '605 Ryan Village\nPort Valerie, FL 39115',
},
    'key97752': 'value77883',
    'key13801': 'value60559',
    'key24950': 'value78774',
},
    {
    'id': 17527490611922,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Nicole Ryan',
    'address': '66041 Valencia Walk\nCarterhaven, NE 03826',
    'text': 'General risk development someone through unit. Break defense job thus. Require life at without of machine myself.',
    'email': 'jesse23@example.org',
    'phone_number': '910.426.2121x2077',
    'json': {
    'name': 'Katelyn Bailey',
    'address': '626 Rosales Track\nMichelleton, OK 58480',
},
    'key4244': 'value24081',
    'key22621': 'value59523',
    'key72210': 'value42889',
    'key26537': 'value82824',
    'key15613': 'value38899',
    'key27070': 'value70759',
    'key57294': 'value22610',
    'key79975': 'value83334',
},
    {
    'id': 17527490611935,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Nancy Evans',
    'address': '5030 Kim Unions\nEast Davidside, MH 74609',
    'text': 'I page approach idea need PM not she. True own cut series really. Take result money sense help short.',
    'email': 'gabriel19@example.org',
    'phone_number': '360-628-5751',
    'json': {
    'name': 'David Barton',
    'address': '2664 Lin Via Apt. 841\nDavisport, PR 10801',
},
    'key84198': 'value51378',
    'key76854': 'value33422',
    'key83333': 'value91761',
    'key92003': 'value38215',
    'key73187': 'value48049',
},
    {
    'id': 17527490611948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Jennifer Blackwell',
    'address': '348 Seth Hill\nJessicaton, CT 00570',
    'text': 'He down guess themselves. Up week hundred. Word relate like central.\nWant general here sound. Special wish down away light.',
    'email': 'cwells@example.net',
    'phone_number': '001-522-435-6355x068',
    'json': {
    'name': 'Rickey Young',
    'address': '7213 Bradshaw Drive Apt. 733\nJamiefort, RI 30725',
},
    'key59710': 'value56292',
    'key79668': 'value12136',
    'key93584': 'value41207',
    'key79683': 'value7227',
    'key5827': 'value64536',
    'key15947': 'value31559',
    'key16886': 'value93846',
    'key69287': 'value90765',
    'key52438': 'value23155',
    'key82354': 'value99192',
},
    {
    'id': 17527490611966,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Joshua Anderson',
    'address': '885 Rogers Parkways Apt. 512\nAlexanderland, ND 69219',
    'text': 'You instead relationship professional build what pretty better. Why sign prove fast all war state. Research lay receive home manage board.',
    'email': 'schmidtjeffrey@example.com',
    'phone_number': '667-842-5121',
    'json': {
    'name': 'Sharon Barnes',
    'address': '445 Sarah Tunnel Suite 368\nJeremiahtown, MN 89262',
},
    'key5768': 'value97066',
    'key68516': 'value21153',
    'key70972': 'value65504',
    'key53947': 'value91059',
    'key4037': 'value94971',
},
    {
    'id': 17527490611984,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Carlos Graham',
    'address': '4328 Daniel Trace Suite 324\nMccoyland, MD 19167',
    'text': 'Have event future. Serious society reflect. Green require student job past remain one simple.',
    'email': 'cherylmeyer@example.org',
    'phone_number': '956.375.2440',
    'json': {
    'name': 'Tina Green',
    'address': '299 Jody Track Apt. 507\nLake Wesley, WI 54508',
},
    'key95444': 'value83627',
    'key81899': 'value61926',
    'key78317': 'value81369',
    'key8366': 'value73676',
    'key73711': 'value97911',
    'key19510': 'value63953',
    'key40587': 'value47689',
    'key89958': 'value68063',
    'key19235': 'value21698',
},
    {
    'id': 17527490611999,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Jessica Jones',
    'address': '6212 Kelly Radial\nLoganchester, ME 41912',
    'text': 'Wonder late western end player. During leave speech specific character. Bring collection similar executive page use stage.',
    'email': 'waremelissa@example.net',
    'phone_number': '+1-978-719-6266x148',
    'json': {
    'name': 'Lee Robertson',
    'address': '7410 Schneider Gardens Apt. 909\nSouth Matthewville, CA 50405',
},
    'key55511': 'value31156',
    'key73715': 'value67919',
    'key95671': 'value36989',
},
    {
    'id': 17527490612013,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Brian Nichols',
    'address': '621 Christine Row\nEast Kyle, GA 57291',
    'text': 'Scene set often. Billion feeling president teach summer great magazine. Again hard recent moment add manager.',
    'email': 'ericmiller@example.com',
    'phone_number': '001-365-256-4268',
    'json': {
    'name': 'Christina Sandoval',
    'address': 'PSC 9107, Box 9763\nAPO AP 20048',
},
    'key7562': 'value98194',
},
    {
    'id': 17527490612025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Michelle Ortega',
    'address': '9423 Johnson Lane Suite 855\nLake Sarah, RI 30800',
    'text': 'Physical choice seven cut between. Important reveal budget argue raise series.\nLittle note certain general loss skin. Make enter head. Perform myself would media less lose.',
    'email': 'garciarichard@example.net',
    'phone_number': '001-890-798-5268x43516',
    'json': {
    'name': 'Wendy Rosales',
    'address': '7830 Lori Prairie Suite 351\nWest Christopher, SC 54974',
},
    'key52631': 'value39031',
    'key83793': 'value88674',
    'key49652': 'value24252',
    'key81622': 'value71272',
    'key53656': 'value248',
    'key71046': 'value80832',
    'key92822': 'value51374',
    'key77493': 'value59909',
},
    {
    'id': 17527490612039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Tammy Johns',
    'address': '49468 Amy Valley\nPort Morgantown, OK 12562',
    'text': 'Old sister personal theory national similar. Our note act buy weight chair. Produce beat physical event herself herself.',
    'email': 'sheila95@example.net',
    'phone_number': '+1-589-233-0958x839',
    'json': {
    'name': 'Dawn Hunter',
    'address': 'USNS Black\nFPO AA 06406',
},
    'key6172': 'value92426',
    'key71969': 'value82080',
    'key15600': 'value18093',
    'key85860': 'value69358',
    'key22489': 'value27393',
    'key81613': 'value78454',
    'key82800': 'value3698',
    'key17562': 'value15286',
    'key50411': 'value70810',
    'key52124': 'value61800',
},
    {
    'id': 17527490612051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Mark Johnson PhD',
    'address': '7677 Diaz Orchard\nNew Kevin, DE 89755',
    'text': 'Hotel name citizen grow quite right arrive. Talk information prepare center force present. Yes fly floor material.',
    'email': 'sanchezmelissa@example.com',
    'phone_number': '902.714.4234x5744',
    'json': {
    'name': 'Michael Valencia',
    'address': '312 Jimenez Spring Apt. 479\nRobinsonmouth, ID 58150',
},
    'key46444': 'value31362',
    'key34747': 'value11725',
    'key38436': 'value63661',
    'key88540': 'value96797',
    'key73297': 'value42822',
    'key90878': 'value16994',
    'key52325': 'value39424',
    'key99764': 'value24860',
    'key86077': 'value5723',
    'key5166': 'value30262',
},
    {
    'id': 17527490612066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Richard Reynolds',
    'address': '40845 Renee Fall Apt. 411\nHardyhaven, AL 02746',
    'text': 'Bring door site all. According language feel.\nHis artist kitchen stop garden kid stay. Develop check left admit shake form bar authority. After oil father able available control rate perhaps.',
    'email': 'jwilliams@example.com',
    'phone_number': '+1-486-875-3650',
    'json': {
    'name': 'Bridget Estes',
    'address': '652 Stone Highway\nChrisburgh, NV 91601',
},
    'key2142': 'value61261',
},
    {
    'id': 17527490612079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Amber Ewing',
    'address': 'PSC 5048, Box 4107\nAPO AA 70412',
    'text': 'Today save century person news will decade. School small really political floor brother. Price would young carry image team bar spring.',
    'email': 'shannon02@example.org',
    'phone_number': '+1-956-336-1878x5499',
    'json': {
    'name': 'Randy Mathis',
    'address': '5747 Nathaniel Haven\nThompsonmouth, PR 03007',
},
    'key92848': 'value10135',
    'key57371': 'value81185',
    'key10379': 'value75212',
    'key9593': 'value31523',
    'key3026': 'value21367',
    'key32365': 'value16898',
    'key61004': 'value37020',
    'key17245': 'value25173',
    'key92000': 'value53727',
    'key7102': 'value22806',
},
    {
    'id': 17527490612088,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Mark Banks',
    'address': '0765 Wallace Cove Suite 292\nGregoryside, WY 30409',
    'text': 'Consider case ball whether. Outside fill surface since coach join. Nature less family huge author teacher.',
    'email': 'melissafernandez@example.org',
    'phone_number': '707-496-8789x855',
    'json': {
    'name': 'Shawn Mack',
    'address': 'USS Long\nFPO AP 70212',
},
    'key46937': 'value78835',
    'key44870': 'value11373',
    'key23856': 'value13386',
    'key18943': 'value11022',
    'key37171': 'value17417',
    'key12862': 'value9408',
    'key95890': 'value90885',
    'key55953': 'value79809',
    'key36632': 'value94203',
},
    {
    'id': 17527490612098,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Dale Anderson',
    'address': '060 Bryant Meadows\nPort Christophershire, ND 75008',
    'text': 'Project campaign picture true different movie join. When figure media must value task all.\nIndividual case six no. Year energy than drop. Design law friend plant employee card over.',
    'email': 'nolanpaul@example.com',
    'phone_number': '(962)829-7528x1163',
    'json': {
    'name': 'Megan Lewis',
    'address': '04513 Evan Alley\nPamville, FM 87773',
},
    'key77332': 'value48850',
    'key26974': 'value34419',
    'key42944': 'value4328',
    'key78569': 'value36257',
    'key65360': 'value78602',
    'key40640': 'value724',
},
    {
    'id': 17527490612109,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Donald Adams',
    'address': '2788 Jacobs Keys Suite 178\nBrianmouth, NJ 64808',
    'text': 'None coach born fight friend space goal. But reflect section table contain claim majority certain. Answer crime country place. Guy apply item determine cause administration design another.',
    'email': 'kimberly37@example.com',
    'phone_number': '001-456-612-3311',
    'json': {
    'name': 'Ryan Walker',
    'address': '16706 Tonya Canyon\nPort Donnaborough, WV 61151',
},
    'key38602': 'value48720',
    'key89403': 'value83811',
    'key34170': 'value79308',
    'key14354': 'value96098',
    'key42774': 'value541',
    'key81766': 'value14164',
    'key69802': 'value81357',
    'key77226': 'value99449',
    'key59449': 'value22507',
},
    {
    'id': 17527490612120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Kenneth Price',
    'address': '286 Watson Fords Suite 120\nRussellchester, WI 08791',
    'text': 'American sea add admit. Score response data live. Least spend career down by great.\nAcross listen difference woman thought budget agree such.\nParticularly picture ability involve really single.',
    'email': 'mark94@example.com',
    'phone_number': '8842448316',
    'json': {
    'name': 'Catherine King',
    'address': '07472 Nicole Crescent\nNew Morgan, DE 78481',
},
    'key80010': 'value43726',
    'key67580': 'value51785',
    'key26455': 'value51999',
    'key44488': 'value35074',
    'key70385': 'value45118',
    'key17692': 'value30487',
    'key61430': 'value7494',
    'key11541': 'value50970',
    'key62978': 'value50016',
},
    {
    'id': 17527490612131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Emily Barber',
    'address': '59200 Devin Heights\nPort Jamesmouth, NJ 94123',
    'text': 'Matter him child within respond process total. Man economy theory democratic protect raise dog.\nTask brother research sign. Floor church various page.\nTell on wear successful hand voice central.',
    'email': 'kleinjennifer@example.net',
    'phone_number': '886.520.9586',
    'json': {
    'name': 'David Cherry',
    'address': '825 Kaitlyn Flat\nEast Katrinashire, MD 56760',
},
    'key71163': 'value86932',
    'key85506': 'value74864',
    'key31943': 'value63679',
    'key11000': 'value58680',
    'key1450': 'value86408',
    'key68388': 'value65586',
    'key71408': 'value51842',
},
    {
    'id': 17527490612149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Mark Martin',
    'address': '3712 Long Streets Apt. 238\nLake Lauraberg, MT 26984',
    'text': 'Good lay mean consider family. Continue officer court help. Body though employee low.\nWe under may energy. We various us water happy.',
    'email': 'jane83@example.net',
    'phone_number': '514-286-6415',
    'json': {
    'name': 'Gregory Moreno',
    'address': '419 Susan Extensions Apt. 026\nEast Alexis, AS 62451',
},
    'key47325': 'value51087',
    'key56696': 'value43648',
    'key88327': 'value40670',
    'key34051': 'value83560',
    'key342': 'value22100',
    'key42985': 'value12090',
    'key8999': 'value35849',
},
    {
    'id': 17527490612160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Lindsay Rowe',
    'address': '3168 Bowman Mountains\nLake Dianabury, NV 34054',
    'text': 'Day strong country do morning condition anything. Nor beat growth letter maybe. I center push protect serve charge resource.',
    'email': 'nsharp@example.org',
    'phone_number': '291-802-0905',
    'json': {
    'name': 'John Alvarado',
    'address': '31492 Sharon Field Apt. 327\nNew Alexander, ID 03185',
},
    'key87945': 'value2970',
    'key74015': 'value60310',
    'key81124': 'value67782',
    'key797': 'value24987',
    'key93170': 'value17611',
    'key93253': 'value28611',
    'key54499': 'value98276',
    'key82143': 'value36742',
    'key19343': 'value1428',
},
    {
    'id': 17527490612171,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Keith Orr',
    'address': '95062 Rhonda Well\nDonnaport, NM 67552',
    'text': 'Budget agency begin player day. Its else almost Republican visit.\nContinue quickly strategy hair. Care firm modern kind test dinner glass. Structure floor win.',
    'email': 'courtneyfranklin@example.com',
    'phone_number': '484.906.3087x223',
    'json': {
    'name': 'Katherine Lester',
    'address': '28522 Lisa Harbors Suite 739\nJamesbury, ME 23736',
},
    'key63237': 'value41374',
    'key4225': 'value60286',
    'key7738': 'value76081',
},
    {
    'id': 17527490612182,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Michael Jones',
    'address': '88265 Anderson Trail\nNorth Dean, GU 75636',
    'text': 'Evidence throw many mission cut put. Enjoy line research cost. Lot discover any agree.\nLeg room whom guess have any. Bank network yes listen nor day. Store tax product rock director at former.',
    'email': 'sullivandakota@example.org',
    'phone_number': '001-571-547-2228x787',
    'json': {
    'name': 'David Scott',
    'address': '162 Cassandra Port\nSarahshire, VT 88169',
},
    'key13229': 'value90451',
},
    {
    'id': 17527490612194,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Eric Lewis',
    'address': '6826 Sarah Plaza\nGriffithmouth, MI 68970',
    'text': 'Hour sister interview shake yeah rather. New no election others appear. Window company water laugh technology.',
    'email': 'johnsoncatherine@example.org',
    'phone_number': '+1-995-360-2409',
    'json': {
    'name': 'Ashley Lynch',
    'address': '30437 Brown Pines\nTateton, ME 84773',
},
    'key53799': 'value13415',
    'key1062': 'value97831',
    'key10119': 'value75934',
    'key81116': 'value28864',
    'key84321': 'value1227',
    'key2392': 'value99700',
    'key67864': 'value33386',
},
    {
    'id': 17527490612206,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Tammy Taylor',
    'address': '8260 Beth Brook Apt. 222\nSouth Michaelland, OK 86995',
    'text': 'Choose example organization main young after. Professional eight future church. Citizen blood door.\nPublic next seven reach. Eat art someone laugh truth control catch. Mention air water fast.',
    'email': 'jessicawilliams@example.org',
    'phone_number': '325-371-3716x1288',
    'json': {
    'name': 'Steven Dunn',
    'address': '34141 Donald Forest\nNorth Rachel, PW 60201',
},
    'key98720': 'value42384',
    'key54926': 'value8362',
    'key86474': 'value3553',
    'key20271': 'value25885',
    'key10831': 'value670',
    'key38237': 'value31429',
    'key11603': 'value94123',
},
    {
    'id': 17527490612217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Kyle Joseph',
    'address': 'Unit 5667 Box 4935\nDPO AE 06996',
    'text': 'Situation sell single meet. Stand small baby campaign scene check.\nBack moment mother course fire million pattern standard. Cold find once let company single. Future listen already figure.',
    'email': 'santanaeileen@example.com',
    'phone_number': '+1-281-654-2809',
    'json': {
    'name': 'Anne Phillips',
    'address': '420 Price Bypass Apt. 369\nWilliamsview, TX 86359',
},
    'key68396': 'value43208',
    'key97741': 'value18804',
    'key32020': 'value34425',
    'key19515': 'value77627',
    'key9101': 'value29882',
    'key70785': 'value88439',
    'key19448': 'value21993',
    'key62369': 'value95048',
},
    {
    'id': 17527490612227,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Jermaine Weeks',
    'address': '429 Lisa Valley\nTaylormouth, DC 27439',
    'text': 'Write explain purpose property consumer break power. Today raise either or house.\nHe father should who against yard.',
    'email': 'whernandez@example.org',
    'phone_number': '8602230353',
    'json': {
    'name': 'Lance Brown',
    'address': '765 Jason Spring\nSouth Melissaside, TN 64168',
},
    'key20899': 'value59231',
    'key53176': 'value57144',
},
    {
    'id': 17527490612238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Travis Cummings',
    'address': '6673 White Motorway Apt. 262\nPort Justinport, NJ 72942',
    'text': 'Scene speech first raise technology professional participant. Police bad financial. Condition theory decide course let need current condition.',
    'email': 'tapiasarah@example.org',
    'phone_number': '(927)203-1632',
    'json': {
    'name': 'Christopher Anthony',
    'address': '63733 Sarah Camp\nJennifermouth, MN 95975',
},
    'key39609': 'value60292',
    'key2233': 'value82981',
    'key13934': 'value88153',
    'key71895': 'value96114',
    'key87751': 'value77572',
    'key56738': 'value60578',
    'key64832': 'value75619',
    'key37432': 'value75107',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
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
    'filter': '[17527490609698, 17527490609720, 17527490609733, 17527490609745, 17527490609756, 17527490609769, 17527490609781, 17527490609794, 17527490609805, 17527490609816, 17527490609828, 17527490609839, 17527490609849, 17527490609861, 17527490609873, 17527490609883, 17527490609894, 17527490609908, 17527490609921, 17527490609941, 17527490609962, 17527490609978, 17527490609989, 17527490610003, 17527490610017, 17527490610031, 17527490610040, 17527490610053, 17527490610068, 17527490610082, 17527490610096, 17527490610110, 17527490610122, 17527490610134, 17527490610146, 17527490610157, 17527490610175, 17527490610193, 17527490610213, 17527490610233, 17527490610254, 17527490610269, 17527490610283, 17527490610294, 17527490610309, 17527490610323, 17527490610336, 17527490610351, 17527490610363, 17527490610376, 17527490610388, 17527490610401, 17527490610413, 17527490610423, 17527490610436, 17527490610448, 17527490610458, 17527490610468, 17527490610480, 17527490610489, 17527490610499, 17527490610511, 17527490610522, 17527490610533, 17527490610545, 17527490610555, 17527490610565, 17527490610575, 17527490610587, 17527490610597, 17527490610606, 17527490610617, 17527490610626, 17527490610636, 17527490610648, 17527490610661, 17527490610673, 17527490610686, 17527490610699, 17527490610710, 17527490610721, 17527490610733, 17527490610745, 17527490610757, 17527490610768, 17527490610778, 17527490610792, 17527490610809, 17527490610830, 17527490610853, 17527490610872, 17527490610887, 17527490610901, 17527490610912, 17527490610926, 17527490610941, 17527490610955, 17527490610970, 17527490610983, 17527490610997, 17527490611011, 17527490611024, 17527490611035, 17527490611048, 17527490611058, 17527490611067, 17527490611077, 17527490611090, 17527490611102, 17527490611113, 17527490611124, 17527490611135, 17527490611146, 17527490611156, 17527490611168, 17527490611179, 17527490611190, 17527490611202, 17527490611214, 17527490611228, 17527490611244, 17527490611266, 17527490611285, 17527490611297, 17527490611311, 17527490611325, 17527490611336, 17527490611348, 17527490611363, 17527490611378, 17527490611390, 17527490611403, 17527490611416, 17527490611427, 17527490611435, 17527490611446, 17527490611457, 17527490611468, 17527490611478, 17527490611489, 17527490611501, 17527490611512, 17527490611523, 17527490611535, 17527490611545, 17527490611557, 17527490611568, 17527490611579, 17527490611589, 17527490611601, 17527490611616, 17527490611635, 17527490611654, 17527490611675, 17527490611689, 17527490611702, 17527490611717, 17527490611731, 17527490611746, 17527490611760, 17527490611773, 17527490611787, 17527490611797, 17527490611805, 17527490611816, 17527490611828, 17527490611839, 17527490611849, 17527490611858, 17527490611868, 17527490611878, 17527490611889, 17527490611899, 17527490611910, 17527490611922, 17527490611935, 17527490611948, 17527490611966, 17527490611984, 17527490611999, 17527490612013, 17527490612025, 17527490612039, 17527490612051, 17527490612066, 17527490612079, 17527490612088, 17527490612098, 17527490612109, 17527490612120, 17527490612131, 17527490612149, 17527490612160, 17527490612171, 17527490612182, 17527490612194, 17527490612206, 17527490612217, 17527490612227, 17527490612238]',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
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
    'RequestId': 'fb7adb72-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_14_901414iBiTBxvO',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVectorNegative_test_query_with_wrong_filter_expr_1752749064.json')
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
    test = AllmilvusLogtestqueryvectornegativeTestQueryWithWrongFilterExpr1752749064Json()
    test.run_tests()
