"""Autonomous Spec-to-Playwright Agent Orchestrator with Self-Healing Loop."""

from typing import Any, Optional

from agent.code_generator import generate_playwright_test
from tools.dom_inspector import inspect_dom_json
from tools.test_runner import run_playwright_test


def run_agent(
    url: str,
    user_story: str,
    output_file: str = "generated_tests/test_saucedemo_login.py",
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Execute the autonomous Spec-to-Playwright workflow:
    1. Inspect live DOM elements on `url`.
    2. Generate a Playwright POM test for `user_story`.
    3. Execute the generated test with pytest.
    4. Self-heal by feeding pytest tracebacks back to the LLM up to `max_retries` times.
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
    last_result: dict[str, Any] = {}

    for attempt in range(1, max_retries + 1):
        print(
            f"\n[2/4] Generating Playwright POM test (Attempt {attempt}/{max_retries})..."
        )
        test_code = generate_playwright_test(
            url=url,
            user_story=user_story,
            dom_json=dom_json,
            error_feedback=error_feedback,
        )

        print(
            f"[3/4] Executing test '{output_file}' with pytest (Attempt {attempt}/{max_retries})..."
        )
        last_result = run_playwright_test(test_code=test_code, filename=output_file)

        if last_result.get("passed"):
            print(f"\n[4/4] [SUCCESS] Test passed on attempt {attempt}!")
            if last_result.get("stdout"):
                print("\n--- Pytest Output ---")
                print(last_result["stdout"])
            return {
                "success": True,
                "attempts": attempt,
                "output_file": last_result.get("file_path", output_file),
                "test_result": last_result,
            }

        # Test failed: prepare feedback (including previous code + traceback) for self-healing
        combined_output = "\n".join(
            part
            for part in [last_result.get("stdout", ""), last_result.get("stderr", "")]
            if part
        ).strip()
        traceback_text = (
            combined_output
            or f"Pytest exited with code {last_result.get('exit_code')}"
        )
        error_feedback = (
            f"Previous failing code:\n```python\n{test_code}\n```\n\n"
            f"Pytest failure output:\n{traceback_text}"
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
        "output_file": last_result.get("file_path", output_file),
        "test_result": last_result,
    }
