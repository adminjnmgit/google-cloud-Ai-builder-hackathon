"""Flask extension instances, created unbound so any module can import them without a circular import."""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names. Without this, MySQL invents names (`token`, `orbit_x_ibfk_1`) that
# differ between databases and make Alembic's autogenerate noisy.
NAMING_CONVENTION = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


OWNED_PREFIX = 'orbit_'


def include_object(obj, name, type_, reflected, compare_to):
    """Tell Alembic to manage only our own tables.

    The database is shared with the newsroom's tables (jagran_biz, biz_signals ...). Without this filter,
    autogenerate would propose dropping them, because the models do not mention them.
    """
    table = name if type_ == 'table' else getattr(getattr(obj, 'table', None), 'name', None)
    return table is None or table.startswith(OWNED_PREFIX)


db = SQLAlchemy(model_class=Base)
migrate = Migrate(compare_type=True, render_as_batch=False, include_object=include_object)
