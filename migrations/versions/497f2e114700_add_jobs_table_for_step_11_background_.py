"""add jobs table for step 11 background processing

Revision ID: 497f2e114700
Revises: fc2036340bcb
Create Date: 2025-09-03 13:52:52.972421

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "497f2e114700"
down_revision: Union[str, Sequence[str], None] = "fc2036340bcb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create jobs table for Step 11 background processing
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.Text, nullable=False, comment="Job type identifier"),
        sa.Column(
            "org_id",
            sa.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope",
        ),
        sa.Column(
            "user_id", sa.UUID(as_uuid=True), nullable=True, comment="Requesting user"
        ),
        sa.Column(
            "payload",
            sa.JSON,
            nullable=False,
            default={},
            comment="Job-specific parameters",
        ),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            default="queued",
            comment="Job status: queued|running|succeeded|failed|deadletter|canceled",
        ),
        sa.Column(
            "priority",
            sa.SmallInteger,
            nullable=False,
            default=5,
            comment="Priority 1-10, lower is higher priority",
        ),
        sa.Column(
            "run_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            default=sa.func.now(),
            comment="Earliest time to run job",
        ),
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            default=0,
            comment="Number of attempts made",
        ),
        # Worker coordination fields
        sa.Column(
            "locked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="When job was locked by worker",
        ),
        sa.Column(
            "locked_by", sa.Text, nullable=True, comment="Worker ID that locked the job"
        ),
        sa.Column(
            "heartbeat_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Last worker heartbeat",
        ),
        # Results and progress
        sa.Column("result", sa.JSON, nullable=True, comment="Job result data"),
        sa.Column(
            "progress",
            sa.JSON,
            nullable=True,
            comment="Progress tracking {processed, total}",
        ),
        sa.Column(
            "error_code", sa.Text, nullable=True, comment="Structured error identifier"
        ),
        sa.Column("last_error", sa.Text, nullable=True, comment="Last error message"),
        # Tracing and deduplication
        sa.Column(
            "dedupe_key",
            sa.Text,
            nullable=True,
            comment="Deduplication key for idempotent jobs",
        ),
        sa.Column(
            "requested_by_user_id",
            sa.UUID(as_uuid=True),
            nullable=True,
            comment="Original requesting user",
        ),
        sa.Column(
            "request_id",
            sa.Text,
            nullable=True,
            comment="Original request ID for tracing",
        ),
        # Timestamps
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        # Constraints
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'deadletter', 'canceled')",
            name="jobs_status_check",
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 10", name="jobs_priority_check"),
    )

    # Create indexes for performance
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])
    op.create_index("ix_jobs_org_id_status", "jobs", ["org_id", "status"])
    op.create_index("ix_jobs_type_status", "jobs", ["type", "status"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])
    op.create_index("ix_jobs_heartbeat_at", "jobs", ["heartbeat_at"])

    # Unique constraint for dedupe_key when job is active (queued, running, or succeeded)
    # Note: Partial unique index to allow NULL dedupe_keys and reuse of keys for completed jobs
    op.create_index(
        "ix_jobs_dedupe_key_active",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text(
            "dedupe_key IS NOT NULL AND status IN ('queued', 'running', 'succeeded')"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("jobs")
