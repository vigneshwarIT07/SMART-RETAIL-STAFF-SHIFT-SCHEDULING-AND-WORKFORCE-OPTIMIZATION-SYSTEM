"""ORM model package.

Importing this package registers every model on ``Base.metadata``, which is
what Alembic autogenerate and the test database setup rely on.
"""

from app.db.session import Base
from app.models.attendance import (
    Attendance,
    AttendanceCorrection,
    Availability,
)
from app.models.employee import Employee
from app.models.enums import (
    AssignmentStatus,
    AttendanceStatus,
    AuditAction,
    AvailabilityType,
    CoverageStatus,
    EmployeeStatus,
    LeaveStatus,
    LeaveType,
    NotificationType,
    ShiftStatus,
    SkillLevel,
    SwapStatus,
    UserRole,
)
from app.models.notification import AuditLog, Notification
from app.models.request import LeaveRequest, ShiftSwapRequest
from app.models.shift import Shift, ShiftAssignment
from app.models.user import Store, User

__all__ = [
    "AssignmentStatus",
    "Attendance",
    "AttendanceCorrection",
    "AttendanceStatus",
    "AuditAction",
    "AuditLog",
    "Availability",
    "AvailabilityType",
    "Base",
    "CoverageStatus",
    "Employee",
    "EmployeeStatus",
    "LeaveRequest",
    "LeaveStatus",
    "LeaveType",
    "Notification",
    "NotificationType",
    "Shift",
    "ShiftAssignment",
    "ShiftStatus",
    "SkillLevel",
    "Store",
    "SwapStatus",
    "User",
    "UserRole",
]