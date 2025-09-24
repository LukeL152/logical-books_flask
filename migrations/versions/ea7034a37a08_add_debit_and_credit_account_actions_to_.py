"""Add debit and credit account actions to transaction rules

Revision ID: ea7034a37a08
Revises: 44cbfc3ebf1a
Create Date: 2025-09-01 02:03:10.245365

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ea7034a37a08'
down_revision = '44cbfc3ebf1a'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('transaction_rule')]

    if 'new_debit_account_id' not in columns:
        op.add_column('transaction_rule', sa.Column('new_debit_account_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_transaction_rule_new_debit_account_id', 'transaction_rule', 'account', ['new_debit_account_id'], ['id'])

    if 'new_credit_account_id' not in columns:
        op.add_column('transaction_rule', sa.Column('new_credit_account_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_transaction_rule_new_credit_account_id', 'transaction_rule', 'account', ['new_credit_account_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_transaction_rule_new_debit_account_id', 'transaction_rule', type_='foreignkey')
    op.drop_constraint('fk_transaction_rule_new_credit_account_id', 'transaction_rule', type_='foreignkey')
    op.drop_column('transaction_rule', 'new_credit_account_id')
    op.drop_column('transaction_rule', 'new_debit_account_id')
