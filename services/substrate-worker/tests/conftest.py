import sys
import tempfile
from pathlib import Path
import os

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

TEST_RUNTIME_DIR = Path(tempfile.gettempdir()) / "substrate-worker-tests"
os.environ.setdefault("CAPTURE_DIR", str(TEST_RUNTIME_DIR / "captures"))
os.environ.setdefault("CTP_DIR", str(TEST_RUNTIME_DIR / "ctp"))
