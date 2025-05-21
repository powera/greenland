// Simple table sorting and filtering
document.addEventListener('DOMContentLoaded', function() {
    // Scroll indicator for table
    const tableSection = document.querySelector('.word-table-section');
    const scrollIndicator = document.querySelector('.scroll-indicator');
    
    function checkScroll() {
        if (tableSection) {
            // Show indicator if there's horizontal scroll available
            if (tableSection.scrollWidth > tableSection.clientWidth) {
                scrollIndicator.style.display = 'block';
                
                // Hide indicator when scrolled to the end
                if (tableSection.scrollLeft + tableSection.clientWidth >= tableSection.scrollWidth - 10) {
                    scrollIndicator.style.display = 'none';
                }
            } else {
                scrollIndicator.style.display = 'none';
            }
        }
    }
    
    // Check on load and whenever columns are toggled
    window.addEventListener('resize', checkScroll);
    tableSection.addEventListener('scroll', checkScroll);
    setTimeout(checkScroll, 500); // Initial check after page has fully rendered
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
            
            // Include translations in search
            const chinese = row.querySelector('.chinese').textContent.toLowerCase();
            const french = row.querySelector('.french').textContent.toLowerCase();
            const korean = row.querySelector('.korean').textContent.toLowerCase();
            const swahili = row.querySelector('.swahili').textContent.toLowerCase();
            const lithuanian = row.querySelector('.lithuanian').textContent.toLowerCase();
            const vietnamese = row.querySelector('.vietnamese').textContent.toLowerCase();
            
            if (word.includes(searchTerm) || 
                definition.includes(searchTerm) || 
                example.includes(searchTerm) ||
                chinese.includes(searchTerm) ||
                french.includes(searchTerm) ||
                korean.includes(searchTerm) ||
                swahili.includes(searchTerm) ||
                lithuanian.includes(searchTerm) ||
                vietnamese.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });
    
    // Column visibility toggles
    const toggles = document.querySelectorAll('.field-toggles input');
    
    // Function to update column visibility
    const updateColumnVisibility = (toggle) => {
        const column = toggle.dataset.column;
        const cells = document.querySelectorAll(`.${column}`);
        
        cells.forEach(cell => {
            cell.style.display = toggle.checked ? '' : 'none';
        });
        
        // Check if scroll indicator should be shown after column visibility changes
        setTimeout(checkScroll, 100);
    };
    
    // Initialize column visibility based on checkbox state
    toggles.forEach(toggle => {
        // Set initial visibility
        updateColumnVisibility(toggle);
        
        // Add change event listener
        toggle.addEventListener('change', function() {
            updateColumnVisibility(this);
        });
    });
});