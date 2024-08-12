function submitVerbalator(event) {
    event.preventDefault(); // Prevent the form from submitting normally

    showLoading();

    // Get the form data
    const form = document.getElementById('verbalator');
    const formData = new FormData(form);
    const prompt = formData.get('prompt');
    const entry = formData.get('entry');
    const model = formData.get('model') || 'phi'; // Default to 'phi' if not specified
    const verbosity = formData.get('verbosity');
    const reading_level = formData.get('reading_level');
    const creativity = formData.get('creativity');
    const politics = formData.get('politics');
    const sports = formData.get('sports');
    const celebrity = formData.get('celebrity');
    const science = formData.get('science');
    const religion = formData.get('religion');

    // Prepare the request data
    const requestData = {
        prompt: prompt,
        entry: entry,
        model: model,
        verbosity: verbosity,
        reading_level: reading_level,
        creativity: creativity,
        politics: politics,
        sports: sports,
        celebrity: celebrity,
        science: science,
        religion: religion,
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
        document.getElementById('info_block').style.display = 'block';
        document.getElementById('tokens_in').textContent = data.usage.tokens_in;
        document.getElementById('tokens_out').textContent = data.usage.tokens_out;
        document.getElementById('cost').textContent = "$" + data.usage.cost.toFixed(6);
        document.getElementById('reading_level').textContent = data.reading_level;
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
    document.getElementById('info_block').style.display = 'none';
    document.getElementById('tokens_in').textContent = '';
    document.getElementById('tokens_out').textContent = '';
    document.getElementById('cost').textContent = '';
    document.getElementById('reading_level').textContent = '';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}
