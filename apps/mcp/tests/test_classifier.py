"""Tests for apps.mcp.classifier: greetings must never reach the tool parser.

Run with: pytest apps/mcp/tests/test_classifier.py
"""

import os
import sys

if __package__ in (None, ""):
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from apps.mcp.classifier import classify_message


def test_greetings_are_friendly():
    assert classify_message("hi") == "greeting"
    assert classify_message("Hi!") == "greeting"
    assert classify_message("hello") == "greeting"
    assert classify_message("hey") == "greeting"
    assert classify_message("salam") == "greeting"
    assert classify_message("aoa") == "greeting"
    assert classify_message("assalam o alaikum") == "greeting"
    assert classify_message("good morning") == "greeting"
    assert classify_message("good morning sir") == "greeting"
    assert classify_message("hi, how are you") == "greeting"
    assert classify_message("how are you doing today") == "greeting"
    assert classify_message("who are you") == "greeting"
    assert classify_message("what can you do") == "greeting"
    assert classify_message("tell me about yourself") == "greeting"


def test_thanks_and_farewell():
    assert classify_message("thanks") == "thanks"
    assert classify_message("thank you so much") == "thanks"
    assert classify_message("shukriya") == "thanks"
    assert classify_message("bye") == "farewell"
    assert classify_message("goodbye") == "farewell"
    assert classify_message("allah hafiz") == "farewell"


def test_greeting_plus_work_is_functional():
    assert classify_message("hi, mark CSC103 attendance") == "functional"
    assert classify_message("hello sir, students below 60% in CSC103") == "functional"
    assert classify_message("good morning, what is my cgpa forecast") == "functional"
    assert classify_message("hi, my classes") == "functional"


def test_plain_work_is_functional():
    assert classify_message("mark my today class all present except bilal and ayesha for PF class section A") == "functional"
    assert classify_message("students below 60% in CSC103") == "functional"
    assert classify_message("quiz marks for CSC103") == "functional"
    assert classify_message("my cgpa forecast") == "functional"
    assert classify_message("what is the attendance report") == "functional"
