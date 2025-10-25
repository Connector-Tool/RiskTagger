import pandas as pd
import os
from decimal import Decimal
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from tqdm import tqdm

sys.path.append('XXXX')
from ML_Detection import LLM_Addr_Detect

def safe_move(src, dst, overwrite=True, rename=False):
    """原有的安全移动文件函数"""
    src_dir = os.path.dirname(src)
    src_filename = os.path.basename(src)
    parent_dir_name = os.path.basename(src_dir)
    
    ext = os.path.splitext(src_filename)[1]
    new_filename = parent_dir_name + ext
    dst = os.path.join(dst, new_filename)
    
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    
    if os.path.exists(dst):
        if overwrite:
            os.remove(dst)
            print(f"已覆盖: {dst}")
        elif rename:
            base, ext = os.path.splitext(dst)
            counter = 1
            new_dst = dst
            while os.path.exists(new_dst):
                new_dst = f"{base}_{counter}{ext}"
                counter += 1
            dst = new_dst
        else:
            print(f"跳过: {dst} 已存在")
            return False
    
    shutil.copy2(src, dst)
    print(f"已复制: {src} -> {dst}")
    return True

def process_single_address(args):
    """
    处理单个地址的包装函数，用于多进程
    """
    addr, blockchainspider_path, depth = args
    file_name = os.path.join(addr, 'AccountTransferItem.csv')
    file_path = os.path.join(blockchainspider_path, file_name)
    
    if not os.path.exists(file_path):
        return addr, None, None, "no_file"
    
    try:
        Is_ML, label = LLM_Addr_Detect(addr)
        return addr, Is_ML, label, "success"
    except Exception as e:
        return addr, None, None, f"error: {str(e)}"

def classify_accounts_parallel(eventName: str = 'bybit', depth: int = 0, max_workers: int = None):
    """
    并行处理版本的账户分类
    
    Args:
        eventName: 事件名称
        depth: 层数
        max_workers: 最大工作进程数，默认使用CPU核心数
    """
    if max_workers is None:
        max_workers = multiprocessing.cpu_count()
    
    print(f"使用 {max_workers} 个进程并行处理")
    
    src_addr_path = 'D:/FORGE2/XBlock/src_addr_token/'
    blockchainspider_path = 'G:/RiskTagger/blockscan_data/'

    large_path = 'D:/FORGE2/XBlock/all_data_large/'
    if not os.path.exists(large_path):
        os.makedirs(large_path)
    raw_path = 'D:/FORGE2/XBlock/all_data_token/'
    if not os.path.exists(raw_path):
        os.makedirs(raw_path)
    
    # 读取现有数据
    if os.path.exists(large_path + 'large_addr_info.csv'):
        df_large_addr = pd.read_csv(large_path + 'large_addr_info.csv')
    else:
        df_large_addr = pd.DataFrame(columns=['address'])
    
    df_hacker = pd.read_csv('D:/FORGE2/XBlock/reference_list/accounts-hacker.csv')
    
    # 读取当前层的源地址
    print("Classify accounts ing...")
    df_src = pd.read_csv(src_addr_path + eventName + '_source_addr' + str(depth) + '.csv')
    addresses = list(df_src['address'])
    
    # 准备任务参数
    tasks = [(addr, blockchainspider_path, depth) for addr in addresses]
    
    results = []
    
    # 使用进程池并行处理
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_addr = {
            executor.submit(process_single_address, task): task[0] 
            for task in tasks
        }
        
        # 使用tqdm显示进度
        for future in tqdm(as_completed(future_to_addr), total=len(tasks), desc="处理地址"):
            addr = future_to_addr[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"处理地址 {addr} 时发生异常: {str(e)}")
                results.append((addr, None, None, f"exception: {str(e)}"))
    
    # 处理结果
    for addr, Is_ML, label, status in results:
        file_name = os.path.join(addr, 'AccountTransferItem.csv')
        file_path = os.path.join(blockchainspider_path, file_name)
        
        if status == "no_file":
            print(f'地址 {addr} 无文件!!!')
            continue
        
        if status != "success":
            print(f'地址 {addr} 处理失败: {status}')
            continue
        
        print(f"地址 {addr}: Is_ML={Is_ML}, label={label}")
        
        if not Is_ML:  # 判为非洗钱账户
            print(f'地址 {addr} 为正常账户')
            #safe_move(file_path, large_path, overwrite=True)
            new_row = pd.DataFrame([{'address': addr}])
            df_large_addr = pd.concat([df_large_addr, new_row], ignore_index=True)
        else:  # 判为洗钱账户
            print(f'地址 {addr} 为洗钱账户')
            #safe_move(file_path, raw_path, overwrite=True)
            new_row = pd.DataFrame([{'address': addr, 'name_tag': label + str(depth), 'label': str(Is_ML)}])
            df_hacker = pd.concat([df_hacker, new_row], ignore_index=True)
    
    # 保存结果
    df_large_addr = df_large_addr.drop_duplicates(subset=['address'], keep='last')
    df_large_addr = df_large_addr.reset_index(drop=True)
    df_large_addr.to_csv(large_path + 'large_addr_info.csv', index=None)
    
    
    df_hacker = df_hacker.drop_duplicates(subset=['address'], keep='last')
    df_hacker = df_hacker.reset_index(drop=True)
    
    with open('D:/FORGE2/XBlock/reference_list/accounts-hacker.csv', 'w', newline='', encoding='utf-8') as f:
        df_hacker.to_csv(f, index=None)
    
    print("✅ 所有账户分类完成")

if __name__ == '__main__':
    classify_accounts_parallel('bybit', 0, max_workers=4)