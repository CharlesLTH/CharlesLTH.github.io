import pandas as pd
import json

def excel_to_json(file_path, output_json):
    # 读取Excel文件
    df = pd.read_excel(file_path, header=0)

    # 预处理：移除全空的行
    df.dropna(how='all', inplace=True)

    # 重置索引，因为我们删除了一些行
    df.reset_index(drop=True, inplace=True)

    # 初始化JSON列表
    records = []

    # 记录当前处理的A列值以及累积的C列值
    current_a_value = None
    accumulated_c_values = []

    for index, row in df.iterrows():
        # 检查是否为新的A列值（即新的数据组）
        if pd.notnull(row['LV']):
            # 如果之前累积了C列的数据，先保存
            if current_a_value is not None:
                record['技能'] = '\n'.join(accumulated_c_values)
                records.append(record)

            # 重置累积的C列值
            accumulated_c_values = []

            # 创建新的数据组
            current_a_value = row['LV']
            record = {col: row[col] for col in df.columns if pd.notnull(row[col]) and col not in ['LV', '技能']}
            record['LV'] = current_a_value
            record['名称'] = row['名称']  # B列的处理逻辑和A列相同，因为它们是合并的单元格

        # 累积C列的值
        if pd.notnull(row['技能']):
            accumulated_c_values.append(str(row['技能']))

    # 确保最后一组数据也被添加到记录中
    if current_a_value is not None:
        record['技能'] = '\n'.join(accumulated_c_values)
        records.append(record)

    # 将记录写入JSON文件
    with open(output_json, 'w', encoding='utf-8') as file:
        json.dump(records, file, ensure_ascii=False, indent=4)

# 指定Excel文件路径和输出JSON文件名
excel_to_json('p_data.xlsx', 'output.json')
