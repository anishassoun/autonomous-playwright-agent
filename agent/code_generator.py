"""LLM code generator for turning user stories and DOM snapshots into Playwright tests."""

import json
import os
import re
import time
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
Write a concise, standalone, runnable Python test file that fulfills the User Story on the Target URL.

Follow these strict rules:
1. Use ONLY the locators present in the DOM JSON snapshot. When an element has an `id`, ALWAYS use `page.locator("#<id>")` (e.g. `page.locator("#user-name")`, `page.locator("#login-button")`, `page.locator("#dropdown")`) without prefixing a tag name.
2. `page.locator(selector)` takes ONLY ONE string argument.
3. Structure the code using this exact Page Object template and ALWAYS call `pom.navigate("<Target URL>")` first inside `test_user_story(page: Page)`:

```python
import re
from playwright.sync_api import Page, expect


class PageObject:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        self.page.goto(url)


def test_user_story(page: Page):
    pom = PageObject(page)
    pom.navigate("https://example.com")
    # perform actions on page.locator(...) and end with expect(...)
```

4. Include ONLY the exact `expect(...)` check specified in the User Story. Do NOT invent extra URL assertions when the User Story checks an error message, checkbox, or dropdown value.
5. Do NOT weaken, delete, or trivialize the `expect()` assertion to make the test pass. Only fix locators, navigation, or element interaction calls.
6. Output ONLY the Python code block and stop immediately after the test function.
"""


def strip_markdown_fences(code: str) -> str:
    """Extract Python code from markdown code fences or strip surrounding fences."""
    cleaned = code.strip()

    fenced_match = re.search(
        r"```(?:python|py)?\s*\n(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced_match:
        cleaned = fenced_match.group(1).strip()
    elif cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Ensure standard playwright/re imports are present if referenced in generated test code
    header_imports = []
    if "re." in cleaned and "import re" not in cleaned:
        header_imports.append("import re")
    if (
        ("Page" in cleaned or "expect(" in cleaned)
        and "from playwright.sync_api import Page, expect" not in cleaned
    ):
        header_imports.append("from playwright.sync_api import Page, expect")

    if header_imports:
        cleaned = "\n".join(header_imports) + "\n" + cleaned

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
                (
                    "CRITICAL SELF-HEALING RULE: Do NOT weaken, delete, or trivialize the "
                    "`expect()` assertion to make the test pass. Only fix locators, "
                    "navigation, or element interaction calls. Replace any broken/stale "
                    "selector with the matching `id` selector from the DOM JSON above."
                ),
            ]
        )
    prompt_parts.append(
        f"\nWrite the complete corrected Python test starting with `pom.navigate('{url}')` inside `def test_user_story(page: Page):`."
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


def _generate_with_ollama(prompt: str, is_retry: bool = False) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model = os.getenv("OLLAMA_MODEL", "phi3:latest")

    models_to_try = [ollama_model, "gemma3:270m"]
    last_exc: Optional[Exception] = None

    for model_candidate in models_to_try:
        payload = {
            "model": model_candidate,
            "system": SYSTEM_INSTRUCTION,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2 if is_retry else 0.0,
                "num_ctx": 2048,
                "num_predict": 320,
            },
        }

        req = urllib.request.Request(
            ollama_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                response_text = body.get("response", "")
                cleaned_code = strip_markdown_fences(response_text)
                validated = GeneratedPlaywrightTest(python_code=cleaned_code)
                return validated.python_code
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_exc = exc
            time.sleep(1)

    raise RuntimeError(
        f"Failed to connect or timed out waiting for Ollama at {ollama_url} "
        f"(model={ollama_model}). Error: {last_exc}"
    ) from last_exc


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

    return _generate_with_ollama(prompt, is_retry=bool(error_feedback))
