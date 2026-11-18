import re
from playwright.sync_api import Page, expect


class SauceDemoPage:
    def __init__(self, page: Page):
        self.page = page
        self.username_input = page.locator("#user-name")
        self.password_input = page.locator("#password")
        self.login_button = page.locator("#login-button")

    def navigate(self):
        self.page.goto("https://www.saucedemo.com/")

    def login(self, username: str, password: str):
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.login_button.click()


def test_login_and_redirect(page: Page):
    pom = SauceDemoPage(page)
    pom.navigate()
    pom.login("standard_user", "secret_sauce")
    expect(page).to_have_url(re.compile(r".*/inventory.html"))