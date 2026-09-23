import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATE_MIN = date(2026, 9, 23)
DATE_MAX = date(2026, 12, 31)
CONTRACT_VERSION = "1.0.0"
RANKING_VERSION = "specialization-price-id-v1"
DEFAULT_DATA_PATH = "hackathon dataset anonymized .csv"


def configured_path(name: str, default: str) -> Path:
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else ROOT / path
