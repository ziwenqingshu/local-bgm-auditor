"""只检查本地依赖，不发网络请求。"""

import importlib.metadata
import platform
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
errors = []
print(f"OS: {platform.system()} / Python: {platform.python_version()}")
if sys.version_info[:2] != (3, 12):
    errors.append("Python 3.12 is required")
for executable in ("ffmpeg", "ffprobe"):
    location = shutil.which(executable)
    print(f"{executable}: {location or 'MISSING'}")
    if not location:
        errors.append(f"Missing {executable}")
for package in ("streamlit", "numpy", "scipy", "pandas", "pyarrow", "psutil", "filelock"):
    try:
        print(f"{package}: {importlib.metadata.version(package)}")
    except importlib.metadata.PackageNotFoundError:
        errors.append(f"Missing {package}")
if not (root / "vendor/audfprint/audfprint_analyze.py").is_file():
    errors.append("Missing bundled audfprint source")
try:
    print(f"ShazamIO (optional): {importlib.metadata.version('shazamio')}")
except importlib.metadata.PackageNotFoundError:
    print("ShazamIO: not installed (offline mode is fully functional)")
for message in errors:
    print("ERROR:", message, file=sys.stderr)
sys.exit(bool(errors))
