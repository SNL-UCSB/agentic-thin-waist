import sys
import tempfile
from pathlib import Path
import os

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    SHARED_DIR = Path(__file__).resolve().parents[3] / "shared"
except IndexError:
    SHARED_DIR = Path("/shared")
if SHARED_DIR.is_dir() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

TEST_RUNTIME_DIR = Path(tempfile.gettempdir()) / "substrate-worker-tests"
os.environ.setdefault("CAPTURE_DIR", str(TEST_RUNTIME_DIR / "captures"))
os.environ.setdefault("CTP_DIR", str(TEST_RUNTIME_DIR / "ctp"))
