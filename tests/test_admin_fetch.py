import json
import time
import pytest
import allure
import os
import sys

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

# ✅ Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.insert(0, project_root)

from conftest import do_login, login_logout, fetch_all_records, save_to_files


def pytest_generate_tests(metafunc):
    """Parameterize test with users.json data."""
    if "user" in metafunc.fixturenames:
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
        with open(data_path, "r", encoding="utf-8") as f:
            users = json.load(f)
        metafunc.parametrize("user", users, ids=[u["id"] for u in users])


def test_admin_login_and_fetch(
    user, login_logout: tuple[WebDriver, WebDriverWait, dict[str, bool]]
):
    """Run login + record fetch for positive and negative scenarios."""
    driver, wait, logged_in = login_logout
    username = user["username"]
    password = user["password"]
    test_type = user["type"]

    with allure.step(f"Attempt login as {username} ({test_type})"):
        success = do_login(driver, wait, username, password)
        if success:
            logged_in["status"] = True

    # ✅ Positive Case
    if test_type == "positive":
        assert success, f"Expected successful login for user: {username}"

        with allure.step("Navigate to Admin > System Users"):
            wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='Admin']"))
            ).click()
            time.sleep(1)

        with allure.step("Fetch user records"):
            records = fetch_all_records(driver, wait)
            assert len(records) > 0, "No records found in Admin table"
            allure.attach(
                json.dumps(records[:5], indent=2),
                name="sample_records",
                attachment_type=allure.attachment_type.JSON,
            )

        with allure.step("Save to JSON and CSV"):
            csv_file, json_file = save_to_files(records)
            allure.attach.file(
                csv_file, name="CSV_Data", attachment_type=allure.attachment_type.CSV
            )
            allure.attach.file(
                json_file, name="JSON_Data", attachment_type=allure.attachment_type.JSON
            )

    # ❌ Negative Cases
    else:
        with allure.step("Validate login failure"):
            error_message = ""

            try:
                # 1️⃣ Look for global alert like "Invalid credentials"
                error_elem = WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located(
                        (
                            By.XPATH,
                            "//div[@role='alert']//p[contains(@class,'oxd-text') or contains(text(),'Invalid') or contains(text(),'Required')]",
                        )
                    )
                )
                error_message = error_elem.text.strip()
            except Exception:
                # 2️⃣ Look for field-level validation like "Required"
                try:
                    field_errors = driver.find_elements(
                        By.XPATH,
                        "//span[contains(@class,'oxd-input-field-error-message')]",
                    )
                    if field_errors:
                        error_message = ", ".join(
                            e.text.strip() for e in field_errors if e.text.strip()
                        )
                except Exception:
                    pass

            # 3️⃣ Fallback screenshot if still nothing
            if not error_message:
                screenshot_path = f"screenshot_{username}.png"
                driver.save_screenshot(screenshot_path)
                allure.attach.file(
                    screenshot_path,
                    name="Login_Error_Screenshot",
                    attachment_type=allure.attachment_type.PNG,
                )

            dashboard = driver.find_elements(By.XPATH, "//span[text()='Dashboard']")
            assert (
                not dashboard
            ), f"Unexpectedly logged in with invalid credentials: {username}"
            assert (
                error_message != ""
            ), "No error message displayed for invalid credentials"

            allure.attach(
                error_message,
                name="Error_Message",
                attachment_type=allure.attachment_type.TEXT,
            )
