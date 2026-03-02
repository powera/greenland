/* Dashboard filtering, sorting, and search logic */

document.addEventListener('DOMContentLoaded', function() {
    const modelTypeRadios = document.querySelectorAll('input[name="modelType"]');
    const categorySelect = document.getElementById('categoryFilter');
    const searchBox = document.getElementById('searchBox');
    const benchmarkSortSelect = document.getElementById('benchmarkSort');
    const viewPresetSelect = document.getElementById('viewPreset');
    const resultsTable = document.getElementById('resultsTable');
    const noResults = document.getElementById('noResults');

    function setModelTypeSelection(modelType) {
        const selectedRadio = document.querySelector(`input[name="modelType"][value="${modelType}"]`);
        if (selectedRadio) {
            selectedRadio.checked = true;
        }
    }

    function applyViewPreset() {
        const preset = viewPresetSelect ? viewPresetSelect.value : 'all';
        const rows = resultsTable.querySelectorAll('tbody .benchmark-row');

        if (preset === 'remote') {
            setModelTypeSelection('remote');
            rows.forEach(row => {
                row.dataset.presetVisible = '1';
            });
            return;
        }

        if (preset === 'local-tier1') {
            setModelTypeSelection('local');
            rows.forEach(row => {
                row.dataset.presetVisible = row.dataset.tier === '1' ? '1' : '0';
            });
            return;
        }

        if (preset === 'local-tier2plus') {
            setModelTypeSelection('local');
            rows.forEach(row => {
                row.dataset.presetVisible = row.dataset.tier !== '1' ? '1' : '0';
            });
            return;
        }

        setModelTypeSelection('all');
        rows.forEach(row => {
            row.dataset.presetVisible = '1';
        });
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
        applyViewPreset();

        const modelType = document.querySelector('input[name="modelType"]:checked').value;
        const selectedCategory = categorySelect ? categorySelect.value : 'all';
        const searchTerm = searchBox.value.toLowerCase();

        const modelCols = resultsTable.querySelectorAll('.model-col');
        modelCols.forEach(col => {
            const colModelType = col.dataset.modelType;
            const showCol = (modelType === 'all' || modelType === colModelType);
            col.style.display = showCol ? '' : 'none';
        });

        const rows = resultsTable.querySelectorAll('tbody .benchmark-row');
        let visibleCount = 0;
        rows.forEach(row => {
            const benchmarkText = row.textContent.toLowerCase();
            const rowCategory = row.dataset.category || '';
            const matchesSearch = benchmarkText.includes(searchTerm);
            const matchesCategory = (selectedCategory === 'all' || rowCategory === selectedCategory);
            const matchesPreset = row.dataset.presetVisible !== '0';
            const showRow = matchesSearch && matchesCategory && matchesPreset;
            row.style.display = showRow ? '' : 'none';
            if (showRow) visibleCount++;
        });

        sortRows();
        noResults.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    modelTypeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (viewPresetSelect && viewPresetSelect.value !== 'all') {
                viewPresetSelect.value = 'all';
            }
            filterTable();
        });
    });

    if (viewPresetSelect) {
        viewPresetSelect.addEventListener('change', filterTable);
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
