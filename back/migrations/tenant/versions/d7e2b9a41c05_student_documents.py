"""student documents (laudos)

Revision ID: d7e2b9a41c05
Revises: c4a1f0d2e7b3
Create Date: 2026-11-07 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e2b9a41c05'
down_revision: Union[str, Sequence[str], None] = 'c4a1f0d2e7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('student_documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
    sa.Column('uploaded_by_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    with op.batch_alter_table('student_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_student_documents_student_id'), ['student_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('student_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_student_documents_student_id'))

    op.drop_table('student_documents')
