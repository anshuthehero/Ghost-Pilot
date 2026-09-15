"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-04 21:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('plan', sa.String(length=50), nullable=False, server_default='development'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False, server_default='Interview Session'),
        sa.Column('domain', sa.String(length=50), nullable=False, server_default='general'),
        sa.Column('custom_instructions', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False)
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)

    # 3. subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='mock'),
        sa.Column('provider_customer_id', sa.String(length=255), nullable=True),
        sa.Column('provider_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('plan', sa.String(length=50), nullable=False, server_default='development'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('current_period_start', sa.DateTime(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)

    # 4. usages table
    op.create_table(
        'usages',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(length=36), sa.ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('operation', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('tokens_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata_json', sa.Text(), nullable=True)
    )
    op.create_index(op.f('ix_usages_user_id'), 'usages', ['user_id'], unique=False)
    op.create_index(op.f('ix_usages_timestamp'), 'usages', ['timestamp'], unique=False)

    # 5. user_settings table
    op.create_table(
        'user_settings',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('response_style', sa.String(length=50), nullable=False, server_default='crisp'),
        sa.Column('custom_instructions', sa.Text(), nullable=True),
        sa.Column('preferred_model', sa.String(length=100), nullable=False, server_default='qwen/qwen3.8-27b'),
        sa.Column('audio_sensitivity_threshold', sa.Float(), nullable=False, server_default='-30.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False)
    )


def downgrade() -> None:
    op.drop_table('user_settings')
    op.drop_table('usages')
    op.drop_table('subscriptions')
    op.drop_table('sessions')
    op.drop_table('users')
