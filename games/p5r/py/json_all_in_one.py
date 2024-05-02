import json
import os

def combine_and_sort_json_files(directory):
    # 定义属性的排序顺序
    attribute_order = ["物理", "枪击", "火焰", "冰冻", "电击", "疾风", "核热", "念动", "祝福", "诅咒", "万能", "异常"]

    # 获取当前目录下所有的JSON文件
    json_files = [file for file in os.listdir(directory) if file.endswith('.json')]
    
    # 读取所有文件并收集数据
    all_data = []
    for file_name in json_files:
        file_path = os.path.join(directory, file_name)
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            all_data.extend(data)
    
    # 根据属性排序
    sorted_data = sorted(all_data, key=lambda x: attribute_order.index(x['属性']) if x['属性'] in attribute_order else len(attribute_order))

    # 将排序后的数据写入一个新的JSON文件
    with open(os.path.join(directory, 'skill.json'), 'w', encoding='utf-8') as file:
        json.dump(sorted_data, file, ensure_ascii=False, indent=4)

# 指定当前目录
combine_and_sort_json_files('.')
