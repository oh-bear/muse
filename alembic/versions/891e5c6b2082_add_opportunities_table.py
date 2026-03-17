"""add opportunities table

Revision ID: 891e5c6b2082
Revises: c64cd9efa446
Create Date: 2026-03-17 11:05:22.524066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '891e5c6b2082'
down_revision: Union[str, Sequence[str], None] = 'c64cd9efa446'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('opportunities',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('trend_category', sa.String(length=64), nullable=False),
    sa.Column('unmet_need', sa.Text(), nullable=False),
    sa.Column('market_gap', sa.Text(), nullable=False),
    sa.Column('geo_opportunity', sa.Text(), nullable=False),
    sa.Column('signal_ids', postgresql.ARRAY(sa.UUID()), nullable=False),
    sa.Column('week_of', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='muse'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('opportunities', schema='muse')
