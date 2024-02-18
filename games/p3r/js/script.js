let currentSortColumn = null;
let currentSortOrder = 'desc';

function sortTable(columnIndex) {
    const table = document.getElementById("excelTable");
    const rows = Array.from(table.rows).slice(1); // 获取表格行，排除表头
    const isNumericSort = !isNaN(rows[0].cells[columnIndex].innerText); // 检查是否为数字排序

    // 更新当前排序列和顺序
    if (currentSortColumn === columnIndex) {
        currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = columnIndex;
        currentSortOrder = 'desc';
    }

    // 排序逻辑
    rows.sort((a, b) => {
        const aValue = isNumericSort ? parseFloat(a.cells[columnIndex].innerText) : a.cells[columnIndex].innerText.toLowerCase();
        const bValue = isNumericSort ? parseFloat(b.cells[columnIndex].innerText) : b.cells[columnIndex].innerText.toLowerCase();

        if (aValue < bValue) {
            return currentSortOrder === 'asc' ? -1 : 1;
        }
        if (aValue > bValue) {
            return currentSortOrder === 'asc' ? 1 : -1;
        }

        // 当主要排序列的值相等时，根据第一列的值进行排序
        const aSecondaryValue = parseFloat(a.cells[0].innerText);
        const bSecondaryValue = parseFloat(b.cells[0].innerText);
        return aSecondaryValue - bSecondaryValue;
    });

    // 更新表格
    rows.forEach(row => table.appendChild(row));

    // 更新箭头方向
    updateSortArrows();
}

function updateSortArrows() {
    document.querySelectorAll('.sortable .sort-arrow').forEach((arrow, index) => {
        if (index === currentSortColumn) {
            arrow.textContent = currentSortOrder === 'asc' ? '▲' : '▼';
        } else {
            arrow.textContent = '▲▼';
        }
    });
}

// 初始化箭头状态
updateSortArrows();
