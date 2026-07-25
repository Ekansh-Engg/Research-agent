"""create readonly_agent role

Revision ID: 7af1d073d8ff
Revises: f0173a013dbc
Create Date: 2026-07-25 18:55:33.119785

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7af1d073d8ff'
down_revision: Union[str, Sequence[str], None] = 'f0173a013dbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_agent') THEN
                CREATE ROLE readonly_agent WITH LOGIN PASSWORD 'readonly_pass';
            END IF;
        END
        $$;
    """)
    op.execute("GRANT CONNECT ON DATABASE research_agent TO readonly_agent;")
    op.execute("GRANT USAGE ON SCHEMA public TO readonly_agent;")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_agent;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_agent;")


def downgrade() -> None:
    op.execute("DROP ROLE IF EXISTS readonly_agent;")