/* Dashboard filtering, sorting, search, and metric switching.
 *
 * Every cell carries all three metrics as data attributes; switching the metric
 * only rewrites chip text and colour, so no round trip to the server is needed.
 */

document.addEventListener('DOMContentLoaded', function() {
    const modelScopeSelect = document.getElementById('modelScope');
    const benchmarkTierFilter = document.getElementById('benchmarkTierFilter');
    const categorySelect = document.getElementById('categoryFilter');
    const searchBox = document.getElementById('searchBox');
    const benchmarkSortSelect = document.getElementById('benchmarkSort');
    const metricSwitch = document.getElementById('metricSwitch');
    const resultsTable = document.getElementById('resultsTable');
    const noResults = document.getElementById('noResults');
    const visibleCount = document.getElementById('visibleCount');

    const STORAGE_KEY = 'benchDashboardPrefs';

    /* Mirrors get_score_color() in server/analysis.py - keep in sync. */
    const SCORE_COLORS = [
        { min: 90, color: '#1b5e20' },
        { min: 75, color: '#4caf50' },
        { min: 50, color: '#ff9800' },
        { min: 25, color: '#f44336' },
        { min: -Infinity, color: '#b71c1c' }
    ];

    /* Used for latency and cost, which have no absolute scale: cells are ranked
     * within their row and coloured best-to-worst. */
    const RANK_COLORS = ['#1b5e20', '#4caf50', '#ff9800', '#f44336', '#b71c1c'];

    let activeMetric = 'score';

    function scoreColor(value) {
        for (const band of SCORE_COLORS) {
            if (value >= band.min) return band.color;
        }
        return RANK_COLORS[RANK_COLORS.length - 1];
    }

    function formatMetric(metric, value) {
        if (metric === 'score') return String(Math.round(value));
        if (metric === 'latency') {
            return value >= 10000 ? (value / 1000).toFixed(1) + 's' : Math.round(value) + 'ms';
        }
        return Math.round(value) + 'µ$';
    }

    function cellValue(chip, metric) {
        const raw = chip.dataset[metric];
        const parsed = parseFloat(raw);
        return isNaN(parsed) ? null : parsed;
    }

    function isVisible(el) {
        return el.style.display !== 'none';
    }

    function visibleChips(row) {
        return Array.from(row.querySelectorAll('td.model-col'))
            .filter(isVisible)
            .map(cell => cell.querySelector('.metric-chip'))
            .filter(chip => chip !== null);
    }

    function rowMetricValues(row, metric) {
        return visibleChips(row)
            .map(chip => cellValue(chip, metric))
            .filter(value => value !== null);
    }

    function mean(values) {
        if (!values.length) return null;
        return values.reduce((a, b) => a + b, 0) / values.length;
    }

    function medianOf(values) {
        if (!values.length) return null;
        const sorted = values.slice().sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    }

    /* Aggregate a metric the way the server does: mean for score and cost,
     * median for latency. */
    function aggregate(values, metric) {
        return metric === 'latency' ? medianOf(values) : mean(values);
    }

    /* Rank-based colouring: split the row's values into as many buckets as we
     * have colours, best value first. Lower is better for latency and cost. */
    function rankColors(values) {
        const unique = Array.from(new Set(values)).sort((a, b) => a - b);
        const colorFor = new Map();
        unique.forEach((value, index) => {
            const bucket = unique.length === 1
                ? 0
                : Math.round((index / (unique.length - 1)) * (RANK_COLORS.length - 1));
            colorFor.set(value, RANK_COLORS[bucket]);
        });
        return colorFor;
    }

    function paintRow(row, metric) {
        const chips = visibleChips(row);
        let colorFor = null;
        if (metric !== 'score') {
            colorFor = rankColors(chips
                .map(chip => cellValue(chip, metric))
                .filter(value => value !== null));
        }

        chips.forEach(chip => {
            const value = cellValue(chip, metric);
            const label = chip.querySelector('.chip-value');
            if (value === null) {
                if (label) label.textContent = '?';
                chip.style.backgroundColor = '#adb5bd';
                return;
            }
            if (label) label.textContent = formatMetric(metric, value);
            chip.style.backgroundColor = metric === 'score'
                ? scoreColor(value)
                : colorFor.get(value);
        });

        const summaryCell = row.querySelector('.col-summary .summary-value');
        if (summaryCell) {
            const rowAggregate = aggregate(rowMetricValues(row, metric), metric);
            summaryCell.textContent = rowAggregate === null ? '–' : formatMetric(metric, rowAggregate);
        }
    }

    function paintColumnSummaries(metric) {
        const headers = Array.from(resultsTable.querySelectorAll('thead th.model-col'));
        headers.forEach((header, columnIndex) => {
            const summary = header.querySelector('.summary-value');
            if (!summary || !isVisible(header)) return;

            const values = [];
            resultsTable.querySelectorAll('tbody .benchmark-row').forEach(row => {
                if (!isVisible(row)) return;
                const cells = row.querySelectorAll('td.model-col');
                const cell = cells[columnIndex];
                if (!cell) return;
                const chip = cell.querySelector('.metric-chip');
                if (!chip) return;
                const value = cellValue(chip, metric);
                if (value !== null) values.push(value);
            });

            /* The benchmark count goes in the tooltip rather than the visible
             * text - it is the widest part of the label and would set the
             * column width for a cell that only needs to hold a chip. */
            const columnAggregate = aggregate(values, metric);
            summary.textContent = columnAggregate === null
                ? '–'
                : formatMetric(metric, columnAggregate);
            summary.title = values.length + ' benchmark' + (values.length === 1 ? '' : 's');
        });
    }

    function applyMetric() {
        resultsTable.querySelectorAll('tbody .benchmark-row').forEach(row => {
            if (isVisible(row)) paintRow(row, activeMetric);
        });
        paintColumnSummaries(activeMetric);
    }

    function getModelScopeConfig() {
        const selectedScope = modelScopeSelect ? modelScopeSelect.value : 'all';

        if (selectedScope === 'remote') {
            return {
                modelPredicate: (modelType) => modelType === 'remote',
                benchmarkPredicate: () => true,
                forceBenchmarkTier: null,
            };
        }

        if (selectedScope === 'local-level1') {
            return {
                modelPredicate: (modelType, modelLevel) => modelType === 'local' && modelLevel === '1',
                benchmarkPredicate: (benchmarkTier) => benchmarkTier === '1',
                forceBenchmarkTier: '1',
            };
        }

        if (selectedScope === 'local-level2plus') {
            return {
                modelPredicate: (modelType, modelLevel) => modelType === 'local' && modelLevel !== '1',
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

    function sortRows() {
        const sortVal = benchmarkSortSelect ? benchmarkSortSelect.value : 'key-asc';
        const tbody = resultsTable.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('.benchmark-row'));
        /* Lower is better for latency and cost, so "best first" flips. */
        const lowerIsBetter = activeMetric !== 'score';

        rows.sort(function(a, b) {
            const keyA = (a.dataset.benchmarkKey || '').toLowerCase();
            const keyB = (b.dataset.benchmarkKey || '').toLowerCase();
            const nameA = (a.dataset.benchmarkName || '').toLowerCase();
            const nameB = (b.dataset.benchmarkName || '').toLowerCase();

            if (sortVal === 'key-asc') return keyA.localeCompare(keyB);
            if (sortVal === 'key-desc') return keyB.localeCompare(keyA);
            if (sortVal === 'name-asc') return nameA.localeCompare(nameB);
            if (sortVal === 'name-desc') return nameB.localeCompare(nameA);

            const aggA = aggregate(rowMetricValues(a, activeMetric), activeMetric);
            const aggB = aggregate(rowMetricValues(b, activeMetric), activeMetric);
            if (aggA === null && aggB === null) return nameA.localeCompare(nameB);
            if (aggA === null) return 1;
            if (aggB === null) return -1;

            const bestFirst = lowerIsBetter ? aggA - aggB : aggB - aggA;
            if (sortVal === 'avg-desc') return bestFirst;
            if (sortVal === 'avg-asc') return -bestFirst;
            return 0;
        });

        rows.forEach(r => tbody.appendChild(r));
    }

    function savePrefs() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                metric: activeMetric,
                scope: modelScopeSelect ? modelScopeSelect.value : null,
                tier: benchmarkTierFilter ? benchmarkTierFilter.value : null,
                category: categorySelect ? categorySelect.value : null,
                sort: benchmarkSortSelect ? benchmarkSortSelect.value : null,
            }));
        } catch (err) {
            /* Private browsing or a full quota: preferences just do not persist. */
        }
    }

    function restorePrefs() {
        let prefs = null;
        try {
            prefs = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
        } catch (err) {
            prefs = null;
        }
        if (!prefs) return;

        /* Only restore values the current page still offers - benchmarks and
         * categories come and go. */
        function restoreSelect(select, value) {
            if (!select || !value) return;
            if (Array.from(select.options).some(option => option.value === value)) {
                select.value = value;
            }
        }
        restoreSelect(modelScopeSelect, prefs.scope);
        restoreSelect(benchmarkTierFilter, prefs.tier);
        restoreSelect(categorySelect, prefs.category);
        restoreSelect(benchmarkSortSelect, prefs.sort);

        if (prefs.metric && metricSwitch) {
            const button = metricSwitch.querySelector('[data-metric="' + prefs.metric + '"]');
            if (button) {
                metricSwitch.querySelectorAll('[data-metric]').forEach(b => b.classList.remove('active'));
                button.classList.add('active');
                activeMetric = prefs.metric;
            }
        }
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
            const colModelLevel = col.dataset.modelLevel;
            const showCol = scopeConfig.modelPredicate(colModelType, colModelLevel);
            col.style.display = showCol ? '' : 'none';
        });

        const rows = resultsTable.querySelectorAll('tbody .benchmark-row');
        let shown = 0;
        rows.forEach(row => {
            const haystack = (row.dataset.search || '').toLowerCase();
            const rowCategory = row.dataset.category || '';
            const rowTier = row.dataset.tier || '';
            const matchesSearch = haystack.includes(searchTerm);
            const matchesCategory = (selectedCategory === 'all' || rowCategory === selectedCategory);
            const matchesTier = (selectedBenchmarkTier === 'all' || rowTier === selectedBenchmarkTier);
            const matchesScope = scopeConfig.benchmarkPredicate(rowTier);
            const showRow = matchesSearch && matchesCategory && matchesTier && matchesScope;
            row.style.display = showRow ? '' : 'none';
            if (showRow) shown++;
        });

        applyMetric();
        sortRows();
        noResults.style.display = shown === 0 ? 'block' : 'none';
        if (visibleCount) {
            visibleCount.textContent = shown + ' of ' + rows.length + ' benchmarks';
        }
        savePrefs();
    }

    [modelScopeSelect, benchmarkTierFilter, categorySelect, benchmarkSortSelect].forEach(control => {
        if (control) control.addEventListener('change', filterTable);
    });
    searchBox.addEventListener('input', filterTable);

    if (metricSwitch) {
        metricSwitch.addEventListener('click', function(event) {
            const button = event.target.closest('[data-metric]');
            if (!button) return;
            metricSwitch.querySelectorAll('[data-metric]').forEach(b => b.classList.remove('active'));
            button.classList.add('active');
            activeMetric = button.dataset.metric;
            filterTable();
        });
    }

    Array.from(document.querySelectorAll('[data-bs-toggle="popover"]')).forEach(
        el => new bootstrap.Popover(el)
    );

    restorePrefs();
    filterTable();
});
