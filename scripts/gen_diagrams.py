"""Generate project diagrams as PNG files (Pillow, no external tools needed).

Reads the live SQLAlchemy metadata so the ER diagram reflects the real app.
Outputs: docs/diagrams/system-architecture.png, er-diagram.png,
python-module-diagram.png
"""

from __future__ import annotations

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

from PIL import Image, ImageDraw  # noqa: E402

OUT = os.path.join(BACKEND_DIR, "..", "docs", "diagrams")
os.makedirs(OUT, exist_ok=True)

BG = (246, 247, 249)
INK = (31, 41, 55)
MUTED = (107, 114, 128)
BLUE = (29, 78, 216)
BOX = (255, 255, 255)
EDGE = (180, 186, 193)


def canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (w, h), BG)
    return img, ImageDraw.Draw(img)


def box(d: ImageDraw.ImageDraw, xy: tuple, title: str, lines: list[str]) -> None:
    x0, y0, x1, y1 = xy
    d.rectangle(xy, fill=BOX, outline=EDGE, width=2)
    d.rectangle((x0, y0, x1, y0 + 26), fill=BLUE)
    d.text((x0 + 8, y0 + 6), title, fill=(255, 255, 255))
    y = y0 + 32
    for line in lines:
        d.text((x0 + 8, y), line, fill=MUTED if line.startswith("(") else INK)
        y += 15


def arrow(d: ImageDraw.ImageDraw, a: tuple, b: tuple, label: str = "") -> None:
    d.line((a, b), fill=EDGE, width=2)
    x, y = b
    d.polygon([(x, y), (x - 8, y - 4), (x - 8, y + 4)], fill=EDGE)
    if label:
        d.text(((a[0] + b[0]) // 2 + 4, (a[1] + b[1]) // 2 - 18), label, fill=MUTED)


def architecture() -> None:
    img, d = canvas(1100, 560)
    d.text(
        (20, 12),
        "Retail Shift Scheduler — System Architecture (real deployment shape)",
        fill=INK,
    )
    box(
        d,
        (20, 50, 260, 220),
        "Browser SPA",
        [
            "React 18 + Vite + Bootstrap 5",
            "React Router + Axios",
            "VITE_API_BASE_URL -> /api",
        ],
    )
    box(
        d,
        (300, 50, 580, 220),
        "FastAPI backend",
        [
            "routers: app/api/v1/* (12)",
            "services: app/services/* (13)",
            "core: auth JWT + RBAC + limits",
            "Swagger UI at /docs",
        ],
    )
    box(
        d,
        (620, 50, 860, 220),
        "PostgreSQL 15",
        [
            "12 tables (11 + corrections)",
            "Alembic migrations",
            "managed instance in prod",
        ],
    )
    box(
        d,
        (900, 50, 1080, 220),
        "Mail server",
        ["smtplib, env credentials", "disabled -> in-app only"],
    )
    box(
        d,
        (20, 280, 260, 420),
        "Vercel / Netlify",
        ["vite build -> dist/", "SPA rewrite to index.html"],
    )
    box(
        d,
        (300, 280, 580, 420),
        "Render / Railway",
        ["uvicorn app.main:app", "alembic upgrade head"],
    )
    box(
        d,
        (620, 280, 1080, 420),
        "CI: GitHub Actions",
        ["backend.yml: ruff/black/pytest", "frontend.yml: eslint/build"],
    )
    arrow(d, (260, 135), (300, 135), "HTTPS JSON")
    arrow(d, (580, 135), (620, 135), "SQLAlchemy 2.x")
    arrow(d, (720, 220), (960, 220), "SMTP")
    img.save(os.path.join(OUT, "system-architecture.png"))


def er_diagram() -> None:
    from app.models import Base  # noqa: E402

    tables = sorted(Base.metadata.tables.items())
    img, d = canvas(1400, 900)
    d.text(
        (20, 12),
        "Retail Shift Scheduler — Entity-Relationship Diagram (from live SQLAlchemy metadata)",
        fill=INK,
    )
    cols, bw, bh, gx, gy = 4, 320, 200, 20, 50
    for i, (name, table) in enumerate(tables):
        r, c = divmod(i, cols)
        x0, y0 = gx + c * (bw + 15), gy + r * (bh + 12)
        d.rectangle((x0, y0, x0 + bw, y0 + bh), fill=BOX, outline=EDGE, width=2)
        d.rectangle((x0, y0, x0 + bw, y0 + 24), fill=BLUE)
        d.text((x0 + 8, y0 + 5), name, fill=(255, 255, 255))
        y = y0 + 30
        for col in list(table.columns)[:10]:
            marker = (
                "PK " if col.primary_key else ("FK " if col.foreign_keys else "   ")
            )
            d.text((x0 + 8, y), f"{marker}{col.name}: {col.type}", fill=INK)
            y += 14
        if len(list(table.columns)) > 10:
            d.text((x0 + 8, y), f"+ {len(list(table.columns)) - 10} more …", fill=MUTED)
    img.save(os.path.join(OUT, "er-diagram.png"))


def modules() -> None:
    img, d = canvas(1100, 620)
    d.text(
        (20, 12),
        "Retail Shift Scheduler — Python Module Diagram (backend/app)",
        fill=INK,
    )
    box(
        d,
        (400, 50, 700, 130),
        "app.main",
        ["FastAPI app, CORS, routers", "GET /  GET /api/health"],
    )
    box(
        d,
        (20, 180, 280, 400),
        "app.api.v1 (12 routers)",
        [
            "auth, stores, employees",
            "shifts, scheduling",
            "availability, attendance",
            "leave, swaps",
            "notifications, reports, health",
        ],
    )
    box(
        d,
        (320, 180, 600, 400),
        "app.services (13)",
        [
            "shift, assignment (10 rules)",
            "scheduling, auto_schedule",
            "attendance, availability",
            "leave, swap (atomic)",
            "notification, email, report",
            "employee, audit",
        ],
    )
    box(
        d,
        (640, 180, 880, 400),
        "app.models (12 tables)",
        [
            "user/store, employee",
            "shift/assignment",
            "attendance + corrections",
            "availability, requests",
            "swaps, notifications, audit",
        ],
    )
    box(
        d,
        (900, 180, 1080, 400),
        "app.core + db",
        ["config, security (JWT)", "deps (RBAC), errors", "rate_limit, session"],
    )
    box(
        d,
        (320, 450, 780, 560),
        "app.schemas + alembic + scripts",
        [
            "pydantic envelopes + validators",
            "versions/*_initial_schema.py",
            "seed.py, create_manager.py",
        ],
    )
    for x in (150, 460, 760, 990):
        arrow(d, (x, 130), (x, 180))
    arrow(d, (460, 400), (460, 450))
    img.save(os.path.join(OUT, "python-module-diagram.png"))


if __name__ == "__main__":
    architecture()
    er_diagram()
    modules()
    print("wrote", sorted(os.listdir(OUT)))
