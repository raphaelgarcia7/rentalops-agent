"""Catalog use cases, deterministic stock and transactional audit history."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.auth import Identity
from rentalops_api.catalog_contracts import (
    MAX_QUANTITY,
    KitCreate,
    KitEdit,
    MaintenanceCommand,
    PhotoEdit,
    ProductCreate,
    ProductEdit,
    ReasonCommand,
    StockAdjustment,
    aggregate_items,
)
from rentalops_api.catalog_models import (
    CatalogHistory,
    CatalogRecord,
    Kit,
    KitItem,
    MaintenanceEntry,
    Product,
    ProductPhoto,
    StockMovement,
)
from rentalops_api.catalog_storage import (
    CatalogError,
    PhotoStorage,
    normalize_image,
)
from rentalops_api.database import session_scope
from rentalops_api.operations import active_operation


def product_snapshot(product: Product) -> dict[str, object]:
    return {
        "id": str(product.id),
        "name": product.name,
        "price": str(product.price),
        "description": product.description,
        "category": product.category,
        "color": product.color,
        "dimensions": product.dimensions,
        "observation": product.observation,
        "replacement_value": str(product.replacement_value)
        if product.replacement_value is not None
        else None,
        "total_quantity": product.total_quantity,
        "maintenance_quantity": product.maintenance_quantity,
        "apt_quantity": product.total_quantity - product.maintenance_quantity,
        "is_active": product.is_active,
        "version": product.version,
        "created_by": str(product.created_by),
        "updated_by": str(product.updated_by),
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def photo_snapshot(photo: ProductPhoto) -> dict[str, object]:
    return {
        "id": str(photo.id),
        "format": photo.format,
        "size": photo.size,
        "sha256": photo.sha256,
        "order": photo.position,
        "is_principal": photo.is_principal,
    }


class CatalogService:
    def __init__(self, factory: sessionmaker[Session], storage: PhotoStorage) -> None:
        self.factory = factory
        self.storage = storage

    def _commit_product(self, session: Session, product: Product) -> dict[str, object]:
        # Assemble the response while the row lock still protects this version.
        session.flush()
        result = self._product_detail(session, product)
        session.commit()
        return result

    def _locked(
        self,
        session: Session,
        model: type[Product] | type[Kit],
        identifier: UUID,
        version: int,
    ) -> Product | Kit:
        record = session.scalar(
            select(model).where(model.id == identifier).with_for_update()
        )
        if record is None:
            raise CatalogError(404, "Cadastro não encontrado.")
        assert isinstance(record, Product | Kit)
        if record.version != version:
            raise CatalogError(
                409,
                "Outra pessoa alterou este cadastro. Seu rascunho foi mantido; "
                "consulte a versão atual antes de tentar novamente.",
            )
        return record

    def _touch(self, record: CatalogRecord, actor: Identity) -> None:
        record.version += 1
        record.updated_at = datetime.now(UTC)
        record.updated_by = actor.user_id

    def _audit(
        self,
        session: Session,
        record: Product | Kit,
        actor: Identity,
        operation: str,
        reason: str,
        snapshot: dict[str, object],
    ) -> None:
        session.add(
            CatalogHistory(
                product_id=record.id if isinstance(record, Product) else None,
                kit_id=record.id if isinstance(record, Kit) else None,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                operation=operation,
                reason=reason,
                snapshot=snapshot,
            )
        )

    def _movement(
        self,
        session: Session,
        product: Product,
        actor: Identity,
        operation: str,
        reason: str,
        quantity: int,
    ) -> None:
        session.add(
            StockMovement(
                product_id=product.id,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                operation=operation,
                reason=reason,
                quantity=quantity,
                total_after=product.total_quantity,
                maintenance_after=product.maintenance_quantity,
            )
        )

    def create_product(
        self, payload: ProductCreate, actor: Identity
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            fields = payload.model_dump(exclude={"initial_quantity"})
            product = Product(
                **fields,
                total_quantity=payload.initial_quantity,
                maintenance_quantity=0,
                created_by=actor.user_id,
                updated_by=actor.user_id,
            )
            session.add(product)
            session.flush()
            self._movement(
                session,
                product,
                actor,
                "initial",
                "Estoque inicial no cadastro",
                payload.initial_quantity,
            )
            self._audit(
                session,
                product,
                actor,
                "created",
                "Cadastro inicial",
                product_snapshot(product),
            )
            return self._commit_product(session, product)

    def edit_product(
        self, identifier: UUID, payload: ProductEdit, actor: Identity
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            record = self._locked(
                session, Product, identifier, payload.expected_version
            )
            assert isinstance(record, Product)
            for key, value in payload.model_dump(exclude={"expected_version"}).items():
                setattr(record, key, value)
            self._touch(record, actor)
            self._audit(
                session,
                record,
                actor,
                "edited",
                "Edição cadastral",
                product_snapshot(record),
            )
            return self._commit_product(session, record)

    def inactivate(
        self, kind: str, identifier: UUID, payload: ReasonCommand, actor: Identity
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            record = self._locked(
                session,
                Product if kind == "products" else Kit,
                identifier,
                payload.expected_version,
            )
            if not record.is_active:
                raise CatalogError(409, "Cadastro já está inativo.")
            record.is_active = False
            self._touch(record, actor)
            snapshot = (
                product_snapshot(record)
                if isinstance(record, Product)
                else self._kit_snapshot(session, record)
            )
            self._audit(session, record, actor, "inactivated", payload.reason, snapshot)
            session.flush()
            result = (
                self._product_detail(session, record)
                if isinstance(record, Product)
                else self._kit_detail(session, record)
            )
            session.commit()
            return result

    def adjust_stock(
        self, identifier: UUID, payload: StockAdjustment, actor: Identity
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            product = self._locked(
                session, Product, identifier, payload.expected_version
            )
            assert isinstance(product, Product)
            total = (
                payload.quantity
                if payload.operation == "correction"
                else product.total_quantity
                + (
                    payload.quantity
                    if payload.operation == "entry"
                    else -payload.quantity
                )
            )
            if not product.maintenance_quantity <= total <= MAX_QUANTITY:
                raise CatalogError(
                    422,
                    "Total deve ser válido e cobrir as unidades em manutenção. "
                    "Libere a manutenção antes de reduzir essas unidades.",
                )
            product.total_quantity = total
            self._touch(product, actor)
            self._movement(
                session,
                product,
                actor,
                payload.operation,
                payload.reason,
                payload.quantity,
            )
            return self._commit_product(session, product)

    def maintenance(
        self, identifier: UUID, payload: MaintenanceCommand, actor: Identity
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            product = self._locked(
                session, Product, identifier, payload.expected_version
            )
            assert isinstance(product, Product)
            if payload.quantity > product.total_quantity - product.maintenance_quantity:
                raise CatalogError(
                    422, "Quantidade supera as unidades aptas do cadastro."
                )
            product.maintenance_quantity += payload.quantity
            session.add(
                MaintenanceEntry(
                    product_id=identifier,
                    quantity=payload.quantity,
                    reason=payload.reason,
                )
            )
            self._touch(product, actor)
            self._movement(
                session, product, actor, "maintenance", payload.reason, payload.quantity
            )
            return self._commit_product(session, product)

    def release(
        self,
        identifier: UUID,
        entry_id: UUID,
        payload: MaintenanceCommand,
        actor: Identity,
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            product = self._locked(
                session, Product, identifier, payload.expected_version
            )
            assert isinstance(product, Product)
            entry = session.get(MaintenanceEntry, entry_id)
            if entry is None or entry.product_id != identifier:
                raise CatalogError(404, "Manutenção não encontrada neste produto.")
            if payload.quantity > entry.quantity - entry.released_quantity:
                raise CatalogError(422, "Quantidade supera o saldo desta manutenção.")
            entry.released_quantity += payload.quantity
            product.maintenance_quantity -= payload.quantity
            self._touch(product, actor)
            self._movement(
                session, product, actor, "release", payload.reason, payload.quantity
            )
            return self._commit_product(session, product)

    def _kit_items(self, session: Session, kit: Kit) -> list[dict[str, object]]:
        rows = session.execute(
            select(KitItem, Product)
            .join(Product, KitItem.product_id == Product.id)
            .where(KitItem.kit_id == kit.id)
            .order_by(Product.name, Product.id)
        ).all()
        return [
            {
                "product_id": str(product.id),
                "name": product.name,
                "quantity": item.quantity,
                "is_active": product.is_active,
            }
            for item, product in rows
        ]

    def _kit_snapshot(self, session: Session, kit: Kit) -> dict[str, object]:
        items = self._kit_items(session, kit)
        return {
            "id": str(kit.id),
            "name": kit.name,
            "price": str(kit.price),
            "is_active": kit.is_active,
            "version": kit.version,
            "created_by": str(kit.created_by),
            "updated_by": str(kit.updated_by),
            "created_at": kit.created_at.isoformat(),
            "updated_at": kit.updated_at.isoformat(),
            "items": items,
            "needs_review": any(not item["is_active"] for item in items),
        }

    def save_kit(
        self,
        payload: KitCreate | KitEdit,
        actor: Identity,
        identifier: UUID | None = None,
    ) -> dict[str, object]:
        try:
            quantities = aggregate_items(payload.items)
        except ValueError:
            raise CatalogError(422, "Quantidade de componente inválida.") from None
        with session_scope(self.factory) as session:
            if identifier is None:
                kit = Kit(
                    name=payload.name,
                    price=payload.price,
                    created_by=actor.user_id,
                    updated_by=actor.user_id,
                )
                session.add(kit)
                session.flush()
                operation = "created"
            else:
                assert isinstance(payload, KitEdit)
                record = self._locked(
                    session, Kit, identifier, payload.expected_version
                )
                assert isinstance(record, Kit)
                kit = record
                kit.name, kit.price = payload.name, payload.price
                self._touch(kit, actor)
                operation = "edited"
            products = session.scalars(
                select(Product)
                .where(Product.id.in_(quantities))
                .order_by(Product.id)
                .with_for_update(read=True)
            ).all()
            if len(products) != len(quantities) or any(
                not product.is_active for product in products
            ):
                raise CatalogError(
                    409,
                    "Selecione somente produtos existentes e ativos. "
                    "Remova ou substitua o componente inativo para revisar o kit.",
                )
            session.execute(delete(KitItem).where(KitItem.kit_id == kit.id))
            session.add_all(
                [
                    KitItem(kit_id=kit.id, product_id=key, quantity=value)
                    for key, value in quantities.items()
                ]
            )
            session.flush()
            self._audit(
                session,
                kit,
                actor,
                operation,
                "Composição e preço comercial",
                self._kit_snapshot(session, kit),
            )
            session.flush()
            result = self._kit_detail(session, kit)
            session.commit()
            return result

    def _history(
        self, session: Session, kind: str, identifier: UUID
    ) -> list[dict[str, object]]:
        column = (
            CatalogHistory.product_id if kind == "products" else CatalogHistory.kit_id
        )
        history = session.scalars(
            select(CatalogHistory)
            .where(column == identifier)
            .order_by(CatalogHistory.created_at.desc(), CatalogHistory.id)
        ).all()
        return [
            {
                "id": str(row.id),
                "actor_id": str(row.actor_id),
                "session_id": str(row.session_id),
                "operation": row.operation,
                "reason": row.reason,
                "snapshot": row.snapshot,
                "created_at": row.created_at.isoformat(),
            }
            for row in history
        ]

    def _product_detail(self, session: Session, product: Product) -> dict[str, object]:
        result = product_snapshot(product)
        result["history"] = self._history(session, "products", product.id)
        movements = session.scalars(
            select(StockMovement)
            .where(StockMovement.product_id == product.id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id)
        ).all()
        result["movements"] = [
            {
                "id": str(row.id),
                "actor_id": str(row.actor_id),
                "session_id": str(row.session_id),
                "operation": row.operation,
                "reason": row.reason,
                "quantity": row.quantity,
                "total_after": row.total_after,
                "maintenance_after": row.maintenance_after,
                "created_at": row.created_at.isoformat(),
            }
            for row in movements
        ]
        entries = session.scalars(
            select(MaintenanceEntry)
            .where(MaintenanceEntry.product_id == product.id)
            .order_by(MaintenanceEntry.created_at, MaintenanceEntry.id)
        ).all()
        result["maintenance"] = [
            {
                "id": str(row.id),
                "quantity": row.quantity,
                "released_quantity": row.released_quantity,
                "reason": row.reason,
            }
            for row in entries
        ]
        result["photos"] = [
            photo_snapshot(photo) for photo in self._photos(session, product.id)
        ]
        return result

    def _kit_detail(self, session: Session, kit: Kit) -> dict[str, object]:
        result = self._kit_snapshot(session, kit)
        result["history"] = self._history(session, "kits", kit.id)
        return result

    def get(self, kind: str, identifier: UUID) -> dict[str, object]:
        with session_scope(self.factory) as session:
            record = session.get(Product if kind == "products" else Kit, identifier)
            if record is None:
                raise CatalogError(404, "Cadastro não encontrado.")
            assert isinstance(record, Product | Kit)
            return (
                self._product_detail(session, record)
                if isinstance(record, Product)
                else self._kit_detail(session, record)
            )

    def list_records(
        self, kind: str, search: str, page: int, page_size: int
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            model = Product if kind == "products" else Kit
            # Treat wildcard characters literally rather than as a query language.
            clause = model.name.icontains(search, autoescape=True)
            total = (
                session.scalar(select(func.count()).select_from(model).where(clause))
                or 0
            )
            rows = session.scalars(
                select(model)
                .where(clause)
                .order_by(model.name, model.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            assert all(isinstance(row, Product | Kit) for row in rows)
            items = [
                product_snapshot(row)
                if isinstance(row, Product)
                else self._kit_snapshot(session, cast(Kit, row))
                for row in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def _photos(self, session: Session, identifier: UUID) -> list[ProductPhoto]:
        return list(
            session.scalars(
                select(ProductPhoto)
                .where(ProductPhoto.product_id == identifier, ProductPhoto.is_attached)
                .order_by(ProductPhoto.position, ProductPhoto.id)
            ).all()
        )

    def upload_photo(
        self,
        identifier: UUID,
        expected_version: int,
        data: bytes,
        content_type: str | None,
        actor: Identity,
    ) -> dict[str, object]:
        with active_operation():
            return self._upload_photo(
                identifier, expected_version, data, content_type, actor
            )

    def _upload_photo(
        self,
        identifier: UUID,
        expected_version: int,
        data: bytes,
        content_type: str | None,
        actor: Identity,
    ) -> dict[str, object]:
        # Decode and write outside DB transaction. Only our new file is compensable.
        self.storage.checked_root()
        normalized, image_format = normalize_image(data, content_type)
        stored = self.storage.write(normalized, image_format)
        committed = False
        try:
            with session_scope(self.factory) as session:
                product = self._locked(session, Product, identifier, expected_version)
                assert isinstance(product, Product)
                photos = self._photos(session, identifier)
                photo = ProductPhoto(
                    product_id=identifier,
                    storage_key=stored.key,
                    format=stored.image_format,
                    size=stored.size,
                    sha256=stored.sha256,
                    position=max((p.position for p in photos), default=-1) + 1,
                    is_principal=not photos,
                    created_by=actor.user_id,
                )
                session.add(photo)
                self._touch(product, actor)
                session.flush()
                self._audit(
                    session,
                    product,
                    actor,
                    "photo_added",
                    "Foto adicionada",
                    photo_snapshot(photo),
                )
                session.flush()
                result = self._product_detail(session, product)
                session.commit()
                committed = True
                return result
        except BaseException:
            if not committed:
                # A lost connection during COMMIT can leave its outcome unknown.
                # Delete only when a fresh transaction proves no metadata exists.
                try:
                    with session_scope(self.factory) as check:
                        absent = (
                            check.scalar(
                                select(ProductPhoto.id).where(
                                    ProductPhoto.storage_key == stored.key
                                )
                            )
                            is None
                        )
                    if absent:
                        self.storage.compensate(stored.key)
                except SQLAlchemyError:
                    pass
            raise

    def edit_photo(
        self,
        identifier: UUID,
        photo_id: UUID,
        payload: PhotoEdit | ReasonCommand,
        actor: Identity,
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            product = self._locked(
                session, Product, identifier, payload.expected_version
            )
            assert isinstance(product, Product)
            photo = session.get(ProductPhoto, photo_id)
            if photo is None or photo.product_id != identifier or not photo.is_attached:
                raise CatalogError(404, "Foto não encontrada nesta galeria.")
            if isinstance(payload, PhotoEdit):
                if payload.is_principal:
                    session.execute(
                        update(ProductPhoto)
                        .where(
                            ProductPhoto.product_id == identifier,
                            ProductPhoto.is_attached,
                        )
                        .values(is_principal=False)
                    )
                    session.flush()
                elif photo.is_principal:
                    raise CatalogError(
                        422, "Escolha outra foto como principal primeiro."
                    )
                photo.position = payload.order
                photo.is_principal = payload.is_principal
                reason, operation = "Ordem e foto principal", "photo_edited"
            else:
                photo.is_attached = False
                was_principal = photo.is_principal
                photo.is_principal = False
                session.flush()
                remaining = self._photos(session, identifier)
                if was_principal and remaining:
                    remaining[0].is_principal = True
                reason, operation = payload.reason, "photo_detached"
            self._touch(product, actor)
            self._audit(
                session, product, actor, operation, reason, photo_snapshot(photo)
            )
            return self._commit_product(session, product)

    def read_photo(self, photo_id: UUID) -> tuple[bytes, str]:
        self.storage.checked_root()
        with session_scope(self.factory) as session:
            photo = session.get(ProductPhoto, photo_id)
            if photo is None:
                raise CatalogError(404, "Foto não encontrada.")
            key, size, digest, image_format = (
                photo.storage_key,
                photo.size,
                photo.sha256,
                photo.format,
            )
        return self.storage.read(key, size, digest), image_format
