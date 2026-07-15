import csv as csv_module

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.profiles.bulk_parser import parse_uploaded_file
from apps.profiles.bulk_processor import process_row
from apps.profiles.serializers_bulk import BulkUploadSerializer


class BulkUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = BulkUploadSerializer

    @extend_schema(request=BulkUploadSerializer, responses={200: dict})
    def post(self, request):
        portal = getattr(request, "portal_name", None)
        if portal != "admin":
            return Response(
                {"detail": "This action is only available on the admin portal."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data["file"]

        rows, parse_error = parse_uploaded_file(uploaded_file)
        if parse_error:
            return Response({"detail": parse_error}, status=status.HTTP_400_BAD_REQUEST)
        if not rows:
            return Response(
                {"detail": "The file is empty or contains no data rows."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.tenants.context import get_current_tenant

        tenant = get_current_tenant()
        db_alias = getattr(tenant, "db_alias", "default") if tenant else "default"

        results = []
        success_count = 0
        error_count = 0
        for index, row in enumerate(rows, start=2):
            result = process_row(row, row_number=index, db_alias=db_alias)
            results.append(result)
            if result["status"] == "success":
                success_count += 1
            else:
                error_count += 1

        return Response(
            {
                "total": len(rows),
                "success_count": success_count,
                "error_count": error_count,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class BulkUploadTemplateView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BulkUploadSerializer

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="bulk_upload_template.csv"'
        )
        writer = csv_module.writer(response)
        from apps.profiles.bulk_constants import ALL_COLUMNS

        writer.writerow(ALL_COLUMNS)
        return response
