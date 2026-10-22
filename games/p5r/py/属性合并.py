import json

def process_skill_attributes(json_path, output_path):
    with open(json_path, 'r', encoding='utf-8') as file:
        skills = json.load(file)
    
    for skill in skills:
        if skill['属性1'] != "" and skill['属性1'] is not None:
            # 删除属性2键
            skill.pop('属性2', None)
        else:
            # 将属性2的值复制到属性1
            skill['属性1'] = skill.get('属性2', '')
            # 删除属性2键
            skill.pop('属性2', None)
    
    # 保存修改后的数据
    with open(output_path, 'w', encoding='utf-8') as outfile:
        json.dump(skills, outfile, ensure_ascii=False, indent=4)

# Example usage:
process_skill_attributes('merged_skills.json', 'updated_skills.json')
