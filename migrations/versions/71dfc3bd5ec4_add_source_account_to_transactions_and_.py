"""Add source account to transactions and rules

Revision ID: 71dfc3bd5ec4
Revises: 558d86863a1c
Create Date: 2025-09-01 23:40:35.688326

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


# revision identifiers, used by Alembic.
revision = '71dfc3bd5ec4'
down_revision = '558d86863a1c'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # For 'transaction' table
    transaction_columns = [c['name'] for c in inspector.get_columns('transaction')]
    if 'source_account_id' not in transaction_columns:
        op.add_column('transaction', sa.Column('source_account_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_transaction_source_account', 'transaction', 'account', ['source_account_id'], ['id'])

    # For 'transaction_rule' table
    transaction_rule_columns = [c['name'] for c in inspector.get_columns('transaction_rule')]
    if 'source_account_id' not in transaction_rule_columns:
        op.add_column('transaction_rule', sa.Column('source_account_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_transaction_rule_source_account', 'transaction_rule', 'account', ['source_account_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_transaction_rule_source_account', 'transaction_rule', type_='foreignkey')
    op.drop_column('transaction_rule', 'source_account_id')

    op.drop_constraint('fk_transaction_source_account', 'transaction', type_='foreignkey')
    op.drop_column('transaction', 'source_account_id')
