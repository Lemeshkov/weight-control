import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal  # noqa: E402
# Register the shared and laboratory ORM tables in the same Base.metadata.
# This mirrors laboratory_main startup and is required to resolve users.id FKs.
import models  # noqa: E402,F401
from services.lab.fuel_quality_history_import import LegacyImportError, import_legacy_rows  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Безопасный импорт исторического журнала качества топлива")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, choices=range(1, 13), default=7)
    parser.add_argument("--workbook", type=Path, default=PROJECT_DIR / "docs" / "reference" / "Ежесуточный контроль топлива 2026.xlsx")
    parser.add_argument("--apply", action="store_true", help="записать проверенные строки в БД (по умолчанию dry-run)")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = import_legacy_rows(db, args.workbook, args.year, args.month, apply=args.apply)
    except LegacyImportError as exc:
        db.rollback()
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        db.rollback()
        print(f"ОШИБКА БД: {exc}", file=sys.stderr)
        return 3
    finally:
        db.close()
    mode = "DRY-RUN" if result.dry_run else "APPLY"
    print(f"{mode}: найдено={result.found}, уже_есть={result.existing}, импортировано={result.imported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
