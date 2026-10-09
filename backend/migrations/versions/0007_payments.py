"""Manual payment accounts, immutable revisions/events and safe replay."""

from alembic import op

revision = "0007_payments"
down_revision = "0006_quotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE payment_accounts (
        quotation_id UUID NOT NULL,
        version INTEGER NOT NULL,
        reconciled_quotation_version INTEGER,
        requires_reconciliation BOOLEAN NOT NULL,
        PRIMARY KEY (quotation_id),
        CONSTRAINT ck_payment_account_version CHECK (version >= 0),
        FOREIGN KEY(quotation_id, reconciled_quotation_version) REFERENCES
        quotation_versions (quotation_id, number),
        FOREIGN KEY(quotation_id) REFERENCES quotations (id)
        )
        """)
    op.execute("""
        CREATE TABLE payment_receipts (
        id UUID NOT NULL,
        quotation_id UUID NOT NULL,
        revision INTEGER NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_payment_receipt_account UNIQUE (id, quotation_id),
        CONSTRAINT ck_payment_receipt_revision CHECK (revision >= 1),
        FOREIGN KEY(quotation_id) REFERENCES payment_accounts (quotation_id)
        )
        """)
    op.execute("""
        CREATE TABLE payment_receipt_revisions (
        receipt_id UUID NOT NULL,
        number INTEGER NOT NULL,
        amount NUMERIC(12, 2) NOT NULL,
        method VARCHAR(4) NOT NULL,
        business_date DATE NOT NULL,
        observation VARCHAR(2000),
        reason VARCHAR(1000),
        actor_id UUID NOT NULL,
        session_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (receipt_id, number),
        CONSTRAINT ck_receipt_revision_money CHECK (number >= 1 AND amount > 0),
        CONSTRAINT ck_receipt_revision_method CHECK (method IN
        ('pix','cash','card')),
        CONSTRAINT ck_receipt_revision_reason CHECK (number = 1 OR
        length(btrim(reason)) BETWEEN 1 AND 1000),
        FOREIGN KEY(receipt_id) REFERENCES payment_receipts (id),
        FOREIGN KEY(actor_id) REFERENCES users (id),
        FOREIGN KEY(session_id) REFERENCES auth_sessions (id)
        )
        """)
    op.execute("""
        CREATE TABLE payment_refunds (
        id UUID NOT NULL,
        quotation_id UUID NOT NULL,
        receipt_id UUID NOT NULL,
        amount NUMERIC(12, 2) NOT NULL,
        method VARCHAR(4) NOT NULL,
        business_date DATE NOT NULL,
        reason VARCHAR(1000) NOT NULL,
        actor_id UUID NOT NULL,
        session_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(receipt_id, quotation_id) REFERENCES payment_receipts (id,
        quotation_id),
        CONSTRAINT ck_payment_refund_money CHECK (amount > 0),
        CONSTRAINT ck_payment_refund_method CHECK (method IN
        ('pix','cash','card')),
        CONSTRAINT ck_payment_refund_reason CHECK (length(btrim(reason)) BETWEEN
        1 AND 1000),
        FOREIGN KEY(quotation_id) REFERENCES payment_accounts (quotation_id),
        FOREIGN KEY(actor_id) REFERENCES users (id),
        FOREIGN KEY(session_id) REFERENCES auth_sessions (id)
        )
        """)
    op.execute("""
        CREATE TABLE payment_proofs (
        id UUID NOT NULL,
        quotation_id UUID NOT NULL,
        receipt_id UUID NOT NULL,
        storage_key VARCHAR(42) NOT NULL,
        content_type VARCHAR(20) NOT NULL,
        size INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        actor_id UUID NOT NULL,
        session_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(receipt_id, quotation_id) REFERENCES payment_receipts (id,
        quotation_id),
        CONSTRAINT ck_payment_proof_size CHECK (size BETWEEN 1 AND 10000000),
        CONSTRAINT ck_payment_proof_digest CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_payment_proof_type CHECK (content_type IN
        ('application/pdf','image/jpeg','image/png')),
        CONSTRAINT uq_payment_proof_key UNIQUE (storage_key),
        FOREIGN KEY(quotation_id) REFERENCES payment_accounts (quotation_id),
        FOREIGN KEY(actor_id) REFERENCES users (id),
        FOREIGN KEY(session_id) REFERENCES auth_sessions (id)
        )
        """)
    op.execute("""
        CREATE TABLE payment_history (
        id UUID NOT NULL,
        quotation_id UUID NOT NULL,
        financial_version INTEGER NOT NULL,
        quotation_version INTEGER NOT NULL,
        operation VARCHAR(20) NOT NULL,
        actor_id UUID NOT NULL,
        session_id UUID NOT NULL,
        reason VARCHAR(1000),
        before JSON NOT NULL,
        after JSON NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_payment_history_version UNIQUE (quotation_id,
        financial_version),
        FOREIGN KEY(quotation_id, quotation_version) REFERENCES
        quotation_versions (quotation_id, number),
        CONSTRAINT ck_payment_history_version CHECK (financial_version >= 1),
        FOREIGN KEY(quotation_id) REFERENCES payment_accounts (quotation_id),
        FOREIGN KEY(actor_id) REFERENCES users (id),
        FOREIGN KEY(session_id) REFERENCES auth_sessions (id)
        )
        """)
    op.execute("""
        CREATE TABLE payment_allocations (
        quotation_id UUID NOT NULL,
        financial_version INTEGER NOT NULL,
        receipt_id UUID NOT NULL,
        deposit NUMERIC(12, 2) NOT NULL,
        balance NUMERIC(12, 2) NOT NULL,
        PRIMARY KEY (quotation_id, financial_version, receipt_id),
        FOREIGN KEY(quotation_id, financial_version) REFERENCES payment_history
        (quotation_id, financial_version),
        FOREIGN KEY(receipt_id, quotation_id) REFERENCES payment_receipts (id,
        quotation_id),
        CONSTRAINT ck_payment_allocation_money CHECK (deposit >= 0 AND balance
        >= 0)
        )
        """)
    op.execute("""
        CREATE TABLE payment_requests (
        actor_id UUID NOT NULL,
        operation VARCHAR(100) NOT NULL,
        request_id UUID NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        quotation_id UUID NOT NULL,
        financial_version INTEGER NOT NULL,
        result JSON NOT NULL,
        PRIMARY KEY (actor_id, operation, request_id),
        CONSTRAINT ck_payment_request_hash CHECK (payload_hash ~
        '^[0-9a-f]{64}$'),
        FOREIGN KEY(quotation_id, financial_version) REFERENCES payment_history
        (quotation_id, financial_version),
        FOREIGN KEY(actor_id) REFERENCES users (id)
        )
        """)
    op.execute("""
        CREATE INDEX ix_payment_history_order ON payment_history (quotation_id,
        created_at, id)
        """)
    op.execute("""
        ALTER TABLE payment_receipts ADD CONSTRAINT fk_payment_receipt_current
        FOREIGN KEY(id, revision) REFERENCES payment_receipt_revisions
        (receipt_id, number) DEFERRABLE INITIALLY DEFERRED
        """)
    op.execute("""CREATE FUNCTION reject_payment_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Financial history is immutable'; END; $$""")
    for table in [
        "payment_receipt_revisions",
        "payment_refunds",
        "payment_proofs",
        "payment_history",
        "payment_allocations",
        "payment_requests",
    ]:
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_payment_mutation()"
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payment_receipt_current", "payment_receipts", type_="foreignkey"
    )
    for table in [
        "payment_requests",
        "payment_allocations",
        "payment_history",
        "payment_proofs",
        "payment_refunds",
        "payment_receipt_revisions",
        "payment_receipts",
        "payment_accounts",
    ]:
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_payment_mutation()")
