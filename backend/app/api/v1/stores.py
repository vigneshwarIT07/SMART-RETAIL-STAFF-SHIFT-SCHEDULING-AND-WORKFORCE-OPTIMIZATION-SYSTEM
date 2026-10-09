"""Store routes: current store profile and manager-level store updates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_store, get_current_user, require_manager
from app.core.errors import success
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.models.enums import AuditAction
from app.models.user import Store, User
from app.schemas.store import StoreResponse, StoreUpdate
from app.services import audit_service

router = APIRouter(prefix="/stores", tags=["stores"])


def _payload(store: Store) -> dict:
    return StoreResponse.model_validate(store).model_dump(mode="json")


@router.get("/me")
def read_own_store(store: Store = Depends(get_current_store)) -> dict:
    """Return the store the caller is attached to."""
    return success(data=_payload(store), message="Store profile")


@router.patch("/me")
def update_own_store(
    payload: StoreUpdate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Update the manager's own store (name, contact details, timezone)."""
    store = db.get(Store, manager.store_id)
    if store is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Store not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(store, key, value)
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="store",
        entity_id=store.id,
        user_id=manager.id,
        store_id=store.id,
        ip_address=client_ip(request),
    )
    return success(data=_payload(store), message="Store updated")


@router.get("/{store_id}")
def read_store(
    store_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return a store by id (callers may only see their own store)."""
    from app.core.deps import enforce_store_scope

    enforce_store_scope(store_id, current_user)
    store = db.get(Store, store_id)
    if store is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Store not found")
    return success(data=_payload(store), message="Store profile")
