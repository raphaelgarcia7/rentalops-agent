from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from rentalops_api.auth import Identity
from rentalops_api.customer_contracts import (
    CustomerCreate,
    CustomerEdit,
    CustomerSearch,
)
from rentalops_api.customer_models import Customer, CustomerAudit
from rentalops_api.customers import CustomerError, CustomerService
from rentalops_api.database import build_session_factory
from rentalops_api.models import AuthSession, Base, User

from ..conftest import migration_config
from ..unit.test_customer_contracts import synthetic_cpf

pytestmark = pytest.mark.integration


@pytest.fixture
def customers(migrated_engine):
    factory = build_session_factory(migrated_engine)
    now = datetime.now(UTC)
    with factory.begin() as session:
        user = User(email="synthetic-customer-actor@example.invalid")
        session.add(user)
        session.flush()
        auth = AuthSession(
            user_id=user.id,
            token_hash=uuid4().hex,
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(hours=12),
        )
        session.add(auth)
        session.flush()
        actor = Identity(user.id, auth.id, auth.expires_at, now + timedelta(hours=1))
    return CustomerService(factory), actor


def create(customers, name="Synthetic A", phone="(11) 91234-5678", **fields):
    service, actor = customers
    return service.create(CustomerCreate(name=name, phone=phone, **fields), actor)


def conflict(code, operation):
    with pytest.raises(CustomerError) as caught:
        operation()
    assert caught.value.status == 409 and caught.value.code == code
    return caught.value


def test_customer_migration_head_incremental_repeat_and_rollback_preserves_catalog(
    isolated_engine,
):
    with isolated_engine.begin() as session:
        config = migration_config(session)
        command.upgrade(config, "0004_catalog")
        user = session.scalar(
            text(
                "INSERT INTO users(email) "
                "VALUES ('synthetic-preserved@example.invalid') RETURNING id"
            )
        )
        product = uuid4()
        session.execute(
            text(
                "INSERT INTO products(id,name,price,is_active,version,created_by,"
                "updated_by,total_quantity,maintenance_quantity) "
                "VALUES (:id,'Synthetic product',1,true,1,:actor,:actor,0,0)"
            ),
            {"id": product, "actor": user},
        )
        previous = set(inspect(session).get_table_names())
        command.upgrade(config, "0005_customers")
        assert (
            session.scalar(text("SELECT version_num FROM alembic_version"))
            == "0005_customers"
        )
        assert set(inspect(session).get_table_names()) == previous | {
            "customers",
            "customer_audit",
        }
        assert (
            compare_metadata(
                MigrationContext.configure(
                    session,
                    opts={
                        "include_object": lambda *args: (
                            not args[1].startswith("quotation")
                            if args[2] == "table"
                            else True
                        )
                    },
                ),
                Base.metadata,
            )
            == []
        )
        customer = uuid4()
        session.execute(
            text(
                "INSERT INTO customers(id,name,phone,version,created_by,updated_by) "
                "VALUES (:id,'Synthetic person',:phone,1,:actor,:actor)"
            ),
            {"id": customer, "phone": "+5511912345678", "actor": user},
        )
        command.upgrade(config, "0005_customers")
        assert session.scalar(text("SELECT id FROM customers")) == customer
        command.downgrade(config, "0004_catalog")
        assert set(inspect(session).get_table_names()) == previous
        assert session.scalar(text("SELECT id FROM products")) == product
        assert session.scalar(text("SELECT id FROM users")) == user
        command.upgrade(config, "0005_customers")
        assert session.scalar(text("SELECT count(*) FROM customers")) == 0


