from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from rentalops_api.auth import (
    COOKIE_NAME,
    PASSWORD_HASHER,
    AuthError,
    AuthService,
    AuthSettings,
    token_hash,
)
from rentalops_api.auth_cli import main as cli
from rentalops_api.auth_routes import auth_service
from rentalops_api.database import build_session_factory
from rentalops_api.main import app
from rentalops_api.models import (
    AuthAudit,
    AuthSession,
    LoginFailure,
    PasswordLink,
    User,
)

from ..conftest import migration_config

pytestmark = pytest.mark.integration
EMAIL = "operator@example.invalid"
PASSWORD = "synthetic pass phrase"
ORIGIN = "http://localhost:5173"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 3, 12, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def service(migrated_engine: Engine):
    return AuthService(
        build_session_factory(migrated_engine),
        AuthSettings(ORIGIN, False, "synthetic-rate-key" * 3),
        Clock(),
    )


def initialize(service, email=EMAIL):
    user_id, _ = service.create_user(email)
    token = service.issue_link(email, "access")
    service.set_password(token, PASSWORD)
    return user_id


def expect_error(status, callback):
    with pytest.raises(AuthError) as failure:
        callback()
    assert failure.value.status == status


def test_closed_access_argon2id_idempotent_normalization_and_equal_accounts(service):
    user_id = initialize(service)
    assert service.create_user(" OPERATOR@EXAMPLE.INVALID ") == (user_id, False)
    token, identity = service.login(EMAIL, PASSWORD, "loopback")
    assert len(token) >= 43
    assert identity.user_id == user_id
    with service.factory() as db:
        user = db.get(User, user_id)
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD_HASHER.verify(user.password_hash, PASSWORD)
        assert db.scalar(select(func.count()).select_from(User)) == 1
        session = db.scalar(select(AuthSession))
        assert (
            session.token_hash == token_hash(token) and token not in session.token_hash
        )
    for email in ("third@example.invalid", "fourth@example.invalid"):
        initialize(service, email)
        assert service.login(email, PASSWORD, "loopback")[1].user_id != user_id
    expect_error(401, lambda: service.login("unknown@example.invalid", PASSWORD, "x"))
    service.create_user("empty@example.invalid")
    expect_error(401, lambda: service.login("empty@example.invalid", PASSWORD, "x"))
    service.deactivate(EMAIL)
    expect_error(401, lambda: service.login(EMAIL, PASSWORD, "x"))


def test_link_boundaries_wrong_purpose_new_link_and_single_use(service):
    user_id, _ = service.create_user(EMAIL)
    old = service.issue_link(EMAIL, "access")
    new = service.issue_link(EMAIL, "access")
    expect_error(400, lambda: service.set_password(old, PASSWORD))
    expect_error(400, lambda: service.set_password("unknown", PASSWORD))
    expect_error(400, lambda: service.issue_link(EMAIL, "other"))
    service.clock.advance(minutes=30)
    expect_error(400, lambda: service.set_password(new, PASSWORD))
    newest = service.issue_link(EMAIL, "access")
    service.clock.advance(minutes=29, seconds=59)
    service.set_password(newest, PASSWORD)
    expect_error(400, lambda: service.set_password(newest, PASSWORD))
    expect_error(400, lambda: service.issue_link(EMAIL, "access"))
    with service.factory() as db:
        links = db.scalars(select(PasswordLink)).all()
        assert len(links) == 3
        assert all(
            link.user_id == user_id and len(link.token_hash) == 64 for link in links
        )
        assert db.scalar(select(func.count()).select_from(AuthAudit)) >= 5


def test_access_link_cannot_overwrite_initialized_account(service):
    user_id, _ = service.create_user(EMAIL)
    token = service.issue_link(EMAIL, "access")
    with service.factory.begin() as db:
        db.get(User, user_id).password_hash = PASSWORD_HASHER.hash(PASSWORD)
    expect_error(400, lambda: service.set_password(token, "another synthetic password"))
    service.login(EMAIL, PASSWORD, "x")


