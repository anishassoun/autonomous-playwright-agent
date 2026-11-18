"""Autonomous Spec-to-Playwright Agent Orchestrator with Self-Healing Loop & AST Assertion Guard."""

from typing import Any, Optional

from agent.assertion_guard import extract_assertions, validate_test_assertions
from agent.code_generator import generate_playwright_test
from tools.dom_inspector import inspect_dom_json
from tools.test_runner import run_playwright_test


def _clean_pytest_traceback(raw_output: str) -> str:
    """Strip pytest warning noise and keep the concise failure traceback."""
    lines = []
    for line in raw_output.splitlines():
        if "warnings summary ===" in line:
            break
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    return cleaned[-1200:] if len(cleaned) > 1200 else cleaned


def run_agent(
    url: str,
    user_story: str,
    output_file: str = "generated_tests/test_saucedemo_login.py",
    max_retries: int = 3,
    initial_code_seed: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute the Spec-to-Playwright workflow:
    1. Inspect live DOM elements on `url`.
    2. Generate a Playwright POM test for `user_story` (or use `initial_code_seed` on Attempt 1).
    3. Validate the generated code with the AST Assertion Guard (`validate_test_assertions`).
    4. Execute the generated test with `pytest`.
    5. Self-heal by feeding `pytest` tracebacks (or AST guard violations) back to the LLM
       up to `max_retries` times without weakening the baseline assertion.
    """
    print("=" * 70)
    print("🚀 Starting Autonomous Spec-to-Playwright Agent")
    print(f"🔗 Target URL : {url}")
    print(f"📋 User Story : {user_story}")
    print(f"💾 Output File: {output_file}")
    print("=" * 70)

    print("\n[1/4] Inspecting DOM for interactive elements...")
    dom_json = inspect_dom_json(url)
    print("      DOM snapshot captured successfully.")

    error_feedback: Optional[str] = None
    baseline_assertions: Optional[list[dict[str, Any]]] = None
    last_result: dict[str, Any] = {}
    last_guard: dict[str, Any] = {}
    attempt_logs: list[dict[str, Any]] = []

    for attempt in range(1, max_retries + 1):
        print(
            f"\n[2/4] Generating Playwright POM test (Attempt {attempt}/{max_retries})..."
        )
        if attempt == 1 and initial_code_seed is not None:
            test_code = initial_code_seed
        else:
            test_code = generate_playwright_test(
                url=url,
                user_story=user_story,
                dom_json=dom_json,
                error_feedback=error_feedback,
            )

        # Static AST Assertion Guard check
        last_guard = validate_test_assertions(
            code=test_code,
            baseline_assertions=baseline_assertions if attempt > 1 else None,
        )
        if attempt == 1 and last_guard["valid"] and not baseline_assertions:
            baseline_assertions = extract_assertions(test_code)

        if not last_guard["valid"]:
            print(f"      [AST GUARD BLOCKED] {last_guard['reason']}")
            last_result = {
                "passed": False,
                "exit_code": -2,
                "stdout": "",
                "stderr": f"AST Assertion Guard Violation: {last_guard['reason']}",
                "file_path": output_file,
            }
            attempt_logs.append(
                {
                    "attempt": attempt,
                    "passed": False,
                    "guard_valid": False,
                    "error": last_guard["reason"],
                }
            )
            error_feedback = (
                f"Previous failing code:\n```python\n{test_code}\n```\n\n"
                f"AST Assertion Guard rejected the code: {last_guard['reason']}\n"
                "Restore a valid Playwright `expect(...)` assertion that verifies the User Story."
            )
            continue

        print(
            f"[3/4] Executing test '{output_file}' with pytest (Attempt {attempt}/{max_retries})..."
        )
        last_result = run_playwright_test(test_code=test_code, filename=output_file)

        if last_result.get("passed"):
            print(
                f"\n[4/4] [SUCCESS] Test passed on attempt {attempt} "
                f"(AST Assertion Guard verified {len(last_guard['assertions'])} assertion(s))!"
            )
            if last_result.get("stdout"):
                print("\n--- Pytest Output ---")
                print(last_result["stdout"])
            attempt_logs.append(
                {
                    "attempt": attempt,
                    "passed": True,
                    "guard_valid": True,
                    "error": None,
                }
            )
            return {
                "success": True,
                "attempts": attempt,
                "healed_on_retry": attempt > 1,
                "output_file": last_result.get("file_path", output_file),
                "test_code": test_code,
                "assertion_guard": last_guard,
                "test_result": last_result,
                "attempt_logs": attempt_logs,
            }

        # Test failed: prepare feedback (including previous code + traceback) for self-healing
        combined_output = "\n".join(
            part
            for part in [last_result.get("stdout", ""), last_result.get("stderr", "")]
            if part
        ).strip()
        traceback_text = _clean_pytest_traceback(
            combined_output
            or f"Pytest exited with code {last_result.get('exit_code')}"
        )
        attempt_logs.append(
            {
                "attempt": attempt,
                "passed": False,
                "guard_valid": True,
                "error": traceback_text,
            }
        )
        error_feedback = (
            f"Pytest failure output:\n{traceback_text}\n\n"
            "Fix the failing locator or missing navigation step using ONLY valid selectors from the DOM JSON."
        )

        print(
            f"\n[4/4] [SELF-HEAL] Attempt {attempt} failed (exit code {last_result.get('exit_code')})."
        )
        if attempt < max_retries:
            print("      Feeding pytest traceback back to the Agent for self-healing...")
        else:
            print("      Maximum retries reached. Test failed after all attempts.")

    return {
        "success": False,
        "attempts": max_retries,
        "healed_on_retry": False,
        "output_file": last_result.get("file_path", output_file),
        "test_code": test_code if "test_code" in locals() else "",
        "assertion_guard": last_guard,
        "test_result": last_result,
        "attempt_logs": attempt_logs,
    }
