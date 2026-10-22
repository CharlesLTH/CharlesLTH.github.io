import json
import os

def add_attribute_to_json_files(directory):
    # 获取当前目录下所有以"技能.json"结尾的JSON文件
    json_files = [file for file in os.listdir(directory) if file.endswith('技能.json')]
    
    for file_name in json_files:
        # 从文件名中提取“属性”的值
        attribute_value = file_name[:-6]  # 移除末尾的"技能.json"，保留前面的部分
        
        # 读取JSON数据
        file_path = os.path.join(directory, file_name)
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        # 为每个数据项添加“属性”键
        for item in data:
            item['属性'] = attribute_value

        # 将修改后的数据写回JSON文件
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

# 指定当前目录
add_attribute_to_json_files('.')
