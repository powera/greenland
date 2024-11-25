from jinja2 import Environment, FileSystemLoader
import math
import os

def get_color(score):
    """
    Convert a score (0-100) to an RGB color value.
    100 = bright green (0, 255, 0)
    Going down to red (255, 0, 0)
    """
    if score == 100:
        return "rgb(0, 255, 0)"
    
    # Convert score to a value between 0 and 1
    normalized = score / 100.0
    
    # Calculate red and green components
    red = int(40 + 215 * (1 - normalized))
    green = int(215 * normalized)
    
    return f"rgb({red}, {green}, 0)"

# Sample data
data = {
<<<<<<< Updated upstream
    'llms': ['USA', 'UK', 'France', 'Germany', 'Japan'],
    'tests': ['Performance', 'Reliability', 'Security', 'Scalability'],
    'scores': {
        ('Performance', 'USA'): 100,
        ('Performance', 'UK'): 92,
        ('Performance', 'France'): 88,
        ('Performance', 'Germany'): 95,
        ('Performance', 'Japan'): 97,
        ('Reliability', 'USA'): 89,
        ('Reliability', 'UK'): 64,
        ('Reliability', 'France'): 75,
        ('Reliability', 'Germany'): 41,
        ('Reliability', 'Japan'): 93,
        ('Security', 'USA'): 85,
        ('Security', 'UK'): 88,
        ('Security', 'France'): 90,
        ('Security', 'Germany'): 14,
        ('Security', 'Japan'): 92,
        ('Scalability', 'USA'): 93,
        ('Scalability', 'UK'): 87,
        ('Scalability', 'France'): 82,
        ('Scalability', 'Germany'): 88,
        ('Scalability', 'Japan'): 91,
=======
    'llms': ['gemma2:9b', 'qwen3.5:3.7b', 'mistral-nemo:12b', 'phi3.5:3.8b', 'llama3.2:3b'],
    'tests': ['0015_SPELL_CHECK', 'Reliability', 'Security', 'Scalability'],
    'scores': {
        ('0015_SPELL_CHECK', 'gemma2:9b'): 97,
        ('0015_SPELL_CHECK', 'qwen3.5:3.7b'): 92,
        ('0015_SPELL_CHECK', 'mistral-nemo:12b'): 69,
        ('0015_SPELL_CHECK', 'phi3.5:3.8b'): 53,
        ('0015_SPELL_CHECK', 'llama3.2:3b'): 54,
        ('Reliability', 'gemma2:9b'): 89,
        ('Reliability', 'qwen3.5:3.7b'): 64,
        ('Reliability', 'mistral-nemo:12b'): 75,
        ('Reliability', 'phi3.5:3.8b'): 41,
        ('Reliability', 'llama3.2:3b'): 93,
        ('Security', 'gemma2:9b'): 85,
        ('Security', 'qwen3.5:3.7b'): 88,
        ('Security', 'mistral-nemo:12b'): 90,
        ('Security', 'phi3.5:3.8b'): 14,
        ('Security', 'llama3.2:3b'): 92,
        ('Scalability', 'gemma2:9b'): 93,
        ('Scalability', 'qwen3.5:3.7b'): 87,
        ('Scalability', 'mistral-nemo:12b'): 82,
        ('Scalability', 'phi3.5:3.8b'): 88,
        ('Scalability', 'llama3.2:3b'): 91,
>>>>>>> Stashed changes
    }
}

# Set up Jinja2 environment
current_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(os.path.dirname(current_dir), 'templates')

env = Environment(loader=FileSystemLoader(template_dir))
template = env.get_template('model_scores.html')

# Add color information to the data
for key in data['scores']:
    score = data['scores'][key]
    data['scores'][key] = {
        'value': score,
        'color': get_color(score)
    }

# Render template
output = template.render(data=data)

# Write to file
with open('output/model_summary.html', 'w') as f:
    f.write(output)
