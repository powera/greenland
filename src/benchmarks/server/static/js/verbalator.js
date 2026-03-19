/* Verbalator UI logic */

document.addEventListener('DOMContentLoaded', function() {
    // Free-form query form
    var freeForm = document.getElementById('verbalator');
    if (freeForm) freeForm.addEventListener('submit', submitVerbalator);

    // Action form
    var actionForm = document.getElementById('action-form');
    if (actionForm) actionForm.addEventListener('submit', submitActions);

    // Toggle context/language rows when action checkboxes change
    var checkboxes = document.querySelectorAll('#action-checkboxes input[type="checkbox"]');
    checkboxes.forEach(function(cb) {
        cb.addEventListener('change', updateActionOptions);
    });
});

function updateActionOptions() {
    var checked = document.querySelectorAll('#action-checkboxes input[type="checkbox"]:checked');
    var needsContext = false;
    var needsLanguage = false;
    checked.forEach(function(cb) {
        if (cb.dataset.needsContext === 'true') needsContext = true;
        if (cb.dataset.needsLanguage === 'true') needsLanguage = true;
    });
    document.getElementById('context-row').style.display = needsContext ? '' : 'none';
    document.getElementById('language-row').style.display = needsLanguage ? '' : 'none';
}

/* ── Actions submission ── */

