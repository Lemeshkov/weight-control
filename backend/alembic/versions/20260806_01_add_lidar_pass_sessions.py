"""add lidar pass sessions

Revision ID: 20260806_01
Revises: 20260802_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_01"
down_revision = "20260802_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lidar_pass_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workflow_state", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_state_name", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("load_scale_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stable_weight_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pre_trigger_seconds", sa.Float(), nullable=False),
        sa.Column("pre_trigger_profiles_count", sa.Integer(), nullable=False),
        sa.Column("profiles_count", sa.Integer(), nullable=False),
        sa.Column("valid_profiles_count", sa.Integer(), nullable=False),
        sa.Column("points_total", sa.Integer(), nullable=False),
        sa.Column("points_valid", sa.Integer(), nullable=False),
        sa.Column("trigger_weight_kg", sa.Float(), nullable=True),
        sa.Column("stable_weight_kg", sa.Float(), nullable=True),
        sa.Column("maximum_observed_weight_kg", sa.Float(), nullable=True),
        sa.Column("weight_samples_count", sa.Integer(), nullable=False),
        sa.Column("state_timestamps", sa.JSON(), nullable=False),
        sa.Column("estimated_volume_m3", sa.Float(), nullable=True),
        sa.Column("volume_status", sa.String(length=32), nullable=False),
        sa.Column("data_file_path", sa.String(length=1000), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"]),
    )
    op.create_index(
        "ix_lidar_pass_sessions_trip_id", "lidar_pass_sessions", ["trip_id"]
    )
    op.create_index(
        "ix_lidar_pass_sessions_status", "lidar_pass_sessions", ["status"]
    )
    op.create_index(
        "ix_lidar_pass_sessions_started_at", "lidar_pass_sessions", ["started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_lidar_pass_sessions_started_at", table_name="lidar_pass_sessions")
    op.drop_index("ix_lidar_pass_sessions_status", table_name="lidar_pass_sessions")
    op.drop_index("ix_lidar_pass_sessions_trip_id", table_name="lidar_pass_sessions")
    op.drop_table("lidar_pass_sessions")
