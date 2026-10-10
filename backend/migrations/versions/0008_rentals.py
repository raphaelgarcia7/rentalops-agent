"""Operational confirmation and daily product commitments."""

from alembic import op

revision = "0008_rentals"
down_revision = "0007_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE rentals (
        id UUID PRIMARY KEY,
        quotation_id UUID NOT NULL,
        quotation_version INTEGER NOT NULL,
        financial_version INTEGER NOT NULL,
        version INTEGER NOT NULL,
        state VARCHAR(20) NOT NULL,
        commercial_snapshot JSON NOT NULL,
        financial_snapshot JSON NOT NULL,
        actor_id UUID NOT NULL REFERENCES users(id),
        session_id UUID NOT NULL REFERENCES auth_sessions(id),
        checked_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_rental_quotation UNIQUE (quotation_id),
        CONSTRAINT ck_rental_state CHECK (version >= 1 AND state = 'confirmed'),
        FOREIGN KEY (quotation_id, quotation_version)
            REFERENCES quotation_versions(quotation_id, number),
        FOREIGN KEY (quotation_id, financial_version)
            REFERENCES payment_history(quotation_id, financial_version)
        )""")
    op.execute("""CREATE TABLE rental_allocations (
        rental_id UUID NOT NULL REFERENCES rentals(id),
        product_id UUID NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL,
        pickup_date DATE NOT NULL,
        return_date DATE NOT NULL,
        PRIMARY KEY (rental_id, product_id),
        CONSTRAINT ck_rental_allocation_qty
            CHECK (quantity BETWEEN 1 AND 2147483647),
        CONSTRAINT ck_rental_allocation_interval CHECK (pickup_date <= return_date)
        )""")
    op.create_index(
        "ix_rental_allocation_period",
        "rental_allocations",
        ["product_id", "pickup_date", "return_date"],
    )
    op.execute("""CREATE TABLE rental_pending (
        id UUID PRIMARY KEY,
        quotation_id UUID NOT NULL,
        quotation_version INTEGER NOT NULL,
        kind VARCHAR(20) NOT NULL,
        source VARCHAR(100) NOT NULL,
        source_version INTEGER NOT NULL,
        details JSON NOT NULL,
        actor_id UUID NOT NULL REFERENCES users(id),
        session_id UUID NOT NULL REFERENCES auth_sessions(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        FOREIGN KEY (quotation_id, quotation_version)
            REFERENCES quotation_versions(quotation_id, number),
        CONSTRAINT uq_rental_pending_origin
            UNIQUE (quotation_id, kind, source, source_version),
        CONSTRAINT ck_rental_pending_kind
            CHECK (kind IN ('inventory','financial') AND source_version >= 1)
        )""")
    op.execute("""CREATE TABLE rental_history (
        id UUID PRIMARY KEY,
        rental_id UUID NOT NULL REFERENCES rentals(id),
        version INTEGER NOT NULL,
        operation VARCHAR(20) NOT NULL,
        actor_id UUID NOT NULL REFERENCES users(id),
        session_id UUID NOT NULL REFERENCES auth_sessions(id),
        created_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT uq_rental_history_version UNIQUE (rental_id, version)
        )""")
    op.execute("""CREATE TABLE rental_requests (
        actor_id UUID NOT NULL REFERENCES users(id),
        operation VARCHAR(80) NOT NULL,
        request_id UUID NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        status INTEGER NOT NULL,
        result JSON NOT NULL,
        PRIMARY KEY (actor_id, operation, request_id),
        CONSTRAINT ck_rental_request_hash CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_rental_request_status CHECK (status IN (201,409))
        )""")
    # Confirmation snapshots and outcomes cannot be rewritten by another module.
    for table in ("rentals", "rental_history", "rental_requests", "rental_pending"):
        op.execute(f"""CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_quotation_mutation()""")


def downgrade() -> None:
    for table in (
        "rental_requests",
        "rental_history",
        "rental_pending",
        "rental_allocations",
        "rentals",
    ):
        op.drop_table(table)
