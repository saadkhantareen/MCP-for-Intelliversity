import logging
import os
import re

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .llm_parser import extract_course_section, parse
from .tools import admin_tools, attendance_tools, marks_tools, query_tools
from .utils.ocr import ocr_image_to_text, parse_ocr_to_attendance, parse_ocr_to_marks

logger = logging.getLogger(__name__)

TOOL_MAP = {
    "mark_bulk_attendance": attendance_tools.mark_bulk_attendance,
    "add_marks_bulk": marks_tools.add_marks_bulk,
    "create_departments_bulk": admin_tools.create_departments_bulk,
    "bulk_create_students": admin_tools.bulk_create_students,
    "get_attendance_report": query_tools.get_attendance_report,
    "get_defaulters": query_tools.get_defaulters,
    "get_my_classes_count": query_tools.get_my_classes_count,
    "get_marks_report": query_tools.get_marks_report,
    "get_departments": query_tools.get_departments,
    "get_faculty_by_department": query_tools.get_faculty_by_department,
    "get_curriculum": query_tools.get_curriculum,
    "get_section_students": query_tools.get_section_students,
    "get_offerings": query_tools.get_offerings,
}


class HealthView(APIView):
    permission_classes = []

    def get(self, request):
        return Response({"status": "mcp ok", "tenant": str(getattr(request, "university", None))})


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        image = request.FILES.get("image")
        message = request.data.get("message", "") or ""
        context = request.data.get("context", "") or ""

        if image:
            image_bytes = image.read()
            is_marks = any(x in message.lower() for x in ["quiz", "mid", "final", "assignment", "marks", "out of"])
            course_code, section = extract_course_section(message)
            if not course_code or not section:
                return Response(
                    {"reply": "Photo received. Add caption: 'PF Section A attendance today' or 'PF Section B Quiz 2 out of 10'"},
                    status=400,
                )
            if is_marks:
                total = re.search(r"out of (\d+)", message.lower())
                total_marks = int(total.group(1)) if total else 10
                seq = re.search(r"quiz\s*(\d+)|mid\s*(\d+)", message.lower())
                seq_no = 1
                if seq:
                    for group in seq.groups():
                        if group:
                            seq_no = int(group)
                            break
                type_code = "QUIZ" if "quiz" in message.lower() else "MID" if "mid" in message.lower() else "FINAL" if "final" in message.lower() else "QUIZ"
                ocr_text = ocr_image_to_text(image_bytes, sheet_type="marks")
                rows = parse_ocr_to_marks(ocr_text)
                if not rows:
                    return Response({"reply": f"Could not read marks. OCR: {ocr_text[:300]}", "ocr_text": ocr_text}, status=400)
                result = marks_tools.add_marks_from_ocr_rows(request.user, course_code, section, type_code, seq_no, total_marks, rows)
                return Response({"reply": result["message"], "ocr_text": ocr_text, "result": result})

            ocr_text = ocr_image_to_text(image_bytes, sheet_type="attendance")
            absent, _raw = parse_ocr_to_attendance(ocr_text)
            result = attendance_tools.mark_bulk_attendance(request.user, course_code, section, "today", "PRESENT", absent)
            return Response({"reply": result["message"] + f" [OCR {len(absent)} absents]", "ocr_text": ocr_text, "result": result})

        if not message:
            return Response({"error": "message or image required"}, status=400)

        parsed = parse(message, context=context)
        logger.info(
            "MCP parse: msg=%r experiential_key_present=%s parsed=%s",
            message[:60],
            bool(os.getenv("EXPERIENTIAL_API_KEY")),
            parsed,
        )
        tool = parsed.get("tool")
        args = parsed.get("args", {})
        if tool not in TOOL_MAP:
            return Response(
                {
                    "reply": "Try: 'PF Section A mark today's attendance as ALL present' or 'Only Ahmad Raza absent rest present' or 'PF Section A attendance report today' or 'students below 60% in PF Section A' or 'bring CS department teachers',",
                    "parsed": parsed,
                }
            )

        try:
            cleaned = {key: value for key, value in args.items() if value is not None}
            result = TOOL_MAP[tool](user=request.user, **cleaned)
            if tool.startswith("get_"):
                return Response({"reply": result["message"], "tool": tool, "data": result.get("data", []), "result": result})
            return Response({"reply": result["message"], "tool": tool, "result": result})
        except Exception as exc:
            return Response({"reply": f"Error: {exc}", "tool": tool}, status=400)