def test_minimum_progressive_same_identity_actor_metadata_and_rollback(customers):
    service, actor = customers
    customer = create(customers)
    identifier = customer["id"]
    assert isinstance(identifier, UUID)
    assert customer["cpf"] is customer["email"] is customer["address"] is None
    assert customer["created_by"] == customer["updated_by"] == actor.user_id
    assert customer["created_at"].utcoffset() == timedelta(0)
    assert customer["version"] == 1
    assert customer["history"][0]["changed_fields"] == ["name", "phone"]
    cpf = synthetic_cpf()
    updated = service.edit(
        identifier,
        CustomerEdit(
            expected_version=1,
            name="Synthetic edited",
            cpf=cpf,
            rg="synthetic",
            address={"city": "Synthetic"},
        ),
        actor,
    )
    assert updated["id"] == identifier and updated["version"] == 2
    assert updated["history"][-1]["changed_fields"] == ["address", "cpf", "name", "rg"]
    assert updated["history"][-1]["session_id"] == actor.session_id
    assert cpf not in str(updated["history"]) and str(customer["phone"]) not in str(
        updated["history"]
    )
    with patch.object(
        Session, "commit", side_effect=OperationalError("synthetic", {}, Exception())
    ):
        with pytest.raises(OperationalError):
            service.edit(
                identifier,
                CustomerEdit(expected_version=2, name="Failed mutation"),
                actor,
            )
        with pytest.raises(OperationalError):
            create(customers, name="Failed create", phone="(41) 91234-5678")
    current = service.get(identifier)
    assert current["name"] == "Synthetic edited" and current["version"] == 2
    assert len(current["history"]) == 2
    assert service.search(CustomerSearch())["total"] == 1
    conflict(
        "stale_version",
        lambda: service.edit(
            identifier, CustomerEdit(expected_version=1, notes="Stale"), actor
        ),
    )


def test_contact_warning_acknowledgement_new_contact_and_edit(customers):
    service, actor = customers
    first = create(customers)
    warning = conflict(
        "shared_contact",
        lambda: create(customers, name="Synthetic B", phone="+55 11 91234-5678"),
    )
    assert warning.existing_ids == [first["id"]]
    second = create(
        customers, name="Synthetic B", acknowledged_shared_contact=warning.existing_ids
    )
    assert first["id"] != second["id"]
    fresh = conflict(
        "shared_contact",
        lambda: create(
            customers,
            name="Synthetic C",
            acknowledged_shared_contact=warning.existing_ids,
        ),
    )
    assert set(fresh.existing_ids) == {first["id"], second["id"]}
    third = create(customers, name="Synthetic C", phone="(21) 91234-5678")
    edit_warning = conflict(
        "shared_contact",
        lambda: service.edit(
            third["id"],
            CustomerEdit(expected_version=1, phone="(11) 91234-5678"),
            actor,
        ),
    )
    assert set(edit_warning.existing_ids) == {first["id"], second["id"]}
    updated = service.edit(
        third["id"],
        CustomerEdit(
            expected_version=1,
            phone="(11) 91234-5678",
            acknowledged_shared_contact=edit_warning.existing_ids,
        ),
        actor,
    )
    assert updated["version"] == 2 and updated["id"] == third["id"]
    # Unchanged shared contact does not require acknowledging it for every edit.
    assert (
        service.edit(
            third["id"], CustomerEdit(expected_version=2, notes="Synthetic note"), actor
        )["version"]
        == 3
    )


def test_progressive_address_preserves_omitted_members_and_explicit_clear(customers):
    service, actor = customers
    record = create(
        customers,
        address={"street": "Synthetic street", "city": "Synthetic city", "state": "SP"},
    )
    identifier = record["id"]
    edited = service.edit(
        identifier, CustomerEdit(expected_version=1, address={"state": "RJ"}), actor
    )
    assert edited["address"]["street"] == "Synthetic street"
    assert edited["address"]["city"] == "Synthetic city"
    assert edited["address"]["state"] == "RJ"
    cleared_member = service.edit(
        identifier, CustomerEdit(expected_version=2, address={"city": " "}), actor
    )
    assert cleared_member["address"]["city"] is None
    assert cleared_member["address"]["street"] == "Synthetic street"
    unchanged = service.edit(
        identifier, CustomerEdit(expected_version=3, address={}), actor
    )
    assert unchanged["address"] == cleared_member["address"]
    assert unchanged["history"][-1]["changed_fields"] == []
    cleared = service.edit(
        identifier, CustomerEdit(expected_version=4, address=None), actor
    )
    assert cleared["id"] == identifier and cleared["address"] is None
    assert cleared["history"][-1]["changed_fields"] == ["address"]


