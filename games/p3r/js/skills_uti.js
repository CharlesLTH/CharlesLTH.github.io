document.addEventListener('DOMContentLoaded', function() {
    fetch('https://raw.githubusercontent.com/CharlesLTH/CharlesLTH.github.io/main/games/p3r/json/skills.json')
    .then(response => response.json())
    .then(data => {
        const filteredData = data.filter(item => item.属性 === "辅助" || item.属性 === "恢复" || item.属性 === "异常");
        initTable(filteredData);
        initSortListeners(filteredData);
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
                    let cellValue = item[dataName];
                    // 特殊处理百分比数据
                    if (['HP', '命中率', '暴击率', '异常率1', '异常率2'].includes(dataName) && cellValue !== "") {
                        cellValue = `${Math.round(parseFloat(cellValue) * 100)}%`;
                    }
                    // 特殊处理异常数据
                    if ((dataName === '异常2' && cellValue === item['异常1']) || cellValue === "") {
                        cellValue = "";
                    }
                    // 特殊处理如果技能为"血腥蓄力"，则读取HP值而不是SP值
                    if (dataName === "SP" && item["技能"] === "血腥蓄力") {
                        cellValue = "40%";
                    }
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
