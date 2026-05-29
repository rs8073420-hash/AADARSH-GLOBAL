import os
import re

template_dir = r"C:\Users\Futur\Downloads\richa global\app\templates"

replacements = {
    '/api/admin/leads': '/api/leads',
    '/api/admin/events': '/api/calendar',
    '/api/admin/gamification': '/api/gamification',
    '/api/admin/activity': '/api/activity',
    '/api/admin/notifications': '/api/notifications',
    '/api/admin/notes': '/api/notes',
    '/api/admin/productivity': '/api/productivity'
}

count = 0
for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            for old, new in replacements.items():
                new_content = new_content.replace(old, new)
                
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                count += 1
                print(f"Fixed {file}")

print(f"Total files fixed: {count}")
