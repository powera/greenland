(function () {
    const form = document.getElementById('concept-form');
    const qidInput = document.getElementById('wikidata_qid');
    const titleInput = document.getElementById('title');
    const summaryInput = document.getElementById('summary');
    const sourcesInput = document.getElementById('sources');
    const preview = document.getElementById('wikidata-preview');
    const includeRegionalWikisInput = document.getElementById('include_regional_wikis');
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

    function sourceUrls(sources) {
        if (!Array.isArray(sources)) {
            return [];
        }
        return sources.map(function (source) {
            return source.url || '';
        }).filter(function (url) {
            return url.length > 0;
        });
    }

    function mergeSourceUrls(existingText, sources) {
        const existingUrls = existingText.split('\n').map(function (line) {
            return line.trim();
        }).filter(function (line) {
            return line.length > 0;
        });
        const seenUrls = new Set(existingUrls);
        sourceUrls(sources).forEach(function (url) {
            if (!seenUrls.has(url)) {
                existingUrls.push(url);
                seenUrls.add(url);
            }
        });
        return existingUrls.join('\n');
    }

    function hydrateFields(data) {
        if (!titleInput.value.trim()) {
            titleInput.value = data.title || '';
        }
        if (!summaryInput.value.trim()) {
            summaryInput.value = data.summary || '';
        }
        sourcesInput.value = mergeSourceUrls(sourcesInput.value, data.sources || []);
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
            return;
        }

        if (!qidPattern.test(qid)) {
            setPreview('Enter a complete Wikidata Q-id such as Q42.', 'form-text text-muted');
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
                    }
                })
                .catch(function () {
                    if (qidInput.value.trim().toUpperCase() === qid) {
                        setPreview('Could not preview ' + qid + '; creation can still try resolving it after you click Create & generate.', 'form-text text-warning');
                    }
                });
        }, 600);
    });
})();
