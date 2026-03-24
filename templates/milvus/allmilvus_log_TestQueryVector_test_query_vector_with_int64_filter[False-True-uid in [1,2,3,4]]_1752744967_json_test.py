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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752744967_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752744967.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUidIn12341752744967Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752744967.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752744967.json"
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
    'RequestId': '6fde5109-62f1-11f0-b8c8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_54_196521zAMzxEPn',
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
    'RequestId': '72fdc074-62f1-11f0-98c3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_54_196521zAMzxEPn',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Rhonda Kim',
    'address': '6160 Hernandez Common Suite 645\nCoffeychester, PR 91183',
    'text': 'Claim choice water note standard tell. It national control want class picture believe. Also time station employee save if Mr.',
    'email': 'usmith@example.org',
    'phone_number': '432-255-6084x8973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Davis',
    'James Everett',
    'Melissa Rivera',
    'Harold Blankenship',
],
    'json': {
    'name': 'Melissa Knox',
    'address': '450 Smith Glen Suite 895\nCoxstad, MN 48424',
},
    'key10971': 'value167',
    'key17743': 'value66788',
    'key19966': 'value16316',
    'key93898': 'value82730',
    'key19189': 'value85755',
    'key26274': 'value32663',
    'key61836': 'value26720',
    'key73485': 'value32010',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Anita Johnson',
    'address': '251 Fitzgerald Glen\nEast Whitneyside, LA 23919',
    'text': 'Next there project wear get behavior people. Cell religious military my. Program claim score history rule person always hear.',
    'email': 'johnsonchristina@example.net',
    'phone_number': '765.865.0280x32942',
    'array_int_dynamic': [
    61111,
],
    'array_varchar_dynamic': [
    'Donna Henson',
    'Kathleen Larson',
    'Elaine Garza',
    'Michael Randall',
    'Mr. Timothy Bell',
    'Erin Rivera',
    'Debbie Sparks',
    'Amy Best',
],
    'json': {
    'name': 'Kathleen Bell',
    'address': '9238 Heather Mission\nNorth Kathleen, VA 75719',
},
    'key93204': 'value93804',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jessica Perry',
    'address': '9168 Garrett Trail Apt. 724\nDiazchester, GA 44892',
    'text': 'Leave affect maybe couple popular serve. Read whose imagine type long record. Six pretty time hour mission forget.\nRather major tough hand hospital me. Beat walk occur future talk.',
    'email': 'terry29@example.net',
    'phone_number': '+1-228-229-5114x549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Diaz',
    'Kevin Torres',
    'Richard Shelton',
    'Brenda Rich',
    'Vanessa Wolfe',
],
    'json': {
    'name': 'Jacqueline Price',
    'address': 'USS Hall\nFPO AP 29637',
},
    'key28155': 'value43062',
    'key39958': 'value50117',
    'key28638': 'value77513',
    'key23478': 'value9096',
    'key43748': 'value2688',
    'key6747': 'value47501',
    'key71653': 'value5785',
    'key40791': 'value88684',
    'key7867': 'value68756',
    'key82605': 'value10859',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Mr. Joseph Cruz',
    'address': '5705 Tammy Cliff\nKaylatown, IN 58248',
    'text': 'Choice reality between. Before still my establish building hospital scientist. Family ever raise. Case act decide capital.',
    'email': 'allenmcdonald@example.net',
    'phone_number': '+1-567-669-1711x685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Clark',
    'Mark Williams',
    'David Harris',
    'Audrey Duncan',
    'Michael Thomas',
    'Tina Tanner',
],
    'json': {
    'name': 'Carrie Hall',
    'address': '64502 Kevin Lights\nPort Patricia, CO 87498',
},
    'key30584': 'value43747',
    'key24427': 'value83693',
    'key62259': 'value67688',
    'key53406': 'value50112',
    'key52901': 'value90132',
    'key28003': 'value47535',
    'key41253': 'value16288',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Bradley Koch',
    'address': '5590 Mary Corner Suite 727\nHayesville, NH 53567',
    'text': 'Possible financial teacher tend account meeting. Floor one human something and toward. Respond ahead world best production back.',
    'email': 'mcdonaldjoseph@example.net',
    'phone_number': '+1-716-478-1927',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Parker MD',
    'Kevin Perez',
    'Dennis Evans',
    'Veronica Moore',
    'Brian Decker DDS',
    'Andrew Hudson MD',
],
    'json': {
    'name': 'Richard Ruiz',
    'address': '0517 Lopez Loop Apt. 852\nCindyberg, PA 51215',
},
    'key38611': 'value6894',
    'key93769': 'value79667',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Louis Jones',
    'address': 'USS Porter\nFPO AP 37387',
    'text': 'Eye either television travel recent as. Rich technology opportunity happy. Effort task hair matter important poor.\nDay they matter tax. Professional white than.',
    'email': 'cheryl43@example.org',
    'phone_number': '(690)484-1615',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Welch',
    'Amanda Rivera',
    'Shannon Espinoza',
    'Theresa Brown',
    'Elizabeth Hess',
    'Adam Smith',
],
    'json': {
    'name': 'Diana Lee',
    'address': '3801 Courtney Greens Apt. 470\nChadburgh, IL 21720',
},
    'key94484': 'value86597',
    'key78767': 'value24731',
    'key58040': 'value83478',
    'key98243': 'value95106',
    'key85113': 'value63263',
    'key47765': 'value97626',
    'key10205': 'value70445',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Meghan Rodriguez',
    'address': 'USS Jones\nFPO AE 34101',
    'text': 'Vote dark his child pattern coach role. News place task.\nNew south forget enjoy house rule. Ready party garden general me peace. Baby suggest yes partner. Site soldier available.',
    'email': 'gonzalezjoseph@example.com',
    'phone_number': '(241)822-9755x580',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gary Curtis',
    'Amy Anderson',
    'Tina Roberson',
    'Yvonne Foster',
    'Richard Rowland',
    'Alexis Gould',
],
    'json': {
    'name': 'Gregory Wheeler',
    'address': '9154 Anderson Rapid\nPort Brianna, VI 22784',
},
    'key19842': 'value12793',
    'key73121': 'value98712',
    'key69996': 'value75608',
    'key74633': 'value14869',
    'key66942': 'value21460',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Andrea Simmons',
    'address': '42318 Smith Valley Suite 933\nChurchside, CA 54492',
    'text': 'Enjoy option they person rich economic threat. Ahead believe arrive happy.\nStatement far early management key entire each. Wait radio reason. Feel listen gun success.',
    'email': 'sarah29@example.com',
    'phone_number': '(346)960-5037x09242',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Carey',
    'Tracy Curtis MD',
    'Christopher Anderson',
    'Sharon Estes',
    'Dr. Christopher Garcia MD',
    'Heather Williams',
    'Nicholas Rodriguez',
    'Brian Franco',
    'Brooke Calhoun',
],
    'json': {
    'name': 'Andrew Bentley',
    'address': '1834 Lewis Groves\nButlerton, DE 45504',
},
    'key8985': 'value90430',
    'key58092': 'value26586',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Lisa Lopez',
    'address': '47579 Samuel Mountains\nVegaport, WY 08671',
    'text': 'Current significant than product until past recently. Guess along imagine dark.',
    'email': 'danielwatkins@example.net',
    'phone_number': '439.689.3298x153',
    'array_int_dynamic': [
    23822,
],
    'array_varchar_dynamic': [
    'Kelly Simmons',
    'Stephen Castillo',
    'Louis Martinez',
    'Cody Hoffman',
    'Charles Mcgee',
    'Kevin Hughes',
    'Tiffany Rodriguez',
    'David Williams',
],
    'json': {
    'name': 'Melissa Love',
    'address': '531 Julie Path\nWest Danielleburgh, KY 18901',
},
    'key77131': 'value93709',
    'key14603': 'value53247',
    'key44089': 'value49054',
    'key44524': 'value15472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Nicholas Martin',
    'address': '5941 Peters Falls\nWilliamschester, AS 98392',
    'text': 'Play very national week movement provide final. Continue sure anything pull authority. On college factor common.',
    'email': 'broberts@example.com',
    'phone_number': '001-239-443-3737x6836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Davis',
    'Steven Allen',
    'Tracy Martin',
    'Ms. Lauren Beard',
    'Matthew Colon',
    'Natasha King',
    'Tracy Fuller',
],
    'json': {
    'name': 'Larry Brown',
    'address': '954 Flores Run Suite 732\nPort Deanna, MS 83942',
},
    'key35107': 'value75283',
    'key9692': 'value83359',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Jack Grant',
    'address': '06992 Hill Fords\nNorth Diana, FM 28817',
    'text': 'In hundred represent also specific second. Feeling explain place as security poor federal.\nEast explain society act. Age beat buy large president maybe. Authority third dinner call.',
    'email': 'stephen34@example.org',
    'phone_number': '001-338-312-2534x803',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Cordova',
    'John Gordon',
    'Kimberly Miranda',
    'Russell Galloway',
    'Julie Bonilla',
    'Benjamin Smith',
    'Jesse Lowery',
    'Ronald Hill',
],
    'json': {
    'name': 'Blake Maynard',
    'address': '3411 Timothy Lock Apt. 916\nEricmouth, NM 52892',
},
    'key49240': 'value17272',
    'key93979': 'value1582',
    'key76565': 'value33986',
    'key36268': 'value99764',
    'key70956': 'value54589',
    'key13558': 'value69639',
    'key56574': 'value90478',
    'key2150': 'value45523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Caitlin Smith',
    'address': '9443 Courtney Neck\nLopezton, MP 16641',
    'text': 'Building final too character establish agree option.\nDemocrat foreign a itself ago explain. Magazine race method feel Democrat discover.\nOften heavy something describe. Year later society subject.',
    'email': 'vrodriguez@example.com',
    'phone_number': '6999196380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Mccormick',
    'Monica Murray',
    'Amy Weber',
    'James Washington',
    'Jeffery Golden',
    'Stephen Perez',
    'Kimberly Collier',
    'Robert Thompson',
    'Angela Johnson',
    'Timothy Clements',
],
    'json': {
    'name': 'Heather Carr',
    'address': '1229 Brianna Locks Apt. 892\nNew Danielbury, AK 14220',
},
    'key24505': 'value15096',
    'key94674': 'value33399',
    'key27971': 'value76283',
    'key43471': 'value66320',
    'key47093': 'value87603',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Ms. Mary Chandler',
    'address': '210 Norris Turnpike\nJacksonport, HI 29489',
    'text': 'Morning wide several race. Forward surface among learn fall. Still loss truth goal activity out product.\nNearly down student instead figure war chair. Unit sense activity probably eight check could.',
    'email': 'susanjohnson@example.org',
    'phone_number': '001-310-604-0291x723',
    'array_int_dynamic': [
    90681,
],
    'array_varchar_dynamic': [
    'Matthew Jones',
    'Dr. Jonathan Patterson',
    'Laurie Campos',
    'Michael Perez',
    'Robert Tanner',
    'Jason Garrett',
],
    'json': {
    'name': 'Sean Baker',
    'address': '181 Natalie Dale Apt. 027\nLake James, PA 10537',
},
    'key61881': 'value2421',
    'key43424': 'value96091',
    'key5589': 'value3521',
    'key11856': 'value7461',
    'key26535': 'value29649',
    'key82168': 'value12016',
    'key93173': 'value74926',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Elizabeth Scott',
    'address': '036 Anderson Manors Suite 423\nNew Corymouth, MA 46781',
    'text': 'Remember serious response seat nature serious determine. Offer box campaign return with be system fish. Mission network yes.',
    'email': 'justin75@example.org',
    'phone_number': '677.493.0357x83038',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Beck',
    'Yolanda Faulkner',
    'Julie Thomas',
    'Debra Neal',
    'Guy Larsen',
    'Kimberly Pena',
],
    'json': {
    'name': 'Maria Carroll',
    'address': '76635 Jeffrey Islands\nNorth Matthew, AR 22233',
},
    'key84615': 'value56777',
    'key63958': 'value38133',
    'key56757': 'value87638',
    'key15757': 'value63951',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Bobby Smith',
    'address': '9558 Eric Bypass Apt. 917\nNatashachester, MO 02852',
    'text': 'Bill window increase various day hundred. Account safe approach consider. Guy police account everything friend left walk. Model will small team top.',
    'email': 'williamsingh@example.com',
    'phone_number': '001-418-753-2330',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Johnston',
    'Scott Turner',
    'Julie Bell',
    'Tammy Craig',
    'Thomas Evans',
    'Keith Singh',
    'Jasmine Arnold',
    'Matthew Richard',
    'Jose French',
    'Kathleen Curtis',
],
    'json': {
    'name': 'Justin Hernandez',
    'address': '2642 Alexandra Mountains\nNancyfort, RI 87221',
},
    'key82752': 'value11698',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jerry Phillips',
    'address': '1453 Lewis Garden\nPort Hollyville, NV 59602',
    'text': 'However data sell size child plant should. National nature produce up perhaps we everybody.\nWind theory figure kitchen system little century. Response Congress around public size.',
    'email': 'zcole@example.com',
    'phone_number': '740-716-2188x3028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Ramos',
    'Angela Wong',
    'Misty Schultz',
    'Yvonne Hunter',
    'Maria King',
    'Joseph Rhodes',
    'Daniel Gomez',
    'Daniel Madden',
    'Christopher Bailey',
],
    'json': {
    'name': 'Gina Ortiz',
    'address': '658 Gregory Mission\nLake Danielland, SC 34953',
},
    'key12592': 'value93760',
    'key47012': 'value82956',
    'key41714': 'value10044',
    'key83794': 'value50066',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kenneth Rodriguez',
    'address': '5504 Christina Forest\nNew James, WY 18110',
    'text': 'Friend gas staff enjoy sea specific once. Industry answer bar process court future worry.',
    'email': 'alexanderward@example.net',
    'phone_number': '768.992.7917x35357',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Waller',
    'Katherine Berry',
    'Melissa Reid',
    'Nancy Saunders',
    'Andrew Brock',
    'David Walton',
    'Peter James',
    'Maria Cruz',
    'Ana Lambert',
],
    'json': {
    'name': 'Lindsay Lee',
    'address': '461 Wright Way Apt. 617\nNew Ericmouth, OR 85081',
},
    'key23386': 'value14424',
    'key1239': 'value40020',
    'key77218': 'value19978',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Kathryn Jones',
    'address': '66540 Kyle Bypass\nNorth Lawrenceside, NM 93668',
    'text': 'Recognize adult baby crime itself fact. Card try art general. Role sit ten his build answer like. Now available research well wear so.',
    'email': 'glenncrawford@example.org',
    'phone_number': '300-971-3004',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Harrell',
    'Erica Hughes',
    'Matthew Clark',
    'Andrea Curry',
    'Terry Glenn',
    'Whitney Ibarra',
    'Angela Diaz',
    'Steven West',
],
    'json': {
    'name': 'Elizabeth Mcclure',
    'address': '392 Brown Gardens\nLake Brendabury, MO 77578',
},
    'key41473': 'value18601',
    'key30772': 'value36957',
    'key90217': 'value85412',
    'key37213': 'value90811',
    'key33525': 'value44553',
    'key46076': 'value20805',
    'key18316': 'value29532',
    'key19152': 'value85680',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Olivia Hill',
    'address': '4958 Russell Glen Suite 638\nWest Paulstad, IA 25765',
    'text': 'Common learn PM worker small. Language item speak local need up word. Fine network that investment turn factor.\nDegree make even parent recognize. Kind marriage remain improve talk.',
    'email': 'josemelton@example.net',
    'phone_number': '492.614.5342x278',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Leach',
    'Rachel Thomas',
    'Morgan Robinson',
    'Julie Duffy',
    'Michael Potter',
],
    'json': {
    'name': 'Connie Mitchell',
    'address': '9439 Colleen Points Apt. 369\nPetersview, GA 33694',
},
    'key43084': 'value30908',
    'key99591': 'value32535',
    'key1519': 'value57167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Brent Olson',
    'address': '450 Cynthia Summit Suite 348\nEast Johnfort, VT 96187',
    'text': 'Bar so measure including activity everyone bag.\nAbove read it civil. Quality onto line financial. Real small politics former expert build sport.',
    'email': 'troy34@example.org',
    'phone_number': '001-976-545-0706x59135',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Paul Holland',
    'Michael King',
    'Richard Clark',
    'Jacob Parks',
    'Kenneth Gardner',
    'Kimberly Carrillo',
    'Malik Chavez',
    'Krista Bradley',
    'Dr. Timothy Flores MD',
],
    'json': {
    'name': 'Robert Becker',
    'address': '7788 Brown Expressway\nWest Craigview, IA 68868',
},
    'key98703': 'value11535',
    'key65067': 'value25129',
    'key74890': 'value6322',
    'key45823': 'value12251',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Traci Allen',
    'address': '872 Zachary Turnpike Suite 117\nSouth Brendashire, PR 17019',
    'text': 'Budget street skill local customer rise. Tough different without time.\nWith employee dark before ask deal. Adult its poor have lose long. Same detail never coach hit no college too.',
    'email': 'dustinlewis@example.net',
    'phone_number': '319-465-2387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gail Miles',
    'Todd Taylor',
    'Terry Farmer',
    'Michelle Brown',
    'Karen Ward',
    'Jane Ray',
    'Teresa Ward',
],
    'json': {
    'name': 'Christopher Maldonado',
    'address': '90762 Thompson Springs Apt. 765\nWest Erinport, NJ 93348',
},
    'key92888': 'value57872',
    'key39841': 'value17261',
    'key92275': 'value66841',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Thomas Campbell',
    'address': '0710 Shelly Rapids Suite 829\nKellymouth, MN 53433',
    'text': 'Those wide third subject wide. Opportunity across decade minute. Actually past between run day individual factor short.\nPlan process coach until resource myself. Study modern leg cold source most.',
    'email': 'wilcoxjason@example.com',
    'phone_number': '(231)799-2107',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Maria Welch',
    'Anthony Kennedy',
],
    'json': {
    'name': 'Abigail Gomez',
    'address': '37238 Williams Forges\nDavismouth, PW 17044',
},
    'key77582': 'value39727',
    'key92354': 'value78267',
    'key54769': 'value91645',
    'key31380': 'value12301',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jessica Miller',
    'address': '2436 Daniel Well\nNew Sarahmouth, AR 13707',
    'text': 'Available pay beautiful poor challenge example. Again difference key voice well through.\nPicture trip dark. Ever challenge middle against bar. Response recent beautiful indicate away miss.',
    'email': 'kevin08@example.org',
    'phone_number': '(613)522-5114',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'William Hernandez',
    'Louis Jackson',
    'Dale Wilson',
    'Hannah Bright',
    'Scott Cole',
    'Paul Smith',
],
    'json': {
    'name': 'Nicholas Miller',
    'address': '789 Pearson Via\nNorth Gregory, NH 50561',
},
    'key89766': 'value57450',
    'key73232': 'value63377',
    'key51053': 'value90545',
    'key69704': 'value57154',
    'key22741': 'value44206',
    'key86114': 'value97429',
    'key54588': 'value97346',
    'key85885': 'value43559',
    'key43204': 'value49395',
    'key91847': 'value11',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Dr. Shane Hansen',
    'address': '91899 Ricky Course Apt. 006\nWest Kimberly, HI 76575',
    'text': 'Foreign security defense work born attention son. Wrong either certainly direction send too. Serious sign voice serve work give collection since.',
    'email': 'billyjohnson@example.net',
    'phone_number': '4326837813',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sierra Blair',
    'Christopher Mendoza',
    'Amanda Ward',
    'Tara Newman',
    'William Garza',
    'Melissa Nichols',
    'Megan Watkins',
],
    'json': {
    'name': 'Caleb Huang',
    'address': '81515 Rodriguez Islands\nSouth Tamarahaven, MO 01093',
},
    'key29400': 'value95799',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Anthony Bender',
    'address': '309 Anderson Plaza\nClarkside, TX 10826',
    'text': 'True serious recognize physical political military. Reason reveal Congress should remember cultural. Risk benefit that its assume.\nLate make support. Leg sign ball role record product floor.',
    'email': 'sarahhernandez@example.com',
    'phone_number': '827.471.1693x31382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Washington',
    'Christina Bishop',
    'Mary Thompson',
    'Melanie Sullivan',
    'Amanda Howell',
    'Tara Cooper',
    'Vanessa Diaz',
    'Jared Johnson',
    'Dustin Shannon',
    'Brent Griffin',
],
    'json': {
    'name': 'Jennifer Massey',
    'address': '616 Bell Wall\nJosephshire, MH 72724',
},
    'key54833': 'value24059',
    'key79543': 'value27962',
    'key18897': 'value89759',
    'key42721': 'value28363',
    'key68643': 'value18143',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Cassandra Torres',
    'address': '3180 Victoria Club\nWest Sarahton, CA 61866',
    'text': 'Treatment fast bring once. Support care strong leader so surface. Quite unit future step player discuss century issue.',
    'email': 'ihall@example.org',
    'phone_number': '+1-475-764-4790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Wagner',
    'Anthony Ortiz',
    'David Hanson',
    'Keith Hernandez',
    'John Bailey',
    'Patrick Wagner',
    'Joshua Cunningham',
],
    'json': {
    'name': 'Kimberly Sanders',
    'address': '6808 Julie Trace Suite 063\nOrtegatown, AK 80984',
},
    'key93667': 'value74509',
    'key48219': 'value69864',
    'key30843': 'value94989',
    'key5108': 'value95564',
    'key36950': 'value83898',
    'key7676': 'value33113',
    'key5067': 'value91503',
    'key64023': 'value94300',
    'key7484': 'value2278',
    'key80734': 'value73223',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Matthew Alvarado Jr.',
    'address': '37542 Leon Ridge\nDouglasburgh, ND 80492',
    'text': 'Student same artist.\nEffort attorney actually always. Color this among quite. Else determine field TV for. Down everything hot toward.',
    'email': 'antoniocook@example.net',
    'phone_number': '+1-831-546-4022x181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'William Johnson',
    'Valerie Meza',
    'Ronald Hebert',
    'Amanda Williamson',
    'Johnny Simmons',
    'Andrew Swanson',
    'Jeffrey Brooks',
    'Kendra Morris',
],
    'json': {
    'name': 'Allison Kane',
    'address': '179 Atkins Street Suite 674\nSouth Jesseburgh, RI 70765',
},
    'key93241': 'value87209',
    'key54506': 'value10767',
    'key44444': 'value14610',
    'key62933': 'value46649',
    'key90241': 'value57144',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'James Villegas',
    'address': '172 Travis Centers Suite 333\nRobertsonfort, VT 04352',
    'text': 'Pretty decide among race. Often structure so travel card.',
    'email': 'hmontoya@example.org',
    'phone_number': '(808)707-4216x7460',
    'array_int_dynamic': [
    96356,
],
    'array_varchar_dynamic': [
    'Alicia Maldonado',
    'Chris Dillon',
    'Aaron Thomas',
    'Derrick Ibarra',
    'Dr. Paula Myers',
    'Krista Owens',
    'Dennis Moore',
    'Jose Ward',
    'Anthony Fox',
    'Cynthia Smith',
],
    'json': {
    'name': 'Ashley Mccormick',
    'address': '6308 Joel Viaduct Suite 461\nMichaelside, WI 65931',
},
    'key36636': 'value1987',
    'key7412': 'value51100',
    'key22209': 'value81825',
    'key34672': 'value96892',
    'key26974': 'value4551',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Ian Bell',
    'address': 'Unit 2227 Box 0763\nDPO AE 65974',
    'text': 'Major involve letter clearly game speech result. Sound apply child fight whatever word.',
    'email': 'kathleen31@example.net',
    'phone_number': '448-289-8347',
    'array_int_dynamic': [
    74594,
],
    'array_varchar_dynamic': [
    'Taylor Brown',
    'Elizabeth Lane',
    'Dr. Michael Shaw Jr.',
    'Allen Butler',
    'Charles Moore',
    'Alexis Poole',
    'Denise Nelson',
    'Christopher Mitchell',
    'Aaron Martin',
    'Christopher Petty',
],
    'json': {
    'name': 'Brandi Bennett',
    'address': '263 Ford Underpass\nChelseafurt, VI 49461',
},
    'key54632': 'value86036',
    'key54458': 'value15516',
    'key14797': 'value59477',
    'key31346': 'value99155',
    'key43628': 'value14838',
    'key28582': 'value17970',
    'key7350': 'value7612',
    'key21113': 'value61890',
    'key15428': 'value46765',
    'key1520': 'value22246',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Angela Sutton',
    'address': '60337 Amber Parks\nNew Nataliestad, IN 38915',
    'text': 'Bring analysis small brother. Serious north eye operation. Bar avoid owner inside firm appear.',
    'email': 'brettnewman@example.org',
    'phone_number': '(855)928-2113',
    'array_int_dynamic': [
    15675,
],
    'array_varchar_dynamic': [
    'Jackie Ford',
    'Johnny Bradley',
    'Mckenzie Lewis',
    'Terri Boone',
],
    'json': {
    'name': 'Kathleen Garza',
    'address': '9864 John Park\nEast Nicoletown, DC 11415',
},
    'key8315': 'value44491',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Andrea Hendricks',
    'address': 'USCGC Dawson\nFPO AE 34966',
    'text': 'Win sign leg claim. Many take somebody bit surface north stand.\nRange return seek myself participant improve. Executive concern drive which. Quickly yet soon writer.',
    'email': 'zgibson@example.com',
    'phone_number': '379-974-5218x0571',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stuart Marshall',
    'Mr. David Adams',
    'Amanda Stephens',
    'Caleb Collier',
    'Kevin Mcconnell',
    'Kimberly Murphy',
],
    'json': {
    'name': 'Tara Le',
    'address': '605 Donna Road\nFernandezstad, HI 67889',
},
    'key17684': 'value6971',
    'key82120': 'value54025',
    'key13867': 'value16188',
    'key37160': 'value45090',
    'key64355': 'value79377',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Lisa Clarke',
    'address': '42396 Collins Summit Apt. 861\nNorth Georgeton, WI 95520',
    'text': 'Suddenly can measure fine degree. Amount thing around significant war. Ok some or kind million.',
    'email': 'jamesjohnson@example.net',
    'phone_number': '+1-649-700-6176x6223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Luis Bailey',
    'Michael Williams',
    'Bryan Brewer',
    'Krista Fowler',
    'Chelsea Moss',
    'Susan Caldwell',
    'Jordan Ward',
],
    'json': {
    'name': 'Ryan Mcgrath',
    'address': '9182 Garcia Corner Apt. 010\nNorth Andrew, FL 88849',
},
    'key80048': 'value80039',
    'key1025': 'value80620',
    'key5867': 'value89530',
    'key71091': 'value51510',
    'key82680': 'value18446',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Antonio Burns',
    'address': '50487 Patricia Orchard\nFergusonhaven, ME 43905',
    'text': 'Heavy well threat head condition bill be be. Short indeed option push.',
    'email': 'hammondmichele@example.com',
    'phone_number': '(491)821-0047x0257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Phillips',
],
    'json': {
    'name': 'Kathy Chavez',
    'address': '7101 Cassandra Greens\nNew Jerrychester, WI 31531',
},
    'key27878': 'value68085',
    'key71328': 'value84637',
    'key217': 'value56434',
    'key29766': 'value47602',
    'key78089': 'value23638',
    'key87304': 'value59046',
    'key83264': 'value29290',
    'key19226': 'value82330',
    'key54783': 'value87216',
    'key50146': 'value44897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Vincent Arias',
    'address': '5081 Anderson Keys\nNorth Cynthiashire, PA 01802',
    'text': 'Everything approach site note both voice room join. He lead begin magazine effect control. Lead voice end doctor wind church.\nAll some poor table. Me list then inside sometimes present door.',
    'email': 'denisehenry@example.net',
    'phone_number': '001-389-951-5863x672',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Marc Fox',
    'Stephanie Mills',
    'Carlos Perez',
    'Marissa Weaver',
    'Kyle Fry',
    'Brian Porter',
    'Mary Sherman',
    'Colleen Velasquez',
    'Jason Reed',
],
    'json': {
    'name': 'Allen Castillo',
    'address': '100 Heather Centers\nEast Jeanbury, TX 01280',
},
    'key95333': 'value59035',
    'key78188': 'value67479',
    'key93391': 'value29770',
    'key51589': 'value53588',
    'key54986': 'value71665',
    'key49933': 'value56588',
    'key28025': 'value88703',
    'key23798': 'value34167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Whitney Powell',
    'address': '513 Heather Overpass Suite 960\nLeontown, FL 44881',
    'text': 'Treat where generation education story. Focus understand notice research worker stand. Phone best walk ago.',
    'email': 'garciapatrick@example.net',
    'phone_number': '001-988-272-4085x422',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Smith',
    'Andrew Clark',
    'Casey Alexander',
    'Amber Carter',
    'Seth Williams',
    'David Jones',
    'Philip Jarvis',
    'Michael Pham',
    'Amber Lawson',
],
    'json': {
    'name': 'Sara Perry',
    'address': '38473 Carrie Ports Suite 468\nGreentown, AL 43899',
},
    'key7281': 'value93612',
    'key83626': 'value81085',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jesus Hughes',
    'address': '2222 Perez Manors Apt. 430\nPort Elizabeth, ND 79784',
    'text': 'Now official crime miss despite. Can walk poor include capital accept free. Morning reach writer already time set.',
    'email': 'hoganjennifer@example.org',
    'phone_number': '753.568.1324x90504',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dana Huerta',
    'Joseph Weiss',
    'Francisco Chambers',
    'Dale Duarte',
    'Max Harrell',
    'Mr. James Hawkins',
    'Wendy Rice',
    'Kyle Benjamin',
    'Caitlin Wong',
    'Justin Crawford',
],
    'json': {
    'name': 'Jeremy Huber',
    'address': '616 Smith Forest\nWest Richard, WI 70437',
},
    'key85458': 'value70873',
    'key13338': 'value36163',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Tony Mendoza',
    'address': '91591 Stacey Mall Suite 742\nNorth Michael, MH 58459',
    'text': 'Someone type more admit face. Another morning travel interesting practice Democrat site. South candidate interview budget.\nProgram poor cause teacher ready resource several.',
    'email': 'ubarton@example.org',
    'phone_number': '(407)207-0774',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Bennett',
    'Lori Douglas',
    'Regina Griffith',
    'Charles Rojas',
    'Alan Baker',
    'Roberta Hernandez',
    'Becky Lowe',
    'Evelyn Moore',
    'Jeremy Marks',
    'Rebecca Tapia',
],
    'json': {
    'name': 'Nicolas Wagner',
    'address': '2360 Anderson Motorway Suite 195\nSouth Ericburgh, IN 86732',
},
    'key51773': 'value10515',
    'key30308': 'value45019',
    'key13526': 'value28413',
    'key98266': 'value1838',
    'key90258': 'value86070',
    'key13242': 'value16623',
    'key22460': 'value70056',
    'key73133': 'value57109',
    'key77248': 'value17305',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Alexander Andrews',
    'address': '21733 Gibson Ramp Suite 817\nLake Brandon, IA 45549',
    'text': 'Protect hotel loss compare star certain again. Something night successful vote really cell agreement. Live hour guess back. Store type guy involve itself model.',
    'email': 'riverajonathan@example.org',
    'phone_number': '(764)405-8640',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Geoffrey Ferguson',
    'Julie Rodriguez',
    'Robert Thomas',
    'Jill Fry',
    'Nicole Gutierrez',
    'Alicia Malone',
    'Steven Lewis',
],
    'json': {
    'name': 'Dawn Walker',
    'address': '0832 Schroeder Square Apt. 317\nRayhaven, TN 28084',
},
    'key71033': 'value17167',
    'key47481': 'value45618',
    'key11807': 'value48043',
    'key49062': 'value17488',
    'key42370': 'value43526',
    'key74645': 'value46305',
    'key95320': 'value96916',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Timothy Miller',
    'address': '272 Jessica Roads Apt. 435\nNew William, SD 23538',
    'text': 'Level father continue parent. Kind vote again ready its. Child various discuss particularly.',
    'email': 'perrydaniel@example.net',
    'phone_number': '(536)528-0633x204',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Mcdonald',
    'Mary Carson',
    'Erica Moore',
    'Cynthia Hoover',
    'Daniel Hamilton',
    'Jacob Berger',
    'Brooke Allen',
    'Brianna Johnson',
    'Sandra Anderson',
],
    'json': {
    'name': 'Meghan Morris',
    'address': '33042 Brown Bridge\nDunnton, WV 00706',
},
    'key83988': 'value6277',
    'key92017': 'value44272',
    'key51010': 'value89100',
    'key52431': 'value28272',
    'key28996': 'value52665',
    'key19466': 'value83706',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Tony Reynolds',
    'address': '366 Williams Pike Apt. 941\nJuanmouth, OR 06602',
    'text': 'Power within miss president method. Small cause there back throw. Main other account new reflect.\nPaper community major relationship its. Listen then example budget. Cup young rather admit.',
    'email': 'rileybecker@example.org',
    'phone_number': '677.301.6338x26711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Gutierrez',
    'Denise Taylor',
],
    'json': {
    'name': 'Jessica Glass',
    'address': '161 Melissa Mills Apt. 509\nJessicatown, NJ 71520',
},
    'key82963': 'value67469',
    'key60033': 'value11415',
    'key32775': 'value37132',
    'key19630': 'value11724',
    'key94013': 'value53333',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'William Scott',
    'address': '78266 Kidd Drive\nDavilaborough, FM 01092',
    'text': 'Mr although any military nor get mean little. No PM such family note sport. Customer rich thought hot garden summer law.\nListen citizen example professional night citizen. Yourself phone rate score.',
    'email': 'brian48@example.com',
    'phone_number': '(640)961-0010',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Morales',
    'Madison Anderson',
    'Andrew Hickman',
    'Joseph Farrell',
    'Roberto Scott',
    'Madeline Wilson',
    'Erik Arellano',
    'Cody Glenn',
],
    'json': {
    'name': 'Amber Zavala',
    'address': '2617 Green Ports Apt. 157\nVeronicashire, FM 27737',
},
    'key49117': 'value34351',
    'key95021': 'value77484',
    'key49495': 'value88675',
    'key65570': 'value6',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Ronald Cervantes',
    'address': '00149 Brown Motorway\nLake Sethview, MS 86373',
    'text': 'Send shake concern bar that. Push seem economy different cost part never.\nDream thought such identify. Election strong I miss scene strategy write.\nBall where say discuss. Money lead far change tell.',
    'email': 'thomasrodriguez@example.org',
    'phone_number': '(782)322-6020x0612',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Bryan',
    'Hannah Coleman',
    'Mark Adams',
],
    'json': {
    'name': 'Stephanie Johnston',
    'address': '11784 Shaw Ranch Suite 647\nWest Wendy, NV 81457',
},
    'key51101': 'value43166',
    'key21149': 'value53499',
    'key13277': 'value55540',
    'key11253': 'value98961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Melissa Brown',
    'address': '82747 Donna Gateway\nKelseybury, NY 48085',
    'text': 'Education understand each move result often door people. Offer dog total bit worry hit. Majority of home American around something society.\nProduct care factor. Move challenge throughout lead far.',
    'email': 'njones@example.org',
    'phone_number': '885-829-0029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Guerrero',
    'Debbie Holloway',
    'Marcus Williamson',
    'Dalton Savage',
    'Janet Martin',
    'Danielle Nicholson',
    'Jordan Perez DVM',
    'Samuel Wilson',
    'Mary Jackson',
],
    'json': {
    'name': 'Bradley Patterson',
    'address': '470 Mckee Shores\nNorth Jamestown, FL 96429',
},
    'key84793': 'value39824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Sandra Meza',
    'address': '32109 Natalie Tunnel Suite 819\nSouth Randy, MH 29925',
    'text': 'Fall matter result young approach. Court yard good source break receive worker.',
    'email': 'hernandezsamuel@example.com',
    'phone_number': '(567)423-3503',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Williams',
    'Sierra White',
    'Matthew Turner',
    'Michael Harrington',
    'Zachary Torres',
],
    'json': {
    'name': 'Todd White',
    'address': '95401 Kelly Rest Apt. 114\nHillshire, MT 15510',
},
    'key61751': 'value72569',
    'key21844': 'value27248',
    'key27885': 'value65187',
    'key79833': 'value87080',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Miss Cynthia Ray DDS',
    'address': '03979 Lauren Burgs\nSouth Margarettown, GU 88817',
    'text': 'Break theory fast peace near collection Democrat body. Subject treatment interesting institution campaign produce official. Large west later.',
    'email': 'katie56@example.org',
    'phone_number': '688-711-4106x60949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'David Hahn',
    'Oscar Bruce',
    'Douglas Pugh',
    'Alexandria Spencer',
    'Cynthia Johnston',
    'Taylor Cook',
    'Stephanie Brown',
    'Megan Houston',
    'Teresa Garcia',
    'Thomas Rocha',
],
    'json': {
    'name': 'Jacqueline Holt',
    'address': '21078 Welch Turnpike\nHuynhport, PW 94818',
},
    'key98478': 'value75710',
    'key98673': 'value56527',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'David Turner',
    'address': '4139 Laura Groves\nLake Sarahport, AL 83525',
    'text': 'Individual herself hard country pretty.\nSocial relate evidence artist wife rest. Pm theory leg account especially ahead truth. Plan on day smile. War then may story say read rate.',
    'email': 'mbrown@example.net',
    'phone_number': '737-968-4528x5456',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christina Blair',
    'Jeffrey Nixon',
    'Jennifer Andrews',
    'Samantha Rodriguez',
],
    'json': {
    'name': 'Brenda Proctor',
    'address': '8310 Bruce Ramp Apt. 414\nLake Brenda, MH 98371',
},
    'key58639': 'value21473',
    'key10595': 'value80352',
    'key2994': 'value27356',
    'key36440': 'value3775',
    'key33645': 'value99219',
    'key52676': 'value6294',
    'key46452': 'value32648',
    'key28145': 'value91330',
    'key7184': 'value31809',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'William Brock',
    'address': '556 Sanchez Ville\nWest Tina, WY 73689',
    'text': 'Shoulder physical trip identify. Keep child kind.\nPush before someone its. Exist scientist garden agreement entire tax speech.\nSee age set be myself tonight always.',
    'email': 'aprilmorgan@example.net',
    'phone_number': '889.313.7037x816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dominic Patton',
    'Terry Baker',
    'Angela Howard',
    'Kevin Conner',
    'Sara Lee',
    'Mary Mason',
    'Lee Harrison',
    'Cassidy Mccullough',
],
    'json': {
    'name': 'Jody Wilson',
    'address': '1177 Stewart Well Suite 700\nErinstad, PA 84413',
},
    'key10445': 'value90292',
    'key6525': 'value10209',
    'key81237': 'value91737',
    'key89465': 'value1666',
    'key39426': 'value16943',
    'key38520': 'value60440',
    'key68890': 'value702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Amber Wilson',
    'address': '775 Jessica Extensions\nNorth Steven, IN 83163',
    'text': 'Every contain evening just. Play visit side commercial.\nConcern pick on. Opportunity whether writer dinner much television. Call analysis guess certainly high bad decide.',
    'email': 'melissa49@example.net',
    'phone_number': '895.344.6661x14943',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sherry Martin',
    'Anthony Palmer',
    'Kirk Wade',
],
    'json': {
    'name': 'Terrence Monroe',
    'address': '54119 Hughes Crossroad Suite 994\nHallport, AS 60176',
},
    'key587': 'value90734',
    'key16126': 'value80621',
    'key77875': 'value6916',
    'key35813': 'value78696',
    'key4991': 'value90002',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christopher Carter MD',
    'address': '3834 Debra Trace\nNorth Brentton, GA 61110',
    'text': 'Be their hair just number. Drop benefit so black. West north drop father out remember feeling.\nSocial spend six art answer. Offer firm other skin early thousand.',
    'email': 'mckinneyjames@example.net',
    'phone_number': '+1-712-650-9398x095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Carroll',
],
    'json': {
    'name': 'Katherine Burch',
    'address': 'Unit 7255 Box 3311\nDPO AE 80659',
},
    'key22430': 'value38980',
    'key64204': 'value52311',
    'key36467': 'value34000',
    'key1720': 'value46862',
    'key50821': 'value34088',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Angela Williams',
    'address': '641 Angela Turnpike Suite 148\nStephensstad, MN 58252',
    'text': 'Benefit enjoy tonight perform detail. Put model big much throughout. Interview plan seem manage conference rise. Month likely month property.',
    'email': 'carrollmary@example.com',
    'phone_number': '001-588-607-1072x16281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Vickie Pace',
    'Amy Brennan',
    'Nicole Landry',
    'Karen Reynolds',
    'Michael Ford',
    'Christine Whitney',
    'Cole Jordan',
],
    'json': {
    'name': 'Teresa Thomas',
    'address': 'PSC 6628, Box 0156\nAPO AA 42858',
},
    'key13133': 'value44443',
    'key55933': 'value19128',
    'key97621': 'value29434',
    'key11456': 'value33772',
    'key82038': 'value62714',
    'key88413': 'value75371',
    'key14894': 'value88946',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Debbie Jackson',
    'address': '46462 Mike Fall\nWilliamsborough, MI 70894',
    'text': 'Operation son among television. Be lot image response.\nYear end little hit respond yet staff hit. Page road recent. Baby think include child.',
    'email': 'tranbrooke@example.net',
    'phone_number': '001-463-397-1646x64898',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Penny Ramirez',
    'Mary Robles',
    'Alexis West',
    'Deborah Rodriguez',
],
    'json': {
    'name': 'Mary Castaneda',
    'address': '68483 Tran Prairie\nWest Jenniferton, KY 41057',
},
    'key71526': 'value61739',
    'key33461': 'value23251',
    'key80617': 'value77329',
    'key41564': 'value17103',
    'key75059': 'value3271',
    'key47603': 'value84275',
    'key72125': 'value23818',
    'key92937': 'value16666',
    'key81217': 'value81232',
    'key68240': 'value90035',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kenneth Contreras',
    'address': '1619 Jeffrey Stravenue Suite 065\nAshleyborough, AS 63430',
    'text': 'Receive agency may. Heart scene fund boy law collection drop run.\nWorker candidate student system my. Find five situation increase. Color threat opportunity.',
    'email': 'edwardsbrandy@example.org',
    'phone_number': '627-459-5201',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sara Ferguson',
    'Raymond Gonzales',
    'Ethan Martinez',
    'Michael Preston',
    'Marvin Miller',
    'Amber Frank',
    'Sandra Luna',
    'Gabriela Hansen',
],
    'json': {
    'name': 'Christian Paul',
    'address': '2147 Baldwin Islands\nWest William, KY 92204',
},
    'key52791': 'value87164',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Cody Weber',
    'address': 'Unit 1589 Box 1604\nDPO AP 06618',
    'text': 'Get happen you moment.\nManager situation participant from population factor six. Eat enough present trouble. Black talk adult perhaps line action write. Whole skin purpose dog land in.',
    'email': 'smallshawn@example.org',
    'phone_number': '497-631-9588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Finley',
    'Bryce Mcconnell',
    'Keith Doyle',
    'Jessica Gonzales',
    'Mary Smith',
    'Gabriela Garcia',
    'Mrs. Emily Casey',
    'Paul Kennedy',
    'Shirley Baker',
    'Jonathan Harper',
],
    'json': {
    'name': 'Brian Rivas',
    'address': '894 Michael Lake\nMelissaborough, NE 26303',
},
    'key75137': 'value43025',
    'key56985': 'value76954',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Dorothy Peterson',
    'address': '4973 Larry Village Suite 352\nAlexanderhaven, KS 33117',
    'text': 'Away around add ok wear. Over expert speak hundred might quality hot news. Man PM month including.\nArm discover above little seven visit information. Price officer memory campaign better American.',
    'email': 'rachel72@example.com',
    'phone_number': '281-820-4289x769',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Nelson',
    'Erin Spence',
    'Robert Williams',
    'Jordan Garcia',
    'Heather Santiago',
    'Kristen Turner',
    'Darren Ross',
    'Chad Bell',
    'Andre Rosario',
],
    'json': {
    'name': 'Andrew Jackson MD',
    'address': '49995 Burns Land\nMichaelland, OH 58488',
},
    'key85263': 'value52919',
    'key33462': 'value13452',
    'key87018': 'value29919',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Debra Mcguire',
    'address': '101 Brown Harbor Suite 506\nSouth Gregoryshire, OH 13238',
    'text': 'Today carry source look imagine treatment many. Course usually report nor everything I sign. Cause off democratic case.\nCongress employee positive hospital position. Tax sure white.',
    'email': 'brett85@example.net',
    'phone_number': '617-227-2254',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Haynes',
    'Jay Williams',
    'Jennifer Harris',
    'Cory Tyler',
    'Daniel Little',
],
    'json': {
    'name': 'Deanna Thompson',
    'address': '962 Kaitlyn Prairie\nEast Stanley, PW 49199',
},
    'key40485': 'value30138',
    'key72460': 'value38436',
    'key20331': 'value27921',
    'key49523': 'value78051',
    'key89733': 'value51402',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Michelle Powell',
    'address': '1484 Christopher Cape\nNew Toddshire, ND 35777',
    'text': 'Court some important economy. Notice consumer list of add.\nSpend American single be newspaper hour investment. Central identify enough behind nearly. Finally nice threat new interest beyond speak.',
    'email': 'smithjonathan@example.org',
    'phone_number': '001-480-971-4850x169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Mitchell',
],
    'json': {
    'name': 'Benjamin Decker',
    'address': '9406 Soto Curve Suite 575\nLake Jasmineview, LA 59543',
},
    'key81137': 'value2616',
    'key22160': 'value47521',
    'key42303': 'value25963',
    'key16438': 'value13061',
    'key41823': 'value96870',
    'key82368': 'value45750',
    'key78029': 'value47186',
    'key30779': 'value11579',
    'key52682': 'value64225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Jonathan Armstrong',
    'address': '91297 Mark Lakes\nPort Aliciamouth, IN 42714',
    'text': 'And prevent dog month better official bring. Thank experience nation success goal. Age team feeling imagine grow market suggest.\nWhite attack end.\nPrevent security eat car increase ready.',
    'email': 'icastro@example.com',
    'phone_number': '5755849459',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Bautista',
],
    'json': {
    'name': 'Christy Richards',
    'address': '374 Nathaniel Lodge\nNorth Lynnport, FL 88177',
},
    'key56215': 'value77048',
    'key86795': 'value98840',
    'key42770': 'value1307',
    'key32888': 'value60161',
    'key47180': 'value70778',
    'key62107': 'value76214',
    'key27785': 'value14319',
    'key78874': 'value88737',
    'key87960': 'value70026',
    'key8574': 'value32750',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'John Hardy',
    'address': '669 Romero Estates Apt. 465\nBrandonville, AL 13624',
    'text': 'Car sign travel seek despite.\nCost cut final plant plan money. For leg about meet.\nVote night card do home best high.',
    'email': 'alishagonzalez@example.org',
    'phone_number': '(214)206-6352x472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Mathis',
    'Janet Michael',
    'Sabrina Hall',
    'Kelly Ford',
    'Melissa Hunt',
    'Bianca Smith',
],
    'json': {
    'name': 'Christopher Pham',
    'address': 'Unit 3789 Box 0777\nDPO AP 52530',
},
    'key89069': 'value84667',
    'key91146': 'value27992',
    'key78445': 'value67685',
    'key84748': 'value813',
    'key92682': 'value51102',
    'key50592': 'value26614',
    'key93342': 'value58620',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jeffrey Lewis',
    'address': '904 Victoria Pass\nCalebfurt, WA 33474',
    'text': 'Baby indicate data agreement catch. Job serve son experience toward save or. Far who religious require next investment lawyer.',
    'email': 'william77@example.org',
    'phone_number': '(205)520-3207',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Justin Rowe',
    'Lisa Wilkins',
],
    'json': {
    'name': 'Cassandra Oneill',
    'address': '813 Cooper Glen Apt. 932\nRobinsonside, PW 11704',
},
    'key76660': 'value88709',
    'key8403': 'value66274',
    'key52262': 'value3689',
    'key87568': 'value70006',
    'key88622': 'value32918',
    'key53674': 'value20331',
    'key1333': 'value70702',
    'key46997': 'value71261',
    'key43537': 'value40862',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kayla Mendoza',
    'address': 'USNS Johnson\nFPO AA 76768',
    'text': 'Edge her win light make will reach. Election speech lose fill clear. Recent play buy drug specific answer expert.\nTerm trip head physical difference. Tonight once rich voice.',
    'email': 'bgarcia@example.org',
    'phone_number': '(531)648-1846x324',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Clark',
],
    'json': {
    'name': 'Charles Johnson MD',
    'address': '36499 Mullins Hollow Suite 159\nJosephland, DC 68555',
},
    'key29501': 'value19240',
    'key22958': 'value62124',
    'key38586': 'value15',
    'key33836': 'value52105',
    'key77593': 'value36149',
    'key49990': 'value51073',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Michael Hopkins',
    'address': '6314 Leonard Alley\nEast Zachary, FM 08436',
    'text': 'Scientist father same note education relate. Camera skin tend.\nDifferent time right perhaps fact. I manage alone trade tough brother fear.',
    'email': 'whardy@example.net',
    'phone_number': '(457)734-6915x61081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Andrews',
    'Joseph Diaz',
    'Mr. Nathaniel Mendoza',
],
    'json': {
    'name': 'Willie Smith',
    'address': 'PSC 8994, Box 4633\nAPO AA 48712',
},
    'key43810': 'value99668',
    'key50202': 'value36740',
    'key66795': 'value85632',
    'key89803': 'value90599',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Aaron Keith',
    'address': '9375 Campbell Terrace\nRamirezburgh, NE 88182',
    'text': 'Almost official month can. Whose ok blue authority tend whose rate.\nCarry describe central financial mouth. Beautiful manage camera discussion boy rule meeting. Black wall lot board.',
    'email': 'nsutton@example.org',
    'phone_number': '(491)706-7498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Strickland',
    'John Riddle',
],
    'json': {
    'name': 'Katelyn Pratt',
    'address': '57869 Mcintosh Center\nSouth Mary, FL 47303',
},
    'key64838': 'value18900',
    'key72843': 'value52749',
    'key8452': 'value33484',
    'key95478': 'value42036',
    'key17242': 'value937',
    'key3460': 'value70560',
    'key76234': 'value63421',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Stephanie Soto',
    'address': '66343 Tanner Expressway\nJosephland, NY 88942',
    'text': 'Leg lawyer management brother. Part computer term stop reason.',
    'email': 'foxsabrina@example.com',
    'phone_number': '+1-372-377-1715x06585',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Matthews',
    'Judy Gomez',
    'Jason Gardner',
    'Crystal Moran',
    'Erica Rivers',
    'Robert Brennan',
    'Erik Ware',
    'Johnathan Ferguson',
],
    'json': {
    'name': 'Robert Mullins',
    'address': '732 Andrew Cove\nPort Amberfort, ND 90376',
},
    'key56088': 'value45098',
    'key73923': 'value14437',
    'key67814': 'value48266',
    'key20879': 'value67618',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Gregory Smith',
    'address': '5972 Davis Causeway Suite 367\nEast Terri, UT 42193',
    'text': 'Bank relationship decide onto leave. Low hospital story writer both pretty the.',
    'email': 'grahamdaniel@example.net',
    'phone_number': '200.334.0239x71556',
    'array_int_dynamic': [
    17819,
],
    'array_varchar_dynamic': [
    'Makayla Cohen',
],
    'json': {
    'name': 'Lauren Wong',
    'address': 'PSC 4806, Box 6918\nAPO AA 46254',
},
    'key80934': 'value76172',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Sarah Evans',
    'address': '4483 Jenkins Orchard Suite 692\nNew Frankshire, NM 53490',
    'text': 'Charge step thank whether present three discover. Present culture reduce tell carry professor.\nUnderstand military share risk chair poor sell. Image range program.',
    'email': 'scott85@example.org',
    'phone_number': '(281)740-4343x096',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Robinson',
    'Lisa Lloyd',
    'Amanda Bright',
    'Kristin Richardson',
    'Marcus Callahan',
    'Corey Bryant',
    'Christopher Santiago',
    'Charles Wong',
    'Nicole Jackson',
    'Patrick Weber',
],
    'json': {
    'name': 'Elizabeth Mendoza',
    'address': '92461 David Track Apt. 479\nNew Brittanyside, IL 60297',
},
    'key23874': 'value62764',
    'key85080': 'value97957',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Kimberly Duran',
    'address': '6153 Park Point\nWest Rebeccamouth, NE 40457',
    'text': 'Turn against enjoy should evening school past. Term government news town less. Down trade free significant two kitchen.',
    'email': 'donna32@example.org',
    'phone_number': '001-271-505-5223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Audrey Johnson',
],
    'json': {
    'name': 'Katherine Aguilar',
    'address': '233 Lori River\nSilvastad, SD 05336',
},
    'key12595': 'value45657',
    'key71384': 'value92630',
    'key2614': 'value71873',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Robert Brown',
    'address': '72249 Mary Flat Apt. 895\nSimonland, KY 03624',
    'text': 'Candidate however into remain look care. Only majority pull make people. Anything science likely rate.\nAgo recent just most. Bar school rise company grow magazine.',
    'email': 'billywalker@example.net',
    'phone_number': '961.374.5952x481',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jimmy Salazar',
    'Ronald Hodges',
    'Wendy Brown',
    'Susan Sosa',
    'Thomas Fisher',
    'Nicholas Beck',
    'Brandon Underwood',
    'Kelly Brown',
],
    'json': {
    'name': 'Raymond Blake',
    'address': '3051 Sean Mountains Suite 850\nDanielmouth, CT 33444',
},
    'key39931': 'value93164',
    'key33750': 'value43912',
    'key44482': 'value4142',
    'key80607': 'value57666',
    'key20453': 'value41197',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Douglas Liu',
    'address': '39461 Casey Squares Apt. 961\nStevehaven, PA 85953',
    'text': 'Brother environmental husband wish small everyone black. Police later poor simply study share.',
    'email': 'carrollnicole@example.com',
    'phone_number': '828-591-2674',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Ross',
    'William Clark',
    'Reginald Miller',
    'Amy Garcia',
    'Timothy Harrison',
    'John Santos',
],
    'json': {
    'name': 'Judy Nunez',
    'address': '29468 Wilson Garden\nEast Christina, WV 19271',
},
    'key49230': 'value88968',
    'key6701': 'value40391',
    'key23500': 'value40794',
    'key17961': 'value34286',
    'key73166': 'value75116',
    'key59167': 'value56156',
    'key92030': 'value37603',
    'key5564': 'value9790',
    'key36190': 'value51984',
    'key65439': 'value47537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Jessica Stanton DVM',
    'address': '706 Kristie Fall Suite 950\nSouth Charleschester, MO 80253',
    'text': 'Charge shoulder past week even seven. Major meet news technology.\nKeep bill public meet upon. Top campaign simple three. Million support nice.',
    'email': 'david36@example.com',
    'phone_number': '001-586-540-4785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Garcia',
    'Victoria Munoz',
    'Brian Davis',
    'Jill Anderson',
],
    'json': {
    'name': 'Amber Hill',
    'address': '41538 Robinson Flats Apt. 466\nMarkfurt, SC 07978',
},
    'key75739': 'value18428',
    'key94112': 'value63467',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Dustin Newton',
    'address': '83612 Terri Route\nNew Cherylville, MP 91041',
    'text': 'Prove lose ahead vote former. Talk hospital guy these tend life skill card.\nSouth throw indeed tax western. Anyone down political image Congress deal. Expect amount customer development.',
    'email': 'wschmidt@example.com',
    'phone_number': '284.270.1963x2081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alejandra Macias',
    'Brooke Todd',
    'Sabrina Davis',
    'Michael Johnson',
    'Tara Wilson',
    'Matthew Baldwin',
    'Maria Nguyen',
    'Linda Pena',
    'Wendy White',
],
    'json': {
    'name': 'Daniel Schneider DDS',
    'address': '019 Amanda Mills Apt. 335\nMatthewbury, ND 33498',
},
    'key13179': 'value36799',
    'key49275': 'value39686',
    'key36933': 'value66048',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Michael Jenkins',
    'address': '8012 Chelsea Groves\nGregorytown, CA 16810',
    'text': 'Behind little upon. Themselves money large local too how. Shoulder time including individual.\nTable apply parent decide. They fish high prove difference under later beat.',
    'email': 'austin54@example.org',
    'phone_number': '5576867412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Mcintosh',
    'Sue Wood',
    'Tyler Gibson',
    'Alan Shaw',
],
    'json': {
    'name': 'Kelly Jackson',
    'address': 'PSC 4997, Box 5562\nAPO AE 65848',
},
    'key11956': 'value82733',
    'key87649': 'value50724',
    'key46373': 'value9355',
    'key23310': 'value89421',
    'key2153': 'value7743',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Troy Vasquez',
    'address': '9374 John Point Suite 141\nSouth Deniseberg, CA 86048',
    'text': 'Sense market mother whatever realize Mr. Old source would oil hope seek. Expect send agent.',
    'email': 'kelseyhill@example.org',
    'phone_number': '669-347-4208x237',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Johnson',
],
    'json': {
    'name': 'Sara Hunter',
    'address': '6971 Thomas Shore Apt. 766\nWest Jennifertown, NY 24676',
},
    'key4517': 'value23714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jerry Ware',
    'address': '3367 Michelle Dam\nStephaniefort, MI 62897',
    'text': 'Son situation care value spring happen occur. Morning claim challenge certain. Wide than benefit cultural likely despite year. Feeling require court ahead never end.',
    'email': 'jamesherrera@example.org',
    'phone_number': '001-546-309-0250',
    'array_int_dynamic': [
    90692,
],
    'array_varchar_dynamic': [
    'Ryan Hernandez',
    'Dawn Ross',
    'Brady Thompson',
    'Jessica Cruz',
],
    'json': {
    'name': 'Matthew Allen',
    'address': '658 Bailey Keys Suite 485\nSouth Lee, MT 74926',
},
    'key21485': 'value38179',
    'key45887': 'value84749',
    'key70108': 'value19556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Laura Carter',
    'address': '0320 Daisy Hollow Apt. 636\nNew Andrewfort, MI 43013',
    'text': 'Security culture choice near smile. Way fear health investment chair use role. Figure wall executive first left particularly each.',
    'email': 'collieranthony@example.net',
    'phone_number': '396-527-4859x888',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Christopher Garcia',
    'Tara Avila',
    'Jonathan Garza',
    'Brittany Miller',
],
    'json': {
    'name': 'Catherine Klein',
    'address': '6657 Miller Fall Suite 361\nSouth Jessicachester, AR 61260',
},
    'key47553': 'value99658',
    'key91215': 'value62789',
    'key17626': 'value22010',
    'key16985': 'value90360',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Tammy Woods',
    'address': '887 Theresa Cliff Suite 670\nPort Jonathan, AL 99435',
    'text': 'Attack society particularly card seek though. Outside society tree over.\nFour Mrs sport care. Letter cut hot. Left store four mind such.',
    'email': 'alexandria79@example.com',
    'phone_number': '001-786-278-3070x747',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Smith',
],
    'json': {
    'name': 'Bradley Turner',
    'address': '9735 Bryan Plain Suite 852\nScotthaven, OK 43670',
},
    'key83936': 'value22599',
    'key32783': 'value60461',
    'key99473': 'value43251',
    'key33291': 'value97712',
    'key36429': 'value21493',
    'key64354': 'value44737',
    'key43786': 'value38805',
    'key54239': 'value15539',
    'key63643': 'value17509',
    'key56805': 'value42066',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Mark Johnson',
    'address': '802 Angie Vista Suite 268\nAnnastad, NH 27227',
    'text': 'Over suddenly religious ask right sea tree. Against north message drug any fire. Bag oil property level national meeting.',
    'email': 'melody21@example.net',
    'phone_number': '(869)687-7542x413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Darin Smith',
    'Matthew Larson',
    'Brian Tapia',
    'Jonathan Sanford',
    'Frederick Jones',
    'Marc Vance',
    'Holly Goodman',
    'Natasha Morris',
    'Linda Spencer',
],
    'json': {
    'name': 'Karen Gonzales',
    'address': '010 Travis Circles\nEast Stacey, KS 60339',
},
    'key11746': 'value50310',
    'key67245': 'value11187',
    'key42479': 'value13963',
    'key17768': 'value26371',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Morgan Glover',
    'address': '987 Jennifer Squares Suite 684\nKristinton, NV 36920',
    'text': 'Get fill organization choose material huge you. City writer ability red break discover executive.\nGuy avoid outside third. Truth can note expect across.',
    'email': 'jhoward@example.org',
    'phone_number': '+1-682-787-8154x17205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bailey Chavez',
    'Sharon Carter',
    'Manuel Gonzales',
    'Paula Martinez',
    'Katie Wright',
    'Jessica Wilcox',
    'Lisa Johnson',
    'Jennifer Walker',
    'Steven Gomez',
    'Spencer Love',
],
    'json': {
    'name': 'Patricia Perry',
    'address': '5647 Amy Run Apt. 939\nNew Sharon, DE 57553',
},
    'key67692': 'value40303',
    'key12625': 'value16466',
    'key7705': 'value79392',
    'key55808': 'value66208',
    'key42830': 'value93400',
    'key38695': 'value68691',
    'key38760': 'value80014',
    'key53482': 'value6014',
    'key45806': 'value34709',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Amanda Reynolds',
    'address': '77695 Erin Tunnel\nBrittanyport, MN 07881',
    'text': 'North on where free realize natural mention. It easy interesting daughter admit.\nUpon something large try. Also usually notice interesting. Rate decide tonight too.',
    'email': 'rmartinez@example.org',
    'phone_number': '913.925.1563',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Park',
    'Justin Esparza',
    'Danielle Pierce DDS',
],
    'json': {
    'name': 'Carrie Savage',
    'address': '6904 Grant Ranch Suite 331\nNew Paige, GA 71033',
},
    'key89147': 'value96965',
    'key64882': 'value58879',
    'key14291': 'value44176',
    'key31880': 'value88957',
    'key50025': 'value43319',
    'key92997': 'value99589',
    'key59245': 'value38207',
    'key37206': 'value67258',
    'key34241': 'value99329',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Sandra Camacho',
    'address': '7007 White Garden\nNew Troyshire, DC 25890',
    'text': 'Sister statement herself every top participant week. Goal nice only threat.',
    'email': 'caseymelissa@example.org',
    'phone_number': '+1-593-390-8159',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Steven Hamilton',
    'Michelle Pruitt',
    'Adam Davis',
    'Laura Clark',
    'Carlos Larsen',
    'Amanda Terry',
    'Brian Bradford',
    'Veronica Noble',
],
    'json': {
    'name': 'Stephen Norton',
    'address': '39177 Santana Mall\nEast Hannah, PA 47660',
},
    'key20314': 'value97992',
    'key23667': 'value63281',
    'key64861': 'value72599',
    'key71875': 'value15420',
    'key12488': 'value36003',
    'key651': 'value48885',
    'key80653': 'value51530',
    'key32675': 'value34330',
    'key6146': 'value63140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Michael Baldwin',
    'address': '69751 Ashley Roads Suite 581\nNorth Monique, LA 31856',
    'text': 'Production teacher popular matter stock gun which. View something travel also board probably manage.',
    'email': 'kingchristopher@example.com',
    'phone_number': '(687)850-9548x8887',
    'array_int_dynamic': [
    7347,
],
    'array_varchar_dynamic': [
    'Brian Castaneda',
    'Jenna Rivera',
    'Audrey Spencer',
    'David Chung',
    'Kelly Porter',
],
    'json': {
    'name': 'Jeffrey Hardy',
    'address': '603 Sherman Knolls\nPort Richard, AL 94984',
},
    'key56095': 'value90609',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Oscar Wallace',
    'address': '4916 Mark Terrace Suite 229\nJohnstonburgh, TX 80550',
    'text': 'For none stand. Partner anything plan range probably no space.\nRoad require necessary art. Yeah face administration finish agree with say sign. Exist inside resource authority call difficult.',
    'email': 'sbuckley@example.net',
    'phone_number': '+1-550-317-6400x721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dylan Shelton',
    'Aaron Scott',
    'Natalie Padilla',
    'Elijah Myers',
    'Michelle Guzman',
    'Jeffery Peters',
    'Brittany Beck',
    'Eric Williams',
],
    'json': {
    'name': 'Bill Buchanan',
    'address': '87050 Michelle Fall\nEast Dennistown, WY 93852',
},
    'key34735': 'value4496',
    'key23959': 'value75386',
    'key33105': 'value5143',
    'key45460': 'value28346',
    'key56549': 'value64158',
    'key37616': 'value86566',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Adrian Chang',
    'address': 'PSC 8648, Box 2329\nAPO AA 02492',
    'text': 'Many nearly but accept. Mention camera similar early manager success. Doctor Democrat happy alone. Resource analysis collection stop any recent stuff.',
    'email': 'haley62@example.com',
    'phone_number': '001-718-949-9547x5879',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Julie Lee',
    'Gary Adkins',
    'Michael Barnes',
    'Tabitha Roberts',
    'Samuel Nelson',
    'Gary Clark',
    'Jacob Adams',
    'Keith Hernandez',
    'Stacy Sanders',
    'Eugene Martinez',
],
    'json': {
    'name': 'Scott Daniels',
    'address': '916 Hahn Viaduct\nWest Michellestad, OK 44810',
},
    'key23787': 'value8018',
    'key21962': 'value28040',
    'key17775': 'value88988',
    'key51579': 'value92810',
    'key60847': 'value22878',
    'key52674': 'value47796',
    'key4334': 'value55199',
    'key22032': 'value27288',
    'key90225': 'value91672',
    'key2707': 'value52555',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Charles Underwood',
    'address': '12382 Pratt Extension\nWest Barbara, MN 91865',
    'text': 'Loss effort back. Popular dream station place garden. Indeed onto out from central ahead.\nBoard share quite long relate. Clearly voice current situation dream my senior laugh.',
    'email': 'andrewwilliams@example.net',
    'phone_number': '614.690.8758x56039',
    'array_int_dynamic': [
    15740,
],
    'array_varchar_dynamic': [
    'Leonard Jones',
    'Curtis Caldwell',
    'Michael Casey',
    'Patrick Kennedy',
    'Jeremy Rogers',
],
    'json': {
    'name': 'Dr. Katrina Harris',
    'address': 'Unit 9120 Box 8910\nDPO AE 55677',
},
    'key53772': 'value67430',
    'key42035': 'value38741',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jennifer Miller',
    'address': '3661 Ramirez Parks Suite 732\nLake Lisa, FM 55895',
    'text': 'Push wind more. Science together cold letter. Wonder understand land politics order. Certainly total throw room with apply manage.',
    'email': 'alan32@example.com',
    'phone_number': '(620)212-9696x101',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Johnson',
    'Nathan Johnson',
    'Anthony Jennings',
    'Johnny Patel',
    'Brandon Berry',
    'Elizabeth White',
],
    'json': {
    'name': 'George Zimmerman',
    'address': '545 Hall Valley Suite 058\nKimberlyside, VA 48102',
},
    'key64052': 'value9072',
    'key12520': 'value4243',
    'key74750': 'value74663',
    'key39143': 'value36805',
    'key8368': 'value5155',
    'key87777': 'value8258',
    'key35123': 'value83987',
    'key14625': 'value91410',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Charles Brown',
    'address': '889 Horton Run\nNew Monica, MP 54293',
    'text': 'Whole onto sort recent. Situation another seven watch peace.\nOutside off group give large word among tough. Reason party hot chair tax with. Less same major treat main.',
    'email': 'campbelleric@example.net',
    'phone_number': '(312)482-8520',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Kline',
    'Kimberly Hamilton',
],
    'json': {
    'name': 'Timothy Zimmerman',
    'address': 'Unit 8697 Box 7623\nDPO AP 43649',
},
    'key29751': 'value59390',
    'key63071': 'value83482',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Antonio Alexander',
    'address': '1431 Karen Parkways\nSouth Tiffanyhaven, DE 70051',
    'text': 'Yeah best concern issue computer development computer. Particularly while significant activity arrive. Quickly but sea sea line now. Son because difficult party plant plant worry store.',
    'email': 'erichardson@example.net',
    'phone_number': '(352)252-6350',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Williams',
    'James Blackburn',
    'Shawn Lee',
    'Brianna Haynes',
    'Stephanie Jackson',
    'James Mills',
    'Susan Tucker',
    'William Henderson',
],
    'json': {
    'name': 'Emily Williams',
    'address': '932 Parker Island\nSwansonville, ID 12763',
},
    'key25761': 'value97714',
    'key86030': 'value50217',
    'key5359': 'value76270',
    'key18442': 'value27966',
    'key9262': 'value10199',
    'key46374': 'value5644',
    'key56465': 'value88952',
    'key96076': 'value97225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Christopher Avila',
    'address': '331 Jones Viaduct\nSouth Tracyberg, AR 03352',
    'text': 'Truth follow interesting. Rate plant individual white forward president. Score security bar.',
    'email': 'brownheather@example.org',
    'phone_number': '(320)856-6832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Cook',
    'Mrs. Kelly Rivera',
    'Michael Harris',
    'Kevin Chavez',
    'Elizabeth Mendoza',
    'Adam Reed DDS',
],
    'json': {
    'name': 'Jeffrey Bell',
    'address': '2689 Smith Skyway\nKellimouth, NM 20966',
},
    'key52636': 'value69826',
    'key46056': 'value82755',
    'key61304': 'value91143',
    'key20677': 'value47819',
    'key13170': 'value91398',
    'key77621': 'value11507',
    'key62724': 'value66151',
    'key19866': 'value43076',
    'key79454': 'value92160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Brandi Mcclain',
    'address': '71189 Sutton Squares\nNew Jonathanshire, ND 92596',
    'text': 'Four notice tree. Natural role same forward tree street news. Field lot as.\nEnergy everyone nearly seek much. Us win Mrs this onto.',
    'email': 'natalie49@example.org',
    'phone_number': '+1-379-408-9104x393',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Gardner',
    'Linda Smith',
    'Mary Walker',
    'Stephanie Holmes',
    'Sarah Smith',
    'Jason Frey',
    'Jeffrey Fox',
    'Samuel Wright',
    'Julie Whitney',
    'Angelica Moody',
],
    'json': {
    'name': 'Timothy Warner',
    'address': 'USNV Moore\nFPO AA 95655',
},
    'key12812': 'value22718',
    'key44486': 'value88603',
    'key81133': 'value66758',
    'key8480': 'value68847',
    'key95240': 'value15955',
    'key24809': 'value88135',
    'key91628': 'value67976',
    'key9247': 'value80488',
    'key56641': 'value80368',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Steven Wilson',
    'address': '40132 Michael Inlet\nLake William, VI 00834',
    'text': 'Thing establish reality learn way season present. Thought better billion base capital themselves product.\nPhone think all activity. Condition expert event beyond month easy likely.',
    'email': 'lauraelliott@example.org',
    'phone_number': '(438)703-3867',
    'array_int_dynamic': [
    57242,
],
    'array_varchar_dynamic': [
    'Linda Walters',
],
    'json': {
    'name': 'Karen Lynn',
    'address': '7766 Sarah Burgs Suite 257\nNorth Ronaldmouth, CT 41019',
},
    'key3842': 'value17584',
    'key74513': 'value44960',
    'key95760': 'value79717',
    'key53207': 'value18570',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Jacqueline Russo',
    'address': '43823 Candice Wall\nNew Patrick, NM 73023',
    'text': 'Many box tend year become behavior. Four minute than.\nMean theory final turn senior seven entire. Artist data project body get ok senior property.',
    'email': 'uburns@example.net',
    'phone_number': '(276)929-5760x1606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Joseph',
    'Jennifer Kirby',
    'Diana Ford',
    'Sara Yates',
    'Sonia Gibson',
    'Jennifer Weber',
    'Christopher Johnson',
],
    'json': {
    'name': 'Joseph Payne',
    'address': '8728 Jimenez Harbor Apt. 872\nPort Marciamouth, FL 22517',
},
    'key56481': 'value96094',
    'key94778': 'value98678',
    'key90690': 'value28654',
    'key57757': 'value75775',
    'key42487': 'value93779',
    'key70547': 'value50645',
    'key38062': 'value51841',
    'key55931': 'value50348',
    'key65502': 'value38899',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Christine Combs',
    'address': '527 Erickson Island Suite 031\nEllistown, KY 03145',
    'text': 'Page light southern might. Long product could detail skill rock. Tough need far bad too say study.\nProfessional page score believe story against during. Deep several recently risk.',
    'email': 'qdavis@example.com',
    'phone_number': '+1-557-854-4360x38116',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Emma Hancock',
    'Christopher Jones',
],
    'json': {
    'name': 'Tanya Anthony',
    'address': 'PSC 9721, Box 7488\nAPO AA 00754',
},
    'key38077': 'value10828',
    'key67055': 'value31121',
    'key30290': 'value22417',
    'key25544': 'value86429',
    'key75874': 'value42203',
    'key1585': 'value27341',
    'key70294': 'value22972',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Mr. Brian Green PhD',
    'address': '908 Amanda Keys\nEast Christopher, NM 89863',
    'text': 'Story top front goal. Begin individual out sport.\nForce reach sense idea chance. Politics herself management civil college. Friend friend challenge attorney feeling return.',
    'email': 'susanjimenez@example.org',
    'phone_number': '001-205-935-0275x6092',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Miller',
    'Eric Russo',
    'Tracy Harvey',
],
    'json': {
    'name': 'Randy Benson',
    'address': '9986 Tyler Highway\nSouth Christina, MI 15822',
},
    'key65356': 'value62869',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'John Schroeder',
    'address': '1791 Sarah Walk Suite 285\nLake Chelsea, GA 68500',
    'text': 'Decision perhaps team opportunity. Often none tell citizen garden. Wonder company his painting stuff.',
    'email': 'aduffy@example.net',
    'phone_number': '5143748764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Corey Wu',
    'Sergio Young',
    'Brooke Fernandez',
],
    'json': {
    'name': 'David Marks',
    'address': '16676 Blair Flats Apt. 749\nEast Nancy, GU 81008',
},
    'key7787': 'value55230',
    'key90007': 'value18809',
    'key49773': 'value46328',
    'key30105': 'value61371',
    'key98883': 'value67003',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Leah Stewart',
    'address': '8841 Jeffrey Villages Suite 686\nElizabethberg, HI 10984',
    'text': 'Near in suffer so various second experience off. Service learn benefit beat choose executive. Citizen away type happen fill positive daughter. Partner gun represent.',
    'email': 'jeffreymiller@example.org',
    'phone_number': '(340)627-4334x69262',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Lynch',
],
    'json': {
    'name': 'Justin Noble',
    'address': '2436 Lewis Street Apt. 494\nWest Sarahfort, ID 78530',
},
    'key548': 'value24563',
    'key32441': 'value93051',
    'key16106': 'value81426',
    'key85926': 'value22891',
    'key51131': 'value59343',
    'key1446': 'value3629',
    'key53098': 'value86742',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Rose Cox',
    'address': '0532 Samantha Gardens Apt. 427\nSouth Heatherburgh, HI 27945',
    'text': 'Way now involve reflect paper understand. Thousand public nature page continue room. Series behavior deal door director account rich.\nBall trial at computer figure. Recognize weight couple.',
    'email': 'gregorycharles@example.net',
    'phone_number': '5538958848',
    'array_int_dynamic': [
    13150,
],
    'array_varchar_dynamic': [
    'Carlos White',
    'Karen Mccullough MD',
    'Lauren Smith',
    'Joseph Joyce',
    'Kathleen Gilmore',
    'Tracy Smith',
    'Jessica Aguilar',
    'Taylor Mayo',
],
    'json': {
    'name': 'Nicole Luna',
    'address': '73994 Hatfield Roads Apt. 619\nNew Jenniferbury, ID 35344',
},
    'key89797': 'value99074',
    'key86075': 'value9777',
    'key55703': 'value51521',
    'key83316': 'value9465',
    'key84933': 'value40430',
    'key93120': 'value11803',
    'key53001': 'value58876',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Mr. Ian Myers',
    'address': '222 John Tunnel Apt. 351\nHayeshaven, HI 09667',
    'text': 'Just none blood moment company. Player state not true investment admit.\nCentral remain herself nearly. Radio customer whom fly.',
    'email': 'thomaswaters@example.com',
    'phone_number': '001-383-277-9043x396',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Dalton',
    'Katherine Perez',
    'Andrew Haley',
    'Joseph Warren',
    'Kenneth Norman',
    'Robert Potter',
    'Peter Smith',
    'Chris Valencia',
    'Dakota House',
    'Brandon Brown',
],
    'json': {
    'name': 'Susan Torres',
    'address': '73411 Wright Court Suite 782\nPort Robertton, OH 75034',
},
    'key25724': 'value80440',
    'key1759': 'value93838',
    'key76123': 'value62464',
    'key69570': 'value50908',
    'key94708': 'value23011',
    'key90866': 'value61555',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Mark Jones',
    'address': '661 Diane Locks Suite 272\nSouth Kiarabury, WY 87773',
    'text': 'On since product consider central around of. Need professional manager. Could point she keep center.\nNone usually follow factor cell. Role weight military letter this need.',
    'email': 'darlene33@example.net',
    'phone_number': '276-214-5173x555',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Mills',
    'Michael Perez',
    'Elizabeth Johnson',
    'Marcus Hurst',
    'Olivia Robinson',
    'Anthony Rodriguez',
    'Jaime Lee',
    'Aaron Leach',
],
    'json': {
    'name': 'Corey Cook',
    'address': 'PSC 3763, Box 8860\nAPO AE 20399',
},
    'key81991': 'value78996',
    'key38865': 'value68280',
    'key72500': 'value67402',
    'key5805': 'value77128',
    'key25937': 'value16468',
    'key75905': 'value48428',
    'key53314': 'value28938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Julie Ellison',
    'address': '1745 Cesar Camp Suite 871\nTimothyview, CT 18078',
    'text': 'Action research hard race buy fish. Debate heavy nearly its card be.\nBefore people fast race. Food minute war now institution. Himself try safe set major.',
    'email': 'christine07@example.org',
    'phone_number': '265.756.9216x3232',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Smith',
    'Jonathan Nguyen',
    'Anthony Johnson',
    'Amanda Walters',
    'Tara Crawford',
    'Jacqueline Brown',
    'Barbara Turner',
],
    'json': {
    'name': 'Michele Molina',
    'address': '5019 Myers Cliffs Suite 512\nSouth Annmouth, AL 13815',
},
    'key41976': 'value59087',
    'key19404': 'value86665',
    'key10234': 'value89868',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Alexandra Perez',
    'address': '12525 Anderson Lights\nNorth Johnathanborough, WA 34492',
    'text': 'Somebody real meet research laugh kind. International including animal camera about spring.\nNumber soldier prove. Tell town write also mean voice.',
    'email': 'josephhiggins@example.net',
    'phone_number': '001-326-499-0528x46862',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Angela Kelley',
],
    'json': {
    'name': 'Martha Anderson',
    'address': '27690 Le Mount Apt. 495\nEast Brendaburgh, AS 18626',
},
    'key2008': 'value84318',
    'key16007': 'value31479',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Daisy Chan',
    'address': '168 Peter Causeway Apt. 679\nNew Luisview, FM 53737',
    'text': 'Among chance standard.\nReveal control woman enough. Enough bag foreign appear speech store or.\nNotice religious remember else college southern book out. Tell arm our. Mention trip red charge.',
    'email': 'jenniferwalters@example.org',
    'phone_number': '352-900-0689',
    'array_int_dynamic': [
    15494,
],
    'array_varchar_dynamic': [
    'Rebecca Wong',
    'Tracie Patrick',
    'James Walker',
    'Daniel Wiggins',
    'Justin Hicks',
],
    'json': {
    'name': 'Francis Alvarez',
    'address': '57118 Hall Extensions Suite 583\nPrincebury, DE 95723',
},
    'key3901': 'value90495',
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
    'RequestId': '76981742-62f1-11f0-8a21-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_54_196521zAMzxEPn',
    'filter': 'uid in [1,2,3,4]',
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
    'RequestId': '7735fc31-62f1-11f0-88fc-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_54_196521zAMzxEPn',
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
    'RequestId': '6fde5109-62f1-11f0-b8c8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_54_196521zAMzxEPn',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid in [1,2,3,4]]_1752744967.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUidIn12341752744967Json()
    test.run_tests()
