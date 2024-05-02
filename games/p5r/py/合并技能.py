import json

def merge_skill_data(skill1, skill2):
    # 确保从至少一个字典中获取技能名称
    skill_name = skill1.get('技能名称', skill2.get('技能名称', ''))
    
    merged_skill = {'技能名称': skill_name}
    keys_to_merge = ['HP消耗量', '目标', '数值伤害', '打击次数', '命中几率', '暴击机率', '效果', '技能独有', '描述', '校正伤害', '平均伤害', 'SP消耗量']
    for key in keys_to_merge:
        merged_skill[key] = skill1.get(key, skill2.get(key, ''))
    
    merged_skill['属性1'] = skill1.get('属性', '')
    merged_skill['属性2'] = skill2.get('属性', '')
    merged_skill['对应P'] = skill2.get('对应P', '')
    
    return merged_skill

def merge_json_data(json1_path, json2_path, output_path):
    with open(json1_path, 'r', encoding='utf-8') as f1, open(json2_path, 'r', encoding='utf-8') as f2:
        skill1_data = json.load(f1)
        skill2_data = json.load(f2)
    
    merged_skills = {}
    
    # Merge skills from json1
    for skill in skill1_data:
        skill_name = skill['技能名称']
        merged_skills[skill_name] = merge_skill_data(skill, {})
    
    # Merge skills from json2
    for skill in skill2_data:
        skill_name = skill['技能名称']
        if skill_name in merged_skills:
            merged_skills[skill_name] = merge_skill_data(merged_skills[skill_name], skill)
        else:
            merged_skills[skill_name] = merge_skill_data({}, skill)
    
    # Convert merged_skills dictionary to a list
    merged_skills_list = list(merged_skills.values())
    
    # Write merged data to output json file
    with open(output_path, 'w', encoding='utf-8') as outfile:
        json.dump(merged_skills_list, outfile, ensure_ascii=False, indent=4)

# Example usage:
merge_json_data('p5r_skills.json', 'Sheet1_output.json', 'merged_skills.json')
