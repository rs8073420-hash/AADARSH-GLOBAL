import os

# Create middleware dir if not exist
os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'middleware'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'services'), exist_ok=True)
