"""
The entry point Vercel runs. It adds the repository root to the import path and
hands over the same FastAPI app that `make run` serves locally.
Nothing in the app knows it is on Vercel apart from where it keeps its data.
Leaves out: anything environment specific, which belongs in app/config.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

__all__ = ["app"]
