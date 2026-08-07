"""Idempotent seed for coal-acceptance directories. Nothing is written without --apply."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal
from lab_models import CoalGrade, Supplier

SUPPLIERS = (
    ('TALTEK', 'ООО "Разрез ТалТЭК"'),
    ('SIBCOAL', 'ООО "УК"СИБКОУЛ"'),
    ('TALDINSKAYA_TRADE', 'Талдинская Трейд. Комп.'),
    ('KTC', 'АО "Кузбасская топливная компания"'),
)
COAL_GRADES = (
    ('GR_0_200', 'ГР 0-200'),
    ('DR_0_300', 'Др (0-300)'),
    ('DOMSH_0_50', 'Домсш (0-50)'),
)


def _key(value: str) -> str:
    return ' '.join(value.split()).casefold()


def seed(db, *, apply: bool) -> dict[str, int]:
    result = {'created_suppliers': 0, 'created_coal_grades': 0, 'existing': 0}
    for model, values, counter in (
        (Supplier, SUPPLIERS, 'created_suppliers'),
        (CoalGrade, COAL_GRADES, 'created_coal_grades'),
    ):
        existing = {_key(row.name): row for row in db.query(model).all()}
        existing_codes = {row.code for row in existing.values() if row.code}
        for code, name in values:
            if _key(name) in existing:
                result['existing'] += 1
                continue
            if code in existing_codes:
                raise RuntimeError(f'Code {code!r} already belongs to another {model.__name__}')
            if apply:
                db.add(model(code=code, name=name, is_active=True))
            result[counter] += 1
    if apply:
        db.commit()
    else:
        db.rollback()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='commit missing rows')
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = seed(db, apply=args.apply)
        mode = 'APPLIED' if args.apply else 'DRY RUN'
        print(f'{mode}: {result}')
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
