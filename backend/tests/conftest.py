"""Pytest configuration: isolated test database, fixtures, API client."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:DevLocal#2024pg@localhost:5432/retail_scheduling_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-for-pytest-suite-1234567890")
os.environ.setdefault("ENVIRONMENT", "testing")

from datetime import date, time
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.db.session import Base
from app.main import app
from app.db.session import get_db
from app.models import Store, User
from app.models.enums import UserRole
from app.models.employee import Employee
from app.models.enums import EmployeeStatus, SkillLevel


TEST_URL = os.environ["DATABASE_URL"]

engine = create_engine(TEST_URL, future=True, pool_pre_ping=True)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _clean_tables(db: Session) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(text(f'TRUNCATE TABLE \"{table.name}\" CASCADE'))
    db.commit()


@pytest.fixture(scope="session", autouse=True)
def _setup_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    # keep schema for inspection


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    session = TestingSession()
    try:
        _clean_tables(session)
        yield session
        session.rollback()
    finally:
        session.close()


def _make_store(session: Session, code: str = "DEMO-001") -> Store:
    store = Store(name="Demo Store", code=code, address="1 Test St", phone="555-0100", timezone="UTC")
    session.add(store)
    session.flush()
    return store


def _make_user(session: Session, store_id: str, email: str, role: UserRole, name: str = "Test User") -> User:
    user = User(email=email, hashed_password=hash_password("Password123!"), full_name=name, role=role, store_id=store_id, is_active=True)
    session.add(user)
    session.flush()
    return user


def _make_employee(session: Session, user: User, number: str = "EMP-0001") -> Employee:
    emp = Employee(id=user.id, employee_number=number, store_id=user.store_id, skill_level=SkillLevel.MID, status=EmployeeStatus.ACTIVE, skills=["cashier"], contract_weekly_hours=40)
    session.add(emp)
    session.flush()
    return emp


@pytest.fixture()
def store(db: Session) -> Store:
    s = _make_store(db)
    db.commit()
    return s


@pytest.fixture()
def manager(db: Session, store: Store) -> User:
    u = _make_user(db, store.id, "manager@example.com", UserRole.MANAGER, "Mara Manager")
    db.commit()
    return u


@pytest.fixture()
def employee_user(db: Session, store: Store) -> User:
    u = _make_user(db, store.id, "alice@example.com", UserRole.EMPLOYEE, "Alice Staff")
    _make_employee(db, u, "EMP-0001")
    db.commit()
    return u


@pytest.fixture()
def employee2_user(db: Session, store: Store) -> User:
    u = _make_user(db, store.id, "bob@example.com", UserRole.EMPLOYEE, "Bob Staff")
    _make_employee(db, u, "EMP-0002")
    db.commit()
    return u


def _override_db(session: Session):
    def _gen():
        try:
            yield session
        finally:
            pass
    return _gen


@pytest.fixture()
def client(db: Session):
    app.dependency_overrides[get_db] = _override_db(db)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.core import rate_limit as rl
    rl.reset_limiter()
    yield
    rl.reset_limiter()


def auth_headers(client: TestClient, email: str, password: str = "Password123!") -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def manager_headers(client: TestClient, manager: User) -> dict:
    return auth_headers(client, "manager@example.com")


@pytest.fixture()
def employee_headers(client: TestClient, employee_user: User) -> dict:
    return auth_headers(client, "alice@example.com")


def make_shift_payload(day: str = None, publish: bool = True) -> dict:
    from datetime import date as _date, timedelta
    d = day or str(_date.today() + timedelta(days=1))
    return {
        "shift_date": d,
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "role_required": "cashier",
        "required_employees": 1,
        "notes": "test shift",
        "publish": publish,
    }
