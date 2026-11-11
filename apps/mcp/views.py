import logging
import os
import re

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .classifier import classify_message
from .llm_parser import extract_course_section, parse
from .roles import is_tool_allowed, role_refusal
from .suggestions import get_suggestions
from .tools import admin_tools, attendance_tools, marks_tools, query_tools
from .utils.ocr import ocr_image_to_text, parse_ocr_to_attendance, parse_ocr_to_marks
from .utils.resolver import AmbiguousCourseError

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
    "get_my_cgpa_forecast": query_tools.get_my_cgpa_forecast,
}


def _clarify_response(args, suggestions):
    """'Did you mean ...?' reply with tappable options for the frontend."""
    options = args.get("options") or []
    names = ", ".join(f"{option['name']} ({option['code']})" for option in options)
    reply = f"Did you mean {names}?" if names else "Which course did you mean?"
    return Response(
        {
            "reply": reply,
            "clarify": {
                "options": options,
                "matched_text": args.get("matched_text", ""),
                "section": args.get("section"),
                "message": args.get("message", ""),
            },
            "suggestions": suggestions,
        }
    )


def _assistant_short_name(request):
    """'FAST University' -> 'FAST', for the greeting reply."""
    uni = getattr(request, "university", None)
    name = (getattr(uni, "name", "") or "").strip()
    short = re.sub(r"\s+university\s*$", "", name, flags=re.I).strip()
    return short or "Intelliversity"


def _friendly_reply(kind, request):
    """Small-talk answer: a greeting never reaches the tool parser."""
    name = _assistant_short_name(request)
    if kind == "thanks":
        return "You're welcome! Anything else I can help with?"
    if kind == "farewell":
        return "Goodbye! Come back any time you need attendance, marks or reports."
    return (
        f"Hi! I am {name} AI Assistant. How can I help you?\n"
        "I can mark attendance, check marks, show CGPA forecasts and pull reports, "
        "just tell me what you need."
    )


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
            suggestions = get_suggestions(request.user)
            # Photo uploads always write attendance or marks: faculty/admin only.
            if not (request.user.is_faculty or request.user.is_admin):
                return Response(
                    {"reply": "That needs a faculty or admin account.", "suggestions": suggestions},
                    status=403,
                )
            image_bytes = image.read()
            is_marks = any(x in message.lower() for x in ["quiz", "mid", "final", "assignment", "marks", "out of"])
            course_code, section = extract_course_section(message)
            if not course_code or not section:
                return Response(
                    {"reply": "Photo received. Add caption: 'PF Section A attendance today' or 'PF Section B Quiz 2 out of 10'", "suggestions": suggestions},
                    status=400,
                )
            try:
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
                        return Response({"reply": f"Could not read marks. OCR: {ocr_text[:300]}", "ocr_text": ocr_text, "suggestions": suggestions}, status=400)
                    result = marks_tools.add_marks_from_ocr_rows(request.user, course_code, section, type_code, seq_no, total_marks, rows)
                    return Response({"reply": result["message"], "ocr_text": ocr_text, "result": result, "suggestions": suggestions})

                ocr_text = ocr_image_to_text(image_bytes, sheet_type="attendance")
                absent, _raw = parse_ocr_to_attendance(ocr_text)
                result = attendance_tools.mark_bulk_attendance(request.user, course_code, section, "today", "PRESENT", absent)
                return Response({"reply": result["message"] + f" [OCR {len(absent)} absents]", "ocr_text": ocr_text, "result": result, "suggestions": suggestions})
            except PermissionError as exc:
                return Response({"reply": str(exc), "suggestions": suggestions}, status=403)
            except AmbiguousCourseError as exc:
                return _clarify_response(
                    {"options": exc.options, "matched_text": exc.query, "section": section, "message": message},
                    suggestions,
                )
            except ValueError as exc:
                return Response({"reply": str(exc), "suggestions": suggestions}, status=400)
            except Exception:
                logger.exception("MCP image chat failed")
                return Response(
                    {"reply": "Sorry, something went wrong on my side. Please try again.", "suggestions": suggestions},
                    status=400,
                )

        if not message:
            return Response({"error": "message or image required"}, status=400)

        suggestions = get_suggestions(request.user)

        # Greetings and small talk never reach the tool parser: "hi" used to
        # come back as a class list. Answer as the assistant instead.
        kind = classify_message(message)
        if kind != "functional":
            return Response({"reply": _friendly_reply(kind, request), "suggestions": suggestions})

        try:
            parsed = parse(message, context=context)
        except Exception:
            logger.exception("MCP parse failed")
            return Response(
                {"reply": "Sorry, I couldn't understand that. Please try again.", "suggestions": suggestions},
                status=400,
            )
        logger.info(
            "MCP parse: msg=%r experiential_key_present=%s parsed=%s",
            message[:60],
            bool(os.getenv("EXPERIENTIAL_API_KEY")),
            parsed,
        )
        tool = parsed.get("tool")
        args = parsed.get("args", {})

        if tool == "clarify":
            return _clarify_response(args, suggestions)

        if tool not in TOOL_MAP:
            examples = " or ".join(f"'{prompt}'" for prompt in suggestions[:3])
            reply = f"I didn't understand that. Try: {examples}." if examples else "I didn't understand that."
            return Response(
                {
                    "reply": reply,
                    "parsed": parsed,
                    "suggestions": suggestions,
                }
            )

        # Role gate: enforced in code, before the tool is called.
        if not is_tool_allowed(tool, request.user):
            return Response(
                {"reply": role_refusal(tool, request.user), "tool": tool, "suggestions": suggestions},
                status=403,
            )

        try:
            cleaned = {key: value for key, value in args.items() if value is not None}
            result = TOOL_MAP[tool](user=request.user, **cleaned)
            if tool.startswith("get_"):
                return Response({"reply": result["message"], "tool": tool, "data": result.get("data", []), "result": result, "suggestions": suggestions})
            return Response({"reply": result["message"], "tool": tool, "result": result, "suggestions": suggestions})
        except PermissionError as exc:
            return Response({"reply": str(exc), "tool": tool, "suggestions": suggestions}, status=403)
        except AmbiguousCourseError as exc:
            return _clarify_response(
                {"options": exc.options, "matched_text": exc.query, "section": args.get("section"), "message": message},
                suggestions,
            )
        except ValueError as exc:
            # Tool guidance ("Which section ...?") is written for the user.
            return Response({"reply": str(exc), "tool": tool, "suggestions": suggestions}, status=400)
        except Exception:
            logger.exception("MCP tool failed tool=%s args=%s", tool, args)
            return Response(
                {
                    "reply": "Sorry, something went wrong on my side. Please try again, or do it from the relevant page.",
                    "tool": tool,
                    "suggestions": suggestions,
                },
                status=400,
            )
