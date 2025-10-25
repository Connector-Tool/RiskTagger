import json
import csv
import pandas as pd
import os
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm  # 添加进度条库

sys.path.append('D:/FORGE2/BlockchainSpider-master/ML-Detection/')  # 改成自己ML_Detection的相关路径
from ML_Detection import run_blockscan_spider


# 1、从报告的 JSON 文件中提取 addresses 列表，并保存为 CSV 文件
# 输入目录：D:/FORGE2/src/report/eventName/eventName_report.pdf.json
# 输出文件：D:/FORGE2/XBlock/src_addr_token/eventName_source_addr0.csv

def json_to_csv(eventName:str, dep:int=0):
    # 1. 读取 JSON 文件
    json_file_path = "D:/FORGE2/src/report/"+ eventName +"/"+ eventName + "_report.pdf.json"  # 替换为你的 JSON 文件路径
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. 提取 attacker_addresses 列表（假设 findings 是列表，可能有多个事件）
    attacker_addresses = []
    for finding in data.get("findings", []):
        attacker_addresses.extend(finding.get("attacker_addresses", []))

    # 3. 保存为 CSV 文件
    csv_file_path = "D:/FORGE2/XBlock/src_addr_token/" + eventName + "_source_addr" + str(dep) + ".csv"
    with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["address"])  # 写入表头
        for addr in attacker_addresses:
            writer.writerow([addr])

    print(f"成功提取 {len(attacker_addresses)} 个攻击者地址并保存到 {csv_file_path}")


# 2、将 csv 转换为 BlockchainSpider 可用的 json 格式
# 输入：该层待爬取的可疑的洗钱账户列表-D:/FORGE2/XBlock/src_addr_token/eventName_source_addr0.csv
# 输出：该层待爬取的可疑的洗钱账户列表json格式--D:/FORGE2/F_extract/json/eventName_source_addr0.json

def csv_to_json(csv_file_name, types, eventName:str='bybit'):
    src_addr_path = 'D:/FORGE2/XBlock/src_addr_token/'  # 存有起始地址集合的路径
    spider_path = 'D:/FORGE2/F_extract/json/'  #改成自己BlockchainSpider的相关路径
    if not os.path.exists(spider_path):
        os.makedirs(spider_path)
    csv_file = pd.read_csv(src_addr_path + csv_file_name + '.csv')
    addr_list = []
    depth = 1   # 爬取数据的层数
    output_path = 'D:/FORGE2/F_extract/data/' + eventName + '/'  # 交易数据输出路径
    #output_path = 'D:/FORGE2/BlockchainSpider-master/blockscan_data/'  # 交易数据输出路径
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    for addr in csv_file['address']:
        print(addr)
        addr_dict = {}

        addr_dict["source"] = addr
        addr_dict["types"] = types
        addr_dict["fields"] = "hash,from,to,value,timeStamp,blockNumber,tokenSymbol,contractAddress,isError," \
                              "gasPrice,gasUsed"
        addr_dict["depth"] = depth
        addr_dict["out"] = output_path

        addr_list.append(addr_dict)

    print("len(addr_list): ", len(addr_list))
    # return json.dumps(addr_list)
    with open(spider_path + csv_file_name + '.json', 'w+') as f:
        f.write(json.dumps(addr_list))

#循环爬取 多线程爬取
def loop_crawl_parallel(csv_file_name, max_workers=10):
    src_addr_path = 'D:/FORGE2/XBlock/src_addr_token/'
    spider_path = 'D:/FORGE2/F_extract/json/'
    
    if not os.path.exists(spider_path):
        os.makedirs(spider_path)
    
    csv_file = pd.read_csv(src_addr_path + csv_file_name + '.csv')
    addr_list = []
    
    # 使用线程安全的集合来跟踪已处理的地址
    processed_addrs = set()
    lock = threading.Lock()
    
    def process_address(addr):
        # 检查是否已处理
        with lock:
            if addr in processed_addrs:
                return None
            processed_addrs.add(addr)
        
        print(f"Processing: {addr}")
        try:
            result = run_blockscan_spider(addr)
            return {"source": addr, "status": "success"}
        except Exception as e:
            return {"source": addr, "status": "failed", "error": str(e)}
    
    addresses = csv_file['address'].tolist()
    total_addresses = len(addresses)
    
    print(f"开始并行爬取 {total_addresses} 个地址，使用 {max_workers} 个线程...")
    
    # 使用进度条显示进度
    with tqdm(total=total_addresses, desc="爬取进度", unit="addr") as pbar:
        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_addr = {
                executor.submit(process_address, addr): addr 
                for addr in addresses
            }
            
            # 收集结果并更新进度条
            for future in as_completed(future_to_addr):
                result = future.result()
                if result:
                    addr_list.append(result)
                pbar.update(1)  # 每完成一个任务，进度条前进1
    
    # 统计成功和失败的数量
    success_count = sum(1 for item in addr_list if item.get("status") == "success")
    failed_count = sum(1 for item in addr_list if item.get("status") == "failed")
    
    print(f"爬取完成！成功: {success_count}, 失败: {failed_count}, 总计: {len(addr_list)}")
    
    # 保存结果
    with open(spider_path + csv_file_name + '.json', 'w+') as f:
        f.write(json.dumps(addr_list))
        
def loop_crawl(csv_file_name):
    src_addr_path = 'D:/FORGE2/XBlock/src_addr_token/'  # 存有起始地址集合的路径
    spider_path = 'D:/FORGE2/F_extract/json/'  #改成自己BlockchainSpider的相关路径(可以保存该层的地址)
    if not os.path.exists(spider_path):
        os.makedirs(spider_path)
    csv_file = pd.read_csv(src_addr_path + csv_file_name + '.csv')
    addr_list = []
    
    for addr in csv_file['address']:
        print(addr)
        addr_dict = {}
        addr_dict["source"] = addr
        addr_list.append(addr_dict)
        run_blockscan_spider(addr)#调用爬虫

    print("len(addr_list): ", len(addr_list))
    # return json.dumps(addr_list)
    with open(spider_path + csv_file_name + '.json', 'w+') as f:
        f.write(json.dumps(addr_list))

#if __name__ == '__main__':
def scrapy_data(eventName:str='bybit',dep:int=0):
    #eventName = 'bybit'  # 改成事件的名称，自定义
    #dep = 0   # 当前数据的层数
    if dep == 0:
        json_to_csv(eventName, dep=dep)  # 只有dep=0时需要运行,将pdf报告中json文件中的源地址转换为csv文件

    '''新版本spider不知道是否可以直接用json，减少改动直接调用ML_Detection中的爬虫调用函数'''
    loop_crawl_parallel(eventName + '_source_addr' + str(dep))
    #csv_to_json(eventName + '_source_addr' + str(dep), types=types, eventName=eventName)
    #os.chdir('D:/FORGE2/BlockchainSpider')
    # 运行爬虫命令，file参数指定输入的json文件
    #os.system('scrapy crawl txs.eth.bfs -a file=D:/FORGE2/F_extract/json/'+eventName+'_source_addr' + str(dep) + '.json')
    #os.chdir('D:/FORGE2/F_extract')