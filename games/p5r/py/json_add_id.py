import json

def add_id_to_json(file_path):
    # 读取JSON文件
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 为每个对象添加ID
    for index, item in enumerate(data):
        item['ID'] = index + 1  # 从1开始编号

    # 将更新后的数据写回JSON文件
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# 指定JSON文件的路径
add_id_to_json('p5r_skills.json')
