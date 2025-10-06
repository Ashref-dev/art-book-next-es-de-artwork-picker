#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
ES-DE Art Book Next Theme - Interactive Artwork Picker
═══════════════════════════════════════════════════════════════════════════

A web-based tool to browse and select custom system carousel artwork.
For each console, view slanted previews of all available game images,
then pick your favorite to use as the system background.

REQUIREMENTS:
    - Python 3.8+
    - Pillow (pip install pillow)
    - Flask (pip install flask)

USAGE:
    1. Place this script in the theme's root directory
    2. Run: python3 artwork_picker.py
    3. Open http://localhost:5000 in your browser
    4. Select console → Browse images → Click to select → Save

CONFIGURATION:
    Edit the paths below if your setup differs from defaults.

═══════════════════════════════════════════════════════════════════════════
"""

import sys
import io
import base64
from pathlib import Path
from typing import Optional, List, Dict

# Check dependencies
try:
    from PIL import Image
except ImportError:
    print("❌ ERROR: Pillow not installed")
    print("   Install: pip3 install pillow")
    sys.exit(1)

try:
    from flask import Flask, render_template_string, jsonify, request
except ImportError:
    print("❌ ERROR: Flask not installed")
    print("   Install: pip3 install flask")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION - Adjust these paths for your setup
# ═══════════════════════════════════════════════════════════════════════════

# Auto-detect paths based on script location
SCRIPT_DIR = Path(__file__).resolve().parent
THEME_ROOT = SCRIPT_DIR  # Assumes script is in theme root

# ES-DE installation path - common locations tried automatically
ESDE_PATHS = [
    Path.home() / "ES-DE",
    Path.home() / "Library/Application Support/ES-DE",
    Path("/Users") / Path.home().name / "ES-DE",
]

# Media priority (first non-empty folder used)
MEDIA_PRIORITY = ["fanart", "screenshots", "titlescreens", "miximages"]

# Systems to exclude
EXCLUDE_SYSTEMS = {'backups', 'backup', 'backups_old', 'ports', 'port', 'hacks', 'hack', 'parts'}

# Artwork directories (relative to theme root)
ARTWORK_DIR_NAMES = [
    '_inc/systems/artwork',
    '_inc/systems/artwork-noir',
    '_inc/systems/artwork-circuit',
    '_inc/systems/artwork-outline',
    '_inc/systems/artwork-screenshots',
]

# ═══════════════════════════════════════════════════════════════════════════
# CORE FUNCTIONALITY
# ═══════════════════════════════════════════════════════════════════════════

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

def find_esde_root() -> Optional[Path]:
    """Auto-detect ES-DE installation directory."""
    for path in ESDE_PATHS:
        if path.exists() and (path / "downloaded_media").is_dir():
            return path
    return None

def find_system_dirs(media_root: Path) -> List[Path]:
    """Get all system directories from media root."""
    systems = []
    for child in media_root.iterdir():
        if child.is_dir():
            systems.append(child)
    return systems

def collect_candidate_images(system_dir: Path) -> List[Path]:
    """Collect game images for a system (priority order: fanart → screenshots → titlescreens → miximages)."""
    for subfolder in MEDIA_PRIORITY:
        folder = system_dir / subfolder
        images = []
        if folder.is_dir():
            for img in folder.rglob('*'):
                if img.suffix.lower() in IMAGE_EXTS and img.is_file():
                    images.append(img)
        if images:
            return images  # Return first non-empty tier
    return []

def load_mask_alpha(theme_root: Path) -> Optional[Image.Image]:
    """Extract alpha channel from original artwork to use as slant mask."""
    base_art = theme_root / '_inc/systems/artwork'
    if not base_art.is_dir():
        return None
    originals = sorted([p for p in base_art.iterdir() 
                      if p.suffix.lower() == '.png' and p.name != '_default.png'])
    if not originals:
        return None
    try:
        img = Image.open(originals[0]).convert('RGBA')
        *_, alpha = img.split()
        return alpha
    except Exception as e:
        print(f"⚠️  Failed to load mask: {e}")
        return None

def composite(shot: Image.Image, mask_alpha: Image.Image) -> Image.Image:
    """Composite a screenshot with the slanted alpha mask."""
    base = shot.convert("RGBA")
    ow, oh = mask_alpha.size
    
    # Resize/crop to mask size
    if base.size != (ow, oh):
        bw, bh = base.size
        base_aspect = bw / bh
        target_aspect = ow / oh
        
        if base_aspect > target_aspect:
            new_h = oh
            new_w = int(new_h * base_aspect)
        else:
            new_w = ow
            new_h = int(new_w / base_aspect)
        
        scaled = base.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - ow) // 2
        top = (new_h - oh) // 2
        base = scaled.crop((left, top, left + ow, top + oh))
    
    # Apply mask
    r, g, b, a = base.split()
    if mask_alpha.size != base.size:
        mask_alpha = mask_alpha.resize(base.size, Image.LANCZOS)
    base.putalpha(mask_alpha)
    return base

def image_to_base64(img: Image.Image) -> str:
    """Convert PIL Image to base64 for web display."""
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# ═══════════════════════════════════════════════════════════════════════════
# WEB APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.config['SECRET_KEY'] = 'esde-artwork-picker-2025'

# Global state
systems_cache: List[Dict] = []
mask_alpha: Optional[Image.Image] = None
media_root: Optional[Path] = None
artwork_dirs: List[Path] = []

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Art Book Next - Artwork Picker</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e1e1e 0%, #2b2b2b 100%);
            color: #fff;
            display: flex;
            height: 100vh;
            overflow: hidden;
        }
        #sidebar {
            width: 280px;
            background: rgba(43, 43, 43, 0.95);
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            flex-direction: column;
            box-shadow: 2px 0 20px rgba(0, 0, 0, 0.3);
        }
        #sidebar h1 {
            padding: 25px 20px;
            font-size: 16px;
            font-weight: 600;
            background: rgba(0, 120, 212, 0.15);
            border-bottom: 2px solid #0078d4;
            letter-spacing: 0.5px;
        }
        #systems-list {
            flex: 1;
            overflow-y: auto;
            padding: 15px 10px;
        }
        #systems-list::-webkit-scrollbar {
            width: 8px;
        }
        #systems-list::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.2);
        }
        #systems-list::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 4px;
        }
        .system-item {
            padding: 14px 18px;
            margin: 6px 0;
            background: rgba(30, 30, 30, 0.6);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid transparent;
            font-size: 14px;
        }
        .system-item:hover {
            background: rgba(54, 54, 54, 0.8);
            transform: translateX(4px);
            border-color: rgba(0, 120, 212, 0.3);
        }
        .system-item.active {
            background: linear-gradient(135deg, #0078d4 0%, #005a9e 100%);
            border-color: #0078d4;
            box-shadow: 0 4px 12px rgba(0, 120, 212, 0.4);
        }
        #main {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        #topbar {
            padding: 20px 35px;
            background: rgba(43, 43, 43, 0.95);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 15px rgba(0, 0, 0, 0.2);
        }
        #status {
            font-size: 16px;
            font-weight: 500;
            color: #e0e0e0;
        }
        #save-btn {
            padding: 14px 32px;
            background: linear-gradient(135deg, #0078d4 0%, #005a9e 100%);
            border: none;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 12px rgba(0, 120, 212, 0.3);
            letter-spacing: 0.3px;
        }
        #save-btn:disabled {
            background: linear-gradient(135deg, #555 0%, #444 100%);
            cursor: not-allowed;
            box-shadow: none;
            opacity: 0.6;
        }
        #save-btn:not(:disabled):hover {
            background: linear-gradient(135deg, #005a9e 0%, #004578 100%);
            box-shadow: 0 6px 20px rgba(0, 120, 212, 0.5);
            transform: translateY(-2px);
        }
        #save-btn:not(:disabled):active {
            transform: translateY(0);
        }
        #content {
            flex: 1;
            overflow-y: auto;
            padding: 35px;
        }
        #content::-webkit-scrollbar {
            width: 12px;
        }
        #content::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.2);
        }
        #content::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 6px;
        }
        #previews {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 25px;
        }
        .preview-card {
            background: rgba(43, 43, 43, 0.7);
            backdrop-filter: blur(5px);
            border-radius: 12px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 3px solid transparent;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        }
        .preview-card:hover {
            background: rgba(54, 54, 54, 0.9);
            transform: translateY(-6px) scale(1.02);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5);
        }
        .preview-card.selected {
            border-color: #0078d4;
            background: linear-gradient(135deg, rgba(0, 120, 212, 0.3) 0%, rgba(0, 90, 158, 0.3) 100%);
            box-shadow: 0 8px 30px rgba(0, 120, 212, 0.5);
            transform: translateY(-4px) scale(1.05);
        }
        .preview-card img {
            width: 100%;
            height: auto;
            border-radius: 8px;
            display: block;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
        }
        .preview-card .name {
            margin-top: 12px;
            font-size: 13px;
            text-align: center;
            color: #d0d0d0;
            word-wrap: break-word;
            line-height: 1.4;
        }
        .loader {
            text-align: center;
            padding: 120px;
            font-size: 18px;
            color: #999;
        }
        .spinner {
            border: 5px solid rgba(255, 255, 255, 0.1);
            border-top: 5px solid #0078d4;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 25px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .footer {
            padding: 15px 35px;
            background: rgba(30, 30, 30, 0.95);
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
            font-size: 12px;
            color: #888;
        }
    </style>
</head>
<body>
    <div id="sidebar">
        <h1>🎮 GAME SYSTEMS</h1>
        <div id="systems-list"></div>
    </div>
    <div id="main">
        <div id="topbar">
            <div id="status">Select a console from the left sidebar</div>
            <button id="save-btn" disabled>💾 Set as Console Artwork</button>
        </div>
        <div id="content">
            <div id="previews"></div>
        </div>
        <div class="footer">
            Art Book Next Theme • ES-DE Artwork Picker • Press Ctrl+C in terminal to exit
        </div>
    </div>

    <script>
        let systems = [];
        let currentSystem = null;
        let selectedIndex = null;
        let previews = [];

        fetch('/api/systems')
            .then(r => r.json())
            .then(data => {
                systems = data.systems;
                renderSystems();
            });

        function renderSystems() {
            const list = document.getElementById('systems-list');
            list.innerHTML = systems.map((sys, i) => 
                `<div class="system-item" onclick="selectSystem(${i})">${sys.name}</div>`
            ).join('');
        }

        function selectSystem(index) {
            currentSystem = systems[index];
            selectedIndex = null;
            
            document.querySelectorAll('.system-item').forEach((el, i) => {
                el.classList.toggle('active', i === index);
            });
            
            document.getElementById('status').textContent = `Loading ${currentSystem.name}...`;
            document.getElementById('save-btn').disabled = true;
            document.getElementById('previews').innerHTML = '<div class="loader"><div class="spinner"></div>Generating slanted previews...</div>';
            
            fetch(`/api/previews/${currentSystem.name}`)
                .then(r => r.json())
                .then(data => {
                    previews = data.previews;
                    renderPreviews();
                    document.getElementById('status').textContent = `${currentSystem.name}: ${previews.length} images available • Click to select`;
                });
        }

        function renderPreviews() {
            const container = document.getElementById('previews');
            container.innerHTML = previews.map((prev, i) => `
                <div class="preview-card" onclick="selectPreview(${i})">
                    <img src="data:image/png;base64,${prev.thumbnail}" alt="${prev.name}">
                    <div class="name">${prev.name}</div>
                </div>
            `).join('');
        }

        function selectPreview(index) {
            selectedIndex = index;
            document.querySelectorAll('.preview-card').forEach((el, i) => {
                el.classList.toggle('selected', i === index);
            });
            document.getElementById('save-btn').disabled = false;
            document.getElementById('status').textContent = `${currentSystem.name}: Selected "${previews[index].name}"`;
        }

        document.getElementById('save-btn').addEventListener('click', () => {
            if (selectedIndex === null || !currentSystem) return;
            
            const btn = document.getElementById('save-btn');
            btn.disabled = true;
            btn.textContent = '💾 Saving...';
            
            fetch('/api/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    system: currentSystem.name,
                    index: selectedIndex
                })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert(`✅ Artwork saved for ${currentSystem.name}\\n\\nUpdated directories:\\n• ${data.saved.join('\\n• ')}`);
                    document.getElementById('status').textContent = `${currentSystem.name}: Artwork saved successfully! ✨`;
                } else {
                    alert('❌ Failed to save artwork');
                }
                btn.textContent = '💾 Set as Console Artwork';
                btn.disabled = false;
            });
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/systems')
def api_systems():
    return jsonify({'systems': systems_cache})

@app.route('/api/previews/<system_name>')
def api_previews(system_name):
    system_path = None
    for sys in systems_cache:
        if sys['name'] == system_name:
            system_path = Path(sys['path'])
            break
    
    if not system_path:
        return jsonify({'error': 'System not found'}), 404
    
    candidates = collect_candidate_images(system_path)
    previews = []
    
    for img_path in candidates:
        try:
            source_img = Image.open(img_path)
            comp = composite(source_img, mask_alpha)
            thumb = comp.copy()
            thumb.thumbnail((220, 220), Image.LANCZOS)
            thumb_b64 = image_to_base64(thumb)
            
            previews.append({
                'name': img_path.stem[:45],
                'thumbnail': thumb_b64,
                'path': str(img_path),
            })
        except Exception as e:
            print(f"⚠️  Failed to load {img_path.name}: {e}")
            continue
    
    return jsonify({'previews': previews})

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    system_name = data.get('system')
    index = data.get('index')
    
    if not system_name or index is None:
        return jsonify({'success': False}), 400
    
    system_path = None
    for sys in systems_cache:
        if sys['name'] == system_name:
            system_path = Path(sys['path'])
            break
    
    if not system_path:
        return jsonify({'success': False}), 404
    
    candidates = collect_candidate_images(system_path)
    if index >= len(candidates):
        return jsonify({'success': False}), 400
    
    try:
        source_img = Image.open(candidates[index])
        comp = composite(source_img, mask_alpha)
        
        saved = []
        for adir in artwork_dirs:
            if not adir.is_dir():
                continue
            out_path = adir / f"{system_name}.png"
            comp.save(out_path)
            saved.append(out_path.parent.name)
        
        return jsonify({'success': True, 'saved': saved})
    except Exception as e:
        print(f"❌ Save error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global systems_cache, mask_alpha, media_root, artwork_dirs
    
    print("\n" + "═" * 70)
    print("  ES-DE Art Book Next Theme - Artwork Picker")
    print("═" * 70 + "\n")
    
    # Validate theme structure
    if not (THEME_ROOT / '_inc/systems/artwork').is_dir():
        print("❌ ERROR: Not in Art Book Next theme directory")
        print("   Place this script in the theme's root folder")
        sys.exit(1)
    
    # Find ES-DE installation
    print("🔍 Locating ES-DE installation...")
    esde_root = find_esde_root()
    if not esde_root:
        print("❌ ERROR: ES-DE installation not found")
        print("   Tried:")
        for p in ESDE_PATHS:
            print(f"     • {p}")
        print("\n   Ensure ES-DE is installed or edit ESDE_PATHS in the script")
        sys.exit(1)
    
    media_root = esde_root / "downloaded_media"
    print(f"✅ Found: {esde_root}")
    
    # Load mask
    print("🎨 Loading slant mask from theme artwork...")
    mask_alpha = load_mask_alpha(THEME_ROOT)
    if not mask_alpha:
        print("❌ ERROR: Could not load mask alpha from theme artwork")
        sys.exit(1)
    print(f"✅ Mask loaded: {mask_alpha.size}")
    
    # Discover artwork directories
    artwork_dirs = [THEME_ROOT / d for d in ARTWORK_DIR_NAMES if (THEME_ROOT / d).is_dir()]
    if not artwork_dirs:
        print("❌ ERROR: No artwork directories found")
        sys.exit(1)
    print(f"✅ Artwork directories: {len(artwork_dirs)}")
    
    # Discover systems
    print("🎮 Discovering game systems...")
    all_systems = find_system_dirs(media_root)
    filtered = [s for s in all_systems if s.name.lower() not in EXCLUDE_SYSTEMS]
    systems_cache = [{'name': s.name, 'path': str(s)} for s in sorted(filtered, key=lambda x: x.name)]
    print(f"✅ Found: {len(systems_cache)} systems")
    
    # Start server
    print("\n" + "═" * 70)
    print("  🚀 SERVER READY")
    print("═" * 70)
    print("\n  Open in your browser:")
    print("    👉 http://localhost:5000\n")
    print("  Press Ctrl+C to stop the server")
    print("═" * 70 + "\n")
    
    try:
        app.run(debug=False, host='127.0.0.1', port=5000)
    except KeyboardInterrupt:
        print("\n\n✨ Server stopped. Goodbye!\n")

if __name__ == '__main__':
    main()
