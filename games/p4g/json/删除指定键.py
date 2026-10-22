import json

def remove_keys_from_json(file_path, keys_to_remove):
    # 读取JSON数据
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 删除指定的键
    for entry in data:
        for key in keys_to_remove:
            entry.pop(key, None)

    # 将更新后的数据写入新的JSON文件
    with open('updated_p4g_skills.json', 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# 调用函数删除指定的键
remove_keys_from_json('p4g_skills.json', ['命中_2', '倍率_2', '数据'])
