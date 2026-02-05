// Agents Launcher JavaScript Module

/**
 * Initialize the agent launcher page
 * @param {string} scriptName - The agent script name (e.g., "dramblys.py")
 */
function initAgentLauncher(scriptName) {
    const modeSelect = document.getElementById('mode');

    // Only set up mode handling for static forms
    if (modeSelect) {
        const modeInputContainer = document.getElementById('modeInputContainer');
        const modeInput = document.getElementById('modeInput');

        // Handle mode selection - show/hide input based on mode requirements
        modeSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const requiresInput = selectedOption.getAttribute('data-requires-input') === 'true';
            const placeholder = selectedOption.getAttribute('data-input-placeholder');

            if (requiresInput) {
                modeInputContainer.style.display = 'block';
                modeInput.placeholder = placeholder;
                modeInput.required = true;
            } else {
                modeInputContainer.style.display = 'none';
                modeInput.required = false;
                modeInput.value = '';
            }
        });
    }

    // Enhanced dynamic form handling
    const agentForm = document.getElementById('agentForm');
    if (agentForm) {
        const generateBtn = document.getElementById('generateCommandBtn');
        const copyBtn = document.getElementById('copyCommandBtn');
        const commandPreview = document.getElementById('commandPreviewCard');
        const commandInput = document.getElementById('generatedCommand');
        const argInputs = document.querySelectorAll('.arg-input');

        // Get agent script name from parameter
        const agentName = scriptName.replace('.py', '');

        // Parameter conflict rules (mutual exclusions)
        const conflictRules = {
            'guid': ['limit', 'sample_rate', 'batch'],
            'batch': ['guid'],
            'limit': ['guid'],
            'sample_rate': ['guid'],
        };

        // Build mode-dependent parameter visibility map from mode_hints
        const modeHints = {};
        argInputs.forEach(input => {
            const dest = input.dataset.dest;
            const argDiv = input.closest('[data-arg]');
            if (argDiv) {
                const modeHint = argDiv.dataset.modeHint;
                if (modeHint) {
                    modeHints[dest] = modeHint;
                }
            }
        });

        // Detect mode selector parameters (typically 'mode', 'check', 'task', etc.)
        const modeSelectors = ['mode', 'check', 'fix', 'stage', 'task', 'form_type'];
        const foundModeSelectors = [];

        // Map parameter names to mode names (for cases where they differ)
        const modeNameMap = {
            'check': 'check'  // can also be a select with choices
        };

        modeSelectors.forEach(selector => {
            const input = document.getElementById(`arg_${selector}`);
            if (input) {
                foundModeSelectors.push(selector);
            }
        });

        // Apply mode-dependent visibility
        function updateModeVisibility() {
            if (foundModeSelectors.length === 0) return;

            // Determine which mode(s) are currently active
            const activeModes = new Set();

            foundModeSelectors.forEach(selector => {
                const input = document.getElementById(`arg_${selector}`);
                if (!input) return;

                let modeName = modeNameMap[selector] || selector;

                if (input.type === 'checkbox') {
                    // Boolean mode flag (e.g., --fix, --stage)
                    if (input.checked) {
                        activeModes.add(modeName);
                    }
                } else if (input.tagName === 'SELECT') {
                    // Select mode (e.g., --mode with choices, or --check with choices)
                    if (input.value && input.value !== '') {
                        activeModes.add(input.value);
                    }
                } else if (input.value && input.value !== '') {
                    // Text/file input that acts as a mode selector
                    activeModes.add(modeName);
                }
            });

            // Show/hide parameters based on active modes
            argInputs.forEach(input => {
                const dest = input.dataset.dest;
                const argDiv = input.closest('[data-arg]');

                // Don't hide the mode selectors themselves
                if (!argDiv || foundModeSelectors.includes(dest)) return;

                const modeHint = argDiv.dataset.modeHint;

                if (modeHint) {
                    // This parameter has a mode hint
                    // Show if its mode hint matches any active mode with flexible matching
                    const shouldShow = activeModes.size > 0 && Array.from(activeModes).some(mode => {
                        // Exact match
                        if (mode === modeHint) return true;
                        // Mode hint contains the active mode (e.g., "check/fix" contains "fix")
                        if (modeHint.includes(mode)) return true;
                        // Active mode contains the mode hint (e.g., "subtypes" contains "subtype")
                        if (mode.includes(modeHint)) return true;
                        // Mode hint contains the active mode with word boundaries
                        // (e.g., "import" matches "[Import mode]")
                        if (modeHint.split(/[\/\s]+/).includes(mode)) return true;
                        if (mode.split(/[\/\s]+/).includes(modeHint)) return true;
                        return false;
                    });

                    if (shouldShow) {
                        argDiv.style.display = 'block';
                    } else {
                        argDiv.style.display = 'none';
                        // Clear value when hiding
                        if (input.type === 'checkbox') {
                            input.checked = false;
                        } else if (input.tagName !== 'SELECT' || !input.multiple) {
                            input.value = '';
                        }
                    }
                } else {
                    // No mode hint - always show (common parameter)
                    argDiv.style.display = 'block';
                }
            });
        }

        // Apply parameter conflict detection
        function checkConflicts() {
            // Re-enable all visible inputs first
            argInputs.forEach(input => {
                const container = input.closest('.mb-3');
                // Only reset if visible
                if (container && container.style.display !== 'none') {
                    input.disabled = false;
                    container.style.opacity = '1';
                }
            });

            // Then apply conflict rules
            argInputs.forEach(input => {
                const dest = input.dataset.dest;
                const inputContainer = input.closest('.mb-3');

                // Skip if this input is hidden due to mode
                if (!dest || (inputContainer && inputContainer.style.display === 'none')) return;

                // Check if this input has value
                let hasValue = false;
                if (input.type === 'checkbox') {
                    hasValue = input.checked;
                } else if (input.tagName === 'SELECT' && input.multiple) {
                    hasValue = Array.from(input.selectedOptions).some(opt => opt.value);
                } else {
                    hasValue = input.value && input.value !== '';
                }

                // If this parameter has conflicts and has a value, disable conflicting params
                if (hasValue && conflictRules[dest]) {
                    conflictRules[dest].forEach(conflictDest => {
                        const conflictInput = document.getElementById(`arg_${conflictDest}`);
                        const conflictContainer = conflictInput ? conflictInput.closest('.mb-3') : null;

                        // Only disable if visible and not already disabled by mode
                        if (conflictInput && conflictInput !== input &&
                            conflictContainer && conflictContainer.style.display !== 'none') {
                            conflictInput.disabled = true;
                            // Clear the value to avoid confusion
                            if (conflictInput.type === 'checkbox') {
                                conflictInput.checked = false;
                            } else if (conflictInput.tagName !== 'SELECT' || !conflictInput.multiple) {
                                // Don't clear multi-selects as they might have been deliberately set
                                if (!conflictInput.value) {
                                    conflictInput.value = '';
                                }
                            }
                            conflictContainer.style.opacity = '0.5';
                        }
                    });
                }
            });

            // Special case: cache_only requires barsukas_url
            const cacheOnlyInput = document.getElementById('arg_cache_only');
            const barsukasUrlInput = document.getElementById('arg_barsukas_url');
            if (cacheOnlyInput && cacheOnlyInput.checked && barsukasUrlInput) {
                barsukasUrlInput.required = true;
            } else if (barsukasUrlInput) {
                barsukasUrlInput.required = false;
            }
        }

        // Listen to all input changes
        argInputs.forEach(input => {
            input.addEventListener('change', function() {
                updateModeVisibility();
                checkConflicts();
            });
            input.addEventListener('input', function() {
                updateModeVisibility();
                checkConflicts();
            });
        });

        // Initial checks
        updateModeVisibility();
        checkConflicts();

        // Generate command line
        function generateCommandLine() {
            const args = [`PYTHONPATH=src python src/agents/${agentName}.py`];

            argInputs.forEach(input => {
                const dest = input.dataset.dest;
                const argDiv = input.closest('[data-arg]');

                // Skip disabled or hidden parameters
                if (!dest || input.disabled || (argDiv && argDiv.style.display === 'none')) return;

                const argName = dest.replace(/_/g, '-');

                if (input.type === 'checkbox') {
                    if (input.checked) {
                        args.push(`--${argName}`);
                    }
                } else if (input.tagName === 'SELECT' && input.multiple) {
                    const selected = Array.from(input.selectedOptions).map(opt => opt.value).filter(v => v);
                    if (selected.length > 0) {
                        args.push(`--${argName}`);
                        args.push(...selected);
                    }
                } else if (input.value && input.value !== '') {
                    args.push(`--${argName}`);
                    // Quote values with spaces
                    if (input.value.includes(' ')) {
                        args.push(`"${input.value}"`);
                    } else {
                        args.push(input.value);
                    }
                }
            });

            return args.join(' ');
        }

        // Generate command button
        if (generateBtn) {
            generateBtn.addEventListener('click', function(e) {
                e.preventDefault();
                const command = generateCommandLine();
                commandInput.value = command;
                commandPreview.style.display = 'block';
                commandPreview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            });
        }

        // Copy command button
        if (copyBtn) {
            copyBtn.addEventListener('click', function() {
                commandInput.select();
                document.execCommand('copy');

                // Visual feedback
                const icon = copyBtn.querySelector('i');
                const originalClass = icon.className;
                icon.className = 'bi bi-check';
                copyBtn.textContent = ' Copied!';
                copyBtn.prepend(icon);

                setTimeout(() => {
                    icon.className = originalClass;
                    copyBtn.textContent = ' Copy';
                    copyBtn.prepend(icon);
                }, 2000);
            });
        }

        // Toggle collapse icons
        document.querySelectorAll('[data-bs-toggle="collapse"]').forEach(trigger => {
            trigger.addEventListener('click', function() {
                const icon = this.querySelector('.toggle-icon');
                if (icon) {
                    setTimeout(() => {
                        const target = document.querySelector(this.dataset.bsTarget);
                        if (target && target.classList.contains('show')) {
                            icon.classList.remove('bi-chevron-right');
                            icon.classList.add('bi-chevron-down');
                        } else {
                            icon.classList.remove('bi-chevron-down');
                            icon.classList.add('bi-chevron-right');
                        }
                    }, 100);
                }
            });
        });
    }
}
