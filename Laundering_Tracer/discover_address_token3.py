import pandas as pd
import os
from decimal import Decimal
import shutil
import chardet
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from tqdm import tqdm

###
# 输入：该层的可疑洗钱账户列表和交易记录，已知标签文件
# 参数：当前案件名称eventName，当前案件层数depth
# 输出：下一层待爬取的可疑的洗钱账户列表

event_time = 1740067200 # 2025-2-21-00:00:00 UTC 时间戳
start_time = event_time

raw_path = 'D:/FORGE2/XBlock/all_data_token/'  
large_path = 'D:/FORGE2/XBlock/all_data_large/'
src_addr_path = 'D:/FORGE2/XBlock/src_addr_token/'
filter_path = 'D:/FORGE2/XBlock/filter_labels_token/'
if not os.path.exists(filter_path):
    os.makedirs(filter_path)

ref_path = 'D:/FORGE2/XBlock/reference_list/'

# 全局变量，在进程间共享（只读）
file_0 = None
file_1 = None
file_2 = None
file_3 = None
file_3_High_Mid = None
file_3_High = None

def init_global_data():
    """初始化全局数据，在进程池创建时调用"""
    global file_0, file_1, file_2, file_3, file_3_High_Mid, file_3_High
    
    file_0 = pd.read_csv('D:/FORGE2/XBlock/all_data_large/large_addr_info.csv', encoding='utf-8')
    file_1 = pd.read_csv(ref_path + 'exchange-list.csv', encoding='utf-8')
    file_2 = pd.read_csv(ref_path + 'wallet-list.csv')
    file_3 = pd.read_csv('D:/FORGE2/XBlock/reference_list/accounts-hacker.csv')
    
    file_3_High_Mid = file_3[file_3['name_tag'].str.contains('high|mid', na=False)]
    file_3_High = file_3[file_3['name_tag'].str.contains('high', na=False)]

def detect_encoding(file_path):
    """检测文件编码格式"""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    result = chardet.detect(raw_data)
    return result['encoding']

def check_contract_address(row: pd.Series) -> bool:
    """检查合约地址是否在白名单中，若在则返回 true，反之返回 false（跳过该交易）"""
    # 白名单文件路径（包含常见合约地址）

    whitelist = {"0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
                    "0xd5F7838F5C461fefF7FE49ea5ebaF7728bB0ADfa",  # mETH
                    "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",  # stETH
                    "0xE6829d9a7eE3040e1276Fa75293Bde931859e8fA",  # cmETH  
                    "0x0000000000000000000000000000000000000000"   # 0x0 ETH
                }
    contract_address = row["contract_address"].strip().lower()
    if pd.isna(contract_address):
        return False  # 地址为空，过滤
    if contract_address and contract_address in whitelist:
        return True  # 在白名单中，保留该交易
    else:
        # print(f"过滤交易，合约地址不在白名单中: {contract_address}")
        return False  # 不在白名单中，过滤该交易
    
def wei2ether(s) -> Decimal:
    """'value'的字符串转数值"""
    length = len(s)
    t = length - 18
    if t > 0:
        s1 = ""
        s1 = s1 + s[0:t]
        s1 = s1 + "."
        s1 = s1 + s[t:]
    else:
        x = 18 - length
        s1 = "0."
        for i in range(0, x):
            s1 = s1 + "0"
        s1 = s1 + s
    return Decimal(s1)

