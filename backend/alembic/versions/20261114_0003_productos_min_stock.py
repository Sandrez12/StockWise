"""products.min_stock: umbral de stock bajo por producto

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("min_stock", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_products_min_stock_non_negative", "products", "min_stock >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_min_stock_non_negative", "products", type_="check")
    op.drop_column("products", "min_stock")
