"""add historical Excel provenance to fuel quality tests

Revision ID: 20260809_01
Revises: 20260808_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260809_01"
down_revision = "20260808_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lab_fuel_quality_tests", sa.Column("source", sa.String(32), nullable=False, server_default="MANUAL"))
    op.add_column("lab_fuel_quality_tests", sa.Column("source_file", sa.String(500)))
    op.add_column("lab_fuel_quality_tests", sa.Column("source_sheet", sa.String(100)))
    op.add_column("lab_fuel_quality_tests", sa.Column("legacy_import_key", sa.String(255)))
    for name in ("calorimeter", "alpha", "hydrogen_input_percent", "qb_a_1_kcal_kg", "qb_a_2_kcal_kg", "lab_technician_name"):
        op.alter_column("lab_fuel_quality_tests", name, existing_type={
            "calorimeter": sa.String(100), "alpha": sa.Numeric(12, 8), "hydrogen_input_percent": sa.Numeric(9, 4),
            "qb_a_1_kcal_kg": sa.Numeric(14, 2), "qb_a_2_kcal_kg": sa.Numeric(14, 2),
            "lab_technician_name": sa.String(255),
        }[name], nullable=True)
    op.create_index("ix_lab_fuel_quality_tests_source", "lab_fuel_quality_tests", ["source"])
    op.create_index("ix_lab_fuel_quality_tests_legacy_import_key", "lab_fuel_quality_tests", ["legacy_import_key"], unique=True)


def downgrade():
    # These alterations fail safely before provenance is dropped if legacy NULLs still exist.
    for name, column_type in (("calorimeter", sa.String(100)), ("alpha", sa.Numeric(12, 8)),
        ("hydrogen_input_percent", sa.Numeric(9, 4)), ("qb_a_1_kcal_kg", sa.Numeric(14, 2)),
        ("qb_a_2_kcal_kg", sa.Numeric(14, 2)), ("lab_technician_name", sa.String(255))):
        op.alter_column("lab_fuel_quality_tests", name, existing_type=column_type, nullable=False)
    op.drop_index("ix_lab_fuel_quality_tests_legacy_import_key", table_name="lab_fuel_quality_tests")
    op.drop_index("ix_lab_fuel_quality_tests_source", table_name="lab_fuel_quality_tests")
    op.drop_column("lab_fuel_quality_tests", "legacy_import_key")
    op.drop_column("lab_fuel_quality_tests", "source_sheet")
    op.drop_column("lab_fuel_quality_tests", "source_file")
    op.drop_column("lab_fuel_quality_tests", "source")
