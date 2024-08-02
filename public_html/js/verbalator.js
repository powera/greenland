function submitVerbalator(event) {
    event.preventDefault(); // Prevent the form from submitting normally

    showLoading();

    // Get the form data
    const form = document.getElementById('verbalator');
    const formData = new FormData(form);
    const prompt = formData.get('prompt');
    const entry = formData.get('entry');
    const model = formData.get('model') || 'phi'; // Default to 'phi' if not specified

    // Prepare the request data
    const requestData = {
        prompt: prompt,
        entry: entry,
        model: model
    };

    // Make the AJAX call
    fetch('/query', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        // Handle the successful response
        console.log('Success:', data);
        document.getElementById('result').textContent = data.response;
    })
    .catch(error => {
        // Handle any errors
        console.error('Error:', error);
        document.getElementById('result').textContent = 'An error occurred: ' + error.message;
    })
    .finally(() => {
        hideLoading();
    });
}

// Attach the function to the form's submit event
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('verbalator');
    if (form) {
        form.addEventListener('submit', submitVerbalator);
    }
});

function showLoading() {
    document.getElementById('loading').style.display = 'block';
    document.getElementById('result').textContent = '';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}
