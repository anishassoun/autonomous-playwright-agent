import re
from playwright.sync_api import Page, expect


class PageObject:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        self.page.goto(url)


def test_user_story(page: Page):
    pom = PageObject(page)
    pom.navigate("https://the-internet.herokuapp.com/dropdown")
    page.locator("#dropdown").select_option("2")
    expect(page.locator("#dropdown")).to_have_value("2")