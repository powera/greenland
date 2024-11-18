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
