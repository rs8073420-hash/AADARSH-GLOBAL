import os
import re

template_dir = r"C:\Users\Futur\Downloads\richa global\app\templates"

# Regex to match <div class="sidebar"> ... </div> (including nested divs)
# But a simple regex might fail on nested divs. Let's do a simple string search and replace,
# but it's risky if the HTML structure varies.
# Wait, actually since I generated all the HTML files, the structure is usually:
# <div class="sidebar">
# ...
# </div>
# <div class="main-content">
# 
# So I can use a regex that matches from <div class="sidebar"> up to <div class="main-content">.

sidebar_pattern = re.compile(r'<div class="sidebar">.*?</div>\s*<div class="main-content">', re.DOTALL)

count_admin = 0
count_employee = 0

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html') and file != 'base.html' and 'components' not in root:
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            if '<div class="sidebar">' in content:
                # determine role by path or content
                if 'employee' in filepath.lower():
                    replacement = "{% include 'components/employee_sidebar.html' %}\n\n<div class=\"main-content\">"
                    count_employee += 1
                else:
                    replacement = "{% include 'components/admin_sidebar.html' %}\n\n<div class=\"main-content\">"
                    count_admin += 1
                
                # We need a robust replacement strategy. Let's find the indices manually.
                start_idx = content.find('<div class="sidebar">')
                end_idx = content.find('<div class="main-content">', start_idx)
                
                if start_idx != -1 and end_idx != -1:
                    new_content = content[:start_idx] + replacement + content[end_idx + len('<div class="main-content">'):]
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)

print(f"Fixed {count_admin} admin sidebars and {count_employee} employee sidebars.")
