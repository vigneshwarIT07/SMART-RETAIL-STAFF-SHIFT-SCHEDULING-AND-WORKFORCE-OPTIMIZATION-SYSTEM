"""Auth, RBAC, security envelope tests."""

from __future__ import annotations


def test_login_success_and_envelope(client, manager):
    resp = client.post("/api/auth/login", json={"email": "manager@example.com", "password": "Password123!"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "access_token" in body["data"]
    assert body["data"]["token_type"] == "bearer"


def test_login_wrong_password_401_envelope(client, manager):
    resp = client.post("/api/auth/login", json={"email": "manager@example.com", "password": "WrongPass1!"})
    assert resp.status_code == 401
    assert resp.json()["success"] is False


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


def test_me_returns_user(client, manager, manager_headers):
    resp = client.get("/api/auth/me", headers=manager_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["email"] == "manager@example.com"


def test_employee_cannot_create_manager(client, employee_user, employee_headers):
    resp = client.post("/api/auth/managers", headers=employee_headers, json={
        "email": "new@example.com", "full_name": "New", "password": "Password123!",
    })
    assert resp.status_code == 403


def test_change_password_flow(client, manager, manager_headers):
    resp = client.post("/api/auth/change-password", headers=manager_headers, json={
        "current_password": "Password123!", "new_password": "NewPassword123!",
    })
    assert resp.status_code == 200, resp.text
    # new password works
    resp2 = client.post("/api/auth/login", json={"email": "manager@example.com", "password": "NewPassword123!"})
    assert resp2.status_code == 200


def test_rate_limit_blocks_after_threshold(client, manager):
    from app.core import deps as _deps  # noqa - ensure importable
    from app.core import rate_limit as rl
    rl.reset_limiter()
    # 5 allowed attempts with wrong password (limit=5), 6th -> 429
    last = None
    for _ in range(7):
        last = client.post("/api/auth/login", json={"email": "manager@example.com", "password": "WrongPass1!"})
    assert last.status_code == 429
    rl.reset_limiter()
