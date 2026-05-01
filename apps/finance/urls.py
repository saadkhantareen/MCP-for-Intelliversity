from django.urls import path

from apps.finance.views import StudentFeeInvoiceHtmlView, StudentFeeInvoicePdfView

urlpatterns = [
    path(
        "my-invoice/pdf/",
        StudentFeeInvoicePdfView.as_view(),
        name="student-fee-invoice-pdf",
    ),
    path(
        "my-invoice/html/",
        StudentFeeInvoiceHtmlView.as_view(),
        name="student-fee-invoice-html",
    ),
]