def test_cpf_duplicate_create_edit_database_constraint_nulls_and_atomic_audit(
    customers,
):
    service, actor = customers
    first = create(customers, cpf=synthetic_cpf())
    second = create(customers, name="Synthetic B", phone="(21) 91234-5678")
    third = create(customers, name="Synthetic C", phone="(31) 91234-5678")
    for operation in (
        lambda: create(customers, phone="(41) 91234-5678", cpf=synthetic_cpf()),
        lambda: service.edit(
            second["id"],
            CustomerEdit(expected_version=1, name="Must rollback", cpf=synthetic_cpf()),
            actor,
        ),
    ):
        assert conflict("duplicate_cpf", operation).existing_ids == [first["id"]]
    assert service.get(second["id"])["name"] == "Synthetic B"
    assert service.get(third["id"])["cpf"] is None
    with service.factory() as session:
        for fields in (
            {"cpf": synthetic_cpf()},
            {"name": " "},
            {"version": 0},
            {"phone": "bad"},
            {"created_by": uuid4()},
        ):
            with pytest.raises(IntegrityError):
                session.add(
                    Customer(
                        **{
                            "name": "Synthetic raw",
                            "phone": "+5511912345678",
                            "created_by": actor.user_id,
                            "updated_by": actor.user_id,
                            **fields,
                        }
                    )
                )
                session.commit()
            session.rollback()
        assert len(session.scalars(select(Customer)).all()) == 3
        assert len(session.scalars(select(CustomerAudit)).all()) == 3


@pytest.mark.parametrize(
    "mode", ["create_cpf", "edit_cpf", "version", "create_phone", "edit_phone"]
)
def test_concurrent_database_invariants(customers, mode):
    service, actor = customers
    barrier = Barrier(2)
    initial = [
        create(customers, phone="(21) 91234-5678"),
        create(customers, phone="(31) 91234-5678"),
    ]

    def operation(index):
        barrier.wait(timeout=10)
        try:
            if mode == "create_cpf":
                return create(
                    customers,
                    phone=["(41) 91234-5678", "(51) 91234-5678"][index],
                    cpf=synthetic_cpf(),
                )
            if mode == "create_phone":
                return create(customers)
            identifier = initial[0]["id"] if mode == "version" else initial[index]["id"]
            fields = (
                {"cpf": synthetic_cpf()}
                if mode == "edit_cpf"
                else {"notes": f"Synthetic {index}"}
                if mode == "version"
                else {"phone": "(11) 91234-5678"}
            )
            return service.edit(
                identifier, CustomerEdit(expected_version=1, **fields), actor
            )
        except CustomerError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, (0, 1)))
    success = [item for item in results if isinstance(item, dict)]
    failures = [item for item in results if isinstance(item, CustomerError)]
    assert len(success) == len(failures) == 1
    assert failures[0].code == (
        "stale_version"
        if mode == "version"
        else "shared_contact"
        if "phone" in mode
        else "duplicate_cpf"
    )
    if mode != "version":
        assert failures[0].existing_ids == [success[0]["id"]]


def test_search_defaults_maximum_pages_stable_order_exact_filters_and_wildcards(
    customers,
):
    service, _ = customers
    first = create(customers, name="Synthetic %_", cpf=synthetic_cpf())
    for _ in range(27):
        create(
            customers,
            name="Synthetic Z",
            acknowledged_shared_contact=[
                row["id"]
                for row in service.search(CustomerSearch(page_size=100))["items"]
            ],
        )
    page1 = service.search(CustomerSearch())
    page2 = service.search(CustomerSearch(page=2))
    assert (
        page1["total"] == 28 and len(page1["items"]) == 25 and len(page2["items"]) == 3
    )
    combined = page1["items"] + page2["items"]
    assert [(item["name"], item["id"]) for item in combined] == sorted(
        (item["name"], item["id"]) for item in combined
    )
    assert service.search(CustomerSearch(name="%_"))["total"] == 1
    assert (
        service.search(CustomerSearch(cpf=synthetic_cpf()))["items"][0]["id"]
        == first["id"]
    )
    assert service.search(CustomerSearch(phone="(11) 91234-5678"))["total"] == 28
    assert service.search(CustomerSearch(name="missing"))["total"] == 0
    assert service.search(CustomerSearch(page_size=100))["page_size"] == 100
