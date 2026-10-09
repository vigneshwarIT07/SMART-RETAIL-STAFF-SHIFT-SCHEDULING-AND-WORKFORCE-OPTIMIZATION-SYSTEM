"""User accounts and the single store record.

``users`` holds credentials and the role. Every operational record belongs to
a ``store``; a manager is bound to exactly one store through
``users.store_id``, and every query in the application is filtered by it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import UserRole

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.employee import Employee


def _uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class Store(Base):
    """A retail location that employees and shifts belong to."""

    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )
    employees: Mapped[list["Employee"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Store {self.code} {self.name!r}>"


class User(Base):
    """An account that can authenticate against the API.

    A user with ``role=employee`` is always paired with exactly one row in
    ``employees`` sharing the same primary key, which is what lets the server
    derive the acting employee from the token rather than trusting a value
    supplied by the browser.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_store_role", "store_id", "role"),
        Index("ix_users_email_unique", "email", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, length=20),
        nullable=False,
        default=UserRole.EMPLOYEE,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    store_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store: Mapped[Store] = relationship(back_populates="users")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    employee: Mapped["Employee | None"] = relationship(
        back_populates="user",
        primaryjoin="User.id == foreign(Employee.id)",
        uselist=False,
        viewonly=True,
    )

    @property
    def is_manager(self) -> bool:
        """True when this account holds the manager role."""
        return self.role == UserRole.MANAGER

    def touch_login(self) -> "User":
        """Record the current time as the last successful login."""
        self.last_login_at = datetime.now(timezone.utc)
        return self

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} role={self.role.value}>"