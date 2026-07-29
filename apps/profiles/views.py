from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.choices import Role
from apps.profiles.models import (
    AdminProfile,
    BaseProfile,
    Document,
    FacultyProfile,
    StudentProfile,
)
from apps.profiles.permissions import IsOwnerOrAdmin
from apps.profiles.serializers import (
    AdminDocumentSerializer,
    AdminProfileSerializer,
    DocumentSerializer,
    FacultyProfileSerializer,
    StudentProfileSerializer,
)
from apps.storage.utils import delete_cloudinary_asset

User = get_user_model()


def get_user_role(user):
    role_names = set(user.groups.values_list("name", flat=True))
    for role in (Role.STUDENT, Role.FACULTY, Role.ADMIN):
        if role in role_names:
            return role
    return None


class MyProfileView(APIView):
    permission_classes = [IsAuthenticated, DjangoModelPermissions, IsOwnerOrAdmin]

    def get_queryset(self):
        role = get_user_role(self.request.user)
        if role == Role.STUDENT:
            return StudentProfile.objects.select_related(
                "base_profile__user", "section"
            ).filter(base_profile__user_id=self.request.user.id)
        elif role == Role.FACULTY:
            return FacultyProfile.objects.select_related(
                "base_profile__user", "department"
            ).filter(base_profile__user_id=self.request.user.id)
        elif role == Role.ADMIN:
            return AdminProfile.objects.select_related("base_profile__user").filter(
                base_profile__user_id=self.request.user.id
            )

    def get(self, request):
        role = get_user_role(request.user)

        if role is None:
            return Response(
                {"detail": "User has no role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role == Role.STUDENT:
            profile = StudentProfile.objects.select_related(
                "base_profile__user", "section"
            ).get(base_profile__user_id=request.user.id)
            serializer = StudentProfileSerializer(profile)

        elif role == Role.FACULTY:
            profile = FacultyProfile.objects.select_related(
                "base_profile__user", "department"
            ).get(base_profile__user_id=request.user.id)
            serializer = FacultyProfileSerializer(profile)

        elif role == Role.ADMIN:
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
    queryset = Document.objects.select_related("base_profile__user")
    serializer_class = DocumentSerializer

    def get(self, request):
        base_profile = BaseProfile.objects.get(user=request.user)
        documents = Document.objects.filter(base_profile=base_profile)
        serializer = self.serializer_class(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        base_profile = BaseProfile.objects.get(user=request.user)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(base_profile=base_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="doc_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Document ID to delete",
                required=True,
            )
        ]
    )
    def delete(self, request):
        base_profile = BaseProfile.objects.get(user=request.user)
        try:
            doc_id = request.query_params.get("doc_id")
            document = Document.objects.get(id=doc_id, base_profile=base_profile)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # delete from Cloudinary as well
        delete_cloudinary_asset(
            document.document_public_id, resource_type=document.resource_type
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
    queryset = Document.objects.select_related("base_profile__user")

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

        base_profile = BaseProfile.objects.get(user=user)
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

        base_profile = BaseProfile.objects.get(user=user)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(base_profile=base_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
