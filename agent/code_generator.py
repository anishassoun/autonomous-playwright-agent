"""LLM code generator for turning user stories and DOM snapshots into Playwright tests."""

import json
import os
import re
from typing import Optional
import urllib.error
import urllib.request

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()


class GeneratedPlaywrightTest(BaseModel):
    """Structured output schema for generated Playwright test code."""

    explanation: str = Field(
        default="Generated Playwright POM test.",
        description="Brief summary of the Page Object Model classes and test flow.",
    )
    python_code: str = Field(
        description=(
            "Complete, standalone, runnable Python pytest-playwright code "
            "without markdown code fences."
        )
    )


SYSTEM_INSTRUCTION = r"""You are an expert QA Automation Engineer specializing in Python `pytest-playwright`.
Your task is to write a complete, standalone, runnable Python test file that fulfills a given User Story on a target URL.

Follow these strict rules:
1. Use ONLY the locators, IDs, names, placeholders, roles, or text present in the provided DOM JSON snapshot. Prefer `#<id>` CSS selectors (for example `page.locator("#user-name")`).
2. `page.locator(selector)` takes ONLY ONE string argument (a CSS selector like `"#user-name"`). Never pass two arguments to `page.locator()`.
3. Call `.fill(text)` and `.click()` directly on the Locator object (e.g. `self.username_input.fill(username)` and `self.login_button.click()`).
4. Structure the code using the Page Object Model (POM) pattern within the same file following this exact pattern:

```python
import re
from playwright.sync_api import Page, expect


class ExamplePage:
    def __init__(self, page: Page):
        self.page = page
        self.some_input = page.locator("#input-id")
        self.submit_btn = page.locator("#submit-id")

    def navigate(self, url: str):
        self.page.goto(url)

    def submit_form(self, value: str):
        self.some_input.fill(value)
        self.submit_btn.click()


def test_user_story(page: Page):
    pom = ExamplePage(page)
    pom.navigate("https://example.com")
    pom.submit_form("test")
    expect(page).to_have_url(re.compile(r".*/expected-path"))
```

5. Output ONLY valid, runnable Python code without markdown explanations.
"""


def strip_markdown_fences(code: str) -> str:
    """Extract Python code from markdown code fences or strip surrounding fences."""
    cleaned = code.strip()

    fenced_match = re.search(
        r"```(?:python|py)?\s*\n(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced_match:
        return fenced_match.group(1).strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    return cleaned


def _build_prompt(
    url: str,
    user_story: str,
    dom_json: str,
    error_feedback: Optional[str] = None,
) -> str:
    prompt_parts = [
        f"Target URL: {url}",
        f"User Story: {user_story}",
        "Extracted Interactive DOM Elements (JSON):",
        dom_json,
    ]
    if error_feedback:
        prompt_parts.extend(
            [
                "\nPrevious Test Execution Failed! Fix the issues based on this pytest error output:",
                error_feedback,
            ]
        )
    prompt_parts.append(
        "\nReturn ONLY runnable Python pytest-playwright code using a Page Object Model class and a `def test_...(page: Page):` function."
    )
    return "\n\n".join(prompt_parts)


def _generate_with_gemini(prompt: str, api_key: str) -> str:
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=GeneratedPlaywrightTest,
            temperature=0.1,
        ),
    )

    if response.parsed and isinstance(response.parsed, GeneratedPlaywrightTest):
        return strip_markdown_fences(response.parsed.python_code)

    raw_text = response.text or ""
    try:
        parsed_dict = json.loads(raw_text)
        if isinstance(parsed_dict, dict) and "python_code" in parsed_dict:
            return strip_markdown_fences(parsed_dict["python_code"])
    except json.JSONDecodeError:
        pass

    return strip_markdown_fences(raw_text)


def _generate_with_ollama(prompt: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model = os.getenv("OLLAMA_MODEL", "phi3:latest")

    payload = {
        "model": ollama_model,
        "system": SYSTEM_INSTRUCTION,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    req = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            response_text = body.get("response", "")
            cleaned_code = strip_markdown_fences(response_text)
            validated = GeneratedPlaywrightTest(python_code=cleaned_code)
            return validated.python_code
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to connect to Ollama at {ollama_url} (model={ollama_model}). "
            f"Ensure GEMINI_API_KEY is set in .env or Ollama is running locally. Error: {exc}"
        ) from exc


def generate_playwright_test(
    url: str,
    user_story: str,
    dom_json: str,
    error_feedback: Optional[str] = None,
) -> str:
    """
    Generate a standalone Python pytest-playwright test file from a target URL,
    user story, and extracted DOM JSON. Uses Gemini (`gemini-2.5-flash`) if
    `GEMINI_API_KEY` is configured in `.env`, or falls back to local Ollama.
    """
    load_dotenv(override=True)
    prompt = _build_prompt(url, user_story, dom_json, error_feedback)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key and api_key != "your_key_here":
        return _generate_with_gemini(prompt, api_key)

    return _generate_with_ollama(prompt)
