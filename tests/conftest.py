import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The project's modules live in rag/ and ingest/, not in an installed package
sys.path.insert(0, str(ROOT / "rag"))
sys.path.insert(0, str(ROOT / "ingest"))
