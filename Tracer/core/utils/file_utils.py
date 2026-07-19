import json
import csv
import shutil
import os
import chardet
from pathlib import Path
from typing import List, Dict, Union, Any

def ensure_dir(path: Union[str, Path]):
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)

def load_json(path: Union[str, Path]) ->  Union[Dict, List]:
    """读取 JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data: Any, path: Union[str, Path], indent: int = 2):
    """保存数据为 JSON"""
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

def detect_encoding(file_path: Union[str, Path]) -> str:
    """检测文件编码"""
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000) # 只读取前10k字节进行检测
    result = chardet.detect(raw_data)
    return result['encoding'] or 'utf-8'

def load_csv_as_dict(path: Union[str, Path]) -> List[Dict]:
    """读取 CSV 为字典列表，自动处理编码"""
    if not os.path.exists(path):
        return []
    
    encoding = detect_encoding(path)
    with open(path, mode="r", encoding=encoding, errors="ignore") as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_csv(data: List[Dict], path: Union[str, Path], fieldnames: List[str] = None):
    """保存字典列表为 CSV"""
    if not data:
        return
    
    ensure_dir(os.path.dirname(path))
    
    if not fieldnames:
        fieldnames = list(data[0].keys())
        
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

def safe_move_file(src: Union[str, Path], dst_dir: Union[str, Path], overwrite: bool = True):
    """
    安全移动文件（从 classify_accounts2.py 移植并优化）
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    ensure_dir(dst_dir)
    
    if not src.exists():
        return False
        
    # 构造目标文件名：保持原文件夹层级结构或简单文件名
    # 这里保持原逻辑：使用上一级目录名作为文件名
    # 例如: .../0x123/AccountTransferItem.csv -> dst_dir/0x123.csv
    parent_dir_name = src.parent.name
    ext = src.suffix
    new_filename = f"{parent_dir_name}{ext}"
    dst = dst_dir / new_filename
    
    if dst.exists():
        if overwrite:
            os.remove(dst)
        else:
            # 重命名逻辑: 0x123_1.csv
            base = dst.stem
            counter = 1
            while dst.exists():
                dst = dst_dir / f"{base}_{counter}{ext}"
                counter += 1
                
    shutil.copy2(src, dst)
    return True