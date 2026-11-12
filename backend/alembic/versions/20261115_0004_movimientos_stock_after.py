"""stock_movements.stock_after e inmutabilidad de los movimientos

- stock_after: instantánea del stock resultante tras cada movimiento (auditoría).
  Se rellena para filas existentes con la suma acumulada de cantidades firmadas
  por producto, en orden de id.
- Trigger: los movimientos son un registro de auditoría; UPDATE y DELETE se
  rechazan en la propia base de datos.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_movements", sa.Column("stock_after", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE stock_movements m
        SET stock_after = s.running
        FROM (
            SELECT id,
                   SUM(CASE WHEN type = 'salida' THEN -quantity ELSE quantity END)
                       OVER (PARTITION BY product_id ORDER BY id) AS running
            FROM stock_movements
        ) s
        WHERE m.id = s.id
        """
    )
    op.alter_column("stock_movements", "stock_after", nullable=False)
    op.create_check_constraint(
        "ck_stock_movements_stock_after_non_negative", "stock_movements", "stock_after >= 0"
    )

    op.execute(
        """
        CREATE FUNCTION forbid_stock_movement_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'stock_movements is append-only (% not allowed)', TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_stock_movements_immutable
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION forbid_stock_movement_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_stock_movements_immutable ON stock_movements")
    op.execute("DROP FUNCTION forbid_stock_movement_change()")
    op.drop_constraint(
        "ck_stock_movements_stock_after_non_negative", "stock_movements", type_="check"
    )
    op.drop_column("stock_movements", "stock_after")
