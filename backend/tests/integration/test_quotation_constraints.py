from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from .test_quotations import create
from .test_quotations import quotations as quotation_fixture

pytestmark = pytest.mark.integration


@pytest.fixture
def quotations(migrated_engine):
    return quotation_fixture.__wrapped__(migrated_engine)


def test_direct_quantity_and_reference_constraints(quotations):
    service, _, ids = quotations
    saved = create(quotations)
    line_id = UUID(saved["lines"][0]["id"])
    with pytest.raises(IntegrityError) as caught, service.factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO quotation_lines(id,quotation_id,version,position,"
                "product_id,quantity,unit_price,source_version,snapshot) "
                "VALUES (:id,:quote,1,99,:product,0,1,1,'{}')"
            ),
            {"id": uuid4(), "quote": UUID(saved["id"]), "product": ids["vase"]},
        )
    assert caught.value.orig.sqlstate == "23514"
    assert caught.value.orig.diag.constraint_name == "ck_quotation_line_values"
    with pytest.raises(IntegrityError) as caught, service.factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO quotation_components(line_id,product_id,quantity,"
                "source_version,source_name) VALUES "
                "(:line,:product,0,1,'Synthetic invalid quantity')"
            ),
            {"line": line_id, "product": uuid4()},
        )
    assert caught.value.orig.diag.constraint_name == "ck_quotation_component_values"
    with pytest.raises(IntegrityError) as caught, service.factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO quotation_components(line_id,product_id,quantity,"
                "source_version,source_name) VALUES "
                "(:line,:product,1,1,'Synthetic invalid reference')"
            ),
            {"line": line_id, "product": uuid4()},
        )
    assert caught.value.orig.sqlstate == "23503"
    with pytest.raises(IntegrityError) as caught, service.factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO quotation_lines(id,quotation_id,version,position,"
                "product_id,quantity,unit_price,source_version,snapshot) "
                "VALUES (:id,:quote,1,0,:product,1,1,1,'{}')"
            ),
            {"id": uuid4(), "quote": UUID(saved["id"]), "product": ids["vase"]},
        )
    assert caught.value.orig.diag.constraint_name == "uq_quotation_line_position"


def test_update_and_delete_immutable_records_and_snapshot_consistency(quotations):
    service, _, _ = quotations
    saved = create(quotations)
    fields = {
        "quotation_versions": "number",
        "quotation_lines": "quantity",
        "quotation_components": "quantity",
        "quotation_audit": "version",
        "quotation_requests": "version",
    }
    for table, field in fields.items():
        with (
            pytest.raises(ProgrammingError) as caught,
            service.factory.begin() as session,
        ):
            session.execute(text(f"UPDATE {table} SET {field} = {field}"))
        assert caught.value.orig.sqlstate == "P0001"
        assert "Commercial revisions are immutable" in str(caught.value.orig)
    assert service.get(UUID(saved["id"]))["lines"] == saved["lines"]
    with service.factory() as session:
        assert session.scalar(text("SELECT current_version FROM quotations")) == 1
