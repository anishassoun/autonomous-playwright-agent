# Multi-Site Benchmark & Mutation Verification Results

- **Total Scenarios**: 8 across 2 sites (`saucedemo.com`, `the-internet.herokuapp.com`)
- **Final Pass Rate**: 8/8 (100%)
- **Self-Healed Scenarios**: 2 (recovered from stale selector tracebacks on Attempt 2)
- **Mutation Verification**: 8/8 passing tests failed when their `expect(...)` assertion was mutated
- **Total Execution Time**: 324.74s

## Benchmark Summary Table

| ID | Story | Target Site | 1st Attempt | Self-Healed on Retry | AST Guard | Mutation Check Failed as Expected | Time (s) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | SauceDemo Valid Login | `saucedemo.com` | Pass (1/1) | N/A (Passed 1st) | Pass | Yes (Mutant Failed) | 9.08s |
| S2 | SauceDemo Locked Out User Error | `saucedemo.com` | Pass (1/1) | N/A (Passed 1st) | Pass | Yes (Mutant Failed) | 5.93s |
| S3 | SauceDemo Empty Username Validation | `saucedemo.com` | Pass (1/1) | N/A (Passed 1st) | Pass | Yes (Mutant Failed) | 8.24s |
| S4 | SauceDemo Stale Button Selector (Self-Heal) | `saucedemo.com` | Fail (Seeded Stale Selector) | Yes (Attempt 2) | Pass | Yes (Mutant Failed) | 58.0s |
| S5 | HerokuApp Form Auth Valid Login | `the-internet.herokuapp.com/login` | Pass (1/1) | N/A (Passed 1st) | Pass | Yes (Mutant Failed) | 29.6s |
| S6 | HerokuApp Stale Input Selector (Self-Heal) | `the-internet.herokuapp.com/login` | Fail (Seeded Stale Selector) | Yes (Attempt 3) | Pass | Yes (Mutant Failed) | 89.57s |
| S7 | HerokuApp Checkboxes Toggle | `the-internet.herokuapp.com/checkboxes` | Pass (1/1) | N/A (Passed 1st) | Pass | Yes (Mutant Failed) | 29.4s |
| S8 | HerokuApp Dropdown Selection | `the-internet.herokuapp.com/dropdown` | Pass (1/1) | N/A (Passed 1st) | Pass | Yes (Mutant Failed) | 54.24s |

## Self-Healing Trace Example (S4: SauceDemo Stale Selector)

### Attempt 1 Failure Output (`#login-btn-stale`)
```text
F                                                                        [100%]
================================== FAILURES ===================================
__________________________ test_user_story[chromium] __________________________
generated_tests\bench_s4_saucedemo_healed.py:19: in test_user_story
    page.locator("#login-btn-stale").click(timeout=2000)
.venv\Lib\site-packages\playwright\sync_api\_generated.py:11045: in click
    self._sync(
.venv\Lib\site-packages\playwright\_impl\locator.py:222: in click
    return await self._frame.click(
.venv\Lib\site-packages\playwright\_impl\frame.py:587: in click
    return await self._channel.click(
.venv\Lib\site-packages\playwright\_impl\channel_owner.py:387: in finish
    raise e from None
.venv\Lib\site-packages\playwright\_impl\channel_owner.py:352: in finish
    result = await zone.run_async(lambda: awaitable)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.venv\Lib\site-packages\playwright\_impl\utils\zones.py:58: in run_async
    return await func()
           ^^^^^^^^^^^^
E   playwright._impl._errors.TimeoutError: Locator.click: Timeout 2000ms exceeded.
E   Call log:
E     - waiting for locator("#login-btn-stale")
```

### Attempt 2 Self-Healed Code (`#login-button`)
```python
import re
from playwright.sync_api import Page, expect


class PageObject:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        self.page.goto(url)


def test_user001(page: Page):
    pom = PageObject(page)
    pom.navigate("https://www.saucedemo.com/")
    page.locator("#user-name").fill("standard_user")
    page.locator("#password").fill("secret_sauce")
    page.locator("#login-button").click()
    expect(page).to_have_url(re.compile(r'.*/inventory.html'))
```
