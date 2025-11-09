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
