/* Dashboard filtering, sorting, and search logic */

document.addEventListener('DOMContentLoaded', function() {
    const modelScopeSelect = document.getElementById('modelScope');
    const benchmarkTierFilter = document.getElementById('benchmarkTierFilter');
    const categorySelect = document.getElementById('categoryFilter');
    const searchBox = document.getElementById('searchBox');
    const benchmarkSortSelect = document.getElementById('benchmarkSort');
    const resultsTable = document.getElementById('resultsTable');
    const noResults = document.getElementById('noResults');

    function getModelScopeConfig() {
        const selectedScope = modelScopeSelect ? modelScopeSelect.value : 'all';

        if (selectedScope === 'all') {
            return {
                modelPredicate: () => true,
                benchmarkPredicate: () => true,
                forceBenchmarkTier: null,
            };
        }

        if (selectedScope === 'remote') {
            return {
                modelPredicate: (modelType) => modelType === 'remote',
                benchmarkPredicate: () => true,
                forceBenchmarkTier: null,
            };
        }

        if (selectedScope === 'local-tier1') {
            return {
                modelPredicate: (modelType, modelTier) => modelType === 'local' && modelTier === '1',
                benchmarkPredicate: (benchmarkTier) => benchmarkTier === '1',
                forceBenchmarkTier: '1',
            };
        }

        if (selectedScope === 'local-tier2') {
            return {
                modelPredicate: (modelType, modelTier) => modelType === 'local' && modelTier !== '1',
                benchmarkPredicate: () => true,
                forceBenchmarkTier: null,
            };
        }

        return {
            modelPredicate: () => true,
            benchmarkPredicate: () => true,
            forceBenchmarkTier: null,
        };
    }

    function getVisibleScores(row) {
        const scores = [];
        const cells = row.querySelectorAll('td.model-col');
        cells.forEach(cell => {
            if (cell.style.display === 'none') return;
            const badge = cell.querySelector('.score-badge');
            if (badge) {
                const val = parseInt(badge.textContent.trim(), 10);
                if (!isNaN(val)) scores.push(val);
            }
        });
        return scores;
    }

    function avgOrNull(scores) {
        if (!scores.length) return null;
        return scores.reduce((a, b) => a + b, 0) / scores.length;
    }

    function sortRows() {
        const sortVal = benchmarkSortSelect ? benchmarkSortSelect.value : 'key-asc';
        const tbody = resultsTable.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('.benchmark-row'));

        rows.sort(function(a, b) {
            const keyA = (a.dataset.benchmarkKey || '').toLowerCase();
            const keyB = (b.dataset.benchmarkKey || '').toLowerCase();
            const nameA = (a.dataset.benchmarkName || '').toLowerCase();
            const nameB = (b.dataset.benchmarkName || '').toLowerCase();

            if (sortVal === 'key-asc') return keyA.localeCompare(keyB);
            if (sortVal === 'key-desc') return keyB.localeCompare(keyA);
            if (sortVal === 'name-asc') return nameA.localeCompare(nameB);
            if (sortVal === 'name-desc') return nameB.localeCompare(nameA);

            const avgA = avgOrNull(getVisibleScores(a));
            const avgB = avgOrNull(getVisibleScores(b));
            if (avgA === null && avgB === null) return nameA.localeCompare(nameB);
            if (avgA === null) return 1;
            if (avgB === null) return -1;
            if (sortVal === 'avg-desc') return avgB - avgA;
            if (sortVal === 'avg-asc') return avgA - avgB;
            return 0;
        });

        rows.forEach(r => tbody.appendChild(r));
    }

    function filterTable() {
        const scopeConfig = getModelScopeConfig();
        const selectedCategory = categorySelect ? categorySelect.value : 'all';
        const selectedBenchmarkTier = scopeConfig.forceBenchmarkTier || (benchmarkTierFilter ? benchmarkTierFilter.value : 'all');
        const searchTerm = searchBox.value.toLowerCase();

        if (benchmarkTierFilter) {
            benchmarkTierFilter.value = selectedBenchmarkTier;
            benchmarkTierFilter.disabled = scopeConfig.forceBenchmarkTier !== null;
        }

        const modelCols = resultsTable.querySelectorAll('.model-col');
        modelCols.forEach(col => {
            const colModelType = col.dataset.modelType;
            const colModelTier = col.dataset.modelTier;
            const showCol = scopeConfig.modelPredicate(colModelType, colModelTier);
            col.style.display = showCol ? '' : 'none';
        });

        const rows = resultsTable.querySelectorAll('tbody .benchmark-row');
        let visibleCount = 0;
        rows.forEach(row => {
            const benchmarkText = row.textContent.toLowerCase();
            const rowCategory = row.dataset.category || '';
            const rowTier = row.dataset.tier || '';
            const matchesSearch = benchmarkText.includes(searchTerm);
            const matchesCategory = (selectedCategory === 'all' || rowCategory === selectedCategory);
            const matchesTier = (selectedBenchmarkTier === 'all' || rowTier === selectedBenchmarkTier);
            const matchesScope = scopeConfig.benchmarkPredicate(rowTier);
            const showRow = matchesSearch && matchesCategory && matchesTier && matchesScope;
            row.style.display = showRow ? '' : 'none';
            if (showRow) visibleCount++;
        });

        sortRows();
        noResults.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    if (modelScopeSelect) {
        modelScopeSelect.addEventListener('change', filterTable);
    }

    if (benchmarkTierFilter) {
        benchmarkTierFilter.addEventListener('change', filterTable);
    }

    if (categorySelect) {
        categorySelect.addEventListener('change', filterTable);
    }

    searchBox.addEventListener('input', filterTable);

    if (benchmarkSortSelect) {
        benchmarkSortSelect.addEventListener('change', filterTable);
    }

    filterTable();
});
