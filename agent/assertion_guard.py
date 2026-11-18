"""AST-based static analysis guard to prevent assertion weakening during self-healing."""

import ast
import re
from typing import Any, Optional


PLAYWRIGHT_EXPECT_MATCHERS = {
    "to_have_url",
    "to_have_title",
    "to_have_text",
    "to_contain_text",
    "to_be_visible",
    "to_be_hidden",
    "to_be_enabled",
    "to_be_disabled",
    "to_be_checked",
    "to_be_editable",
    "to_be_empty",
    "to_be_focused",
    "to_have_attribute",
    "to_have_class",
    "to_have_count",
    "to_have_css",
    "to_have_id",
    "to_have_js_property",
    "to_have_value",
    "to_have_values",
    "not_to_have_url",
    "not_to_have_title",
    "not_to_have_text",
    "not_to_contain_text",
    "not_to_be_visible",
    "not_to_be_hidden",
    "not_to_be_enabled",
    "not_to_be_disabled",
    "not_to_be_checked",
    "not_to_have_value",
}


def _is_expect_call(node: ast.AST) -> Optional[dict[str, Any]]:
    """
    Check if `node` is a Playwright `expect(...).<matcher>(...)` call.
    Also supports `expect(...).not_to_...(...)`.
    """
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute):
        return None

    matcher_name = node.func.attr
    receiver = node.func.value

    # Handle expect(x).to_...(...)
    if (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "expect"
        and matcher_name in PLAYWRIGHT_EXPECT_MATCHERS
    ):
        target_src = ast.unparse(receiver.args[0]) if receiver.args else ""
        args_src = [ast.unparse(arg) for arg in node.args]
        return {
            "kind": "expect",
            "matcher": matcher_name,
            "target": target_src,
            "args": args_src,
            "source": ast.unparse(node),
        }

    return None


def _is_trivial_assert(node: ast.Assert) -> bool:
    """Return True if an `assert` statement is a tautology like `assert True` or `assert 1 == 1`."""
    test = node.test

    # Constant truthy value: `assert True`, `assert 1`, `assert "nonempty"`
    if isinstance(test, ast.Constant):
        return True

    # `assert bool(True)` or `assert bool(1)`
    if (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "bool"
        and all(isinstance(arg, ast.Constant) for arg in test.args)
    ):
        return True

    # Self-comparison or constant comparison: `assert 1 == 1`, `assert x == x`
    if isinstance(test, ast.Compare) and len(test.comparators) == 1:
        left_src = ast.unparse(test.left)
        right_src = ast.unparse(test.comparators[0])
        if left_src == right_src:
            return True
        if isinstance(test.left, ast.Constant) and isinstance(
            test.comparators[0], ast.Constant
        ):
            return True

    return False


def extract_assertions(code: str) -> list[dict[str, Any]]:
    """
    Parse Python test code and extract all valid Playwright `expect(...)` calls
    and non-trivial `assert` statements inside `test_*` functions.
    """
    tree = ast.parse(code)
    assertions: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            for child in ast.walk(node):
                expect_info = _is_expect_call(child)
                if expect_info is not None:
                    expect_info["function"] = node.name
                    assertions.append(expect_info)
                elif isinstance(child, ast.Assert):
                    if not _is_trivial_assert(child):
                        assertions.append(
                            {
                                "kind": "assert",
                                "matcher": "assert",
                                "target": ast.unparse(child.test),
                                "args": [],
                                "source": ast.unparse(child),
                                "function": node.name,
                            }
                        )
    return assertions


