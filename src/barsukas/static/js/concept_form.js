(function () {
    const qidInput = document.getElementById('wikidata_qid');
    const preview = document.getElementById('wikidata-preview');
    if (!qidInput || !preview) {
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

            fetch(previewUrl + '?qid=' + encodeURIComponent(qid), {
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
                        setPreview(
                            'Wikidata match: ' + data.title + (data.summary ? ' — ' + data.summary : ''),
                            'form-text text-success'
                        );
                    } else {
                        setPreview('No Wikidata match found for ' + qid + '.', 'form-text text-warning');
                    }
                })
                .catch(function () {
                    if (qidInput.value.trim().toUpperCase() === qid) {
                        setPreview('Could not preview ' + qid + '; creation can still try resolving it.', 'form-text text-warning');
                    }
                });
        }, 600);
    });
})();
