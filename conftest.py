import json
import os
import time
import pytest
import pandas as pd
import allure
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


@pytest.fixture(scope="session")
def users_from_json():
    """Load user credentials and test data."""
    data_path = os.path.join(os.path.dirname(__file__), "data", "users.json")
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def login_logout():
    """Setup and teardown browser."""
    driver = webdriver.Chrome()
    driver.maximize_window()
    wait = WebDriverWait(driver, 10)
    logged_in = {"status": False}

    yield driver, wait, logged_in

    # Logout if logged in
    if logged_in["status"]:
        try:
            wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//p[@class='oxd-userdropdown-name']")
                )
            ).click()
            wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[normalize-space()='Logout']")
                )
            ).click()
            wait.until(EC.presence_of_element_located((By.NAME, "username")))
        except Exception:
            pass

    driver.quit()


def do_login(driver, wait, username, password):
    """Perform login and return True if successful."""
    driver.get("https://opensource-demo.orangehrmlive.com/web/index.php/auth/login")
    wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(
        username
    )
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    # Check if Dashboard appears
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//span[text()='Dashboard']"))
        )
        return True
    except Exception:
        return False


def fetch_all_records(driver, wait):
    """Fetch all user table data from Admin -> System Users."""
    records = []
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.oxd-table-body")))
    time.sleep(1)

    while True:
        rows = driver.find_elements(
            By.XPATH, "//div[@class='oxd-table-body']//div[@role='row']"
        )
        for row in rows:
            cols = row.find_elements(By.XPATH, ".//div[@role='cell']")
            if len(cols) >= 4:
                record = {
                    "Username": cols[1].text.strip(),
                    "User Role": cols[2].text.strip(),
                    "Employee Name": cols[3].text.strip(),
                    "Status": cols[4].text.strip(),
                }
                records.append(record)

        try:
            next_btn = driver.find_element(
                By.XPATH,
                "//button[@class='oxd-pagination-page-item oxd-pagination-next']",
            )
            if "disabled" in next_btn.get_attribute("class"):
                break
            next_btn.click()
            time.sleep(1)
        except Exception:
            break

    return records


def save_to_files(data, prefix="orangehrm_users"):
    """Save to JSON and CSV."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_file = f"{prefix}_{timestamp}.csv"
    json_file = f"{prefix}_{timestamp}.json"

    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    return csv_file, json_file
