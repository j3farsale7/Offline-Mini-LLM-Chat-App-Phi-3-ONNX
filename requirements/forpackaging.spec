#.spec
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

#Hidden imports for runtime dependencies
hidden_imports = (
    collect_submodules('onnxruntime_genai') +
    collect_submodules('numpy') +
    [
        'bs4',
        'readability.readability',
        'playwright.async_api',
        'httpx',
        'aiofiles',
        'tkinter',
    ]
)

#NumPy shared libraries
numpy_data = collect_data_files('numpy')

#model folder
model_name = "Phi-3-mini-4k-instruct-onnx"
model_data = []
if os.path.exists(model_name):
    model_data.append((os.path.join(model_name, "**", "*"), model_name))
else:
    print(f"Model directory '{model_name}' not found. Make sure it exists next to my_app.spec")

#Data: Playwright browser binaries (dynamic path) ===
playwright_browsers = []
playwright_path = os.path.join(os.getcwd(), "ms-playwright")
if os.path.exists(playwright_path):
    playwright_browsers.append((os.path.join("ms-playwright", "**", "*"), "ms-playwright"))
else:
    print("Playwright browser path not found. You may need to run:")
    print("playwright install-deps && playwright install chromium")

#Analysis
a = Analysis(
    ['GUI.py'],                     # Main entry script
    pathex=['.'],
    binaries=[],
    datas=numpy_data + model_data + playwright_browsers + [("config.json", ".")],
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

#packaging
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='Offline MiniLLM ChatAPP (Phi-3)',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico' if os.path.exists('icon.ico') else None
)