def validate_test_assertions(
    code: str,
    baseline_assertions: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Statically validate a generated Playwright test file before/after execution:
    1. Code must be syntactically valid Python.
    2. At least one `def test_*` function must exist.
    3. Every `def test_*` function must have at least one real `expect(...)` or
       meaningful comparison `assert` (rejecting `assert True`, `pass`, etc.).
    4. If `baseline_assertions` (from Attempt 1) is provided, subsequent self-healing
       attempts must not drop `expect(...)` calls or reduce assertion count.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "valid": False,
            "reason": f"SyntaxError in generated code: {exc}",
            "assertions": [],
        }

    test_funcs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    if not test_funcs:
        return {
            "valid": False,
            "reason": "No `def test_*` function found in generated code.",
            "assertions": [],
        }

    # Check for trivial `assert True` or constant assertions anywhere in test_* functions
    for func in test_funcs:
        for child in ast.walk(func):
            if isinstance(child, ast.Assert) and _is_trivial_assert(child):
                return {
                    "valid": False,
                    "reason": (
                        f"Trivial assertion `{ast.unparse(child)}` detected in `{func.name}`. "
                        "Self-healing must not use tautological assertions."
                    ),
                    "assertions": [],
                }

    assertions = extract_assertions(code)
    for func in test_funcs:
        func_assertions = [a for a in assertions if a.get("function") == func.name]
        if not func_assertions:
            return {
                "valid": False,
                "reason": (
                    f"Test function `{func.name}` contains no valid Playwright `expect(...)` "
                    "or meaningful assertion."
                ),
                "assertions": [],
            }

    if baseline_assertions:
        baseline_expects = [a for a in baseline_assertions if a["kind"] == "expect"]
        current_expects = [a for a in assertions if a["kind"] == "expect"]

        if baseline_expects and not current_expects:
            return {
                "valid": False,
                "reason": (
                    "Assertion weakening detected: Attempt 1 used Playwright `expect(...)` "
                    "assertions, which were removed in the retry attempt."
                ),
                "assertions": assertions,
            }

        if len(assertions) < len(baseline_assertions):
            return {
                "valid": False,
                "reason": (
                    f"Assertion weakening detected: assertion count dropped from "
                    f"{len(baseline_assertions)} in baseline to {len(assertions)}."
                ),
                "assertions": assertions,
            }

        # Verify expected argument literals aren't replaced with empty wildcards like `r".*"`
        for exp in current_expects:
            for arg in exp.get("args", []):
                if arg in ('""', "''", 're.compile(r".*")', 're.compile(".*")'):
                    return {
                        "valid": False,
                        "reason": (
                            f"Assertion weakening detected: overly permissive wildcard `{arg}` "
                            f"in `{exp['source']}`."
                        ),
                        "assertions": assertions,
                    }

    return {
        "valid": True,
        "reason": "All test functions contain valid, non-weakened assertions.",
        "assertions": assertions,
    }


def mutate_test_assertion(code: str) -> str:
    """
    Create a mutated copy of a passing Playwright test by inverting or corrupting
    the expected outcome inside `expect(...)` so that running pytest on the mutant
    must FAIL if the assertion is genuinely verifying application state.
    """
    # 1. Flip boolean state matchers if present
    boolean_flips = [
        (".to_be_checked()", ".not_to_be_checked()"),
        (".not_to_be_checked()", ".to_be_checked()"),
        (".to_be_visible()", ".to_be_hidden()"),
        (".to_be_hidden()", ".to_be_visible()"),
        (".to_be_enabled()", ".to_be_disabled()"),
        (".to_be_disabled()", ".to_be_enabled()"),
    ]
    for original, mutated in boolean_flips:
        if original in code:
            return code.replace(original, mutated, 1)

    # 2. Mutate string/regex expectations in to_have_url / to_contain_text / to_have_text / to_have_value
    pattern = re.compile(
        r"(\.to_(?:have_url|contain_text|have_text|have_value|have_title)\s*\()([^)]+)(\))"
    )
    match = pattern.search(code)
    if match:
        prefix, _, suffix = match.groups()
        mutated_call = f'{prefix}"__MUTATED_IMPOSSIBLE_EXPECTED_VALUE_99999__"{suffix}'
        return code[: match.start()] + mutated_call + code[match.end() :]

    # 3. Fallback: replace any `expect(` with an impossible URL check appended
    return code + '\n    raise AssertionError("Mutated assertion fallback")\n'
