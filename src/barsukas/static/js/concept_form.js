(function () {
    const form = document.getElementById('concept-form');
    const qidInput = document.getElementById('wikidata_qid');
    const titleInput = document.getElementById('title');
    const summaryInput = document.getElementById('summary');
    const sourcesInput = document.getElementById('sources');
    const preview = document.getElementById('wikidata-preview');
    const includeRegionalWikisInput = document.getElementById('include_regional_wikis');
    const generatedSources = document.getElementById('wikidata-generated-sources');
    if (!form || !qidInput || !titleInput || !summaryInput || !sourcesInput || !preview) {
        return;
    }

    const previewUrl = qidInput.dataset.previewUrl;
    const qidPattern = /^Q[1-9][0-9]*$/i;
    let lastRequestedQid = '';
    let debounceHandle = null;

    function setPreview(message, className) {
        preview.textContent = message;
        preview.className = className;
    }

    function sourceLabels(sources) {
        if (!Array.isArray(sources)) {
            return [];
        }
        return sources.map(function (source) {
            return source.title || source.url || '';
        }).filter(function (label) {
            return label.length > 0;
        });
    }

    function renderGeneratedSources(sources) {
        if (!generatedSources) {
            return;
        }
        const labels = sourceLabels(sources);
        generatedSources.textContent = '';
        if (labels.length === 0) {
            return;
        }
        const heading = document.createElement('div');
        heading.textContent = 'Q-id generated sources that will be included automatically:';
        generatedSources.appendChild(heading);
        const list = document.createElement('ul');
        list.className = 'mb-0';
        labels.forEach(function (label) {
            const item = document.createElement('li');
            item.textContent = label;
            list.appendChild(item);
        });
        generatedSources.appendChild(list);
    }

    function hydrateFields(data) {
        if (!titleInput.value.trim()) {
            titleInput.value = data.title || '';
        }
        if (!summaryInput.value.trim()) {
            summaryInput.value = data.summary || '';
        }
        renderGeneratedSources(data.sources || []);
    }

    qidInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            qidInput.dispatchEvent(new Event('input'));
            setPreview('Looking up this Q-id; review the populated fields, then click Create & generate.', 'form-text text-muted');
        }
    });

    if (includeRegionalWikisInput) {
        includeRegionalWikisInput.addEventListener('change', function () {
            lastRequestedQid = '';
            qidInput.dispatchEvent(new Event('input'));
        });
    }

    qidInput.addEventListener('input', function () {
        const qid = qidInput.value.trim().toUpperCase();
        window.clearTimeout(debounceHandle);

        if (!qid) {
            lastRequestedQid = '';
            setPreview('', 'form-text');
            renderGeneratedSources([]);
            return;
        }

        if (!qidPattern.test(qid)) {
            setPreview('Enter a complete Wikidata Q-id such as Q42.', 'form-text text-muted');
            renderGeneratedSources([]);
            return;
        }

        debounceHandle = window.setTimeout(function () {
            if (qid === lastRequestedQid) {
                return;
            }
            lastRequestedQid = qid;
            setPreview('Looking up ' + qid + '…', 'form-text text-muted');

            const regionalParam = includeRegionalWikisInput && includeRegionalWikisInput.checked ? '&include_regional_wikis=1' : '';
            fetch(previewUrl + '?qid=' + encodeURIComponent(qid) + regionalParam, {
                headers: {Accept: 'application/json'},
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('preview failed');
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (qidInput.value.trim().toUpperCase() !== qid) {
                        return;
                    }
                    if (data.found) {
                        hydrateFields(data);
                        setPreview(
                            'Wikidata match: ' + data.title + (data.summary ? ' — ' + data.summary : '') + '. Review the fields, then click Create & generate.',
                            'form-text text-success'
                        );
                    } else {
                        setPreview('No Wikidata match found for ' + qid + '.', 'form-text text-warning');
                        renderGeneratedSources([]);
                    }
                })
                .catch(function () {
                    if (qidInput.value.trim().toUpperCase() === qid) {
                        setPreview('Could not preview ' + qid + '; creation can still try resolving it after you click Create & generate.', 'form-text text-warning');
                        renderGeneratedSources([]);
                    }
                });
        }, 600);
    });
})();
