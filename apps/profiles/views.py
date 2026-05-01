from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.choices import Roles
from apps.profiles.models import (
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
)


def get_user_role(user):
    role_names = set(user.groups.values_list("name", flat=True))
    for role in (Roles.STUDENT, Roles.FACULTY, Roles.ADMIN):
        if role in role_names:
            return role
    return None


class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = get_user_role(request.user)

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

        else:
            return Response(
                {"detail": "User has no role."}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {"role": role, "profile": serializer.data}, status=status.HTTP_200_OK
        )


class StudentProfileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StudentProfileSerializer
    queryset = StudentProfile.objects.select_related("base_profile__user", "section")


class FacultyProfileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FacultyProfileSerializer
    queryset = FacultyProfile.objects.select_related("base_profile__user", "department")


class AdminProfileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AdminProfileSerializer
    queryset = AdminProfile.objects.select_related("base_profile__user")


# class FacultyProfileView(APIView):
#     permission_classes = [IsAuthenticated]
#     serializer_class = FacultyProfileSerializer

#     def get(self, request, faculty_id):
#         profile = FacultyProfile.objects.select_related(
#             "base_profile__user", "department"
#         ).get(id=faculty_id)
#         serializer = self.serializer_class(profile)
#         return Response(serializer.data, status=status.HTTP_200_OK)

#     def post(self, request):
#         serializer = self.serializer_class(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         faculty_profile = serializer.save()
#         return Response(
#             self.serializer_class(faculty_profile).data,
#             status=status.HTTP_201_CREATED,
#         )

#     def patch(self, request, profile_id):
#         profile = FacultyProfile.objects.select_related(
#             "base_profile__user", "department"
#         ).get(id=profile_id)
#         serializer = self.serializer_class(profile, data=request.data, partial=True)
#         serializer.is_valid(raise_exception=True)
#         updated_profile = serializer.save()
#         return Response(
#             self.serializer_class(updated_profile).data, status=status.HTTP_200_OK
#         )

#     def delete(self, request, profile_id):
#         profile = FacultyProfile.objects.get(id=profile_id)
#         user = profile.base_profile.user
#         user.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)


# class AdminProfileView(APIView):
#     permission_classes = [IsAuthenticated]
#     serializer_class = AdminProfileSerializer

#     def get(self, request, admin_id):
#         profile = AdminProfile.objects.select_related("base_profile__user").get(
#             id=admin_id
#         )
#         serializer = self.serializer_class(profile)
#         return Response(serializer.data, status=status.HTTP_200_OK)

#     def post(self, request):
#         serializer = self.serializer_class(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         admin_profile = serializer.save()
#         return Response(
#             self.serializer_class(admin_profile).data,
#             status=status.HTTP_201_CREATED,
#         )

#     def patch(self, request, profile_id):
#         profile = AdminProfile.objects.select_related("base_profile__user").get(
#             id=profile_id
#         )
#         serializer = self.serializer_class(profile, data=request.data, partial=True)
#         serializer.is_valid(raise_exception=True)
#         updated_profile = serializer.save()
#         return Response(
#             self.serializer_class(updated_profile).data, status=status.HTTP_200_OK
#         )

#     def delete(self, request, profile_id):
#         profile = AdminProfile.objects.get(id=profile_id)
#         user = profile.base_profile.user
#         user.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentSerializer
    queryset = Document.objects.select_related("base_profile__user").all()
