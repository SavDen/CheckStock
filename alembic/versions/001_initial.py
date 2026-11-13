"""Initial CheckStock schema, deliberately frozen here for repeatable fresh installs."""

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("physical", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.UniqueConstraint("product_id", "warehouse_id"),
        sa.CheckConstraint("physical >= 0 AND reserved >= 0 AND reserved <= physical", name="valid_stock"),
    )
    op.create_table(
        "movements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(15), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("destination_label", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="positive_quantity"),
        sa.CheckConstraint("kind IN ('transfer', 'fbs', 'fbo')", name="valid_kind"),
        sa.CheckConstraint(
            "status IN ('reserved', 'transit', 'completed', 'cancelled')", name="valid_status"
        ),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id")),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("source_label", sa.String(100), nullable=False),
        sa.Column("destination_label", sa.String(100), nullable=False),
        sa.Column("movement_id", sa.String(36), sa.ForeignKey("movements.id")),
        sa.Column("physical_delta", sa.Integer(), nullable=False),
        sa.Column("reserved_delta", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(250), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "idempotency",
        sa.Column("key", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )
    op.execute("INSERT INTO stores (id, name) VALUES (1, 'Ракета · демомагазин')")


def downgrade():
    for name in ["idempotency", "events", "movements", "stocks", "warehouses", "products", "stores"]:
        op.drop_table(name)
