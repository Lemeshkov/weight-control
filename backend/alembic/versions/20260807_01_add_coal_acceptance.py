"""add coal acceptance; Revision ID: 20260807_01; Revises: 20260806_01"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260807_01"
down_revision = "20260806_01"
branch_labels = None
depends_on = None

def upgrade() -> None:
    status = postgresql.ENUM("DRAFT", "COMPLETED", name="coal_acceptance_status", create_type=False)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table("coal_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("shipment_date", sa.Date()), sa.Column("act_number", sa.String(100)),
        sa.Column("transport_invoice_number", sa.String(100)),
        sa.Column("document_net_weight_t", sa.Numeric(18, 3)),
        sa.Column("supplier_id", sa.Integer()), sa.Column("coal_grade_id", sa.Integer()),
        sa.Column("uk_number", sa.String(100)), sa.Column("invoice_number", sa.String(100)),
        sa.Column("receiver_name", sa.String(255)), sa.Column("notes", sa.Text()),
        sa.Column("status", status, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer()), sa.Column("updated_by", sa.Integer()),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["coal_grade_id"], ["coal_grades.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]), sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("trip_id", name="uq_coal_acceptances_trip_id"))
    for c in ("trip_id", "transport_invoice_number", "supplier_id", "coal_grade_id", "status"):
        op.create_index(f"ix_coal_acceptances_{c}", "coal_acceptances", [c])
    op.create_table("coal_acceptance_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("coal_acceptance_id", sa.Integer(), nullable=False), sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False), sa.Column("changed_by", sa.Integer()),
        sa.Column("changed_by_name", sa.String(255)), sa.Column("previous_values", postgresql.JSONB()), sa.Column("new_values", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["coal_acceptance_id"], ["coal_acceptances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["changed_by"], ["users.id"]))
    for c in ("coal_acceptance_id", "trip_id", "created_at"):
        op.create_index(f"ix_coal_acceptance_audit_log_{c}", "coal_acceptance_audit_log", [c])

def downgrade() -> None:
    for c in ("created_at", "trip_id", "coal_acceptance_id"):
        op.drop_index(f"ix_coal_acceptance_audit_log_{c}", table_name="coal_acceptance_audit_log")
    op.drop_table("coal_acceptance_audit_log")
    for c in ("status", "coal_grade_id", "supplier_id", "transport_invoice_number", "trip_id"):
        op.drop_index(f"ix_coal_acceptances_{c}", table_name="coal_acceptances")
    op.drop_table("coal_acceptances")
    sa.Enum(name="coal_acceptance_status").drop(op.get_bind(), checkfirst=True)


