from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.profiles.models import (
    AdminProfile,
    BaseProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)
from apps.profiles.serializers import (
    AdminDocumentSerializer,
    AdminFacultyProfileSerializer,
    AdminProfileSerializer,
    AdminStudentProfileSerializer,
    DocumentSerializer,
    FacultyProfileSerializer,
    StudentProfileSerializer,
)

User = get_user_model()

# Role → (role profile model, user serializer, admin serializer)
ROLE_PROFILE_MAP = {
    "student": (
        StudentProfile,
        StudentProfileSerializer,
        AdminStudentProfileSerializer,
    ),
    "faculty": (
        FacultyProfile,
        FacultyProfileSerializer,
        AdminFacultyProfileSerializer,
    ),
    "admin": (AdminProfile, AdminProfileSerializer, AdminProfileSerializer),
}


def get_or_create_base_profile(user):
    """Always get or create BaseProfile first."""
    base_profile, _ = BaseProfile.objects.get_or_create(user=user)
    return base_profile


def get_or_create_role_profile(user, profile_model):
    """Get or create role specific profile linked to BaseProfile."""
    base_profile = get_or_create_base_profile(user)
    profile, _ = profile_model.objects.get_or_create(base_profile=base_profile)
    return profile


def get_user_role(user):
    roles = list(user.groups.values_list("name", flat=True))
    return roles[0] if roles else None


class MyProfileView(APIView):
    """
    GET /api/v1/profiles/me/  → get own profile
    PUT /api/v1/profiles/me/  → update own profile (limited fields)
    """

    permission_classes = [IsAuthenticated]

    def _check_portal_access(self, request):
        role = request.portal_name
        user_roles = list(request.user.groups.values_list("name", flat=True))
        return role in user_roles

    def get(self, request):
        if not self._check_portal_access(request):
            return Response(
                {"detail": "You do not have permission to access this portal."},
                status=status.HTTP_403_FORBIDDEN,
            )

        role = request.portal_name

        if role not in ROLE_PROFILE_MAP:
            return Response(
                {"detail": "No profile found for this role."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile_model, serializer_class, _ = ROLE_PROFILE_MAP[role]
        profile = get_or_create_role_profile(request.user, profile_model)
        serializer = serializer_class(profile)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        if not self._check_portal_access(request):
            return Response(
                {"detail": "You do not have permission to access this portal."},
                status=status.HTTP_403_FORBIDDEN,
            )

        role = request.portal_name

        if role not in ROLE_PROFILE_MAP:
            return Response(
                {"detail": "No profile found for this role."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile_model, serializer_class, _ = ROLE_PROFILE_MAP[role]
        profile = get_or_create_role_profile(request.user, profile_model)
        serializer = serializer_class(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


class UserProfileView(APIView):
    """
    Admin only.
    GET /api/v1/profiles/users/             → list all users with profiles
    GET /api/v1/profiles/users/<user_id>/   → get any user profile
    PUT /api/v1/profiles/users/<user_id>/   → edit any user profile (all fields)
    """

    permission_classes = [IsAuthenticated]

    def _is_admin(self, request):
        return request.portal_name == "admin"

    def get(self, request, user_id=None):
        if not self._is_admin(request):
            return Response(
                {"detail": "Only admins can access this."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # list all users
        if user_id is None:
            users = User.objects.all()
            data = []
            for user in users:
                role = get_user_role(user)
                if role not in ROLE_PROFILE_MAP:
                    continue
                profile_model, _, admin_serializer_class = ROLE_PROFILE_MAP[role]
                profile = get_or_create_role_profile(user, profile_model)
                serializer = admin_serializer_class(profile)
                data.append(serializer.data)
            return Response(data, status=status.HTTP_200_OK)

        # get single user profile
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        role = get_user_role(user)
        if role not in ROLE_PROFILE_MAP:
            return Response(
                {"detail": "No profile found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile_model, _, admin_serializer_class = ROLE_PROFILE_MAP[role]
        profile = get_or_create_role_profile(user, profile_model)
        serializer = admin_serializer_class(profile)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, user_id):
        if not self._is_admin(request):
            return Response(
                {"detail": "Only admins can access this."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        role = get_user_role(user)
        if role not in ROLE_PROFILE_MAP:
            return Response(
                {"detail": "No profile found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile_model, _, admin_serializer_class = ROLE_PROFILE_MAP[role]
        profile = get_or_create_role_profile(user, profile_model)
        serializer = admin_serializer_class(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentView(APIView):
    """
    GET  /api/v1/profiles/documents/          → list own documents
    POST /api/v1/profiles/documents/          → upload new document
    DELETE /api/v1/profiles/documents/<id>/   → delete own document
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        base_profile = get_or_create_base_profile(request.user)
        documents = Document.objects.filter(base_profile=base_profile)
        serializer = DocumentSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        base_profile = get_or_create_base_profile(request.user)
        serializer = DocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(base_profile=base_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, doc_id):
        base_profile = get_or_create_base_profile(request.user)
        try:
            document = Document.objects.get(id=doc_id, base_profile=base_profile)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        document.delete()
        return Response(
            {"detail": "Document deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminDocumentView(APIView):
    """
    Admin only.
    GET    /api/v1/profiles/documents/admin/<user_id>/        → list user documents
    POST   /api/v1/profiles/documents/admin/<user_id>/        → upload document for user
    PUT    /api/v1/profiles/documents/admin/<doc_id>/verify/  → verify document
    DELETE /api/v1/profiles/documents/admin/<doc_id>/         → delete any document
    """

    permission_classes = [IsAuthenticated]

    def _is_admin(self, request):
        return request.portal_name == "admin"

    def get(self, request, user_id):
        if not self._is_admin(request):
            return Response(
                {"detail": "Only admins can access this."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )

        base_profile = get_or_create_base_profile(user)
        documents = Document.objects.filter(base_profile=base_profile)
        serializer = AdminDocumentSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, user_id):
        if not self._is_admin(request):
            return Response(
                {"detail": "Only admins can access this."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )

        base_profile = get_or_create_base_profile(user)
        serializer = AdminDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(base_profile=base_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
