"""add laboratory mvp

Revision ID: 20260802_01
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260802_01"
down_revision = None
branch_labels = None
depends_on = None

status_enum = sa.Enum("DRAFT", "COMPLETED", "ARCHIVED", name="lab_experiment_status")
volume_enum = sa.Enum("LITER", "M3", name="lab_volume_unit")


def upgrade():
    op.create_table("coal_grades",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("coal_fractions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("min_size_mm", sa.Numeric(12, 3)), sa.Column("max_size_mm", sa.Numeric(12, 3)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_size_mm IS NULL OR min_size_mm >= 0", name="ck_coal_fraction_min_nonnegative"),
        sa.CheckConstraint("max_size_mm IS NULL OR max_size_mm >= 0", name="ck_coal_fraction_max_nonnegative"),
        sa.CheckConstraint("min_size_mm IS NULL OR max_size_mm IS NULL OR min_size_mm <= max_size_mm", name="ck_coal_fraction_range"))
    op.create_table("suppliers",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(50), unique=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("lab_experiments",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("experiment_number", sa.String(100), nullable=False, unique=True),
        sa.Column("coal_grade_id", sa.Integer(), sa.ForeignKey("coal_grades.id"), nullable=False),
        sa.Column("coal_fraction_id", sa.Integer(), sa.ForeignKey("coal_fractions.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("batch_number", sa.String(100)), sa.Column("invoice_number", sa.String(100)),
        sa.Column("sampled_at", sa.DateTime(timezone=True)), sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moisture_percent", sa.Numeric(7, 3)), sa.Column("status", status_enum, nullable=False, server_default="DRAFT"),
        sa.Column("laboratory_user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("laboratory_user_name", sa.String(255), nullable=False),
        sa.Column("comment", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("moisture_percent IS NULL OR (moisture_percent >= 0 AND moisture_percent <= 100)", name="ck_lab_experiment_moisture_range"))
    for name in ("coal_grade_id", "coal_fraction_id", "supplier_id", "batch_number", "invoice_number", "tested_at", "status"):
        op.create_index(f"ix_lab_experiments_{name}", "lab_experiments", [name])
    op.create_table("lab_measurements",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("lab_experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False), sa.Column("entered_volume_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("entered_volume_unit", volume_enum, nullable=False), sa.Column("container_volume_m3", sa.Numeric(18, 9), nullable=False),
        sa.Column("material_mass_kg", sa.Numeric(18, 6), nullable=False), sa.Column("calculated_density_kg_m3", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_included", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("exclusion_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "sequence_number", name="uq_lab_measurement_sequence"),
        sa.CheckConstraint("sequence_number > 0 AND entered_volume_value > 0 AND container_volume_m3 > 0 AND material_mass_kg > 0", name="ck_lab_measurement_positive_values"),
        sa.CheckConstraint("is_included OR exclusion_reason IS NOT NULL", name="ck_lab_measurement_exclusion_reason"))
    op.create_index("ix_lab_measurements_experiment_id", "lab_measurements", ["experiment_id"])
    op.create_table("lab_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("lab_experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement_id", sa.Integer()), sa.Column("action", sa.String(50), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("changed_by_name", sa.String(255)),
        sa.Column("previous_values", postgresql.JSONB()), sa.Column("new_values", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_lab_audit_log_experiment_id", "lab_audit_log", ["experiment_id"])
    op.create_index("ix_lab_audit_log_created_at", "lab_audit_log", ["created_at"])


def downgrade():
    op.drop_table("lab_audit_log")
    op.drop_table("lab_measurements")
    op.drop_table("lab_experiments")
    op.drop_table("suppliers")
    op.drop_table("coal_fractions")
    op.drop_table("coal_grades")
    volume_enum.drop(op.get_bind(), checkfirst=True)
    status_enum.drop(op.get_bind(), checkfirst=True)
