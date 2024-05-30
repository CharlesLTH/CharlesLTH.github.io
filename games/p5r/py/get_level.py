import json
import re

# 读取JSON文件
with open('p5r_p.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# 提取数字并添加到新键"等级"
for item in data:
    if 'LV' in item:
        match = re.search(r'\d+', item['LV'])
        if match:
            item['等级'] = int(match.group())

# 将修改后的数据写回JSON文件
with open('p5r_p_modified.json', 'w', encoding='utf-8') as file:
    json.dump(data, file, ensure_ascii=False, indent=4)

print("修改完成，结果保存在p5r_p_modified.json文件中")