// Barsukas Web Interface JavaScript

/**
 * Audio Generation Voice Selection Handler
 *
 * Sets up dynamic voice selection for audio generation modals.
 * Works with both lemma and sentence audio generation forms.
 *
 * @param {Object} config - Configuration object
 * @param {string} config.modalId - ID of the modal element
 * @param {string} config.engineSelectId - ID of the TTS engine select
 * @param {string} config.languageSelectId - ID of the language select
 * @param {string} config.voicesContainerId - ID of the voices container div
 * @param {string} config.voiceHelpId - ID of the voice help text element
 * @param {string} config.engineInfoId - ID of the engine info alert element
 * @param {string} config.idPrefix - Prefix for voice checkbox IDs (e.g., 'audio' or 'sentence-audio')
 * @param {Array} config.openaiVoices - Array of OpenAI voice names
 * @param {Object} config.espeakVoices - Object mapping language codes to eSpeak voice arrays
 * @param {Object} config.piperVoices - Object mapping language codes to Piper voice arrays
 * @param {Object} config.coquiVoices - Object mapping language codes to Coqui voice arrays
 * @param {Object} config.qwen3Voices - Object mapping language codes to Qwen3 voice arrays
 */
function setupAudioVoiceSelection(config) {
    const ttsEngineSelect = document.getElementById(config.engineSelectId);
    const languageSelect = document.getElementById(config.languageSelectId);
    const voicesContainer = document.getElementById(config.voicesContainerId);
    const voiceHelp = document.getElementById(config.voiceHelpId);
    const engineInfo = document.getElementById(config.engineInfoId);
    const modal = document.getElementById(config.modalId);

    if (!ttsEngineSelect || !languageSelect || !voicesContainer || !modal) {
        console.warn('Audio voice selection: Missing required elements');
        return;
    }

    function createVoiceCheckbox(voiceName, voiceLabel, genderBadge, checked) {
        const formCheck = document.createElement('div');
        formCheck.className = 'form-check';

        const checkbox = document.createElement('input');
        checkbox.className = 'form-check-input';
        checkbox.type = 'checkbox';
        checkbox.name = 'voices';
        checkbox.value = voiceName;
        checkbox.id = `${config.idPrefix}-voice-${voiceName}`;
        checkbox.checked = checked;

        const label = document.createElement('label');
        label.className = 'form-check-label';
        label.htmlFor = checkbox.id;
        label.innerHTML = genderBadge ? `${voiceLabel} <span class="badge bg-secondary">${genderBadge}</span>` : voiceLabel;

        formCheck.appendChild(checkbox);
        formCheck.appendChild(label);
        return formCheck;
    }

    function createTwoColumnLayout(items) {
        const row = document.createElement('div');
        row.className = 'row';

        const col1 = document.createElement('div');
        col1.className = 'col-md-6';
        const col2 = document.createElement('div');
        col2.className = 'col-md-6';

        const midpoint = Math.ceil(items.length / 2);
        items.forEach((item, idx) => {
            if (idx < midpoint) {
                col1.appendChild(item);
            } else {
                col2.appendChild(item);
            }
        });

        row.appendChild(col1);
        row.appendChild(col2);
        return row;
    }

    function updateVoiceOptions() {
        const engine = ttsEngineSelect.value;
        const language = languageSelect.value;

        voicesContainer.innerHTML = '';

        if (engine === 'openai') {
            if (voiceHelp) voiceHelp.textContent = 'Select OpenAI voices to generate (default: ash, alloy, nova)';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using OpenAI TTS API (paid). Review records will be created with status "pending_review".';

            const checkboxes = config.openaiVoices.map(voice =>
                createVoiceCheckbox(voice, voice, null, ['ash', 'alloy', 'nova'].includes(voice))
            );
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));

        } else if (engine === 'espeak-ng') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.espeakVoices[language];
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No eSpeak voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select eSpeak-NG voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using eSpeak-NG (free, synthetic). Review records will be created with status "pending_review".';

            const checkboxes = voices.map(voice => {
                const genderBadge = voice.gender === 'f' ? 'F' : 'M';
                return createVoiceCheckbox(voice.name, voice.name, genderBadge, true);
            });
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));

        } else if (engine === 'piper') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.piperVoices[language];
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No Piper voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select Piper neural voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using Piper (free, neural). Review records will be created with status "pending_review".';

            const checkboxes = voices.map(voice => {
                const genderBadge = voice.gender === 'f' ? 'F' : 'M';
                return createVoiceCheckbox(voice.name, voice.ui_name, genderBadge, true);
            });
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));

        } else if (engine === 'coqui') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.coquiVoices[language];
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No Coqui voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select Coqui XTTS voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using Coqui TTS (free, neural, voice cloning). Review records will be created with status "pending_review".';

            const checkboxes = voices.map(voice => {
                const genderBadge = voice.gender === 'f' ? 'F' : 'M';
                return createVoiceCheckbox(voice.name, voice.ui_name, genderBadge, true);
            });
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));

        } else if (engine === 'qwen3') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.qwen3Voices[language];
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No Qwen3 voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select Qwen3 neural voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using Qwen3 TTS (free, neural, multilingual). Review records will be created with status "pending_review".';

            const checkboxes = voices.map(voice => {
                const genderBadge = voice.gender === 'f' ? 'F' : 'M';
                return createVoiceCheckbox(voice.name, voice.ui_name, genderBadge, true);
            });
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));
        }
    }

    ttsEngineSelect.addEventListener('change', updateVoiceOptions);
    languageSelect.addEventListener('change', updateVoiceOptions);
    modal.addEventListener('shown.bs.modal', updateVoiceOptions);
}

/**
 * Audio Player Handler
 *
 * Sets up play/pause functionality for audio buttons.
 *
 * @param {string} buttonSelector - CSS selector for play buttons
 */
function setupAudioPlayer(buttonSelector) {
    const audioPlayer = new Audio();
    let currentPlayButton = null;

    document.querySelectorAll(buttonSelector).forEach(btn => {
        btn.addEventListener('click', function() {
            const audioUrl = this.dataset.audioUrl;

            if (currentPlayButton === this && !audioPlayer.paused) {
                audioPlayer.pause();
                this.innerHTML = '<i class="bi bi-play-circle"></i>';
                return;
            }

            if (currentPlayButton) {
                currentPlayButton.innerHTML = '<i class="bi bi-play-circle"></i>';
            }

            audioPlayer.src = audioUrl;
            audioPlayer.play();
            this.innerHTML = '<i class="bi bi-pause-circle"></i>';
            currentPlayButton = this;
        });
    });

    audioPlayer.addEventListener('ended', function() {
        if (currentPlayButton) {
            currentPlayButton.innerHTML = '<i class="bi bi-play-circle"></i>';
            currentPlayButton = null;
        }
    });
}

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