def test_two_concurrent_consumers_exactly_one_commits(service):
    service.create_user(EMAIL)
    token = service.issue_link(EMAIL, "access")
    barrier = Barrier(2)

    def consume(_):
        barrier.wait(timeout=10)
        try:
            service.set_password(token, PASSWORD)
            return "committed"
        except AuthError as error:
            assert error.status == 400
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(consume, range(2))) == ["committed", "rejected"]
    with service.factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthAudit)
                .where(AuthAudit.code == "password_link_consumed")
            )
            == 1
        )


def test_recovery_generation_reset_deactivation_and_restart_revocation(service):
    user_id = initialize(service)
    first, _ = service.login(EMAIL, PASSWORD, "x")
    second, _ = service.login(EMAIL, PASSWORD, "x")
    service.logout(first)
    expect_error(401, lambda: service.identity(first))
    assert service.identity(second).user_id == user_id
    recovery = service.issue_link(EMAIL, "reset")
    restarted = AuthService(service.factory, service.settings, service.clock)
    expect_error(401, lambda: restarted.identity(second))
    after_issue, _ = restarted.login(EMAIL, PASSWORD, "x")
    next_recovery = restarted.issue_link(EMAIL, "reset")
    expect_error(400, lambda: restarted.set_password(recovery, PASSWORD))
    later_session, _ = restarted.login(EMAIL, PASSWORD, "x")
    restarted.set_password(next_recovery, "another synthetic password")
    for token in (first, second, after_issue, later_session):
        expect_error(401, lambda token=token: restarted.identity(token))
    active, _ = restarted.login(EMAIL, "another synthetic password", "x")
    last_link = restarted.issue_link(EMAIL, "reset")
    restarted.deactivate(EMAIL)
    expect_error(401, lambda: restarted.identity(active))
    expect_error(400, lambda: restarted.set_password(last_link, PASSWORD))
    expect_error(400, lambda: restarted.issue_link(EMAIL, "reset"))
    with service.factory() as db:
        assert db.get(User, user_id) is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthAudit)
                .where(AuthAudit.code == "account_deactivated")
            )
            == 1
        )


def test_expiry_exact_boundaries_polling_activity_throttle_and_absolute(service):
    initialize(service)
    token, initial = service.login(EMAIL, PASSWORD, "x")
    service.clock.advance(minutes=59, seconds=59)
    for _ in range(3):
        assert service.identity(token).idle_expires_at == initial.idle_expires_at
    service.clock.advance(seconds=1)
    expect_error(401, lambda: service.identity(token, activity=True))
    active, initial = service.login(EMAIL, PASSWORD, "x")
    service.clock.advance(seconds=29)
    assert (
        service.identity(active, activity=True).idle_expires_at
        == initial.idle_expires_at
    )
    service.clock.advance(seconds=1)
    assert (
        service.identity(active, activity=True).idle_expires_at
        > initial.idle_expires_at
    )
    for _ in range(11):
        service.clock.advance(minutes=59)
        assert service.identity(active, activity=True).expires_at == initial.expires_at
    service.clock.now = initial.expires_at - timedelta(seconds=1)
    # Last intentional activity needs to remain within the idle window.
    with service.factory.begin() as db:
        row = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash(active))
        )
        row.last_activity = service.clock.now - timedelta(minutes=1)
    assert service.identity(active).expires_at == initial.expires_at
    service.clock.advance(seconds=1)
    expect_error(401, lambda: service.identity(active))
    expect_error(401, lambda: service.identity(None, activity=True))


def test_identifier_limit_survives_restart_and_window_is_exact(service):
    initialize(service)
    for _ in range(10):
        expect_error(401, lambda: service.login(EMAIL, "wrong synthetic password", "x"))
    restarted = AuthService(service.factory, service.settings, service.clock)
    expect_error(429, lambda: restarted.login(EMAIL, PASSWORD, "another-origin"))
    service.clock.advance(minutes=14, seconds=59)
    expect_error(429, lambda: restarted.login(EMAIL, PASSWORD, "x"))
    service.clock.advance(seconds=1)
    restarted.login(EMAIL, PASSWORD, "x")
    with service.factory() as db:
        failures = db.scalars(select(LoginFailure)).all()
        assert len(failures) == 10
        assert all(
            len(item.identifier_hash) == 64
            and len(item.origin_hash) == 64
            and item.identifier_hash != EMAIL
            and item.origin_hash != "x"
            for item in failures
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthAudit)
                .where(AuthAudit.code == "login_failed")
            )
            == 10
        )


