let currentSortColumn = 0;
let currentSortOrder = 'asc'; // 默认从小到大排序

function sortTable(columnIndex) {
    const table = document.getElementById("excelTable");
    let rows = Array.from(table.tBodies[0].rows);

    // 如果点击了新的列进行排序或者页面刚加载，设置为升序，否则切换排序顺序
    if (currentSortColumn !== columnIndex) {
        currentSortOrder = 'asc';
    } else {
        currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
    }
    currentSortColumn = columnIndex; // 更新当前排序的列

    // 进行排序
    rows.sort((a, b) => {
        let aValue = a.cells[columnIndex].innerText.trim();
        let bValue = b.cells[columnIndex].innerText.trim();

        // 尝试转换为数字进行比较
        aValue = aValue ? parseFloat(aValue) || aValue : 0;
        bValue = bValue ? parseFloat(bValue) || bValue : 0;

        // 如果转换为数字后相等或任一值为非数字，则使用第0列作为次要排序
        if (aValue === bValue || isNaN(aValue) || isNaN(bValue)) {
            aValue = parseFloat(a.cells[0].innerText) || 0;
            bValue = parseFloat(b.cells[0].innerText) || 0;
        }

        // 排序方向
        return (aValue - bValue) * (currentSortOrder === 'asc' ? 1 : -1);
    });

    // 将排序后的行重新添加到tbody中
    rows.forEach(row => table.tBodies[0].appendChild(row));

    // 更新箭头方向
    updateSortArrows();
}

function updateSortArrows() {
    // 清除所有箭头状态
    document.querySelectorAll('.sortable .sort-arrow').forEach((arrow) => {
        arrow.textContent = '↕'; // 重置为默认双向箭头
    });

    // 更新当前排序列的箭头
    const arrows = document.querySelectorAll('.sortable .sort-arrow');
    if (arrows[currentSortColumn]) {
        arrows[currentSortColumn].textContent = currentSortOrder === 'asc' ? '↑' : '↓';
    }
}

// 页面加载完成后，按第0列升序排序
//document.addEventListener('DOMContentLoaded', () => {
//    sortTable(0);
//});
