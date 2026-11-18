"""Unit tests for the AST Assertion Guard, DOM Inspector, and Prompt Builder."""

import urllib.parse

from agent.assertion_guard import (
    extract_assertions,
    mutate_test_assertion,
    validate_test_assertions,
)
from agent.code_generator import _build_prompt, strip_markdown_fences
from tools.dom_inspector import inspect_dom


def test_assertion_guard_allows_valid_expect_url():
    code = """
import re
from playwright.sync_api import Page, expect

def test_valid_login(page: Page):
    page.goto("https://www.saucedemo.com/")
    page.locator("#user-name").fill("standard_user")
    page.locator("#password").fill("secret_sauce")
    page.locator("#login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory.html"))
"""
    result = validate_test_assertions(code)
    assert result["valid"] is True
    assert len(result["assertions"]) == 1
    assert result["assertions"][0]["matcher"] == "to_have_url"


def test_assertion_guard_rejects_assert_true():
    code = """
from playwright.sync_api import Page

def test_cheating_with_assert_true(page: Page):
    page.goto("https://www.saucedemo.com/")
    assert True
"""
    result = validate_test_assertions(code)
    assert result["valid"] is False
    assert "Trivial assertion" in result["reason"]


def test_assertion_guard_rejects_missing_assertions():
    code = """
from playwright.sync_api import Page

def test_no_assertions(page: Page):
    page.goto("https://www.saucedemo.com/")
    page.locator("#login-button").click()
"""
    result = validate_test_assertions(code)
    assert result["valid"] is False
    assert "contains no valid Playwright" in result["reason"]


def test_assertion_guard_rejects_weakened_retry():
    attempt_1_code = """
import re
from playwright.sync_api import Page, expect

def test_login(page: Page):
    page.goto("https://www.saucedemo.com/")
    page.locator("#stale-btn").click()
    expect(page).to_have_url(re.compile(r".*/inventory.html"))
"""
    baseline = extract_assertions(attempt_1_code)
    assert len(baseline) == 1

    # Attempt 2 deletes expect(page) and uses a generic assert on page.url != ""
    attempt_2_weakened = """
from playwright.sync_api import Page

def test_login(page: Page):
    page.goto("https://www.saucedemo.com/")
    page.locator("#login-button").click()
    assert page.url != ""
"""
    result = validate_test_assertions(attempt_2_weakened, baseline_assertions=baseline)
    assert result["valid"] is False
    assert "Assertion weakening detected" in result["reason"]


def test_mutate_test_assertion_inverts_or_corrupts_expectation():
    original = """
from playwright.sync_api import Page, expect

def test_login(page: Page):
    expect(page).to_have_url("https://www.saucedemo.com/inventory.html")
"""
    mutated = mutate_test_assertion(original)
    assert mutated != original
    assert "__MUTATED_IMPOSSIBLE_EXPECTED_VALUE_99999__" in mutated


def test_strip_markdown_fences_and_retry_prompt():
    wrapped = "Here is the code:\n```python\ndef test_a(page):\n    pass\n```\n"
    assert strip_markdown_fences(wrapped) == "def test_a(page):\n    pass"

    retry_prompt = _build_prompt(
        url="https://example.com",
        user_story="Login test",
        dom_json="{}",
        error_feedback="Locator timeout",
    )
    assert "Do NOT weaken, delete, or trivialize" in retry_prompt


def test_dom_inspector_extracts_only_visible_interactive_elements():
    html = """
    <html>
      <head><title>Unit Test Page</title></head>
      <body>
        <div class="non-interactive">Ignore me</div>
        <form id="login-form" aria-label="Login Form">
          <input type="text" id="user" name="username" placeholder="Enter user" data-testid="user-input" />
          <input type="hidden" id="csrf" value="secret" />
          <button type="submit" id="submit-btn" style="display:none;">Hidden Button</button>
          <button type="submit" id="visible-btn">Sign In</button>
          <select id="role-select">
            <option value="admin">Admin</option>
            <option value="guest">Guest</option>
          </select>
        </form>
      </body>
    </html>
    """
    data_url = "data:text/html," + urllib.parse.quote(html)
    snapshot = inspect_dom(data_url)

    assert snapshot["title"] == "Unit Test Page"
    ids = [el.get("id") for el in snapshot["interactive_elements"]]
    assert "user" in ids
    assert "visible-btn" in ids
    assert "role-select" in ids
    # Hidden elements must be excluded
    assert "csrf" not in ids
    assert "submit-btn" not in ids
