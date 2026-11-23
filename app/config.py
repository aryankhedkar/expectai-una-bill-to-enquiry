"""
Every setting the rest of the app depends on.
It lives in one file so the walkthrough gives the same answer on any day.
Leaves out: per-environment config files and secret management.
"""

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"

SAMPLES_DIR = ROOT / "samples"
FIXTURES_DIR = ROOT / "fixtures"
DOCS_DIR = ROOT / "docs"

# The demo treats this as today's date, so the checks and the countdown to the
# contract end date do not change from one day to the next.
TODAY = date(2026, 11, 23)

# A read value below this confidence becomes a question for the business owner.
CONFIDENCE_THRESHOLD = 0.85

# Two money figures are treated as agreeing if they are within five pence.
MONEY_TOLERANCE = 0.05

# "recorded" replays saved model output. "model" calls a live model.
READER = os.environ.get("READER", "recorded")
MODEL_NAME = os.environ.get("MODEL_NAME", "claude-sonnet-4-5")
MODEL_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
