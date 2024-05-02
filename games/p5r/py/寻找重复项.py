import json

# 读取JSON文件的函数
def read_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 检测重复的技能名称
def detect_duplicates(data):
    skill_count = {}
    # 计算每个技能名称出现的次数
    for item in data:
        skill_name = item['技能名称']
        if skill_name in skill_count:
            skill_count[skill_name] += 1
        else:
            skill_count[skill_name] = 1

    # 找出并返回重复的技能名称
    duplicates = {skill: count for skill, count in skill_count.items() if count > 1}
    return duplicates

# 主要处理逻辑
def process_json(file_path):
    # 读取JSON数据
    data = read_json(file_path)
    # 检测重复的技能名称
    duplicates = detect_duplicates(data)
    
    # 如果有重复项，打印出来
    if duplicates:
        print("发现重复的技能名称及其出现次数：")
        for skill, count in duplicates.items():
            print(f"技能名称：{skill}, 出现次数：{count}")
    else:
        print("没有发现重复的技能名称。")

# 指定文件路径
file_path = 'Sheet1_output.json'

# 执行函数
process_json(file_path)