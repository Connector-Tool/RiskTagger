import os
import pandas as pd
import json

##给洗钱账户和正常账户添加LLM结果

# 配置路径
txt_directory = 'G:/RiskTagger/LLM_result'     # 存放 txt 文件的目录
'''
#洗钱账户
isnormal = False
label_file = 'D:/FORGE2/XBlock/reference_list/accounts-hacker.csv'          # label 文件路径
output_file = 'D:/FORGE2/XBlock/reference_list/hacker_label_enriched.csv' # 输出文件名
#正常账户
'''
isnormal = True
label_file = 'D:/FORGE2/XBlock/all_data_large/large_addr_info.csv'          # label 文件路径
output_file = 'D:/FORGE2/XBlock/reference_list/normal_label_enriched.csv' # 输出文件名
#'''
# 读取 label 文件
df_label = pd.read_csv(label_file)

# 确保 address 列为字符串类型（避免格式问题）
df_label['address'] = df_label['address'].astype(str).str.strip()
df_label['address'] = df_label['address'].astype(str).str.lower()
# 去重
df_label = df_label.drop_duplicates(subset=['address'])
df_label = df_label.reset_index(drop=True)

if isnormal:
    df_label['name_tag'] = ''
    df_label['label'] = ''

# 初始化八个新列，四个保存结果，四个保存原因
df_label['a_transaction_patterns'] = ''
df_label['evidence_a_transaction_patterns'] = ''
df_label['b_fund_flows'] = ''
df_label['evidence_b_fund_flows'] = ''
df_label['c_associated_addresses'] = ''
df_label['evidence_c_associated_addresses'] = ''
df_label['d_temporal_behavioral_signs'] = ''
df_label['evidence_d_temporal_behavioral_signs'] = ''


#如果是正常账户，需要补充label和tag
def LLM_result_read(source)->tuple[bool,str]:
    result_dir = "G:/RiskTagger/LLM_result"
    out_path = os.path.join(result_dir, source + '.txt')
    if os.path.exists(out_path):
        with open(out_path, 'r', encoding='utf-8') as f:
            response_text = f.read()
        # 只提取“明确结论：”之后的内容
            start = response_text.find("suspicion_level")
        if start == -1:
            label = "-1_unknown"
        else:
            # 截取结论后的一小段（比如100字符），避免扫描全文
            conclusion_part = response_text[start:start + 35]
            
            #print(f"conclusion_part: {conclusion_part}")
            if "High" in conclusion_part or "high" in conclusion_part:
                label = "high-ML"
            elif "Medium" in conclusion_part or "medium" in conclusion_part:
                label = "mid-ML"
            elif "Low" in conclusion_part or "low" in conclusion_part:
                label = "low-ML"
            elif "No Suspicion" in conclusion_part or "no suspicion" in conclusion_part or "No suspicion" in conclusion_part:
                label = "No Suspicion"
            else:
                label = "unknown"
            #print(f"conclusion_part: {conclusion_part}")
            #print(f"label: {label}")
        if label != "unknown" and label != "No Suspicion":
            return [True,label]
        else:
            return [False,label]
    



# 存储从 txt 文件中提取的结果
results = {}

# 遍历 txt 文件目录
for filename in os.listdir(txt_directory):
    if filename.endswith('.txt'):
        # 提取文件名中的地址（去掉 .txt）
        address = os.path.splitext(filename)[0].lower()

        filepath = os.path.join(txt_directory, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 提取四个字段的 result和evidence
            if isnormal:
                label, tag = LLM_result_read(address)
            a_result = data.get("a_transaction_patterns", {}).get("result", "")
            b_result = data.get("b_fund_flows", {}).get("result", "")
            c_result = data.get("c_associated_addresses", {}).get("result", "")
            d_result = data.get("d_temporal_behavioral_signs", {}).get("result", "")

            a_evidence = data.get("a_transaction_patterns", {}).get("evidence", "")
            b_evidence = data.get("b_fund_flows", {}).get("evidence", "")
            c_evidence = data.get("c_associated_addresses", {}).get("evidence", "")
            d_evidence = data.get("d_temporal_behavioral_signs", {}).get("evidence", "")

            # 存入字典
            results[address] = {
                # 当is normal时，补充label和tag,否则不用
                'label': label if isnormal else None,
                'name_tag': tag if isnormal else None,
                'a_transaction_patterns': a_result,
                'b_fund_flows': b_result,
                'c_associated_addresses': c_result,
                'd_temporal_behavioral_signs': d_result,
                'evidence_a_transaction_patterns': a_evidence,
                'evidence_b_fund_flows': b_evidence,
                'evidence_c_associated_addresses': c_evidence,
                'evidence_d_temporal_behavioral_signs': d_evidence
            }
        except Exception as e:
            print(f"Error reading/parsing {filename}: {e}")

# 将结果合并到 label DataFrame
for idx, row in df_label.iterrows():
    addr = row['address']
    if addr in results:
        if isnormal:
            df_label.at[idx, 'label'] = results[addr]['label']
            df_label.at[idx, 'name_tag'] = results[addr]['name_tag']
        df_label.at[idx, 'a_transaction_patterns'] = results[addr]['a_transaction_patterns']
        df_label.at[idx, 'b_fund_flows'] = results[addr]['b_fund_flows']
        df_label.at[idx, 'c_associated_addresses'] = results[addr]['c_associated_addresses']
        df_label.at[idx, 'd_temporal_behavioral_signs'] = results[addr]['d_temporal_behavioral_signs']

        df_label.at[idx, 'evidence_a_transaction_patterns'] = results[addr]['evidence_a_transaction_patterns']
        df_label.at[idx, 'evidence_b_fund_flows'] = results[addr]['evidence_b_fund_flows']
        df_label.at[idx, 'evidence_c_associated_addresses'] = results[addr]['evidence_c_associated_addresses']
        df_label.at[idx, 'evidence_d_temporal_behavioral_signs'] = results[addr]['evidence_d_temporal_behavioral_signs']

# 保存结果
df_label.to_csv(output_file, index=False)
print(f"Enriched label file saved to {output_file}")