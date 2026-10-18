"""The Alembic migrations and the models must describe the same schema."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from orbit.database import schema_revisions
from orbit.extensions import db, include_object


def test_models_and_migrations_agree(app):
    """Fails when someone changes a model without writing a migration (run `flask db migrate`)."""
    with app.app_context(), db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={'compare_type': True, 'include_object': include_object})
        assert compare_metadata(context, db.metadata) == []


def test_the_schema_is_at_the_latest_revision(app):
    with app.app_context():
        current, head = schema_revisions()
    assert current == head
    assert head is not None


def test_alembic_ignores_tables_it_does_not_own(app):
    """The newsroom tables share the database; migrations must never try to drop them."""
    assert not include_object(None, 'jagran_biz', 'table', True, None)
    assert include_object(None, 'orbit_events', 'table', True, None)
