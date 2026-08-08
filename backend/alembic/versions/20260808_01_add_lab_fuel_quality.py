"""add laboratory fuel quality tests

Revision ID: 20260808_01
Revises: 20260807_01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260808_01"
down_revision = "20260807_01"
branch_labels = None
depends_on = None


def upgrade():
    status = postgresql.ENUM("DRAFT","COMPLETED","ARCHIVED",name="lab_experiment_status",create_type=False)
    op.create_table("lab_fuel_quality_tests",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("sample_date",sa.Date(),nullable=False),
        sa.Column("sample_name",sa.String(255),nullable=False),sa.Column("calorimeter",sa.String(100),nullable=False),
        sa.Column("sa_percent",sa.Numeric(9,4),nullable=False),sa.Column("alpha",sa.Numeric(12,8),nullable=False),
        sa.Column("wa_percent",sa.Numeric(9,4),nullable=False),sa.Column("aa_percent",sa.Numeric(9,4),nullable=False),
        sa.Column("wr_percent",sa.Numeric(9,4),nullable=False),sa.Column("hydrogen_input_percent",sa.Numeric(9,4),nullable=False),
        sa.Column("qb_a_1_kcal_kg",sa.Numeric(14,2),nullable=False),sa.Column("qb_a_2_kcal_kg",sa.Numeric(14,2),nullable=False),
        sa.Column("va_percent",sa.Numeric(9,4),nullable=False),sa.Column("status",status,nullable=False,server_default="DRAFT"),
        sa.Column("lab_technician_name",sa.String(255),nullable=False),sa.Column("wagon_numbers",sa.String(500)),
        sa.Column("invoice_number",sa.String(100)),sa.Column("fuel_consumption_note",sa.Text()),
        sa.Column("calculation_snapshot",postgresql.JSONB()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("archived_at",sa.DateTime(timezone=True)),
        sa.Column("created_by",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("updated_by",sa.Integer(),sa.ForeignKey("users.id")))
    for name in ("sample_date","sample_name","status","invoice_number"):
        op.create_index(f"ix_lab_fuel_quality_tests_{name}","lab_fuel_quality_tests",[name])
    op.create_table("lab_fuel_quality_audit_log",
        sa.Column("id",sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column("test_id",sa.Integer(),sa.ForeignKey("lab_fuel_quality_tests.id",ondelete="CASCADE"),nullable=False),
        sa.Column("action",sa.String(50),nullable=False),sa.Column("changed_by_user_id",sa.Integer(),sa.ForeignKey("users.id")),
        sa.Column("changed_by_name",sa.String(255)),sa.Column("previous_values",postgresql.JSONB()),
        sa.Column("new_values",postgresql.JSONB()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_lab_fuel_quality_audit_log_test_id","lab_fuel_quality_audit_log",["test_id"])
    op.create_index("ix_lab_fuel_quality_audit_log_created_at","lab_fuel_quality_audit_log",["created_at"])


def downgrade():
    op.drop_table("lab_fuel_quality_audit_log")
    op.drop_table("lab_fuel_quality_tests")
