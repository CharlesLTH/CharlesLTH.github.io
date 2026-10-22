import json

# 读取JSON文件的函数
def read_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 写入JSON文件的函数
def write_json(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

# 合并技能数据
def merge_skills(data):
    merged = {}
    for item in data:
        skill_name = item['技能名称']
        # 如果技能名称已经在字典中，则合并“对应P”
        if skill_name in merged:
            merged[skill_name]['对应P'] += ", " + item['对应P']
        else:
            # 否则，添加新条目
            merged[skill_name] = item
    
    # 将字典转换为列表形式
    return list(merged.values())

# 主要处理逻辑
def process_json(file_path, output_path):
    # 读取JSON数据
    data = read_json(file_path)
    # 合并技能数据
    merged_data = merge_skills(data)
    # 写入到新的JSON文件
    write_json(merged_data, output_path)

# 指定文件路径
file_path = 'Sheet1.json'
output_path = 'Sheet1_output.json'

# 执行函数
process_json(file_path, output_path)
