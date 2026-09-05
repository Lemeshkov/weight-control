"""supplier vehicle and declared coal specification administration

Revision ID: 20260905_01
Revises: 20260809_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260905_01"
down_revision = "20260809_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("suppliers", sa.Column("short_name", sa.String(100)))
    op.add_column("suppliers", sa.Column("inn", sa.String(20)))
    op.add_column("suppliers", sa.Column("comment", sa.Text()))
    op.create_index("ix_suppliers_inn", "suppliers", ["inn"])
    op.create_table("supplier_vehicles",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("registration_number",sa.String(32),nullable=False),
        sa.Column("registration_number_normalized",sa.String(32),nullable=False),sa.Column("make_model",sa.String(255)),
        sa.Column("comment",sa.Text()),sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint("registration_number_normalized",name="uq_supplier_vehicle_registration_normalized"))
    op.create_index("ix_supplier_vehicles_registration_normalized","supplier_vehicles",["registration_number_normalized"])
    op.create_table("vehicle_supplier_assignments",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("vehicle_id",sa.Integer(),nullable=False),sa.Column("supplier_id",sa.Integer(),nullable=False),
        sa.Column("valid_from",sa.Date(),nullable=False),sa.Column("valid_to",sa.Date()),sa.Column("comment",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["vehicle_id"],["supplier_vehicles.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["supplier_id"],["suppliers.id"],ondelete="RESTRICT"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from",name="ck_vehicle_supplier_assignment_dates"))
    op.create_index("ix_vehicle_supplier_assignments_vehicle_id","vehicle_supplier_assignments",["vehicle_id"])
    op.create_index("ix_vehicle_supplier_assignments_supplier_id","vehicle_supplier_assignments",["supplier_id"])
    op.create_index("ix_vehicle_supplier_assignment_validity","vehicle_supplier_assignments",["vehicle_id","valid_from","valid_to"])
    op.create_index("uq_vehicle_one_open_assignment","vehicle_supplier_assignments",["vehicle_id"],unique=True,postgresql_where=sa.text("valid_to IS NULL"))
    op.create_table("supplier_coal_specs",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("supplier_id",sa.Integer(),nullable=False),sa.Column("coal_grade_id",sa.Integer(),nullable=False),
        sa.Column("calorific_value",sa.Numeric(14,3)),sa.Column("calorific_value_unit",sa.String(32),nullable=False,server_default="kcal/kg"),
        sa.Column("moisture_pct",sa.Numeric(6,3)),sa.Column("ash_pct",sa.Numeric(6,3)),sa.Column("valid_from",sa.Date(),nullable=False),sa.Column("valid_to",sa.Date()),
        sa.Column("comment",sa.Text()),sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["supplier_id"],["suppliers.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["coal_grade_id"],["coal_grades.id"],ondelete="RESTRICT"),
        sa.CheckConstraint("calorific_value IS NULL OR calorific_value > 0",name="ck_supplier_coal_spec_calorific_positive"),
        sa.CheckConstraint("moisture_pct IS NULL OR (moisture_pct >= 0 AND moisture_pct <= 100)",name="ck_supplier_coal_spec_moisture_pct"),
        sa.CheckConstraint("ash_pct IS NULL OR (ash_pct >= 0 AND ash_pct <= 100)",name="ck_supplier_coal_spec_ash_pct"),sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from",name="ck_supplier_coal_spec_dates"))
    op.create_index("ix_supplier_coal_specs_supplier_id","supplier_coal_specs",["supplier_id"]);op.create_index("ix_supplier_coal_specs_coal_grade_id","supplier_coal_specs",["coal_grade_id"])
    op.create_index("ix_supplier_coal_spec_lookup","supplier_coal_specs",["supplier_id","coal_grade_id","valid_from","valid_to"])
    op.create_table("supplier_coal_fraction_specs",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("supplier_coal_spec_id",sa.Integer(),nullable=False),sa.Column("fraction_min_mm",sa.Numeric(12,3),nullable=False),
        sa.Column("fraction_max_mm",sa.Numeric(12,3),nullable=False),sa.Column("operator",sa.String(2),nullable=False),sa.Column("value",sa.Numeric(8,3),nullable=False),
        sa.Column("unit",sa.String(16),nullable=False,server_default="%"),sa.Column("comment",sa.Text()),sa.ForeignKeyConstraint(["supplier_coal_spec_id"],["supplier_coal_specs.id"],ondelete="CASCADE"),
        sa.CheckConstraint("fraction_min_mm >= 0 AND fraction_max_mm >= fraction_min_mm",name="ck_supplier_fraction_range"),sa.CheckConstraint("operator IN ('<', '<=', '=', '>=', '>')",name="ck_supplier_fraction_operator"),sa.CheckConstraint("value >= 0 AND (unit <> '%' OR value <= 100)",name="ck_supplier_fraction_value"))
    op.create_index("ix_supplier_coal_fraction_specs_supplier_coal_spec_id","supplier_coal_fraction_specs",["supplier_coal_spec_id"])


def downgrade():
    op.drop_table("supplier_coal_fraction_specs")
    op.drop_table("supplier_coal_specs")
    op.drop_index("uq_vehicle_one_open_assignment",table_name="vehicle_supplier_assignments")
    op.drop_table("vehicle_supplier_assignments")
    op.drop_table("supplier_vehicles")
    op.drop_index("ix_suppliers_inn",table_name="suppliers")
    op.drop_column("suppliers","comment");op.drop_column("suppliers","inn");op.drop_column("suppliers","short_name")
