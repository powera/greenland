// Simple table sorting and filtering
document.addEventListener('DOMContentLoaded', function() {
    // Table sorting
    const table = document.querySelector('.word-table');
    const headers = table.querySelectorAll('th.sortable');
    const tableBody = table.querySelector('tbody');
    const rows = tableBody.querySelectorAll('tr');
    
    // Add click event to all sortable headers
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const column = header.dataset.sort;
            const isNumeric = column === 'rank';
            
            // Check if we're sorting same column or different
            const currentSort = header.getAttribute('data-current-sort');
            const ascending = currentSort !== 'asc';
            
            // Reset all headers
            headers.forEach(h => h.removeAttribute('data-current-sort'));
            
            // Set current sort
            header.setAttribute('data-current-sort', ascending ? 'asc' : 'desc');
            
            // Convert rows to array for sorting
            const rowsArray = Array.from(rows);
            rowsArray.sort((rowA, rowB) => {
                let valueA = rowA.querySelector(`td.${column}`).textContent.trim();
                let valueB = rowB.querySelector(`td.${column}`).textContent.trim();
                
                if (isNumeric) {
                    // Handle numerical sorting (with '-' representing null)
                    valueA = valueA === '-' ? Infinity : parseInt(valueA);
                    valueB = valueB === '-' ? Infinity : parseInt(valueB);
                }
                
                // String comparison for non-numeric
                if (!isNumeric) {
                    if (valueA < valueB) return ascending ? -1 : 1;
                    if (valueA > valueB) return ascending ? 1 : -1;
                    return 0;
                }
                
                // Numeric comparison
                return ascending ? valueA - valueB : valueB - valueA;
            });
            
            // Clear and re-add rows
            tableBody.innerHTML = '';
            rowsArray.forEach(row => tableBody.appendChild(row));
        });
    });
    
    // Table filtering
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        
        rows.forEach(row => {
            const word = row.querySelector('.word').textContent.toLowerCase();
            const definition = row.querySelector('.definition').textContent.toLowerCase();
            const example = row.querySelector('.example').textContent.toLowerCase();
            
            if (word.includes(searchTerm) || definition.includes(searchTerm) || example.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });
    
    // Column visibility toggles
    const toggles = document.querySelectorAll('.field-toggles input');
    toggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const column = this.dataset.column;
            const cells = document.querySelectorAll(`.${column}`);
            
            cells.forEach(cell => {
                cell.style.display = this.checked ? '' : 'none';
            });
        });
    });
});