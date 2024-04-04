import json

def reorder_keys_in_json(file_path, new_order):
    # 读取JSON数据
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 重新排序键
    reordered_data = []
    for entry in data:
        reordered_entry = {key: entry.get(key, "") for key in new_order}
        reordered_data.append(reordered_entry)

    # 将更新后的数据写入新的JSON文件
    with open('reordered_p4g_skills.json', 'w', encoding='utf-8') as file:
        json.dump(reordered_data, file, ensure_ascii=False, indent=4)

# 调用函数重新排序键
new_order = ["日文名", "英文名", "中文名", "属性", "消耗", "倍率", "命中", "暴击", "次数", "昏厥", "附加", "附加率", "目标", "效果", "英文效果", "等级", "抽卡", "技能卡", "突变", "价格"]
reorder_keys_in_json('p4g_skills.json', new_order)
