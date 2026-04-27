from rest_framework import serializers


def validate_prerequisites(self, attrs):
    prereqs = attrs.get("prerequisites")
    if not prereqs:
        return attrs

    # Use the instance if it exists (Update),otherwise look at incoming attrs (Create)
    # This handles cases where 'code' might not bein the request body
    current_instance = self.instance
    incoming_code = attrs.get("code")
    for p in prereqs:
        # Check against instance (for Updates)
        if current_instance and p.pk == current_instance.pk:
            raise serializers.ValidationError(
                {"prerequisites": "A course cannotbe its own prerequisite."}
            )

        # Check against incoming code (for Creationor if code is being changed)
        if incoming_code and p.code == incoming_code:
            raise serializers.ValidationError(
                {"prerequisites": "A course cannotbe its own prerequisite."}
            )
    return attrs
