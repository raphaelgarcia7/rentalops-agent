"""Versioned rental changes without rewriting immutable commercial history."""

from alembic import op

revision = "0009_rental_changes"
down_revision = "0008_rentals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER rentals_immutable ON rentals")
    op.execute("ALTER TABLE rentals DROP CONSTRAINT ck_rental_state")
    op.execute("""ALTER TABLE rentals ADD CONSTRAINT ck_rental_state CHECK (
        version >= 1 AND state IN ('confirmed','cancelled','review'))""")
    op.execute("ALTER TABLE rentals ALTER COLUMN financial_version DROP NOT NULL")
    op.execute("ALTER TABLE rentals ADD confirmation_deposit NUMERIC(12,2)")
    op.execute("""UPDATE rentals SET confirmation_deposit =
        (commercial_snapshot->>'estimated_deposit')::numeric""")
    op.execute("ALTER TABLE rentals ALTER COLUMN confirmation_deposit SET NOT NULL")
    op.execute("""ALTER TABLE rentals ADD CONSTRAINT ck_rental_deposit
        CHECK (confirmation_deposit > 0)""")
    op.execute("ALTER TABLE rental_history ADD reason VARCHAR(1000)")
    op.execute("ALTER TABLE rental_history ADD before JSON NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE rental_history ADD after JSON NOT NULL DEFAULT '{}'")
    op.execute("DROP TRIGGER rental_history_immutable ON rental_history")
    op.execute("""UPDATE rental_history h SET after = json_build_object(
        'commercial', r.commercial_snapshot, 'financial', r.financial_snapshot,
        'state', r.state) FROM rentals r WHERE h.rental_id = r.id""")
    op.execute("""CREATE TRIGGER rental_history_immutable
        BEFORE UPDATE OR DELETE ON rental_history
        FOR EACH ROW EXECUTE FUNCTION reject_quotation_mutation()""")
    op.execute("ALTER TABLE rental_history ALTER COLUMN before DROP DEFAULT")
    op.execute("ALTER TABLE rental_history ALTER COLUMN after DROP DEFAULT")
    op.execute("""CREATE FUNCTION validate_rental_revision() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Rental history is preserved'; END IF;
        IF NEW.id <> OLD.id OR NEW.quotation_id <> OLD.quotation_id
            OR NEW.version <> OLD.version + 1 THEN
            RAISE EXCEPTION 'Rental changes require a new revision';
        END IF;
        RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER rentals_versioned BEFORE UPDATE OR DELETE ON rentals
        FOR EACH ROW EXECUTE FUNCTION validate_rental_revision()""")


def downgrade() -> None:
    # Never discard live cancellation/review history to make a downgrade fit.
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM rentals
        WHERE state <> 'confirmed' OR financial_version IS NULL OR version <> 1) THEN
        RAISE EXCEPTION 'Resolve newer rental states before downgrade';
        END IF; END; $$""")
    op.execute("DROP TRIGGER rentals_versioned ON rentals")
    op.execute("DROP FUNCTION validate_rental_revision()")
    op.execute("ALTER TABLE rentals DROP CONSTRAINT ck_rental_state")
    op.execute("""ALTER TABLE rentals ADD CONSTRAINT ck_rental_state
        CHECK (version >= 1 AND state = 'confirmed')""")
    op.execute("ALTER TABLE rentals ALTER COLUMN financial_version SET NOT NULL")
    op.execute("ALTER TABLE rentals DROP COLUMN confirmation_deposit")
    for column in ("reason", "before", "after"):
        op.execute(f'ALTER TABLE rental_history DROP COLUMN "{column}"')
    op.execute("""CREATE TRIGGER rentals_immutable BEFORE UPDATE OR DELETE ON rentals
        FOR EACH ROW EXECUTE FUNCTION reject_quotation_mutation()""")
