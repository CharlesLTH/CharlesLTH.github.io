import json

# The path to the original JSON file - replace this with the actual file path on your system.
input_json_file_path = 'skills.json'

# The path to the new JSON file - replace this with the desired file path on your system.
output_json_file_path = 'slash.json'

# Function to read the JSON data, filter it, and write it to a new file.
def filter_skills(input_path, output_path):
    # Read the JSON data from the file.
    with open(input_path, 'r', encoding='utf-8') as file:
        skills_data = json.load(file)
    
    # Filter the skills data to remove skills without 'elem' set to '斩'.
    filtered_skills = {name: details for name, details in skills_data.items() if details.get('elem') == '斩'}
    
    # Write the filtered data to a new file.
    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(filtered_skills, file, ensure_ascii=False, indent=4)

# Call the function to filter the skills and write to the new file.
filter_skills(input_json_file_path, output_json_file_path)