function submitActions(event) {
    event.preventDefault();
    showLoading();
    document.getElementById('action-results').innerHTML = '';
    document.getElementById('result').textContent = '';

    var form = document.getElementById('action-form');
    var formData = new FormData(form);

    var selectedActions = [];
    form.querySelectorAll('input[name="actions"]:checked').forEach(function(cb) {
        selectedActions.push(cb.value);
    });

    if (selectedActions.length === 0) {
        hideLoading();
        document.getElementById('result').textContent = 'Please select at least one action.';
        return;
    }

    var text = formData.get('text');
    var model = formData.get('model');
    var context = formData.get('context') || '';
    var targetLanguage = formData.get('target_language') || 'en';

    var pending = selectedActions.length;
    var container = document.getElementById('action-results');

    selectedActions.forEach(function(actionName) {
        var requestData = {
            action_name: actionName,
            text: text,
            model: model,
            context: context || undefined,
            target_language: targetLanguage
        };

        fetch('/verbalator/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        })
        .then(function(response) {
            if (!response.ok) return response.json().then(function(d) { throw new Error(d.error || 'Request failed'); });
            return response.json();
        })
        .then(function(data) {
            renderActionResult(container, data);
            if (data.usage) updateUsage(data.usage);
        })
        .catch(function(error) {
            renderActionError(container, actionName, error.message);
        })
        .finally(function() {
            pending--;
            if (pending <= 0) hideLoading();
        });
    });
}

function renderActionResult(container, data) {
    var card = document.createElement('div');
    var actionName = data.action || 'unknown';
    var colorClass = getColorClass(actionName);
    card.className = 'action-result-card ' + colorClass;

    var header = document.createElement('div');
    header.className = 'card-header';
    header.textContent = formatActionName(actionName);
    card.appendChild(header);

    var body = document.createElement('div');
    body.className = 'card-body';

    var result = data.result;
    if (actionName === 'decomposition') {
        body.innerHTML = renderDecomposition(result);
    } else if (actionName === 'metadata') {
        body.innerHTML = renderMetadata(result);
    } else if (actionName === 'time_analysis') {
        body.innerHTML = renderTimeAnalysis(result);
    } else if (actionName === 'response_to') {
        body.innerHTML = renderResponseTo(result);
    } else if (actionName === 'attribution') {
        body.innerHTML = renderAttribution(result);
    } else if (actionName === 'sarcasm') {
        body.innerHTML = renderSarcasm(result);
    } else if (actionName === 'pronunciation') {
        body.innerHTML = renderPronunciation(result);
    } else if (actionName === 'comprehension') {
        body.innerHTML = renderComprehension(result);
    } else {
        body.innerHTML = '<pre>' + JSON.stringify(result, null, 2) + '</pre>';
    }

    card.appendChild(body);
    container.appendChild(card);
}

function renderActionError(container, actionName, message) {
    var card = document.createElement('div');
    card.className = 'action-result-card';
    card.innerHTML = '<div class="card-header" style="background:#fce8e6;color:#c5221f;">'
        + formatActionName(actionName) + ' - Error</div>'
        + '<div class="card-body">' + escapeHtml(message) + '</div>';
    container.appendChild(card);
}

/* ── Result renderers ── */

function renderDecomposition(result) {
    if (!result || !result.languages || !result.languages[0]) return '<em>No data</em>';
    var lang = result.languages[0];
    var html = '<p><strong>Language:</strong> ' + escapeHtml(lang.language_code)
        + ' &mdash; <strong>Translation:</strong> ' + escapeHtml(lang.translation)
        + ' &mdash; <strong>Words:</strong> ' + lang.word_count + '</p>';
    html += '<table class="result-table"><thead><tr>'
        + '<th>#</th><th>Surface Form</th><th>Lemma</th><th>Role</th>'
        + '<th>English Gloss</th><th>Grammatical Form</th><th>GUID</th>'
        + '</tr></thead><tbody>';
    (lang.words || []).forEach(function(w) {
        html += '<tr>'
            + '<td>' + w.position + '</td>'
            + '<td>' + escapeHtml(w.surface_form) + '</td>'
            + '<td>' + escapeHtml(w.lemma) + '</td>'
            + '<td>' + escapeHtml(w.role) + '</td>'
            + '<td>' + escapeHtml(w.english_gloss) + '</td>'
            + '<td><code>' + escapeHtml(w.grammatical_form) + '</code></td>'
            + '<td><code>' + escapeHtml(w.lemma_guid) + '</code></td>'
            + '</tr>';
    });
    html += '</tbody></table>';
    return html;
}

function renderMetadata(r) {
    if (!r) return '<em>No data</em>';
    var rows = [
        ['Language', r.language],
        ['Dialect', r.dialect],
        ['Register', r.register],
        ['Formality', r.formality],
        ['Length Category', r.estimated_length_category],
        ['Author Type', r.author_type],
        ['Genre', r.genre],
        ['Key Topics', (r.key_topics || []).join(', ')]
    ];
    var html = '<table class="result-table"><tbody>';
    rows.forEach(function(row) {
        html += '<tr><th>' + row[0] + '</th><td>' + escapeHtml(String(row[1] || '')) + '</td></tr>';
    });
    html += '</tbody></table>';
    return html;
}

function renderTimeAnalysis(r) {
    if (!r) return '<em>No data</em>';
    var confPct = { very_low: 10, low: 30, medium: 50, high: 75, very_high: 95 };
    var pct = confPct[r.confidence] || 50;
    var color = pct >= 75 ? '#34a853' : pct >= 50 ? '#fbbc04' : '#ea4335';

    var html = '<table class="result-table"><tbody>'
        + '<tr><th>Estimated Era</th><td>' + escapeHtml(r.estimated_era || '') + '</td></tr>'
        + '<tr><th>Date Range</th><td>' + escapeHtml(r.date_range_start || '') + ' &ndash; ' + escapeHtml(r.date_range_end || '') + '</td></tr>'
        + '<tr><th>Confidence</th><td>' + escapeHtml(r.confidence || '')
        + ' <span class="confidence-meter"><span class="fill" style="width:' + pct + '%;background:' + color + '"></span></span>'
        + '</td></tr>'
        + '<tr><th>Reasoning</th><td>' + escapeHtml(r.reasoning || '') + '</td></tr>'
        + '</tbody></table>';

    if (r.temporal_clues && r.temporal_clues.length) {
        html += '<h6 class="mt-2">Temporal Clues</h6><ul>';
        r.temporal_clues.forEach(function(c) {
            html += '<li><strong>' + escapeHtml(c.clue) + '</strong>: ' + escapeHtml(c.implication) + '</li>';
        });
        html += '</ul>';
    }
    return html;
}

function renderResponseTo(r) {
    if (!r) return '<em>No data</em>';
    var html = '<table class="result-table"><tbody>'
        + '<tr><th>Is Response?</th><td>' + (r.is_response ? 'Yes' : 'No') + '</td></tr>'
        + '<tr><th>Responding To</th><td>' + escapeHtml(r.responding_to_summary || '') + '</td></tr>'
        + '<tr><th>Relationship</th><td>' + escapeHtml(r.relationship_type || '') + '</td></tr>'
        + '<tr><th>Confidence</th><td>' + escapeHtml(r.confidence || '') + '</td></tr>'
        + '</tbody></table>';

    if (r.key_references && r.key_references.length) {
        html += '<h6 class="mt-2">Key References</h6><ul>';
        r.key_references.forEach(function(ref) {
            html += '<li><strong>' + escapeHtml(ref.reference) + '</strong> &rarr; ' + escapeHtml(ref.refers_to) + '</li>';
        });
        html += '</ul>';
    }
    return html;
}

/* ── Free-form query (legacy) ── */

function submitVerbalator(event) {
    event.preventDefault();
    showLoading();

    var form = document.getElementById('verbalator');
    var formData = new FormData(form);

    var requestData = {
        prompt: formData.get('prompt'),
        entry: formData.get('entry'),
        model: formData.get('model') || 'phi3:3.8b',
        verbosity: formData.get('verbosity'),
        reading_level: formData.get('reading_level'),
        creativity: formData.get('creativity'),
        politics: formData.get('politics'),
        sports: formData.get('sports'),
        celebrity: formData.get('celebrity'),
        science: formData.get('science'),
        religion: formData.get('religion'),
    };

    fetch('/verbalator/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
    })
    .then(function(response) {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(function(data) {
        document.getElementById('result').textContent = data.response;
        document.getElementById('info_block').style.display = 'block';
        document.getElementById('tokens_in').textContent = data.usage.tokens_in;
        document.getElementById('tokens_out').textContent = data.usage.tokens_out;
        document.getElementById('cost').textContent = "$" + data.usage.cost.toFixed(6);
        document.getElementById('reading_level').textContent = data.reading_level;
    })
    .catch(function(error) {
        document.getElementById('result').textContent = 'An error occurred: ' + error.message;
    })
    .finally(function() {
        hideLoading();
    });
}

/* ── Helpers ── */

function showLoading() {
    document.getElementById('loading').style.display = 'block';
    document.getElementById('result').textContent = '';
    document.getElementById('info_block').style.display = 'none';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

function updateUsage(usage) {
    document.getElementById('info_block').style.display = 'block';
    var tin = document.getElementById('tokens_in');
    var tout = document.getElementById('tokens_out');
    var costEl = document.getElementById('cost');
    // Accumulate across multiple action calls
    tin.textContent = (parseInt(tin.textContent) || 0) + (usage.tokens_in || 0);
    tout.textContent = (parseInt(tout.textContent) || 0) + (usage.tokens_out || 0);
    var prev = parseFloat((costEl.textContent || '').replace('$', '')) || 0;
    costEl.textContent = '$' + (prev + (usage.cost || 0)).toFixed(6);
}

function renderAttribution(r) {
    if (!r) return '<em>No data</em>';
    var html = '<table class="result-table"><tbody>'
        + '<tr><th>Has Quotations?</th><td>' + (r.has_quotations ? 'Yes' : 'No') + '</td></tr>'
        + '<tr><th>Summary</th><td>' + escapeHtml(r.summary || '') + '</td></tr>'
        + '</tbody></table>';

    if (r.quotations && r.quotations.length) {
        html += '<h6 class="mt-2">Quotations</h6>';
        html += '<table class="result-table"><thead><tr>'
            + '<th>Quoted Text</th><th>Type</th><th>Attributed?</th>'
            + '<th>Attributed To</th><th>Needs Attribution?</th><th>Suggested Source</th>'
            + '</tr></thead><tbody>';
        r.quotations.forEach(function(q) {
            var needsClass = q.needs_attribution ? ' style="color:#c5221f;font-weight:600"' : '';
            html += '<tr>'
                + '<td>' + escapeHtml(q.quoted_text) + '</td>'
                + '<td>' + escapeHtml((q.quotation_type || '').replace(/_/g, ' ')) + '</td>'
                + '<td>' + (q.is_attributed ? 'Yes' : 'No') + '</td>'
                + '<td>' + escapeHtml(q.attributed_to || '') + '</td>'
                + '<td' + needsClass + '>' + (q.needs_attribution ? 'Yes' : 'No') + '</td>'
                + '<td>' + escapeHtml(q.suggested_source || '') + '</td>'
                + '</tr>';
        });
        html += '</tbody></table>';
    }
    return html;
}

function renderSarcasm(r) {
    if (!r) return '<em>No data</em>';
    var confPct = { very_low: 10, low: 30, medium: 50, high: 75, very_high: 95 };
    var pct = confPct[r.confidence] || 50;
    var color = pct >= 75 ? '#34a853' : pct >= 50 ? '#fbbc04' : '#ea4335';

    var html = '<table class="result-table"><tbody>'
        + '<tr><th>Contains Sarcasm?</th><td>' + (r.contains_sarcasm ? 'Yes' : 'No') + '</td></tr>'
        + '<tr><th>Overall Tone</th><td>' + escapeHtml(r.overall_tone || '') + '</td></tr>'
        + '<tr><th>Confidence</th><td>' + escapeHtml(r.confidence || '')
        + ' <span class="confidence-meter"><span class="fill" style="width:' + pct + '%;background:' + color + '"></span></span>'
        + '</td></tr>'
        + '<tr><th>Reasoning</th><td>' + escapeHtml(r.reasoning || '') + '</td></tr>'
        + '</tbody></table>';

    if (r.instances && r.instances.length) {
        html += '<h6 class="mt-2">Sarcastic Passages</h6>';
        r.instances.forEach(function(inst) {
            html += '<div style="border-left:3px solid #a0522d;padding:6px 10px;margin-bottom:8px;background:#fdf6f3">'
                + '<p><strong>Passage:</strong> ' + escapeHtml(inst.passage) + '</p>'
                + '<p><strong>Type:</strong> ' + escapeHtml((inst.sarcasm_type || '').replace(/_/g, ' ')) + '</p>'
                + '<p><strong>Literal:</strong> ' + escapeHtml(inst.literal_meaning) + '</p>'
                + '<p><strong>Intended:</strong> ' + escapeHtml(inst.intended_meaning) + '</p>'
                + '<p><strong>Clues:</strong> ' + (inst.clues || []).map(escapeHtml).join(', ') + '</p>'
                + '</div>';
        });
    }
    return html;
}

function renderPronunciation(r) {
    if (!r) return '<em>No data</em>';
    var html = '<table class="result-table"><tbody>'
        + '<tr><th>Language</th><td>' + escapeHtml(r.language || '') + '</td></tr>'
        + '<tr><th>Summary</th><td>' + escapeHtml(r.summary || '') + '</td></tr>'
        + '</tbody></table>';

    if (r.words && r.words.length) {
        html += '<h6 class="mt-2">Difficult Words</h6>';
        html += '<table class="result-table"><thead><tr>'
            + '<th>Word</th><th>Difficulty</th><th>IPA</th><th>Reasons</th>'
            + '</tr></thead><tbody>';
        r.words.forEach(function(w) {
            var diffClass = w.difficulty === 'very_hard' ? ' style="color:#c5221f;font-weight:600"'
                : w.difficulty === 'hard' ? ' style="color:#e37400;font-weight:600"' : '';
            html += '<tr>'
                + '<td>' + escapeHtml(w.word) + '</td>'
                + '<td' + diffClass + '>' + escapeHtml((w.difficulty || '').replace(/_/g, ' ')) + '</td>'
                + '<td><code>' + escapeHtml(w.ipa || '') + '</code></td>'
                + '<td>' + (w.reasons || []).map(escapeHtml).join('; ') + '</td>'
                + '</tr>';
        });
        html += '</tbody></table>';
    }
    return html;
}

function renderComprehension(r) {
    if (!r) return '<em>No data</em>';
    var html = '<table class="result-table"><tbody>'
        + '<tr><th>Language</th><td>' + escapeHtml(r.language || '') + '</td></tr>'
        + '<tr><th>Summary</th><td>' + escapeHtml(r.summary || '') + '</td></tr>'
        + '</tbody></table>';

    if (r.words && r.words.length) {
        html += '<h6 class="mt-2">Difficult Words</h6>';
        html += '<table class="result-table"><thead><tr>'
            + '<th>Word</th><th>Difficulty</th><th>Explanation</th><th>Reasons</th>'
            + '</tr></thead><tbody>';
        r.words.forEach(function(w) {
            var diffClass = w.difficulty === 'very_hard' ? ' style="color:#c5221f;font-weight:600"'
                : w.difficulty === 'hard' ? ' style="color:#e37400;font-weight:600"' : '';
            html += '<tr>'
                + '<td>' + escapeHtml(w.word) + '</td>'
                + '<td' + diffClass + '>' + escapeHtml((w.difficulty || '').replace(/_/g, ' ')) + '</td>'
                + '<td>' + escapeHtml(w.simplified_explanation || '') + '</td>'
                + '<td>' + (w.reasons || []).map(escapeHtml).join('; ') + '</td>'
                + '</tr>';
        });
        html += '</tbody></table>';
    }
    return html;
}

function getColorClass(actionName) {
    /* Mirror verbalator/colors.py COLOR_ORDER mapping. */
    var colorMap = {
        'metadata': 'blue', 'time_analysis': 'blue', 'response_to': 'blue',
        'decomposition': 'green',
        'attribution': 'yellow',
        'sarcasm': 'xantham',
        'pronunciation': 'color-pending',
        'comprehension': 'color-pending'
    };
    return colorMap[actionName] || 'blue';
}

function formatActionName(name) {
    return name.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
