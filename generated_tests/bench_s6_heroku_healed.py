import re
from playwright.sync_api import Page, expect


class PageObject:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        self.page.goto(url)


def test_user001(page: Page):
    pom = PageObject(page)
    pom.navigate("https://the-internet.herokuapp.com/login")
    page.locator("#username").fill("wrong_user", timeout=2000)
    page.locator("#password").fill("wrong_pass", timeout=2000)
    page.locator("button[type='submit']").click(timeout=2000)
    expect(page.locator("#flash")).to_contain_text("Your username is invalid!")