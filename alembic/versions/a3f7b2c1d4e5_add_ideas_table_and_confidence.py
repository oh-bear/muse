"""add ideas table and confidence column

Revision ID: a3f7b2c1d4e5
Revises: 891e5c6b2082
Create Date: 2026-03-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3f7b2c1d4e5'
down_revision: Union[str, Sequence[str], None] = '891e5c6b2082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add confidence to opportunities + create ideas table."""
    # Add confidence column to opportunities
    op.add_column('opportunities',
        sa.Column('confidence', sa.String(length=16), nullable=False, server_default='medium'),
        schema='muse'
    )

    # Create ideas table
    op.create_table('ideas',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('one_liner', sa.Text(), nullable=False),
        sa.Column('target_users', sa.Text(), nullable=False),
        sa.Column('pain_point', sa.Text(), nullable=False),
        sa.Column('differentiation', sa.Text(), nullable=False),
        sa.Column('channels', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('revenue_model', sa.String(length=32), nullable=False),
        sa.Column('key_resources', sa.Text(), nullable=False),
        sa.Column('cost_estimate', sa.Text(), nullable=False),
        sa.Column('validation_method', sa.Text(), nullable=False),
        sa.Column('difficulty', sa.SmallInteger(), nullable=False),
        sa.Column('opportunity_id', sa.UUID(), nullable=True),
        sa.Column('notion_page_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['muse.opportunities.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='muse'
    )

    # Create indexes
    op.create_index('idx_ideas_notion_page_id_null', 'ideas', ['id'],
                    schema='muse', postgresql_where=sa.text('notion_page_id IS NULL'))
    op.create_index('idx_ideas_opportunity_id', 'ideas', ['opportunity_id'], schema='muse')


def downgrade() -> None:
    """Remove ideas table and confidence column."""
    op.drop_index('idx_ideas_opportunity_id', table_name='ideas', schema='muse')
    op.drop_index('idx_ideas_notion_page_id_null', table_name='ideas', schema='muse')
    op.drop_table('ideas', schema='muse')
    op.drop_column('opportunities', 'confidence', schema='muse')
