import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_app_path = os.path.join(APP_DIR, "app.py")
_spec = importlib.util.spec_from_file_location("zyntra_app", _app_path)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)

app = _module.app
