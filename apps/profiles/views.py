from rest_framework import status
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from django.contrib.auth import get_user_model
from apps.profiles.permissions import IsOwnerOrAdmin

from apps.accounts.choices import Roles
from apps.profiles.models import (
    BaseProfile,
    AdminProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)
from apps.profiles.serializers import (
    AdminProfileSerializer,
    DocumentSerializer,
    FacultyProfileSerializer,
    StudentProfileSerializer,
    AdminDocumentSerializer,
)
from apps.storage.utils import delete_cloudinary_asset

User = get_user_model()


def get_or_create_base_profile(user):
    base_profile, _ = BaseProfile.objects.get_or_create(user=user)
    return base_profile


def get_or_create_role_profile(user, profile_model):
    base_profile = get_or_create_base_profile(user)
    profile, _ = profile_model.objects.get_or_create(base_profile=base_profile)
    return profile


def get_user_role(user):
    role_names = set(user.groups.values_list("name", flat=True))
    for role in (Roles.STUDENT, Roles.FACULTY, Roles.ADMIN):
        if role in role_names:
            return role
    return None


class MyProfileView(APIView):
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]

    def get(self, request):
        role = get_user_role(request.user)

        if role is None:
            return Response(
                {"detail": "User has no role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role == Roles.STUDENT:
            profile = StudentProfile.objects.select_related(
                "base_profile__user", "section"
            ).get(base_profile__user_id=request.user.id)
            serializer = StudentProfileSerializer(profile)

        elif role == Roles.FACULTY:
            profile = FacultyProfile.objects.select_related(
                "base_profile__user", "department"
            ).get(base_profile__user_id=request.user.id)
            serializer = FacultyProfileSerializer(profile)

        elif role == Roles.ADMIN:
            profile = AdminProfile.objects.select_related("base_profile__user").get(
                base_profile__user_id=request.user.id
            )
            serializer = AdminProfileSerializer(profile)

        return Response(
            {"role": role, "profile": serializer.data},
            status=status.HTTP_200_OK,
        )


class StudentProfileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]
    serializer_class = StudentProfileSerializer
    queryset = StudentProfile.objects.select_related("base_profile__user", "section")


class FacultyProfileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]
    serializer_class = FacultyProfileSerializer
    queryset = FacultyProfile.objects.select_related("base_profile__user", "department")


class AdminProfileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]
    serializer_class = AdminProfileSerializer
    queryset = AdminProfile.objects.select_related("base_profile__user")


class DocumentView(APIView):
    """
    GET    /api/v1/profiles/documents/          → list own documents (with signed URLs)
    POST   /api/v1/profiles/documents/          → save document after Cloudinary upload
    DELETE /api/v1/profiles/documents/<doc_id>/ → delete own document
    """

    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]

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
                {"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # delete from Cloudinary as well
        delete_cloudinary_asset(
            document.public_id, resource_type=document.resource_type
        )
        document.delete()
        return Response(
            {"detail": "Document deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminDocumentView(APIView):
    """
    Admin only.
    GET  /api/v1/profiles/documents/admin/<user_id>/ → list user documents (with signed URLs)
    POST /api/v1/profiles/documents/admin/<user_id>/ → upload document for user
    """

    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]
    serializer_class = AdminDocumentSerializer

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
        serializer = self.serializer_class(documents, many=True)
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
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(base_profile=base_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
