"""Module for inspecting a webpage's DOM and extracting interactive elements."""

import json
import sys
from typing import Any
from playwright.sync_api import sync_playwright


EXTRACTION_JS = """
() => {
    const selectors = [
        'button',
        'input',
        'a',
        'select',
        'textarea',
        'form',
        '[role="button"]',
        '[role="link"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="combobox"]',
        '[role="textbox"]',
        '[role="menuitem"]',
        '[role="tab"]'
    ];
    
    const elements = document.querySelectorAll(selectors.join(', '));
    const results = [];
    const seen = new Set();

    const isVisible = (el) => {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    elements.forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);

        const tag = el.tagName.toLowerCase();
        const inputType = (el.type || '').toLowerCase();
        if (tag === 'input' && inputType === 'hidden') {
            return;
        }
        if (!isVisible(el)) {
            return;
        }

        const getAttr = (name) => {
            const val = el.getAttribute(name);
            return val !== null && val.trim() !== '' ? val.trim() : null;
        };

        // Extract visible text (avoiding huge container text dumps for forms/selects)
        let text = null;
        if (tag === 'input' && ['submit', 'button', 'reset'].includes(inputType)) {
            text = el.value ? el.value.trim() : null;
        } else if (!['form', 'input', 'select'].includes(tag)) {
            const rawText = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            text = rawText ? rawText.slice(0, 200) : null;
        }

        let options = null;
        if (tag === 'select' && el.options) {
            options = Array.from(el.options).map(opt => ({
                value: opt.value,
                text: (opt.text || '').trim()
            }));
        }

        let checked = null;
        if (tag === 'input' && ['checkbox', 'radio'].includes(inputType)) {
            checked = Boolean(el.checked);
        }

        const item = {
            tag: tag,
            type: tag === 'input' || tag === 'button' ? (getAttr('type') || (tag === 'input' ? 'text' : null)) : null,
            text: text,
            id: el.id ? el.id.trim() : null,
            name: getAttr('name'),
            placeholder: getAttr('placeholder'),
            role: getAttr('role') || el.ariaRoleDescription || null,
            data_testid: getAttr('data-testid') || getAttr('data-test'),
            aria_label: getAttr('aria-label'),
            href: tag === 'a' ? getAttr('href') : null,
            checked: checked,
            options: options
        };

        // Remove null/empty fields to keep JSON lightweight for LLM token efficiency
        const cleanItem = Object.fromEntries(
            Object.entries(item).filter(([_, v]) => v !== null && v !== '')
        );

        results.push(cleanItem);
    });

    return results;
}
"""


def inspect_dom(url: str, headless: bool = True, timeout: int = 30000) -> dict[str, Any]:
    """
    Launch a headless Chromium browser, navigate to the target URL, and return a
    lightweight dictionary of interactive elements on the page.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=timeout)
            title = page.title()
            interactive_elements = page.evaluate(EXTRACTION_JS)

            return {
                "url": page.url,
                "title": title,
                "element_count": len(interactive_elements),
                "interactive_elements": interactive_elements,
            }
        finally:
            browser.close()


def inspect_dom_json(url: str, indent: int = 2) -> str:
    """Convenience wrapper that returns the extracted DOM data as a JSON string."""
    data = inspect_dom(url)
    return json.dumps(data, indent=indent, ensure_ascii=False)


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.saucedemo.com/"
    print(inspect_dom_json(target_url))
