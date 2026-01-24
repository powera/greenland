// API Client JavaScript Module

/**
 * Initialize the API client page
 * @param {Object} config - Configuration object
 * @param {Object} config.endpointDescriptions - Map of endpoint paths to descriptions
 * @param {string} config.defaultServerUrl - Default server URL (window.location.origin)
 */
function initApiClient(config) {
    const endpointDescriptions = config.endpointDescriptions;

    // Update endpoint description and dynamic params when selection changes
    document.getElementById('endpoint').addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        const path = this.value;

        // Update description
        const descEl = document.getElementById('endpointDescription');
        descEl.textContent = endpointDescriptions[path] || '';

        // Update dynamic parameters
        const paramsContainer = document.getElementById('dynamicParams');
        paramsContainer.innerHTML = '';

        if (selectedOption.dataset.params) {
            const params = JSON.parse(selectedOption.dataset.params);
            params.forEach(param => {
                const div = document.createElement('div');
                div.className = 'mb-3';

                const label = document.createElement('label');
                label.className = 'form-label';
                label.htmlFor = 'param_' + param.name;
                label.textContent = param.label + (param.required ? ' *' : '');
                div.appendChild(label);

                if (param.type === 'select') {
                    const select = document.createElement('select');
                    select.className = 'form-select';
                    select.id = 'param_' + param.name;
                    select.name = param.name;
                    if (param.required) select.required = true;

                    param.options.forEach(opt => {
                        const option = document.createElement('option');
                        option.value = opt[0];
                        option.textContent = opt[1];
                        if (opt[0] === param.default) option.selected = true;
                        select.appendChild(option);
                    });
                    div.appendChild(select);
                } else {
                    const input = document.createElement('input');
                    input.type = param.type === 'number' ? 'number' : 'text';
                    input.className = 'form-control';
                    input.id = 'param_' + param.name;
                    input.name = param.name;
                    if (param.required) input.required = true;
                    if (param.default) input.value = param.default;
                    div.appendChild(input);
                }

                paramsContainer.appendChild(div);
            });
        }

        updateRequestPreview();
    });

    // Update preview when any form field changes
    document.getElementById('apiRequestForm').addEventListener('input', updateRequestPreview);
    document.getElementById('model').addEventListener('change', updateRequestPreview);
    document.getElementById('useSystemKey').addEventListener('change', function() {
        document.getElementById('apiKey').disabled = this.checked;
        updateRequestPreview();
    });

    function getProviderFromModel(model) {
        if (model.startsWith('gpt-')) return 'openai';
        if (model.startsWith('claude-')) return 'anthropic';
        if (model.startsWith('gemini-')) return 'google';
        return 'openai'; // default
    }

    function updateRequestPreview() {
        const endpoint = document.getElementById('endpoint').value;
        const serverUrl = document.getElementById('serverUrl').value || 'http://localhost:5000';
        const model = document.getElementById('model').value;

        if (!endpoint) {
            document.getElementById('requestPreview').textContent = 'Select an operation to see the request preview';
            return;
        }

        const requestBody = { model: model };

        // Add dynamic parameters
        const paramInputs = document.querySelectorAll('#dynamicParams input, #dynamicParams select');
        paramInputs.forEach(input => {
            if (input.value) {
                requestBody[input.name] = input.type === 'number' ? parseInt(input.value) : input.value;
            }
        });

        // Add API key placeholder
        const useSystemKey = document.getElementById('useSystemKey').checked;
        const provider = getProviderFromModel(model);
        requestBody[provider + '_api_key'] = useSystemKey ? '(system key)' : '(manual key)';

        const preview = `POST ${serverUrl}${endpoint}
Content-Type: application/json

${JSON.stringify(requestBody, null, 2)}`;

        document.getElementById('requestPreview').textContent = preview;
    }

    // Handle form submission
    document.getElementById('apiRequestForm').addEventListener('submit', async function(e) {
        e.preventDefault();

        const endpoint = document.getElementById('endpoint').value;
        const serverUrl = document.getElementById('serverUrl').value;
        const model = document.getElementById('model').value;
        const useSystemKey = document.getElementById('useSystemKey').checked;
        const manualApiKey = document.getElementById('apiKey').value;

        if (!endpoint) {
            alert('Please select an operation');
            return;
        }

        // Build request body
        const requestBody = { model: model };

        // Add dynamic parameters
        const paramInputs = document.querySelectorAll('#dynamicParams input, #dynamicParams select');
        paramInputs.forEach(input => {
            if (input.value) {
                requestBody[input.name] = input.type === 'number' ? parseInt(input.value) : input.value;
            }
        });

        // Get API key
        const provider = getProviderFromModel(model);
        let apiKey = manualApiKey;

        if (useSystemKey) {
            // Fetch system key from local server
            try {
                const keyResponse = await fetch('/api/llm/system-key/' + provider);
                const keyData = await keyResponse.json();
                if (keyData.success) {
                    apiKey = keyData.api_key;
                } else {
                    alert('System API key not available: ' + (keyData.error || 'Unknown error'));
                    return;
                }
            } catch (err) {
                alert('Failed to fetch system API key: ' + err.message);
                return;
            }
        }

        if (!apiKey) {
            alert('Please provide an API key or check "Use system API key"');
            return;
        }

        // Add API key to request
        requestBody[provider + '_api_key'] = apiKey;

        // Show loading state
        document.getElementById('responseLoading').style.display = 'block';
        document.getElementById('responseContent').innerHTML = '';
        document.getElementById('responseStatus').className = 'badge bg-secondary';
        document.getElementById('responseStatus').textContent = 'Sending...';
        document.getElementById('submitBtn').disabled = true;

        try {
            const response = await fetch(serverUrl + endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });

            const data = await response.json();

            // Update status
            if (data.success) {
                document.getElementById('responseStatus').className = 'badge bg-success';
                document.getElementById('responseStatus').textContent = 'Success';
            } else {
                document.getElementById('responseStatus').className = 'badge bg-danger';
                document.getElementById('responseStatus').textContent = 'Error';
            }

            // Display response
            document.getElementById('responseContent').innerHTML =
                '<pre>' + JSON.stringify(data, null, 2) + '</pre>';

        } catch (err) {
            document.getElementById('responseStatus').className = 'badge bg-danger';
            document.getElementById('responseStatus').textContent = 'Failed';
            document.getElementById('responseContent').innerHTML =
                '<div class="alert alert-danger">' +
                '<strong>Request failed:</strong> ' + err.message +
                '</div>';
        } finally {
            document.getElementById('responseLoading').style.display = 'none';
            document.getElementById('submitBtn').disabled = false;
        }
    });

    // Initialize with default server URL
    document.getElementById('serverUrl').value = config.defaultServerUrl;
}
