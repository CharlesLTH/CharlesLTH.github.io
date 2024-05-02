import json

# 读取JSON文件的函数
def read_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 写入JSON文件的函数
def write_json(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

# 主要处理逻辑
def compare_json_files(file1_path, file2_path, output_path):
    json1 = read_json(file1_path)
    json2 = read_json(file2_path)

    # 提取技能名称集合
    skills1 = {item['技能名称'] for item in json1}
    skills2 = {item['技能名称']: item for item in json2}

    # 结果存储
    result = []

    # 检查第二个文件的技能名称在第一个文件中是否存在
    for skill, properties in skills2.items():
        if skill not in skills1:
            result.append({'技能名称': skill, '属性': properties['属性']})

    # 写入结果到新的JSON文件
    write_json(result, output_path)

# 指定文件路径
file1_path = 'p5r_skills.json'
file2_path = 'Sheet1_output.json'
output_path = 'output.json'

# 执行函数
compare_json_files(file1_path, file2_path, output_path)
