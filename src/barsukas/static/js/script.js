// Barsukas Web Interface JavaScript

// Auto-dismiss flash messages after 5 seconds (only in the flash-messages container)
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.flash-messages .alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

// Confirm deletion actions
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this?');
}

// Check for slash in translation and show warning
function checkTranslationSlash(input, warningId) {
    const warning = document.getElementById(warningId);
    if (!warning) return;

    if (input.value.includes('/')) {
        warning.style.display = 'block';
    } else {
        warning.style.display = 'none';
    }
}

// Validate difficulty level
function validateDifficultyLevel(input) {
    const value = input.value.trim();
    if (value === '') return true;

    const num = parseInt(value);
    if (isNaN(num)) {
        return false;
    }

    return num === -1 || (num >= 1 && num <= 20);
}

// Add event listener to difficulty level inputs
document.addEventListener('DOMContentLoaded', function() {
    const difficultyInputs = document.querySelectorAll('input[name="difficulty_level"]');
    difficultyInputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (!validateDifficultyLevel(this)) {
                alert('Difficulty level must be -1 (exclude) or between 1 and 20');
                this.focus();
            }
        });
    });
});

// Prevent double-submission of forms (especially for LLM operations)
document.addEventListener('DOMContentLoaded', function() {
    // Track submitted forms to prevent double-submission
    const submittedForms = new Set();

    // Add submit handler to all forms.
    //
    // GET forms are exempt: the guard exists to stop a second POST kicking off
    // a duplicate LLM run or write, and a GET form is a search box whose
    // resubmission is both idempotent and the normal way to use it. Guarding
    // them left the button dead after a back-navigation.
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        if ((form.method || '').toLowerCase() === 'get') {
            return;
        }
        form.addEventListener('submit', function(event) {
            // Create a unique identifier for this form
            const formId = form.action + form.method;

            // Check if this form was already submitted
            if (submittedForms.has(formId)) {
                event.preventDefault();
                console.log('Form submission prevented (already submitted):', formId);
                return false;
            }

            // Mark this form as submitted
            submittedForms.add(formId);

            // Disable the submit button to prevent additional clicks
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;

                // Add a spinner to the button to show activity
                const originalHTML = submitButton.innerHTML;
                submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' +
                                        (submitButton.textContent || 'Processing...');

                // Store original state for potential reset
                submitButton.dataset.originalHtml = originalHTML;
            }

            // Allow form submission to proceed
            return true;
        });
    });

    // Clean up submitted forms set when navigating away
    window.addEventListener('beforeunload', function() {
        submittedForms.clear();
    });

    // Restore every guarded button when the page is shown again.
    //
    // Going Back restores the page from the bfcache with its DOM intact, so the
    // button is still disabled and its formId is still in the set - and
    // beforeunload does not fire on the way *in*, so nothing undid either one.
    // The result was a permanently dead submit button on any page reached by
    // Back. pageshow fires on both a fresh load and a bfcache restore.
    window.addEventListener('pageshow', function() {
        submittedForms.clear();
        document.querySelectorAll('button[type="submit"][disabled]').forEach(button => {
            button.disabled = false;
            if (button.dataset.originalHtml) {
                button.innerHTML = button.dataset.originalHtml;
                delete button.dataset.originalHtml;
            }
        });
    });
});

// Toggle secondary (non-default) language rows in translations table
document.addEventListener('DOMContentLoaded', function() {
    var toggleBtn = document.getElementById('toggleSecondaryLangsBtn');
    if (!toggleBtn) return;

    var hiddenCount = document.querySelectorAll('.secondary-translation').length;
    toggleBtn.innerHTML = '<i class="bi bi-chevron-down"></i> Show all languages (' + hiddenCount + ' more)';

    toggleBtn.addEventListener('click', function() {
        var rows = document.querySelectorAll('.secondary-translation');
        var isHidden = rows.length > 0 && rows[0].classList.contains('d-none');
        rows.forEach(function(row) {
            row.classList.toggle('d-none');
        });
        if (isHidden) {
            toggleBtn.innerHTML = '<i class="bi bi-chevron-up"></i> Show fewer languages';
        } else {
            toggleBtn.innerHTML = '<i class="bi bi-chevron-down"></i> Show all languages (' + hiddenCount + ' more)';
        }
    });
});
