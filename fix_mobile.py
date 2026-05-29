import os

def fix_mobile_nav():
    app_dir = os.path.join(os.path.dirname(__file__), 'app', 'templates')
    
    # 1. Fix base.html (Dark Theme Sidebars)
    base_file = os.path.join(app_dir, 'base.html')
    if os.path.exists(base_file):
        with open(base_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'mobileMenuBtn' not in content:
            # Inject CSS and Button
            css_patch = """
        @media (max-width: 768px) {
            .sidebar { transform: translateX(-100%); transition: transform 0.3s ease; }
            .sidebar.mobile-open { transform: translateX(0) !important; box-shadow: 0 0 50px rgba(0,0,0,0.5); }
            #mobileMenuBtn { display: flex !important; }
        }
    </style>
"""
            content = content.replace('</style>', css_patch)
            
            js_patch = """
<button id="mobileMenuBtn" onclick="document.querySelector('.sidebar').classList.toggle('mobile-open')" style="display:none; position:fixed; bottom:20px; right:20px; width:56px; height:56px; border-radius:28px; background:var(--primary); color:#fff; border:none; z-index:99999; box-shadow:0 10px 25px rgba(99,102,241,0.5); align-items:center; justify-content:center; font-size:24px; cursor:pointer;">
    <i class="fas fa-bars"></i>
</button>
<script>
"""
            content = content.replace('<script>', js_patch, 1)
            
            with open(base_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Fixed base.html")

    # 2. Fix Tailwind Dashboards
    for dash in ['admin/dashboard.html', 'employee/dashboard.html']:
        dash_file = os.path.join(app_dir, dash)
        if os.path.exists(dash_file):
            with open(dash_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'mobileMenuBtn' not in content:
                # Replace hidden md:flex with responsive transform classes
                old_sidebar = '<aside class="w-64 glass-panel border-r border-slate-200/60 flex flex-col z-50 shrink-0 hidden md:flex shadow-xl shadow-slate-200/20">'
                new_sidebar = '<aside id="appSidebar" class="w-64 glass-panel border-r border-slate-200/60 flex flex-col z-50 shrink-0 fixed inset-y-0 left-0 transform -translate-x-full md:relative md:translate-x-0 transition-transform duration-300 ease-in-out shadow-2xl shadow-slate-900/20 md:shadow-xl md:shadow-slate-200/20 bg-white/95 md:bg-transparent">'
                
                content = content.replace(old_sidebar, new_sidebar)
                
                # Inject FAB
                btn_code = """
<!-- Mobile Menu Button -->
<button id="mobileMenuBtn" onclick="document.getElementById('appSidebar').classList.toggle('-translate-x-full')" class="md:hidden fixed bottom-6 right-6 w-14 h-14 rounded-full bg-indigo-600 text-white flex items-center justify-center text-2xl shadow-lg shadow-indigo-600/40 z-[100] transition-transform hover:scale-110">
    <i class="fas fa-bars"></i>
</button>
"""
                content = content.replace('</body>', btn_code + '\n</body>')
                
                with open(dash_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Fixed {dash}")

if __name__ == '__main__':
    fix_mobile_nav()
