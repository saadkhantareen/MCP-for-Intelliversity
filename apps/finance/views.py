from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from weasyprint import HTML

from apps.academics.models import StudentTermRecord
from apps.finance.models import StudentFeeInvoice


class StudentFeeInvoicePdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student_id = request.user.profile.student_profile.id
        invoice = StudentFeeInvoice.objects.select_related(
            "student", "student_term_record"
        ).get(student_id=student_id)

        html = render_to_string(
            "finance/student_fee_invoice.html",
            {"invoice": invoice},
        )

        pdf_bytes = HTML(
            string=html, base_url=request.build_absolute_uri("/")
        ).write_pdf()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="invoice-{invoice.id}.pdf"'
        return response


class StudentFeeInvoiceHtmlView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, invoice_id):
        student_id = request.user.profile.student_profile.id
        current_term_record_id = (
            StudentTermRecord.objects.filter(
                student_id=student_id, term__is_active=True
            )
            .values_list("id", flat=True)
            .first()
        )

        invoice = StudentFeeInvoice.objects.select_related(
            "student", "student_term_record"
        ).get(student_id=student_id, student_term_record_id=current_term_record_id)

        return render(
            request, "templates/finance/student_fee_invoice.html", {"invoice": invoice}
        )
