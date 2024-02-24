let currentSortColumn = null;
let currentSortOrder = 'asc';

// Function to load the JSON data and add it to the table
function loadAndDisplaySkills(sortProperty = null, sortOrder = 'asc') {
    fetch('./json/skills.json')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            let skillsArray = Object.entries(data).map(([key, value], index) => {
                return { ...value, name: key, index: index + 1 }; // Add skill name and index
            });
            if (sortProperty) {
                skillsArray = sortSkills(skillsArray, sortProperty, sortOrder);
            }
            displaySkills(skillsArray);
        })
        .catch(error => {
            console.error('Error fetching skills:', error);
        });
}

// 显示技能到表格中
function displaySkills(skillsArray) {
    const tbody = document.getElementById('skillTable').querySelector('tbody');
    tbody.innerHTML = ''; // 清空现有的行

    skillsArray.forEach((skill, index) => {
        const row = tbody.insertRow();
        row.insertCell().textContent = skill.index; // 序号
        row.insertCell().textContent = skill.elem || ''; // 属性
        row.insertCell().textContent = skill.name; // 技能名称
        row.insertCell().textContent = skill.cost || ''; // 消耗
        row.insertCell().textContent = skill.power || ''; // 伤害倍率
        row.insertCell().textContent = skill.crit || ''; // 暴击率
        row.insertCell().textContent = skill.hit || ''; // 命中率
        row.insertCell().textContent = skill.add || ''; // 技能效果
        row.insertCell().textContent = skill.mod || ''; // 效果附加概率
        row.insertCell().textContent = skill.effect || ''; // 技能效果描述
        row.insertCell().textContent = skill.target || ''; // 对象
        row.insertCell().textContent = ''; // 来源（留空）
        row.insertCell().textContent = skill.rank || ''; // 技能等级
        row.insertCell().textContent = skill.card || ''; // 技能卡等级
    });
}

// 排序函数
function sortSkills(skillsArray, sortProperty) {
    return skillsArray.sort((a, b) => {
        const aValue = a[sortProperty] || 0;
        const bValue = b[sortProperty] || 0;
        return (aValue - bValue) * (currentSortOrder === 'asc' ? 1 : -1);
    });
}

// 当表头被点击时，调用这个函数进行排序和显示
function sortTable(sortProperty) {
    currentSortOrder = (currentSortColumn === sortProperty && currentSortOrder === 'asc') ? 'desc' : 'asc';
    currentSortColumn = sortProperty;

    fetch('./json/skills.json')
        .then(response => response.json())
        .then(data => {
            let skillsArray = Object.values(data);
            skillsArray = sortSkills(skillsArray, sortProperty);
            displaySkills(skillsArray);
        })
        .catch(error => {
            console.error('Error sorting skills:', error);
        });
}

// 页面加载时获取并显示数据
document.addEventListener('DOMContentLoaded', loadAndDisplaySkills);
