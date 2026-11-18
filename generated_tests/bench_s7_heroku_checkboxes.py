import re
from playwright.sync_api import Page, expect


class PageObject:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        self.page.goto(url)


def test_user_story(page: Page):
    pom = PageObject(page)
    pom.navigate("https://the-internet.herokuapp.com/checkboxes")
    page.locator("input[type='checkbox']").first.check()
    expect(page.locator("input[type='checkbox']").first).to_be_checked()