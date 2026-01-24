// Audio Review JavaScript Module

/**
 * Initialize the audio review page
 * @param {Object} config - Configuration object
 * @param {string} config.currentStatus - Current review status
 */
function initAudioReview(config) {
    const form = document.querySelector('form');
    const issuesInput = document.getElementById('quality_issues_json');

    // Collect checked issues into JSON array on form submit
    form.addEventListener('submit', function(e) {
        // Collect all checked issues
        const issues = [];
        document.querySelectorAll('.issue-checkbox input:checked').forEach(checkbox => {
            issues.push(checkbox.value);
        });

        // Update hidden field
        issuesInput.value = JSON.stringify(issues);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Space - play/pause audio
        if (e.code === 'Space' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            const audio = document.querySelector('audio');
            if (audio.paused) {
                audio.play();
            } else {
                audio.pause();
            }
        }

        // A or Enter - Approve
        if ((e.code === 'KeyA' || e.code === 'Enter') && e.target.tagName !== 'TEXTAREA' && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            document.getElementById('status_approved').checked = true;
            form.requestSubmit();
        }

        // R - Reject (needs replacement)
        if (e.code === 'KeyR' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            document.getElementById('status_needs_replacement').checked = true;
            form.requestSubmit();
        }

        if (e.code === 'KeyN' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            document.querySelector('[name="save_and_next"]').click();
        }
    });

    window.confirmRemove = function() {
        const currentStatus = config.currentStatus;
        let message = "Are you sure you want to remove this file from the database?";

        if (currentStatus !== 'needs_replacement') {
            message = "WARNING: This file is currently marked as '" + currentStatus + "' (not 'needs_replacement').\n\n" + message;
        }

        if (confirm(message)) {
            document.getElementById('remove-form').submit();
        }
    };
}
