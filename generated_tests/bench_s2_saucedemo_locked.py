import re
from playwright.sync_api import Page, expect


class PageObject:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        self.page.goto(url)


def test_user_story(page: Page):
    pom = PageObject(page)
    pom.navigate("https://www.saucedemo.com/")
    page.locator("#user-name").fill("locked_out_user")
    page.locator("#password").fill("secret_sauce")
    page.locator("#login-button").click()
    expect(page.locator('[data-test="error"]')).to_contain_text('locked out')