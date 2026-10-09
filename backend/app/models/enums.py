"""Enumerations shared by the ORM models.

These are stored as native PostgreSQL enum types. Every enumeration derives
from ``str`` so that values serialise transparently to JSON and compare
directly with the string literals used in the frontend.
"""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    """Role held by a user account."""

    MANAGER = "manager"
    EMPLOYEE = "employee"


class EmployeeStatus(str, enum.Enum):
    """Employment status of an employee record."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_LEAVE = "on_leave"


class SkillLevel(str, enum.Enum):
    """Seniority attached to an employee."""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class ShiftStatus(str, enum.Enum):
    """Lifecycle state of a shift."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class CoverageStatus(str, enum.Enum):
    """Whether a shift has enough assigned staff."""

    FULLY_STAFFED = "fully_staffed"
    UNDERSTAFFED = "understaffed"
    UNASSIGNED = "unassigned"
    CANCELLED = "cancelled"


class AssignmentStatus(str, enum.Enum):
    """State of one employee-to-shift assignment."""

    ASSIGNED = "assigned"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class AvailabilityType(str, enum.Enum):
    """Direction of an availability window."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class AttendanceStatus(str, enum.Enum):
    """Outcome of one attendance record."""

    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    INCOMPLETE = "incomplete"
    EXCUSED = "excused"


class LeaveStatus(str, enum.Enum):
    """State of a leave request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveType(str, enum.Enum):
    """Category of leave."""

    ANNUAL = "annual"
    SICK = "sick"
    UNPAID = "unpaid"
    OTHER = "other"


class SwapStatus(str, enum.Enum):
    """State of a shift swap request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class NotificationType(str, enum.Enum):
    """Category of an in-app notification."""

    ASSIGNMENT = "assignment"
    SCHEDULE_PUBLISHED = "schedule_published"
    LEAVE_REQUEST = "leave_request"
    LEAVE_DECISION = "leave_decision"
    SWAP_REQUEST = "swap_request"
    SWAP_DECISION = "swap_decision"
    ATTENDANCE = "attendance"
    GENERAL = "general"


class AuditAction(str, enum.Enum):
    """Kind of change recorded in the audit log."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    ASSIGNMENT = "assignment"
    UNASSIGNMENT = "unassignment"
    APPROVAL = "approval"
    REJECTION = "rejection"
    CORRECTION = "correction"
    PUBLISH = "publish"
