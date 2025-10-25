from asyncio import sleep
import sys
sys.path.append('X')  # 改成自己ML_Detection的相关路径
from csv2json_new1 import scrapy_data
from classify_accounts2 import classify_accounts_parallel
from discover_address_token3 import accounts_bfs
import time
if __name__ == '__main__':
    eventname = 'bybit'
    
    for depth in range(0,22):
        #break
        print('##################################Processing event:', eventname, 'at depth:', depth, '\n')
        scrapy_data(eventName=eventname, dep=depth)
        #classify_accounts(eventName=eventname, depth=depth)
        # 使用并行版本，可以指定进程数
        classify_accounts_parallel(eventName=eventname, depth=depth, max_workers=8)
        accounts_bfs(eventName=eventname, depth=depth)
