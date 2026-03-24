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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-10+20 <= uid < 20+30]_1752748865_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-10+20 <= uid < 20+30]_1752748865.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalse1020Uid20301752748865Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-10+20 <= uid < 20+30]_1752748865.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-10+20 <= uid < 20+30]_1752748865.json"
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
    'data': [
    {
    'id': 17527488575009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Molly Castaneda',
    'address': '872 Williams Points\nEast Daniel, RI 31678',
    'text': 'Play goal president else late want daughter expert. Professor indeed magazine today lay back. Machine treat character level necessary provide.',
    'email': 'wendyaguilar@example.com',
    'phone_number': '+1-519-989-7217x597',
    'json': {
    'name': 'Wesley Jones',
    'address': '36976 Jones Pine Suite 862\nJohnsonchester, PA 32594',
},
    'key53774': 'value20899',
    'key17815': 'value41859',
    'key41607': 'value69783',
    'key31312': 'value87176',
    'key4271': 'value12336',
    'key23637': 'value63131',
    'key55916': 'value48064',
    'key91971': 'value27049',
    'key28766': 'value86904',
},
    {
    'id': 17527488575027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Michael King',
    'address': '19508 Brennan Corner Suite 103\nCastilloland, FM 42568',
    'text': 'Wait think read report. East drop hard dark measure lot though pull.\nThreat for firm miss fine save. Begin news interview.',
    'email': 'judyallison@example.org',
    'phone_number': '948.613.5652x66645',
    'json': {
    'name': 'Steven Jackson',
    'address': '31829 Christopher Underpass Apt. 396\nKinghaven, KS 85818',
},
    'key8234': 'value53195',
    'key84345': 'value55166',
    'key61199': 'value91125',
    'key18325': 'value89955',
    'key55203': 'value49383',
    'key39727': 'value83166',
    'key16908': 'value88024',
},
    {
    'id': 17527488575042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Steven Rogers',
    'address': '584 Boyd Glen Apt. 026\nSouth Robert, NE 98720',
    'text': 'Chair upon past cost everything parent fast. Return movie travel direction meet.\nCall detail market religious what tend collection. Tell recent life nothing employee. Right election risk realize.',
    'email': 'scasey@example.net',
    'phone_number': '569.614.4825',
    'json': {
    'name': 'Alex Wong',
    'address': '379 Gibbs Throughway Apt. 323\nWest David, PR 27167',
},
    'key270': 'value81009',
    'key2904': 'value22311',
    'key50316': 'value43332',
    'key22490': 'value40661',
},
    {
    'id': 17527488575056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Emma Jordan',
    'address': 'PSC 1231, Box 4092\nAPO AA 23058',
    'text': 'Stand paper sing certain husband today them. Republican rate bad across. Scientist them drug quite over.',
    'email': 'owalker@example.org',
    'phone_number': '6832134403',
    'json': {
    'name': 'Matthew Smith',
    'address': '18229 Joshua Road Suite 042\nPort Andrewmouth, IA 78469',
},
    'key8419': 'value62834',
    'key65479': 'value84837',
    'key58226': 'value246',
},
    {
    'id': 17527488575066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Allen Daniel',
    'address': '69968 York Court\nPerrymouth, VI 41805',
    'text': 'Always training save air especially generation bring.\nSuch seek friend child family once else red. Prove just hard eight way.',
    'email': 'alexanderjones@example.net',
    'phone_number': '4424133482',
    'json': {
    'name': 'Michael Gallagher',
    'address': 'USS Boyd\nFPO AP 27145',
},
    'key49357': 'value78626',
    'key54531': 'value67614',
    'key84681': 'value66595',
    'key63912': 'value7732',
    'key54615': 'value8747',
},
    {
    'id': 17527488575080,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Leah Wolf',
    'address': '6899 Manning Port Apt. 047\nPort Carmenport, TN 17830',
    'text': 'Side financial want. Mrs color boy court.\nBuild condition respond treatment put scientist agreement. Stop process move he goal true. Garden east professor guy before building office.',
    'email': 'david07@example.com',
    'phone_number': '+1-772-803-3806',
    'json': {
    'name': 'David Carey',
    'address': '63812 Bryan Ports Apt. 044\nEast Michaelfort, PW 58447',
},
    'key44279': 'value19496',
    'key58477': 'value98016',
    'key48085': 'value64497',
    'key89488': 'value37007',
    'key44944': 'value25877',
    'key37432': 'value94049',
    'key68311': 'value63134',
    'key51087': 'value8486',
    'key63740': 'value15470',
},
    {
    'id': 17527488575093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'David Oneal',
    'address': '511 Higgins Alley Suite 362\nMolinaburgh, MT 23401',
    'text': 'Show spend until door sure scientist three. Piece stay consider I teach myself. Fast TV strong.\nTelevision time red ago test important. Improve side successful.',
    'email': 'ashley80@example.net',
    'phone_number': '001-525-675-4024x0762',
    'json': {
    'name': 'Gregory Arias',
    'address': '73854 Ashley Avenue\nReginaldchester, IL 50354',
},
    'key34850': 'value13189',
    'key44082': 'value76270',
    'key75665': 'value3514',
},
    {
    'id': 17527488575105,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Kelli Harper',
    'address': '6576 Kelly Hills Suite 988\nLake Stephanie, MN 97964',
    'text': 'Marriage deal despite general rule trial some. Front suffer wait. He challenge western various north admit.\nNever white yes compare. Pick different late west. Truth now detail own policy often.',
    'email': 'amylowe@example.com',
    'phone_number': '375-403-3253x8688',
    'json': {
    'name': 'Michael Salazar',
    'address': '43415 Bishop Divide Apt. 890\nRobertsburgh, NY 05837',
},
    'key14611': 'value80342',
},
    {
    'id': 17527488575118,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Sara Cunningham',
    'address': '72568 Tony Ramp Suite 712\nEast Linda, ND 98300',
    'text': 'Road point enjoy trouble coach. Stock deal pick from a past. Participant real feeling hot information perform.\nReady already vote itself house.',
    'email': 'taylorkelly@example.com',
    'phone_number': '386.390.5618x1013',
    'json': {
    'name': 'Erika Livingston',
    'address': '1525 Gordon Turnpike Suite 467\nJonathanshire, MA 43337',
},
    'key43472': 'value46546',
    'key49599': 'value54219',
    'key88624': 'value3375',
    'key51386': 'value69043',
    'key43903': 'value43884',
    'key76525': 'value88517',
    'key49461': 'value17644',
    'key18691': 'value11350',
    'key34203': 'value93918',
    'key63756': 'value67281',
},
    {
    'id': 17527488575130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Katherine Mcgee',
    'address': '07804 Brown Drive\nLake Deniseside, VT 21758',
    'text': 'Morning pressure step member never guess how.\nBase research main natural white defense imagine.\nMean beautiful evening either hotel series herself anything. Chance together low up point.',
    'email': 'christinemcfarland@example.net',
    'phone_number': '348-761-9153',
    'json': {
    'name': 'Tiffany Lopez',
    'address': '99293 Fisher Square Apt. 200\nNorth Catherineport, AK 65614',
},
    'key45394': 'value14332',
    'key942': 'value9393',
    'key51138': 'value36947',
},
    {
    'id': 17527488575143,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Tiffany Harris',
    'address': 'Unit 9710 Box 5447\nDPO AE 36277',
    'text': 'Can summer member good born. Sometimes quality affect prevent research strong. Reach away you service training.',
    'email': 'susan79@example.net',
    'phone_number': '+1-715-980-5098x0532',
    'json': {
    'name': 'Shelley Gonzalez',
    'address': '3971 Elizabeth Forest Apt. 049\nEast Steven, NE 53834',
},
    'key73785': 'value50664',
    'key20969': 'value82562',
    'key67363': 'value85432',
    'key31779': 'value43108',
    'key13921': 'value65184',
    'key28559': 'value71114',
},
    {
    'id': 17527488575152,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Carrie Salazar',
    'address': '7396 Tony Spur Apt. 553\nEast Elizabethton, IN 53405',
    'text': 'Result entire social part police fall for. Century marriage one but charge us.\nWind wear far maybe Republican whom politics. Truth turn save nice dog take lead yard.',
    'email': 'zlane@example.org',
    'phone_number': '+1-918-944-1840x751',
    'json': {
    'name': 'Christine Kelley',
    'address': '834 Tiffany Squares\nAllenmouth, DE 85710',
},
    'key84975': 'value48070',
    'key75701': 'value25930',
    'key69697': 'value34641',
    'key45413': 'value77675',
    'key58541': 'value29406',
    'key12311': 'value1610',
    'key26711': 'value17467',
},
    {
    'id': 17527488575164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Melinda Hill',
    'address': 'PSC 1708, Box 9434\nAPO AP 27365',
    'text': 'Note finish market road return. Table man throw story news over.\nNext officer simply staff. Mention age establish together raise learn.',
    'email': 'wrightsusan@example.net',
    'phone_number': '(387)921-1428x707',
    'json': {
    'name': 'Brian Maddox',
    'address': '854 Wilcox Points\nPort Richard, ND 02643',
},
    'key6085': 'value5057',
    'key26476': 'value91667',
    'key71534': 'value36419',
    'key13023': 'value99934',
    'key17187': 'value66601',
    'key48724': 'value67339',
    'key45547': 'value49246',
    'key17536': 'value43691',
    'key98041': 'value72463',
    'key72198': 'value28866',
},
    {
    'id': 17527488575175,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Sabrina Davis',
    'address': 'PSC 1989, Box 2176\nAPO AP 50949',
    'text': 'Month industry learn billion. Collection form single hope beyond hand him. More responsibility or after member huge.',
    'email': 'cookgregory@example.org',
    'phone_number': '298.636.9308x8274',
    'json': {
    'name': 'Matthew Martin',
    'address': '298 Julie Park\nFrancisland, AR 18287',
},
    'key7285': 'value74653',
    'key22220': 'value64397',
    'key99692': 'value17253',
    'key42893': 'value25156',
},
    {
    'id': 17527488575185,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Whitney Evans',
    'address': '6859 Nicholas Stream\nSmithview, AS 14868',
    'text': 'Speak appear skin system certain movie. Purpose goal side doctor Democrat indicate.\nNow notice consumer once happy body wish box. Responsibility let part give surface require.',
    'email': 'carolynfarmer@example.net',
    'phone_number': '001-203-300-1079x1539',
    'json': {
    'name': 'Julia Hughes',
    'address': '2936 Lewis Crescent Apt. 288\nPaynefurt, MP 16628',
},
    'key97124': 'value49988',
    'key88247': 'value73444',
    'key29109': 'value93309',
},
    {
    'id': 17527488575198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Dr. Shawn Wilson Jr.',
    'address': '8742 Kristina Cove Apt. 223\nEast Jerryville, NJ 85143',
    'text': 'View manager card few including car arrive. Star wish probably. Game arm take could really. Reveal sport south five happy.\nStructure that eye radio themselves quite speak. Plant way already speak.',
    'email': 'brian28@example.net',
    'phone_number': '(605)996-9161',
    'json': {
    'name': 'Stephen Benitez',
    'address': '9856 Sandra Neck Apt. 523\nLaurafort, TN 47320',
},
    'key86686': 'value63307',
    'key31700': 'value75173',
    'key15863': 'value36435',
    'key35248': 'value11405',
    'key55169': 'value95130',
    'key63325': 'value73585',
    'key65621': 'value45452',
},
    {
    'id': 17527488575211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'April Fitzpatrick',
    'address': '521 Martin Unions Apt. 948\nTaylorchester, MS 32111',
    'text': 'Color network west whom account good order stay. Least occur both this market talk. Company plan increase thank.',
    'email': 'jose76@example.org',
    'phone_number': '(472)429-1300x15087',
    'json': {
    'name': 'Alyssa Aguilar',
    'address': '557 Mullins Springs Suite 194\nLake Margaretland, AR 53713',
},
    'key88484': 'value18531',
    'key78764': 'value96001',
    'key96191': 'value25018',
    'key88928': 'value17043',
    'key64786': 'value56699',
    'key52188': 'value48424',
    'key68045': 'value48976',
    'key47567': 'value63846',
},
    {
    'id': 17527488575225,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Todd Wilson',
    'address': '66760 Ashley Cliffs Apt. 011\nBlackport, IN 98633',
    'text': 'Sure rock point really place. Present head book discussion whole risk plan.\nBetter field new onto. Improve third hard yourself heavy professor assume fast. Light development possible fear.',
    'email': 'virginia45@example.org',
    'phone_number': '(547)597-2586',
    'json': {
    'name': 'David Morales',
    'address': '245 Amber Mountains\nWest Garyshire, WY 59327',
},
    'key17054': 'value93844',
    'key28487': 'value75232',
    'key62482': 'value74734',
    'key1421': 'value31577',
    'key67448': 'value19028',
    'key5073': 'value58261',
    'key15301': 'value25146',
},
    {
    'id': 17527488575238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Anthony Hubbard',
    'address': '80141 Thompson Green Apt. 949\nNew Samantha, AS 68151',
    'text': 'Huge choose foot how fund get stop. Fall animal catch pick. Lead sing art bank participant concern.\nNumber traditional man boy human. Include build nearly myself war. During bring it add her.',
    'email': 'terrence80@example.net',
    'phone_number': '9692667457',
    'json': {
    'name': 'Stephen Aguirre',
    'address': '76461 Gardner Forge\nNorth Xavier, WV 92362',
},
    'key45884': 'value47557',
},
    {
    'id': 17527488575250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Samantha Young',
    'address': '0854 Phillips Avenue Suite 364\nPort Elizabeth, AL 03977',
    'text': 'Civil wife easy clearly agree. Smile PM security mission issue source. Live player tonight.',
    'email': 'donald08@example.com',
    'phone_number': '(293)616-7061x8679',
    'json': {
    'name': 'Alison Hansen',
    'address': 'PSC 0396, Box 2374\nAPO AP 23356',
},
    'key22935': 'value37879',
    'key2338': 'value47181',
    'key96052': 'value13762',
    'key37978': 'value54841',
    'key26387': 'value92455',
    'key5715': 'value30756',
    'key64415': 'value1546',
    'key30082': 'value90581',
    'key47918': 'value28086',
},
    {
    'id': 17527488575260,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Alexandra Gilbert',
    'address': '3625 Mccormick Ports\nSusanmouth, VT 12429',
    'text': 'Each discuss push join size national. Budget dark place particular truth practice draw firm. Business home experience only. Value bank floor game.',
    'email': 'iadams@example.org',
    'phone_number': '(861)263-6094',
    'json': {
    'name': 'Rhonda Nelson',
    'address': 'USS Love\nFPO AA 16012',
},
    'key11057': 'value4421',
    'key99041': 'value45999',
},
    {
    'id': 17527488575270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Amy Jones',
    'address': '0432 Jessica Landing Suite 224\nHallfort, GU 64764',
    'text': 'Old responsibility whole ready exactly. Act year never seat forget once above. Himself song truth bad.',
    'email': 'akaiser@example.org',
    'phone_number': '868.558.7628',
    'json': {
    'name': 'Mary Johnson',
    'address': '89853 Gregory Views Suite 960\nTranport, AS 72163',
},
    'key79595': 'value38017',
    'key38391': 'value83262',
    'key87396': 'value62654',
    'key98300': 'value35543',
},
    {
    'id': 17527488575281,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Luke Burns',
    'address': '956 Richardson Fords\nNew Jefferymouth, GA 92346',
    'text': 'Bring to something resource. Prove ok discover be. Anyone hot want concern.\nBlood every form sometimes me foot onto everyone. System training listen authority tax garden.',
    'email': 'ortizjason@example.org',
    'phone_number': '+1-972-983-9538x53561',
    'json': {
    'name': 'Steven Lambert',
    'address': 'PSC 1102, Box 0311\nAPO AP 14780',
},
    'key21024': 'value79452',
    'key60047': 'value69106',
    'key47458': 'value29661',
    'key99887': 'value25146',
    'key35897': 'value71479',
    'key8912': 'value31936',
    'key84281': 'value51330',
    'key32864': 'value13762',
    'key15047': 'value11054',
    'key73357': 'value88265',
},
    {
    'id': 17527488575291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Brenda Reid',
    'address': '925 Henson Islands Suite 934\nPort Saraside, AL 20866',
    'text': 'Identify entire same few new dog garden. Picture even allow according toward Republican one.',
    'email': 'jskinner@example.com',
    'phone_number': '956-323-1178x740',
    'json': {
    'name': 'David Gibson',
    'address': '4774 Sweeney Highway\nDerrickhaven, ID 57625',
},
    'key65114': 'value53553',
},
    {
    'id': 17527488575301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Sarah Wood',
    'address': 'Unit 7795 Box 2905\nDPO AP 63310',
    'text': 'Usually summer foreign chair. Mission show according several apply.\nPlant world suggest.\nFinish more popular court yeah perform. Prepare matter product prove total.',
    'email': 'james85@example.com',
    'phone_number': '001-719-835-0601x9406',
    'json': {
    'name': 'Maria Moore',
    'address': '2253 Hoffman Oval Suite 803\nLake Robertstad, KY 13546',
},
    'key3961': 'value59681',
    'key56417': 'value34457',
    'key72517': 'value38902',
    'key62200': 'value87423',
    'key23860': 'value83589',
    'key92188': 'value23057',
},
    {
    'id': 17527488575310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Michael Blair',
    'address': '196 Thomas Bypass Suite 694\nPort Lance, AS 55080',
    'text': 'Stop old actually animal task. Summer sister clearly father. Without station politics school center toward hope center.',
    'email': 'parkerjohn@example.net',
    'phone_number': '(834)723-0176x32936',
    'json': {
    'name': 'Stacey Peterson',
    'address': '01601 Todd Port Apt. 414\nRodriguezside, AS 92269',
},
    'key32303': 'value35500',
    'key44792': 'value18504',
    'key51502': 'value18236',
    'key15251': 'value93234',
    'key5778': 'value38846',
    'key95757': 'value90702',
    'key55591': 'value72666',
    'key20778': 'value82566',
},
    {
    'id': 17527488575322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Kevin Price',
    'address': '5600 Chelsea Flat Suite 845\nMarkland, MI 50880',
    'text': 'Deal break there big laugh however. Knowledge practice manage someone memory. Buy participant gas scientist describe west.',
    'email': 'gho@example.net',
    'phone_number': '001-667-655-0553',
    'json': {
    'name': 'Ryan Moore',
    'address': '855 Jones Parks Apt. 610\nNew Victoriabury, AS 54748',
},
    'key20890': 'value78963',
    'key63976': 'value80590',
    'key3981': 'value38261',
},
    {
    'id': 17527488575332,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Patricia Mcdonald',
    'address': '27047 Christine Islands\nNorth Joy, IN 99754',
    'text': 'One down safe soon stuff leg. Water business most it. Site measure region PM focus sit.\nSpace nature whose international leg human guy. Moment put lot right voice. Kind no network executive some.',
    'email': 'jacobwelch@example.com',
    'phone_number': '(534)954-4739',
    'json': {
    'name': 'Joseph Whitney',
    'address': '4440 Nicholas Summit Apt. 047\nNorth Michaelshire, WY 75162',
},
    'key42909': 'value99552',
    'key37468': 'value81580',
    'key93': 'value70128',
    'key6046': 'value90311',
    'key24758': 'value8216',
    'key61690': 'value78676',
    'key76453': 'value5668',
},
    {
    'id': 17527488575344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Stephanie Hernandez',
    'address': '4156 Alexandria Circles\nWest Corymouth, OH 03343',
    'text': 'Executive speak stage response office doctor test. Television stock reveal require discuss. Still tonight rock successful indeed develop keep.',
    'email': 'towens@example.net',
    'phone_number': '(608)881-3612',
    'json': {
    'name': 'Charles Maxwell',
    'address': 'USNS Andersen\nFPO AE 36574',
},
    'key81408': 'value6108',
    'key12013': 'value94880',
    'key60354': 'value74631',
    'key68910': 'value97827',
    'key66591': 'value46502',
    'key79586': 'value39309',
    'key61531': 'value44063',
    'key9920': 'value88148',
},
    {
    'id': 17527488575353,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Cheryl King',
    'address': '48681 Paul Courts\nWest Virginiafort, DC 15714',
    'text': 'Mother majority business unit similar contain. Little campaign blue produce. Speak sell majority law skin.\nTrue everybody even seek have item. Nothing have good wear morning.',
    'email': 'danielcantu@example.org',
    'phone_number': '+1-862-873-8201x885',
    'json': {
    'name': 'Kevin Ritter',
    'address': '4377 Valencia Rue Apt. 117\nMillsborough, OK 33217',
},
    'key8524': 'value28675',
    'key37611': 'value62656',
    'key54323': 'value49309',
    'key8810': 'value11967',
    'key74267': 'value23296',
    'key42808': 'value12509',
},
    {
    'id': 17527488575364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Keith Rivera',
    'address': '5357 Kyle Shore Suite 178\nSamanthatown, PW 90505',
    'text': 'Feel machine test range play. When edge medical southern structure person. Opportunity sound under management development cultural likely.',
    'email': 'mike35@example.com',
    'phone_number': '(261)715-0377',
    'json': {
    'name': 'Mark Gonzalez',
    'address': '582 Roger Union Apt. 549\nEast John, NC 73021',
},
    'key46060': 'value85696',
    'key11429': 'value66338',
    'key1451': 'value62859',
    'key62870': 'value77979',
    'key11326': 'value69429',
},
    {
    'id': 17527488575374,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Joseph Young',
    'address': '1241 Young Via Apt. 910\nEast Jenniferhaven, TN 70961',
    'text': 'Allow contain Republican door trial artist. Attorney less important age.\nPolitical choice source push building. West behind large part within seat cultural. Much measure civil sound.',
    'email': 'brianhutchinson@example.net',
    'phone_number': '760.258.3863x06367',
    'json': {
    'name': 'Jeff Santiago',
    'address': '15884 Wendy Roads\nLynnstad, PR 44665',
},
    'key61588': 'value97602',
    'key23180': 'value99007',
    'key528': 'value3290',
    'key19473': 'value57520',
    'key78246': 'value94386',
},
    {
    'id': 17527488575385,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Rebecca Henry',
    'address': '4682 Flores Squares Apt. 078\nBurtonbury, ME 29781',
    'text': 'Too month standard up issue become focus nor. True rather leg life leave near. Do according four thousand purpose development section.',
    'email': 'kellylloyd@example.com',
    'phone_number': '(901)298-3503x3434',
    'json': {
    'name': 'Carolyn Hansen',
    'address': 'Unit 8388 Box 8280\nDPO AP 97015',
},
    'key13841': 'value8018',
    'key48986': 'value70513',
    'key49059': 'value14490',
},
    {
    'id': 17527488575394,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kevin Schultz',
    'address': '7296 Beth Loop\nReyesberg, GA 18061',
    'text': 'Reality threat laugh experience scientist between. Lose media firm down conference modern.\nFine exactly stage mother certain. She expert process minute.',
    'email': 'smithjohn@example.com',
    'phone_number': '+1-826-926-0842',
    'json': {
    'name': 'Thomas Hunt',
    'address': '531 Michele Rest Suite 727\nNew Donnamouth, IL 49734',
},
    'key41434': 'value75364',
    'key41804': 'value98789',
    'key72876': 'value91721',
},
    {
    'id': 17527488575405,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Dr. Jodi Martin MD',
    'address': '0837 Montoya Squares\nVictoriachester, TN 58736',
    'text': 'Serious about per enough no by. According human others just allow cause.\nHowever join front. Rather top special create art daughter foot even. Land force his.',
    'email': 'paulholt@example.com',
    'phone_number': '+1-964-327-7430x6994',
    'json': {
    'name': 'Traci Boyd',
    'address': '2664 Miller Place Apt. 501\nJeffreyborough, IL 18197',
},
    'key31000': 'value12929',
    'key13345': 'value6267',
    'key74226': 'value25244',
    'key9059': 'value64388',
    'key178': 'value78954',
    'key50198': 'value6727',
    'key20864': 'value47715',
    'key80881': 'value49754',
    'key85769': 'value34951',
    'key23425': 'value28762',
},
    {
    'id': 17527488575417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Emily Simon',
    'address': '11133 Ashley Cliff\nSouth Seanstad, MT 61793',
    'text': 'Course far quality wife edge best we. Tax also agency exist. Successful little nation nearly.\nBig effort recognize another forward. Drop impact trade.',
    'email': 'youngstephanie@example.com',
    'phone_number': '339.949.8818x1424',
    'json': {
    'name': 'Richard Brown',
    'address': '2246 Mitchell Parks Apt. 699\nFloydberg, NH 58879',
},
    'key19833': 'value78904',
},
    {
    'id': 17527488575429,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'William Robinson',
    'address': '315 Jimenez Burgs\nStephaniemouth, SC 35453',
    'text': 'Its hit family believe surface. Grow new although school size behavior born.\nDetermine enter professional for thus. Hotel blue tend probably cover happy.',
    'email': 'smithjohn@example.net',
    'phone_number': '654.478.6612x41813',
    'json': {
    'name': 'Angela Rowland',
    'address': '4951 Julia Course\nRosshaven, VT 57358',
},
    'key31670': 'value32539',
    'key87971': 'value1823',
    'key51397': 'value24022',
    'key74179': 'value82699',
},
    {
    'id': 17527488575440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Courtney Lane',
    'address': '7754 Weiss Road Apt. 536\nMedinaport, FL 37623',
    'text': 'Quality material seem a break.\nSection hear raise. Off poor life reduce in over.\nMagazine seek weight focus quickly range. Difficult candidate feeling idea everybody including method.',
    'email': 'adam15@example.org',
    'phone_number': '8352160983',
    'json': {
    'name': 'Joseph Kelley',
    'address': '136 Ware Squares Apt. 351\nWest Nicole, OR 09868',
},
    'key84291': 'value40267',
    'key81992': 'value90993',
    'key927': 'value81030',
    'key28431': 'value59944',
    'key17354': 'value49982',
    'key42472': 'value88557',
    'key6887': 'value53036',
},
    {
    'id': 17527488575451,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Nicholas Thomas',
    'address': 'Unit 7593 Box 3174\nDPO AE 65211',
    'text': 'Huge continue worry skill final. Blood game really teacher identify wish positive. Least must thank just least enjoy.',
    'email': 'zjohnson@example.org',
    'phone_number': '001-234-467-3344x10828',
    'json': {
    'name': 'Cody Bailey',
    'address': '3157 Watson Inlet\nSouth Jessicamouth, FM 04945',
},
    'key10115': 'value81513',
    'key18696': 'value90159',
    'key67869': 'value47824',
},
    {
    'id': 17527488575460,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Christopher Williams',
    'address': '41372 Brittney Land Suite 852\nJohnsonstad, OK 30527',
    'text': 'Hard perform within ask natural recently. Enjoy ten traditional evening write. Gas real here adult. Truth consider range investment.',
    'email': 'nelsonsharon@example.com',
    'phone_number': '626.888.3720',
    'json': {
    'name': 'Kelsey Mason',
    'address': '1393 Gregory Rue Apt. 111\nSusanfurt, AS 37051',
},
    'key86308': 'value60553',
    'key71590': 'value88226',
    'key12625': 'value99648',
    'key34710': 'value94632',
    'key76463': 'value40340',
    'key83013': 'value43488',
    'key73893': 'value24779',
    'key27741': 'value99113',
    'key43530': 'value52196',
},
    {
    'id': 17527488575471,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Anthony Smith',
    'address': 'USNV Fischer\nFPO AE 52015',
    'text': 'Movie truth history increase so human. Situation both dinner help instead.\nAvailable from capital still.\nBig get show what find will Congress. Edge state include third development decade.',
    'email': 'chad23@example.org',
    'phone_number': '+1-466-797-3861x499',
    'json': {
    'name': 'John Braun',
    'address': '744 Lewis Knoll\nHernandezshire, ND 37790',
},
    'key60269': 'value92981',
    'key69304': 'value27178',
    'key2712': 'value99310',
},
    {
    'id': 17527488575481,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Catherine Brown',
    'address': '64584 Mary Mill\nMorrisport, FM 05588',
    'text': 'Rich pretty guess.\nProgram that plant structure relate.\nFull best man. Standard air experience possible already player.\nNewspaper pretty west floor only new. Bank certainly particular.',
    'email': 'waltondonna@example.org',
    'phone_number': '358-595-0524',
    'json': {
    'name': 'Kim Pierce',
    'address': '273 Sanchez Lake\nNew Marcus, OK 79617',
},
    'key923': 'value90271',
    'key5762': 'value5430',
    'key93223': 'value56276',
    'key55863': 'value407',
    'key43933': 'value10217',
    'key36155': 'value381',
},
    {
    'id': 17527488575493,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Gerald Hill',
    'address': '52689 Charles Divide Suite 021\nSouth Joshua, WY 34743',
    'text': 'Mention business southern drive gun particularly any. Wonder also role close boy. Government ground occur policy.\nScene environment religious control. Let key current mouth paper.',
    'email': 'kennethkrueger@example.net',
    'phone_number': '384.617.1894x579',
    'json': {
    'name': 'Mario Adams',
    'address': '331 Ryan Forges\nEast Rogerville, IN 41900',
},
    'key97956': 'value8285',
    'key3761': 'value50708',
    'key59105': 'value33562',
    'key65760': 'value7581',
    'key98012': 'value79095',
},
    {
    'id': 17527488575505,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Shelby Russell',
    'address': '8964 Matthew Route\nSawyerberg, GA 40420',
    'text': 'Girl standard glass best economic decade would. Next man leg we nice manage low begin.\nFind hair book something manage. Eye national girl. Anything if scientist month issue who.',
    'email': 'cochrannicholas@example.com',
    'phone_number': '001-951-453-4820x75990',
    'json': {
    'name': 'Micheal Johnson',
    'address': 'PSC 0197, Box 2443\nAPO AE 76292',
},
    'key40213': 'value93016',
    'key30951': 'value27759',
    'key56594': 'value47148',
    'key4354': 'value9713',
    'key66378': 'value51831',
    'key33915': 'value81914',
},
    {
    'id': 17527488575514,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Carol Turner',
    'address': '415 Ryan Station\nNew Ricardomouth, HI 11275',
    'text': 'Travel serious whether behavior group explain gas two. Every full performance increase never. View source manager during today land.\nAlong cold top seek me.',
    'email': 'lesteranthony@example.net',
    'phone_number': '6739779512',
    'json': {
    'name': 'Jennifer Gomez',
    'address': '2121 Susan Track Apt. 055\nWest Blakeport, MH 31386',
},
    'key87763': 'value65406',
    'key4315': 'value77649',
    'key20879': 'value46359',
    'key36670': 'value65199',
    'key90360': 'value65737',
    'key52944': 'value86578',
    'key88981': 'value98303',
    'key40409': 'value88589',
    'key71903': 'value16036',
    'key66363': 'value21064',
},
    {
    'id': 17527488575525,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Meghan Barker',
    'address': '48011 Larson Heights\nJasonchester, OR 35105',
    'text': 'Fund themselves they house. Fact throughout information laugh. Would effort save wear very.\nExpect price across deal dark southern let edge. Since officer often enough very well available else.',
    'email': 'jacobdavid@example.net',
    'phone_number': '(299)896-1281x37205',
    'json': {
    'name': 'Veronica Allen',
    'address': '080 Martin Cliffs Suite 331\nWilliamsville, IA 70074',
},
    'key43179': 'value75620',
    'key87813': 'value73031',
    'key73668': 'value45519',
    'key50677': 'value12237',
    'key79344': 'value77391',
    'key38130': 'value22493',
    'key19908': 'value92278',
    'key20504': 'value78260',
},
    {
    'id': 17527488575537,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Samantha Mcguire',
    'address': '58709 Lowe Meadow\nMelissashire, GU 61882',
    'text': 'Goal most home responsibility nothing blood participant. Nothing himself task cell until. Operation since investment various take.',
    'email': 'ashley09@example.net',
    'phone_number': '(466)570-2463x75588',
    'json': {
    'name': 'Robert Bell',
    'address': 'PSC 1962, Box 1602\nAPO AA 66243',
},
    'key42416': 'value67192',
},
    {
    'id': 17527488575545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Angel Hill',
    'address': '4702 Alexis Turnpike Suite 415\nHannahbury, CO 95704',
    'text': 'Little imagine contain matter cause. Page ask TV care level.\nThemselves talk view election involve card. Well figure even else blood. Technology garden difference daughter add.',
    'email': 'cassie78@example.org',
    'phone_number': '938.252.0062',
    'json': {
    'name': 'Bryan Kennedy',
    'address': '038 Troy Locks Apt. 657\nMooremouth, KY 98212',
},
    'key43386': 'value83947',
    'key76404': 'value61935',
    'key12562': 'value8082',
    'key4567': 'value85540',
    'key90959': 'value22709',
    'key59878': 'value77353',
    'key21411': 'value47722',
    'key90216': 'value42655',
},
    {
    'id': 17527488575556,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christy Flores',
    'address': '1568 Murphy Common Apt. 199\nSouth Robert, MS 71394',
    'text': 'Return cup thank hour. Finally truth food ability address number.\nLate one strong take land region meet accept. Compare we large watch light write democratic. Story just ago article million.',
    'email': 'rodriguezmaria@example.org',
    'phone_number': '479-675-4142x8944',
    'json': {
    'name': 'Curtis Ramos',
    'address': '795 David Lake\nEast Douglas, NV 05251',
},
    'key4683': 'value87387',
},
    {
    'id': 17527488575567,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Sarah Nguyen',
    'address': '479 Michael Center Apt. 804\nPort Andrewstad, NC 64587',
    'text': 'Into whom home popular see impact start accept. Yes claim girl candidate why back.\nBuilding management rise maintain anything. Thus opportunity far. Against begin enter memory.',
    'email': 'steven54@example.com',
    'phone_number': '001-521-619-2835x0875',
    'json': {
    'name': 'Lisa Freeman',
    'address': 'Unit 8049 Box 0808\nDPO AE 43338',
},
    'key26138': 'value99346',
    'key92877': 'value45707',
},
    {
    'id': 17527488575576,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Paige Quinn',
    'address': '6421 Ward Inlet Apt. 258\nJohnsonmouth, NY 34602',
    'text': 'Increase lawyer individual exactly interview her let. See activity under fear worker. Face other key himself.\nSituation finish simple worker anything remember. His seem stand per.',
    'email': 'anthonyadams@example.com',
    'phone_number': '001-764-687-4328',
    'json': {
    'name': 'Gary Gonzales',
    'address': '301 Veronica Lake\nSouth Dominiquetown, HI 64504',
},
    'key74291': 'value93435',
    'key28362': 'value41060',
    'key67626': 'value7486',
    'key80754': 'value60329',
    'key70206': 'value38302',
    'key58778': 'value64512',
    'key41439': 'value35404',
    'key45040': 'value47823',
    'key66023': 'value45363',
},
    {
    'id': 17527488575587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kathy Wilson',
    'address': '53296 Amy Loaf Apt. 839\nGambleberg, OH 79829',
    'text': 'Brother him hit possible under. Former answer word alone successful second.',
    'email': 'connie33@example.net',
    'phone_number': '001-687-945-0950x88540',
    'json': {
    'name': 'Colleen Gross',
    'address': '0693 Goodwin Forge\nWest Nicoleview, ID 98996',
},
    'key231': 'value19124',
    'key67274': 'value79867',
    'key46777': 'value13160',
    'key3078': 'value71618',
    'key12323': 'value90518',
    'key76602': 'value38138',
},
    {
    'id': 17527488575598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Sherry Perry',
    'address': '8229 White Mountain Suite 575\nPort Erinfort, DE 42784',
    'text': 'Eye growth threat mind start fly push. Check tonight nothing play. True teach door exist something war.\nReflect thus moment push. Force boy theory partner central remain.',
    'email': 'tiffany78@example.net',
    'phone_number': '001-902-464-2837',
    'json': {
    'name': 'Charles Morales',
    'address': '028 Pratt Ports\nLake Josephburgh, MT 30094',
},
    'key51310': 'value59918',
    'key80108': 'value12398',
    'key45698': 'value15628',
    'key68864': 'value15233',
    'key77063': 'value39862',
    'key81240': 'value41316',
    'key26385': 'value15322',
    'key23384': 'value22031',
    'key58298': 'value55929',
    'key15324': 'value6903',
},
    {
    'id': 17527488575609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Emily Roberts',
    'address': '593 Johnson Crossing\nAndrewchester, MO 06061',
    'text': 'Much central billion exactly late relationship wrong. Huge natural side keep light turn bill. Especially owner yes movie.\nCollege reality detail treat high. End anyone process eye door might expert.',
    'email': 'hjordan@example.net',
    'phone_number': '243-447-6741x03582',
    'json': {
    'name': 'Christian Hebert',
    'address': 'PSC 3487, Box 3212\nAPO AP 88760',
},
    'key57215': 'value49833',
    'key29769': 'value3740',
    'key43222': 'value85995',
    'key17174': 'value75526',
    'key61038': 'value11321',
    'key96004': 'value67667',
    'key14650': 'value2120',
    'key30547': 'value20139',
    'key52923': 'value58578',
    'key94821': 'value20161',
},
    {
    'id': 17527488575618,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Antonio Garcia',
    'address': '8267 Johnson Plaza\nLake George, AK 37112',
    'text': 'Thing stock employee realize even gun member bag. Through soon buy this probably. Require pattern response social theory perform true.',
    'email': 'emills@example.com',
    'phone_number': '495-768-7061x7767',
    'json': {
    'name': 'Larry Suarez DDS',
    'address': '8360 Bauer Flat\nNew Patricia, IL 42556',
},
    'key53352': 'value14408',
    'key44158': 'value15304',
    'key24555': 'value2252',
    'key16026': 'value49983',
},
    {
    'id': 17527488575628,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jennifer Taylor',
    'address': '4984 Mendez Mall\nWest Matthew, AS 29128',
    'text': 'Animal clear rich. Determine number brother house easy. Tonight sure office. Suggest strategy must increase bring.',
    'email': 'april29@example.com',
    'phone_number': '+1-329-385-8706x658',
    'json': {
    'name': 'Marie Allen',
    'address': '458 Martin Station\nLake Jeremybury, FM 14606',
},
    'key21623': 'value23630',
    'key98397': 'value48391',
    'key50225': 'value76728',
    'key18382': 'value18923',
    'key21097': 'value69762',
    'key71173': 'value20450',
},
    {
    'id': 17527488575639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Jonathan Olson',
    'address': '5849 Robert Lodge Suite 917\nRamirezborough, PA 53137',
    'text': 'Face these level sort coach. Community hand single painting increase.',
    'email': 'jason98@example.org',
    'phone_number': '260.924.8877',
    'json': {
    'name': 'Sydney Johnson',
    'address': '153 Denise Alley Apt. 324\nDesireeshire, TX 31142',
},
    'key99544': 'value17101',
    'key64286': 'value70240',
    'key28876': 'value4784',
    'key89048': 'value75978',
},
    {
    'id': 17527488575649,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Eric Brown',
    'address': '07046 David Street\nSouth John, TX 44148',
    'text': 'Car on population democratic. Hair history paper.\nWhatever radio least become public could. Statement partner coach discussion newspaper out those. Artist deal memory tonight lead teach use.',
    'email': 'james52@example.com',
    'phone_number': '2308468220',
    'json': {
    'name': 'William Benson',
    'address': '350 Soto Plaza\nDouglasmouth, AK 47556',
},
    'key16437': 'value72818',
},
    {
    'id': 17527488575658,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'James Adams',
    'address': '49566 Suzanne Islands Apt. 265\nEast Jennifer, AL 68329',
    'text': 'Main two yard throughout husband black. Year ten here know home. Agency discussion few car candidate girl blue he.\nCup some leg leader about three. Image poor official interest but.',
    'email': 'michael12@example.net',
    'phone_number': '4073194017',
    'json': {
    'name': 'Hannah Kelly',
    'address': '92659 Wanda Lake Apt. 704\nNorth Cheryl, WA 20373',
},
    'key1283': 'value83490',
    'key23781': 'value18094',
    'key41163': 'value83760',
    'key19685': 'value32015',
    'key53707': 'value38262',
    'key54751': 'value1006',
    'key18356': 'value52228',
    'key29336': 'value43320',
    'key83429': 'value79176',
    'key41529': 'value37793',
},
    {
    'id': 17527488575669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Elizabeth Mendez',
    'address': '666 Hoffman Landing Suite 583\nPort Lindamouth, IN 03831',
    'text': 'Common million measure everybody visit company skill. Way against decision interesting. Rock main health station back.\nChurch add upon. Let per edge international military hard.',
    'email': 'greenejodi@example.net',
    'phone_number': '783.382.3687',
    'json': {
    'name': 'Kelly Kennedy',
    'address': '656 May Streets\nBenjaminland, VA 35835',
},
    'key55246': 'value26818',
    'key86604': 'value97123',
    'key24530': 'value84512',
    'key30146': 'value62005',
    'key47973': 'value5159',
    'key30598': 'value77777',
    'key6640': 'value69482',
},
    {
    'id': 17527488575680,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Robert Blair',
    'address': '7474 Hernandez Freeway\nNorth Diana, WA 52249',
    'text': 'Score book draw marriage drive writer. Choice bar receive mission economy party.\nFact with director discussion project. Consumer admit peace a machine pressure skill.',
    'email': 'nshaw@example.org',
    'phone_number': '(249)479-0353x3705',
    'json': {
    'name': 'Chris Lee',
    'address': '6247 Lloyd Branch Suite 513\nBettyland, SD 24572',
},
    'key40612': 'value30817',
},
    {
    'id': 17527488575691,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Tracy Brown',
    'address': '472 Jessica Camp Suite 507\nEast Susanmouth, VI 73179',
    'text': 'Window guess hit fish serve. Attention guy so everyone treatment assume great.\nGrow save nothing building college.\nTravel theory race door between beautiful unit woman. You per determine five.',
    'email': 'brandon24@example.org',
    'phone_number': '(666)240-3083x01593',
    'json': {
    'name': 'Andrea Leon',
    'address': '11171 Melendez Row\nNew Gary, KY 89790',
},
    'key33955': 'value92455',
    'key2084': 'value88461',
    'key38189': 'value71699',
    'key68241': 'value53070',
},
    {
    'id': 17527488575702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Robert Gonzalez',
    'address': '903 Kevin Valley Suite 983\nNorth Lisa, NY 03333',
    'text': 'Think activity fast oil. End head a election performance. Early the machine culture some ask. Draw later policy huge face.\nProfessional recent policy movement seek. Job prevent health wide language.',
    'email': 'madison99@example.org',
    'phone_number': '359.930.8575',
    'json': {
    'name': 'Michael Rasmussen',
    'address': '04621 Walters Plains Apt. 780\nAndrebury, IN 96327',
},
    'key54720': 'value80008',
    'key50372': 'value30846',
    'key13919': 'value68724',
    'key49354': 'value6465',
    'key82995': 'value97315',
    'key40367': 'value26151',
    'key94932': 'value47839',
    'key44319': 'value22327',
},
    {
    'id': 17527488575713,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Donna King',
    'address': '8843 Wayne Pass Suite 559\nNew Katherinestad, NE 32150',
    'text': 'Star understand special learn position catch.\nSix deep read billion.\nForward land group eat finish soon. East majority time mention color.',
    'email': 'elizabeth39@example.net',
    'phone_number': '708.544.5974',
    'json': {
    'name': 'Dr. William Johnson',
    'address': '0156 Hannah Extension\nNew Terrifurt, FL 82872',
},
    'key7041': 'value61025',
    'key17225': 'value48014',
    'key70895': 'value53011',
},
    {
    'id': 17527488575723,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Lisa Johnson',
    'address': '199 Kristen Place Suite 706\nAnnside, TN 14175',
    'text': 'Citizen person writer total. Two majority chance window security onto.\nPlace middle anything lot. Ground us wish someone break.\nFamily bit bed minute stuff charge such. This Republican four eat.',
    'email': 'lori42@example.com',
    'phone_number': '001-369-849-7697x6264',
    'json': {
    'name': 'Nancy Flowers',
    'address': '17208 Anderson Loaf\nDayburgh, TN 02195',
},
    'key60629': 'value63227',
    'key56598': 'value37531',
    'key726': 'value18444',
    'key75413': 'value39077',
    'key1036': 'value31541',
    'key57171': 'value96277',
    'key23800': 'value75348',
},
    {
    'id': 17527488575734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Michael Dawson',
    'address': '13880 Laurie Heights Suite 914\nEast Fernando, WY 84211',
    'text': 'Color begin arrive nor season board population rate. Note lose be president.\nExplain those American operation theory.',
    'email': 'bkaufman@example.org',
    'phone_number': '(593)301-9403x280',
    'json': {
    'name': 'Charles Clark',
    'address': '3689 Michael Vista Apt. 286\nCarterview, IL 54476',
},
    'key55823': 'value38723',
    'key85745': 'value94324',
    'key89261': 'value33110',
    'key64510': 'value84306',
    'key7917': 'value40369',
    'key87272': 'value28656',
    'key14061': 'value76497',
    'key7768': 'value31694',
    'key12618': 'value4732',
    'key63551': 'value87904',
},
    {
    'id': 17527488575745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Robert Smith',
    'address': '8791 Matthew Bridge Apt. 057\nSouth David, OK 87197',
    'text': 'Body full special close kid floor. Threat them many dinner hand. Usually over move soon city.\nGas any outside standard. Upon economic response its be million far order.',
    'email': 'ashley94@example.org',
    'phone_number': '(504)337-0483x288',
    'json': {
    'name': 'Mrs. Jennifer Clark',
    'address': '41110 Timothy Mountain\nHarveyton, VI 24717',
},
    'key18483': 'value4575',
    'key69364': 'value41187',
    'key73831': 'value30652',
    'key91333': 'value35868',
    'key29605': 'value93676',
},
    {
    'id': 17527488575755,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Mr. Christopher Conner',
    'address': 'PSC 9921, Box 6691\nAPO AE 87132',
    'text': 'Coach particularly these five. Foreign born indeed onto store.\nThreat itself discover. Own himself before within just hit business star. Born week knowledge stock be soldier site walk.',
    'email': 'jonesanthony@example.com',
    'phone_number': '001-215-284-9063x228',
    'json': {
    'name': 'Raymond Baker',
    'address': '71592 Brenda Road\nNorth Stacyberg, WV 48256',
},
    'key11535': 'value15691',
    'key2131': 'value71552',
    'key33934': 'value82024',
},
    {
    'id': 17527488575764,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Danielle Simpson',
    'address': '5585 Rogers Terrace\nPatricialand, NJ 35889',
    'text': 'Provide ground expert main common. Week after theory minute much.\nOil them hold gun around environment. Increase best financial lawyer customer building thing.',
    'email': 'leslie07@example.org',
    'phone_number': '528-965-5571x098',
    'json': {
    'name': 'Andrew Greene',
    'address': '1543 Lacey Motorway Suite 614\nNew Erikbury, TX 90782',
},
    'key43688': 'value48430',
    'key66445': 'value14887',
},
    {
    'id': 17527488575774,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Carlos Butler',
    'address': '725 Robert Freeway Apt. 143\nReeveston, AL 15342',
    'text': 'Risk let eight hour.\nTechnology office drug street wrong available action. Total can girl four later five score baby. Size recently paper skill several his wait.',
    'email': 'christinanovak@example.com',
    'phone_number': '(929)477-4854',
    'json': {
    'name': 'Andre Alvarez',
    'address': '66479 Thomas Fork Apt. 759\nErichaven, FL 58916',
},
    'key38538': 'value60590',
},
    {
    'id': 17527488575785,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Elizabeth Adkins',
    'address': '6575 Andrea Shore\nPort Alexischester, OR 98857',
    'text': 'More high religious student huge. From future water make always everyone. Hear nation think though fire discuss.',
    'email': 'yadams@example.com',
    'phone_number': '276.729.7419',
    'json': {
    'name': 'Richard Morrow',
    'address': '8091 Wells Well Suite 847\nBergerburgh, AK 01406',
},
    'key14120': 'value2609',
    'key62571': 'value3339',
    'key26127': 'value2123',
    'key53161': 'value6943',
    'key87999': 'value85916',
    'key47218': 'value72595',
    'key37262': 'value94418',
    'key1353': 'value38310',
    'key87117': 'value60777',
},
    {
    'id': 17527488575796,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Shawn Adkins',
    'address': '14256 Cabrera Viaduct\nNew Vickieview, OK 75889',
    'text': 'Voice six remain dream seven card. Action style sister against to student work. Exist wall goal drug government.\nClear a man. Education nor probably member relate far talk.',
    'email': 'istevens@example.net',
    'phone_number': '(333)741-5828x455',
    'json': {
    'name': 'Kimberly Golden',
    'address': '421 Blake Glen Suite 449\nSouth Brandon, NC 79379',
},
    'key5028': 'value44064',
    'key78635': 'value82297',
},
    {
    'id': 17527488575807,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Ellen Cooley',
    'address': 'Unit 2180 Box 0675\nDPO AP 25424',
    'text': 'Relate pass project piece great sit.\nRepresent see team.\nBox whose it choose all. Speech rather especially your but identify better. Charge performance occur court talk.',
    'email': 'williamsmichael@example.net',
    'phone_number': '(473)720-8662x1715',
    'json': {
    'name': 'Michael Wilson',
    'address': '8591 Frank Summit Suite 783\nPort Michele, NY 08121',
},
    'key60163': 'value25319',
    'key91138': 'value77206',
    'key74113': 'value10817',
    'key97547': 'value38636',
    'key90130': 'value82667',
    'key45193': 'value46525',
    'key36789': 'value51986',
},
    {
    'id': 17527488575817,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Thomas Avery',
    'address': '347 Baker Turnpike Suite 811\nWilliamsonborough, MD 63140',
    'text': 'Add maintain represent learn. Eye election allow ok.\nWant somebody know act choice exist choose light. Necessary together interview minute class home.',
    'email': 'christophermorales@example.net',
    'phone_number': '5923229207',
    'json': {
    'name': 'Sandra Ryan',
    'address': '16573 Gates View\nMartinborough, AS 23169',
},
    'key50528': 'value6588',
},
    {
    'id': 17527488575828,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Diamond Nguyen',
    'address': '988 Richard Forges Suite 351\nJefferyview, AR 88080',
    'text': 'Serve base friend level right pay bed down. Reality from build food song.',
    'email': 'melissa51@example.org',
    'phone_number': '305.797.4870',
    'json': {
    'name': 'Matthew Coleman',
    'address': 'PSC 5390, Box 9076\nAPO AE 77331',
},
    'key42078': 'value16470',
    'key90284': 'value22764',
    'key86348': 'value31918',
    'key16322': 'value49862',
    'key53227': 'value22418',
    'key94441': 'value54576',
},
    {
    'id': 17527488575836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Diane Bonilla',
    'address': '5286 Zachary Wells Suite 754\nRamirezfort, ND 36732',
    'text': 'Generation north apply pull thank speak.\nHis agree officer Mr majority interview box couple. Responsibility physical Mrs land fine. Other fear military mean paper.',
    'email': 'sandraadams@example.org',
    'phone_number': '+1-548-838-3624',
    'json': {
    'name': 'Alexandra Foster',
    'address': 'Unit 8516 Box 1344\nDPO AP 20975',
},
    'key48683': 'value83350',
    'key71020': 'value88717',
    'key85943': 'value38790',
    'key59616': 'value22869',
    'key40940': 'value57572',
    'key71545': 'value55595',
    'key32672': 'value28848',
},
    {
    'id': 17527488575845,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Adam Brooks',
    'address': '7542 Hunt Cliffs\nWest Davidhaven, AK 09326',
    'text': 'Capital sing material rich source west. Be economy key challenge around. Expert start what adult.\nCity improve your that along real husband. Lose should start.',
    'email': 'sroberts@example.net',
    'phone_number': '5246109548',
    'json': {
    'name': 'Robert Sherman',
    'address': '49282 Rodriguez Spring Suite 293\nNorth Thomasborough, LA 75593',
},
    'key79': 'value18784',
    'key19246': 'value36174',
    'key88056': 'value64414',
    'key52873': 'value59990',
    'key95770': 'value89124',
    'key29007': 'value39184',
    'key2056': 'value13386',
    'key32817': 'value18962',
    'key67593': 'value69181',
},
    {
    'id': 17527488575857,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Tara Brown',
    'address': '831 Davis Prairie\nBallfort, UT 35273',
    'text': 'Throw child natural race result push behavior again.\nFund deep mouth during unit. Concern simply point especially.\nBag ask case produce hit watch. Low nice if challenge kid.',
    'email': 'ilam@example.com',
    'phone_number': '4406013509',
    'json': {
    'name': 'Andrew Pugh',
    'address': '4795 Neal Oval\nMartinezchester, MS 04979',
},
    'key16849': 'value97605',
    'key88306': 'value66375',
    'key79566': 'value98144',
},
    {
    'id': 17527488575868,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'William Fritz',
    'address': '755 Long Station Apt. 008\nEllisfurt, ID 82672',
    'text': 'Account bed generation chance. Laugh me heavy foreign she seat still.\nSeries wife leg water. Behind attorney compare seat couple matter station. Learn a data firm.',
    'email': 'keithlindsay@example.com',
    'phone_number': '934-486-3244',
    'json': {
    'name': 'Sara Miller',
    'address': 'Unit 4324 Box 0392\nDPO AP 17970',
},
    'key83192': 'value94996',
    'key12305': 'value83755',
    'key60713': 'value7938',
    'key40744': 'value76626',
    'key4442': 'value88131',
    'key94216': 'value324',
    'key82911': 'value77403',
    'key11101': 'value37660',
    'key86636': 'value21691',
},
    {
    'id': 17527488575878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Natalie Morrison',
    'address': '69754 Rose Haven Apt. 323\nNorth Larryborough, AL 81830',
    'text': 'Note many bed help. Entire according cultural lead message.\nHotel mouth political get.',
    'email': 'suzannejones@example.org',
    'phone_number': '(361)481-2024x78524',
    'json': {
    'name': 'Laura Wallace',
    'address': '51046 Walker Plains Suite 285\nNorth Tracy, OR 31818',
},
    'key86362': 'value32892',
    'key77967': 'value6691',
    'key83939': 'value6523',
},
    {
    'id': 17527488575890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Mario Jackson',
    'address': '7690 Haynes Spurs\nRayport, CA 56439',
    'text': 'Tell stop drug understand office since never.\nPush him radio church majority range child. Into must house nature early some. Two forget rock standard first else Mrs. Different control threat program.',
    'email': 'satkins@example.net',
    'phone_number': '8554255947',
    'json': {
    'name': 'Travis Walters',
    'address': '3998 Curtis Mall\nPort Kevinville, MI 35282',
},
    'key7341': 'value53854',
    'key15048': 'value90378',
    'key8508': 'value31207',
    'key44755': 'value42604',
    'key56402': 'value76861',
    'key464': 'value64095',
    'key31704': 'value46573',
    'key11945': 'value63963',
    'key32728': 'value59028',
    'key70222': 'value14998',
},
    {
    'id': 17527488575901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Daniel Cooper',
    'address': '9412 Hanna Freeway\nSmithburgh, OK 98265',
    'text': 'Owner eight option look. Science relationship religious town yard play school.',
    'email': 'jason01@example.org',
    'phone_number': '001-668-592-7002',
    'json': {
    'name': 'Joel Russell',
    'address': '93883 Kayla Mission Suite 489\nHolttown, ID 82164',
},
    'key80769': 'value82467',
    'key98421': 'value85895',
    'key64291': 'value59808',
    'key68779': 'value12185',
    'key6037': 'value92351',
    'key79746': 'value38767',
    'key72544': 'value50018',
    'key89241': 'value23950',
    'key4078': 'value83025',
},
    {
    'id': 17527488575912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Claudia Cannon',
    'address': '0153 Jessica Stravenue\nWest Richard, VI 30842',
    'text': 'Whether develop war full next media only. Instead science focus. Effect purpose mission feel never take leg.\nWhite stock successful at boy wife loss. Bar middle attorney travel concern ago some.',
    'email': 'michaelhawkins@example.org',
    'phone_number': '586-993-7470',
    'json': {
    'name': 'Yvette Garcia',
    'address': '842 Castro Mountain Suite 091\nHernandezmouth, GU 18126',
},
    'key75287': 'value9087',
    'key42570': 'value17907',
    'key76129': 'value54143',
    'key61321': 'value76533',
    'key32131': 'value24296',
    'key5067': 'value59526',
    'key34499': 'value28553',
    'key59255': 'value39723',
    'key17387': 'value74925',
    'key8642': 'value99946',
},
    {
    'id': 17527488575925,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Sarah Jones',
    'address': '0093 Mitchell Field\nCarlsonmouth, IL 57004',
    'text': 'Next if trade address something keep. Factor share structure together film half cost. Our evening most finish decide common.',
    'email': 'bcastillo@example.com',
    'phone_number': '514.308.8494x54752',
    'json': {
    'name': 'Amber Ross',
    'address': '69015 Parker Prairie\nLake Jack, ND 90714',
},
    'key59361': 'value46240',
    'key32598': 'value88096',
    'key67383': 'value79154',
    'key66595': 'value26876',
    'key3552': 'value35938',
    'key34924': 'value26855',
},
    {
    'id': 17527488575936,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Yvette Fisher',
    'address': '25114 Benjamin Route\nSouth Stevestad, IL 21713',
    'text': 'Common development certain simple. Huge until growth process all subject. Economic analysis foot four.',
    'email': 'hbenjamin@example.com',
    'phone_number': '+1-511-800-9034x482',
    'json': {
    'name': 'Alexander Myers',
    'address': '47839 Brown Locks\nChristineview, ID 71881',
},
    'key63803': 'value51500',
    'key95849': 'value82756',
    'key67165': 'value74316',
    'key1052': 'value3788',
    'key47076': 'value83881',
    'key36369': 'value91323',
    'key7727': 'value5409',
    'key11683': 'value46463',
},
    {
    'id': 17527488575947,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Michael Duffy',
    'address': '04965 Mathis Harbors Apt. 444\nKhanmouth, ME 70914',
    'text': 'Far fall system form either life. Need room growth government.\nPoor voice kitchen view political even. Enter say oil Mrs seven learn imagine. Stay book capital civil fine little.',
    'email': 'chelsea26@example.org',
    'phone_number': '902.397.2860',
    'json': {
    'name': 'Kathryn Walker',
    'address': '99578 Smith Overpass Suite 155\nPort Bradleyland, SC 74743',
},
    'key71632': 'value53897',
    'key25733': 'value24846',
    'key91326': 'value81425',
    'key85123': 'value31380',
    'key93999': 'value91453',
    'key54797': 'value85943',
    'key54733': 'value2755',
    'key93817': 'value31710',
},
    {
    'id': 17527488575958,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Zachary Payne',
    'address': '554 Jason Isle Apt. 756\nSouth Edward, TN 61181',
    'text': 'Major among let believe commercial personal him place. Phone political government.\nNumber bank cover. Stage anything computer serious want doctor whatever. Wife central half business meeting cold.',
    'email': 'morgankristina@example.org',
    'phone_number': '788.652.3886',
    'json': {
    'name': 'Kevin Rodriguez',
    'address': '944 Renee Islands\nNew Jason, CT 77567',
},
    'key64597': 'value59327',
    'key14617': 'value59412',
    'key57697': 'value88115',
    'key52013': 'value3903',
    'key76413': 'value69119',
    'key70872': 'value23241',
    'key77407': 'value88866',
    'key16951': 'value30357',
    'key3576': 'value10986',
},
    {
    'id': 17527488575969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Melissa Stokes',
    'address': '361 Sanders Curve\nBrandtberg, KY 94745',
    'text': 'Whom morning along. Fear build hair employee in skill crime allow. Score despite change Mrs character boy. Style physical all along trip environmental who.',
    'email': 'zhorn@example.net',
    'phone_number': '5054575646',
    'json': {
    'name': 'Anthony Wilson',
    'address': '488 Sonia Meadow\nLake Michael, WV 54581',
},
    'key79722': 'value54447',
    'key62011': 'value77790',
    'key64515': 'value2214',
    'key83100': 'value73634',
},
    {
    'id': 17527488575980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Scott Alexander',
    'address': '79118 Claire Summit\nWest Brent, ND 35037',
    'text': 'About discuss art agreement billion. Ability approach financial population forget.\nRemember best team floor. Than majority well entire.',
    'email': 'slucas@example.net',
    'phone_number': '001-823-500-9461',
    'json': {
    'name': 'Jennifer Williams MD',
    'address': '1553 Ochoa Parkways Apt. 603\nWalkerchester, DC 02823',
},
    'key53856': 'value85745',
    'key46185': 'value40007',
    'key44703': 'value33830',
    'key15921': 'value73048',
    'key23521': 'value64839',
},
    {
    'id': 17527488575990,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Willie Lowe',
    'address': 'USNV Freeman\nFPO AE 75533',
    'text': 'Care thought trip kid painting easy. Boy leave available six strong. Term pay everybody place member third industry.',
    'email': 'kathrynblack@example.com',
    'phone_number': '784-657-6488',
    'json': {
    'name': 'Barbara Williams',
    'address': '5167 Sutton Path Suite 237\nPort Tamara, AL 91503',
},
    'key92879': 'value70416',
},
    {
    'id': 17527488576000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Elizabeth Page',
    'address': '50039 Sabrina Crossroad Suite 919\nKellyville, CO 15714',
    'text': 'Teach you care discover take music today from. Per product including debate her.\nName add together make ten. Sometimes themselves mean up season relate.',
    'email': 'tonyacolon@example.com',
    'phone_number': '882.640.3789x480',
    'json': {
    'name': 'Brian Christensen',
    'address': '7744 Warren Radial Apt. 494\nEast Sean, ME 14433',
},
    'key39526': 'value22992',
    'key42263': 'value30117',
    'key19081': 'value94693',
    'key88332': 'value67652',
    'key53857': 'value67275',
    'key93885': 'value93619',
    'key95875': 'value30830',
    'key93149': 'value91515',
    'key4290': 'value12592',
    'key27238': 'value97418',
},
    {
    'id': 17527488576012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'James Cook',
    'address': 'Unit 5494 Box 9471\nDPO AA 85610',
    'text': 'Heavy few onto TV sense dog authority. Really easy magazine. Glass structure catch test past last pick night.',
    'email': 'wsoto@example.com',
    'phone_number': '926-563-0843x1302',
    'json': {
    'name': 'Cody Henderson',
    'address': '57797 Haley Well\nLake Peterton, OH 85435',
},
    'key8575': 'value29513',
    'key25707': 'value84332',
    'key16273': 'value6707',
    'key28239': 'value67583',
    'key22584': 'value29147',
    'key73022': 'value18675',
    'key60646': 'value66904',
    'key89022': 'value35535',
    'key69347': 'value60393',
    'key83996': 'value49912',
},
    {
    'id': 17527488576021,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'William Johnson',
    'address': '730 Washington Fort Apt. 767\nNew Jessica, TN 14332',
    'text': 'Have health war turn large strategy garden rule. Whose hot music detail attack loss.\nPattern environmental then. Experience apply eight turn. Operation office score lead church.',
    'email': 'ijohnson@example.net',
    'phone_number': '+1-397-580-7304x4363',
    'json': {
    'name': 'Matthew Estrada',
    'address': '1364 Moses Rapid Apt. 980\nWest Wendychester, AL 50558',
},
    'key79263': 'value98151',
    'key85676': 'value18732',
    'key87219': 'value50538',
    'key91431': 'value4444',
    'key45180': 'value26785',
},
    {
    'id': 17527488576031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Jennifer French',
    'address': '75152 Kristi Fields Apt. 822\nLake Dustinmouth, MA 28548',
    'text': 'Whose commercial stop build human anyone.\nPerson store economy me. However significant any.',
    'email': 'linda06@example.org',
    'phone_number': '6285290526',
    'json': {
    'name': 'Tiffany York',
    'address': '919 Michelle Forge Suite 043\nDaviesshire, WA 44811',
},
    'key83157': 'value73317',
    'key98928': 'value8534',
    'key25089': 'value70178',
    'key18842': 'value35093',
    'key61002': 'value14167',
    'key12526': 'value69659',
    'key36989': 'value96137',
    'key8692': 'value10470',
    'key89226': 'value68869',
    'key61010': 'value51557',
},
    {
    'id': 17527488576042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'George Baker',
    'address': '046 Jeremy Drives Suite 622\nDavidmouth, GA 60820',
    'text': 'Success around thus education like. Huge success nearly. Face unit professor Mr service. Fish collection modern spring TV and.',
    'email': 'kari20@example.com',
    'phone_number': '288.358.6492',
    'json': {
    'name': 'Robert Zimmerman',
    'address': '792 Banks Row\nNew Francisco, FL 67001',
},
    'key66718': 'value44725',
    'key4671': 'value9102',
    'key93293': 'value23320',
    'key6879': 'value4196',
},
    {
    'id': 17527488576052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Michael Hamilton',
    'address': 'PSC 6354, Box 8084\nAPO AA 09154',
    'text': 'Hot ago speech school defense information peace. Reflect those whose yard. Plan senior institution. Mean those commercial instead not subject.',
    'email': 'davisjoel@example.org',
    'phone_number': '970-857-9090x357',
    'json': {
    'name': 'Kenneth Conrad',
    'address': '8250 Rodriguez Mews\nPort Geraldfort, NM 35267',
},
    'key43807': 'value74889',
    'key77841': 'value80922',
    'key30403': 'value81441',
},
    {
    'id': 17527488576062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Christopher Campbell',
    'address': '3440 David Keys\nNorth Lisaville, WY 04783',
    'text': 'Boy both western shake food across including type. Practice campaign soon thought pull give.\nTraining former tend action international radio. Well country environment bank writer black be.',
    'email': 'carol29@example.net',
    'phone_number': '+1-286-988-2556',
    'json': {
    'name': 'Tiffany Davis',
    'address': '74006 Miller Meadows Suite 990\nTurnerville, WA 43242',
},
    'key71623': 'value84524',
    'key20501': 'value72769',
    'key64326': 'value41891',
    'key5264': 'value36285',
    'key19398': 'value32340',
    'key67912': 'value20518',
},
    {
    'id': 17527488576072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Casey Weber',
    'address': '741 Harper Island Apt. 677\nEvansbury, TX 17614',
    'text': 'When language generation reflect edge. Whole century everyone Congress discussion spend. American plan southern TV throughout.',
    'email': 'paige67@example.net',
    'phone_number': '001-742-654-6853x73199',
    'json': {
    'name': 'Stephanie Jensen',
    'address': 'Unit 3666 Box 2046\nDPO AA 24475',
},
    'key13306': 'value79645',
    'key73595': 'value92054',
    'key50433': 'value12924',
},
    {
    'id': 17527488576081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Daniel Henson',
    'address': '46868 Christensen Divide\nSouth Jennifermouth, GA 76705',
    'text': 'Memory claim team them clear be two.\nTwo none possible quite truth. Early gun popular end visit meeting. Represent cup customer. Protect full ever energy both woman.',
    'email': 'mullinsjessica@example.com',
    'phone_number': '(431)395-3386x695',
    'json': {
    'name': 'Christopher Sanders',
    'address': '887 Ellis Roads Apt. 002\nPort Thomas, WY 89369',
},
    'key43345': 'value58014',
    'key57474': 'value54129',
    'key55913': 'value20457',
    'key2772': 'value10064',
    'key84837': 'value29039',
    'key52618': 'value60755',
    'key40722': 'value69699',
    'key22043': 'value32211',
    'key92390': 'value16751',
    'key83211': 'value63053',
},
    {
    'id': 17527488576092,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Steven Mcintyre',
    'address': '68603 Gary Viaduct\nSandraville, CO 92058',
    'text': 'Somebody event show act major mission bit. Visit southern no sort. Interest on choice type strong claim couple.',
    'email': 'rrodriguez@example.com',
    'phone_number': '(959)917-8484',
    'json': {
    'name': 'Lauren Hicks',
    'address': '999 Jennifer Knolls\nWest Julianstad, PA 24253',
},
    'key58619': 'value36905',
    'key40566': 'value29943',
    'key86991': 'value66985',
    'key63357': 'value38963',
    'key54808': 'value99757',
    'key29590': 'value36695',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
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
    'RequestId': '82393498-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_51_465967sInOHpKl',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-10+20 <= uid < 20+30]_1752748865.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalse1020Uid20301752748865Json()
    test.run_tests()
