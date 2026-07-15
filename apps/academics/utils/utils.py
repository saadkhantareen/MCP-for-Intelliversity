from apps.academics.models import CoursePrerequisite


def set_prerequisites(self, course, prerequisites):
    # Existing prerequisite IDs in DB
    existing_ids = set(
        CoursePrerequisite.objects.filter(course=course).values_list(
            "prerequisite_course_id", flat=True
        )
    )

    # Incoming prerequisite IDs from frontend
    new_ids = set([p.id for p in prerequisites])

    # Compute differences
    to_add_ids = new_ids - existing_ids
    to_remove_ids = existing_ids - new_ids

    # Delete only removed
    if to_remove_ids:
        CoursePrerequisite.objects.filter(
            course=course, prerequisite_course_id__in=to_remove_ids
        ).delete()

    # Add only new
    if to_add_ids:
        CoursePrerequisite.objects.bulk_create(
            [
                CoursePrerequisite(course=course, prerequisite_course_id=pid)
                for pid in to_add_ids
            ]
        )
