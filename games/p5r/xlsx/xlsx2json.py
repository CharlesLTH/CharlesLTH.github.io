import pandas as pd

def excel_sheets_to_json(file_path):
    # 读取Excel文件
    xls = pd.ExcelFile(file_path)

    # 获取所有sheet的名字
    sheet_names = xls.sheet_names

    # 为每个sheet创建一个JSON文件
    for sheet_name in sheet_names:
        # 读取sheet
        df = pd.read_excel(xls, sheet_name=sheet_name)
        
        # 将DataFrame转换为JSON
        json_file_name = f"{sheet_name}.json"
        df.to_json(json_file_name, orient='records', force_ascii=False, indent=4)

# 指定Excel文件路径
excel_sheets_to_json('unmerged_card.xlsx')
