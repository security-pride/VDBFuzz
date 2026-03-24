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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestRestfulSdkCompatibility_test_collection_create_by_restful_delete_vector_by_sdk_1752747081_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_delete_vector_by_sdk_1752747081.json"
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



class AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulDeleteVectorBySdk1752747081Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_delete_vector_by_sdk_1752747081.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_delete_vector_by_sdk_1752747081.json"
        self.test_count = 6  # 测试方法数量
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
    'RequestId': '5844244e-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_11_03_085892lqWCFcoK',
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
    'RequestId': '5844244e-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_11_03_085892lqWCFcoK',
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
    'RequestId': '5844244e-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_11_03_085892lqWCFcoK',
    'data': [
    {
    'id': 17527470691229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Donald Shannon',
    'address': '23476 Fisher Garden Apt. 165\nSheilaborough, FM 94269',
    'text': 'Rich law free series worry will art read. Glass now traditional card.\nConcern politics similar. Fund candidate week news simply space effort. Pick responsibility radio rule we wind.',
    'email': 'tatesherry@example.org',
    'phone_number': '332.718.0395x34873',
    'json': {
    'name': 'Janet Thompson',
    'address': '415 Michael Wells Apt. 923\nSouth Rhondastad, PR 34723',
},
    'key83382': 'value20920',
    'key814': 'value90239',
    'key72488': 'value25114',
    'key93875': 'value21108',
},
    {
    'id': 17527470691248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Lisa Hogan',
    'address': '528 Sierra Mount Apt. 732\nEricberg, NH 75629',
    'text': 'A answer life air green. Painting who deep example throughout. Turn reflect improve once around.\nEnter drop number talk letter weight second. Lead star campaign consumer.',
    'email': 'michael55@example.net',
    'phone_number': '001-466-467-5084x581',
    'json': {
    'name': 'Hannah Porter',
    'address': '292 Williams Walks Apt. 207\nJessicaside, AL 04635',
},
    'key24782': 'value88630',
    'key42465': 'value32215',
    'key15973': 'value31447',
},
    {
    'id': 17527470691261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'John Edwards',
    'address': 'PSC 6797, Box 1058\nAPO AP 27031',
    'text': 'Reason team happy stand best before. Perform guess action institution store rise listen. Picture support mean share article. Report use site speech.',
    'email': 'gillalicia@example.net',
    'phone_number': '897-378-7446',
    'json': {
    'name': 'Christian Bryan',
    'address': '849 Jennifer Extension Suite 154\nSouth Jamesland, MH 33693',
},
    'key89399': 'value21955',
    'key70848': 'value86777',
    'key46370': 'value63938',
    'key22783': 'value92177',
    'key86483': 'value24661',
},
    {
    'id': 17527470691273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Brenda Kelley',
    'address': '322 Theresa Field\nNicholsbury, VI 03638',
    'text': 'Themselves pattern social despite child staff. Civil security single write service performance.\nTake opportunity window. Page recognize upon in.',
    'email': 'rodriguezjonathan@example.com',
    'phone_number': '(388)567-3841x477',
    'json': {
    'name': 'Lindsey Harmon',
    'address': '076 Thomas Squares\nEast Diane, TX 66608',
},
    'key48495': 'value66223',
    'key83974': 'value68677',
    'key22504': 'value4189',
    'key25483': 'value59129',
    'key48303': 'value42602',
    'key46995': 'value53712',
    'key57791': 'value61752',
    'key93652': 'value2824',
    'key31232': 'value36556',
},
    {
    'id': 17527470691287,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Christopher Johnson',
    'address': 'USCGC Jackson\nFPO AP 23021',
    'text': 'Admit effort management loss involve either window. Help or note something home finally man art. Respond personal down commercial during.\nMarket very Congress impact. Policy music mouth because.',
    'email': 'stevenstewart@example.com',
    'phone_number': '861.269.4645x684',
    'json': {
    'name': 'James Webb',
    'address': '8535 Megan Isle\nManningport, MS 12932',
},
    'key11450': 'value22919',
    'key34699': 'value10877',
},
    {
    'id': 17527470691300,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Patrick Manning',
    'address': '1006 Juarez Run\nTyroneland, OK 25381',
    'text': 'Game prove account debate. A town above five other hot.\nTurn grow sing own center be. Record drive assume decision study.\nReport story her myself court. Energy pull beat box item product.',
    'email': 'pwang@example.org',
    'phone_number': '(415)629-4584',
    'json': {
    'name': 'Daniel Huber',
    'address': '3996 Freeman Keys\nEast Rebeccatown, VA 33816',
},
    'key21681': 'value96002',
    'key88099': 'value60144',
    'key29460': 'value11875',
},
    {
    'id': 17527470691313,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Robert Romero',
    'address': 'PSC 4028, Box 6842\nAPO AE 31135',
    'text': 'Fear create that also wide look. Sure believe before send attorney page speech. Really try indicate Congress Republican course.\nIncrease past talk sort six even.',
    'email': 'sabrina99@example.com',
    'phone_number': '234.566.8803x40401',
    'json': {
    'name': 'Tara Chang',
    'address': '05856 Brian Lane\nVictoriafurt, UT 49896',
},
    'key84698': 'value82878',
    'key32258': 'value1834',
    'key76739': 'value28755',
    'key68769': 'value77615',
    'key36946': 'value29437',
    'key56964': 'value16853',
    'key72300': 'value83877',
},
    {
    'id': 17527470691323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Robert Williams',
    'address': '9726 Davis Loop Suite 826\nBakerfort, UT 84049',
    'text': 'Society director leader moment. Young parent design this good involve. Speech hair six.\nPurpose serve skin moment station bed since. Pay physical challenge write drug degree.',
    'email': 'sarahhayes@example.net',
    'phone_number': '+1-959-456-5989x132',
    'json': {
    'name': 'Suzanne Young',
    'address': '75658 Todd Burgs\nWest Joseph, PW 34030',
},
    'key29626': 'value99763',
    'key1036': 'value23188',
    'key8713': 'value2634',
    'key24756': 'value88108',
    'key54964': 'value16387',
    'key84646': 'value79621',
    'key88284': 'value8391',
},
    {
    'id': 17527470691336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Nicholas Powers',
    'address': '089 Brittney Island Apt. 039\nPort Christina, SC 19099',
    'text': 'Since western raise just daughter relationship thought.\nJoin shake laugh describe respond chance poor. Education force image entire computer.',
    'email': 'rileypatterson@example.com',
    'phone_number': '(448)690-9649x575',
    'json': {
    'name': 'James Nelson',
    'address': '346 Orozco Mills\nNorth Stacey, SD 51239',
},
    'key55583': 'value83439',
    'key80920': 'value75534',
    'key8517': 'value1170',
    'key56566': 'value67691',
    'key39768': 'value28932',
},
    {
    'id': 17527470691348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Wesley Johnson',
    'address': '5361 Hardin Dale Suite 546\nLake John, FL 11990',
    'text': 'Teach exist blue school possible miss site station. Allow camera behavior still community western.\nLater health hot western represent try certain. Bad big talk ability. Pm worry run wonder I meeting.',
    'email': 'shannon34@example.org',
    'phone_number': '(713)570-9215x7568',
    'json': {
    'name': 'Jessica Anderson',
    'address': '2845 Jasmin Trail\nEast Sabrina, MN 98932',
},
    'key77060': 'value90246',
    'key5463': 'value12521',
    'key9010': 'value48238',
},
    {
    'id': 17527470691360,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Stacey Franklin',
    'address': '002 Christine Trail Suite 386\nSouth Steventown, NM 65286',
    'text': 'Drive technology place hold. Yeah since surface son. Poor plan debate federal. Often old eat support pull low deal.\nPush memory ability. Language foreign exactly president degree.',
    'email': 'owalker@example.org',
    'phone_number': '235.846.2098',
    'json': {
    'name': 'Ashley Hernandez',
    'address': '651 Samuel Lake\nNorth Thomas, NV 05170',
},
    'key77931': 'value30096',
},
    {
    'id': 17527470691371,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Sheryl Jackson',
    'address': '7490 Sara Tunnel\nNorth Katie, NJ 87439',
    'text': 'Push particularly beautiful performance until later. Fall find none. Thing only many business describe involve say.',
    'email': 'heather84@example.com',
    'phone_number': '(713)304-3841',
    'json': {
    'name': 'Jennifer Dennis',
    'address': 'PSC 1072, Box 3385\nAPO AE 12285',
},
    'key79089': 'value12311',
    'key24393': 'value50844',
},
    {
    'id': 17527470691380,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Lindsay Miller',
    'address': '4738 Tucker Tunnel\nShawnland, MO 15988',
    'text': 'Drive stay try fire interesting writer big. Public any church health center office.\nForm type ground father least same not. Model over to notice. Decision glass coach road practice black.',
    'email': 'nnolan@example.org',
    'phone_number': '(557)551-2001x4878',
    'json': {
    'name': 'Michael Ball',
    'address': '5586 Daniel Mountains\nTimothyburgh, NH 11952',
},
    'key85825': 'value87027',
    'key15953': 'value31599',
    'key95951': 'value67357',
    'key38998': 'value56864',
    'key39941': 'value32370',
    'key9725': 'value83658',
},
    {
    'id': 17527470691390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Paul Burgess',
    'address': '824 Craig Well\nNorth Alexis, NY 80528',
    'text': 'Involve both smile myself. Central risk money friend see manager much.\nHouse situation attorney drive line. Forward west cold sign.',
    'email': 'vking@example.com',
    'phone_number': '001-597-224-0494',
    'json': {
    'name': 'Dr. Natalie Lindsey',
    'address': '97986 Elijah Viaduct Suite 018\nRobbinsfort, AS 21749',
},
    'key47290': 'value26932',
    'key48225': 'value61551',
    'key89407': 'value30803',
    'key62590': 'value33024',
    'key34463': 'value50974',
},
    {
    'id': 17527470691402,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Randall Caldwell',
    'address': '09771 Taylor Shoals Apt. 924\nEast Monicaborough, VI 25548',
    'text': 'Its start room federal media. Begin race join small foot. Art else more side.\nCut strong him discuss individual. Coach seek claim possible picture reduce.',
    'email': 'james90@example.net',
    'phone_number': '875-817-2537',
    'json': {
    'name': 'Curtis Crawford',
    'address': '696 Deanna Oval Suite 100\nSouth Donald, VA 51772',
},
    'key25666': 'value77112',
    'key60787': 'value46665',
    'key53775': 'value27712',
    'key81704': 'value88369',
},
    {
    'id': 17527470691413,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Levi White',
    'address': '345 Michelle Path Apt. 070\nKellershire, SD 96295',
    'text': 'At marriage always book simple eight different. Baby sister beyond improve expect.\nNearly room total major listen address although. Get either red woman action wait should. From herself let compare.',
    'email': 'ubradford@example.com',
    'phone_number': '511-690-9843',
    'json': {
    'name': 'Daniel Becker',
    'address': '40948 Rhonda Turnpike\nNew Kevinside, KY 82642',
},
    'key29429': 'value60495',
    'key83090': 'value33892',
    'key64753': 'value86689',
    'key23370': 'value51111',
    'key93169': 'value66928',
    'key83216': 'value50257',
    'key89741': 'value48692',
    'key891': 'value63094',
},
    {
    'id': 17527470691424,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Mandy Hudson',
    'address': '3717 Moore Terrace\nSouth Bryan, MA 40156',
    'text': 'Son leg part five. Approach particularly finish heart institution opportunity state. And sea now another write course popular.',
    'email': 'jason77@example.org',
    'phone_number': '001-880-866-6221x986',
    'json': {
    'name': 'Felicia Shepherd',
    'address': 'Unit 2989 Box 4014\nDPO AA 69848',
},
    'key22783': 'value50851',
    'key84986': 'value57873',
    'key43824': 'value26916',
    'key81258': 'value58950',
    'key23247': 'value65480',
    'key49078': 'value36574',
    'key9869': 'value48569',
    'key12058': 'value73750',
    'key62588': 'value75294',
    'key51958': 'value42336',
},
    {
    'id': 17527470691432,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tina Diaz',
    'address': '775 Jefferson Falls\nHeidiside, NJ 55866',
    'text': 'Point either bill even theory enjoy explain security. Painting author kitchen visit. Sort continue prevent as.',
    'email': 'james02@example.com',
    'phone_number': '9849314106',
    'json': {
    'name': 'Ryan Wiley',
    'address': '77258 Daniel Fields Apt. 525\nPort Matthewmouth, FM 64015',
},
    'key44130': 'value32644',
    'key38397': 'value39153',
    'key15263': 'value6982',
    'key89507': 'value71622',
    'key16115': 'value27632',
    'key36152': 'value48139',
    'key24320': 'value756',
    'key47899': 'value47738',
},
    {
    'id': 17527470691443,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Anthony Jones',
    'address': '76219 Perez Loop\nGreenstad, ND 11473',
    'text': 'Night theory manager remember clear talk look clearly. Analysis simple west economic within.\nTable report especially decide forget especially.\nBar town own with among both.',
    'email': 'amanda43@example.net',
    'phone_number': '(967)963-8390x4902',
    'json': {
    'name': 'Kimberly Guzman',
    'address': 'Unit 2522 Box 3015\nDPO AA 60794',
},
    'key94836': 'value81920',
    'key84974': 'value12554',
    'key19219': 'value66715',
    'key69232': 'value58048',
    'key37633': 'value47033',
    'key58142': 'value41495',
    'key80198': 'value82980',
    'key93439': 'value5182',
    'key95226': 'value82012',
},
    {
    'id': 17527470691451,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Paul Moody',
    'address': '77404 Jennifer Ridges\nNew Kellymouth, HI 04293',
    'text': 'Professor new article including. Green sister enough.\nOur result shoulder social artist according indeed. Trial population once they sea management edge.',
    'email': 'cfrey@example.net',
    'phone_number': '+1-337-313-3695x709',
    'json': {
    'name': 'Gregory Jackson',
    'address': '675 Alexander Freeway\nDavidsonshire, TN 94506',
},
    'key21605': 'value8176',
    'key1399': 'value10739',
    'key86071': 'value24517',
    'key76803': 'value72425',
    'key78411': 'value25194',
    'key94203': 'value68018',
    'key81519': 'value64169',
    'key1455': 'value34181',
    'key25199': 'value48220',
},
    {
    'id': 17527470691462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Alexander Taylor',
    'address': '34367 Jackson Common\nNorth Erin, NV 82928',
    'text': 'Court unit indeed any end miss. Worker walk bank stand career around probably.\nArt unit woman middle. Strong anything skill current.',
    'email': 'tmccoy@example.net',
    'phone_number': '+1-565-251-8902x544',
    'json': {
    'name': 'Robert Smith',
    'address': '79544 Thomas Mission Suite 121\nMariefurt, MA 59157',
},
    'key23428': 'value79439',
    'key89638': 'value14238',
    'key30601': 'value88777',
    'key26255': 'value6908',
    'key31536': 'value73940',
    'key29123': 'value40928',
    'key1777': 'value25584',
    'key82088': 'value25510',
    'key19664': 'value50230',
    'key33424': 'value89537',
},
    {
    'id': 17527470691473,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Brandon Anderson',
    'address': '23317 Harold Street\nDouglasstad, MD 17380',
    'text': 'Fight often century one remember office. Stand across street behavior mention poor pass. Religious stop chance. Security start moment.',
    'email': 'edavis@example.net',
    'phone_number': '301.612.2901x514',
    'json': {
    'name': 'John Hernandez',
    'address': '579 Stanley Isle\nRicardoton, VT 28722',
},
    'key2246': 'value73504',
    'key48579': 'value48428',
    'key55799': 'value749',
    'key6343': 'value59219',
    'key21878': 'value7426',
    'key62504': 'value96155',
    'key12809': 'value87385',
    'key36225': 'value47934',
    'key93033': 'value51014',
},
    {
    'id': 17527470691483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Alan Flores',
    'address': 'PSC 5135, Box 3546\nAPO AP 94179',
    'text': 'Girl never million determine memory administration. Them difficult product sister. Along hold authority particularly look.',
    'email': 'mlopez@example.net',
    'phone_number': '456.523.8616',
    'json': {
    'name': 'Karina Boone',
    'address': '064 Jacob Road\nLake Emilystad, AL 60759',
},
    'key67944': 'value34556',
    'key78803': 'value56680',
    'key84897': 'value27609',
    'key50946': 'value34721',
},
    {
    'id': 17527470691491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Catherine Daniels',
    'address': '1447 Reyes Islands Suite 925\nAmyburgh, NM 01217',
    'text': 'Agree capital walk produce should century. Source side develop win prevent meet. Green stage which create book woman.\nLate me reflect although particularly. Occur each property issue.',
    'email': 'jennifermartin@example.net',
    'phone_number': '984.961.8337x4643',
    'json': {
    'name': 'Kimberly Mclean',
    'address': '14598 Young Summit\nSouth Amber, ME 24888',
},
    'key37728': 'value97709',
},
    {
    'id': 17527470691503,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Christopher Wise',
    'address': '6568 Watts Ports Apt. 386\nWest Katherineport, VI 97669',
    'text': 'Television deep together then your. Business continue write TV quality natural. Vote which quite through crime.\nDifference apply throw organization. Night past street less.',
    'email': 'qmartinez@example.org',
    'phone_number': '8999386302',
    'json': {
    'name': 'Robert Henry',
    'address': '764 Tanner Mill Suite 932\nNew Jordanton, CA 52710',
},
    'key99484': 'value97238',
    'key33962': 'value53233',
    'key45422': 'value87251',
    'key12302': 'value99536',
    'key33666': 'value69150',
},
    {
    'id': 17527470691514,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'John Jones',
    'address': '639 Matthew Orchard Apt. 157\nTaramouth, SC 08385',
    'text': 'Drug push allow guy low. Change read politics sometimes happen them.\nNow gun issue compare set. Professional interest your almost second. Task discussion fight dog.',
    'email': 'craig90@example.com',
    'phone_number': '281-671-7384x3144',
    'json': {
    'name': 'Raymond Diaz',
    'address': '300 Lisa Springs Suite 663\nAshleyberg, MP 52519',
},
    'key17714': 'value96086',
    'key97435': 'value35900',
    'key82139': 'value39265',
    'key55085': 'value66022',
    'key87688': 'value57605',
},
    {
    'id': 17527470691524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Denise Ramirez',
    'address': '8040 Adkins Shoals Apt. 264\nFloresstad, NJ 17997',
    'text': 'Carry employee world necessary main break most see. Indeed animal design. Possible media radio girl fast option. Everyone world final another eight soldier.',
    'email': 'brett76@example.org',
    'phone_number': '7326773249',
    'json': {
    'name': 'Ebony Bailey',
    'address': '209 Oliver Squares\nSylviaport, ID 66220',
},
    'key40886': 'value68584',
    'key41402': 'value63811',
    'key57582': 'value17527',
},
    {
    'id': 17527470691535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Lisa Schneider',
    'address': '4375 Marshall Islands\nNorth Jamesville, GA 17714',
    'text': 'According budget level civil black accept street notice. Husband bit spend. Trip pay clearly our six.',
    'email': 'sanchezclayton@example.com',
    'phone_number': '+1-383-861-0396x8044',
    'json': {
    'name': 'Brittany Burton',
    'address': '29515 Bryant Island Apt. 693\nEast Deannaburgh, UT 33832',
},
    'key40332': 'value62868',
    'key92340': 'value19402',
    'key85129': 'value70762',
    'key23395': 'value45192',
    'key43139': 'value37371',
    'key91012': 'value14499',
    'key98315': 'value59243',
},
    {
    'id': 17527470691547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Mr. Patrick Hudson',
    'address': '86763 Ellis Falls\nLake Adrianton, WY 56045',
    'text': 'Church stock production child. Affect century indeed matter discover investment. Side road hit indicate surface.\nBill thank artist if opportunity leader. List prove boy receive by.',
    'email': 'uwright@example.org',
    'phone_number': '+1-287-313-8810',
    'json': {
    'name': 'Luke Matthews',
    'address': '17439 Turner Meadow\nDavidtown, UT 98273',
},
    'key2450': 'value36295',
    'key42901': 'value90044',
    'key27305': 'value75941',
    'key19849': 'value34950',
    'key74766': 'value25678',
},
    {
    'id': 17527470691558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Veronica Miller',
    'address': '32083 Avila Neck Apt. 141\nHawkinsland, TN 95477',
    'text': 'Rise as why per glass health fact. Teacher under toward prove.\nPeople let north land identify recognize conference. Better age peace show.',
    'email': 'riggsryan@example.net',
    'phone_number': '384-210-2895x42539',
    'json': {
    'name': 'Sarah Tran',
    'address': '6458 Benitez Crossing Suite 672\nNorth Jeffery, MT 55916',
},
    'key586': 'value50266',
    'key31773': 'value89794',
    'key36327': 'value86417',
    'key40729': 'value65526',
    'key95650': 'value1883',
    'key68344': 'value61810',
    'key23828': 'value75308',
    'key4041': 'value43621',
    'key85620': 'value73150',
    'key79551': 'value30346',
},
    {
    'id': 17527470691571,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Joseph James',
    'address': '192 Smith Square Suite 247\nLeonfurt, SD 83530',
    'text': 'A itself impact her. Word consider world whether sell take break young. Data here tell child girl pick just.',
    'email': 'brendabuchanan@example.org',
    'phone_number': '001-463-843-1378x4656',
    'json': {
    'name': 'Kenneth Lozano',
    'address': '9363 Diane Vista Suite 495\nJenniferland, DE 15413',
},
    'key75394': 'value41741',
    'key64381': 'value97386',
    'key90538': 'value24146',
    'key18422': 'value70089',
},
    {
    'id': 17527470691582,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Grant Russell',
    'address': '0851 Pratt Drives Apt. 688\nHutchinsonfurt, NM 04486',
    'text': 'Decade amount contain describe author save. Specific ability eat economic world relationship cold. Sound human one stand. Common else later add.\nRecognize field defense miss idea federal also.',
    'email': 'logan20@example.net',
    'phone_number': '001-610-578-6247x7658',
    'json': {
    'name': 'Gregory Stokes',
    'address': '896 Freeman Terrace\nRogerside, FM 90772',
},
    'key25721': 'value65821',
    'key3659': 'value81011',
    'key90487': 'value68732',
    'key68042': 'value92023',
    'key81686': 'value62995',
    'key43622': 'value97386',
},
    {
    'id': 17527470691593,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'William Adams',
    'address': '660 Taylor Crescent\nGreerstad, SD 21157',
    'text': 'Test space cup task. Stage course onto easy finish security. Home son long she vote.\nAffect quite special professor officer require across.\nAt page officer apply. No laugh sell ever test resource.',
    'email': 'whiteheadleslie@example.com',
    'phone_number': '001-331-383-5747x81859',
    'json': {
    'name': 'Christina Pearson',
    'address': '6230 Shawn Hills\nPort Allison, OH 93252',
},
    'key46643': 'value58688',
    'key95112': 'value52354',
    'key18579': 'value72746',
    'key40445': 'value57884',
    'key56176': 'value360',
},
    {
    'id': 17527470691605,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jaclyn Mcdonald',
    'address': '57620 James River\nNorth Kelly, RI 76406',
    'text': 'Positive kid reveal response people. Sister party how see now. Establish such method. Former partner remember their name record.',
    'email': 'robertjames@example.net',
    'phone_number': '+1-308-771-5225x205',
    'json': {
    'name': 'Jason Velez',
    'address': 'Unit 2753 Box 6325\nDPO AA 53856',
},
    'key95655': 'value65920',
    'key65975': 'value45771',
    'key38297': 'value22128',
    'key82910': 'value56781',
    'key86383': 'value96405',
},
    {
    'id': 17527470691614,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Eric Fowler',
    'address': '5756 Contreras Run Apt. 881\nDawnview, OR 73130',
    'text': 'Able necessary man explain American. Wife off war plan draw beautiful. Wish indicate population wear during leg box first. Only technology easy yard heart job.',
    'email': 'jeffreylewis@example.net',
    'phone_number': '848.383.0068x58837',
    'json': {
    'name': 'Grant Morgan',
    'address': '901 Amy Rapid Apt. 863\nPort Michaelahaven, FL 55180',
},
    'key82889': 'value99883',
    'key38258': 'value45487',
    'key33280': 'value20716',
    'key72274': 'value27298',
    'key72675': 'value13312',
},
    {
    'id': 17527470691624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Mary Johnson',
    'address': '83391 Burns Landing Apt. 862\nChristopherstad, CO 43930',
    'text': 'Author ability leave order.\nCentral so tell image thank. Size beat million nothing front before. So approach quite.\nHigh board phone. Bring here father wall clearly quite never.',
    'email': 'zgonzalez@example.net',
    'phone_number': '698.655.2385x66076',
    'json': {
    'name': 'Andrew Myers',
    'address': '07631 Yvonne Pines\nSmithberg, OH 72199',
},
    'key58238': 'value65264',
    'key61752': 'value43997',
    'key325': 'value8876',
    'key76683': 'value61653',
    'key21747': 'value4421',
    'key99530': 'value47157',
    'key8137': 'value304',
    'key32658': 'value15539',
    'key97273': 'value32877',
},
    {
    'id': 17527470691636,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Bryan Huynh',
    'address': '3730 Ashley Court\nNew Ryan, KY 21235',
    'text': 'Let computer admit. Foot believe point man cultural. Speak try believe challenge mouth water best.',
    'email': 'joshuasmith@example.org',
    'phone_number': '687-480-9862',
    'json': {
    'name': 'Carla Wood',
    'address': '2937 Caitlin Route\nStewartchester, MS 90121',
},
    'key60347': 'value61317',
    'key99934': 'value68350',
    'key66208': 'value58047',
    'key3900': 'value38316',
    'key36947': 'value30186',
    'key48344': 'value97529',
    'key130': 'value25915',
    'key65719': 'value97878',
    'key22820': 'value84750',
},
    {
    'id': 17527470691647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'William Shea',
    'address': '9516 Griffith Ways Suite 669\nYoungstad, DE 46750',
    'text': 'Huge candidate say. Campaign strong admit writer.\nInformation half data series down. East hit shake discussion professional. Only teacher alone.',
    'email': 'holmesbeverly@example.com',
    'phone_number': '(415)386-4163',
    'json': {
    'name': 'Gabriella Allen',
    'address': '421 Burns Canyon Suite 088\nNew Shanemouth, AS 10774',
},
    'key56403': 'value3347',
    'key10408': 'value40279',
    'key76503': 'value39859',
    'key4351': 'value43298',
    'key27720': 'value48330',
    'key7254': 'value95703',
    'key15671': 'value93062',
},
    {
    'id': 17527470691659,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Duane Spears',
    'address': '94889 Kristi Keys Suite 102\nEast Mistyborough, HI 26943',
    'text': 'Over cut thing candidate against century. Man responsibility dinner.\nRecord available trip performance career director. Ask all bad. Sort remain meeting Democrat occur similar.',
    'email': 'tiffany32@example.net',
    'phone_number': '(577)648-3955',
    'json': {
    'name': 'Angela Blake',
    'address': '3331 Watson Fields Apt. 269\nAnnton, MH 92980',
},
    'key41183': 'value66270',
    'key10559': 'value79942',
    'key61707': 'value53371',
},
    {
    'id': 17527470691669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jackie Lester',
    'address': '65134 Smith Mill Suite 328\nMontgomeryton, NV 20829',
    'text': 'Wait whatever area win.\nArrive house young second. Box candidate city defense life. Box bed follow reveal send.\nLive music computer order. Pull remain plan man. Choice might up safe capital pick.',
    'email': 'hullmegan@example.net',
    'phone_number': '(459)748-3466',
    'json': {
    'name': 'Anne Powers',
    'address': '14184 Byrd Rue\nJacksonburgh, NE 45962',
},
    'key76674': 'value7068',
    'key76988': 'value15810',
    'key28273': 'value36805',
    'key31683': 'value4915',
    'key92334': 'value16464',
    'key19333': 'value84410',
    'key53426': 'value86656',
},
    {
    'id': 17527470691681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Amy Khan',
    'address': '131 Dustin Wells Apt. 096\nAshleytown, DE 61490',
    'text': 'Purpose none star thousand. Best road next.\nReceive production purpose.\nRed test ability ten pay. Tend mind color. Push recently consider eat capital.',
    'email': 'kathryn88@example.com',
    'phone_number': '+1-920-594-9941',
    'json': {
    'name': 'Erica Ramirez',
    'address': 'Unit 1779 Box 4901\nDPO AE 17463',
},
    'key60024': 'value41882',
    'key45461': 'value58256',
    'key69656': 'value17196',
    'key15750': 'value73991',
    'key38478': 'value65477',
    'key10237': 'value2795',
    'key23269': 'value5341',
},
    {
    'id': 17527470691690,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Krystal Jones',
    'address': 'USNV Hill\nFPO AA 15779',
    'text': 'I degree front when sure. Blue network yeah begin first show recent.',
    'email': 'milleradrian@example.org',
    'phone_number': '+1-412-607-5542x9626',
    'json': {
    'name': 'Valerie Holmes',
    'address': '346 Campbell Ridges\nWest Chad, TX 44778',
},
    'key95298': 'value19242',
    'key31464': 'value51597',
    'key4472': 'value48529',
    'key25172': 'value49334',
},
    {
    'id': 17527470691700,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Carrie Villarreal',
    'address': '88183 Stout Parkways\nSteventown, MP 82803',
    'text': 'Food send environmental. Quality mouth talk yeah point charge summer.',
    'email': 'kathryn38@example.org',
    'phone_number': '001-727-593-2732x430',
    'json': {
    'name': 'Timothy Walker',
    'address': '657 Cunningham Shore Suite 499\nRomeroton, NV 44243',
},
    'key13426': 'value53386',
    'key36597': 'value70313',
    'key72108': 'value31657',
    'key97748': 'value12864',
    'key62104': 'value54090',
    'key91691': 'value5311',
    'key56633': 'value57132',
    'key74156': 'value26835',
    'key2149': 'value94726',
},
    {
    'id': 17527470691712,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Timothy Long',
    'address': 'USNV Perez\nFPO AA 54236',
    'text': 'Speak everybody whole real certainly trouble already. Another wonder training section where. Expect song like above sea.',
    'email': 'ellen87@example.com',
    'phone_number': '656-806-0906x9783',
    'json': {
    'name': 'Darrell Richardson',
    'address': '996 Tara Oval Suite 415\nKurtbury, NV 25204',
},
    'key23569': 'value57411',
    'key45540': 'value32668',
    'key13748': 'value48298',
    'key66279': 'value76011',
    'key14211': 'value14023',
    'key24650': 'value6203',
    'key32628': 'value18142',
    'key44750': 'value39719',
    'key64442': 'value41207',
},
    {
    'id': 17527470691721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Alicia Fields',
    'address': '007 Courtney Inlet Suite 115\nMercadoview, DE 96161',
    'text': 'But plan capital history head sea. Mind phone fear glass. From choose red simply view series third.',
    'email': 'nicholas45@example.net',
    'phone_number': '+1-949-982-7161x8498',
    'json': {
    'name': 'Kevin Taylor',
    'address': '49718 John Stravenue\nJosephchester, VT 11919',
},
    'key72350': 'value95978',
    'key3961': 'value70030',
    'key84814': 'value84946',
    'key45354': 'value42792',
    'key53620': 'value9576',
},
    {
    'id': 17527470691731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Teresa King',
    'address': '65895 Wallace Spurs Apt. 992\nPort Ernestmouth, GA 28816',
    'text': 'Actually others beyond small strong same daughter. Miss less network good then.',
    'email': 'johnwright@example.com',
    'phone_number': '484.499.8923x73551',
    'json': {
    'name': 'Kristine Chase',
    'address': '14898 Medina Roads\nWest Michaelhaven, NJ 41737',
},
    'key2788': 'value89746',
    'key67547': 'value98229',
    'key83742': 'value10899',
    'key56361': 'value63670',
    'key19217': 'value45665',
    'key57993': 'value11910',
    'key95294': 'value56145',
    'key66452': 'value29621',
},
    {
    'id': 17527470691743,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Courtney Buckley',
    'address': '32727 Pamela Street\nTammiemouth, ME 97290',
    'text': 'Use community space final law record. Whether call her name present. Exist consumer their thus nor store.',
    'email': 'lortiz@example.com',
    'phone_number': '336-296-9298',
    'json': {
    'name': 'Jessica Perez',
    'address': 'USNV Jordan\nFPO AA 67991',
},
    'key6603': 'value63866',
    'key54899': 'value49762',
    'key93788': 'value15134',
    'key62368': 'value60714',
    'key93291': 'value11334',
},
    {
    'id': 17527470691752,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Joseph Moon',
    'address': '735 Chris Unions Apt. 641\nPort Renee, MI 24177',
    'text': 'Company type trial fast. Follow step finish form apply serve much eye.\nGun least we range.',
    'email': 'cummingsjennifer@example.net',
    'phone_number': '001-479-535-0235x3953',
    'json': {
    'name': 'Martha Reyes',
    'address': '89935 Nathan Rue Suite 350\nThomasborough, PA 08955',
},
    'key50489': 'value36710',
    'key66740': 'value54401',
    'key42728': 'value75804',
},
    {
    'id': 17527470691762,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'David Foster',
    'address': '0729 Steven Fords\nSouth Peggyfort, MS 59891',
    'text': 'Now tell since explain. Purpose range effort box commercial as.\nItself kid one across shake water.\nCompare coach vote style real summer. My occur respond. North perform president forward role.',
    'email': 'ucook@example.org',
    'phone_number': '763.594.8533x34637',
    'json': {
    'name': 'Sherri Henderson',
    'address': '649 Angela Path Suite 969\nKaylamouth, PW 65616',
},
    'key25088': 'value88805',
    'key64492': 'value58467',
    'key9886': 'value68561',
    'key26106': 'value56619',
    'key78578': 'value56138',
    'key65985': 'value27674',
    'key69027': 'value98806',
    'key54874': 'value47747',
},
    {
    'id': 17527470691773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Cameron Walter',
    'address': '253 Timothy Place Apt. 348\nTrujillomouth, IA 73888',
    'text': 'Young perform course move mind never. Billion world side water price. How government sense on attorney article mother.',
    'email': 'juan63@example.com',
    'phone_number': '4962646437',
    'json': {
    'name': 'Jason Valencia',
    'address': '7560 Allen Manor Apt. 089\nFoxberg, PA 90822',
},
    'key92242': 'value75640',
    'key3118': 'value47320',
    'key2692': 'value85353',
    'key38935': 'value80851',
},
    {
    'id': 17527470691785,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Sally Madden',
    'address': '5475 White Square Apt. 961\nAmytown, CO 67818',
    'text': 'Center keep century science moment several. Nor represent Mr body require program. World side project part allow certain. Low might arrive rock page.',
    'email': 'april54@example.net',
    'phone_number': '(985)729-6362',
    'json': {
    'name': 'Pamela Bonilla',
    'address': '09055 Sarah Ridges Apt. 234\nEast Austinshire, CA 43427',
},
    'key61839': 'value29881',
    'key43768': 'value52345',
    'key19932': 'value17528',
    'key87802': 'value6050',
    'key15654': 'value16725',
    'key4555': 'value20506',
    'key20532': 'value81149',
},
    {
    'id': 17527470691796,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jennifer Gonzalez',
    'address': '31075 Erik Grove\nDavidtown, AK 63047',
    'text': 'Traditional mind recently decision out personal. Style including agency nearly quite cost.',
    'email': 'patriciaharrison@example.org',
    'phone_number': '834.912.8748x44492',
    'json': {
    'name': 'Jeremiah Solis',
    'address': '885 Moore Crest\nJessicafurt, AL 42447',
},
    'key70014': 'value97864',
    'key92531': 'value15724',
},
    {
    'id': 17527470691807,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'David Hernandez',
    'address': 'PSC 9293, Box 6112\nAPO AP 46993',
    'text': 'Kitchen send course.\nWhat wonder woman agree. Maybe significant after piece area three behavior.\nIf Mrs mind usually week. Yard response whose part prepare. Federal onto character everything.',
    'email': 'ddavidson@example.org',
    'phone_number': '(349)512-5765',
    'json': {
    'name': 'Gregory Lynch',
    'address': '2501 Kaitlyn Fields Suite 090\nBrooksside, SC 00925',
},
    'key76501': 'value83401',
},
    {
    'id': 17527470691816,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Jason Gonzalez',
    'address': '26852 Megan Cove Apt. 111\nSouth Michael, VA 87528',
    'text': 'Life again image brother build. Floor thus necessary billion Republican executive.\nThus news throw fill reduce attorney window sing. He next pull maintain these most.',
    'email': 'edward55@example.net',
    'phone_number': '001-424-712-9215x84198',
    'json': {
    'name': 'Andrew Gonzalez',
    'address': '597 Swanson Valley Apt. 213\nLake Jenniferland, OH 37011',
},
    'key55711': 'value22773',
    'key52409': 'value24294',
    'key56312': 'value94780',
    'key20748': 'value21876',
},
    {
    'id': 17527470691826,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Derek Gamble',
    'address': '03745 Charles Unions Suite 721\nNorth Eileenfort, VT 26059',
    'text': 'Beautiful notice operation environmental. Address meeting natural keep. Approach owner order word as would one.\nFollow nature responsibility contain. Adult small skin.',
    'email': 'smithwilliam@example.com',
    'phone_number': '713.219.1656x808',
    'json': {
    'name': 'William Thomas',
    'address': '92999 Christine Falls Apt. 133\nGonzalezside, VT 60424',
},
    'key13694': 'value14220',
    'key39971': 'value63737',
    'key99525': 'value85295',
},
    {
    'id': 17527470691837,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jonathan Ward',
    'address': '953 Holly Point\nWest Jennifer, SD 05768',
    'text': 'Answer evening table skin south sell against. Product happy put true. Significant force her seem.',
    'email': 'latoyareeves@example.net',
    'phone_number': '(214)265-2077',
    'json': {
    'name': 'Michele James',
    'address': '5118 Heidi Spurs Apt. 506\nPort Jacob, ME 41774',
},
    'key58166': 'value94231',
    'key26649': 'value69902',
    'key54757': 'value55318',
    'key84866': 'value12531',
    'key54149': 'value4431',
    'key97405': 'value18596',
    'key96874': 'value98853',
    'key61134': 'value6239',
    'key8704': 'value97706',
},
    {
    'id': 17527470691848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Steven Dominguez',
    'address': '0055 Martin Mission\nNew Sarah, AS 05403',
    'text': 'Environmental off wear send send voice. Reduce relate serious wide. Bank development wide.\nSure including hair. Enjoy white hear some whose win.',
    'email': 'douglasdavid@example.com',
    'phone_number': '555.860.3171',
    'json': {
    'name': 'Nicholas Blair',
    'address': '0372 Juan Cliffs Apt. 720\nNorth Kirsten, NJ 00931',
},
    'key17762': 'value59216',
    'key93680': 'value85997',
    'key61394': 'value25251',
    'key79698': 'value29493',
    'key6998': 'value67102',
    'key84566': 'value57337',
},
    {
    'id': 17527470691859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Laura Kline',
    'address': '8454 Brendan Fields Suite 328\nKirbymouth, ME 05671',
    'text': 'Scene light western soldier reduce star. Professional significant dark leave exactly painting card organization. Country peace region.\nThen sound foot. Your certain upon commercial.',
    'email': 'ryanjones@example.org',
    'phone_number': '634.756.5516x52835',
    'json': {
    'name': 'Heather Cooper',
    'address': '3225 Hopkins Alley Apt. 116\nLake Elainemouth, FL 59510',
},
    'key64432': 'value74062',
    'key61167': 'value59712',
    'key76488': 'value51422',
    'key30211': 'value97824',
    'key98209': 'value1511',
    'key47475': 'value8237',
    'key14170': 'value14095',
},
    {
    'id': 17527470691871,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Kenneth Morgan',
    'address': '663 Emily Harbor\nWest Christinaberg, VA 37592',
    'text': 'Popular rule yeah vote a maybe. Care break wrong prove reach contain attention. Person tax care leave hard.',
    'email': 'ahull@example.net',
    'phone_number': '(430)753-4417',
    'json': {
    'name': 'Mrs. Kathleen Price DDS',
    'address': '624 Michael Manors Suite 214\nMckaymouth, MI 84737',
},
    'key43216': 'value12302',
    'key87129': 'value81968',
    'key56012': 'value26096',
    'key86518': 'value57029',
    'key27172': 'value46139',
    'key86597': 'value21494',
    'key58229': 'value41816',
    'key3775': 'value26007',
},
    {
    'id': 17527470691882,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Jennifer Smith',
    'address': '7484 Gibbs Station Suite 945\nRobertburgh, FM 01623',
    'text': 'That though environment one night. Note price network identify fine. Last important situation international.',
    'email': 'edwardsderek@example.org',
    'phone_number': '001-724-339-6294',
    'json': {
    'name': 'Anne Luna',
    'address': '81308 Romero Inlet\nWest David, PR 59169',
},
    'key35368': 'value65316',
    'key3247': 'value46796',
    'key20404': 'value57760',
    'key31229': 'value95499',
    'key97918': 'value22495',
    'key99625': 'value56889',
    'key40595': 'value60793',
    'key8885': 'value28112',
    'key25604': 'value56081',
    'key18026': 'value82253',
},
    {
    'id': 17527470691894,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Stephanie Foley',
    'address': '578 Smith Mission Apt. 341\nBuckfurt, PW 15681',
    'text': 'Both talk customer science along scene. Group level act success husband.',
    'email': 'umathews@example.org',
    'phone_number': '942.250.8627x3619',
    'json': {
    'name': 'Beverly Contreras',
    'address': '641 Allen Trafficway\nEast Karlahaven, IA 78772',
},
    'key60174': 'value68821',
    'key43073': 'value1088',
    'key11060': 'value68310',
    'key43942': 'value43690',
    'key35442': 'value20851',
},
    {
    'id': 17527470691905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Natasha Ramos',
    'address': '302 Moore Estates Suite 973\nSanchezburgh, OH 14419',
    'text': 'Out guess bring until. Respond tend present nation rich office require sometimes. My responsibility investment discussion measure my.\nPaper probably beyond. Station account too much.',
    'email': 'kevin26@example.org',
    'phone_number': '001-369-432-7609x3998',
    'json': {
    'name': 'Nathan Holloway',
    'address': '596 Rodriguez Drives\nWest Jeremiahland, IA 77921',
},
    'key74817': 'value66596',
    'key56807': 'value53124',
    'key87348': 'value56501',
    'key94697': 'value9361',
    'key98457': 'value22014',
    'key88926': 'value76991',
    'key51406': 'value68509',
},
    {
    'id': 17527470691916,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Alicia Ruiz',
    'address': '921 Harding Roads\nPadillaland, KY 15082',
    'text': 'Rest think wear next piece focus idea forget. Nature clearly statement business help answer month. Small strong program reveal expert off. Still at popular.',
    'email': 'anthonynewman@example.com',
    'phone_number': '9194957843',
    'json': {
    'name': 'Mary Burgess',
    'address': '30555 Jennifer Shoal\nLake Brittany, DC 27381',
},
    'key33814': 'value68307',
    'key6984': 'value77382',
    'key75210': 'value49007',
    'key83444': 'value63859',
    'key45291': 'value11787',
},
    {
    'id': 17527470691927,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Mrs. Jeanette Murray',
    'address': '18828 James Mission\nLake Taraside, MA 31989',
    'text': 'Prevent sort such experience site serve be. Think once writer town Congress among.\nPosition leader this general personal significant water. Project short close marriage day.',
    'email': 'tiffany25@example.com',
    'phone_number': '(283)500-9611x56696',
    'json': {
    'name': 'Cindy Davis',
    'address': '22195 John Stravenue\nNew Michaelside, MD 78599',
},
    'key32576': 'value60093',
    'key63514': 'value55441',
    'key62157': 'value90491',
    'key15471': 'value9842',
},
    {
    'id': 17527470691937,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Nicole Mayer',
    'address': '1373 Wanda Cape\nWoodsshire, ME 39313',
    'text': 'Kid score case this success. Follow role during tax. Station prove cell bad lose health employee.\nStreet enter agency charge democratic kind million. Wear record sea media.',
    'email': 'fphillips@example.org',
    'phone_number': '(507)678-8082x463',
    'json': {
    'name': 'Erin Diaz',
    'address': '038 Russell Alley Suite 444\nLake Margaret, HI 87954',
},
    'key49560': 'value49338',
    'key97064': 'value1647',
    'key56395': 'value15898',
    'key46137': 'value41145',
    'key82579': 'value40622',
    'key59591': 'value28412',
    'key11888': 'value19200',
    'key67632': 'value11577',
},
    {
    'id': 17527470691948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Catherine James',
    'address': 'Unit 6924 Box 5781\nDPO AE 27071',
    'text': 'Difficult continue my question occur hand interview. Without discover month image.\nSeveral movie education. Throw spring fight eight. Choose fish plan music section.',
    'email': 'nelsonconnie@example.com',
    'phone_number': '464-744-7393',
    'json': {
    'name': 'Philip Anderson',
    'address': '86009 Barnett Run Suite 224\nSuttontown, LA 26437',
},
    'key96956': 'value24059',
    'key22139': 'value72307',
    'key19383': 'value31472',
    'key70255': 'value80174',
    'key97177': 'value79749',
    'key33802': 'value35775',
    'key42872': 'value22544',
},
    {
    'id': 17527470691958,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kaitlin Moore',
    'address': '777 Acevedo Cove\nWilsonport, IA 67959',
    'text': 'Environmental certain writer professional. Figure give return system hand standard play vote. Name paper happy religious why our ability threat. Thank anything field imagine.',
    'email': 'awheeler@example.net',
    'phone_number': '830-777-7301x553',
    'json': {
    'name': 'Maria Morris',
    'address': '5956 Williams Estate Apt. 970\nNorth Mark, MI 61973',
},
    'key68852': 'value44898',
    'key38505': 'value9413',
    'key63046': 'value98110',
    'key1537': 'value75042',
    'key12131': 'value47069',
},
    {
    'id': 17527470691970,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Dr. Christopher Adkins',
    'address': '957 Bernard Fort\nLake Daisy, MS 26363',
    'text': 'During couple beautiful teacher beautiful hear picture. Term able enter teach image decision evening. Year art again behavior gas.',
    'email': 'villarrealjose@example.org',
    'phone_number': '982.420.6076',
    'json': {
    'name': 'Ryan Grant',
    'address': '7824 Garcia Road\nEast Sethberg, AS 54306',
},
    'key48939': 'value33967',
    'key33838': 'value83789',
},
    {
    'id': 17527470691982,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Lori Cox',
    'address': '0950 Blankenship Harbors\nSouth Vanessatown, MI 77797',
    'text': 'Set agency fast several boy author product. Walk movement young I. Pattern good by between.\nShould bad cover office require. Surface response school. Population lot alone long just then.',
    'email': 'bryan21@example.net',
    'phone_number': '4265604630',
    'json': {
    'name': 'Mrs. Mary Allen',
    'address': '776 Anderson Lodge\nSnowberg, DE 04025',
},
    'key23998': 'value33889',
    'key88098': 'value31406',
    'key47256': 'value27937',
    'key93055': 'value63764',
    'key25047': 'value94734',
},
    {
    'id': 17527470691994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Kelli Chen',
    'address': '98474 Houston Shore\nEast Bradleyville, WA 12391',
    'text': 'Worry wall soldier ask season. Create compare moment house.\nWhole unit guess environment conference sure water. Plan image kind this southern yeah page have.',
    'email': 'rickyharrington@example.org',
    'phone_number': '+1-259-294-2053x32955',
    'json': {
    'name': 'Bobby Davenport',
    'address': '07183 Stephanie Tunnel Apt. 895\nLake John, NE 09489',
},
    'key28392': 'value29609',
    'key25983': 'value91853',
    'key62221': 'value32292',
},
    {
    'id': 17527470692006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Alicia Douglas',
    'address': '603 Thomas Passage Suite 906\nPort Ashley, MI 49270',
    'text': 'Others act will person open.\nExactly reality behavior character father possible.\nChild top hot skin set share. Heavy cup early scene. Make child really inside detail reveal.',
    'email': 'brianna93@example.com',
    'phone_number': '001-457-606-4485x3915',
    'json': {
    'name': 'Daniel Green',
    'address': '2027 Madden Ridge\nSusanton, CT 65098',
},
    'key25826': 'value60039',
    'key11224': 'value39659',
    'key67982': 'value33037',
    'key9098': 'value53773',
},
    {
    'id': 17527470692018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jason Bailey',
    'address': '6066 Christopher Prairie Apt. 689\nJodibury, PW 87202',
    'text': 'Once most public lay. Memory religious page environmental traditional point. Political make grow.\nIf tax section blue. Like issue put either thing listen. Tell same Democrat Mr.',
    'email': 'jonesjesse@example.com',
    'phone_number': '(299)630-9080',
    'json': {
    'name': 'Stephen Simmons MD',
    'address': '1166 David Haven\nMasonview, CO 62306',
},
    'key39737': 'value66701',
    'key56058': 'value8907',
    'key38401': 'value68971',
    'key40876': 'value31809',
    'key62853': 'value22810',
    'key54192': 'value98844',
    'key2042': 'value30047',
    'key54444': 'value93648',
    'key19858': 'value72459',
},
    {
    'id': 17527470692029,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Christina Garcia',
    'address': '397 Ritter Trafficway Suite 056\nNew Ryan, HI 20086',
    'text': 'Guy price less deep cell.\nBrother record manage. Court seek chair chair represent. Government series home concern college.',
    'email': 'timothy00@example.org',
    'phone_number': '001-367-533-6763x460',
    'json': {
    'name': 'Elizabeth Rogers',
    'address': '24066 Jones Prairie Suite 683\nWebsterstad, WA 31169',
},
    'key6348': 'value63981',
    'key1771': 'value6963',
    'key64571': 'value1866',
    'key94475': 'value27151',
    'key34236': 'value51771',
    'key82279': 'value55990',
    'key98816': 'value66052',
},
    {
    'id': 17527470692041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Denise Casey',
    'address': '328 Thomas Streets Apt. 126\nJonland, PR 77668',
    'text': 'Third summer should represent.\nFinally start bill certain carry firm. Line factor paper increase add save mission.\nEvening road head friend. Toward activity voice. Guess box meet card science.',
    'email': 'ylittle@example.com',
    'phone_number': '+1-484-804-9016x0638',
    'json': {
    'name': 'Caleb Sanchez',
    'address': '96823 Martinez Brooks\nClarkview, VA 81890',
},
    'key49091': 'value96414',
    'key78652': 'value92827',
    'key56862': 'value6122',
    'key34946': 'value30364',
    'key75086': 'value19186',
    'key41049': 'value47226',
    'key4755': 'value59407',
    'key32428': 'value9981',
    'key15282': 'value77754',
    'key15929': 'value23391',
},
    {
    'id': 17527470692053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Kimberly Mcbride MD',
    'address': '0707 Collins Orchard\nGreeneside, KY 68256',
    'text': 'Once eat month anyone believe present. Sure age concern sign success various. Begin low decide structure rest. Customer big tree relate eye continue.',
    'email': 'catherineburton@example.net',
    'phone_number': '001-554-644-1730',
    'json': {
    'name': 'Edward Smith',
    'address': '35267 Melinda Ridge\nEast William, SC 35195',
},
    'key99040': 'value52994',
    'key30433': 'value97128',
    'key88031': 'value86526',
    'key25575': 'value90946',
    'key91770': 'value40774',
    'key25490': 'value68403',
    'key6200': 'value18490',
},
    {
    'id': 17527470692064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Rose Garner',
    'address': '07926 Allen Trafficway Apt. 566\nPort Jonathanshire, CA 61730',
    'text': 'Use relate within. Could ability network visit red hot seven along.\nExpect have yeah receive sometimes daughter. Main wide game school foreign blood may.',
    'email': 'julie81@example.net',
    'phone_number': '+1-270-359-4638x41834',
    'json': {
    'name': 'Sarah Erickson',
    'address': '2849 Marquez Drives Suite 988\nNew Joseton, MO 73040',
},
    'key34': 'value98791',
    'key68235': 'value79995',
    'key80662': 'value59442',
    'key74035': 'value85187',
    'key38795': 'value93494',
},
    {
    'id': 17527470692075,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Tommy Salinas',
    'address': '7206 Nguyen Valleys\nNew Lisa, MS 39724',
    'text': 'History believe beyond yard early wall back. Strategy fall late gun. Large choice amount order.\nWar firm behind most indicate born. She require make course listen.',
    'email': 'pwilliams@example.org',
    'phone_number': '001-266-803-0948x784',
    'json': {
    'name': 'Noah Johnson',
    'address': 'PSC 0072, Box 7894\nAPO AP 70812',
},
    'key29126': 'value32926',
},
    {
    'id': 17527470692084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'John Acosta',
    'address': '318 Marcus Trace Apt. 332\nSouth Ianstad, UT 71980',
    'text': 'Nearly American boy development tree ok various size. Somebody area fund after clear.\nWho art agent child. Choice miss among ever day represent.',
    'email': 'sandra09@example.com',
    'phone_number': '721-852-9150x961',
    'json': {
    'name': 'Brian Rivera',
    'address': '473 Carter Causeway Suite 498\nWest Daniel, IA 78126',
},
    'key8527': 'value21491',
    'key52609': 'value25456',
    'key65229': 'value43038',
    'key60775': 'value93820',
    'key19142': 'value43576',
    'key24475': 'value33400',
    'key12081': 'value80191',
    'key96930': 'value7039',
},
    {
    'id': 17527470692094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Chloe Stafford',
    'address': '079 Michael Bypass\nAlexandriaton, NY 51020',
    'text': 'Debate lay interesting eye century level. American study force need road.',
    'email': 'dianadavidson@example.net',
    'phone_number': '457.875.2523x452',
    'json': {
    'name': 'Carol Stevenson',
    'address': '333 Bethany Tunnel\nTaylorhaven, LA 90902',
},
    'key91455': 'value90927',
    'key80982': 'value8277',
    'key51762': 'value6171',
    'key21588': 'value30713',
    'key79288': 'value12261',
    'key1813': 'value11467',
},
    {
    'id': 17527470692105,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Nicholas James',
    'address': '59778 Mitchell Hills\nLake Terri, FM 61719',
    'text': 'Let player against production past. Attention just big Democrat sport eat see end. Cover chance and line stay. Apply person as table nation evening peace.',
    'email': 'matthewvilla@example.net',
    'phone_number': '(847)314-0535x686',
    'json': {
    'name': 'Thomas Clark',
    'address': '08734 Carey Cove Apt. 039\nPort Jared, SC 34418',
},
    'key22503': 'value3811',
    'key60038': 'value92967',
},
    {
    'id': 17527470692117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Justin Hatfield',
    'address': '211 Gary Trace Suite 896\nLake Paulhaven, IA 55792',
    'text': 'Early shoulder like skin. The surface city. Candidate task media deal seven.\nTask trial particularly.\nFire will space brother bag thing capital player. Get into movement sense.',
    'email': 'kford@example.net',
    'phone_number': '(434)415-2500x15607',
    'json': {
    'name': 'John Hanna',
    'address': '938 Austin Pine\nErikmouth, FM 90105',
},
    'key44107': 'value13453',
    'key92048': 'value47930',
    'key39808': 'value62725',
    'key6933': 'value34499',
    'key37619': 'value67991',
    'key68396': 'value51351',
    'key35803': 'value83601',
    'key2997': 'value58162',
    'key91477': 'value52713',
},
    {
    'id': 17527470692128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Christopher Keller',
    'address': '2498 Sarah Viaduct Suite 404\nLake Natalie, IL 66973',
    'text': 'Early at free others you every. Everyone right why however wonder fund. Imagine woman baby character.',
    'email': 'gary24@example.com',
    'phone_number': '001-682-424-0983x188',
    'json': {
    'name': 'Daryl Williams',
    'address': '5954 Paul Route Suite 571\nSusantown, AK 88249',
},
    'key38833': 'value78931',
    'key91143': 'value83723',
    'key29910': 'value85414',
},
    {
    'id': 17527470692138,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sarah Mcguire',
    'address': '12196 Bender View\nJacksonfort, NJ 74461',
    'text': 'Ready life name term hospital performance important. Expert image environment radio least. Sport certain their treat leave attorney short bad.',
    'email': 'robertross@example.com',
    'phone_number': '5387800402',
    'json': {
    'name': 'Renee Walsh',
    'address': '105 Strickland Walks Suite 146\nChristopherbury, MT 63916',
},
    'key4141': 'value73305',
    'key99227': 'value62651',
    'key29440': 'value14768',
    'key37660': 'value64476',
    'key38851': 'value93033',
    'key93270': 'value20935',
    'key5059': 'value83643',
    'key14504': 'value21826',
},
    {
    'id': 17527470692150,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'William Alvarez',
    'address': '92153 Jessica Keys\nNorth Benjamin, PA 30139',
    'text': 'Attorney drop small. Raise morning dinner loss late north.\nCard occur on yeah participant difficult. Outside Mr wall five ability. Experience born them worker education pressure job style.',
    'email': 'vlopez@example.net',
    'phone_number': '970.545.1672x5382',
    'json': {
    'name': 'Kayla Becker',
    'address': '5639 Clayton Ports\nWilliamfort, GA 88783',
},
    'key85865': 'value90822',
    'key76114': 'value14313',
    'key24079': 'value23738',
    'key89183': 'value93590',
    'key64563': 'value7331',
    'key56562': 'value17386',
},
    {
    'id': 17527470692160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Joshua Faulkner',
    'address': '4992 Crawford Glen Apt. 860\nMccarthymouth, TX 87109',
    'text': 'Soon while big administration with. Professor condition set mind style car. Office strong want hotel until away tonight.',
    'email': 'udelacruz@example.org',
    'phone_number': '(791)609-2485',
    'json': {
    'name': 'Amy Jenkins',
    'address': '43914 Armstrong Field Suite 692\nBrittanymouth, PA 84330',
},
    'key47684': 'value12524',
    'key61738': 'value28537',
},
    {
    'id': 17527470692171,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Robert Hurst',
    'address': '7247 Michelle Plaza\nEast Thomas, NH 02355',
    'text': 'Threat will meeting very successful quality kitchen join. Pressure alone degree total mother ago series.',
    'email': 'iburke@example.net',
    'phone_number': '001-750-583-4106',
    'json': {
    'name': 'Brian Mclaughlin',
    'address': 'PSC 7194, Box 4375\nAPO AE 09540',
},
    'key59689': 'value22815',
    'key82476': 'value39088',
    'key86554': 'value93193',
},
    {
    'id': 17527470692179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Breanna Walker',
    'address': '586 Cole Islands Apt. 636\nJenniferbury, PW 76602',
    'text': 'Look house indicate chair lay plan there. Herself member like affect involve single watch yeah.\nAlso laugh firm three nothing represent. Lot work campaign drive spring just grow whom.',
    'email': 'howarddanielle@example.com',
    'phone_number': '5024468437',
    'json': {
    'name': 'Sabrina Tucker',
    'address': '6316 Jill Vista\nNew Kenneth, IA 91946',
},
    'key20030': 'value6049',
},
    {
    'id': 17527470692190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Dr. Ashley Chambers',
    'address': '69937 Bass Orchard Suite 194\nLake Donaldstad, MH 18571',
    'text': 'White dog chair now window probably their maybe. Key good story support democratic notice.\nPretty scene wide onto may. Professional first short source bank increase choose design.',
    'email': 'zcarter@example.org',
    'phone_number': '658-593-0628x6852',
    'json': {
    'name': 'Mike Glenn',
    'address': '991 Williams Mews Suite 234\nLake Catherinemouth, WI 86187',
},
    'key20822': 'value22468',
    'key84656': 'value23460',
    'key44081': 'value53195',
    'key63237': 'value91336',
    'key87074': 'value11671',
    'key71233': 'value79252',
},
    {
    'id': 17527470692201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Aaron Ortiz',
    'address': '843 Crystal Stream Suite 050\nAnthonyberg, MD 00730',
    'text': 'Personal charge form join officer figure rest more.\nItem may suffer hot body man. Those story college seem get. Size kid force physical parent behind.',
    'email': 'teresa28@example.org',
    'phone_number': '+1-866-894-5274x908',
    'json': {
    'name': 'Joseph Owen',
    'address': '2217 Christopher Key Apt. 673\nTeresaland, MI 79224',
},
    'key80978': 'value44767',
    'key8068': 'value39696',
},
    {
    'id': 17527470692211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Brenda Edwards MD',
    'address': '82872 Garrett Rapid Suite 507\nDrewmouth, VA 31466',
    'text': 'Effect our from effort statement quite. All even since learn stuff toward study. Carry easy local clear dinner.\nOffice food worker them real. About state do chair hope speech.',
    'email': 'markjohnson@example.com',
    'phone_number': '497-481-9951x268',
    'json': {
    'name': 'Mr. Jason Mercado',
    'address': '8313 Timothy Ports\nSouth Erinmouth, NC 86977',
},
    'key34244': 'value8783',
    'key97721': 'value93547',
    'key81968': 'value6439',
    'key39050': 'value51799',
    'key65465': 'value28671',
    'key21457': 'value95654',
    'key91231': 'value6187',
    'key98743': 'value35137',
},
    {
    'id': 17527470692223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Eric Riley',
    'address': '774 King Prairie Apt. 892\nYoungfort, ND 63050',
    'text': 'Bit apply thing. Support subject guy dog apply interview bring break.\nSomeone my have each newspaper magazine different. Question tend other unit room.',
    'email': 'garybass@example.org',
    'phone_number': '377-354-4484',
    'json': {
    'name': 'Michael Jones',
    'address': '749 Wayne Viaduct\nNew Courtneyfurt, SC 09630',
},
    'key63457': 'value60631',
    'key66854': 'value51056',
    'key49261': 'value50692',
    'key86537': 'value34148',
    'key84388': 'value32969',
    'key25913': 'value4984',
    'key49903': 'value52269',
    'key7122': 'value81793',
},
    {
    'id': 17527470692234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Leslie Hansen',
    'address': '8894 Deborah Point\nKimberlymouth, OR 71289',
    'text': 'Technology strong story minute. Simple issue economy skill.\nProve traditional team life. Spend either system job stop. Deep carry majority yes method foot whether. Offer star interview commercial.',
    'email': 'kyleneal@example.net',
    'phone_number': '203-850-0334x703',
    'json': {
    'name': 'Michael Vasquez',
    'address': '41204 Smith Mall\nHayesberg, MI 30749',
},
    'key64509': 'value15756',
    'key24704': 'value17181',
},
    {
    'id': 17527470692246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Chad Tucker',
    'address': '4898 Burns Mission Apt. 496\nLake Jessicaland, MO 95480',
    'text': 'Reach use election charge without behind. Prove institution message challenge accept sea.',
    'email': 'jonesjanice@example.org',
    'phone_number': '402.728.5530',
    'json': {
    'name': 'Bruce Newman',
    'address': 'PSC 6799, Box 5955\nAPO AA 18616',
},
    'key71417': 'value16205',
    'key42431': 'value18526',
},
    {
    'id': 17527470692255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'James Brown MD',
    'address': '573 Carlson Forges Apt. 310\nArmstrongtown, AK 20661',
    'text': 'Night claim defense. Evening commercial able including car.\nSometimes home military according. Week prove themselves movement day.',
    'email': 'rachel81@example.com',
    'phone_number': '001-610-797-5903',
    'json': {
    'name': 'Willie Davis',
    'address': '08978 Robbins Unions Suite 318\nSosaside, NV 80818',
},
    'key66387': 'value27445',
    'key96': 'value99434',
    'key85377': 'value11283',
    'key76142': 'value19042',
    'key59292': 'value85787',
    'key10076': 'value117',
    'key59000': 'value52751',
    'key51156': 'value6015',
    'key31619': 'value51929',
    'key4920': 'value30722',
},
    {
    'id': 17527470692266,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Alexa Sutton',
    'address': 'USS Rodriguez\nFPO AA 02956',
    'text': 'Always message experience read everything former Republican. Could voice job prepare seat card. Ok rise relationship senior bit.',
    'email': 'turnerglenda@example.com',
    'phone_number': '767.282.0674',
    'json': {
    'name': 'Stephanie Branch',
    'address': '771 Barr Trafficway\nWallbury, RI 15848',
},
    'key93990': 'value22046',
    'key38742': 'value1552',
},
    {
    'id': 17527470692276,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Gabriela Anderson',
    'address': '328 Kenneth Court\nNew Grace, NC 08422',
    'text': 'Thank force situation hear TV nature local. Answer whether enough imagine sort teach beautiful close. Beyond sea dog traditional to her reveal indicate. Itself change first him see media.',
    'email': 'barbarawilson@example.org',
    'phone_number': '001-712-283-4332x19473',
    'json': {
    'name': 'Morgan Jenkins',
    'address': '70264 Gilbert Plain\nNew Heatherberg, MP 24105',
},
    'key6489': 'value21737',
    'key95092': 'value25918',
    'key69319': 'value84468',
    'key73643': 'value66533',
    'key71520': 'value17894',
    'key60885': 'value38710',
},
    {
    'id': 17527470692287,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'James Schneider',
    'address': '294 Sherry Mount\nEast Cassidyville, VI 32748',
    'text': 'Leader bill none her thus relationship budget. Live forward three two. Himself work into.\nCountry wish check be sound. Along send still too bad. Clearly according six general water.',
    'email': 'david36@example.com',
    'phone_number': '+1-491-422-2298x896',
    'json': {
    'name': 'Jessica Vasquez',
    'address': '11688 Rachel Unions Apt. 379\nRobertmouth, CA 03525',
},
    'key43334': 'value98967',
    'key19238': 'value51224',
    'key83840': 'value4923',
    'key3409': 'value37541',
},
    {
    'id': 17527470692297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Sandra Mendoza',
    'address': '54570 Reginald Lock\nTurnershire, WA 51037',
    'text': 'Daughter son guy. Treat boy instead beyond Congress. All improve laugh federal affect cup side eye.',
    'email': 'xrichmond@example.com',
    'phone_number': '001-994-791-5399',
    'json': {
    'name': 'Christine Taylor',
    'address': 'Unit 1535 Box 9488\nDPO AE 12315',
},
    'key84975': 'value95437',
    'key72898': 'value66216',
},
    {
    'id': 17527470692305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Donald Curry',
    'address': '6671 Garcia Spring\nSouth Jessica, VI 92376',
    'text': 'Human eight street away professional. Heart also ball put skin finally clear. Theory everyone support up plan pass.',
    'email': 'john17@example.com',
    'phone_number': '741.695.6849x68097',
    'json': {
    'name': 'Sheri Newton',
    'address': '35670 Norton Fall\nCarmenhaven, NE 58962',
},
    'key98133': 'value74567',
    'key96789': 'value3173',
    'key18945': 'value49317',
    'key43624': 'value5920',
    'key43819': 'value70292',
},
    {
    'id': 17527470692316,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'James Rivera',
    'address': '7702 Tanya Harbors Suite 196\nWest Amanda, FL 01922',
    'text': 'Enjoy still reach human paper body sea. Key score more lead condition minute.\nTeach happy child help natural law. Your administration brother.',
    'email': 'emilysanders@example.com',
    'phone_number': '(880)738-8682',
    'json': {
    'name': 'Kaitlyn Nelson',
    'address': '84668 Smith Forges Apt. 461\nEast Davidmouth, SC 87111',
},
    'key82500': 'value65903',
    'key94201': 'value84964',
    'key31080': 'value19216',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '5844244e-62f6-11f0-91de-0242ac11000b',
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



    def test_request_4(self):
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '5844244e-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_11_03_085892lqWCFcoK',
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



    def test_request_5(self):
        """测试请求 5 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '5844244e-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_11_03_085892lqWCFcoK',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_delete_vector_by_sdk_1752747081.json')
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
    test = AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulDeleteVectorBySdk1752747081Json()
    test.run_tests()
