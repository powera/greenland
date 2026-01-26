// Rapid Review JavaScript Module

/**
 * Initialize the rapid review page
 * @param {Object} config - Configuration object
 * @param {number|null} config.initialReviewId - Initial review ID or null
 * @param {number} config.totalCount - Total number of reviews
 * @param {string} config.languageFilter - Language filter value
 * @param {string} config.voiceFilter - Voice filter value
 * @param {string} config.statusFilter - Status filter value
 * @param {string} config.subtypeFilter - Subtype filter value
 * @param {string} config.levelFilter - Level filter value
 * @param {string} config.typeFilter - Audio type filter value (lemma/sentence)
 * @param {string} config.rapidReviewIndexUrl - URL for rapid review index
 */
function initRapidReview(config) {
    let currentReviewId = config.initialReviewId;
    let reviewedCount = 0;
    let totalCount = config.totalCount;
    let selectedIssues = [];
    const languageFilter = config.languageFilter;
    const voiceFilter = config.voiceFilter;
    const statusFilter = config.statusFilter;
    const subtypeFilter = config.subtypeFilter;
    const levelFilter = config.levelFilter;
    const typeFilter = config.typeFilter || '';

    // Undo stack - stores last 5 reviews
    const MAX_UNDO_STACK = 5;
    let undoStack = [];

    // Issue tag selection
    document.querySelectorAll('.issue-tag').forEach((tag, index) => {
        tag.addEventListener('click', function() {
            this.classList.toggle('selected');
            const issue = this.dataset.issue;
            if (selectedIssues.includes(issue)) {
                selectedIssues = selectedIssues.filter(i => i !== issue);
            } else {
                selectedIssues.push(issue);
            }
        });
    });

    // Number key shortcuts (1-9, 0 for 10th) - outside the forEach loop
    document.addEventListener('keydown', function(e) {
        // Only handle number keys if not in an input or select element
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        const key = parseInt(e.key);
        const tags = document.querySelectorAll('.issue-tag');
        if (key >= 1 && key <= 9) {
            e.preventDefault();
            tags[key - 1]?.click();
        } else if (e.key === '0') {
            e.preventDefault();
            tags[9]?.click();
        }
    });

    // Approve button
    document.getElementById('btn-approve')?.addEventListener('click', function() {
        submitReview('approved');
    });

    // Acceptable button
    document.getElementById('btn-acceptable')?.addEventListener('click', function() {
        submitReview('approved_with_issues');
    });

    // Reject button
    document.getElementById('btn-reject')?.addEventListener('click', function() {
        submitReview('needs_replacement');
    });

    // Undo button
    document.getElementById('btn-undo')?.addEventListener('click', function() {
        performUndo();
    });

    // Skip button
    document.getElementById('btn-skip')?.addEventListener('click', function() {
        skipToNext();
    });

    // Bad translation button
    document.getElementById('btn-bad-translation')?.addEventListener('click', function() {
        markBadTranslation();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // G - Approve (Good/OK)
        if (e.code === 'KeyG' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
            e.preventDefault();
            submitReview('approved');
        }

        // A - Acceptable with issues
        if (e.code === 'KeyA' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
            e.preventDefault();
            submitReview('approved_with_issues');
        }

        // R - Reject (Problem)
        if (e.code === 'KeyR' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
            e.preventDefault();
            submitReview('needs_replacement');
        }

        // S - Skip to next without marking
        if (e.code === 'KeyS' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
            e.preventDefault();
            skipToNext();
        }

        // T - Mark translation as bad
        if (e.code === 'KeyT' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
            e.preventDefault();
            markBadTranslation();
        }

        // P - Replay audio
        if (e.code === 'KeyP' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
            e.preventDefault();
            const audio = document.getElementById('audio-player');
            if (audio) {
                audio.currentTime = 0;
                audio.play();
            }
        }

        // U or Backspace - Undo
        if ((e.code === 'KeyU' || e.code === 'Backspace') && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            performUndo();
        }
    });

    // Filter application
    document.getElementById('apply-filters')?.addEventListener('click', function() {
        const language = document.getElementById('language-filter').value;

        // Language is required
        if (!language) {
            alert('Please select a language to begin rapid review');
            return;
        }

        const voice = document.getElementById('voice-filter').value;
        const status = document.getElementById('status-filter').value;
        const type = document.getElementById('type-filter').value;
        const subtype = document.getElementById('subtype-filter').value;
        const level = document.getElementById('level-filter').value;

        const params = new URLSearchParams();
        params.set('language', language);  // Language is always set
        if (voice) params.set('voice', voice);
        if (status) params.set('status', status);
        if (type) params.set('type', type);
        if (subtype) params.set('subtype', subtype);
        if (level) params.set('level', level);

        window.location.href = config.rapidReviewIndexUrl + '?' + params.toString();
    });

    function submitReview(status) {
        if (!currentReviewId) return;

        // Save current state to undo stack before submitting
        const currentState = {
            id: currentReviewId,
            guid: document.getElementById('guid').textContent,
            expected_text: document.getElementById('expected-text').textContent,
            language_code: document.getElementById('language').textContent,
            voice_name: document.getElementById('voice').textContent,
            pinyin: document.getElementById('romanization-display')?.textContent || null,
            audio_url: document.getElementById('audio-source').src,
            previous_status: 'pending_review', // Assume it was pending before
            new_status: status,
            issues: [...selectedIssues]
        };

        fetch(`/audio/rapid-review/submit/${currentReviewId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                status: status,
                quality_issues: selectedIssues,
                language: languageFilter,
                voice: voiceFilter,
                status_filter: statusFilter,
                type: typeFilter,
                subtype: subtypeFilter,
                level: levelFilter
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
                    loadNextReview(data.next_review);
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

    function loadNextReview(review) {
        currentReviewId = review.id;
        selectedIssues = [];

        // Update UI
        document.getElementById('expected-text').textContent = review.expected_text;
        document.getElementById('guid').textContent = review.guid;
        document.getElementById('language').textContent = review.language_code;
        document.getElementById('voice').textContent = review.display_voice;

        // Update pinyin if present (for Chinese)
        const pinyinDisplay = document.getElementById('romanization-display');
        if (pinyinDisplay && review.pinyin) {
            pinyinDisplay.textContent = review.pinyin;
        }

        // Check for translation mismatch and display warning
        const warningDiv = document.getElementById('translation-warning');
        if (warningDiv) {
            if (review.validation && review.validation.mismatch) {
                const audioTextEl = document.getElementById('warning-audio-text');
                const currentTextEl = document.getElementById('warning-current-text');
                if (audioTextEl) audioTextEl.textContent = review.expected_text;
                if (currentTextEl) currentTextEl.textContent = review.validation.current_translation;
                warningDiv.style.display = 'block';
            } else {
                warningDiv.style.display = 'none';
            }
        }

        // Update audio
        const audioPlayer = document.getElementById('audio-player');
        const audioSource = document.getElementById('audio-source');
        audioSource.src = review.audio_url;
        audioPlayer.load();
        audioPlayer.play();

        // Clear selected issue tags
        document.querySelectorAll('.issue-tag').forEach(tag => {
            tag.classList.remove('selected');
        });
    }

    function updateProgress() {
        const percentage = (reviewedCount / totalCount) * 100;
        document.getElementById('progress-bar').style.width = percentage + '%';
        document.getElementById('progress-text').textContent =
            `Reviewed ${reviewedCount} of ${totalCount} files`;
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

        // Revert the status change
        fetch(`/audio/rapid-review/submit/${lastReview.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                status: lastReview.previous_status,
                quality_issues: [],
                language: languageFilter,
                voice: voiceFilter,
                status_filter: statusFilter,
                type: typeFilter,
                subtype: subtypeFilter,
                level: levelFilter
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Load the previous review back into the UI
                loadPreviousReview(lastReview);

                // Decrement reviewed count
                reviewedCount--;
                updateProgress();
            } else {
                alert('Error undoing review: ' + data.error);
                // Put it back on the stack if it failed
                undoStack.push(lastReview);
                updateUndoButton();
            }
        })
        .catch(error => {
            alert('Error undoing review: ' + error);
            // Put it back on the stack if it failed
            undoStack.push(lastReview);
            updateUndoButton();
        });
    }

    function loadPreviousReview(review) {
        currentReviewId = review.id;
        selectedIssues = [];

        // Update UI
        document.getElementById('expected-text').textContent = review.expected_text;
        document.getElementById('guid').textContent = review.guid;
        document.getElementById('language').textContent = review.language_code;
        document.getElementById('voice').textContent = review.display_voice;

        // Update pinyin if present
        const pinyinDisplay = document.getElementById('romanization-display');
        if (pinyinDisplay && review.pinyin) {
            pinyinDisplay.textContent = review.pinyin;
        }

        // Update audio
        const audioPlayer = document.getElementById('audio-player');
        const audioSource = document.getElementById('audio-source');
        audioSource.src = review.audio_url;
        audioPlayer.load();
        audioPlayer.play();

        // Clear selected issue tags
        document.querySelectorAll('.issue-tag').forEach(tag => {
            tag.classList.remove('selected');
        });

        // Show review area if it was hidden
        document.getElementById('review-area').style.display = 'block';
        document.getElementById('completion-area').style.display = 'none';
    }

    function skipToNext() {
        if (!currentReviewId) return;

        // Just fetch the next review without changing the status of the current one
        fetch(`/audio/rapid-review/skip/${currentReviewId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                language: languageFilter,
                voice: voiceFilter,
                status_filter: statusFilter,
                type: typeFilter,
                subtype: subtypeFilter,
                level: levelFilter
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (data.has_next) {
                    loadNextReview(data.next_review);
                } else {
                    showCompletion();
                }
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            alert('Error skipping to next: ' + error);
        });
    }

    function markBadTranslation() {
        if (!currentReviewId) return;

        // Mark the translation as needing attention (we'll use a specific issue tag)
        // and mark the status as needs_replacement
        const badTranslationIssues = ['translation_mismatch'];

        fetch(`/audio/rapid-review/bad-translation/${currentReviewId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                language: languageFilter,
                voice: voiceFilter,
                status_filter: statusFilter,
                type: typeFilter,
                subtype: subtypeFilter,
                level: levelFilter
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                reviewedCount++;
                updateProgress();

                if (data.has_next) {
                    loadNextReview(data.next_review);
                } else {
                    showCompletion();
                }
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            alert('Error marking bad translation: ' + error);
        });
    }
}
