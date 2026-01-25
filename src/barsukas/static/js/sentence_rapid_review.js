// Sentence Rapid Review JavaScript Module

/**
 * Initialize the sentence rapid review page
 * @param {Object} config - Configuration object
 * @param {number|null} config.initialSentenceId - Initial sentence ID or null
 * @param {number} config.totalCount - Total number of sentences
 * @param {string} config.statusFilter - Status filter value
 * @param {string} config.levelFilter - Level filter value
 * @param {string} config.patternFilter - Pattern filter value
 * @param {string} config.rapidReviewIndexUrl - URL for rapid review index
 */
function initSentenceRapidReview(config) {
    let currentSentenceId = config.initialSentenceId;
    let reviewedCount = 0;
    let totalCount = config.totalCount;
    const statusFilter = config.statusFilter;
    const levelFilter = config.levelFilter;
    const patternFilter = config.patternFilter;

    // Undo stack - stores last 5 reviews
    const MAX_UNDO_STACK = 5;
    let undoStack = [];

    // Verify button
    document.getElementById('btn-verify')?.addEventListener('click', function() {
        submitReview('verify');
    });

    // Skip button
    document.getElementById('btn-skip')?.addEventListener('click', function() {
        skipToNext();
    });

    // Reject button
    document.getElementById('btn-reject')?.addEventListener('click', function() {
        submitReview('reject');
    });

    // Undo button
    document.getElementById('btn-undo')?.addEventListener('click', function() {
        performUndo();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Skip if in input/select/textarea
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        // G - Verify (Good)
        if (e.code === 'KeyG') {
            e.preventDefault();
            submitReview('verify');
        }

        // S - Skip
        if (e.code === 'KeyS') {
            e.preventDefault();
            skipToNext();
        }

        // R - Reject
        if (e.code === 'KeyR') {
            e.preventDefault();
            submitReview('reject');
        }

        // U or Backspace - Undo
        if (e.code === 'KeyU' || e.code === 'Backspace') {
            e.preventDefault();
            performUndo();
        }
    });

    // Filter application
    document.getElementById('apply-filters')?.addEventListener('click', function() {
        const status = document.getElementById('status-filter').value;
        const level = document.getElementById('level-filter').value;
        const pattern = document.getElementById('pattern-filter').value;

        const params = new URLSearchParams();
        if (status) params.set('status', status);
        if (level) params.set('level', level);
        if (pattern) params.set('pattern', pattern);

        window.location.href = config.rapidReviewIndexUrl + '?' + params.toString();
    });

    function submitReview(action) {
        if (!currentSentenceId) return;

        // Save current state to undo stack before submitting
        const currentState = {
            id: currentSentenceId,
            translations: {
                en: document.getElementById('trans-en').textContent,
                es: document.getElementById('trans-es').textContent,
                fr: document.getElementById('trans-fr').textContent,
                zh: document.getElementById('trans-zh').textContent,
                lt: document.getElementById('trans-lt').textContent,
            },
            pinyin: document.getElementById('trans-zh-pinyin')?.textContent || null,
            level: document.getElementById('sentence-level')?.textContent || null,
            pattern: document.getElementById('sentence-pattern')?.textContent || null,
            tense: document.getElementById('sentence-tense')?.textContent || null,
            action: action,
            previous_verified: false,
            previous_rejected: false
        };

        const endpoint = action === 'verify'
            ? `/sentences/rapid-review/verify/${currentSentenceId}`
            : `/sentences/rapid-review/reject/${currentSentenceId}`;

        fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                status_filter: statusFilter,
                level: levelFilter,
                pattern: patternFilter
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Add to undo stack
                undoStack.push(currentState);
                if (undoStack.length > MAX_UNDO_STACK) {
                    undoStack.shift(); // Remove oldest entry
                }
                updateUndoButton();

                reviewedCount++;
                updateProgress();

                if (data.has_next) {
                    loadNextSentence(data.next_sentence);
                } else {
                    showCompletion();
                }
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            alert('Error submitting review: ' + error);
        });
    }

    function skipToNext() {
        if (!currentSentenceId) return;

        fetch(`/sentences/rapid-review/skip/${currentSentenceId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                status_filter: statusFilter,
                level: levelFilter,
                pattern: patternFilter
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (data.has_next) {
                    loadNextSentence(data.next_sentence);
                } else {
                    showCompletion();
                }
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            alert('Error skipping: ' + error);
        });
    }

    function loadNextSentence(sentence) {
        currentSentenceId = sentence.id;

        // Update UI
        document.getElementById('sentence-id').textContent = '#' + sentence.id;

        const levelEl = document.getElementById('sentence-level');
        if (levelEl) {
            levelEl.textContent = sentence.minimum_level || '-';
        }

        const patternEl = document.getElementById('sentence-pattern');
        if (patternEl && sentence.pattern_type) {
            patternEl.textContent = sentence.pattern_type;
            patternEl.parentElement.style.display = '';
        } else if (patternEl) {
            patternEl.parentElement.style.display = 'none';
        }

        const tenseEl = document.getElementById('sentence-tense');
        if (tenseEl && sentence.tense) {
            tenseEl.textContent = sentence.tense;
            tenseEl.parentElement.style.display = '';
        } else if (tenseEl) {
            tenseEl.parentElement.style.display = 'none';
        }

        // Update translations
        const translations = sentence.translations || {};
        document.getElementById('trans-en').textContent = translations.en || '(no English)';
        document.getElementById('trans-es').textContent = translations.es || '(missing)';
        document.getElementById('trans-fr').textContent = translations.fr || '(missing)';
        document.getElementById('trans-zh').textContent = translations.zh || '(missing)';
        document.getElementById('trans-lt').textContent = translations.lt || '(missing)';

        // Update pinyin
        const pinyinEl = document.getElementById('trans-zh-pinyin');
        if (pinyinEl) {
            if (sentence.pinyin) {
                pinyinEl.textContent = sentence.pinyin;
                pinyinEl.style.display = '';
            } else {
                pinyinEl.style.display = 'none';
            }
        }

        // Update view details link
        const viewDetailBtn = document.getElementById('btn-view-detail');
        if (viewDetailBtn) {
            viewDetailBtn.href = `/sentences/${sentence.id}`;
        }
    }

    function updateProgress() {
        const percentage = (reviewedCount / totalCount) * 100;
        document.getElementById('progress-bar').style.width = percentage + '%';
        document.getElementById('progress-text').textContent =
            `Reviewed ${reviewedCount} of ${totalCount} sentences`;
    }

    function showCompletion() {
        document.getElementById('review-area').style.display = 'none';
        document.getElementById('completion-area').style.display = 'block';
    }

    function updateUndoButton() {
        const undoButton = document.getElementById('btn-undo');
        const undoCount = document.getElementById('undo-count');

        if (undoStack.length > 0) {
            undoButton.disabled = false;
            undoCount.textContent = undoStack.length;
        } else {
            undoButton.disabled = true;
            undoCount.textContent = '0';
        }
    }

    function performUndo() {
        if (undoStack.length === 0) return;

        // Pop the last review from the stack
        const lastReview = undoStack.pop();
        updateUndoButton();

        // Call undo endpoint to restore state
        fetch(`/sentences/rapid-review/undo/${lastReview.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                previous_verified: lastReview.previous_verified,
                previous_rejected: lastReview.previous_rejected
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Load the previous sentence back into the UI
                loadNextSentence(data.sentence);

                // Decrement reviewed count
                reviewedCount--;
                updateProgress();

                // Show review area if it was hidden
                document.getElementById('review-area').style.display = 'block';
                document.getElementById('completion-area').style.display = 'none';
            } else {
                alert('Error undoing: ' + data.error);
                // Put it back on the stack if it failed
                undoStack.push(lastReview);
                updateUndoButton();
            }
        })
        .catch(error => {
            alert('Error undoing: ' + error);
            // Put it back on the stack if it failed
            undoStack.push(lastReview);
            updateUndoButton();
        });
    }
}