def test_origin_limit_and_concurrent_failures_cannot_bypass(service):
    for n in range(30):
        expect_error(
            401, lambda n=n: service.login(f"absent{n}@example.invalid", PASSWORD, "x")
        )
    expect_error(429, lambda: service.login("new@example.invalid", PASSWORD, "x"))
    barrier = Barrier(12)

    def fail(_):
        barrier.wait(timeout=15)
        try:
            service.login(EMAIL, PASSWORD, "other-origin")
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=12) as executor:
        outcomes = list(executor.map(fail, range(12)))
    assert outcomes.count(401) == 10 and outcomes.count(429) == 2


def test_atomic_rollback_does_not_consume_token_or_change_password(service):
    service.create_user(EMAIL)
    token = service.issue_link(EMAIL, "access")
    with patch.object(
        service, "audit", side_effect=OperationalError("synthetic", {}, None)
    ):
        with pytest.raises(OperationalError):
            service.set_password(token, PASSWORD)
    service.set_password(token, PASSWORD)
    assert service.login(EMAIL, PASSWORD, "x")[1].user_id


def test_incremental_migration_preserves_identity_downgrade_and_constraints(
    isolated_engine,
):
    with isolated_engine.begin() as db:
        command.upgrade(migration_config(db), "0001_team_identity")
        user_id = db.scalar(
            text(
                "INSERT INTO users(email) VALUES ('keep@example.invalid') RETURNING id"
            )
        )
        command.upgrade(migration_config(db), "head")
        command.upgrade(migration_config(db), "head")
        assert db.scalar(text("SELECT id FROM users")) == user_id
        assert db.scalar(text("SELECT password_hash FROM users")) is None
        command.downgrade(migration_config(db), "0001_team_identity")
        assert set(inspect(db).get_table_names()) == {"alembic_version", "users"}
        assert db.scalar(text("SELECT id FROM users")) == user_id
        command.upgrade(migration_config(db), "head")
    service = AuthService(
        build_session_factory(isolated_engine), AuthSettings(ORIGIN, False, "x" * 32)
    )
    service.issue_link("keep@example.invalid", "access")
    with service.factory() as db:
        link = db.scalar(select(PasswordLink))
        assert link.purpose == "access"
    with pytest.raises(IntegrityError), service.factory.begin() as db:
        db.add(
            PasswordLink(
                user_id=user_id,
                token_hash=link.token_hash,
                purpose="reset",
                created_at=link.created_at,
                expires_at=link.expires_at,
            )
        )
    with pytest.raises(IntegrityError), service.factory.begin() as db:
        db.add(
            PasswordLink(
                user_id=user_id,
                token_hash="a" * 64,
                purpose="wrong",
                created_at=link.created_at,
                expires_at=link.expires_at,
            )
        )


