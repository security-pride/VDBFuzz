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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752744993_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752744993.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid01752744993Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752744993.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752744993.json"
        self.test_count = 4  # 测试方法数量
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
    'RequestId': '7fd8041e-62f1-11f0-bea7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_20_998772BmnnOxZM',
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
    'RequestId': '82f8053f-62f1-11f0-8697-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_20_998772BmnnOxZM',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Gina Duke',
    'address': '43179 Carroll Divide Apt. 671\nMillerstad, MS 48272',
    'text': 'Choose bank activity next cause. Time environment staff. Offer other religious.\nFactor home I. Before class short lawyer finally enjoy. Hear opportunity picture need.',
    'email': 'kennedyleah@example.org',
    'phone_number': '421-424-1071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Shelley Lyons',
    'Spencer Nelson',
    'Teresa Smith',
],
    'json': {
    'name': 'Brenda Collins',
    'address': '50864 Hopkins Drives Apt. 759\nWest Kelseyville, CO 09096',
},
    'key64878': 'value3187',
    'key42519': 'value60924',
    'key71747': 'value43682',
    'key40245': 'value71347',
    'key93660': 'value78355',
    'key50567': 'value65615',
    'key90747': 'value28483',
    'key5742': 'value82',
    'key15423': 'value86320',
    'key36885': 'value82224',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Natalie Lee',
    'address': '3035 Simpson Hollow\nEdwardside, OR 91712',
    'text': 'Military sister different would cell item. Wrong system teach staff serve.\nEnjoy full foot loss job what.\nUp old indeed ago. Term western raise on face. Meeting wife arm fall.',
    'email': 'ajacobs@example.org',
    'phone_number': '001-398-762-2563x2106',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Bush',
    'Jennifer Rodriguez',
],
    'json': {
    'name': 'Mary Sanchez',
    'address': '28947 Kimberly Cliff\nNew Johnfurt, VA 06773',
},
    'key9188': 'value87734',
    'key92419': 'value13766',
    'key48362': 'value42878',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Mackenzie Stanton',
    'address': '278 Melinda Ridge Suite 210\nSouth Michelle, AR 11735',
    'text': 'Clear shoulder Republican remain. Among again next color about rich some almost.',
    'email': 'shahangela@example.net',
    'phone_number': '(547)810-6684',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ethan Henry',
    'Barbara Raymond',
    'Carmen Brown',
    'Emily Tucker',
    'Michael Lambert',
    'Elizabeth Coleman',
    'Kathryn Wagner',
    'Kelly Rodriguez',
],
    'json': {
    'name': 'Donna Camacho',
    'address': 'USNV Gonzales\nFPO AP 04056',
},
    'key50838': 'value70216',
    'key43517': 'value49489',
    'key16498': 'value30327',
    'key98460': 'value84870',
    'key92242': 'value59710',
    'key53826': 'value5717',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Yolanda Mitchell',
    'address': '994 Wilson Gardens Suite 031\nSheilamouth, NV 40060',
    'text': 'Little scientist individual better. My leave official measure past all. Score campaign full impact economy capital.',
    'email': 'vdouglas@example.com',
    'phone_number': '(707)478-6823',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Munoz',
    'Laura Valencia',
    'Hannah Farmer',
    'Sean Sosa',
    'Joseph Knapp',
    'Heather Hebert',
    'Kenneth Smith',
],
    'json': {
    'name': 'Maria Rocha',
    'address': '661 Sanders Meadow\nPort Brittanyhaven, DC 84981',
},
    'key24641': 'value61690',
    'key31522': 'value94387',
    'key60722': 'value64561',
    'key38620': 'value87541',
    'key8682': 'value32715',
    'key59382': 'value80078',
    'key71059': 'value36328',
    'key47473': 'value65975',
    'key59338': 'value46798',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Megan Silva',
    'address': '9577 Burton Centers Suite 338\nHinesberg, SC 39404',
    'text': 'Down marriage president. Base push when cover spring agree its pretty. Particular apply daughter through.',
    'email': 'harrisjennifer@example.net',
    'phone_number': '474.926.7892x84674',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Perry',
],
    'json': {
    'name': 'Brandon Klein',
    'address': '435 Griffin Motorway\nJeanborough, OR 89674',
},
    'key91203': 'value35840',
    'key56645': 'value67729',
    'key53297': 'value47829',
    'key3617': 'value29568',
    'key73399': 'value74730',
    'key87599': 'value38154',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Erin Flores',
    'address': '0545 Kaufman Port\nBookershire, MI 43390',
    'text': 'Place themselves organization smile eight last standard. Understand media book college ball keep.',
    'email': 'youngdavid@example.net',
    'phone_number': '879.560.0397x7450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brandy Moore',
    'Brianna Duncan',
    'Dwayne Maxwell',
    'Daniel Velazquez',
    'Tina Villarreal',
    'Matthew Reeves',
    'Nicholas Scott',
    'Sarah Delgado',
],
    'json': {
    'name': 'Anita Johnson',
    'address': '57082 Jones Villages\nJessicaberg, IL 76844',
},
    'key89448': 'value19136',
    'key3670': 'value41307',
    'key70923': 'value81451',
    'key27977': 'value81567',
    'key83911': 'value8530',
    'key84300': 'value36329',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Andrew Green',
    'address': 'Unit 0139 Box 6543\nDPO AA 82756',
    'text': 'Matter popular option mouth wall data result claim. Culture participant experience husband.\nMessage large prepare general table. Cut name teach for.\nEffect they life trial.',
    'email': 'jonesmegan@example.net',
    'phone_number': '001-401-726-8033x46387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Meghan Smith',
    'Timothy Roberts',
    'Tim Adams',
    'Adriana Hernandez',
    'Robert Gardner',
],
    'json': {
    'name': 'Donald Powell',
    'address': '30619 Williams Run\nNorth Adam, NH 43330',
},
    'key47000': 'value67767',
    'key44909': 'value75768',
    'key38889': 'value21976',
    'key32848': 'value38722',
    'key21837': 'value55138',
    'key95892': 'value64393',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Rhonda Strickland',
    'address': '44575 Joshua Plaza\nJenniferbury, NV 80167',
    'text': 'Operation design near. Project product at court agency.\nWonder environment property determine similar. Country short make result heavy.',
    'email': 'janejohnson@example.com',
    'phone_number': '5529070947',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brooke Barker',
    'James Cabrera',
    'Sandra Little',
    'Derek Mata',
    'Nicholas Herrera',
    'Elizabeth Burke',
    'John Smith',
],
    'json': {
    'name': 'Raven Harris',
    'address': 'Unit 4941 Box 6500\nDPO AE 97050',
},
    'key59525': 'value31563',
    'key43263': 'value98796',
    'key8807': 'value66048',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Janice Graham',
    'address': '8660 Jessica Ford Apt. 756\nHuntton, MI 19542',
    'text': 'Especially senior you artist interesting foot.\nUnder opportunity laugh police film finally somebody. Hospital who economic five response.',
    'email': 'roberttran@example.org',
    'phone_number': '237.968.8221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jean Avila DDS',
    'Melissa Meyers',
    'Russell Young',
    'Linda Hill',
    'Amanda Williams',
    'Nathan Cole',
    'Leslie Johnson',
    'Cathy Roach',
    'Gina Rose',
],
    'json': {
    'name': 'Joshua Carlson',
    'address': '589 Howard Coves\nMargaretstad, WA 50225',
},
    'key28791': 'value25081',
    'key1303': 'value30723',
    'key32953': 'value17125',
    'key86857': 'value14046',
    'key47436': 'value75572',
    'key16622': 'value21427',
    'key48611': 'value79205',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Laura Turner',
    'address': '682 Moyer Divide\nAndreaside, WV 87098',
    'text': 'Box may lawyer particular production Democrat. International note the.\nWish five support program generation. Stock number live huge expert.',
    'email': 'ihernandez@example.org',
    'phone_number': '(358)626-6788x4727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Conway',
    'Carl Mahoney',
    'Rebecca Hodge',
    'Mary Taylor',
    'James Bell',
    'Natasha Beck',
    'Timothy Wade',
    'Vanessa Beck',
    'Kristie Perez',
],
    'json': {
    'name': 'Michael Miller',
    'address': '230 Myers Garden\nNew Christopherview, IN 20237',
},
    'key2345': 'value32324',
    'key35520': 'value11722',
    'key57521': 'value60084',
    'key92066': 'value88842',
    'key34554': 'value51201',
    'key90536': 'value24286',
    'key78491': 'value55798',
    'key13': 'value15628',
    'key50855': 'value54424',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Robert Velez Jr.',
    'address': '9406 Jones Cove Apt. 094\nMeganmouth, VT 86496',
    'text': 'Quality population discover middle participant total middle herself. Almost woman perhaps almost who. Former go rather sound more discuss.',
    'email': 'donald08@example.net',
    'phone_number': '261.802.6191x9939',
    'array_int_dynamic': [
    66305,
],
    'array_varchar_dynamic': [
    'Courtney Wilson',
    'Frank Allen',
    'Kyle Faulkner',
    'Debbie Cruz',
    'Gabriella Mueller',
    'Courtney Thompson',
    'Ms. Andrea Thomas',
    'Timothy Robertson',
],
    'json': {
    'name': 'Thomas Andrews',
    'address': '65359 Scott Forks Suite 413\nWest Gary, CT 57589',
},
    'key7897': 'value67658',
    'key20635': 'value53814',
    'key78018': 'value20623',
    'key73276': 'value98915',
    'key98506': 'value96593',
    'key51068': 'value72276',
    'key37226': 'value19372',
    'key77940': 'value50636',
    'key5457': 'value26315',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Susan Griffin',
    'address': '425 Owens Isle\nSouth David, AL 62652',
    'text': 'Site challenge campaign apply put material interesting. Tv hour what word.',
    'email': 'rhondamoreno@example.org',
    'phone_number': '001-852-334-9831x37261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Payne',
    'Andrea Hill',
    'Kimberly Wood',
    'Mrs. Jennifer Johnston',
    'Erica Smith',
],
    'json': {
    'name': 'Michael Turner',
    'address': '878 Peterson Station\nTinaside, TX 56521',
},
    'key8729': 'value59232',
    'key60841': 'value90122',
    'key1058': 'value95613',
    'key52614': 'value60533',
    'key97893': 'value10946',
    'key99669': 'value63748',
    'key70537': 'value88683',
    'key76964': 'value91487',
    'key17709': 'value24225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Laura Barr',
    'address': '783 Kayla Cove\nCoxshire, NH 49641',
    'text': 'Around say culture interview painting look.\nDegree range blue resource employee turn. Dream wind anyone whole trial. Everybody business save.',
    'email': 'qtaylor@example.net',
    'phone_number': '794.592.9904x4625',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Cole',
    'Scott Baker',
    'Melinda Jones',
    'Clifford Miller',
    'Yesenia Hall',
    'Raymond Moreno',
    'Michael Phillips MD',
],
    'json': {
    'name': 'Brian Brown',
    'address': '03383 Watson Plaza\nPaynechester, WA 50920',
},
    'key21837': 'value65292',
    'key29841': 'value38738',
    'key84498': 'value76301',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'David George',
    'address': '150 Bruce Ford\nNew Andrewview, ME 75643',
    'text': 'Develop agent conference not. Television note consumer I difference partner because worker. Light above hand it man.',
    'email': 'melissaavila@example.com',
    'phone_number': '933.883.0958',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mariah Melendez',
    'Matthew Russell',
    'Tammy Stevenson',
    'Jasmine Garcia',
    'Jose Greer',
    'Carolyn Ortiz',
    'Shannon Garrett',
],
    'json': {
    'name': 'Timothy James',
    'address': '76271 Aguilar Well\nLake Claudia, VI 72561',
},
    'key27032': 'value71550',
    'key23409': 'value7500',
    'key31268': 'value85011',
    'key33846': 'value24120',
    'key36552': 'value50702',
    'key53766': 'value64134',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Justin Miller',
    'address': '425 Thomas Rest Suite 112\nNew Kevin, MD 22875',
    'text': 'Policy where data central. Hot new choice college investment their.\nCatch house once government. Economic whose several until. None poor improve only southern mother.',
    'email': 'edwardgarcia@example.org',
    'phone_number': '+1-734-572-0317',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stacy Cole',
    'Joseph Harris',
],
    'json': {
    'name': 'Stephen Peterson',
    'address': '1115 Kelly Islands Apt. 835\nPort Kimhaven, WI 78687',
},
    'key63': 'value49234',
    'key65428': 'value82258',
    'key48597': 'value65624',
    'key85917': 'value3375',
    'key3121': 'value63496',
    'key26780': 'value28779',
    'key73137': 'value76709',
    'key50233': 'value36311',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Mariah Moody',
    'address': 'Unit 0777 Box 3959\nDPO AE 58302',
    'text': 'Build fine reach night career economy use. Even cover continue treat stop. Personal large car add beautiful activity put.',
    'email': 'carl11@example.org',
    'phone_number': '(562)485-3511x9896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'William Evans',
    'Christopher Smith',
    'Jeremiah Navarro',
    'Deborah Holmes',
    'Katherine Ross',
    'Madeline Martinez',
    'Kathy Hill',
],
    'json': {
    'name': 'Stacy Walsh',
    'address': '94807 Rachel Court\nRodriguezhaven, GA 43150',
},
    'key78762': 'value88466',
    'key2153': 'value36241',
    'key11298': 'value51880',
    'key75267': 'value74012',
    'key97232': 'value10867',
    'key41195': 'value47747',
    'key58959': 'value41913',
    'key45454': 'value63854',
    'key28474': 'value65668',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Brenda Clark',
    'address': '18499 David Radial Suite 725\nJonesfurt, AK 46897',
    'text': 'Station power draw sure sell short. Weight animal involve.\nTable identify others movement same. Best anything baby.',
    'email': 'matthewsmall@example.com',
    'phone_number': '+1-245-781-5045x279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Angela Tate',
    'Cory Wagner',
],
    'json': {
    'name': 'Linda Stewart',
    'address': '4651 Cassie Turnpike\nNorth Jeffrey, DC 60470',
},
    'key59056': 'value98033',
    'key89802': 'value30183',
    'key97551': 'value98793',
    'key67860': 'value89141',
    'key68241': 'value74267',
    'key39921': 'value63268',
    'key33263': 'value74969',
    'key96098': 'value38894',
    'key20838': 'value84165',
    'key12577': 'value44544',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Christopher Davidson',
    'address': '97683 Barbara Street Suite 175\nLake Robertfurt, VT 55728',
    'text': 'About less summer rich realize. Court very factor later reduce staff. Write win peace.\nCapital environmental government development. Realize opportunity concern recognize whatever not.',
    'email': 'shannonwilliams@example.com',
    'phone_number': '001-405-723-9649x835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Hunt',
    'Brandon Byrd',
    'Joseph Long',
    'Collin Robinson',
    'Jack Ashley',
    'Jenna Fox',
    'Stacy Hall',
],
    'json': {
    'name': 'Ryan Galvan',
    'address': 'PSC 4862, Box 5067\nAPO AE 02315',
},
    'key19543': 'value52457',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'David Briggs',
    'address': '00224 Herman Cape\nLake Thomas, PW 58245',
    'text': 'Floor somebody admit raise however. Member work free ball stand home official.\nPut will see generation should. Voice though ball sport page its. Science stuff air water capital.',
    'email': 'rsmith@example.com',
    'phone_number': '559.320.9958x63084',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mr. William Rogers PhD',
    'Justin Bowman',
    'Jeffrey Farley',
    'Autumn Dawson',
    'James Vaughan',
    'Jeffery Cook',
    'Charles Scott',
],
    'json': {
    'name': 'William Mann',
    'address': '82198 Colleen Glen Apt. 696\nButlerhaven, FM 47018',
},
    'key56862': 'value83075',
    'key62677': 'value18517',
    'key2427': 'value87242',
    'key90025': 'value98880',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Mary Hardy',
    'address': '171 Cowan Stream\nWest Rachel, VT 52981',
    'text': 'Something friend down and anyone wide. Environmental performance again. School seek consider few writer.\nEver choice above real.',
    'email': 'priceann@example.com',
    'phone_number': '(716)508-6085',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Darryl Anderson',
    'Jonathon Alvarado',
    'Antonio Phillips',
    'Tony Middleton',
    'Whitney Sanchez',
    'Lauren Franco',
    'Hannah Lambert',
    'Howard Smith',
    'Brian Khan MD',
    'Blake Burnett V',
],
    'json': {
    'name': 'John Munoz',
    'address': '362 Sara Circle Suite 500\nJoshuafort, MN 43073',
},
    'key33473': 'value28295',
    'key13067': 'value71986',
    'key47132': 'value52345',
    'key50939': 'value5898',
    'key38053': 'value27472',
    'key43163': 'value23474',
    'key53887': 'value84087',
    'key17483': 'value54394',
    'key53775': 'value25838',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Michael Austin',
    'address': '07030 Smith Course\nWest Angelland, IN 94697',
    'text': 'Upon health north moment TV brother region hair. Accept feel individual stop watch well sit. A national movement.\nLawyer many him state also region writer. If many total traditional already short.',
    'email': 'evan36@example.net',
    'phone_number': '860.402.9125',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Roman',
    'Robert Chase',
    'Timothy Roberts',
    'Denise Morris',
    'Melissa Page',
    'Rhonda Smith',
    'Andrew Crosby',
],
    'json': {
    'name': 'Michael Morris',
    'address': '86926 Jason Station Apt. 717\nWest Brian, MN 60072',
},
    'key94162': 'value27320',
    'key46391': 'value50189',
    'key58222': 'value77870',
    'key1032': 'value69248',
    'key79060': 'value85998',
    'key29742': 'value58150',
    'key96675': 'value75612',
    'key14642': 'value2027',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Calvin Bolton',
    'address': '17077 Ross Pine\nRichardberg, ND 86215',
    'text': 'Network attention development address material instead. Score message today while structure account. Pay form his accept many. After your quickly.',
    'email': 'jerry26@example.org',
    'phone_number': '(792)841-0949x13196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Murray',
    'Caroline Brooks',
    'William Jones',
    'Scott Parker',
    'Colton Anderson',
    'Bruce Smith',
    'Jennifer Campbell',
],
    'json': {
    'name': 'Erica Dean',
    'address': '662 Hartman Court Apt. 726\nPort Timothy, NE 26719',
},
    'key64010': 'value73831',
    'key78044': 'value99124',
    'key29085': 'value42053',
    'key80771': 'value28755',
    'key48874': 'value44677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'John Thomas',
    'address': '3133 William Meadows Suite 601\nNew Jon, WI 12710',
    'text': 'Mrs right actually goal. Including indicate campaign clear the sell suggest.\nChoice think guy education. Stop order know. Argue middle skin simply teach.',
    'email': 'wcook@example.org',
    'phone_number': '+1-243-789-3227x8209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Baker',
],
    'json': {
    'name': 'Elizabeth Shannon',
    'address': '454 Smith Orchard\nDanielleton, AR 13018',
},
    'key53337': 'value92868',
    'key86872': 'value7513',
    'key89078': 'value59516',
    'key51423': 'value52715',
    'key57850': 'value48482',
    'key74722': 'value25402',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Amanda Lewis',
    'address': '511 Lewis Rapids\nGonzalestown, AL 19554',
    'text': 'This under ten season. Understand like employee mind response. Score prove value minute do age manager.\nMaintain west similar staff development just. Long plant discuss.',
    'email': 'michael06@example.net',
    'phone_number': '(468)934-7362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Kaiser',
    'Jessica Martin',
    'Sylvia Kent',
    'Jeremy Richards',
    'Daniel Lee',
],
    'json': {
    'name': 'Rachel Hill',
    'address': '2821 Cox Keys Suite 586\nGregoryberg, WV 79430',
},
    'key97652': 'value76154',
    'key29073': 'value78691',
    'key42016': 'value81103',
    'key61291': 'value17965',
    'key16954': 'value59817',
    'key37129': 'value64334',
    'key64186': 'value13367',
    'key61344': 'value77930',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Caitlin Thompson',
    'address': '6960 Lee Gateway\nWest Garrett, PA 11728',
    'text': 'Sea near surface someone accept. None sure nearly Mrs. Newspaper policy remain necessary five PM.\nSpace while billion big candidate cost year fine. Size head always stage until despite education.',
    'email': 'marcdavis@example.org',
    'phone_number': '508-838-5732',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Drew Morris',
    'Laura Taylor',
    'Julie Schmitt',
    'David Reid',
    'Gene Grant',
    'Patricia Arellano',
],
    'json': {
    'name': 'William Joyce',
    'address': '0413 Perez Skyway\nTorresberg, KY 64088',
},
    'key82511': 'value94651',
    'key3930': 'value89515',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Timothy Horn',
    'address': '9985 John River Suite 345\nGilestown, TN 56983',
    'text': 'Station score American affect human. Environmental right attack arm west majority. Himself close report hard. Up including child majority note Republican.',
    'email': 'shaunwilliams@example.com',
    'phone_number': '(818)419-8104x8677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Miles',
    'Leonard Jones',
    'Lisa Oconnor',
    'Rose Clark',
    'Kerri Medina',
    'Adrian Mann',
    'Cynthia Lynn',
],
    'json': {
    'name': 'Diane Robles',
    'address': '2963 Brenda Forge\nEast Alison, NE 30112',
},
    'key42390': 'value10226',
    'key95388': 'value11000',
    'key93546': 'value80512',
    'key46132': 'value63744',
    'key10869': 'value14340',
    'key27294': 'value64485',
    'key80382': 'value73113',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Ernest Burton',
    'address': '4742 Scott Estates\nNorth Williamborough, MN 59240',
    'text': 'Soldier process agree finally training provide summer. Person boy baby girl.\nDinner image administration church. Decision attorney they laugh fact require ball.',
    'email': 'toddjames@example.net',
    'phone_number': '001-323-740-0025',
    'array_int_dynamic': [
    74017,
],
    'array_varchar_dynamic': [
    'Angel Hernandez',
    'Robert Hughes',
    'Tommy Benitez',
    'Robert Williams',
    'Alyssa Diaz',
    'Joseph Mendez',
    'Nicole Griffith',
    'Kimberly Brown',
],
    'json': {
    'name': 'Jessica Garza',
    'address': '0338 Lee Trace Apt. 617\nBryanmouth, NY 56624',
},
    'key46572': 'value50016',
    'key30860': 'value67373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Ashley Dodson',
    'address': '31618 Mark Crest Suite 372\nLake Mark, AS 08723',
    'text': 'Another American well top black. Because until five painting mind play place admit.\nGarden far game fear quickly during. East ground voice world.',
    'email': 'shellylevy@example.com',
    'phone_number': '(643)353-2781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jason Mitchell',
    'Emily Mann',
    'Teresa Irwin',
    'Mary Hill',
    'Joshua Hill',
    'Jamie Wilson',
    'Judith Ramsey',
    'Peter Garza',
    'Shane Shah',
    'Mrs. Sherry Sutton DDS',
],
    'json': {
    'name': 'David Thompson',
    'address': '605 Mitchell Estates\nEast Jeremyside, TN 91933',
},
    'key52866': 'value62016',
    'key81733': 'value23807',
    'key96406': 'value63512',
    'key29212': 'value3344',
    'key81972': 'value71945',
    'key67873': 'value58059',
    'key99483': 'value4558',
    'key48212': 'value49751',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Alexander Brown',
    'address': 'USNS Smith\nFPO AA 81470',
    'text': 'Huge value success age write drive. Finally all sort shake view.\nWhile personal along shoulder. Know around physical draw truth.',
    'email': 'youngbrianna@example.net',
    'phone_number': '4534875928',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Graves',
],
    'json': {
    'name': 'Billy Sexton',
    'address': '5204 Brown Springs\nMatthewfort, CO 82655',
},
    'key47804': 'value50246',
    'key21361': 'value93527',
    'key34959': 'value72310',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'James Smith',
    'address': '323 Diane Pass Apt. 653\nMatthewhaven, NJ 49212',
    'text': 'Hope control happy require difficult include. Pass every huge should. Seem south book animal future shake dinner. New why walk him simply skill.',
    'email': 'chadware@example.net',
    'phone_number': '(685)704-8824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Victor Sanchez',
    'Melissa Booth',
    'Tammy Simmons',
    'Lauren Miller',
    'Ashley Simmons',
    'Robert Manning',
],
    'json': {
    'name': 'Mackenzie Rodriguez',
    'address': '26814 Robert Lane Suite 386\nBrianview, NM 14519',
},
    'key79161': 'value84161',
    'key21600': 'value16171',
    'key35034': 'value75723',
    'key80345': 'value75473',
    'key40341': 'value91106',
    'key54021': 'value7876',
    'key17338': 'value76052',
    'key61226': 'value35070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'David Lambert',
    'address': '7274 Hoffman Light\nSouth Amanda, IN 84532',
    'text': 'Down six human hotel. Imagine opportunity likely state most start. Home each else challenge. Idea shoulder soon.',
    'email': 'russellsimpson@example.org',
    'phone_number': '468-557-1346x3296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Walton',
    'Christopher Peterson',
],
    'json': {
    'name': 'Craig Clarke',
    'address': '667 Nathan Rapids\nEast James, ND 40955',
},
    'key50383': 'value6684',
    'key42462': 'value87459',
    'key18971': 'value8723',
    'key83092': 'value25753',
    'key36906': 'value58935',
    'key16423': 'value84702',
    'key18867': 'value5133',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Nancy Wall',
    'address': 'USCGC Pace\nFPO AE 57158',
    'text': 'Box safe ready near. Task skin since. Process daughter actually direction organization expert arrive.',
    'email': 'martinhannah@example.org',
    'phone_number': '466.273.4405x4567',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Victor Smith',
],
    'json': {
    'name': 'Michael Young',
    'address': '017 Kelly Course\nBrianberg, IN 65118',
},
    'key74207': 'value95890',
    'key13369': 'value39617',
    'key95042': 'value49821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Susan Roberson',
    'address': '49661 Diana Cape\nWaltonchester, WA 27857',
    'text': 'Wait your suggest design Republican. Quite check consumer begin chair.',
    'email': 'sonya80@example.net',
    'phone_number': '(415)489-8178x748',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Martin Taylor',
    'Jimmy Payne',
],
    'json': {
    'name': 'Rebecca Thomas',
    'address': 'PSC 7547, Box 6158\nAPO AE 86248',
},
    'key22525': 'value88707',
    'key32380': 'value68724',
    'key71083': 'value92941',
    'key53733': 'value20392',
    'key39591': 'value74564',
    'key29516': 'value19374',
    'key47169': 'value39212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Samuel Gutierrez',
    'address': '6843 Wheeler Shoals Apt. 998\nSouth Robertport, MN 82850',
    'text': 'Last relationship market country. He it bag create lay statement book wait. Teach notice authority hundred purpose.',
    'email': 'shawn43@example.org',
    'phone_number': '561-908-9370x599',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Rodriguez',
    'Elizabeth Terry',
    'Michael Nixon',
    'Kathleen Baldwin',
    'Cassidy Love',
],
    'json': {
    'name': 'Joseph Sexton',
    'address': '40227 David Rapid\nNorth Thomas, CO 11331',
},
    'key686': 'value83092',
    'key49815': 'value33876',
    'key71879': 'value78515',
    'key21170': 'value57348',
    'key20493': 'value92691',
    'key71127': 'value17772',
    'key26438': 'value28760',
    'key45825': 'value51183',
    'key36475': 'value78106',
    'key46459': 'value99285',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Gail Flynn',
    'address': '9404 Vargas Meadow Suite 449\nWalkerchester, GA 54441',
    'text': 'Much campaign level guy. Individual minute partner side.\nLand eat seat work want know manage. Box third Republican cover friend smile.',
    'email': 'cooperdonna@example.com',
    'phone_number': '5146471782',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Cook',
    'Donna Novak',
    'Nicole Lopez',
    'Jeffrey Porter',
    'Dr. Christine Wilson',
    'Kimberly Lambert',
    'Taylor Page',
    'Diane Miller',
],
    'json': {
    'name': 'James Reynolds',
    'address': '0563 Kennedy Harbor Apt. 322\nNorth John, AL 91463',
},
    'key7043': 'value36271',
    'key9204': 'value92644',
    'key41219': 'value56260',
    'key24918': 'value74318',
    'key23783': 'value23373',
    'key3202': 'value38707',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jodi Guzman',
    'address': '201 Elizabeth Ridge\nShannonchester, AK 33163',
    'text': 'North total best join law source dog. North couple dog feel.\nListen ever little even task dinner.',
    'email': 'miranda82@example.org',
    'phone_number': '+1-409-424-4295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gina Thomas',
    'Theresa Kelly',
],
    'json': {
    'name': 'Regina Jackson',
    'address': '655 Raymond Ports\nSanderschester, UT 47161',
},
    'key32903': 'value41414',
    'key79733': 'value71850',
    'key2186': 'value47194',
    'key74556': 'value96987',
    'key80351': 'value26614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Joseph Fry',
    'address': '3929 Bethany Mountain Apt. 183\nGregorymouth, ME 94819',
    'text': 'Suffer use discussion pretty community. Subject film service far idea. Plan author apply key answer. Business want actually finish.',
    'email': 'anne71@example.net',
    'phone_number': '784-212-6648',
    'array_int_dynamic': [
    66517,
],
    'array_varchar_dynamic': [
    'Edward Mccarty',
    'Kelly Price',
    'Crystal Moran',
    'Alexis Boone',
    'Dawn Martinez',
    'Grant Foster',
    'James Wilcox',
    'Theresa Mcconnell',
],
    'json': {
    'name': 'Nicole James',
    'address': '5117 Ruiz Island\nGuerraside, SD 81071',
},
    'key71909': 'value75686',
    'key94725': 'value62788',
    'key91500': 'value7482',
    'key18819': 'value92709',
    'key62425': 'value9631',
    'key24506': 'value33227',
    'key2495': 'value141',
    'key51944': 'value56559',
    'key71949': 'value16344',
    'key20498': 'value99030',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Brenda Berg',
    'address': '359 Anderson Inlet\nWest Erikafort, ME 63031',
    'text': 'Research whether rate daughter skill turn. Place source can happen note compare condition. Fear upon food.\nSingle model true necessary open today hotel.',
    'email': 'ashleywilliamson@example.net',
    'phone_number': '795.737.2869x441',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brian Jones',
    'Megan Holt',
    'Mary Rogers',
    'Brenda Oliver',
    'Dana Willis',
    'Mr. Carl Carlson MD',
    'Shelly Lewis',
],
    'json': {
    'name': 'Kimberly Bradley',
    'address': '383 Kari Wells\nJeanneland, AS 51702',
},
    'key75301': 'value18951',
    'key9592': 'value90675',
    'key75485': 'value64410',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Robert Knox',
    'address': 'PSC 4314, Box 5396\nAPO AP 19105',
    'text': 'Investment control course skill management find current school. While she spend return whose over reality. Into might security risk season suggest.',
    'email': 'hgardner@example.net',
    'phone_number': '312.201.9487x42186',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Leonard Coleman',
    'Seth Evans',
    'Michael Conley',
    'John Johnson',
],
    'json': {
    'name': 'William Gray',
    'address': '51678 Johnson Rapid\nLauraville, MS 83071',
},
    'key42879': 'value66692',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Shannon Swanson',
    'address': '2153 Reed Parks\nMedinashire, GA 99090',
    'text': 'Hard discussion performance speech so someone thing. Enjoy head real country. Rather week fund note.\nAvoid feel must. Make best set.',
    'email': 'bearderic@example.com',
    'phone_number': '(825)661-4854',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Cline',
    'Anthony Baker',
    'Gary Turner',
    'Brandon Cunningham',
    'John Holmes MD',
],
    'json': {
    'name': 'Kristin Rice',
    'address': '0683 Kelly Greens Apt. 993\nRebeccaland, NJ 49721',
},
    'key92546': 'value78168',
    'key62072': 'value44980',
    'key44792': 'value39499',
    'key4871': 'value11121',
    'key64475': 'value16692',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Summer Henry',
    'address': '13281 Nicole Knolls\nWaltersland, PR 05536',
    'text': 'Behind continue him four operation fast. Across record network hospital travel final something our. Worry main factor represent.\nFocus happen right development during. Wind protect read order.',
    'email': 'ericmarshall@example.org',
    'phone_number': '714.652.5166x988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Megan Miller',
    'Chelsea Hardy',
    'Jennifer Bell',
    'Sarah Bowman',
    'Jose Horne',
    'Jeffrey Brown',
],
    'json': {
    'name': 'Stephen Brown',
    'address': '623 Zachary Glens Suite 093\nHansonfurt, VI 66726',
},
    'key70379': 'value77048',
    'key513': 'value42986',
    'key51677': 'value89073',
    'key70751': 'value3641',
    'key27675': 'value52859',
    'key10761': 'value3163',
    'key34164': 'value636',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Charles Peterson',
    'address': '04374 Connor Viaduct\nBradborough, FL 42239',
    'text': 'Trial memory condition third claim well. Environmental tonight officer industry bring. Huge report just whatever good number what.',
    'email': 'robert45@example.net',
    'phone_number': '001-836-693-9349',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Williams',
    'Lauren Cross',
    'Brittney Holmes',
    'James Morris',
],
    'json': {
    'name': 'Ashley Matthews',
    'address': '50663 Tara Island\nAlisonfort, MP 06111',
},
    'key48043': 'value41975',
    'key47350': 'value14446',
    'key19709': 'value25672',
    'key77452': 'value83914',
    'key65922': 'value54669',
    'key10503': 'value80334',
    'key12033': 'value76720',
    'key26905': 'value13884',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Sarah Robinson',
    'address': '687 Steven Viaduct\nTimothyhaven, MA 58850',
    'text': 'Their truth me western. Indicate join better mouth certainly control.\nArtist side action sort. Wind indeed produce fall number debate.\nMove series say.',
    'email': 'catherinehill@example.com',
    'phone_number': '216-374-8474x90569',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cassie Young',
    'Chelsea Cherry',
    'Joseph Matthews',
    'Steven Austin',
    'David Castro',
    'Troy Lee',
    'Andrew Padilla',
    'Jim Alexander',
    'Justin Ross',
    'Ms. Jennifer Nielsen MD',
],
    'json': {
    'name': 'Sara Schmidt',
    'address': '397 Gilbert Wells\nNew Dwaynefort, ME 85327',
},
    'key46980': 'value4259',
    'key32414': 'value8831',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Paige Garrison',
    'address': 'Unit 8792 Box 4525\nDPO AE 90676',
    'text': 'Bar any share finish parent year commercial. Street process style goal before.\nListen Republican doctor. Small teacher none station old. Present task speak become.\nWho discussion station series foot.',
    'email': 'leealyssa@example.net',
    'phone_number': '380.900.4303x10902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Nguyen',
    'Charles Jackson',
    'Kelly Gill',
    'Cody West',
    'Sarah Thomas',
],
    'json': {
    'name': 'Adam Frank',
    'address': 'USNV Carter\nFPO AP 07642',
},
    'key98722': 'value14977',
    'key22681': 'value85109',
    'key59236': 'value17987',
    'key63803': 'value48638',
    'key45011': 'value47452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'David Patterson',
    'address': '588 Williams Islands\nJessicatown, CO 52912',
    'text': 'Past issue why source. Report war result mouth. Song in it radio.\nStar charge data serious himself everything most. Commercial side produce policy.',
    'email': 'jwatson@example.org',
    'phone_number': '001-940-927-0752x800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amy Evans',
    'Donna Warner',
    'David Webb',
    'Donald Blackburn',
],
    'json': {
    'name': 'Grant Hill',
    'address': '7090 Martin Passage Apt. 096\nLake Josephshire, VA 31103',
},
    'key56787': 'value45058',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Stephen Guzman',
    'address': '24769 Stephanie Ville Suite 050\nRobertsshire, CT 70084',
    'text': 'Total top meet. Few method piece. Fine least sort pull thought law.\nRepresent child front.\nNever power official opportunity. Stand as page price friend.',
    'email': 'kellerscott@example.net',
    'phone_number': '(619)586-1205x209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Mcconnell',
    'Thomas Hill Jr.',
    'Robert White',
    'Tina Hall',
    'Tammy Simmons',
    'Leah Thomas',
    'Kevin Maxwell',
],
    'json': {
    'name': 'Thomas Johnson',
    'address': '40969 Ronnie Harbors\nSilvaton, AZ 17355',
},
    'key21134': 'value3662',
    'key80663': 'value64817',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Patricia Lester',
    'address': 'Unit 0092 Box 4111\nDPO AP 81998',
    'text': 'Bill use once hope five. Blue worry really tell case foreign.\nEntire phone it team. Within still nation that son.',
    'email': 'fieldscourtney@example.org',
    'phone_number': '999-568-4879',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Rodriguez',
    'Jason Shannon',
    'Jimmy Bautista',
    'Cindy Odom',
    'Erica Dillon',
    'James Lewis',
    'Chris Adams',
    'Richard Thomas',
    'Keith Swanson',
    'Kathryn Turner',
],
    'json': {
    'name': 'Sabrina Rodriguez',
    'address': 'PSC 8449, Box 3074\nAPO AA 42481',
},
    'key65529': 'value89810',
    'key54563': 'value17171',
    'key5515': 'value74584',
    'key3974': 'value38025',
    'key45555': 'value79433',
    'key74400': 'value35478',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Nicholas Arias',
    'address': '1968 Keller Pines Suite 268\nWest Jeffrey, GA 20597',
    'text': 'Begin party those surface best bad. Price available office back left.\nSupport bag foreign. Leave and open indeed worker.',
    'email': 'sanchezdawn@example.net',
    'phone_number': '(625)717-6581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Lee',
    'Joseph Sellers',
    'Heather Gonzalez',
],
    'json': {
    'name': 'Jeffrey Wilson',
    'address': 'PSC 2175, Box 1051\nAPO AA 37510',
},
    'key90109': 'value17622',
    'key82678': 'value34331',
    'key78623': 'value80755',
    'key42116': 'value6597',
    'key71160': 'value16172',
    'key60110': 'value78871',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Rita Frederick',
    'address': '5338 Lisa Mount Suite 179\nPort Matthewmouth, SD 43327',
    'text': 'Size lose discussion why theory. Sound two great with environment partner.',
    'email': 'robertnelson@example.org',
    'phone_number': '660.719.0813x613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Krueger',
    'Regina Clark',
    'Mary Lewis',
],
    'json': {
    'name': 'Jeffrey Patterson',
    'address': '741 Burke Parks Suite 495\nJulieport, NM 52050',
},
    'key62474': 'value54804',
    'key10339': 'value85341',
    'key81912': 'value32232',
    'key84942': 'value83027',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Shannon Pope',
    'address': '19059 Cassandra Road\nPort Jenniferville, WV 63078',
    'text': 'Prevent officer about arm.\nCut must realize. Yes none treat far possible couple money.\nOwn within still thousand establish owner. Republican really collection so own.',
    'email': 'tsparks@example.com',
    'phone_number': '906.426.3457x749',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Cook',
    'Jacqueline Smith',
    'Rebecca Hughes',
    'Luis Wallace',
],
    'json': {
    'name': 'Robert Shepherd',
    'address': '695 Howard Fords Apt. 635\nSimmonsview, NM 02746',
},
    'key90385': 'value27026',
    'key79807': 'value13556',
    'key79138': 'value74386',
    'key33478': 'value28460',
    'key31511': 'value34053',
    'key91309': 'value33354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Stephanie Schroeder',
    'address': '2685 Eric Circle\nSmithtown, MS 45673',
    'text': 'Early only quickly none act. Local wind mother explain such region charge smile. Factor father write nation.\nMonth know goal ask people. Option child energy but everything.',
    'email': 'ihensley@example.com',
    'phone_number': '425.477.6753',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Hernandez',
    'Carrie Cook',
    'Zachary Tucker',
    'William Gutierrez',
    'Jennifer Rios',
    'Elizabeth King',
    'Anna Chen',
    'Cynthia Ramirez',
    'Eileen Schneider',
    'Levi Thompson',
],
    'json': {
    'name': 'Stacy Edwards',
    'address': '986 Harris Meadow\nSouth Adamburgh, ID 85086',
},
    'key54502': 'value42927',
    'key89715': 'value82855',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Karen Cohen',
    'address': '41007 Moore Knolls Suite 381\nWillismouth, IA 61701',
    'text': 'Home organization pull. Theory enjoy old young give space.\nConsider suffer purpose kind party week. Member student bill around.',
    'email': 'carolynprice@example.org',
    'phone_number': '725.895.9389x3410',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Diana Ramirez',
    'Anthony Grant',
    'James Hawkins',
    'Chelsea Fowler',
    'Benjamin Coffey',
    'Frederick Brewer',
    'Holly Schultz',
    'Rachel Mitchell',
    'Pamela Long',
],
    'json': {
    'name': 'Lee Lynch',
    'address': '967 Dunn Village Apt. 878\nWademouth, IN 50555',
},
    'key31866': 'value14249',
    'key67102': 'value37636',
    'key57544': 'value89215',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Marie Brooks DDS',
    'address': '1403 Roberts Isle\nSouth Mark, OR 33984',
    'text': 'Free admit above safe. Score through street study. Likely late experience social.\nWhile investment far important lose old dark. No wait end because inside. Federal put meeting participant.',
    'email': 'hollandebony@example.com',
    'phone_number': '255.394.7092x387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mason Smith',
    'Shannon Jenkins',
    'Matthew Rivera',
    'Christine Blair',
    'William Ramsey',
    'Jennifer Howard',
    'Mr. Justin Jacobson',
    'Mary Murphy',
],
    'json': {
    'name': 'Pamela Cain',
    'address': '5507 Amanda Coves Apt. 417\nPort Thomasberg, NM 54884',
},
    'key47467': 'value41238',
    'key30803': 'value31466',
    'key13843': 'value45660',
    'key48862': 'value34590',
    'key1325': 'value1703',
    'key38393': 'value13123',
    'key16876': 'value12538',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Shane Glenn',
    'address': 'USCGC Crawford\nFPO AP 26636',
    'text': 'Girl few into hit position question. Down base as indicate improve. Former up air movie focus recently. Including positive role field sign standard.',
    'email': 'catherine37@example.org',
    'phone_number': '975.582.2644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Callahan',
    'Patrick Mccarty',
    'Patrick Moody',
    'Jacqueline Adams',
    'Joe Coleman',
    'Norma Bailey',
],
    'json': {
    'name': 'Dr. Benjamin Salas',
    'address': '567 Michelle Field\nEast Lisachester, ID 65298',
},
    'key99767': 'value32274',
    'key13747': 'value2382',
    'key42746': 'value62928',
    'key42406': 'value88874',
    'key40856': 'value13625',
    'key2664': 'value26703',
    'key24589': 'value62000',
    'key24945': 'value77686',
    'key12342': 'value85735',
    'key87683': 'value91717',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Matthew Harris',
    'address': '2262 Cohen Club\nEast Emily, NJ 54049',
    'text': 'Return public response young improve century east. Medical reduce tree these court senior.\nAssume entire follow. Six pull table audience. Amount item carry hotel probably poor.',
    'email': 'julie58@example.com',
    'phone_number': '311-525-0533x5166',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Richard Gonzales',
    'David White',
    'Blake Perez',
    'Russell Stark',
],
    'json': {
    'name': 'Tamara Rodriguez',
    'address': '7829 Sabrina Grove Apt. 116\nEast Jessica, ME 72185',
},
    'key45569': 'value48702',
    'key27204': 'value49324',
    'key97427': 'value84299',
    'key32841': 'value27212',
    'key28438': 'value65548',
    'key11613': 'value3422',
    'key14420': 'value71689',
    'key6708': 'value6564',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Tina Burke',
    'address': '456 Carter Creek Suite 904\nWendyburgh, DE 22174',
    'text': 'Community eat five alone reach not market. Produce page trial similar generation send.\nCharge reality almost political stock piece degree. Factor model say.',
    'email': 'phillipsjohn@example.org',
    'phone_number': '001-821-608-0505x5345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Misty May',
    'Kimberly Roberts',
    'Bruce Hahn',
    'Mary Buck',
    'Dennis Sexton',
    'Nancy Tran',
],
    'json': {
    'name': 'Victor Snyder',
    'address': '346 Brown Park\nHernandezside, UT 64136',
},
    'key81048': 'value95573',
    'key59302': 'value75750',
    'key97676': 'value67771',
    'key59216': 'value82169',
    'key40352': 'value61575',
    'key38065': 'value44825',
    'key62326': 'value64357',
    'key86699': 'value95245',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Matthew Chambers',
    'address': '504 Owen Courts\nHortonmouth, FL 52447',
    'text': 'Much system voice figure eat couple. Local day amount with feel.\nSure test special you future white. New thousand structure above detail huge president. Agent owner state free language accept.',
    'email': 'saundersbilly@example.com',
    'phone_number': '(826)238-9327x0091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Vickie Santana DDS',
    'Elizabeth Nguyen',
    'Ernest Charles',
    'Reginald Rodriguez',
    'Brian Robles',
    'Rebecca Clark',
    'Autumn West',
    'Rebecca Sutton',
    'Daniel Smith',
],
    'json': {
    'name': 'Sharon Reid',
    'address': '7149 Chelsea Inlet\nNorth Julie, OR 67404',
},
    'key92294': 'value49003',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Wesley Atkins',
    'address': 'Unit 1400 Box 2266\nDPO AE 51620',
    'text': 'Hotel campaign on relationship turn. Range prevent yard from. Environmental serve next ball class.\nPull create amount among this cup. The range guess green.',
    'email': 'rmay@example.net',
    'phone_number': '7147884193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'John Wise',
    'Peter Clark',
    'Joseph Johnson',
    'Mary Hughes',
    'Justin Evans',
    'Sean Black',
    'Nicholas Mcclure',
    'Christopher Hughes',
    'Kayla Bush',
    'Dawn Fischer',
],
    'json': {
    'name': 'Louis Berg',
    'address': 'PSC 6733, Box 3119\nAPO AE 66147',
},
    'key73814': 'value12173',
    'key91607': 'value56846',
    'key69911': 'value15173',
    'key47772': 'value76872',
    'key59510': 'value89203',
    'key37567': 'value93279',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Traci Wagner',
    'address': '133 Jones Squares Apt. 019\nSouth Johnport, WV 85672',
    'text': 'Up skill star indicate. Where collection matter eight that.\nDevelopment education available. Exist worry hold form doctor.',
    'email': 'kevinmcdaniel@example.org',
    'phone_number': '739-507-6649x005',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Carr',
    'Roger Scott',
    'Roger Larson',
    'Claire Whitehead',
    'Dana Allen',
    'Shelley Mitchell',
],
    'json': {
    'name': 'Brett Holmes',
    'address': '1310 Smith Cliff\nEast Rebekah, SC 26115',
},
    'key63423': 'value72573',
    'key68229': 'value50380',
    'key94242': 'value58088',
    'key73102': 'value59171',
    'key87217': 'value42876',
    'key73128': 'value23039',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Elaine Roman',
    'address': '218 Adam Courts\nNorth Mary, GU 32229',
    'text': 'Outside major among attention. Rise total certainly military result shake way. Beat six charge see Republican.\nCard whom friend simple occur fill. Do knowledge major organization as floor.',
    'email': 'colejeanette@example.com',
    'phone_number': '215-525-6128x277',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Emma Patterson',
    'Donna Mullen',
    'Chad Skinner',
],
    'json': {
    'name': 'Mary Lucas DDS',
    'address': '699 Hannah Hollow Suite 373\nSouth Sharon, AR 94709',
},
    'key24927': 'value58456',
    'key90549': 'value70039',
    'key42935': 'value59636',
    'key96252': 'value53780',
    'key7255': 'value21176',
    'key22162': 'value48971',
    'key53179': 'value22074',
    'key29930': 'value89121',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Lynn Hernandez',
    'address': 'Unit 4176 Box 1649\nDPO AP 70580',
    'text': 'Common foot method rich simply field population. Happy threat decide bad. Everything power eight onto would writer.',
    'email': 'heather93@example.org',
    'phone_number': '613.893.5838x569',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Moore',
    'Jasmine Ortega',
    'Helen Sanders',
    'Robert Cohen',
    'Lisa Bryant',
    'Hayley James',
    'Jonathan Robinson',
    'Vincent Coffey',
    'Ashley Spears',
],
    'json': {
    'name': 'Melissa Brown',
    'address': '1843 Martinez Crossroad\nSouth Theresa, AZ 04425',
},
    'key19206': 'value18744',
    'key41022': 'value62689',
    'key65204': 'value97858',
    'key7669': 'value40556',
    'key42949': 'value88401',
    'key20935': 'value2103',
    'key21169': 'value39011',
    'key47535': 'value53566',
    'key85036': 'value27701',
    'key65180': 'value63454',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Kristin Steele',
    'address': '39548 Buchanan River\nTurnerfurt, MT 10411',
    'text': 'Cultural back entire wish. International produce girl.',
    'email': 'laurenjordan@example.org',
    'phone_number': '(911)576-6962',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Castro',
    'Tracy Phillips',
    'Patricia Marshall',
    'Jacqueline Sanders',
],
    'json': {
    'name': 'Jamie Berger',
    'address': '2804 Isabel Rest Suite 952\nNew Michael, NY 75545',
},
    'key1453': 'value61758',
    'key85689': 'value42269',
    'key56475': 'value48863',
    'key2772': 'value94695',
    'key36281': 'value64642',
    'key18675': 'value63218',
    'key69006': 'value16627',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Shawn Smith',
    'address': '0558 Gray Station Suite 407\nRobinsonmouth, PA 02771',
    'text': 'Everybody change painting. Fill center partner table. Art hard else they for realize quickly.',
    'email': 'olsonandrew@example.org',
    'phone_number': '(363)789-8506',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Brown',
    'Maurice Cobb',
],
    'json': {
    'name': 'Michael Gould',
    'address': '17317 Edward Trafficway Apt. 899\nCassandrabury, WA 35133',
},
    'key76475': 'value74474',
    'key63757': 'value38489',
    'key60285': 'value29448',
    'key84378': 'value26795',
    'key73179': 'value30888',
    'key53343': 'value1426',
    'key59096': 'value39648',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Gregory Gomez',
    'address': '6182 Kent Summit\nCastromouth, ID 07319',
    'text': 'Cost central car stay price really media. Artist arrive message guess. Shoulder produce energy last left.',
    'email': 'andrea86@example.net',
    'phone_number': '+1-316-368-9207x28682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Wood',
    'Michael Howell',
    'Robert Smith',
    'Jonathan Bennett',
    'Marcus Jackson',
    'Kelsey Morales',
],
    'json': {
    'name': 'Shelley Ryan',
    'address': 'PSC 5716, Box 9175\nAPO AP 08303',
},
    'key65786': 'value6929',
    'key80160': 'value59356',
    'key61516': 'value87202',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Jacob Compton',
    'address': '57597 Brittney Groves\nSouth Davidland, OR 44677',
    'text': 'Yourself understand determine. Feeling town media up believe. Music strong stuff yeah.\nOwn crime standard sea treat town. Ability everybody pretty worry son why mention new. Feeling open notice wall.',
    'email': 'ocobb@example.com',
    'phone_number': '(450)680-6386x0866',
    'array_int_dynamic': [
    96352,
],
    'array_varchar_dynamic': [
    'Kenneth Moore',
    'Jesse Morris',
    'Richard Gray',
    'Stacie Haney',
    'Tammy Reyes',
],
    'json': {
    'name': 'Kimberly Mccarthy',
    'address': '760 Mora Corners Apt. 593\nNorth Janetberg, VA 81531',
},
    'key53545': 'value67286',
    'key4271': 'value40764',
    'key56686': 'value82448',
    'key47300': 'value66367',
    'key48824': 'value20354',
    'key22897': 'value77252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Andrew Johnston',
    'address': '459 Abigail Square\nRhondastad, VA 32527',
    'text': 'Interest main card among. Party case sign then who case myself sister. Lot ready should data give economic pick imagine.',
    'email': 'rossmeghan@example.org',
    'phone_number': '6077205424',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Julie Willis',
    'Joseph Cherry',
    'Travis Yates',
    'Sandra Johnson',
    'Joy Nguyen',
    'Kenneth Jimenez',
],
    'json': {
    'name': 'Brian Oneal',
    'address': '5192 Rhonda Lane\nCabreraville, NE 84751',
},
    'key85690': 'value42965',
    'key64861': 'value39087',
    'key58269': 'value84806',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jennifer Gilbert',
    'address': 'Unit 6193 Box 5110\nDPO AP 32041',
    'text': 'Dog radio mind chance prevent rest heavy share. Up option institution sea. Generation paper American well gas amount. Right strong leave from most memory time become.',
    'email': 'wglenn@example.org',
    'phone_number': '(698)465-2828x48010',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Simmons',
    'Mike Ball',
    'Daniel Mcmahon PhD',
    'Natalie Reed',
    'Richard Holt',
    'Michelle Knapp',
    'Mitchell Cox',
    'Jonathan Phelps',
    'Lisa Figueroa',
],
    'json': {
    'name': 'Richard Gomez',
    'address': 'Unit 7091 Box 1434\nDPO AA 54732',
},
    'key62466': 'value475',
    'key99895': 'value96759',
    'key157': 'value45283',
    'key37914': 'value15465',
    'key34613': 'value45921',
    'key33073': 'value75419',
    'key772': 'value26374',
    'key41344': 'value62788',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Erica Scott',
    'address': '93135 Martinez Roads\nPettystad, ME 87561',
    'text': 'On military old turn change sure. Experience blue I indicate. Watch success capital member writer church.\nStand for fear after. Serve audience news cold behavior. Type part could movie bag happy.',
    'email': 'toddclayton@example.org',
    'phone_number': '001-274-713-8596x84691',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Lopez',
    'Anita Graham',
    'Jessica Stewart',
    'Stephanie Frazier',
    'David Mendez',
    'Derrick Beard',
    'Jamie Torres',
    'Bradley Reynolds',
],
    'json': {
    'name': 'Daniel Graves',
    'address': '05386 Fernandez Union Apt. 866\nMarytown, OR 80079',
},
    'key84589': 'value21211',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Christine Williams',
    'address': '2358 Charles Isle\nWatsonberg, VA 29217',
    'text': 'Cup others adult ten ever. On would simply catch. Each at response successful sport body. Congress summer there task sound east.',
    'email': 'ithomas@example.com',
    'phone_number': '7904911525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Maureen Franklin',
],
    'json': {
    'name': 'Rick Johnson',
    'address': '52499 Jerry Point\nHahnberg, SD 83838',
},
    'key44543': 'value16596',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Bobby Mendez',
    'address': '13652 Marc Cape\nPort Jameston, MN 13977',
    'text': 'President cup trial military some. New how ask pretty heavy central buy. Husband design card seven us school pull.',
    'email': 'gnelson@example.com',
    'phone_number': '802-483-7371',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Ross',
    'Cheyenne Arnold',
    'Nicole Jones',
    'Steve Kelley',
    'Stephen Mcmillan',
    'Mrs. Jennifer Fisher',
    'Larry Rogers',
    'Julia Love',
    'Brandon Stokes',
],
    'json': {
    'name': 'Angela Barajas',
    'address': 'USNS Franklin\nFPO AP 36092',
},
    'key67133': 'value74872',
    'key442': 'value63037',
    'key8799': 'value91705',
    'key78517': 'value49983',
    'key88154': 'value39628',
    'key28843': 'value60094',
    'key71471': 'value65489',
    'key8886': 'value72122',
    'key41437': 'value50144',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Cathy Gordon',
    'address': '63443 Christopher Roads Suite 009\nSouth Timothy, TX 91214',
    'text': 'It if tax drive performance Mr step. Including wish actually spring bad along glass.\nShould require glass participant sport vote say. Reflect parent create only economic.',
    'email': 'jonesjoe@example.org',
    'phone_number': '001-323-647-5172',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Grant',
    'Larry Vargas',
    'Katelyn Duarte',
    'Dr. Joseph Henderson MD',
    'Christopher Frederick',
    'Laura Jones',
],
    'json': {
    'name': 'Aaron Valdez',
    'address': '238 Daniel Islands\nDanielton, ID 41573',
},
    'key65698': 'value88746',
    'key81603': 'value69203',
    'key21425': 'value68379',
    'key29498': 'value36991',
    'key85306': 'value12817',
    'key74574': 'value22037',
    'key97668': 'value89626',
    'key16832': 'value23248',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Sarah Warner',
    'address': '425 Martin Circles\nSouth Kim, KY 63797',
    'text': 'Recent fish husband within. Body behavior traditional staff moment loss consumer way. Light forward collection adult.',
    'email': 'steveburns@example.net',
    'phone_number': '7194451294',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Hernandez',
    'Brent Saunders',
    'Mark Johnson',
],
    'json': {
    'name': 'Jamie Mckay',
    'address': '936 Janice Plains Suite 925\nNorth Christophermouth, CT 40377',
},
    'key88': 'value32792',
    'key77160': 'value18564',
    'key95599': 'value63192',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Kristopher Adams PhD',
    'address': '41111 Jeffery Drives\nEast Derrickhaven, IN 87999',
    'text': 'Remember use receive without. Letter every door recent note.\nBook about whole be method.\nWest attention war. Yourself sing form measure country party stand animal.',
    'email': 'stuartamanda@example.com',
    'phone_number': '+1-309-760-5129x84276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Marsh',
    'Alice Stone',
    'Brett Donovan',
    'Pamela Hurley',
],
    'json': {
    'name': 'Justin Saunders',
    'address': '42322 Anderson Estate Suite 092\nPort Jamie, AK 56810',
},
    'key4750': 'value20723',
    'key10819': 'value77000',
    'key44914': 'value36982',
    'key72860': 'value70669',
    'key34760': 'value16653',
    'key88014': 'value672',
    'key44809': 'value15067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Brian Fowler',
    'address': 'PSC 4216, Box 7652\nAPO AP 47825',
    'text': 'Half door would participant month meet. Board east if ability.\nLike capital each view coach value. Happen prove nice think whatever admit.',
    'email': 'kelly10@example.net',
    'phone_number': '390.457.5842',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Poole',
    'Shannon Mitchell',
    'Kevin Robinson',
    'Tracy Grant',
    'Michael Joseph',
    'Christina Lewis',
    'David Olson',
    'Katelyn Moreno',
    'Tonya Richards',
    'John Garcia',
],
    'json': {
    'name': 'Frank Green',
    'address': '42181 Rodriguez Harbors\nEast Prestontown, NM 71280',
},
    'key88800': 'value84064',
    'key75279': 'value32490',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'David Glass',
    'address': 'USNV Sanchez\nFPO AA 87100',
    'text': 'Decade choice sense dog stock image. Work respond they bit. Go enjoy but include final number safe.',
    'email': 'fergusontaylor@example.com',
    'phone_number': '(667)891-2419x3765',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Mitchell',
    'Michael Rush',
    'Debra Dodson',
    'Brooke May',
    'Timothy Stevens II',
    'Kelly Rowland',
    'Betty Golden',
    'John Mitchell',
    'Erik Newton',
],
    'json': {
    'name': 'Timothy Pratt',
    'address': '4351 Campbell Cape\nPort James, ID 03352',
},
    'key28039': 'value95421',
    'key31984': 'value72476',
    'key19922': 'value51718',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Michelle Lopez',
    'address': '1178 Reed Plaza\nKellyborough, FL 52978',
    'text': 'Feeling partner pass many allow just. Gun collection nearly his they always draw. Likely week former artist skill truth.',
    'email': 'thendrix@example.org',
    'phone_number': '+1-674-524-1977x949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cathy Stewart',
    'Brett Lambert',
    'Larry Smith',
    'Martha Johnson',
    'Jane Smith',
    'Scott White',
    'Brian Gilbert',
],
    'json': {
    'name': 'Jamie Chapman',
    'address': '2810 Kathy Isle\nWest Cynthiaberg, NE 67683',
},
    'key34067': 'value61193',
    'key35434': 'value1048',
    'key54767': 'value29325',
    'key78483': 'value30511',
    'key68539': 'value37831',
    'key75964': 'value87869',
    'key98420': 'value80712',
    'key47661': 'value87279',
    'key72654': 'value50449',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'April Jacobs',
    'address': '3496 Hughes Place\nEast Christopher, KS 85447',
    'text': 'Sister production attack series Mrs day clear. Prove help environment example. Wonder study Mrs memory somebody despite top.',
    'email': 'mmiller@example.com',
    'phone_number': '+1-737-313-0745x598',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Martinez',
    'Andrew Barnett',
    'Mark Walker',
    'David Thompson',
],
    'json': {
    'name': 'Ricky Welch',
    'address': '442 Heather Village Suite 487\nNorth Megan, VA 94817',
},
    'key75666': 'value93886',
    'key49341': 'value6417',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Stephanie Kelly',
    'address': '13913 Katherine Fort Suite 279\nEast Jacqueline, KY 88429',
    'text': 'Manage require development. Common late Mrs analysis remain citizen. Analysis short cup skin arm.\nLarge economic history employee him think authority. Rest bag force plant.',
    'email': 'lorihammond@example.com',
    'phone_number': '6902345739',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Hayes',
    'Jill Gilbert',
],
    'json': {
    'name': 'Richard Martinez',
    'address': '6016 Wright Lights\nChristopherchester, LA 52561',
},
    'key18968': 'value69865',
    'key84762': 'value64795',
    'key26594': 'value6352',
    'key7004': 'value71567',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Rachel Hancock',
    'address': '9720 Zachary Field\nArnoldfort, HI 75073',
    'text': 'Recently rather know. Director director lead respond Republican third.\nIndeed those case any ground training. Reflect explain some star hope agency.',
    'email': 'boydvictoria@example.org',
    'phone_number': '634-326-4911',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Williams',
    'Rachel Butler',
],
    'json': {
    'name': 'Hailey Salazar',
    'address': 'PSC 9703, Box 9655\nAPO AA 16537',
},
    'key92967': 'value39047',
    'key30933': 'value23383',
    'key54619': 'value12901',
    'key96808': 'value3357',
    'key78962': 'value36222',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Kathleen Boyle',
    'address': '65956 Rodriguez Squares\nDouglasstad, WA 57230',
    'text': 'Difficult administration reason computer. Away manager commercial low return right month. Store pay avoid partner worry stuff lay.',
    'email': 'stevensonbrandy@example.org',
    'phone_number': '796-438-2626',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kristy Morris',
    'Kelly Armstrong',
    'Ruth Kennedy',
    'Dawn Harvey',
    'Katherine Smith',
    'Monique Hale',
    'Patricia Goodwin PhD',
    'Michael Marks',
],
    'json': {
    'name': 'Jamie Serrano',
    'address': '9154 Thomas Grove Suite 671\nDarylmouth, NE 45908',
},
    'key13011': 'value64471',
    'key16479': 'value21727',
    'key79874': 'value53139',
    'key3014': 'value99058',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Tammy Pierce',
    'address': '9798 Wilcox Walk Apt. 265\nNew Briannaton, FL 69451',
    'text': 'Same hold fire. Section young air though teach strong. Blue box summer majority.',
    'email': 'farleymelanie@example.net',
    'phone_number': '+1-930-790-3178x45512',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Scott Anderson',
    'Craig Hernandez',
    'Raymond Brown MD',
    'Natalie Patel',
    'Rachel Wagner',
    'Michael Martin',
],
    'json': {
    'name': 'Jason Gray',
    'address': 'PSC 2307, Box 0161\nAPO AE 97655',
},
    'key22173': 'value1759',
    'key1044': 'value98',
    'key22347': 'value80207',
    'key40875': 'value62216',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Sandra Brown',
    'address': '234 Walker Circles\nDawnton, NV 88538',
    'text': 'Write stand set item message. Executive former bit election believe step sport. Success Mr edge total one during option.',
    'email': 'michaelolsen@example.org',
    'phone_number': '702.685.7936',
    'array_int_dynamic': [
    52219,
],
    'array_varchar_dynamic': [
    'Kathryn Morris',
    'Phillip Simmons',
    'Mark Sims',
    'Mr. Dale Wilson',
    'Christopher Wells',
    'Daniel Evans PhD',
    'Joshua Mccarthy',
],
    'json': {
    'name': 'Charles Rodriguez',
    'address': '446 Elliott Unions\nOliviaport, KS 78564',
},
    'key74320': 'value23597',
    'key72394': 'value98420',
    'key67845': 'value99062',
    'key51510': 'value60260',
    'key216': 'value88005',
    'key66532': 'value19351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Mark Mendez',
    'address': '06468 Payne Rue Suite 232\nSouth Mark, AL 27682',
    'text': 'World growth source food area use through. Find experience economic state its political.\nProduct general his month store. Real see down.',
    'email': 'anthonyrogers@example.org',
    'phone_number': '+1-751-814-7023x969',
    'array_int_dynamic': [
    10516,
],
    'array_varchar_dynamic': [
    'Lisa Hernandez',
    'Jennifer Gibson',
    'Samantha Cameron',
],
    'json': {
    'name': 'Michael Lee',
    'address': '58123 Smith Corner Suite 888\nAmyfort, OK 19105',
},
    'key8179': 'value46194',
    'key75054': 'value69361',
    'key48302': 'value36344',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Erica Richardson DDS',
    'address': '86896 Malik Curve\nEast Andreaview, GA 62058',
    'text': 'Under ago style view after. New two town.\nPaper budget agent walk.\nThese left change huge rest take today. Much church war although. Five wonder thus once national news day.',
    'email': 'thomas53@example.org',
    'phone_number': '680.741.2567x51498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Krystal Baker',
    'Tricia Rice',
    'Jennifer Davis',
    'Charles Hawkins',
    'Cheryl Davis',
    'Angela Higgins',
    'Diane Morse',
    'Kristy Mclean',
    'Monica Roman',
],
    'json': {
    'name': 'Nancy Pratt',
    'address': '659 Davis Passage Apt. 195\nLake Josemouth, MS 67437',
},
    'key23880': 'value81900',
    'key48491': 'value93035',
    'key47864': 'value93987',
    'key76362': 'value62582',
    'key90503': 'value44890',
    'key19193': 'value37794',
    'key96470': 'value20568',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Stephanie Vasquez',
    'address': 'USCGC Gonzalez\nFPO AE 15685',
    'text': 'Remain mean much there around throughout onto. Five difference to begin job sit.\nScientist live crime. Whose since individual discuss. Gas environment various somebody operation would fine.',
    'email': 'gregoryphillips@example.com',
    'phone_number': '(449)268-1767x2359',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Spencer Washington',
    'Kimberly Paul',
    'Dr. Andrea Castro',
    'Michael Pearson',
    'Benjamin Ross',
],
    'json': {
    'name': 'Kevin White',
    'address': '1459 Brennan Station Suite 729\nDavisside, NJ 01894',
},
    'key88307': 'value87110',
    'key75833': 'value18384',
    'key42371': 'value81229',
    'key47129': 'value49393',
    'key92280': 'value91704',
    'key27873': 'value22685',
    'key89940': 'value68762',
    'key89594': 'value68212',
    'key52958': 'value27351',
    'key54471': 'value42738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Brittany Ochoa',
    'address': '2395 Williams Locks\nWelchstad, MA 29043',
    'text': 'Wife sea so something coach debate. Cost behavior year book risk.\nResult party culture research PM single movie. Crime official soon have hand realize. Which result meeting.',
    'email': 'ualexander@example.org',
    'phone_number': '(455)401-1311x659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jill Graham',
    'Connor Fletcher',
    'Steven Obrien',
    'Gina Savage MD',
    'Joy Rodriguez',
    'Mark Navarro',
    'Joyce Moore',
    'Sharon Hernandez',
    'Elizabeth Moore',
    'Thomas Elliott',
],
    'json': {
    'name': 'Alejandra Moore',
    'address': '502 Casey Stream Suite 852\nCrystalside, VT 29363',
},
    'key96155': 'value11702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Alexandra Richardson',
    'address': '2599 Kathleen Locks Apt. 119\nNorth Andrew, PR 83946',
    'text': 'Something current agency scientist city contain. Will important through event hot money success. Detail those support. Test among quite simply end past and.',
    'email': 'fjohnson@example.com',
    'phone_number': '4543061011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristin Anderson',
    'Diane Cruz',
    'Jennifer Carpenter',
    'Christopher Mills',
    'Jessica Best',
    'Jeffery Turner',
    'Robin Yang',
    'Laura Franklin DDS',
],
    'json': {
    'name': 'Matthew Foley',
    'address': '46469 Luna Spring\nDakotafort, KS 89529',
},
    'key46718': 'value53416',
    'key46869': 'value82513',
    'key83840': 'value31952',
    'key59143': 'value5889',
    'key36868': 'value15229',
    'key94485': 'value74089',
    'key13749': 'value48608',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Lisa Horn',
    'address': 'PSC 9908, Box 5429\nAPO AA 79326',
    'text': 'Voice home level fire.\nOfficer sit century color different. Parent by light create well candidate.\nNews they exactly kid concern training just. State someone production statement represent finally.',
    'email': 'acook@example.net',
    'phone_number': '635.711.1091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Jackson',
    'Lisa Monroe',
    'William Sanchez',
    'Rachel Hudson',
    'Brian Herrera',
    'Joyce Gibbs',
],
    'json': {
    'name': 'Mary Floyd',
    'address': '31546 Rhonda Locks Suite 056\nGrantmouth, MI 59334',
},
    'key94200': 'value61614',
    'key24272': 'value27651',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'William Bruce',
    'address': '742 Huang Pass Apt. 459\nRichardsonland, WV 70636',
    'text': 'Forward challenge camera. I way couple their.\nWall media speech really rock turn discuss. Thought recently bad contain tough class. Claim each effect. Today parent level way join.',
    'email': 'ahernandez@example.org',
    'phone_number': '(540)919-3998',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Yolanda Nelson',
    'Spencer Wilkins',
],
    'json': {
    'name': 'Seth Brown',
    'address': '365 Diane Way\nDenisemouth, ID 72857',
},
    'key28162': 'value88673',
    'key3699': 'value20724',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Robert Edwards',
    'address': '29684 Jessica Key\nLake Jacquelineberg, KS 06567',
    'text': 'Station everybody thus program seek force thing. Image you tree camera.\nPersonal argue their him work available none. Commercial check sound buy standard.',
    'email': 'carlsonjulie@example.com',
    'phone_number': '718-548-1897x4925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Jones',
],
    'json': {
    'name': 'Leonard Franco',
    'address': '22888 Daniel Drives\nTaylorshire, ND 36471',
},
    'key72040': 'value97721',
    'key37766': 'value16704',
    'key4895': 'value21302',
    'key588': 'value12807',
    'key13311': 'value76230',
    'key85818': 'value10771',
    'key97276': 'value42647',
    'key5793': 'value40236',
    'key41706': 'value44921',
    'key27594': 'value34427',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Darlene Crawford',
    'address': '2937 Zimmerman Park\nWest John, MP 53904',
    'text': 'Figure so bar free buy culture necessary scientist. Cause generation improve his. News learn move alone choose example. Several rather blue result challenge manage dream.',
    'email': 'tammyrussell@example.com',
    'phone_number': '(706)291-2222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Casey Alvarado',
    'Sarah Goodman',
    'Andrew Miller',
    'Mary Pitts',
    'Tiffany Martinez',
],
    'json': {
    'name': 'Robert Alvarez',
    'address': '20459 Pratt Club Apt. 225\nNicholastown, KS 01542',
},
    'key27910': 'value80882',
    'key94129': 'value79650',
    'key82138': 'value16889',
    'key35787': 'value82628',
    'key34231': 'value41817',
    'key63822': 'value78127',
    'key38971': 'value9087',
    'key40234': 'value89560',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Gabrielle Glass',
    'address': '14686 Benjamin Bypass Apt. 480\nGarciafurt, MD 38084',
    'text': 'Part prevent site. Herself body class total indicate speak tell. Heavy tough remain let also like when product.\nCountry daughter deep pull stand claim. Girl choice front current. Or economic type.',
    'email': 'palexander@example.org',
    'phone_number': '385-543-2012x687',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'James Mann',
    'Mark Carroll',
    'Sandra Herrera',
    'Kathryn Thompson',
    'Michael Martin',
    'Ashley Hernandez',
    'Heather Young',
    'Sarah Bowers',
    'Donald Sandoval',
    'Latasha Summers',
],
    'json': {
    'name': 'Joshua Flores',
    'address': '4221 White Route Apt. 497\nSouth Angela, UT 26462',
},
    'key67376': 'value72261',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Kelli Joseph',
    'address': '132 Rhodes Turnpike\nPort Matthewhaven, VT 81265',
    'text': 'Growth professional among third. Effect compare whether life hotel art. Effect material in.\nPer over seek deal others cost thousand. Worry language American movement.',
    'email': 'aaron67@example.net',
    'phone_number': '723.989.8635',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Brown',
    'Brandon Rocha',
],
    'json': {
    'name': 'Mr. Martin Klein',
    'address': '727 Smith Keys Suite 789\nWest Christine, OH 58776',
},
    'key35444': 'value49362',
    'key7646': 'value26800',
    'key55779': 'value87181',
    'key54369': 'value15167',
    'key33054': 'value7123',
    'key50949': 'value65989',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kelly Dean',
    'address': '9450 Davis Parkway Suite 020\nBateshaven, FL 69103',
    'text': 'Dog would offer interest what respond floor report. Sing doctor child hand. Use bad probably own.',
    'email': 'autumnpeterson@example.org',
    'phone_number': '+1-524-883-2776x934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Austin Meza',
    'Danny Osborn',
    'Chelsea Buchanan',
    'Peter Keller',
    'Douglas Hamilton',
    'Bryan Glass',
    'George Elliott',
],
    'json': {
    'name': 'Joshua Davis',
    'address': '359 Ian Summit\nPort Julieton, NV 61576',
},
    'key30756': 'value6663',
    'key86281': 'value42864',
    'key85042': 'value10824',
    'key77306': 'value4895',
    'key67698': 'value19727',
    'key85979': 'value33042',
    'key27633': 'value23109',
    'key97723': 'value55856',
    'key41231': 'value45011',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Megan Hall',
    'address': '401 Norton Courts\nWest Samanthafort, NV 11445',
    'text': 'Term particular current national water simply there. Test vote each work thought common size.\nWord tree lay subject.',
    'email': 'nathanieljones@example.net',
    'phone_number': '803-695-8714x2587',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laura Hall',
    'Caroline Crawford',
    'Sarah Dorsey',
    'Jerry Johnson',
],
    'json': {
    'name': 'Melissa Shannon',
    'address': '114 Bartlett River Suite 474\nMillsborough, TN 35516',
},
    'key30487': 'value31586',
    'key98033': 'value22845',
    'key63739': 'value54156',
    'key20530': 'value55223',
    'key69766': 'value27245',
    'key91052': 'value9696',
    'key24915': 'value82376',
    'key78936': 'value77164',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Eileen Ford',
    'address': '4660 Gillespie Lights Apt. 686\nOsbornside, VI 33830',
    'text': 'Off its find relate act. Education front particular. Recognize government nature along.\nCreate thus drug item industry tonight. Travel visit opportunity sign great.',
    'email': 'maxwellcody@example.org',
    'phone_number': '334.745.8774x7624',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Peter Mendoza',
    'Zachary Johnson',
    'Darin Watts',
    'Brittany White',
    'Willie Garcia',
    'Jared Woods',
    'Ms. Nicole White',
    'Karen James',
    'Ryan Barker',
    'Regina Davis',
],
    'json': {
    'name': 'Diana Mason',
    'address': '661 Barron Lake Suite 624\nSouth Kristenland, ID 04902',
},
    'key79434': 'value80045',
    'key9888': 'value54838',
    'key44620': 'value73941',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Matthew Flores',
    'address': 'PSC 8633, Box 2357\nAPO AE 45738',
    'text': 'Certainly rise tough positive trade race off. Through reduce build only couple good right.\nTreat become hot clearly water end responsibility. Court growth produce lot.',
    'email': 'richardwalker@example.com',
    'phone_number': '+1-630-547-1674x40700',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Micheal Miles',
    'Justin Garcia',
    'Justin Pena',
    'Bryan Davis',
    'Joseph James',
],
    'json': {
    'name': 'Taylor Smith',
    'address': '561 Steven Turnpike\nDonaldland, AZ 03798',
},
    'key94233': 'value49937',
    'key28179': 'value15698',
    'key27463': 'value78072',
    'key34738': 'value67826',
    'key84102': 'value74424',
    'key42951': 'value72909',
    'key85473': 'value92874',
    'key84292': 'value79021',
    'key81707': 'value91897',
    'key2012': 'value39903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Leslie House',
    'address': '2061 Reese Expressway Apt. 369\nSouth Billy, GU 52844',
    'text': 'Site Mrs station high later early. Office such reason stand authority.\nNational lawyer others color surface across. Receive to always market.',
    'email': 'barneslarry@example.com',
    'phone_number': '(781)739-8471',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Moyer',
    'Matthew Harrington',
],
    'json': {
    'name': 'Rebecca Spears',
    'address': '2054 Sue Creek Suite 334\nAnitatown, PR 43635',
},
    'key37722': 'value26165',
    'key96380': 'value76925',
    'key98329': 'value70707',
    'key61552': 'value43670',
    'key64323': 'value99747',
    'key60182': 'value23696',
    'key80396': 'value27948',
    'key90052': 'value97330',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Catherine Cooper',
    'address': '332 Donald Fall Suite 059\nBaileyhaven, CO 38031',
    'text': 'Community energy future hand technology scene mind. Operation would mention these experience before exist.',
    'email': 'lmcgee@example.net',
    'phone_number': '+1-318-676-6192x4200',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Richard Burgess',
    'Greg Gilbert',
    'Miranda Hodge',
    'Richard Haynes',
    'Daniel Martin',
    'Glenn Mccall',
],
    'json': {
    'name': 'Joanna Davidson',
    'address': '1612 David Summit Suite 266\nIanstad, ME 19313',
},
    'key75055': 'value3766',
    'key39141': 'value7197',
    'key40763': 'value33013',
    'key1624': 'value36542',
    'key23323': 'value96962',
    'key48028': 'value31333',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Keith Ruiz',
    'address': '192 James Skyway Apt. 485\nMeganhaven, VT 18751',
    'text': 'Author of whether defense true friend by. Must bank work.\nUpon research outside nothing rest professor remain. Value quickly arrive whom five relationship. Any player voice also practice raise space.',
    'email': 'perrybrandy@example.com',
    'phone_number': '723-911-9461',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Mack',
    'Thomas Garcia',
    'William Mcpherson',
    'Jennifer Barber',
    'Brenda Bradley',
    'Anthony Griffin',
],
    'json': {
    'name': 'Tara Mitchell',
    'address': '04359 Jennifer Villages Apt. 498\nAshleyville, CA 87038',
},
    'key24277': 'value73322',
    'key56664': 'value52158',
    'key92168': 'value47320',
    'key81375': 'value86945',
    'key72872': 'value45450',
    'key7476': 'value14073',
    'key32946': 'value71283',
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
    'RequestId': '86922294-62f1-11f0-9c71-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_20_998772BmnnOxZM',
    'filter': 'uid >= 0',
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '7fd8041e-62f1-11f0-bea7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_20_998772BmnnOxZM',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752744993.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid01752744993Json()
    test.run_tests()
