from rest_framework import serializers

class BulkUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="A .csv or .xlsx file containing user rows.")
    def validate_file(self, value):
        allowed = (".csv", ".xlsx", ".xls")
        if not value.name.lower().endswith(allowed):
            raise serializers.ValidationError(f"Unsupported file type. Allowed: {', '.join(allowed)}")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File size exceeds 5 MB limit.")
        return value
