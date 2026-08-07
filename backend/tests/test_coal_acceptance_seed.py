from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from lab_models import CoalGrade, Supplier
from scripts.seed_coal_acceptance_directories import COAL_GRADES, SUPPLIERS, seed


def test_seed_is_idempotent_and_dry_run_does_not_write():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    preview = seed(db, apply=False)
    assert preview['created_suppliers'] == len(SUPPLIERS)
    assert db.query(Supplier).count() == 0

    first = seed(db, apply=True)
    second = seed(db, apply=True)
    assert first['created_suppliers'] == len(SUPPLIERS)
    assert first['created_coal_grades'] == len(COAL_GRADES)
    assert second == {'created_suppliers': 0, 'created_coal_grades': 0, 'existing': 7}
    assert db.query(Supplier).count() == 4
    assert db.query(CoalGrade).count() == 3
