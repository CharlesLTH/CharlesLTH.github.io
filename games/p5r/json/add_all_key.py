import json
import os

def complete_keys_in_json_files(directory):
    # 获取当前目录下所有的JSON文件
    json_files = [file for file in os.listdir(directory) if file.endswith('.json')]
    
    # 初始化集合用于存储所有出现的键
    all_keys = set()

    # 读取每个文件并收集所有键
    json_data = []
    for file_name in json_files:
        with open(os.path.join(directory, file_name), 'r', encoding='utf-8') as file:
            data = json.load(file)
            json_data.append((file_name, data))
            for item in data:
                all_keys.update(item.keys())

    # 确保每个JSON数据包含所有键，并填充缺失的键
    for file_name, data in json_data:
        for item in data:
            for key in all_keys:
                if key not in item:
                    item[key] = ""  # 填充缺失的键

        # 将修改后的数据写回对应的JSON文件
        with open(os.path.join(directory, file_name), 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

# 指定目录，这里使用当前目录
complete_keys_in_json_files('.')
