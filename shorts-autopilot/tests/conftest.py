import os
import sys
import tempfile
from pathlib import Path

# Base et sorties isolées pour les tests (jamais les vraies données)
_tmp = tempfile.mkdtemp(prefix="autopilot-tests-")
os.environ["DATA_DIR"] = f"{_tmp}/data"
os.environ["OUTPUT_DIR"] = f"{_tmp}/output"
os.environ["MODE"] = "test"
os.environ["NICHE"] = "tech_ai_en"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
