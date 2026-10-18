"""Baseline schema: every orbit_* table.

Revision ID: 0001
Revises:
Create Date: 2026-10-17

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "orbit_pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "source_detail", sa.String(length=255), server_default="", nullable=False
        ),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "reports_in", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "considered", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "classified", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "events_out", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("skipped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_pipeline_runs")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_orbit_pipeline_runs_is_active"),
        "orbit_pipeline_runs",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orbit_pipeline_runs_status"),
        "orbit_pipeline_runs",
        ["status"],
        unique=False,
    )
    op.create_table(
        "orbit_translations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("biz_id", sa.Integer(), nullable=False),
        sa.Column("headline_en", sa.Text(), nullable=False),
        sa.Column("summary_en", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("translated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_translations")),
        sa.UniqueConstraint("biz_id", name=op.f("uq_orbit_translations_biz_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "orbit_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "sector", sa.String(length=20), server_default="Automotive", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_workspaces")),
        sa.UniqueConstraint("token", name=op.f("uq_orbit_workspaces_token")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "orbit_business_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("sector", sa.String(length=20), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["orbit_workspaces.id"],
            name=op.f("fk_orbit_business_profiles_workspace_id_orbit_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_business_profiles")),
        sa.UniqueConstraint("workspace_id", "sector", name="uq_orbit_profile"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "orbit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.Column("var", sa.String(length=40), nullable=False),
        sa.Column("topic", sa.String(length=40), server_default="", nullable=False),
        sa.Column(
            "is_index", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=8), nullable=False),
        sa.Column("hit", sa.Double(), nullable=False),
        sa.Column("direction", sa.SmallInteger(), nullable=False),
        sa.Column("mag", sa.Double(), nullable=False),
        sa.Column(
            "extracted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "n_extracted", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("n_facts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "report_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("first_at", sa.DateTime(), nullable=False),
        sa.Column("last_at", sa.DateTime(), nullable=False),
        sa.Column("rep", sa.Text(), nullable=False),
        sa.Column("rep_summary", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=60), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["orbit_pipeline_runs.id"],
            name=op.f("fk_orbit_events_run_id_orbit_pipeline_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_events")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_orbit_events_run_code", "orbit_events", ["run_id", "code"], unique=False
    )
    op.create_index(
        "ix_orbit_events_run_last", "orbit_events", ["run_id", "last_at"], unique=False
    )
    op.create_index(
        "ix_orbit_events_run_var", "orbit_events", ["run_id", "var"], unique=False
    )
    op.create_table(
        "orbit_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("sector", sa.String(length=20), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column(
            "position", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("owner", sa.String(length=120), server_default="", nullable=False),
        sa.Column("due", sa.String(length=60), server_default="", nullable=False),
        sa.Column("signal", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "done", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["orbit_workspaces.id"],
            name=op.f("fk_orbit_tasks_workspace_id_orbit_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_tasks")),
        sa.UniqueConstraint(
            "workspace_id", "sector", "client_id", name="uq_orbit_task"
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_orbit_tasks_workspace_id"),
        "orbit_tasks",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "orbit_event_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("sl", sa.Integer(), nullable=False),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.Column("section", sa.String(length=80), server_default="", nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("mag", sa.Double(), nullable=True),
        sa.Column(
            "direction", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "outlook", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("level", sa.String(length=60), nullable=True),
        sa.Column(
            "machine", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["orbit_events.id"],
            name=op.f("fk_orbit_event_reports_event_id_orbit_events"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_event_reports")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_orbit_event_reports_event_id"),
        "orbit_event_reports",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orbit_event_reports_sl"), "orbit_event_reports", ["sl"], unique=False
    )
    op.create_table(
        "orbit_event_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("value", sa.String(length=40), nullable=False),
        sa.Column(
            "position", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["orbit_events.id"],
            name=op.f("fk_orbit_event_tags_event_id_orbit_events"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orbit_event_tags")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_orbit_event_tags_event_id"),
        "orbit_event_tags",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_orbit_event_tags_kind_value",
        "orbit_event_tags",
        ["kind", "value"],
        unique=False,
    )


def downgrade():
    # Dropping a table drops its indexes with it. Order: children before the tables they reference.
    for table in (
        "orbit_event_tags",
        "orbit_event_reports",
        "orbit_tasks",
        "orbit_events",
        "orbit_business_profiles",
        "orbit_workspaces",
        "orbit_translations",
        "orbit_pipeline_runs",
    ):
        op.drop_table(table)
