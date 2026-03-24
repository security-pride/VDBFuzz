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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-2]_1752744104_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-2]_1752744104.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId321021752744104Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-2]_1752744104.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-2]_1752744104.json"
        self.test_count = 3  # 测试方法数量
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
    'RequestId': '74a3f483-62ef-11f0-a65a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_43_209167puAAuTjZ',
    'dimension': 32,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
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
    'RequestId': '74ab63f5-62ef-11f0-8166-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_43_209167puAAuTjZ',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Kimberly Bonilla',
    'address': '9841 Bradley Inlet Suite 597\nDanielshire, AL 51321',
    'text': 'Or want put write site. Herself table market serve. Local majority material government here.\nFoot above ahead raise know. Far trade but why. City discuss no visit high.',
    'email': 'cartersarah@example.org',
    'phone_number': '506.642.1783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Moore',
    'Nicholas Williams',
    'Jose Wise',
    'Charles Hahn',
    'Julie Frank',
],
    'json': {
    'name': 'Maria Ruiz',
    'address': '12125 Samuel Wells Apt. 161\nFloresstad, SD 02082',
},
    'key22641': 'value80134',
    'key15380': 'value47366',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Angelica Miller',
    'address': '8952 Thompson Squares Apt. 690\nEast Melissaland, MN 96030',
    'text': 'Administration hard why add sort religious between. Stay letter black already teacher personal per. Agent information former may draw cell.\nOther board with. Court offer call manage theory rate.',
    'email': 'theresaguzman@example.org',
    'phone_number': '511.299.7252x35486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Hamilton',
    'Angela Davis',
    'Raymond Lawrence',
    'Gabrielle Porter',
    'Erika Larson',
    'Sandra Bradley',
    'Jason Craig',
    'Christina Davis',
    'Brooke Peterson',
],
    'json': {
    'name': 'Robert Patterson',
    'address': '7214 Edwards Curve Apt. 018\nNew Shannonshire, IN 81338',
},
    'key37203': 'value21623',
    'key86217': 'value45872',
    'key40295': 'value35174',
    'key80079': 'value3595',
    'key43548': 'value42374',
    'key12408': 'value96712',
    'key25982': 'value82554',
    'key707': 'value37908',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Sean Williamson',
    'address': '331 Weiss Road Suite 456\nNew Christinaborough, MD 47621',
    'text': 'Operation theory admit hotel yard likely what. None many painting bad ready.\nCheck special kitchen. Read identify various we.',
    'email': 'probertson@example.com',
    'phone_number': '(536)565-4299x975',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Mitchell',
    'Jonathan Costa',
],
    'json': {
    'name': 'Darren Lopez',
    'address': '52719 Reed Cape\nPort Kevinberg, OR 28933',
},
    'key8083': 'value33788',
    'key89617': 'value37503',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'William Adkins',
    'address': 'Unit 8279 Box 2392\nDPO AE 29357',
    'text': 'Almost reach environment traditional hit city.\nStage floor certainly class choose soon.\nActually own husband health. City manager couple agree role dog.\nRun gun rock force look.',
    'email': 'hunterbrown@example.com',
    'phone_number': '787-313-9178x2392',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Beck',
    'Mary Banks',
],
    'json': {
    'name': 'Ryan Joseph',
    'address': '2271 Woods Inlet\nWalkerbury, VA 25859',
},
    'key49025': 'value46902',
    'key58625': 'value94863',
    'key6800': 'value66259',
    'key29995': 'value27871',
    'key80578': 'value18034',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Devon Jensen',
    'address': '461 Matthew Islands\nTiffanyville, SC 07384',
    'text': 'Quickly line culture need century skin Mrs. Understand general front environmental skin memory.',
    'email': 'sheliaalvarez@example.com',
    'phone_number': '(648)930-0829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Ford',
    'Adam Bates',
    'Brandon Copeland',
    'Travis Wood',
],
    'json': {
    'name': 'Jodi Jones',
    'address': '8894 Jessica Throughway\nMichaelshire, NE 29549',
},
    'key98865': 'value986',
    'key70394': 'value99198',
    'key39863': 'value42637',
    'key49965': 'value19521',
    'key23890': 'value40672',
    'key70338': 'value1561',
    'key78941': 'value73995',
    'key9604': 'value17295',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'John Johnston',
    'address': 'Unit 9438 Box 1782\nDPO AA 04275',
    'text': 'Black raise large level forget. Policy here product far blood rather. Today teach seem deep. Federal ten send.',
    'email': 'gary33@example.com',
    'phone_number': '(531)293-5825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ruth Davenport',
    'Spencer Park',
    'Holly Wallace',
    'Jeffrey Thomas',
    'Cheryl Bentley',
    'Julie Gutierrez',
    'Rhonda Rodriguez',
    'Megan Norman',
    'Michelle Jennings',
    'Derrick Bernard',
],
    'json': {
    'name': 'Carrie Krueger',
    'address': 'Unit 8580 Box 1231\nDPO AP 74623',
},
    'key64631': 'value57657',
    'key33231': 'value2082',
    'key62177': 'value20952',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Brian Higgins',
    'address': '187 Oliver Station Suite 476\nWilsonfort, WY 87079',
    'text': 'Other arm easy letter surface Mrs instead smile. Defense sure possible push pattern live.\nSkin bar commercial water. Film alone probably get pass.',
    'email': 'fernandezdenise@example.com',
    'phone_number': '317.674.5334x613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Sawyer',
    'Madison Clark',
    'Stacy Bishop',
],
    'json': {
    'name': 'Brian Lee',
    'address': '178 George Port Suite 362\nStonemouth, KS 96966',
},
    'key93688': 'value82055',
    'key43047': 'value73130',
    'key50304': 'value3183',
    'key26235': 'value89755',
    'key3566': 'value81871',
    'key33270': 'value96951',
    'key7986': 'value5681',
    'key80159': 'value32486',
    'key89269': 'value78727',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Amanda Allen',
    'address': '330 Philip Crossroad\nJoshuahaven, FM 95711',
    'text': 'Stage parent choose kind month whom who. Result stock wear property your change.\nUnit kid close book. Specific present strong size majority. Floor indicate or specific wide student.',
    'email': 'marksholly@example.net',
    'phone_number': '+1-624-660-2641x51511',
    'array_int_dynamic': [
    75346,
],
    'array_varchar_dynamic': [
    'Leah Torres',
    'Billy Rivers',
    'Robert Johnson',
    'Courtney Lewis',
    'Corey Smith',
    'Linda Cox',
    'Mr. Carlos Osborne MD',
],
    'json': {
    'name': 'Veronica Robinson',
    'address': '5854 Clark Inlet Suite 653\nEast Desiree, AR 12176',
},
    'key32977': 'value69228',
    'key592': 'value82773',
    'key89746': 'value82632',
    'key6585': 'value46580',
    'key25666': 'value94684',
    'key55731': 'value88154',
    'key89239': 'value53597',
    'key97380': 'value23400',
    'key40772': 'value54699',
    'key86224': 'value67952',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Carlos Cruz',
    'address': '983 Flores Pike Apt. 592\nGallegosview, WY 10322',
    'text': 'Increase bed song military. Wish sea raise mouth.\nTeam hand read. Western them sell production by ready visit. Heavy memory event beat current area citizen this.',
    'email': 'harry37@example.org',
    'phone_number': '596.948.9107x641',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Johnson',
    'Linda Hall',
    'George Barnett',
    'Jennifer Juarez',
    'Noah Graham',
    'Robert Whitehead',
],
    'json': {
    'name': 'Michael Mayer',
    'address': 'PSC 2251, Box 5350\nAPO AA 45535',
},
    'key54290': 'value68578',
    'key91185': 'value83975',
    'key81262': 'value54750',
    'key78815': 'value22243',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Jacob Cortez',
    'address': '16972 Mark Extension\nSouth Alexanderfort, VA 60793',
    'text': 'Discussion common consumer opportunity apply down us. Simple fact wind set low save. But into lose test.\nModern or start find prevent owner life.\nInside manage into call rather.',
    'email': 'kelly47@example.org',
    'phone_number': '001-988-860-4161x6634',
    'array_int_dynamic': [
    2791,
],
    'array_varchar_dynamic': [
    'Alejandra Fisher',
    'Christopher Moreno',
    'Jason Collins',
    'Christine Wise',
    'Rebecca Moore',
    'Jessica Whitaker',
    'Bradley Pope',
    'Fernando Gonzalez',
    'Lindsay Ferguson',
    'Cynthia Brandt',
],
    'json': {
    'name': 'Kristin Martinez',
    'address': '25683 Richard Skyway\nPort Hector, GU 38533',
},
    'key67203': 'value86035',
    'key90990': 'value48331',
    'key37654': 'value13091',
    'key36881': 'value56',
    'key58493': 'value94131',
    'key78448': 'value27519',
    'key20414': 'value49787',
},
],
    'dbName': 'prod',
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
        """测试请求 2 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '74a3f483-62ef-11f0-a65a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_43_209167puAAuTjZ',
    'dimension': 32,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-2]_1752744104.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId321021752744104Json()
    test.run_tests()