def test_http_contracts_csrf_protected_identity_cookie_no_secret_errors(
    service, caplog
):
    initialize(service)
    app.dependency_overrides[auth_service] = lambda: service
    try:
        with TestClient(app, base_url=ORIGIN) as client:
            assert client.get("/auth/session").status_code == 401
            assert client.get("/internal/identity").status_code == 401
            assert (
                client.post(
                    "/auth/activity", json={}, headers={"Origin": ORIGIN}
                ).status_code
                == 401
            )
            payload = {"email": EMAIL, "password": PASSWORD}
            for headers in ({}, {"Origin": "http://evil.invalid"}):
                assert (
                    client.post(
                        "/auth/password/login", json=payload, headers=headers
                    ).status_code
                    == 403
                )
            headers = {"Origin": ORIGIN}
            for changed in (
                payload | {"actor_id": "forged"},
                payload | {"password": "short"},
                payload | {"email": "invalid"},
            ):
                response = client.post(
                    "/auth/password/login", json=changed, headers=headers
                )
                assert response.status_code == 422
                assert (
                    "private-short" not in response.text
                    and "forged" not in response.text
                )
            response = client.post(
                "/auth/password/login", json=payload, headers=headers
            )
            assert response.status_code == 200
            cookie = response.headers["set-cookie"]
            assert (
                "HttpOnly" in cookie
                and "SameSite=lax" in cookie
                and "Domain" not in cookie
            )
            token = client.cookies.get(COOKIE_NAME)
            user_id = response.json()["user_id"]
            assert client.get("/internal/identity").json() == {"user_id": user_id}
            assert client.get("/auth/session").json() == response.json()
            assert client.get("/auth/session").headers["cache-control"] == "no-store"
            assert (
                client.post(
                    "/auth/logout", json={}, headers={"Origin": "http://evil.invalid"}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/auth/activity", json={"user_id": "fake"}, headers=headers
                ).status_code
                == 422
            )
            assert (
                client.post("/auth/logout", json={}, headers=headers).status_code == 204
            )
            assert client.get("/auth/session").status_code == 401
            invalid = client.post(
                "/auth/password/set",
                json={"token": "invalid", "password": PASSWORD},
                headers=headers,
            )
            assert invalid.status_code == 400
            # Token in query has no effect; only the typed body is accepted.
            assert (
                client.post(
                    "/auth/password/set", json={"password": PASSWORD}, headers=headers
                ).status_code
                == 422
            )
            assert token not in caplog.text and PASSWORD not in caplog.text
            assert "SELECT" not in caplog.text and EMAIL not in caplog.text
    finally:
        app.dependency_overrides.clear()


def test_production_cookie_secure_and_login_ignores_supplied_cookie(service):
    initialize(service)
    service.settings = AuthSettings("https://rentalops.example.invalid", True, "x" * 32)
    app.dependency_overrides[auth_service] = lambda: service
    try:
        with TestClient(app, base_url=service.settings.origin) as client:
            client.cookies.set(COOKIE_NAME, "client-chosen")
            response = client.post(
                "/auth/password/login",
                json={"email": EMAIL, "password": PASSWORD},
                headers={"Origin": service.settings.origin},
            )
            assert (
                response.status_code == 200
                and "Secure" in response.headers["set-cookie"]
            )
            assert "client-chosen" not in response.headers["set-cookie"]
    finally:
        app.dependency_overrides.clear()


def test_cli_exact_target_idempotent_no_secret_and_failure(service, capsys):
    other = initialize(service, "other@example.invalid")

    def run(command, email):
        with (
            patch("sys.argv", ["auth_cli", command, "--email", email]),
            patch(
                "rentalops_api.auth_cli.AuthSettings.from_environment",
                return_value=service.settings,
            ),
            patch("rentalops_api.auth_cli.build_engine") as engine,
            patch("rentalops_api.auth_cli.DatabaseSettings.from_environment"),
            patch("rentalops_api.auth_cli.AuthService", return_value=service),
        ):
            cli()
            engine.return_value.dispose.assert_called_once()

    run("create-user", EMAIL)
    assert "created user_id=" in capsys.readouterr().out
    run("create-user", EMAIL)
    assert "existing user_id=" in capsys.readouterr().out
    run("issue-access-link", EMAIL)
    # Capture privately; do not print URL/token to evidence or logs.
    private = capsys.readouterr().out.strip()
    assert private.startswith(ORIGIN + "/definir-senha#token=")
    service.set_password(private.split("#token=")[1], PASSWORD)
    run("issue-reset-link", EMAIL)
    assert capsys.readouterr().out.startswith(ORIGIN + "/definir-senha#token=")
    run("deactivate-user", EMAIL)
    assert "deactivated user_id=" in capsys.readouterr().out
    assert service.login("other@example.invalid", PASSWORD, "x")[1].user_id == other
    with pytest.raises(SystemExit) as failure:
        run("issue-access-link", EMAIL)
    assert failure.value.code == 1
    assert PASSWORD not in capsys.readouterr().err
