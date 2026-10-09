"""Business-logic services.

Every rule that decides whether data may change lives here, never in the
route handlers. Routers parse HTTP, services decide. Services flush their
changes but never commit: the ``get_db`` dependency commits once the whole
request succeeds, which keeps multi-step operations (for example swap
approval) atomic.
"""

from __future__ import annotations
