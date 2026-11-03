from app.models.tenant.catalog import Discount, Plan, Room
from app.models.tenant.notification import Notification
from app.models.tenant.people import Student, Teacher, User
from app.models.tenant.schedule import Attendance, ClassGroup, Enrollment, Lesson
from app.models.tenant.subscription import Subscription

__all__ = [
    "Attendance",
    "ClassGroup",
    "Discount",
    "Enrollment",
    "Lesson",
    "Notification",
    "Plan",
    "Room",
    "Student",
    "Subscription",
    "Teacher",
    "User",
]
