"""Add transaction_id to journal entry

Revision ID: 30955be0b656
Revises: e0b7ad376907
Create Date: 2025-09-01 14:48:59.513703

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


# revision identifiers, used by Alembic.
revision = '30955be0b656'
down_revision = 'e0b7ad376907'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('journal_entries')]

    if 'transaction_id' not in columns:
        op.add_column('journal_entries', sa.Column('transaction_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_journal_entries_transaction_id', 'journal_entries', 'transaction', ['transaction_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_journal_entries_transaction_id', 'journal_entries', type_='foreignkey')
    op.drop_column('journal_entries', 'transaction_id')
