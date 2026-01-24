// Settings JavaScript Module

/**
 * Copy text to clipboard from an input element
 * @param {string} elementId - ID of the input element to copy from
 */
function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    element.select();
    document.execCommand('copy');

    // Show feedback
    const button = event.target.closest('button');
    const originalHtml = button.innerHTML;
    button.innerHTML = 'Copied!';
    setTimeout(() => {
        button.innerHTML = originalHtml;
    }, 2000);
}

/**
 * Initialize the settings page
 * @param {Object} config - Configuration object
 * @param {string} config.restartUrl - URL for restart endpoint
 * @param {string} config.restartStatusUrl - URL for restart status endpoint
 * @param {string} config.settingsIndexUrl - URL for settings index page
 */
function initSettings(config) {
    window.restartBarsukas = function() {
        if (!confirm('Are you sure you want to restart Barsukas? This will wait for all active requests to complete before restarting.')) {
            return;
        }

        const statusDiv = document.getElementById('restart-status');
        const messageDiv = document.getElementById('restart-message');
        const restartButton = event.target.closest('button');

        // Disable button and show status
        restartButton.disabled = true;
        statusDiv.style.display = 'block';
        messageDiv.textContent = 'Initiating restart...';

        // Trigger restart
        fetch(config.restartUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                messageDiv.textContent = 'Waiting for active requests to complete...';

                // Poll for restart status
                const pollInterval = setInterval(() => {
                    fetch(config.restartStatusUrl)
                        .then(response => response.json())
                        .then(status => {
                            if (status.shutdown_requested) {
                                messageDiv.textContent = `Waiting for ${status.active_requests} active request(s) to complete...`;
                            }
                        })
                        .catch(err => {
                            // Connection lost - restart likely completed
                            clearInterval(pollInterval);
                            messageDiv.textContent = 'Restart completed. Waiting for server to come back online...';

                            // Try to reconnect
                            const reconnectInterval = setInterval(() => {
                                fetch(config.settingsIndexUrl)
                                    .then(response => {
                                        if (response.ok) {
                                            clearInterval(reconnectInterval);
                                            window.location.reload();
                                        }
                                    })
                                    .catch(() => {
                                        // Still waiting for server to restart
                                    });
                            }, 1000);
                        });
                }, 500);
            } else {
                messageDiv.textContent = 'Error: ' + (data.error || 'Unknown error');
                restartButton.disabled = false;
            }
        })
        .catch(error => {
            messageDiv.textContent = 'Error initiating restart: ' + error.message;
            restartButton.disabled = false;
        });
    };
}
