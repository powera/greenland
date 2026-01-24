// Exports JavaScript Module

/**
 * Helper function to escape HTML
 * @param {string} text - Text to escape
 * @returns {string} - Escaped HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize the ELNIAS export form
 * @param {Object} config - Configuration object
 * @param {string} config.generateUrl - URL for generate endpoint
 * @param {string} config.downloadUrlBase - Base URL for download endpoint
 */
function initElniasExport(config) {
    const form = document.getElementById('elniasForm');
    const generateBtn = document.getElementById('generateBtn');
    const outputContainer = document.getElementById('outputContainer');
    const outputContent = document.getElementById('outputContent');
    const statusBadge = document.getElementById('statusBadge');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Show loading state
        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Generating...';
        outputContainer.style.display = 'none';

        // Build form data
        const formData = new FormData();
        formData.append('language', document.getElementById('language').value);
        formData.append('include_unverified', document.getElementById('include_unverified').checked);

        try {
            // Execute generation
            const response = await fetch(config.generateUrl, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            // Show output
            outputContainer.style.display = 'block';

            if (result.success) {
                statusBadge.className = 'badge bg-success';
                statusBadge.textContent = 'Success';

                let outputHtml = '';

                // Show file path and download button if available
                if (result.output_path) {
                    outputHtml += `
                        <div class="alert alert-success mb-3">
                            <h6><i class="bi bi-check-circle"></i> Export Complete</h6>
                            <p class="mb-2"><strong>File saved to:</strong></p>
                            <code class="d-block mb-3 p-2 bg-light border rounded">${escapeHtml(result.output_path)}</code>
                            <a href="${config.downloadUrlBase}?path=${encodeURIComponent(result.output_path)}"
                               class="btn btn-primary btn-sm">
                                <i class="bi bi-download"></i> Download File
                            </a>
                        </div>
                    `;
                }

                // Show stdout output
                outputHtml += `<h6>Output:</h6><pre>${escapeHtml(result.stdout)}</pre>`;

                outputContent.innerHTML = outputHtml;
            } else {
                statusBadge.className = 'badge bg-danger';
                statusBadge.textContent = 'Error';
                outputContent.innerHTML = `
                    <div class="alert alert-danger">
                        <strong>Error:</strong> ${escapeHtml(result.error || 'Unknown error')}
                    </div>
                    ${result.stdout ? '<h6>Standard Output:</h6><pre>' + escapeHtml(result.stdout) + '</pre>' : ''}
                    ${result.stderr ? '<h6>Error Output:</h6><pre>' + escapeHtml(result.stderr) + '</pre>' : ''}
                `;
            }

            // Scroll to output
            outputContainer.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            outputContainer.style.display = 'block';
            statusBadge.className = 'badge bg-danger';
            statusBadge.textContent = 'Error';
            outputContent.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Error:</strong> ${escapeHtml(error.message)}
                </div>
            `;
        } finally {
            // Reset button
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<i class="bi bi-play-circle"></i> Generate Bootstrap File';
        }
    });
}

/**
 * Initialize the POVAS export form
 * @param {Object} config - Configuration object
 * @param {string} config.generateUrl - URL for generate endpoint
 */
function initPovasExport(config) {
    const form = document.getElementById('povasForm');
    const generateBtn = document.getElementById('generateBtn');
    const outputContainer = document.getElementById('outputContainer');
    const outputContent = document.getElementById('outputContent');
    const statusBadge = document.getElementById('statusBadge');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Show loading state
        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Generating...';
        outputContainer.style.display = 'none';

        // Build form data
        const formData = new FormData();
        formData.append('generation_mode', document.getElementById('generation_mode').value);
        formData.append('dry_run', document.getElementById('dry_run').checked);

        try {
            // Execute generation
            const response = await fetch(config.generateUrl, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            // Show output
            outputContainer.style.display = 'block';

            if (result.success) {
                statusBadge.className = 'badge bg-success';
                statusBadge.textContent = 'Success';
                outputContent.innerHTML = `<pre>${escapeHtml(result.stdout)}</pre>`;
            } else {
                statusBadge.className = 'badge bg-danger';
                statusBadge.textContent = 'Error';
                outputContent.innerHTML = `
                    <div class="alert alert-danger">
                        <strong>Error:</strong> ${escapeHtml(result.error || 'Unknown error')}
                    </div>
                    ${result.stdout ? '<h6>Standard Output:</h6><pre>' + escapeHtml(result.stdout) + '</pre>' : ''}
                    ${result.stderr ? '<h6>Error Output:</h6><pre>' + escapeHtml(result.stderr) + '</pre>' : ''}
                `;
            }

            // Scroll to output
            outputContainer.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            outputContainer.style.display = 'block';
            statusBadge.className = 'badge bg-danger';
            statusBadge.textContent = 'Error';
            outputContent.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Error:</strong> ${escapeHtml(error.message)}
                </div>
            `;
        } finally {
            // Reset button
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<i class="bi bi-play-circle"></i> Generate HTML';
        }
    });
}
