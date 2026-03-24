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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-100-2]_1752744152_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-100-2]_1752744152.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl12810021752744152Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-100-2]_1752744152.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-100-2]_1752744152.json"
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
    'RequestId': '912db064-62ef-11f0-948c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_31_088056fqKwlqQi',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
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
    'RequestId': '9158feb8-62ef-11f0-8e6f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_31_088056fqKwlqQi',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Brian Sanders',
    'address': '014 Larsen Forges\nNew Jon, FM 16302',
    'text': 'Itself write support popular view day. Trial who his raise rest prepare impact. First together everything stay down itself.',
    'email': 'ymoore@example.com',
    'phone_number': '678-712-7938',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'George Singh',
    'Eric Meyer',
    'Nathan Lowe',
],
    'json': {
    'name': 'Stephanie Valencia',
    'address': '736 Vanessa Street\nChristinaburgh, AK 10651',
},
    'key19863': 'value46648',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Zachary Davis',
    'address': '8240 Connie Orchard Suite 170\nJuliefurt, IN 66093',
    'text': 'Just medical necessary behavior language market hotel moment. Pick writer American number effort. With up fine.',
    'email': 'derekcarson@example.org',
    'phone_number': '641.276.7930',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Susan Lopez',
    'Daniel Daniel',
],
    'json': {
    'name': 'Leah Moon',
    'address': '81575 Matthew Lights Suite 618\nJuarezfort, MT 25145',
},
    'key99385': 'value90397',
    'key52437': 'value46378',
    'key36602': 'value51147',
    'key20216': 'value48074',
    'key19483': 'value95242',
    'key33426': 'value6475',
    'key67196': 'value78369',
    'key32561': 'value5301',
    'key16760': 'value53481',
    'key61608': 'value60682',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Heather Gutierrez',
    'address': '23149 Rachel Glens Apt. 940\nSchmittshire, NY 44136',
    'text': 'Type your natural national administration whatever price. Same order total trip data. Own beyond president hear them evidence sport.',
    'email': 'xmorales@example.org',
    'phone_number': '971-222-8884x43366',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Hernandez',
    'Benjamin Li',
    'Maria Williams',
    'Molly Johnson',
    'Kimberly Miles',
    'Lynn Guerrero',
    'Richard Cooper',
    'Cynthia Sanchez',
    'Lauren Lee',
],
    'json': {
    'name': 'Heather Johnson',
    'address': '7071 Jenkins Hills Apt. 588\nNelsonshire, SD 98165',
},
    'key90603': 'value5639',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jennifer Vincent',
    'address': '2495 Curtis Drives\nLake Juanshire, AL 03937',
    'text': 'Mention success right thing from happen industry. Information themselves or cost foot more fish.\nExecutive dog beyond risk. Group sure deep citizen event physical. Yet can population.',
    'email': 'morgan58@example.com',
    'phone_number': '+1-604-672-2041x12517',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brian Kramer',
    'Tammy Gray',
    'Scott Andrews',
    'Patrick May',
    'Bryan Stephenson',
    'Deborah Levine',
    'Michael Crosby',
    'Lisa Baxter',
    'Nicole Robinson',
    'Edward Barnes',
],
    'json': {
    'name': 'Christopher Stephens',
    'address': '70320 Mark Square Suite 156\nMarshallberg, MD 54669',
},
    'key17818': 'value36517',
    'key377': 'value57770',
    'key34652': 'value90306',
    'key41944': 'value91942',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Shannon Reynolds',
    'address': '8259 Wright Well\nVictoriachester, FL 16338',
    'text': 'Son against entire down. Boy she together alone give industry man.',
    'email': 'smolina@example.net',
    'phone_number': '001-415-864-6707x73014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Williams',
    'Amy Riley',
    'Stephen Arellano',
    'Tiffany Reed',
    'Tiffany Scott',
    'Valerie Miller',
    'Christina Landry',
],
    'json': {
    'name': 'Mike Nelson',
    'address': '5895 Carter Inlet Suite 195\nSouth Danielburgh, PR 39223',
},
    'key26537': 'value85519',
    'key80084': 'value55011',
    'key26276': 'value84581',
    'key25992': 'value71030',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Rebecca Lloyd',
    'address': '44895 Daniels Ridges\nKimfort, MH 85773',
    'text': 'Suddenly no ability high deep doctor none. Six property none your share inside. College song certain social. Star book you drive.',
    'email': 'bartonjames@example.com',
    'phone_number': '+1-936-215-2783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Juan Montgomery',
    'Deborah Long',
    'Jaime Johnson',
    'Kevin Kane',
    'Melissa Williams',
    'Rachel Harvey',
],
    'json': {
    'name': 'Curtis Bender',
    'address': '65805 Samantha Brooks\nEast Brandon, GA 20342',
},
    'key82625': 'value87207',
    'key85627': 'value33465',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Angela Miller',
    'address': 'PSC 0240, Box 0078\nAPO AE 34401',
    'text': 'After level your candidate large since. Myself collection next might style support program eat. Data some table detail figure half.',
    'email': 'toddnguyen@example.org',
    'phone_number': '(815)247-9689x6132',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Todd Evans',
    'Kiara Price',
    'Lisa Hill',
    'Janet Wallace',
],
    'json': {
    'name': 'Jeremy Rose',
    'address': '721 Sanders Valley Suite 608\nJohnfurt, NY 47396',
},
    'key7259': 'value92967',
    'key67570': 'value80630',
    'key81783': 'value44149',
    'key45730': 'value11239',
    'key94661': 'value42420',
    'key55568': 'value84605',
    'key39591': 'value63078',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Emily Gray',
    'address': '2635 Robinson Vista\nWest Jillian, AK 45786',
    'text': 'Camera cell important key environmental maintain consumer. List everything sort.\nRemember never never character travel. Approach whole peace impact business perform inside.',
    'email': 'goodmanamy@example.net',
    'phone_number': '550.245.1979x49044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Beth Huffman',
    'Tara Nguyen',
],
    'json': {
    'name': 'William Garner',
    'address': '800 Mann Forks\nPort Jacksonfurt, AL 27327',
},
    'key96671': 'value55584',
    'key9547': 'value59668',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Sean Harris',
    'address': '2381 Butler Path Suite 418\nSandersport, NC 12972',
    'text': 'Six dark glass never think as. Either sound campaign newspaper. Style better listen candidate decide movie.\nReport less enter step present. Certain let million speech radio yet tell.',
    'email': 'rebeccahall@example.net',
    'phone_number': '870.297.0926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Ford',
    'Laura Lee MD',
    'Nicholas Cruz',
],
    'json': {
    'name': 'Angela King',
    'address': '34692 Michael Lodge\nMatthewberg, PA 05784',
},
    'key69110': 'value59444',
    'key83898': 'value28699',
    'key34349': 'value43332',
    'key49983': 'value92562',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Monica Sanders',
    'address': '2841 Kelly Route\nPort Amandabury, WV 53742',
    'text': 'Shake open opportunity water perhaps charge sign. Surface PM scientist toward station.',
    'email': 'kmoore@example.com',
    'phone_number': '001-469-909-2052',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Rasmussen',
    'Joseph Barnett',
    'Courtney Griffith',
    'Mark Roberts',
    'Christie Scott',
    'Jason Anthony',
    'Dennis Pham',
    'Barbara Wood',
    'Laura Phillips',
    'Brandon Alvarado',
],
    'json': {
    'name': 'Joshua Nunez',
    'address': '5480 Vaughn Burgs\nNew John, KS 75545',
},
    'key24570': 'value22138',
    'key41334': 'value71714',
    'key90381': 'value20057',
    'key80535': 'value98912',
    'key99990': 'value46553',
    'key97475': 'value7457',
    'key63409': 'value28349',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Richard Moody',
    'address': '7059 Thompson Spur Suite 334\nSmithbury, NM 44958',
    'text': 'Natural store born plan when already wall. Area understand affect base. Before whether finally study.\nGame current level career. She indicate activity alone. Claim tend American big.',
    'email': 'clarketravis@example.org',
    'phone_number': '(831)901-9820x53220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Arias',
    'Denise Wood',
    'Amy Hayes',
    'Jeanne Rojas',
    'Cassandra Harris',
    'Timothy Williams',
    'James Vincent',
    'Mrs. Melissa Carrillo',
    'Jacqueline Hicks',
    'Brenda Wheeler',
],
    'json': {
    'name': 'Jaclyn Ellis',
    'address': '069 Hernandez Ports Suite 249\nEast Mary, CO 94390',
},
    'key32184': 'value22312',
    'key37868': 'value70792',
    'key16255': 'value5292',
    'key67094': 'value34276',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Brittany Salazar',
    'address': '86422 Mark Wells Apt. 171\nHallshire, OH 21683',
    'text': 'Management marriage chair listen. Heart accept current exist.\nStrong left to half indicate. All fall certainly per improve action two part.',
    'email': 'paulamullins@example.org',
    'phone_number': '+1-432-337-1609x5397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Prince',
],
    'json': {
    'name': 'Mrs. Pamela Baird',
    'address': '268 Harrison Run\nWest Annefort, CA 88908',
},
    'key3478': 'value66616',
    'key16619': 'value93492',
    'key6776': 'value67690',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Gabriela Graham',
    'address': 'PSC 7684, Box 4028\nAPO AA 03251',
    'text': 'School speech color project actually. Yes lot fish bring. Onto recently economic most wish.\nHere choice world region appear. Alone sound idea part.',
    'email': 'cardenasstephanie@example.org',
    'phone_number': '583-205-8470',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Butler',
    'John Lopez',
    'Brendan Fisher',
    'Mr. James Navarro',
    'Michael Mathis',
    'Pamela Middleton',
    'Nancy Hampton MD',
    'Elizabeth Graves',
    'Margaret Sanders',
    'Jade Gonzalez',
],
    'json': {
    'name': 'Alexis Brewer',
    'address': '7487 Troy Pass\nSouth Franciscobury, OK 97961',
},
    'key6439': 'value30796',
    'key28835': 'value15038',
    'key72728': 'value91951',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Rebecca Wright',
    'address': '947 Rojas Cove Suite 044\nEast Kimberly, TX 69639',
    'text': 'Deep learn back participant. History him service. National early want ability. Magazine marriage chair them white without.',
    'email': 'pamelaarmstrong@example.org',
    'phone_number': '421.975.9154x7878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brian Jones',
    'James Johnson',
    'Darren Hicks',
    'Anthony Johnston',
],
    'json': {
    'name': 'Tina Sullivan',
    'address': '61538 Walker Island\nSouth Elizabeth, OR 54521',
},
    'key11944': 'value50736',
    'key52699': 'value91355',
    'key52123': 'value18481',
    'key37684': 'value51194',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Stephanie Webster',
    'address': '33091 Castaneda Causeway Apt. 329\nRomanshire, FL 42118',
    'text': 'Check whom interview might feeling. Resource involve choice their else. Eye some realize red option than.',
    'email': 'tylerallen@example.com',
    'phone_number': '(597)705-7190x279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Perez',
    'Jason Ball',
    'Carmen Bradley',
    'Joshua Farrell',
    'Amy Castillo',
    'Carol Martinez',
    'James Young',
    'Emily Russo',
    'Kathy Robinson',
],
    'json': {
    'name': 'Scott Brooks',
    'address': '9163 Ward Springs\nGilmorestad, DE 90470',
},
    'key39150': 'value29958',
    'key13015': 'value83151',
    'key94859': 'value67581',
    'key62438': 'value37786',
    'key36539': 'value4467',
    'key14220': 'value89923',
    'key26157': 'value69248',
    'key10694': 'value74453',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Tricia Brown',
    'address': '21438 Miller View\nNormanland, VA 63748',
    'text': 'Against civil notice executive television oil. Something contain everybody human store pressure happen.\nCarry future quickly cost world artist be. Now beautiful determine media.',
    'email': 'johnnywhite@example.com',
    'phone_number': '729.561.3135x859',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Steele',
    'Emily Bradshaw',
    'Dylan Russell',
    'Jared Solomon',
    'John Andrews',
    'Chelsea Stephenson DDS',
    'Cynthia Butler',
],
    'json': {
    'name': 'Makayla Stevenson',
    'address': '073 Downs Knoll Suite 001\nLake Vickitown, FL 43621',
},
    'key89958': 'value20453',
    'key10741': 'value87180',
    'key3334': 'value61280',
    'key52540': 'value61170',
    'key39549': 'value5411',
    'key7301': 'value39139',
    'key11923': 'value81610',
    'key90748': 'value2247',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Terry Banks',
    'address': '4296 Kevin Divide\nMichaelport, AZ 36130',
    'text': 'Price glass care. Scene behind organization light himself.\nDegree start to easy gun thus. Another age her stay by wrong. Attack hear require population put price.\nNatural play peace.',
    'email': 'mathewbrown@example.org',
    'phone_number': '925.984.6911x00539',
    'array_int_dynamic': [
    41847,
],
    'array_varchar_dynamic': [
    'Matthew Garcia',
    'Brian Webster',
    'Lauren Barrett',
    'Douglas Barker',
    'Danielle Thomas',
    'David Lewis',
],
    'json': {
    'name': 'Jacob Davis',
    'address': '310 Smith Ramp Suite 654\nPort Patricia, AR 05448',
},
    'key49937': 'value20012',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Ian Gonzalez',
    'address': '2080 Susan Groves Apt. 228\nPort Wesleyton, VA 43850',
    'text': 'Black fast not generation.\nWill stuff him difference out team. Provide country start. Society range company no course base pass.',
    'email': 'corey78@example.net',
    'phone_number': '(388)634-7528x66021',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Steven Gonzalez',
    'Mrs. Christina Lopez',
    'Jane Snyder',
    'Michelle Jackson',
    'Rebecca Evans',
    'Mary Ford',
    'Robert Acosta',
    'Lauren Patterson',
],
    'json': {
    'name': 'Charles Meadows',
    'address': '2894 Lawrence Camp\nWest Andrewhaven, IA 22427',
},
    'key1344': 'value57706',
    'key54651': 'value38155',
    'key84706': 'value86366',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Marc Jimenez',
    'address': '883 Jessica Gardens\nPort Steven, NC 16000',
    'text': 'Speech image fine control only choose. At fall control enjoy television.\nSeries guess degree brother among. War western allow sister available everybody.',
    'email': 'nelsoncameron@example.org',
    'phone_number': '+1-785-703-7547',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Chase Anderson',
],
    'json': {
    'name': 'Michael Oliver',
    'address': '162 Marks Glen\nBlaketon, OH 86357',
},
    'key55918': 'value97167',
    'key65910': 'value54402',
    'key43366': 'value91329',
    'key19846': 'value98621',
    'key61878': 'value51227',
    'key8173': 'value57321',
    'key35968': 'value45865',
    'key94537': 'value4265',
    'key41784': 'value38192',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Lee Cochran',
    'address': '635 Jordan Junction Apt. 364\nEast Zachary, CA 03507',
    'text': 'Son window safe. Explain suggest good spring consider try.\nConference student finish. Mission wrong performance doctor future road.',
    'email': 'dianawhite@example.net',
    'phone_number': '+1-291-603-1815x636',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Chelsea Carey',
    'Christopher Ross',
    'Christopher Peters',
    'Stacy Kelly',
    'Connie Meyer',
],
    'json': {
    'name': 'Melanie Nunez',
    'address': '1241 Smith Walk\nWest Saramouth, LA 50109',
},
    'key38884': 'value77597',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Michael Kline',
    'address': 'PSC 5063, Box 6093\nAPO AA 51554',
    'text': 'Rather film through force. Help fly senior offer such. Ask cut child deal that.',
    'email': 'reidjoseph@example.net',
    'phone_number': '(782)235-0108x6056',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sheryl Berry',
    'Wayne Morse',
    'Samantha Potter',
    'Shelby Hughes',
    'Jessica Zhang',
    'Mary Padilla',
    'James Brown',
],
    'json': {
    'name': 'Susan Morris',
    'address': '540 Brian Spurs\nTylerview, TN 31243',
},
    'key90246': 'value18562',
    'key44095': 'value65314',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Heather Conner',
    'address': '78585 Anthony Well Apt. 620\nNorth Tony, ME 94992',
    'text': 'Anything best hotel worry production. Several experience environment worry five. He base avoid artist her.',
    'email': 'briannalopez@example.org',
    'phone_number': '+1-806-497-8940x773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sean Giles',
    'Stephanie Weiss',
    'Gregory Reed',
    'Susan Foster',
    'Christopher Oneal',
    'Karen Jackson',
    'Jay Velez',
    'Randall Stanley',
    'Joe Austin',
    'Amanda Mclaughlin',
],
    'json': {
    'name': 'Alexis Nguyen',
    'address': 'USS Harvey\nFPO AE 62599',
},
    'key39773': 'value18139',
    'key52090': 'value6220',
    'key77348': 'value14752',
    'key84118': 'value78222',
    'key16641': 'value11654',
    'key14897': 'value49320',
    'key52800': 'value75735',
    'key86422': 'value23132',
    'key92267': 'value3619',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jenny Holloway',
    'address': '298 Kenneth Glen Apt. 080\nSouth Lisachester, VA 02159',
    'text': 'Eye despite who by eye agent. Treat cover own.\nFace lay mind entire. Employee long live head involve official.\nPattern environment finally decide century. Pm mission voice. Hair watch same sign.',
    'email': 'williambarr@example.net',
    'phone_number': '(346)689-1256',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tricia Kelly',
    'David Williams',
],
    'json': {
    'name': 'Raymond Burton',
    'address': '8165 Brooke Station\nWest William, OK 79045',
},
    'key44189': 'value56392',
    'key85326': 'value16390',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Julie Meyer',
    'address': '912 Riley Causeway\nEast Jerryport, RI 87997',
    'text': 'Two rich memory dog husband. Speech popular why course feeling.',
    'email': 'sgilbert@example.org',
    'phone_number': '572.496.9670x20617',
    'array_int_dynamic': [
    93454,
],
    'array_varchar_dynamic': [
    'Jennifer Jensen',
],
    'json': {
    'name': 'Jennifer Olson',
    'address': '4813 Jonathan Well\nAshleyborough, AR 07376',
},
    'key42577': 'value72214',
    'key42986': 'value28707',
    'key21004': 'value29246',
    'key9085': 'value39453',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Alexa Spencer',
    'address': 'Unit 2789 Box 2025\nDPO AE 88684',
    'text': 'Think field carry stage me avoid trouble. Cup throw later part financial. Audience that they step Democrat pressure their.',
    'email': 'anthonymatthews@example.com',
    'phone_number': '622-710-6830x0093',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Justin Hudson',
    'Amy Brown',
],
    'json': {
    'name': 'Alexis Waters',
    'address': '87210 Johnny Street\nCrawfordport, DC 77802',
},
    'key25250': 'value70222',
    'key61626': 'value13876',
    'key19390': 'value49414',
    'key80129': 'value1731',
    'key65894': 'value86578',
    'key93401': 'value33470',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Erica Anderson',
    'address': '165 Mcdonald Squares Suite 706\nWilliamshaven, IA 52225',
    'text': 'Create cell away phone modern thousand. Represent far will result yourself.',
    'email': 'epeters@example.net',
    'phone_number': '629.386.0148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amber Thomas',
    'Michele Baker',
],
    'json': {
    'name': 'Darrell Rodriguez',
    'address': '33522 King Lodge\nNorth Josephberg, UT 30897',
},
    'key68316': 'value97664',
    'key90611': 'value49692',
    'key81043': 'value58271',
    'key86578': 'value74388',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Ryan Morgan',
    'address': 'Unit 5985 Box 6359\nDPO AE 72976',
    'text': 'Could trip value same every top sense religious. Kitchen scientist pick half. Him member key should.',
    'email': 'ucarroll@example.net',
    'phone_number': '316-486-0499x764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Jones',
    'Michael Gonzalez',
    'Samantha Foster',
    'Brian Smith',
    'Joseph Robinson',
    'Erin Johns',
    'Gloria Hamilton',
],
    'json': {
    'name': 'Jesse James',
    'address': '72141 Megan Plain\nDanielborough, SD 23329',
},
    'key46967': 'value14783',
    'key19052': 'value99926',
    'key28142': 'value37338',
    'key33534': 'value45886',
    'key46974': 'value66373',
    'key24555': 'value73515',
    'key44706': 'value88730',
    'key95285': 'value84069',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Nathan Campbell',
    'address': '8042 John Grove\nWest Davidfurt, NY 15516',
    'text': 'Stand recently clear major perhaps have head look.',
    'email': 'austinchristopher@example.net',
    'phone_number': '(235)370-6798x2305',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Linda Lopez',
],
    'json': {
    'name': 'Brandon Williams',
    'address': '5838 Jodi Street Suite 143\nNew Lisamouth, MP 30785',
},
    'key52258': 'value33233',
    'key62398': 'value13769',
    'key57877': 'value32773',
    'key8376': 'value51801',
    'key36427': 'value21470',
    'key1018': 'value36459',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Lynn Young',
    'address': '59182 Matthew Extension Suite 469\nSuzanneside, CT 22523',
    'text': 'Last change look save nation. Approach up adult see prepare order strategy region.\nTake and skill film take media TV. Lose throw medical we ask sea. Sell party stand social.',
    'email': 'darrenshort@example.net',
    'phone_number': '477-829-3923x24498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Bennett',
    'Sara Knox',
    'Christopher Montgomery',
    'Allison Peterson',
],
    'json': {
    'name': 'Ms. Elizabeth Miller MD',
    'address': '91899 Antonio Gardens\nTaylorton, AL 17713',
},
    'key30204': 'value84023',
    'key94596': 'value80543',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Susan Martin',
    'address': 'PSC 7060, Box 8838\nAPO AP 51884',
    'text': 'Ball prove chance once training. Respond have night popular. Down face few oil will raise under. Gun herself right three.',
    'email': 'justin39@example.org',
    'phone_number': '(610)325-1418',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Bowen',
    'Jill Hanna',
    'Anne Davis',
    'Kenneth Ramirez',
    'Alicia West',
    'Michael Rivera',
],
    'json': {
    'name': 'Elizabeth Mendoza',
    'address': '130 Sean Streets Suite 259\nPort Maria, MP 77122',
},
    'key94179': 'value54622',
    'key93213': 'value44632',
    'key5838': 'value14332',
    'key41313': 'value43191',
    'key91362': 'value56040',
    'key9610': 'value84110',
    'key16016': 'value54764',
    'key28368': 'value7969',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Kathleen Lowe',
    'address': 'Unit 1756 Box 7387\nDPO AE 09773',
    'text': 'Free professional spring stop worker arrive public theory.',
    'email': 'alfredburton@example.com',
    'phone_number': '628.420.8588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Virginia Bishop',
    'Allison Sandoval',
    'Aaron Coffey',
    'David Wheeler',
    'Samantha Garcia',
    'Teresa Holt',
    'Molly Farley',
],
    'json': {
    'name': 'Brian Watson',
    'address': '895 Palmer Gardens Apt. 652\nNorth Katherineberg, OK 60926',
},
    'key469': 'value90285',
    'key86378': 'value22962',
    'key78730': 'value42591',
    'key5167': 'value90180',
    'key51755': 'value76619',
    'key65429': 'value21900',
    'key56843': 'value45256',
    'key7829': 'value19500',
    'key90322': 'value5204',
    'key14000': 'value17005',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Justin Ward',
    'address': '570 Benjamin Lake\nMarkfort, TX 67832',
    'text': 'Production friend blue your cover leader. Activity her rise more about.\nCustomer crime only vote. Fill tough speech light control seem guess.',
    'email': 'danielle98@example.com',
    'phone_number': '(591)745-3518x17796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Ayala',
    'Ashley Noble',
    'Mr. Kenneth Payne DVM',
    'Brian Trujillo',
],
    'json': {
    'name': 'Cynthia Edwards',
    'address': '7946 Veronica Ford\nNorth Amanda, AR 19120',
},
    'key25157': 'value32467',
    'key83619': 'value13446',
    'key98468': 'value39348',
    'key14805': 'value50368',
    'key72375': 'value26687',
    'key72693': 'value25163',
    'key27405': 'value90929',
    'key53216': 'value55630',
    'key29282': 'value95050',
    'key26918': 'value40528',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Desiree Williams',
    'address': '5962 Curtis Heights Apt. 377\nEast Justinburgh, GA 48523',
    'text': 'Spend in interview subject. Point wish address end degree may.\nModel learn religious write. Wall see wide law.\nPut management newspaper again. Result employee name.',
    'email': 'heather08@example.org',
    'phone_number': '001-455-745-5923',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Levi David',
    'Leah Reynolds',
],
    'json': {
    'name': 'Rebecca Dixon',
    'address': '8037 Meyers Orchard\nAndrewland, WV 76835',
},
    'key39245': 'value26699',
    'key40695': 'value28806',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Tony Ramirez',
    'address': '7180 Logan Forest\nEast Amandafurt, ND 06441',
    'text': 'Democrat fish story difference side. People science the south real seven.\nShow learn head theory necessary. Apply employee police born right election.',
    'email': 'groberson@example.org',
    'phone_number': '001-415-436-2559x310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Hoover',
    'Jason Robinson',
    'Jennifer Farmer',
    'Christina Bradley',
],
    'json': {
    'name': 'Vanessa Evans',
    'address': '331 Patel Prairie\nWallaceburgh, AZ 71168',
},
    'key69838': 'value17915',
    'key93303': 'value51445',
    'key89452': 'value30827',
    'key85758': 'value38242',
    'key88518': 'value21810',
    'key43574': 'value53645',
    'key18377': 'value33791',
    'key50339': 'value85045',
    'key55539': 'value47104',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Ashley Bailey',
    'address': 'PSC 8859, Box 6135\nAPO AP 21850',
    'text': 'Newspaper doctor former pattern member. Animal entire letter court some increase your recently.\nGreen economic technology view take far. Parent teach street unit since. Game market hot.',
    'email': 'richardwashington@example.org',
    'phone_number': '9284371355',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Duane Wallace',
    'Brittany Smith',
],
    'json': {
    'name': 'Laura Black',
    'address': '091 Michael View\nLake Lisa, CA 09596',
},
    'key29898': 'value95678',
    'key80817': 'value10291',
    'key25724': 'value11634',
    'key35207': 'value43970',
    'key67606': 'value68018',
    'key90741': 'value57405',
    'key4': 'value19936',
    'key33031': 'value41378',
    'key76214': 'value76315',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Edward Perez',
    'address': '247 Moore Underpass Suite 956\nWest Alexisside, WI 88426',
    'text': 'Others item ground dark pass air plant. History example suffer with baby. Stock relate almost quality himself point authority.',
    'email': 'harrisjacqueline@example.com',
    'phone_number': '646.645.6325',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mark Smith',
    'Danielle Chapman',
    'Anthony Zhang',
    'Peter Williams',
],
    'json': {
    'name': 'Kimberly Smith',
    'address': '6928 Travis Plaza\nSouth Stephen, DE 87506',
},
    'key69801': 'value13988',
    'key56131': 'value56972',
    'key85052': 'value37071',
    'key17887': 'value2166',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'John Velazquez',
    'address': '2224 Mckinney Lodge Suite 702\nNew Daniel, IN 52065',
    'text': 'Simple industry energy activity compare nation score.\nSing report best way human head. Rule half rich mother race nor drop.',
    'email': 'murraycheryl@example.net',
    'phone_number': '(744)950-3068',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Susan Byrd',
    'Cindy Wong',
    'Lisa Clark',
    'Becky Valencia',
    'Garrett Glover',
    'Judy Frank',
    'Jennifer Richardson',
    'Rebecca Parker',
    'Edward Dyer Jr.',
    'Autumn Stephenson',
],
    'json': {
    'name': 'Robin Rodriguez',
    'address': '72637 Vazquez Fords Suite 840\nHuffberg, WV 47141',
},
    'key50212': 'value73657',
    'key79671': 'value9399',
    'key26806': 'value60364',
    'key1094': 'value4005',
    'key28314': 'value18748',
    'key89810': 'value86021',
    'key69632': 'value33744',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Mrs. Rachel Zimmerman MD',
    'address': '45259 Johnson Harbors Suite 153\nAlvarezborough, OR 17914',
    'text': 'Notice compare item dog although south major. Page life final challenge attention game. Team radio bad second.\nAct president gun day sound here. Attack me result hope.',
    'email': 'fjones@example.net',
    'phone_number': '763-445-9322x733',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Marshall',
    'Cynthia Hudson',
    'Gregory Roman',
    'Casey Clark',
    'Kimberly Manning',
    'Michael Stewart',
    'Benjamin Dorsey',
],
    'json': {
    'name': 'Michael Mcdaniel',
    'address': '742 Jared Lodge\nSouth Amyfurt, NV 05763',
},
    'key48032': 'value58317',
    'key51890': 'value68068',
    'key18305': 'value20345',
    'key61487': 'value11362',
    'key99319': 'value57743',
    'key42438': 'value69242',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Heidi Gutierrez',
    'address': 'USS Blair\nFPO AE 11454',
    'text': 'Else interest bill. Everything fear truth minute hotel new car. Effort ahead including fight wide.\nManagement window skin near eye time cold. They animal respond white new simply soldier.',
    'email': 'lmoore@example.net',
    'phone_number': '4106298527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Adam Woodward',
],
    'json': {
    'name': 'Matthew Walker',
    'address': '58094 Horton Garden\nEast Donna, SC 03528',
},
    'key69324': 'value16709',
    'key31167': 'value45932',
    'key8764': 'value68094',
    'key46200': 'value4474',
    'key4374': 'value16862',
    'key94024': 'value7562',
    'key94436': 'value84460',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Robin Mcdonald',
    'address': '315 Joshua Courts Suite 534\nSouth Kim, NC 27570',
    'text': 'Case wind street. My provide good fine floor question.\nTalk inside main option tonight ball even thousand. Up size pay indeed house. Toward behind every often life.',
    'email': 'torreslaura@example.com',
    'phone_number': '818.228.5487',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Gray',
    'Samantha Moore',
    'Dwayne Park',
    'Theresa Paul',
    'Carol Carrillo',
    'Kelli Smith',
    'James Bonilla',
    'Richard Williams',
    'Kevin Stuart',
    'Alyssa Delgado',
],
    'json': {
    'name': 'Nathan Clarke',
    'address': '572 Hatfield Roads\nWest Jason, NV 11923',
},
    'key39505': 'value7586',
    'key95846': 'value53940',
    'key4704': 'value64563',
    'key61041': 'value56869',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Wendy Robinson',
    'address': '534 Hall Plains Apt. 512\nWest Charles, GU 42037',
    'text': 'Degree go less pay order realize. Hard office fish seem art fact sister.\nThan here lose without be throughout. Recent admit above there will around not.',
    'email': 'joshua65@example.org',
    'phone_number': '001-810-975-7580x77880',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Richard Chavez MD',
    'Rebecca Torres',
    'Daniel Jordan',
    'Luis Wilcox',
    'Joyce Obrien',
    'Eric Williams',
    'Brooke Ramirez',
    'Juan Sexton',
    'Jeffrey Leonard',
    'William Wilson',
],
    'json': {
    'name': 'Amanda Oconnor',
    'address': '808 Cody Dam Apt. 451\nNew Christinaland, AZ 65060',
},
    'key62050': 'value80494',
    'key63437': 'value57428',
    'key60255': 'value50191',
    'key67019': 'value59393',
    'key29362': 'value59942',
    'key98353': 'value90513',
    'key29039': 'value64085',
    'key44393': 'value92388',
    'key38009': 'value53150',
    'key87664': 'value3900',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Marissa Hicks',
    'address': '46391 Benjamin Pike\nWest Jessica, LA 86097',
    'text': 'Theory threat peace wonder space look draw. Civil blue but.\nMonth again upon movie.\nFinish step role morning trial they. Attention decide safe expect half. Imagine us treatment.',
    'email': 'cassidy60@example.org',
    'phone_number': '001-773-776-2037x00973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'David Young',
    'Todd Jacobs',
    'Brittany Hardin',
],
    'json': {
    'name': 'Antonio Diaz',
    'address': '266 Christina Trail Apt. 144\nEast Travis, ID 45148',
},
    'key17340': 'value677',
    'key49277': 'value52357',
    'key52930': 'value15673',
    'key15471': 'value60534',
    'key57740': 'value88144',
    'key38712': 'value30616',
    'key44526': 'value99068',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Monica Adkins',
    'address': '8934 Williams Rapid\nSouth Paulhaven, MI 08653',
    'text': 'Heavy main owner product listen degree. Professor operation join. Program sure case might.\nMemory know development she. Catch not new late. Situation alone look play.',
    'email': 'brittanysmith@example.com',
    'phone_number': '+1-586-378-5252',
    'array_int_dynamic': [
    39757,
],
    'array_varchar_dynamic': [
    'Bradley Boyle',
],
    'json': {
    'name': 'Mark Benjamin',
    'address': '98840 Matthew Plains Suite 217\nLake Matthew, LA 80116',
},
    'key53840': 'value44391',
    'key18855': 'value77193',
    'key1173': 'value76002',
    'key93781': 'value80852',
    'key71831': 'value87303',
    'key71911': 'value40270',
    'key80931': 'value60606',
    'key69491': 'value78733',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Roy Mendoza',
    'address': '55134 Elizabeth Crest\nPort Cindyfurt, PW 27384',
    'text': 'Parent child history call challenge people. Member no system describe process sit hotel. Guess light student its stand. System program those tough successful compare crime.',
    'email': 'dillonnixon@example.org',
    'phone_number': '295.432.9637x8076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Laura Simpson',
],
    'json': {
    'name': 'Megan Price',
    'address': '6060 Cruz Meadow\nLittleborough, IA 11735',
},
    'key33285': 'value35868',
    'key81902': 'value76104',
    'key23081': 'value21916',
    'key47973': 'value61027',
    'key48166': 'value69725',
    'key49203': 'value31739',
    'key47218': 'value32118',
    'key61253': 'value21583',
    'key74651': 'value691',
    'key65313': 'value48099',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Sydney Gould',
    'address': '16468 Molina Ville\nWest Valerieshire, MA 18746',
    'text': 'Take population affect field national how. Community similar yes scientist popular street prepare source.',
    'email': 'tayloreric@example.com',
    'phone_number': '929.952.7727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Mckee',
    'Taylor Houston',
],
    'json': {
    'name': 'Jennifer Larson',
    'address': '60710 Perry Spur Suite 640\nPort Nathanton, CT 39698',
},
    'key8250': 'value65158',
    'key94366': 'value84332',
    'key88470': 'value70206',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Samantha Ramirez',
    'address': '0890 Simpson Ports\nWest Travis, FL 67357',
    'text': 'System certainly sound hospital edge alone. Something current guess decide happy member public new.\nForeign form drug stop fact. Price team see bar bed.',
    'email': 'wguerrero@example.net',
    'phone_number': '568.950.0187x692',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jody Carr',
    'Dr. Dennis Roberts',
    'Juan Frazier MD',
    'Joan Weber',
],
    'json': {
    'name': 'Tammy Brown',
    'address': '454 Nicholson Run Suite 573\nNorth Wendy, VA 89274',
},
    'key93391': 'value1052',
    'key45640': 'value88046',
    'key47907': 'value54933',
    'key53015': 'value35805',
    'key22272': 'value95682',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Maria Duncan',
    'address': '4029 White Trafficway\nCarolstad, PA 16255',
    'text': 'Stuff close west day rate would nearly. Our parent player.',
    'email': 'wagnerwalter@example.org',
    'phone_number': '(711)534-9292',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Gomez',
    'Sarah Walker',
    'Justin Torres',
    'Theresa Anderson',
],
    'json': {
    'name': 'Joseph Delgado',
    'address': '180 Timothy Cliffs\nSouth Paul, TN 86384',
},
    'key93452': 'value50475',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Mariah Murphy',
    'address': '70465 Perkins Port Suite 259\nMooreview, IN 89623',
    'text': 'Bad agreement doctor expect. Provide society guess mention government report.\nSouthern include possible yourself. Hotel charge step stand hair. Five measure quickly whose even.',
    'email': 'sjones@example.net',
    'phone_number': '001-571-690-5386x6137',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Collins',
    'Melissa Jones',
    'Chris Adkins',
    'Jamie Castillo',
],
    'json': {
    'name': 'Jose Bailey',
    'address': '62097 Cynthia Heights\nEast Paul, SC 45036',
},
    'key26002': 'value26102',
    'key53318': 'value25388',
    'key96114': 'value22561',
    'key52469': 'value93988',
    'key27883': 'value98569',
    'key38089': 'value4855',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Hannah Davis',
    'address': '72278 James Neck\nEast Whitneyville, NJ 33416',
    'text': 'Accept music impact choose really do white. Agent business us. Require surface budget expert husband.\nKitchen than stay available big really phone. Kid weight Mr difference.',
    'email': 'christophergay@example.net',
    'phone_number': '001-390-417-6549x726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Martinez',
    'Ann Page',
    'Jason Reyes',
    'Joshua Patrick',
    'Jennifer Thomas',
    'Nicole Johnson',
    'Edward Fitzgerald',
    'Kathy Mendoza',
    'Sandra Castaneda',
    'James Jackson',
],
    'json': {
    'name': 'Melissa Roberts',
    'address': '7825 Kristopher Lakes Suite 463\nCoryberg, AL 20421',
},
    'key90370': 'value17443',
    'key50211': 'value45666',
    'key14166': 'value84911',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Christine Shaw',
    'address': '7253 Jessica Ferry\nAmandafort, NV 50798',
    'text': 'Baby history number positive. Drug wrong change wonder.\nGun food resource no choice government. Leader deal would where cause chair. Stage hand politics whether close.',
    'email': 'mitchell66@example.com',
    'phone_number': '001-358-537-0567x73741',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amber Carey',
    'Marcia Rodriguez',
    'Amber Jones',
    'Michelle Phillips',
    'Keith Brown',
],
    'json': {
    'name': 'Cindy Weber',
    'address': '4475 Catherine Lakes\nNorth Andrewstad, HI 31301',
},
    'key478': 'value20185',
    'key5035': 'value23990',
    'key39007': 'value40871',
    'key64092': 'value13539',
    'key23722': 'value29511',
    'key95531': 'value67748',
    'key25237': 'value81780',
    'key18475': 'value39431',
    'key6062': 'value38474',
    'key26711': 'value55247',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Juan Reyes',
    'address': '8907 Boyer Loop\nPort Billy, FM 86390',
    'text': 'Involve season special call. Hard fill consumer cover. State cup leader understand.\nEye suggest movie perform service tonight. Imagine financial stage car free.',
    'email': 'mgonzalez@example.com',
    'phone_number': '(676)256-4652x3815',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Ramirez',
    'Lori Waters',
    'John Zimmerman',
],
    'json': {
    'name': 'Bianca Young',
    'address': '1795 Laura Falls\nNorth Seantown, PR 52108',
},
    'key94387': 'value80569',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Ashley Estrada',
    'address': '4088 Amanda Mountain Apt. 617\nNew Joshua, OH 91534',
    'text': 'Huge set mind from good. Room yard wife job. Husband paper style some present. Sense share husband.\nSend of American movement bag even. Mrs account Republican need wrong law. Build ask themselves.',
    'email': 'hayesjean@example.org',
    'phone_number': '001-653-702-7202x306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Anita Miller',
    'Shane Villa',
    'Norman Estes',
    'Daniel Wilson',
    'Joy Knight',
],
    'json': {
    'name': 'William Thompson',
    'address': '7343 Wilson Track Suite 642\nDavismouth, LA 24505',
},
    'key87849': 'value11169',
    'key12978': 'value86008',
    'key42940': 'value60463',
    'key60117': 'value66587',
    'key12899': 'value87853',
    'key40591': 'value17589',
    'key45656': 'value70319',
    'key52543': 'value2243',
    'key34109': 'value45396',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Robin Montgomery',
    'address': '701 Manuel Throughway Suite 287\nPort Joshuachester, AK 07914',
    'text': 'Allow claim stop treatment. Increase name consider house movement arm. Suggest among determine fill health.',
    'email': 'kyoung@example.net',
    'phone_number': '577.961.4337',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Fisher',
    'Michael Kent',
    'Daniel Campbell',
    'Danielle Escobar DDS',
    'Samantha Holland',
    'Timothy Rodriguez',
],
    'json': {
    'name': 'William Petersen',
    'address': '643 Barnett Ports\nRebeccaborough, NJ 58444',
},
    'key84088': 'value39386',
    'key26385': 'value98758',
    'key25330': 'value75081',
    'key42229': 'value77295',
    'key74993': 'value34985',
    'key66362': 'value81007',
    'key69048': 'value72222',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Nicholas Morales',
    'address': '928 Jones Gateway\nLake Moniquebury, MS 76485',
    'text': 'Mother key single me challenge. Teacher difficult together minute case explain allow common. Along radio million capital surface direction.',
    'email': 'steven81@example.net',
    'phone_number': '(609)504-9933x07814',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Smith',
    'Amanda White',
    'Tony Sweeney',
    'Daniel Roach',
],
    'json': {
    'name': 'Daniel Cook',
    'address': '6447 Deborah Route\nStephenbury, TX 83358',
},
    'key50237': 'value2968',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Amanda Vasquez',
    'address': '1063 Ramirez Plaza Suite 642\nJessicaland, ME 63187',
    'text': 'Mention serve rich him ever. Help choice four us fall gas sign.\nFocus alone within new. Interest reach himself above body serious idea than. Clear democratic particular even wrong draw against.',
    'email': 'frogers@example.com',
    'phone_number': '001-257-804-7321x8248',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amber Fisher',
    'Walter Torres',
    'Jesse King',
    'Kevin Reed',
    'Elizabeth Mcmillan',
    'Laurie Young',
],
    'json': {
    'name': 'Dorothy Wilson',
    'address': '19961 Jennifer Shoal Suite 601\nSharimouth, IA 43464',
},
    'key31953': 'value80276',
    'key3961': 'value74151',
    'key41493': 'value63009',
    'key86234': 'value32727',
    'key58139': 'value9841',
    'key36523': 'value33299',
    'key39192': 'value38733',
    'key77050': 'value80602',
    'key54161': 'value92667',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Tyler Lynn Jr.',
    'address': '0411 Tracy Expressway\nPort Brandonton, MD 86390',
    'text': 'Inside edge however stock. Could remember too among hotel end. Situation right story.',
    'email': 'fwyatt@example.com',
    'phone_number': '885.825.9709x9072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Spencer',
    'Veronica Aguilar',
    'Joseph Jefferson',
    'Samuel Mitchell',
    'Mr. Corey Mcgee',
    'Daniel Haynes',
    'Michael Harris',
],
    'json': {
    'name': 'Nicolas Ingram',
    'address': '05743 James Skyway\nParrishmouth, VT 39969',
},
    'key68917': 'value49365',
    'key53099': 'value49579',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Susan Miller',
    'address': '649 Herman Passage Apt. 889\nPort Frederickhaven, VI 10252',
    'text': 'Choice my dark even president debate. Close build per sell across thing fill. Interview game understand long.\nAlong trip answer world. Affect coach character six raise.',
    'email': 'pthomas@example.org',
    'phone_number': '001-883-705-3187x1401',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Molly Marshall',
    'Michael Gillespie',
    'Holly Stephenson',
],
    'json': {
    'name': 'Scott Wise',
    'address': 'USNS Mullen\nFPO AA 51135',
},
    'key95350': 'value50244',
    'key43983': 'value4135',
    'key15918': 'value16486',
    'key54941': 'value8684',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Sean Walls',
    'address': '6646 Delgado Dam\nWilliammouth, OH 94203',
    'text': 'Health different big real account answer. Person her onto community. Cold help dream behind before. Ask available building toward worry western in.',
    'email': 'leoncolin@example.com',
    'phone_number': '(726)730-3271x57002',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Anthony Brown',
    'Crystal Clark',
    'Cameron Larson',
],
    'json': {
    'name': 'Sandra Reed',
    'address': '812 Daniel Tunnel\nNew Lisa, IA 17249',
},
    'key90454': 'value60001',
    'key97342': 'value48919',
    'key50177': 'value87639',
    'key67238': 'value85343',
    'key21723': 'value42901',
    'key94954': 'value87304',
    'key40967': 'value68635',
    'key70503': 'value76550',
    'key41251': 'value2639',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jeremy Wells',
    'address': '914 Camacho Light\nJenniferburgh, AZ 47974',
    'text': 'Mrs drug forget. He style nation.\nStore Republican address those. Toward idea director learn picture fast six.',
    'email': 'bryantgeorge@example.net',
    'phone_number': '(287)889-5542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Justin Burgess',
    'Daniel Fowler',
],
    'json': {
    'name': 'Tammy Roy',
    'address': '03722 Adams Falls\nRogerview, GA 84794',
},
    'key24045': 'value68761',
    'key12947': 'value59385',
    'key36672': 'value33730',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Elizabeth Garcia',
    'address': '0408 Frank Plains Apt. 718\nNew Randy, MS 75295',
    'text': 'Knowledge give pressure PM area throw. Night mention enter hour commercial. Recent dark data good.\nNature plant second think purpose employee. Strategy five argue everybody.',
    'email': 'fsharp@example.net',
    'phone_number': '001-920-531-5411x7374',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Donna Ortiz',
    'Eric Wilson',
    'Jonathan Richardson',
    'Donald Armstrong',
    'Christina Hoffman',
    'Alexis Gibbs',
],
    'json': {
    'name': 'Dominique Wolf',
    'address': '0922 Patrick Expressway Suite 638\nSouth Catherine, NE 95335',
},
    'key62494': 'value35684',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Carl Davis',
    'address': '40931 White Union Apt. 480\nEast Edward, KY 05387',
    'text': 'Site pattern arrive trip. Could finally sense heart. A see quite beyond establish game specific manager.\nBy answer goal finish throughout environmental war let. Accept wind black those fire.',
    'email': 'marie04@example.net',
    'phone_number': '001-646-394-6918x5313',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Scott',
    'Travis Gonzalez',
    'Allison Fox',
    'Ryan Taylor',
    'Leslie Stark',
    'Wendy Brown',
    'Keith Lowe',
],
    'json': {
    'name': 'Melissa Hamilton',
    'address': '48097 Kenneth Courts\nEast Morganhaven, AK 72097',
},
    'key49556': 'value50526',
    'key66638': 'value47741',
    'key69579': 'value6160',
    'key25428': 'value70589',
    'key94934': 'value33573',
    'key23285': 'value43314',
    'key26697': 'value33797',
    'key38143': 'value11244',
    'key86039': 'value5588',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Anne Campbell',
    'address': '14326 Amy Shore\nAmbershire, FM 49151',
    'text': 'Nor fire should whole Congress instead machine.\nReduce scientist trial affect later owner shake. Result above hear everyone whatever maintain dark rise. Often want chance.',
    'email': 'kristineshelton@example.net',
    'phone_number': '+1-936-895-4984x42536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Julie Stephens',
    'Scott Gonzalez',
    'Joshua Parker',
    'Derrick Lee',
    'Tracy Vaughn',
    'Juan Nielsen',
    'Phyllis Sanchez',
],
    'json': {
    'name': 'Kristy Caldwell',
    'address': '292 Rodney Plains\nSaunderstown, DE 87007',
},
    'key44812': 'value86580',
    'key93697': 'value73016',
    'key16863': 'value9178',
    'key26021': 'value30377',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Michael Novak',
    'address': '29792 Lee Roads Suite 490\nBrittanyhaven, ME 26447',
    'text': 'Describe later ever perhaps scene hotel similar.\nSeat nature raise technology hair ahead. This enter keep behavior everyone price. Similar hour series choose because discuss toward rich.',
    'email': 'johnsondawn@example.org',
    'phone_number': '001-678-961-3985x4813',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christian Weeks',
    'Maria Archer',
    'Shannon Paul',
    'Scott Green',
    'Crystal Moore',
],
    'json': {
    'name': 'Ryan Chavez',
    'address': '3420 Derrick Crossroad Apt. 797\nPort Brandonhaven, NH 96996',
},
    'key55021': 'value22637',
    'key62433': 'value36769',
    'key10543': 'value56086',
    'key39495': 'value28993',
    'key98566': 'value56847',
    'key96204': 'value25116',
    'key14865': 'value78213',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Steven Spencer',
    'address': '8942 Rickey Freeway\nWheelerview, AS 09879',
    'text': 'Dark either standard daughter out force case. Cup bad do vote each.\nProcess professor smile mother least. Too around friend last enjoy arm decision.',
    'email': 'qwaller@example.com',
    'phone_number': '818-284-1188',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Bruce',
    'Kayla Freeman',
    'Carla Phillips',
    'Katie Walker',
    'Matthew Caldwell',
    'Tonya Buckley',
    'Michael Stewart',
    'Rebecca Moss',
],
    'json': {
    'name': 'Karen Caldwell',
    'address': '89036 Robin Orchard\nEast Caroline, AS 65221',
},
    'key13840': 'value76299',
    'key62520': 'value31093',
    'key41309': 'value66146',
    'key58448': 'value62575',
    'key22719': 'value56760',
    'key11701': 'value56399',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Alicia Clayton',
    'address': '924 Brian Gateway Suite 423\nGrantmouth, MT 06607',
    'text': 'Would attorney on apply question story television nice. Food leg character might up sure born general. Add week nice song.',
    'email': 'kimberlyflores@example.com',
    'phone_number': '849.674.0517',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Richard',
    'Tyler Pugh',
    'Cassandra Mcintosh',
    'Linda Nicholson',
],
    'json': {
    'name': 'Michelle Jones',
    'address': '0158 Sarah Courts Suite 019\nLake Christopher, FM 15108',
},
    'key93938': 'value57488',
    'key31409': 'value3429',
    'key31988': 'value25256',
    'key97559': 'value54584',
    'key98362': 'value86918',
    'key48661': 'value79676',
    'key74760': 'value95538',
    'key11983': 'value80981',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jesus Villanueva',
    'address': '547 Raymond Spring Suite 598\nLake Mary, WA 50211',
    'text': 'Range room authority science include. We mean read under television we.\nWatch debate once often day artist ground common. Exactly close someone capital almost. Onto card set computer energy number.',
    'email': 'jennifer53@example.net',
    'phone_number': '859.807.6035x208',
    'array_int_dynamic': [
    9504,
],
    'array_varchar_dynamic': [
    'David Carr',
    'John Castillo',
    'Christine Hopkins',
    'Michael Barker',
    'Cynthia Fitzpatrick',
    'Ryan Stewart',
    'James Avila',
    'Carla Espinoza',
    'Lauren Delgado',
    'Nancy Jordan',
],
    'json': {
    'name': 'Shelby Clark',
    'address': '086 James Mountains Suite 581\nDelgadofort, KS 65880',
},
    'key23256': 'value23109',
    'key18131': 'value91069',
    'key72281': 'value10512',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Melissa Martinez',
    'address': '0934 Michael Forge\nStevenborough, TN 04624',
    'text': 'Catch build letter that. Strong add data. Across explain reason system heavy entire TV.\nLevel chance mention agency. According drive probably sign finally cell. Guess bill develop.',
    'email': 'frank38@example.org',
    'phone_number': '317-485-0456x06508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kim Huff',
],
    'json': {
    'name': 'David Anderson',
    'address': '6125 Porter Motorway Apt. 971\nWest Gregory, MS 20775',
},
    'key73221': 'value87668',
    'key69186': 'value45048',
    'key86656': 'value56944',
    'key50580': 'value41868',
    'key62248': 'value76527',
    'key52152': 'value82482',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Ryan Noble',
    'address': '846 Young Meadow\nPhillipton, FL 31676',
    'text': 'To support character. Cold nothing southern collection bag hour win daughter. That stuff appear yet task.\nInformation way main choose more.',
    'email': 'bonillakevin@example.org',
    'phone_number': '(882)498-9845x349',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gary Parks',
    'Betty Clark',
    'Heather Lopez',
    'Daniel Smith',
    'Bryan Davis',
    'Tonya Klein',
    'Deborah Hamilton',
    'Ashley King',
    'Kevin Watkins',
],
    'json': {
    'name': 'Brandy Wheeler',
    'address': '276 Tyler Prairie Suite 254\nStevensonfurt, WA 19408',
},
    'key8452': 'value34473',
    'key26237': 'value85051',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Erin Rios MD',
    'address': 'PSC 1240, Box 4402\nAPO AP 80854',
    'text': 'Hope south customer business once. Enjoy what walk safe school. Teach campaign research cold another raise item heart.',
    'email': 'lucaskaren@example.net',
    'phone_number': '780.638.6485x321',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Richmond',
    'Anita Ramirez',
    'Kyle Wilson',
    'Allison Cruz',
    'Darryl Lewis',
    'Summer Weaver',
    'Melissa Carter',
    'Matthew Smith',
    'Katelyn Garcia DVM',
    'Spencer Valencia',
],
    'json': {
    'name': 'Sandra Chambers',
    'address': '5480 Newman Turnpike Suite 080\nMorenochester, ND 33774',
},
    'key20490': 'value60693',
    'key64247': 'value836',
    'key21980': 'value80104',
    'key67258': 'value94518',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Alexander Hayes',
    'address': '879 Andrews Streets\nEast Amanda, NH 62505',
    'text': 'Score poor letter expect arm. Clearly player whatever yourself produce officer like.\nSystem land bar his floor. Leave who throw prepare statement.',
    'email': 'xwilliams@example.org',
    'phone_number': '001-215-564-5906x38316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Miller',
    'Luis Owen',
    'Jessica Mccoy',
],
    'json': {
    'name': 'Lauren Rivera',
    'address': '119 Ashley View\nOrtegashire, AL 39148',
},
    'key7009': 'value13262',
    'key60294': 'value71054',
    'key18918': 'value46471',
    'key79574': 'value24255',
    'key47943': 'value57107',
    'key37287': 'value50013',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Joshua Clark',
    'address': '99322 Joseph Roads\nJoshuamouth, CT 07880',
    'text': 'Including smile animal back friend reality art.\nStrong this player also always water. Off town would someone financial first seat. Level money enjoy parent trip.',
    'email': 'cstewart@example.net',
    'phone_number': '708.528.6661x980',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lori Chavez',
    'Robert Poole',
    'Michael Wu',
    'Mary Thomas',
    'Dustin Jones',
    'Debra Thompson',
    'Sarah Mcdowell',
    'Nicole Leonard',
    'Carly Barker',
],
    'json': {
    'name': 'Alicia Garza',
    'address': '72831 Sharon Court Apt. 044\nSeanhaven, MO 09748',
},
    'key96985': 'value21558',
    'key99564': 'value4603',
    'key61634': 'value85329',
    'key13298': 'value3288',
    'key45383': 'value48631',
    'key72311': 'value78337',
    'key27853': 'value673',
    'key56983': 'value44219',
    'key96246': 'value59036',
    'key41740': 'value69687',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jeremy Rice',
    'address': 'PSC 1936, Box 5232\nAPO AA 76218',
    'text': 'Without season officer since system. Give friend able seem member artist.\nPoint perform adult again ready. Several many voice. Project consider effort bill.',
    'email': 'caitlin04@example.com',
    'phone_number': '+1-756-331-8754x5686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mark Henson',
    'Darren Kidd',
    'Andrea Campbell',
    'Elizabeth Peterson',
    'Kari Williams',
    'Ariel Lopez MD',
    'Beth Hansen',
    'Robin Chavez DDS',
],
    'json': {
    'name': 'Andrew Sloan',
    'address': '73021 Cynthia Landing\nKatherinebury, RI 07333',
},
    'key45043': 'value70811',
    'key56491': 'value18803',
    'key83776': 'value36530',
    'key70395': 'value18204',
    'key92259': 'value88375',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Tracey Nunez',
    'address': '85426 Taylor Springs Suite 736\nJonesland, OK 41930',
    'text': 'Peace stuff it notice I. Exactly boy every develop Congress thank information.\nAccept become camera require debate loss size. Realize environmental lay certainly. Trial statement four maybe begin.',
    'email': 'davidwright@example.com',
    'phone_number': '480-965-2426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Luis Sanders',
    'Mark Weiss',
    'Shawna Hart',
    'Kelly Kennedy',
    'Timothy Miller',
    'Cody Wilson',
],
    'json': {
    'name': 'Matthew Johnson',
    'address': '3974 Mckee Walks\nEast Sharonmouth, SD 85599',
},
    'key33205': 'value14968',
    'key10516': 'value98415',
    'key29619': 'value38691',
    'key62556': 'value93735',
    'key26691': 'value92155',
    'key46196': 'value46220',
    'key1804': 'value66267',
    'key11761': 'value60213',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Sarah Chaney',
    'address': 'Unit 8484 Box 5323\nDPO AA 59675',
    'text': 'Body property concern year. View to ahead cold help event wear help.\nStreet own eye arrive stay both. Suddenly election protect radio difficult style.',
    'email': 'litonya@example.net',
    'phone_number': '3912918227',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joy Galvan',
],
    'json': {
    'name': 'Tony Aguilar',
    'address': '630 Martin Ramp\nWestborough, CO 49847',
},
    'key95243': 'value15866',
    'key14875': 'value77793',
    'key93190': 'value80499',
    'key28786': 'value96536',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'James Stephens',
    'address': '551 Joshua Haven Suite 965\nJeffreyview, AR 54893',
    'text': 'Peace north total network even enjoy material blood. Prepare that culture bad hear would. Billion camera final behind.',
    'email': 'jeffery58@example.com',
    'phone_number': '738-418-9917x69635',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Clifford Green MD',
    'Antonio Martinez',
    'Mark Wilson',
],
    'json': {
    'name': 'Kimberly Gibson',
    'address': '32222 Vicki Junctions\nHernandezberg, FM 43311',
},
    'key62461': 'value95726',
    'key61682': 'value36251',
    'key53902': 'value9246',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Justin Mcmillan',
    'address': '522 Wise Wells\nNew Matthew, VT 56323',
    'text': 'Agency fall music parent after. Operation third create several behind produce.\nFinancial knowledge imagine all boy many cover. Themselves realize treat show.',
    'email': 'terrijames@example.org',
    'phone_number': '+1-910-943-6194x2376',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Susan Diaz',
    'Stuart Brown PhD',
    'Betty Gould',
],
    'json': {
    'name': 'Robin Goodwin',
    'address': '2229 Erin Corner Apt. 798\nMichaeltown, SC 63361',
},
    'key8033': 'value92216',
    'key92298': 'value46257',
    'key52748': 'value98685',
    'key31994': 'value28990',
    'key69238': 'value55913',
    'key35493': 'value9714',
    'key34164': 'value85284',
    'key61401': 'value66913',
    'key43645': 'value38149',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Frederick Espinoza',
    'address': 'USNS Walton\nFPO AE 27954',
    'text': 'Price majority opportunity buy history. View deep TV run media.\nScore source live statement large. Society purpose behind lead already edge area. Particularly main seek.',
    'email': 'mfuller@example.net',
    'phone_number': '971.296.0973x33682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christina Garcia',
    'Jeffrey Raymond',
    'Casey Gonzalez',
],
    'json': {
    'name': 'Courtney Carter',
    'address': '4566 Richardson Mountains Suite 326\nPort Brandonview, CA 67358',
},
    'key90619': 'value22475',
    'key16507': 'value17855',
    'key38926': 'value68086',
    'key144': 'value38052',
    'key21653': 'value54037',
    'key7905': 'value82796',
    'key26274': 'value81780',
    'key57391': 'value59552',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Kelly Camacho DVM',
    'address': '308 Lopez Knolls Apt. 784\nLake Tonyatown, CA 25282',
    'text': 'Responsibility owner who prepare entire. Whom matter always pull. Experience assume democratic increase top want inside.\nSuccess technology much cover mean local. Item read everyone.',
    'email': 'martinezjulie@example.org',
    'phone_number': '(444)507-2600x81470',
    'array_int_dynamic': [
    53123,
],
    'array_varchar_dynamic': [
    'Rick Villegas',
    'Angela Harris',
    'Stephen Grant',
    'Philip Vazquez',
    'Candace Jefferson',
    'Ryan Martinez',
    'James Ball',
],
    'json': {
    'name': 'Gregory Pitts',
    'address': '009 Cortez Divide\nPadillaville, IN 21904',
},
    'key69219': 'value19160',
    'key52526': 'value59383',
    'key24930': 'value34547',
    'key42625': 'value67524',
    'key10213': 'value66175',
    'key55555': 'value14418',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Anita Hodges',
    'address': '75675 Jimenez Cliffs Suite 910\nAshleyfurt, NE 60687',
    'text': 'Technology go leave. Rather their sport if.\nLeg modern appear feeling serve. Election structure memory listen. Really reality style news.',
    'email': 'horntracy@example.com',
    'phone_number': '+1-827-593-1380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Sullivan',
    'Steven Cummings',
    'Cynthia Coleman',
    'Janet Lamb',
    'Christopher Johnson',
    'Paul Smith',
    'Lindsey Ramos',
],
    'json': {
    'name': 'Kevin Nunez',
    'address': '3497 Wayne Fort Suite 277\nEast Kendrafort, AS 87041',
},
    'key29595': 'value63365',
    'key19754': 'value9618',
    'key88015': 'value82493',
    'key92730': 'value48536',
    'key18564': 'value96594',
    'key98407': 'value27142',
    'key56425': 'value54809',
    'key65344': 'value64804',
    'key80486': 'value57541',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Melvin Conway',
    'address': '48794 Friedman Path\nLake Heidi, VA 53979',
    'text': 'Many explain American population be beyond door police. Purpose maybe walk.\nConcern try wall security I trip. Current condition likely ball thought avoid. Indeed me street cell trial well lay.',
    'email': 'pinedanicole@example.net',
    'phone_number': '(308)848-6109x07022',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Escobar MD',
    'Sharon Davis',
    'Anthony Jackson',
],
    'json': {
    'name': 'Todd Craig',
    'address': '0848 White Rest Suite 701\nLake Bryan, DC 92870',
},
    'key191': 'value52733',
    'key59218': 'value11094',
    'key57886': 'value58999',
    'key91621': 'value47379',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Andrew Dean',
    'address': '49716 Randolph Loaf Suite 360\nCurtiston, AZ 50263',
    'text': 'Report sea the carry resource value nature development. It also step way until. Mrs forget summer candidate adult whole experience month.',
    'email': 'anagarcia@example.org',
    'phone_number': '347.890.6713x5050',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Cole',
],
    'json': {
    'name': 'Julie Lee',
    'address': '184 Williams Loaf Suite 626\nNorth Steventon, WV 68350',
},
    'key11427': 'value48967',
    'key75759': 'value74733',
    'key2576': 'value19761',
    'key33649': 'value7201',
    'key30113': 'value60504',
    'key70409': 'value81106',
    'key28426': 'value37337',
    'key47253': 'value36209',
    'key56369': 'value41409',
    'key11336': 'value13619',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Andrea Crawford',
    'address': '3945 Zhang View Suite 116\nMichaelberg, AR 78373',
    'text': 'Plant my national. Factor girl small stop enough however. However choice them risk result west future necessary. Someone none its animal difficult worry sit personal.',
    'email': 'andersondylan@example.com',
    'phone_number': '493.341.8686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Carpenter',
    'Timothy Nelson',
    'Richard Gates',
    'Richard Chen',
    'Krista Moore',
    'Jessica Mayo',
],
    'json': {
    'name': 'Annette Marshall',
    'address': '3753 Andrew Ridges\nPort Jeffreybury, DC 12025',
},
    'key57986': 'value6344',
    'key78735': 'value68725',
    'key60885': 'value50115',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Mike Bell',
    'address': '5112 Peter Street\nStephanieburgh, MI 97539',
    'text': 'Political first open current today. Alone on either voice though.\nRise manager easy seek data law test. Want large group believe.',
    'email': 'kathleenhill@example.com',
    'phone_number': '525-338-4470',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angela Frazier',
    'Joseph Walton',
    'Andrew Cook',
    'Ronald Hodge',
    'Brandon Morris',
    'Charles Williams',
    'Suzanne Burton',
    'Jennifer Ashley',
    'Justin Goodman',
    'Randall Baker',
],
    'json': {
    'name': 'Mark Flores',
    'address': '5859 Jacob Square Suite 582\nAlantown, NV 93337',
},
    'key63535': 'value42916',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Eric Jackson',
    'address': '99913 Lewis Vista Apt. 856\nTravisfurt, NM 48967',
    'text': 'Finally despite hope away baby soon. Between old evidence everything hour tend continue.',
    'email': 'timothy67@example.org',
    'phone_number': '987-224-8508x6613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Hill',
    'Matthew Brown',
    'Tiffany Allen',
    'David Gonzalez',
    'Veronica Warner',
    'William Briggs',
    'Julie Hernandez',
],
    'json': {
    'name': 'James Newton',
    'address': '60825 Abbott Meadows\nLake Carlos, NE 13041',
},
    'key58861': 'value98663',
    'key3243': 'value5593',
    'key1661': 'value27159',
    'key43717': 'value67534',
    'key48285': 'value63654',
    'key91097': 'value26953',
    'key55081': 'value6262',
    'key30215': 'value80757',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Samantha Hansen',
    'address': '553 Chen Crossing Suite 668\nShelleymouth, MH 41147',
    'text': 'Along contain lay small administration second visit. Second yeah outside happy.\nCause yes perform. Sound or capital view. Box director future reflect within measure born.',
    'email': 'pamela27@example.com',
    'phone_number': '(494)617-6475',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Connor Morrison',
    'Sheila Suarez',
    'Eric Grant',
    'Sheri Gray',
    'Susan Garcia',
    'John Thomas',
    'Jorge Jones',
    'Anna Anthony',
    'Charles Lee',
],
    'json': {
    'name': 'David Mendoza',
    'address': '865 Duncan Trace\nNorth Charlesborough, MH 76020',
},
    'key29287': 'value39300',
    'key63109': 'value2988',
    'key64287': 'value40094',
    'key61544': 'value28715',
    'key19030': 'value97377',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Tyler Matthews',
    'address': '1753 Wiley Corners\nAlisonfurt, OR 09297',
    'text': 'Seek white recently something major. Road provide although effort color must. Stage trade into.\nBefore physical best source lead. Community black partner beyond.',
    'email': 'kayla53@example.org',
    'phone_number': '789.834.4263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Lopez',
    'Judy Wright',
    'Melanie Wood',
    'Daniel Schmidt',
],
    'json': {
    'name': 'Jerome Rogers',
    'address': '71427 Acevedo Squares\nPort Jamesport, KY 12551',
},
    'key94602': 'value43127',
    'key35380': 'value46621',
    'key4457': 'value21939',
    'key76728': 'value11555',
    'key14616': 'value56028',
    'key59882': 'value40249',
    'key30444': 'value76167',
    'key1042': 'value47632',
    'key48423': 'value20094',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Gabriel Baldwin',
    'address': '35575 Hughes Lights Apt. 986\nJameston, AL 65233',
    'text': 'Same partner security receive smile your close road. Close official add today oil hospital.\nWhose perhaps southern across agent and. Her reach anything some nice example agree total.',
    'email': 'pauljohn@example.com',
    'phone_number': '001-789-256-1254',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Adams',
],
    'json': {
    'name': 'Michael Torres',
    'address': '2984 Sherry Mill Suite 996\nWest Monique, MA 53817',
},
    'key82778': 'value25234',
    'key52682': 'value99462',
    'key20165': 'value57932',
    'key20888': 'value24867',
    'key50406': 'value55280',
    'key40730': 'value88739',
    'key73179': 'value23142',
    'key12402': 'value75799',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'William Sanchez',
    'address': '416 Erica Grove\nSouth Julie, AK 86902',
    'text': 'Family education nation beat position fast by. News necessary dream single sort pretty computer.\nAuthor school after push nothing decision. Enter response address.',
    'email': 'mmason@example.com',
    'phone_number': '001-782-505-4396x9660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Julie Choi',
    'Lindsay Diaz',
],
    'json': {
    'name': 'Kenneth Wheeler',
    'address': '1490 Webb Dale\nColemanburgh, WV 45958',
},
    'key92950': 'value36166',
    'key78711': 'value80376',
    'key58720': 'value7048',
    'key97822': 'value41501',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Zachary Li',
    'address': '043 Ross Locks Apt. 124\nBatesville, MT 39905',
    'text': 'Whatever man certainly vote go movement culture. After each western cup.\nGreat spring better still should after national yourself. Cause specific message how.',
    'email': 'monique77@example.org',
    'phone_number': '+1-269-324-5344x9884',
    'array_int_dynamic': [
    19811,
],
    'array_varchar_dynamic': [
    'Cassandra Davis',
    'Tyler Duncan',
    'Cynthia Avery',
    'Colleen Golden',
],
    'json': {
    'name': 'Jamie Delgado',
    'address': '2238 Ryan Heights\nJohnsonmouth, LA 25551',
},
    'key51972': 'value83599',
    'key82511': 'value60798',
    'key74979': 'value90980',
    'key61265': 'value77682',
    'key68563': 'value10889',
    'key60896': 'value70599',
    'key34779': 'value25939',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Jennifer Washington',
    'address': '679 Reyes Vista\nDerekshire, PA 11234',
    'text': 'Show effect someone eat work. Into ground person operation water air degree. Station away no just protect hard cold.',
    'email': 'moorejustin@example.net',
    'phone_number': '281.732.5164x05774',
    'array_int_dynamic': [
    9509,
],
    'array_varchar_dynamic': [
    'Marcus Church',
    'James Tanner',
    'Amanda Moreno',
    'Douglas Smith',
    'Peter Thompson',
],
    'json': {
    'name': 'Brian Wall',
    'address': '69532 Kelly Square\nStephaniechester, ND 64977',
},
    'key47712': 'value61483',
    'key45260': 'value50735',
    'key47724': 'value14717',
    'key70616': 'value45082',
    'key36449': 'value15359',
    'key42087': 'value5133',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'David Villanueva',
    'address': '1906 Benjamin Way\nNew John, NE 48374',
    'text': 'Win guy claim officer future skill wrong.\nCertain place may throw western along leader. Well position seven save issue.',
    'email': 'amanda31@example.org',
    'phone_number': '547.699.8867',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Lopez',
    'Tonya Martin',
    'Eric Haney',
    'Danielle Rios',
    'Todd Stephens',
    'Mrs. Lindsey Smith',
    'Kathy Thompson DDS',
    'Virginia King',
    'Sonya Davies',
    'Sarah Carter',
],
    'json': {
    'name': 'Joanne Moody MD',
    'address': '930 Michael Villages Apt. 739\nHaydenton, PW 98979',
},
    'key30289': 'value9227',
    'key45910': 'value7373',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Kristi Gray',
    'address': '494 Lisa Coves\nChristinatown, OR 92239',
    'text': 'Bring end force. Television box loss talk man.\nDevelop real make hit. Talk modern step bit effort test.\nItem decade lot join. Window soldier collection treatment.',
    'email': 'mclark@example.com',
    'phone_number': '(566)489-7751x7032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Murphy',
    'Jonathan Thompson',
    'Jason Stevenson',
    'David Howell',
    'Julia Perez',
],
    'json': {
    'name': 'Angela Crawford',
    'address': '327 Crawford Pine\nHendersonside, MD 39307',
},
    'key17676': 'value59998',
    'key80084': 'value39818',
    'key44556': 'value28042',
    'key67373': 'value1225',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'James Hernandez',
    'address': '446 Daniel Place\nNorth Andreaburgh, AK 63984',
    'text': 'Everybody civil fight character size. Read own community sea impact strategy. Task never modern. Push could social light wonder.',
    'email': 'melanie03@example.com',
    'phone_number': '(225)319-3171x3496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Steven Estes',
    'Michael Sims',
    'Albert Valdez',
    'Lisa Garner',
    'Betty Thomas',
],
    'json': {
    'name': 'Elizabeth Harper',
    'address': '143 Ashlee Corner Apt. 631\nWardmouth, NJ 68730',
},
    'key62430': 'value60457',
    'key96274': 'value55011',
    'key10118': 'value75010',
    'key72834': 'value6591',
    'key47460': 'value84010',
    'key77356': 'value70994',
    'key38445': 'value5839',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Adrienne Gonzales',
    'address': '295 Dennis Course\nStevenfort, TN 56191',
    'text': 'Develop somebody baby similar. Field spend too decade coach.\nHealth child serve wait.\nAbove understand must book. Current feeling test support compare must.',
    'email': 'stewartjessica@example.com',
    'phone_number': '+1-779-812-4958x4767',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amber Fisher',
    'James Reyes',
    'Thomas Buchanan',
    'Robert Shannon',
    'Michelle Brown',
    'Penny Walker',
],
    'json': {
    'name': 'Michelle Brown',
    'address': '8013 Vasquez Islands Apt. 278\nKeithstad, WI 37088',
},
    'key57378': 'value48696',
    'key29466': 'value57437',
    'key43493': 'value42704',
    'key36708': 'value21146',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Tanya Owens',
    'address': '83353 Karen Neck\nPort Clinton, CT 96048',
    'text': 'Pick administration strong guy let between themselves. Care memory Democrat key charge garden throughout.',
    'email': 'willie55@example.net',
    'phone_number': '288.488.2040',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Reed',
    'Mark Durham',
],
    'json': {
    'name': 'Vicki Morales',
    'address': '0829 David Square\nSouth Bryanborough, ND 56457',
},
    'key21032': 'value60100',
    'key64306': 'value46526',
    'key2814': 'value64652',
    'key48291': 'value31254',
    'key55031': 'value86355',
    'key56559': 'value9711',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Valerie Vargas',
    'address': '790 Pearson Falls Apt. 136\nSouth William, AL 90616',
    'text': 'To animal quickly idea community. Law degree character thus whatever story high.\nNatural our skin move. Space spring raise.',
    'email': 'dpalmer@example.net',
    'phone_number': '(895)813-7428x811',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Hill',
    'Jeffrey Davis',
    'Mrs. Donna Kelly MD',
    'Hannah Green',
    'Marvin Torres',
],
    'json': {
    'name': 'Willie Taylor',
    'address': '6059 Larry Squares Suite 947\nSouth Jessica, CO 53618',
},
    'key60053': 'value15594',
    'key62318': 'value61292',
    'key95524': 'value97350',
    'key80597': 'value76966',
    'key21043': 'value19213',
    'key33124': 'value9447',
    'key92239': 'value34216',
    'key99268': 'value52751',
    'key12607': 'value46152',
    'key70573': 'value74079',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Melinda Sanchez',
    'address': '05582 Martin Key\nTanyaside, GU 02953',
    'text': 'Cut make important close go seem network. Degree amount painting however.\nThan have feel begin. Each hour point arrive late always official. Too white throw fine consumer theory true read.',
    'email': 'wilsonlisa@example.net',
    'phone_number': '545-582-9308x1644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Roger Rhodes',
    'Jeffrey Garcia',
    'Bethany Pace',
    'Spencer Estes',
    'Megan Hayes',
],
    'json': {
    'name': 'Samuel Vargas',
    'address': '160 Karen Forges\nJohnstonmouth, ID 22985',
},
    'key55102': 'value69508',
    'key40490': 'value96854',
    'key37490': 'value87735',
    'key92945': 'value19956',
    'key35477': 'value64521',
    'key41371': 'value4412',
    'key32108': 'value30937',
    'key42485': 'value49507',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Herbert Anderson',
    'address': '20094 Young Trace Apt. 723\nHoffmanfort, VT 99542',
    'text': 'Computer president program consider. Get keep since ten light offer rich.\nInterview structure girl single middle. Ability treat loss possible condition environment program small. Ago camera nearly.',
    'email': 'jennifer15@example.org',
    'phone_number': '+1-888-474-1790x679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diane Smith',
    'William Cook',
    'Michael Cuevas',
    'Courtney Johnson',
],
    'json': {
    'name': 'Kelly Barr',
    'address': '751 Michael Union Suite 433\nSouth Sarah, MI 15369',
},
    'key75425': 'value39134',
    'key52361': 'value37719',
    'key75972': 'value77733',
    'key56914': 'value21701',
    'key11436': 'value53007',
    'key43328': 'value96912',
    'key42670': 'value69904',
    'key98877': 'value27394',
    'key64706': 'value94665',
    'key94777': 'value99877',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Tara Flores',
    'address': '900 Kevin Parks\nAudreyfort, OR 86716',
    'text': 'Person including movement participant guess put. Month ten buy identify.\nLine lay value example old. Thank attention cover capital agent these. Result modern lawyer forget agreement resource or.',
    'email': 'john57@example.com',
    'phone_number': '714-675-6137x21878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Perez',
    'Tammy Mcclure',
    'Stephanie Tanner',
],
    'json': {
    'name': 'Frank Jacobson',
    'address': '2897 Thomas Camp Apt. 554\nHectortown, NY 75808',
},
    'key51833': 'value17330',
    'key69306': 'value27642',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Samuel Oconnor',
    'address': '464 Douglas Corners\nSarahshire, VI 85076',
    'text': 'Wait nor floor wear third eight. Use second degree drug rule hotel thank.\nSuch impact poor little produce. During two car school.',
    'email': 'reidkristin@example.com',
    'phone_number': '6904874264',
    'array_int_dynamic': [
    93694,
],
    'array_varchar_dynamic': [
    'Shawn Mcintosh',
    'Christopher Golden',
    'Steven Parker',
    'Jonathan Campos',
    'Jerry Ramirez',
    'Willie Bernard',
],
    'json': {
    'name': 'Erica Moore',
    'address': '780 Michael Point\nEast Aliciaport, MI 70598',
},
    'key14577': 'value32754',
    'key46015': 'value66780',
    'key75883': 'value37481',
    'key49113': 'value82133',
    'key95033': 'value56774',
    'key3579': 'value69248',
    'key43069': 'value11190',
    'key99536': 'value99717',
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
    'RequestId': '912db064-62ef-11f0-948c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_31_088056fqKwlqQi',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-100-2]_1752744152.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl12810021752744152Json()
    test.run_tests()
