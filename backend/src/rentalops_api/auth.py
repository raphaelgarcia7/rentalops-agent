"""Deterministic authentication services shared by HTTP and the operator CLI."""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import HashingError, InvalidHashError, VerificationError
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.config import environment_values
from rentalops_api.models import (
    AuthAudit,
    AuthSession,
    LoginFailure,
    PasswordLink,
    PasswordSetAttempt,
    User,
)

PASSWORD_HASHER = PasswordHasher()
# Valid Argon2id work is performed for unknown and uninitialized accounts too.
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
COOKIE_NAME = "rentalops_session"


class AuthError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class AuthSettings:
    origin: str
    secure_cookie: bool
    rate_key: str = field(repr=False)

    @classmethod
    def from_values(cls, values: dict[str, str]) -> AuthSettings:
        origin = values.get("AUTH_ORIGIN", "")
        key = values.get("AUTH_RATE_KEY", "")
        environment = values.get("APP_ENV", "development")
        parsed = urlsplit(origin)
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("Invalid authentication configuration.") from None
        if (
            environment not in {"development", "production"}
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
            or len(key.encode()) < 32
            or (environment == "production" and parsed.scheme != "https")
            or (
                parsed.scheme == "http"
                and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            )
        ):
            raise ValueError("Invalid authentication configuration.")
        return cls(origin, environment == "production" or parsed.scheme == "https", key)

    @classmethod
    def from_environment(cls) -> AuthSettings:
        return cls.from_values(environment_values())


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    # Delivery/DNS is not checked; account authorization belongs to the operator.
    if (
        len(normalized) > 320
        or normalized.count("@") != 1
        or any(char.isspace() for char in normalized)
        or not all(normalized.split("@"))
        or "." not in normalized.split("@")[-1]
    ):
        raise ValueError("Invalid email.")
    return normalized


def validate_password(value: str) -> str:
    if not 12 <= len(value) <= 128:
        raise ValueError("Password must contain 12–128 characters.")
    return value


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Identity:
    user_id: UUID
    session_id: UUID
    expires_at: datetime
    idle_expires_at: datetime


