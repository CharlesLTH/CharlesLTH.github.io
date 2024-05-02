document.addEventListener('DOMContentLoaded', function() {
    fetch('https://raw.githubusercontent.com/CharlesLTH/CharlesLTH.github.io/main/games/p5r/json/p5r_skills.json')
    .then(response => response.json())
    .then(data => {
        // 过滤数据：只保留属性为“物理”的数据
        const filteredData = data.filter(item => item.属性 === "物理" || item.属性 === "枪击");
        // 调整消耗值
        const adjustedData = filteredData.map(item => {
            item.HP消耗量 = (item.HP消耗量 * 100).toFixed(2) + "%";
            return item;
        });
        initTable(adjustedData);
        initSortListeners(adjustedData);
    })
    .catch(error => console.error('Error loading JSON data:', error));

    function initTable(data) {
        var tableBody = document.querySelector('#dataTable tbody');
        tableBody.innerHTML = ''; // 清空现有内容
        data.forEach(item => {
            var row = document.createElement('tr');
            const headers = document.querySelectorAll('th[data-name]');
            headers.forEach(header => {
                const dataName = header.getAttribute('data-name');
                if (item.hasOwnProperty(dataName)) { // 检查 JSON 对象是否包含该属性
                    var cell = document.createElement('td');
                    // 特别处理“HP消耗量”值以保持格式不变
                    let cellValue = (dataName === "HP消耗量" && typeof item[dataName] === "number") ? item[dataName].toString() : item[dataName];
                    cell.textContent = cellValue;
                    row.appendChild(cell);
                }
            });
            tableBody.appendChild(row);
        });
    }

    function initSortListeners(data) {
        var sortableHeaders = document.querySelectorAll('th[data-name].sortable');
        sortableHeaders.forEach(header => {
            header.addEventListener('click', () => {
                const dataName = header.getAttribute('data-name'); // 获取列的 data-name 属性
                const isAscending = header.classList.toggle('asc', !header.classList.contains('asc'));
                sortTable(data, dataName, isAscending);
                updateColumnBackground(header);
            });
        });
    }

    function updateColumnBackground(header) {
        // 清除所有单元格的背景色
        document.querySelectorAll('#dataTable td').forEach(td => td.style.backgroundColor = '');
        // 找到被点击列的索引
        const columnIndex = Array.from(document.querySelectorAll('th[data-name]')).indexOf(header) + 1;
        // 为整列设置背景色
        document.querySelectorAll(`#dataTable tr td:nth-child(${columnIndex})`).forEach(td => td.style.backgroundColor = '#f0f0f0');
    }

    function sortTable(data, sortBy, ascending) {
        const sortedData = data.sort((a, b) => {
            let valueA = a[sortBy];
            let valueB = b[sortBy];
            // 处理带有“%”的情况
            valueA = (typeof valueA === "string" && valueA.endsWith("%")) ? Number(valueA.slice(0, -1)) : valueA;
            valueB = (typeof valueB === "string" && valueB.endsWith("%")) ? Number(valueB.slice(0, -1)) : valueB;
            valueA = isNaN(Number(valueA)) ? valueA : Number(valueA);
            valueB = isNaN(Number(valueB)) ? valueB : Number(valueB);

            if (valueA < valueB) {
                return ascending ? -1 : 1;
            }
            if (valueA > valueB) {
                return ascending ? 1 : -1;
            }
            return 0;
        });
        initTable(sortedData); // 使用排序后的数据重新初始化表格
    }
});
