"""initial_schema

Revision ID: a43d3810bad8
Revises:
Create Date: 2026-06-30 02:50:17.344824

"""

from collections.abc import Sequence

revision: str = "a43d3810bad8"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
