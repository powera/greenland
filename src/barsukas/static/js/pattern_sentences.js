// Pattern Sentences JavaScript Module

/**
 * Initialize the pattern sentences page
 * @param {Object} config - Configuration object
 * @param {string} config.generateCandidatesUrl - URL for generate candidates endpoint
 * @param {string} config.submitBatchUrl - URL for submit batch endpoint
 * @param {string} config.batchStatusUrl - URL for batch status endpoint
 */
function initPatternSentences(config) {
    // Handle "All Patterns" checkbox
    document.getElementById('pattern_all').addEventListener('change', function(e) {
        const checkboxes = document.querySelectorAll('.pattern-checkbox');
        checkboxes.forEach(cb => {
            cb.disabled = e.target.checked;
            if (e.target.checked) {
                cb.checked = false;
            }
        });
    });

    // Uncheck "All Patterns" when individual pattern is selected
    document.querySelectorAll('.pattern-checkbox').forEach(cb => {
        cb.addEventListener('change', function() {
            if (this.checked) {
                document.getElementById('pattern_all').checked = false;
            }
        });
    });

    // Handle candidate generation form submission
    document.getElementById('generateCandidatesForm').addEventListener('submit', async function(e) {
        e.preventDefault();

        const submitBtn = document.getElementById('generateCandidatesBtn');
        const outputSection = document.getElementById('candidatesOutputSection');
        const progressSpinner = document.getElementById('candidatesProgressSpinner');
        const output = document.getElementById('candidatesOutput');

        // Show output section
        outputSection.style.display = 'block';
        progressSpinner.style.display = 'block';
        output.textContent = '';
        output.style.display = 'none';

        // Disable submit
        submitBtn.disabled = true;

        // Build form data
        const formData = new FormData(this);

        try {
            const response = await fetch(config.generateCandidatesUrl, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            // Hide spinner, show output
            progressSpinner.style.display = 'none';
            output.style.display = 'block';

            if (result.success) {
                output.textContent = result.stdout;
                if (result.stderr) {
                    output.textContent += '\n\nSTDERR:\n' + result.stderr;
                }
            } else {
                output.textContent = 'ERROR: ' + (result.error || 'Generation failed');
                if (result.stdout) output.textContent += '\n\nSTDOUT:\n' + result.stdout;
                if (result.stderr) output.textContent += '\n\nSTDERR:\n' + result.stderr;
            }
        } catch (error) {
            progressSpinner.style.display = 'none';
            output.style.display = 'block';
            output.textContent = 'ERROR: ' + error.message;
        } finally {
            // Re-enable submit
            submitBtn.disabled = false;
        }
    });

    // Handle batch submission form
    document.getElementById('submitBatchForm').addEventListener('submit', async function(e) {
        e.preventDefault();

        const submitBtn = document.getElementById('submitBatchBtn');
        const outputSection = document.getElementById('batchOutputSection');
        const progressSpinner = document.getElementById('batchProgressSpinner');
        const output = document.getElementById('batchOutput');

        // Show output section
        outputSection.style.display = 'block';
        progressSpinner.style.display = 'block';
        output.textContent = '';
        output.style.display = 'none';

        // Disable submit
        submitBtn.disabled = true;

        // Build form data
        const formData = new FormData(this);

        try {
            const response = await fetch(config.submitBatchUrl, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            // Hide spinner, show output
            progressSpinner.style.display = 'none';
            output.style.display = 'block';

            if (result.success) {
                output.textContent = result.stdout;
                if (result.stderr) {
                    output.textContent += '\n\nSTDERR:\n' + result.stderr;
                }
            } else {
                output.textContent = 'ERROR: ' + (result.error || 'Batch submission failed');
                if (result.stdout) output.textContent += '\n\nSTDOUT:\n' + result.stdout;
                if (result.stderr) output.textContent += '\n\nSTDERR:\n' + result.stderr;
            }
        } catch (error) {
            progressSpinner.style.display = 'none';
            output.style.display = 'block';
            output.textContent = 'ERROR: ' + error.message;
        } finally {
            // Re-enable submit
            submitBtn.disabled = false;
        }
    });

    // Handle batch status check
    document.getElementById('checkStatusBtn').addEventListener('click', async function() {
        const statusBtn = this;
        const outputSection = document.getElementById('statusOutputSection');
        const output = document.getElementById('statusOutput');

        // Disable button temporarily
        statusBtn.disabled = true;
        output.textContent = 'Loading...';
        outputSection.style.display = 'block';

        try {
            const response = await fetch(config.batchStatusUrl);
            const result = await response.json();

            if (result.success) {
                output.textContent = result.stdout;
                if (result.stderr) {
                    output.textContent += '\n\nSTDERR:\n' + result.stderr;
                }

                // Parse batch IDs from output and create clickable links
                const batchIdRegex = /Batch: (batch_[a-zA-Z0-9]+)/g;
                const batchIds = [];
                let match;
                while ((match = batchIdRegex.exec(result.stdout)) !== null) {
                    batchIds.push(match[1]);
                }

                if (batchIds.length > 0) {
                    const batchListDiv = document.getElementById('statusBatchList');
                    batchListDiv.innerHTML = '<p><strong>Quick Actions:</strong></p>';
                    batchIds.forEach(batchId => {
                        const btn = document.createElement('button');
                        btn.className = 'btn btn-sm btn-outline-primary me-2 mb-2';
                        btn.textContent = `Check ${batchId}`;
                        btn.onclick = () => {
                            document.getElementById('batchIdInput').value = batchId;
                            document.getElementById('checkBatchBtn').click();
                        };
                        batchListDiv.appendChild(btn);
                    });
                }
            } else {
                output.textContent = 'ERROR: ' + (result.error || 'Failed to fetch status');
                if (result.stdout) output.textContent += '\n\nSTDOUT:\n' + result.stdout;
                if (result.stderr) output.textContent += '\n\nSTDERR:\n' + result.stderr;
            }
        } catch (error) {
            output.textContent = 'ERROR: ' + error.message;
        } finally {
            statusBtn.disabled = false;
        }
    });

    // Handle specific batch check
    document.getElementById('checkBatchBtn').addEventListener('click', async function() {
        const batchId = document.getElementById('batchIdInput').value.trim();
        if (!batchId) {
            alert('Please enter a batch ID');
            return;
        }

        const checkBtn = this;
        const outputSection = document.getElementById('batchCheckOutputSection');
        const progressSpinner = document.getElementById('batchCheckProgressSpinner');
        const output = document.getElementById('batchCheckOutput');

        // Show output section
        outputSection.style.display = 'block';
        progressSpinner.style.display = 'block';
        output.textContent = '';
        output.style.display = 'none';

        // Disable button
        checkBtn.disabled = true;

        try {
            console.log('Fetching batch status for:', batchId);
            const response = await fetch(`/pattern-sentences/check-batch/${batchId}`);
            console.log('Response status:', response.status);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            console.log('Result:', result);

            // Hide spinner, show output
            progressSpinner.style.display = 'none';
            output.style.display = 'block';

            if (result.success) {
                // Logging goes to stderr, so show that as main output
                output.textContent = '=== BATCH STATUS ===\n' + (result.stderr || result.stdout);

                // If batch was completed and retrieved
                if (result.is_completed && result.retrieve_success) {
                    output.textContent += '\n\n=== RETRIEVAL RESULTS ===\n' + (result.retrieve_stderr || result.retrieve_stdout);
                    output.textContent += '\n\n✓ Batch results successfully retrieved and applied to database!';
                } else if (result.is_completed && result.retrieve_success === false) {
                    output.textContent += '\n\n✗ Batch is completed but retrieval failed.';
                    if (result.retrieve_stderr) {
                        output.textContent += '\n\nRETRIEVAL ERROR:\n' + result.retrieve_stderr;
                    }
                } else if (!result.is_completed) {
                    output.textContent += '\n\nℹ Batch is not yet completed. Check back later.';
                }
            } else {
                output.textContent = 'ERROR: ' + (result.error || 'Failed to check batch');
                if (result.stdout) output.textContent += '\n\nSTDOUT:\n' + result.stdout;
                if (result.stderr) output.textContent += '\n\nSTDERR:\n' + result.stderr;
            }
        } catch (error) {
            console.error('Batch check error:', error);
            progressSpinner.style.display = 'none';
            output.style.display = 'block';
            output.textContent = 'ERROR: ' + error.message + '\n\nCheck browser console for details.';
        } finally {
            checkBtn.disabled = false;
        }
    });

    // Allow Enter key in batch ID input
    document.getElementById('batchIdInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            document.getElementById('checkBatchBtn').click();
        }
    });
}