def process_single_address(args):
    """
    处理单个地址的包装函数，用于多进程并行处理
    """
    file_name, addr, min_amount, max_addresses, top_amount_ratio = args
    
    ##### 并行在这里修改参数 #####
    min_amount=10
    max_addresses=3
    top_amount_ratio=0.05

    # 使用全局数据
    global file_0, file_1, file_2, file_3, file_3_High_Mid, file_3_High
    
    print(f"处理地址: {addr}")
    
    if not os.path.exists(raw_path + file_name):
        print(f"文件不存在: {raw_path + file_name}")
        return None
    
    try:
        tx_file = pd.read_csv(raw_path + file_name)
        # 获取满足时序递增要求的下游账户                
        tx_file = tx_file[tx_file['value'] != '0']
        print(f'{addr}: 过滤前交易数 {len(tx_file)}')
        
        heist = addr.lower()

        # 合约地址白名单筛选


        # 所有从洗钱节点往下游的节点的交易都被保留
        related = tx_file[tx_file['address_from'].str.lower() == heist]
        related = related[related.apply(check_contract_address, axis=1)]

        print(f'{addr}: 过滤前相关交易数 {len(related)}')
        
        if len(related) == 0:
            print(f'{addr}: 无相关交易')
            return None
        
        # 将value转换为数值类型用于金额筛选
        # 只提取你需要的列和行
        related = tx_file[tx_file['address_from'].str.lower() == heist]
        related['value_numeric'] = related['value'].astype(float) / (10**related['decimals'].astype(float))

        #print(f'{addr}: 交易金额 {related["value_numeric"]}')
        # === 金额筛选策略 ===
        if min_amount is not None:
            # 按最小金额阈值筛选
            related = related[related['value_numeric'] >= min_amount]
            print(f'{addr}: 金额过滤后 {len(related)} 笔交易')
        
        if top_amount_ratio < 1.0 and len(related) > 0:
            # 按金额排序，保留前N%的大额交易
            related = related.sort_values('value_numeric', ascending=False)
            keep_count = max(1, int(len(related) * top_amount_ratio))
            related = related.head(keep_count)
            print(f'{addr}: 保留前{top_amount_ratio*100}%大额交易 {len(related)} 笔')
        
        # === 地址数量限制策略 ===
        if max_addresses is not None and len(related) > 0:
            # 按地址分组，计算每个地址的总交易金额
            address_totals = related.groupby('address_to')['value_numeric'].sum().reset_index()
            address_totals = address_totals.sort_values('value_numeric', ascending=False)
            
            # 保留交易金额最大的前N个地址
            top_addresses = address_totals.head(max_addresses)['address_to'].tolist()
            related = related[related['address_to'].isin(top_addresses)]
            print(f'{addr}: 保留前{max_addresses}个地址 {len(related)} 笔交易')
        
        # 标签库过滤
        related = related[~related['address_to'].str.lower().isin(list(file_0['address'].str.lower()))]
        related = related[~related['address_to'].str.lower().isin(list(file_1['address'].str.lower()))]
        related = related[~related['address_to'].str.lower().isin(list(file_2['address'].str.lower()))]
        related = related[~related['address_to'].str.lower().isin(list(file_3['address'].str.lower()))]
        
        related = related.reset_index(drop=True)
        related['address_to'] = related['address_to'].str.lower()

        print(f'{addr}: 最终相关交易数 {len(related)}')

        if len(related) == 0:
            print(f'{addr}: 无符合条件的交易')
            return None
        
        # 生成下一层地址文件
        test_file = pd.DataFrame(data=list(set(related['address_to'])), columns=['address'])
        test_file = test_file.drop_duplicates(subset=['address'])
        test_file = test_file.reset_index(drop=True)
        test_file['name_tag'] = ''
        test_file['label'] = ''

        # 保存单个地址的结果
        test_file.to_csv(filter_path + file_name + '_address.csv', index=False)

        no_label_addr = test_file[test_file['label'] == '']['address']
        print(f'{addr}: 发现 {len(no_label_addr)} 个无标签地址')
        
        # 输出统计信息
        if len(related) > 0:
            total_amount = related['value_numeric'].sum()
            avg_amount = related['value_numeric'].mean()
            print(f'{addr}: 交易统计 - 总金额: {total_amount:.2f}, 平均金额: {avg_amount:.2f}, 交易数: {len(related)}')
        
        return no_label_addr
        
    except Exception as e:
        print(f"处理地址 {addr} 时出错: {str(e)}")
        return None

