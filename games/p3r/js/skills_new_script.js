document.addEventListener('DOMContentLoaded', function() {
    // 从 JSON 文件加载数据
    fetch('./json/all_skill_data.json')
    .then(response => response.json())
    .then(data => {
        fillTable(data);
        initSortListeners(data);
    })
    .catch(error => console.error('Error loading JSON data:', error));

    // 填充表格函数
    function fillTable(data) {
        var tableBody = document.querySelector('#dataTable tbody');
        tableBody.innerHTML = ''; // 清空现有内容
        data.forEach(item => {
            var row = document.createElement('tr');
            Object.values(item).forEach(value => {
                var cell = document.createElement('td');
                cell.textContent = value;
                row.appendChild(cell);
            });
            tableBody.appendChild(row);
        });
    }

    // 初始化排序监听器
    function initSortListeners(jsonData) {
        var sortableHeaders = document.querySelectorAll('.sortable');
        sortableHeaders.forEach((header, index) => {
            header.addEventListener('click', () => {
                // 获取当前列是否已经按升序排序
                const isAscending = header.classList.toggle('asc', !header.classList.contains('asc'));
                // 获取对应列的键名
                const keyName = header.getAttribute('data-sort-index');
                sortTable(jsonData, keyName, isAscending);
                // 更新列背景色
                updateColumnBackground(index + 1);
            });
        });
    }

    // 更新排序列背景色
    function updateColumnBackground(columnIndex) {
        document.querySelectorAll('#dataTable tr td').forEach(td => td.style.backgroundColor = '');
        document.querySelectorAll(`#dataTable tr td:nth-child(${columnIndex})`).forEach(td => td.style.backgroundColor = '#f0f0f0');
    }

    // 排序表格
    function sortTable(data, sortBy, ascending) {
        data.sort((a, b) => {
            let valueA = a[sortBy];
            let valueB = b[sortBy];
            // 尝试将值转换为数字进行比较
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
        fillTable(data);
    }
});
