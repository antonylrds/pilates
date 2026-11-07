"""payments (student plan payments and teacher payments)

Revision ID: c4a1f0d2e7b3
Revises: 884860db39b5
Create Date: 2026-11-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a1f0d2e7b3'
down_revision: Union[str, Sequence[str], None] = '884860db39b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('student', 'teacher', name='paymentkind', native_enum=False, length=20, validate_strings=True, create_constraint=False), nullable=False),
    sa.Column('status', sa.Enum('pending', 'paid', 'cancelled', name='paymentstatus', native_enum=False, length=20, validate_strings=True, create_constraint=False), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('paid_at', sa.Date(), nullable=True),
    sa.Column('cancelled_at', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('student_id', sa.Integer(), nullable=True),
    sa.Column('subscription_id', sa.Integer(), nullable=True),
    sa.Column('teacher_id', sa.Integer(), nullable=True),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("(kind = 'student' AND student_id IS NOT NULL AND subscription_id IS NOT NULL AND teacher_id IS NULL) OR (kind = 'teacher' AND teacher_id IS NOT NULL AND student_id IS NULL AND subscription_id IS NULL)", name='ck_payments_kind_links'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_student_id'), ['student_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_subscription_id'), ['subscription_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_teacher_id'), ['teacher_id'], unique=False)

    # Planos já contratados ganham um pagamento: pago (com a data), cancelado (plano cancelado e não pago)
    # ou pendente. A data de criação é a do plano.
    op.execute(
        "INSERT INTO payments (kind, status, amount, paid_at, cancelled_at, student_id, subscription_id, "
        "created_at, updated_at) "
        "SELECT 'student', "
        "CASE WHEN is_paid THEN 'paid' WHEN status = 'cancelled' THEN 'cancelled' ELSE 'pending' END, "
        "final_price, "
        "CASE WHEN is_paid THEN COALESCE(paid_at, start_date) END, "
        "CASE WHEN NOT is_paid AND status = 'cancelled' THEN DATE(updated_at) END, "
        "student_id, id, created_at, updated_at "
        "FROM subscriptions"
    )
    # Plano pago sem data: o espelho passa a ter a data usada acima.
    op.execute("UPDATE subscriptions SET paid_at = start_date WHERE is_paid AND paid_at IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_teacher_id'))
        batch_op.drop_index(batch_op.f('ix_payments_subscription_id'))
        batch_op.drop_index(batch_op.f('ix_payments_student_id'))
        batch_op.drop_index(batch_op.f('ix_payments_status'))
        batch_op.drop_index(batch_op.f('ix_payments_kind'))

    op.drop_table('payments')
