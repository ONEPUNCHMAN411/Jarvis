
import re

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

_ICONS = {
    "pass": "[PASS]", "fail": "[FAIL]", "skip": "[SKIP]",
    "blocked": "[BLOCKED]", "pending": "[ -- ]",
}


def _parse_steps(steps) -> list:
    if isinstance(steps, list):
        return [str(s).strip() for s in steps if str(s).strip()]
    out = []
    for line in str(steps or "").splitlines():
        line = re.sub(r"^\s*(\d+[\.\)]|[-*•])\s*", "", line.strip())
        if line:
            out.append(line)
    return out


class AppTesterPlugin(Plugin):
    """Drive a manual/UI test pass: take a list of buttons or features to test,
    exercise each one with the screen-control tools, and produce a pass/fail
    report. The plugin holds the plan + results; YOU perform each step."""

    def __init__(self):
        super().__init__("app_tester")

    def _get(self):
        from jarvis.brain.test_runner import get_test_runner
        return get_test_runner()

    async def initialize(self) -> None:
        logger.info("AppTesterPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="start_app_test",
                    description=(
                        "Begin a test pass over an app's buttons/features. Pass the "
                        "list of things to test (the user gives it in chat, or put it "
                        "in 'steps'). After starting, go through EACH step yourself: "
                        "use take_screenshot, find_ui_element, click_element, "
                        "describe_screen, and the app's own tools to actually exercise "
                        "the button/feature, then call record_test_result for each "
                        "with pass/fail and what you observed. Finish with "
                        "get_test_report. Use when the user says 'test every button', "
                        "'go through the app and check each feature', 'QA this'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "steps": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of buttons/features/steps to test",
                            },
                            "steps_text": {
                                "type": "string",
                                "description": "Alternatively, a newline or numbered list as one string",
                            },
                            "name": {"type": "string", "description": "Name for this test run"},
                        },
                    },
                ),
                self.start_app_test,
            ),
            (
                ToolDefinition(
                    name="record_test_result",
                    description=(
                        "Record the outcome of one test step. status is pass, fail, "
                        "skip, or blocked. step is the step number or part of its "
                        "description; notes is what you observed."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "step": {"type": "string", "description": "Step number or description"},
                            "status": {"type": "string", "description": "pass | fail | skip | blocked"},
                            "notes": {"type": "string", "description": "What happened / why"},
                        },
                        "required": ["step", "status"],
                    },
                ),
                self.record_test_result,
            ),
            (
                ToolDefinition(
                    name="get_test_report",
                    description="Compile and return the pass/fail report for the current test run.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.get_test_report,
            ),
            (
                ToolDefinition(
                    name="clear_app_test",
                    description="Clear the current test run.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.clear_app_test,
            ),
        ]

    async def start_app_test(self, steps=None, steps_text="", name="") -> str:
        parsed = _parse_steps(steps if steps else steps_text)
        if not parsed:
            return "No test steps provided. Give a list of buttons/features to test."
        res = self._get().start(name, parsed)
        lines = [f"Started test run '{res['name']}' with {res['count']} step(s):"]
        for i, s in enumerate(parsed, 1):
            lines.append(f"  {i}. {s}")
        lines.append("")
        lines.append("Now exercise each step with your screen-control tools, then "
                     "call record_test_result per step, and finish with get_test_report.")
        return "\n".join(lines)

    async def record_test_result(self, step, status, notes="") -> str:
        res = self._get().record(step, status, notes)
        return f"Recorded: {_ICONS.get(res['status'], '[?]')} {res['desc']}"

    async def get_test_report(self, **_) -> str:
        rep = self._get().report()
        if not rep["steps"]:
            return "No test run in progress. Use start_app_test first."
        c = rep["counts"]
        lines = [
            f"Test report — {rep['name']}",
            (f"  PASS {c.get('pass', 0)}  ·  FAIL {c.get('fail', 0)}  ·  "
             f"SKIP {c.get('skip', 0)}  ·  BLOCKED {c.get('blocked', 0)}  ·  "
             f"PENDING {c.get('pending', 0)}"),
            "",
        ]
        for i, s in enumerate(rep["steps"], 1):
            lines.append(f"  {i}. {_ICONS.get(s['status'], '[?]')} {s['desc']}")
            if s["note"]:
                lines.append(f"        ↳ {s['note']}")
        return "\n".join(lines)

    async def clear_app_test(self, **_) -> str:
        self._get().clear()
        return "Test run cleared."
