import json

# 读取JSON文件
with open('p4g_skills.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# 提取并打印所有唯一的属性值
attributes = {item['属性'] for item in data}
print("属性出现过的所有值：", attributes)