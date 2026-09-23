"""python -m scripts.validate_data [--path FILE]. Не изменяет исходный CSV."""
import argparse
import json
from pathlib import Path

from backend.app.catalog import CatalogError, load_catalog
from backend.app.config import DEFAULT_DATA_PATH, configured_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка CSV-каталога")
    parser.add_argument("--path", type=Path,
                        default=configured_path("DATA_PATH", DEFAULT_DATA_PATH))
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.path)
    except CatalogError as exc:
        print(json.dumps({"error": exc.code, "issues": [x.model_dump() for x in exc.issues]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"data_version": catalog.data_version, **catalog.report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
