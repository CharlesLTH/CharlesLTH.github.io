import json

def update_json_data(file_path):
    # 读取JSON数据
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 确保每一组数据的键都齐全
    all_keys = set().union(*(d.keys() for d in data))
    for entry in data:
        for key in all_keys:
            if key not in entry:
                entry[key] = ""

    # 更新"突变"键的内容
    english_name_to_chinese_name = {d["英文名"]: d["中文名"] for d in data}
    for entry in data:
        if entry["突变"]:
            entry["突变"] = english_name_to_chinese_name.get(entry["突变"], entry["突变"])

    # 将更新后的数据写入新的JSON文件
    with open('updated_p4g_skills.json', 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# 调用函数更新JSON数据
update_json_data('p4g_skills.json')
