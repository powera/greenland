// Barsukas Web Interface JavaScript

// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
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

    // Add submit handler to all forms
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
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
});
