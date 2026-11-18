"""CLI entry point for the Autonomous Spec-to-Playwright Agent."""

import argparse
import sys

from agent.orchestrator import run_agent

DEFAULT_URL = "https://www.saucedemo.com/"
DEFAULT_STORY = (
    "Log in with username 'standard_user' and password 'secret_sauce', "
    "and verify that after login the user is redirected to the inventory page ('/inventory.html')"
)
DEFAULT_OUTPUT = "generated_tests/test_saucedemo_login.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Spec-to-Playwright Agent: Generates and self-heals Playwright POM tests."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"Target webpage URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--story",
        type=str,
        default=DEFAULT_STORY,
        help="User story / specification to automate.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"File path for the generated test (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum number of self-healing attempts (default: 3)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_agent(
        url=args.url,
        user_story=args.story,
        output_file=args.output,
        max_retries=args.retries,
    )

    print("\n" + "=" * 70)
    if summary["success"]:
        print(
            f"✅ Agent finished successfully in {summary['attempts']} attempt(s)! "
            f"Saved to: {summary['output_file']}"
        )
        return 0
    else:
        print(
            f"❌ Agent failed after {summary['attempts']} attempt(s). "
            f"Last test saved to: {summary['output_file']}"
        )
        if summary["test_result"].get("stdout"):
            print("\nLast Pytest Output:\n" + summary["test_result"]["stdout"])
        if summary["test_result"].get("stderr"):
            print("\nLast Pytest Error:\n" + summary["test_result"]["stderr"])
        return 1


if __name__ == "__main__":
    sys.exit(main())
