from django.db import models


# -----------------------------------------------------------------------
# 1. What kind of class? (used by ClassSession)
# -----------------------------------------------------------------------
class SessionType(models.TextChoices):
    LECTURE = "lecture", "Lecture"
    LAB = "lab", "Lab"
    TUTORIAL = "tutorial", "Tutorial"
    SEMINAR = "seminar", "Seminar"


# -----------------------------------------------------------------------
# 2. Did the class happen? (used by ClassSession)
# BR5: only HELD sessions go into the denominator.
# -----------------------------------------------------------------------
class SessionStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"  # not taught yet -> not counted
    HELD = "held", "Held"  # taught -> COUNTED
    CANCELLED = "cancelled", "Cancelled"  # holiday/absence -> not counted

    @classmethod
    def countable(cls):
        """Statuses included in attendance denominators. BR5"""
        return [cls.HELD]


# -----------------------------------------------------------------------
# 3. How was the class delivered? (used by ClassSession)
# -----------------------------------------------------------------------
class DeliveryMode(models.TextChoices):
    ONSITE = "onsite", "On-site"
    ONLINE = "online", "Online"
    HYBRID = "hybrid", "Hybrid"


# -----------------------------------------------------------------------
# 4. One student's status in one session (used by AttendanceRecord)
# ONLY THREE VALUES. LEAVE is present-equivalent by design (BR6).
# -----------------------------------------------------------------------
class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LEAVE = "leave", "Leave"  # counted as present, but reported separately

    @classmethod
    def present_equivalent(cls):
        """Statuses that count in the NUMERATOR. BR6/BR9"""
        return [cls.PRESENT, cls.LEAVE]
