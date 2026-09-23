import csv
from pathlib import Path

import pytest

from backend.app.catalog import CatalogError, load_catalog
from backend.app.config import DEFAULT_DATA_PATH, ROOT


def test_actual_catalog_import(catalog):
    report = catalog.report
    assert report["record_count"] == report["unique_ids"] == 66
    assert report["values"]["cities"] == {"Алматы": 50, "Астана": 15, "Зарубежье": 1}
    assert report["flags"]["synthetic"]["true"] == 13
    assert report["flags"]["price_imputed"]["true"] == 18
    assert report["flags"]["city_imputed"]["true"] == 8
    assert report["multiple_categories"] == 13
    assert report["null_max_hours"] == 9
    assert catalog.sha256 == "6a724b6b7dfb5973343e68ba18dadb60fc807d87e3d78f03ee86fb26cb089f7d"
    with (ROOT / DEFAULT_DATA_PATH).open(encoding="utf-8-sig", newline="") as source:
        original = {row["id"]: row for row in csv.DictReader(source)}
    for profile in catalog.profiles:
        assert profile.description == original[profile.id]["description"]
        assert type(profile.price_from_kzt) is int


@pytest.mark.parametrize("field,value", [
    ("synthetic", "maybe"), ("city_imputed", "false"), ("price_imputed", "1"),
    ("price_from_kzt", "1.5"), ("price_from_kzt", "0"), ("price_from_kzt", ""),
    ("max_hours", "nan"), ("max_hours", "-1"), ("max_hours", "bad"),
    ("busy_dates", "2027-01-01"), ("busy_dates", "2026-10-32"),
    ("city", ""), ("city", "Неизвестный"), ("categories", "Несуществующая"),
    ("event_formats", ""), ("languages", "немецкий"),
])
def test_invalid_csv_reports_row_and_id(fixture_path, tmp_path, field, value):
    with fixture_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        row = next(reader)
        headers = reader.fieldnames
    row[field] = value
    path = tmp_path / "invalid.csv"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert exc.value.code == "dataset_invalid"
    assert exc.value.issues[0].line == 2
    assert exc.value.issues[0].id == "TEST-001"


def test_duplicate_id_is_not_partial_success(fixture_path, tmp_path):
    text = fixture_path.read_text(encoding="utf-8")
    path = tmp_path / "duplicate.csv"
    path.write_text(text + text.splitlines()[1] + "\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="Повторяющийся id"):
        load_catalog(path)


def test_empty_and_missing(tmp_path):
    path = tmp_path / "missing.csv"
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert exc.value.code == "dataset_missing"
    path.write_text("", encoding="utf-8")
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert exc.value.code == "dataset_invalid"
