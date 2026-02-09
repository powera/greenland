// Barsukas Audio Utilities

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
 * @param {Object} config.pollyVoices - Object mapping language codes to Amazon Polly voice arrays
 * @param {Object} config.azureVoices - Object mapping language codes to Azure TTS voice arrays
 * @param {Object} config.googleVoices - Object mapping language codes to Google Cloud TTS voice arrays
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

        } else if (engine === 'polly') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.pollyVoices ? config.pollyVoices[language] : null;
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No Amazon Polly voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select Amazon Polly voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using Amazon Polly (paid, neural). Review records will be created with status "pending_review".';

            const checkboxes = voices.map(voice => {
                const genderBadge = voice.gender === 'f' ? 'F' : 'M';
                return createVoiceCheckbox(voice.name, voice.ui_name, genderBadge, true);
            });
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));

        } else if (engine === 'azure') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.azureVoices ? config.azureVoices[language] : null;
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No Azure TTS voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select Azure Cognitive TTS voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using Azure Cognitive TTS (paid, neural). Review records will be created with status "pending_review".';

            const checkboxes = voices.map(voice => {
                const genderBadge = voice.gender === 'f' ? 'F' : 'M';
                return createVoiceCheckbox(voice.name, voice.ui_name, genderBadge, true);
            });
            voicesContainer.appendChild(createTwoColumnLayout(checkboxes));

        } else if (engine === 'google') {
            if (!language) {
                voicesContainer.innerHTML = '<div class="text-muted">Please select a language first</div>';
                return;
            }

            const voices = config.googleVoices ? config.googleVoices[language] : null;
            if (!voices || voices.length === 0) {
                voicesContainer.innerHTML = '<div class="text-warning">No Google Cloud TTS voices available for this language</div>';
                return;
            }

            if (voiceHelp) voiceHelp.textContent = 'Select Google Cloud TTS voices to generate';
            if (engineInfo) engineInfo.innerHTML = '<i class="bi bi-info-circle"></i> <strong>Note:</strong> Audio will be generated using Google Cloud TTS (paid, Wavenet/Neural2). Review records will be created with status "pending_review".';

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