def discover_address_label_parallel(file_name, addr=None, min_amount=None, max_addresses=None, top_amount_ratio=1.0):
    """
    并行版本的地址发现函数
    """
    # 对于单个地址，直接调用处理函数
    result = process_single_address((file_name, addr, min_amount, max_addresses, top_amount_ratio))
    return result

def accounts_bfs_parallel(eventName: str = 'bybit', depth: int = 0, max_workers: int = None):
    """
    并行版本的BFS地址发现
    """
    if max_workers is None:
        max_workers = multiprocessing.cpu_count()
    
    print(f'Finding next level addresses using {max_workers} processes...')
    
    # 初始化全局数据
    init_global_data()
    
    df_src = pd.read_csv(src_addr_path + eventName + '_source_addr' + str(depth) + '.csv')
    addresses = list(df_src['address'].str.lower())
    
    # 准备任务参数
    tasks = []
    for addr in addresses:
        file_name = addr + '.csv'
        tasks.append((file_name, addr, None, 8, 0.05))  # 使用原有的参数设置
    
    next_addr_results = []
    
    # 使用进程池并行处理
    with ProcessPoolExecutor(max_workers=max_workers, initializer=init_global_data) as executor:
        # 提交所有任务
        future_to_addr = {
            executor.submit(process_single_address, task): task[1] 
            for task in tasks
        }
        
        # 显示进度
        for future in tqdm(as_completed(future_to_addr), total=len(tasks), desc="发现下一层地址"):
            addr = future_to_addr[future]
            try:
                result = future.result()
                if result is not None:
                    next_addr_results.append(result)
            except Exception as e:
                print(f"处理地址 {addr} 时发生异常: {str(e)}")
    
    # 合并所有结果
    if next_addr_results:
        next_addr_file = pd.concat(next_addr_results, ignore_index=True)
        next_addr_file = next_addr_file.drop_duplicates()
        next_addr_file = next_addr_file.reset_index(drop=True)
        next_addr_file = pd.DataFrame(next_addr_file, columns=['address'])
        
        print('len(next_addr_file)', len(next_addr_file))
        
        if len(next_addr_file) == 0:
            print('Congratulation! Finished!')
        else:
            output_path = src_addr_path + eventName + '_source_addr' + str(depth + 1) + '.csv'
            next_addr_file.to_csv(output_path, index=False)
            print(f'下一层地址已保存到: {output_path}')
    else:
        print('未发现任何下一层地址')
        next_addr_file = pd.DataFrame(columns=['address'])

def accounts_bfs(eventName: str = 'bybit', depth: int = 0):
    """
    保持原有接口的并行版本
    默认使用CPU核心数一半的进程数
    """
    max_workers = max(2, multiprocessing.cpu_count() // 2)
    return accounts_bfs_parallel(eventName, depth, max_workers)

# 保留原有的串行版本用于测试或特殊情况
def accounts_bfs_sequential(eventName: str = 'bybit', depth: int = 0):
    """
    原有的串行版本，用于测试或特殊情况
    """
    print('Finding next level addresses (sequential mode)...')
    
    init_global_data()
    
    df_src = pd.read_csv(src_addr_path + eventName + '_source_addr' + str(depth) + '.csv')
    next_addr_file = pd.DataFrame()
    
    for i in range(len(df_src)):
        addr = df_src.loc[i, 'address'].lower()
        print('---------------------------------------------------')
        next_addr = discover_address_label_parallel(addr + '.csv', addr=addr, max_addresses=15, top_amount_ratio=0.5)
        if next_addr is not None:
            next_addr_file = pd.concat([next_addr_file, next_addr], ignore_index=True)
    
    next_addr_file = next_addr_file.drop_duplicates()
    next_addr_file = next_addr_file.reset_index(drop=True)
    next_addr_file = next_addr_file.rename(columns={0: 'address'})

    print('len(next_addr_file)', len(next_addr_file))
    if len(next_addr_file) == 0:
        print('Congratulation! Finished!')
    else:
        next_addr_file.to_csv(src_addr_path + eventName + '_source_addr' + str(depth + 1) + '.csv', index=False)