class AuthService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: AuthSettings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.clock = clock

    def audit(
        self,
        db: Session,
        code: str,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> None:
        db.add(
            AuthAudit(
                code=code,
                user_id=user_id,
                session_id=session_id,
                created_at=self.clock(),
            )
        )

    def create_user(self, email: str) -> tuple[UUID, bool]:
        email = normalize_email(email)
        with self.factory.begin() as db:
            result = db.scalar(
                insert(User)
                .values(email=email)
                .on_conflict_do_nothing(index_elements=[User.email])
                .returning(User.id)
            )
            if result is not None:
                self.audit(db, "account_created", result)
                return result, True
            existing = db.scalar(select(User.id).where(User.email == email))
            assert existing is not None
            return existing, False

    def locked_user(self, db: Session, email: str) -> User:
        user = db.scalar(
            select(User).where(User.email == normalize_email(email)).with_for_update()
        )
        if user is None or not user.is_active:
            raise AuthError(400, "Conta ativa autorizada necessária.")
        return user

    def revoke(self, db: Session, user_id: UUID) -> None:
        now = self.clock()
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.execute(
            update(PasswordLink)
            .where(PasswordLink.user_id == user_id, PasswordLink.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.audit(db, "account_access_revoked", user_id)

    def issue_link(self, email: str, purpose: str) -> str:
        if purpose not in {"access", "reset"}:
            raise AuthError(400, "Finalidade inválida.")
        with self.factory.begin() as db:
            user = self.locked_user(db, email)
            if purpose == "access" and user.password_hash is not None:
                raise AuthError(400, "Conta já inicializada; use recuperação.")
            if purpose == "reset":
                self.revoke(db, user.id)
            else:
                db.execute(
                    update(PasswordLink)
                    .where(
                        PasswordLink.user_id == user.id,
                        PasswordLink.revoked_at.is_(None),
                    )
                    .values(revoked_at=self.clock())
                )
            token = secrets.token_urlsafe(32)
            now = self.clock()
            db.add(
                PasswordLink(
                    user_id=user.id,
                    token_hash=token_hash(token),
                    purpose=purpose,
                    created_at=now,
                    expires_at=now + timedelta(minutes=30),
                )
            )
            self.audit(
                db,
                "access_link_issued" if purpose == "access" else "reset_link_issued",
                user.id,
            )
        return token

    def deactivate(self, email: str) -> UUID:
        with self.factory.begin() as db:
            user = db.scalar(
                select(User)
                .where(User.email == normalize_email(email))
                .with_for_update()
            )
            if user is None:
                raise AuthError(400, "Conta autorizada necessária.")
            user.is_active = False
            self.revoke(db, user.id)
            self.audit(db, "account_deactivated", user.id)
            return user.id

    def password_link(
        self, db: Session, digest: str, *, lock_user: bool
    ) -> tuple[User, PasswordLink]:
        denied = AuthError(400, "Link inválido ou expirado. Procure o administrador.")
        link = db.scalar(select(PasswordLink).where(PasswordLink.token_hash == digest))
        if link is None:
            raise denied
        query = select(User).where(User.id == link.user_id)
        user = db.scalar(query.with_for_update() if lock_user else query)
        if lock_user:
            # All account mutations lock user first; re-read after a concurrent writer.
            db.refresh(link)
        if (
            user is None
            or not user.is_active
            or link.consumed_at is not None
            or link.revoked_at is not None
            or self.clock() >= link.expires_at
            or link.purpose not in {"access", "reset"}
            or (link.purpose == "access" and user.password_hash is not None)
        ):
            raise denied
        return user, link

    def set_password(self, token: str, password: str, origin: str) -> None:
        validate_password(password)
        digest = token_hash(token)
        identifier = self.pseudonym("password-set-token", token)
        source = self.pseudonym("password-set-origin", origin)
        # Commit every admitted attempt, even invalid ones or a later hash/DB failure.
        # These short counter locks end before Argon2, and survive process restarts.
        with self.factory.begin() as db:
            self.check_attempt_budget(db, PasswordSetAttempt, identifier, source)
            db.add(
                PasswordSetAttempt(
                    identifier_hash=identifier,
                    origin_hash=source,
                    created_at=self.clock(),
                )
            )
            try:
                self.password_link(db, digest, lock_user=False)
                invalid = False
            except AuthError:
                invalid = True
        if invalid:
            raise AuthError(400, "Link inválido ou expirado. Procure o administrador.")
        # Only a verified, budgeted link reaches expensive work. No transaction or
        # account/counter lock remains open while hashing; concurrent work is bounded.
        try:
            encoded = PASSWORD_HASHER.hash(password)
        except HashingError:
            raise AuthError(503, "Serviço indisponível.") from None
        with self.factory.begin() as db:
            # Validate again under the account lock before committing single use.
            user, link = self.password_link(db, digest, lock_user=True)
            now = self.clock()
            link.consumed_at = now
            user.password_hash = encoded
            self.revoke(db, user.id)
            self.audit(db, "password_link_consumed", user.id)

    def pseudonym(self, namespace: str, value: str) -> str:
        return hmac.new(
            self.settings.rate_key.encode(),
            f"{namespace}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def check_attempt_budget(
        self,
        db: Session,
        records: type[LoginFailure] | type[PasswordSetAttempt],
        identifier: str,
        source: str,
    ) -> None:
        # Deterministic ordering serializes both counters across processes.
        for key in sorted({identifier, source}):
            db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int.from_bytes(bytes.fromhex(key)[:8], signed=True)},
            )
        cutoff = self.clock() - timedelta(minutes=15)
        for column, value, limit in (
            (records.identifier_hash, identifier, 10),
            (records.origin_hash, source, 30),
        ):
            count = db.scalar(
                select(func.count())
                .select_from(records)
                .where(column == value, records.created_at > cutoff)
            )
            if count is not None and count >= limit:
                raise AuthError(429, "Muitas tentativas. Aguarde 15 minutos.")

    def login(self, email: str, password: str, origin: str) -> tuple[str, Identity]:
        email = normalize_email(email)
        identifier = self.pseudonym("identifier", email)
        source = self.pseudonym("origin", origin)
        # Serialize counters across processes, including unknown account attempts.
        with self.factory.begin() as db:
            self.check_attempt_budget(db, LoginFailure, identifier, source)
            user = db.scalar(select(User).where(User.email == email).with_for_update())
            stored = user.password_hash if user and user.password_hash else DUMMY_HASH
            valid: bool
            try:
                valid = PASSWORD_HASHER.verify(stored, password)
            except VerificationError, InvalidHashError:
                valid = False
            if (
                not valid
                or user is None
                or not user.is_active
                or not user.password_hash
            ):
                db.add(
                    LoginFailure(
                        identifier_hash=identifier,
                        origin_hash=source,
                        created_at=self.clock(),
                    )
                )
                self.audit(db, "login_failed")
                # Failure must persist; raise only after the transaction commits.
                outcome = None
            else:
                if PASSWORD_HASHER.check_needs_rehash(stored):
                    user.password_hash = PASSWORD_HASHER.hash(password)
                token = secrets.token_urlsafe(32)
                now = self.clock()
                session = AuthSession(
                    user_id=user.id,
                    token_hash=token_hash(token),
                    created_at=now,
                    last_activity=now,
                    expires_at=now + timedelta(hours=12),
                )
                db.add(session)
                db.flush()
                self.audit(db, "login_succeeded", user.id, session.id)
                outcome = (
                    token,
                    Identity(
                        user.id,
                        session.id,
                        session.expires_at,
                        now + timedelta(hours=1),
                    ),
                )
        if outcome is None:
            raise AuthError(401, "E-mail ou senha inválidos.")
        return outcome

    def authenticated(self, db: Session, token: str | None) -> tuple[User, AuthSession]:
        denied = AuthError(401, "Sessão encerrada. Entre novamente.")
        if not token:
            raise denied
        session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash(token))
        )
        if session is None:
            raise denied
        user = db.scalar(
            select(User).where(User.id == session.user_id).with_for_update()
        )
        db.refresh(session)
        now = self.clock()
        if (
            user is None
            or not user.is_active
            or session.revoked_at is not None
            or now >= session.expires_at
            or now >= session.last_activity + timedelta(hours=1)
        ):
            raise denied
        return user, session

    def identity(self, token: str | None, *, activity: bool = False) -> Identity:
        with self.factory.begin() as db:
            user, session = self.authenticated(db, token)
            now = self.clock()
            if activity and now - session.last_activity >= timedelta(seconds=30):
                session.last_activity = now
            return Identity(
                user.id,
                session.id,
                session.expires_at,
                session.last_activity + timedelta(hours=1),
            )

    def logout(self, token: str | None) -> None:
        with self.factory.begin() as db:
            user, session = self.authenticated(db, token)
            session.revoked_at = self.clock()
            self.audit(db, "logout", user.id, session.id)
