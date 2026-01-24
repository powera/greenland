// Audio List JavaScript Module

/**
 * Initialize the audio list page
 * @param {Object} config - Configuration object
 * @param {string} config.quickUpdateUrlBase - Base URL for quick update endpoint (with placeholder)
 */
function initAudioList(config) {
    // Create a single shared audio player
    const audioPlayer = new Audio();
    let currentPlayButton = null;

    // Play audio button handlers
    document.querySelectorAll('.play-audio-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const audioUrl = this.dataset.audioUrl;

            // If clicking the same button, toggle play/pause
            if (currentPlayButton === this && !audioPlayer.paused) {
                audioPlayer.pause();
                this.innerHTML = '<i class="bi bi-play-circle"></i>';
                return;
            }

            // Reset previous button
            if (currentPlayButton) {
                currentPlayButton.innerHTML = '<i class="bi bi-play-circle"></i>';
            }

            // Play new audio
            audioPlayer.src = audioUrl;
            audioPlayer.play();
            this.innerHTML = '<i class="bi bi-pause-circle"></i>';
            currentPlayButton = this;
        });
    });

    // Reset button when audio ends
    audioPlayer.addEventListener('ended', function() {
        if (currentPlayButton) {
            currentPlayButton.innerHTML = '<i class="bi bi-play-circle"></i>';
            currentPlayButton = null;
        }
    });

    // Quick approve handlers
    document.querySelectorAll('.quick-approve').forEach(btn => {
        btn.addEventListener('click', function() {
            const reviewId = this.dataset.id;
            quickUpdate(reviewId, 'approved', this);
        });
    });

    // Quick reject handlers
    document.querySelectorAll('.quick-reject').forEach(btn => {
        btn.addEventListener('click', function() {
            const reviewId = this.dataset.id;
            quickUpdate(reviewId, 'needs_replacement', this);
        });
    });

    function quickUpdate(reviewId, status, button) {
        button.disabled = true;
        const row = document.querySelector(`tr[data-review-id="${reviewId}"]`);

        fetch(config.quickUpdateUrlBase.replace('0', reviewId), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status: status })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Update status badge (6th column: GUID, Text, English, Language, Voice, Status)
                const statusCell = row.querySelector('td:nth-child(6)');
                if (status === 'approved') {
                    statusCell.innerHTML = '<span class="badge bg-success status-badge">Approved</span>';
                } else if (status === 'needs_replacement') {
                    statusCell.innerHTML = '<span class="badge bg-danger status-badge">Needs Replacement</span>';
                }
                // Flash success
                row.style.backgroundColor = '#d4edda';
                setTimeout(() => {
                    row.style.backgroundColor = '';
                }, 1000);
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            alert('Error updating status: ' + error);
        })
        .finally(() => {
            button.disabled = false;
        });
    }
}
