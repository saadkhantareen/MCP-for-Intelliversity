from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, Permission
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import User


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("name",)


# class RegisterSerializer(serializers.ModelSerializer):
#     """Used for registering a new user."""

#     roles = serializers.SlugRelatedField(
#         many=True,
#         slug_field="name",
#         queryset=Group.objects.all(),
#         write_only=True,
#     )

#     role = serializers.SerializerMethodField()

#     class Meta:
#         model = User
#         fields = [
#             "id",
#             "email",
#             "first_name",
#             "last_name",
#             "password",
#             "roles",
#             "role",
#         ]
#         extra_kwargs = {"password": {"write_only": True}}

#     def get_role(self, obj):
#         return [group.name for group in obj.groups.all()]

#     def create(self, validated_data):
#         groups = validated_data.pop("groups", [])
#         password = validated_data.pop("password")
#         roles = validated_data.pop("roles", [])
#         user = User.objects.create_user(password=password, **validated_data)
#         user.groups.set(groups)
#         return user

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         # Return roles as list of strings in the response
#         representation["roles"] = list(instance.groups.values_list("name", flat=True))
#         return representation


class RegisterSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=["student", "teacher", "admin"]),
        write_only=True,
    )
    groups = GroupSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "password",
            "roles",
            "groups",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        roles = validated_data.pop("roles", [])
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        user.groups.set(Group.objects.filter(name__in=roles))
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")

        refresh = RefreshToken.for_user(user)
        return {
            "user": {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            "university": request.tenant.name,
        }
