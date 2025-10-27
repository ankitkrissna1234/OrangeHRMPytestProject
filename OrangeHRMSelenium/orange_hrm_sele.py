"""
fetch_orangehrm_users.py

Purpose:
 - Login to OrangeHRM demo
 - Navigate to Admin -> System Users
 - Fetch ALL user records across pages
 - Save results to orangehrm_users.csv and orangehrm_users.json

Pre-req:
 pip install selenium pandas
 Download the matching chromedriver and have it in PATH
"""

import time
import json
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


def safe_find_elements(locator_list, root):
    """
    Try multiple locator tuples on root (or driver) and return first non-empty result.
    locator_list: list of (By, selector) tuples
    root: driver or a WebElement
    """
    for by, sel in locator_list:
        try:
            elems = root.find_elements(by, sel)
            if elems:
                return elems
        except Exception:
            continue
    return []


def click_element(driver, by, sel):
    """Click with fallback catches and small wait"""
    try:
        el = driver.find_element(by, sel)
        el.click()
        return True
    except ElementClickInterceptedException:
        # try JS click
        try:
            driver.execute_script("arguments[0].click();", driver.find_element(by, sel))
            return True
        except Exception:
            return False
    except Exception:
        return False


def main():
    driver = webdriver.Chrome()
    driver.maximize_window()
    wait = WebDriverWait(driver, 20)

    try:
        # 1) Open login page
        driver.get("https://opensource-demo.orangehrmlive.com/web/index.php/auth/login")

        # 2) Login
        wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys("Admin")
        driver.find_element(By.NAME, "password").send_keys("admin123")
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        # 3) Wait for Dashboard and click Admin


        wait.until(EC.presence_of_element_located((By.XPATH, "//span[text()='Dashboard']")))
        wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Admin']"))).click()
        time.sleep(5)
        current_url = driver.current_url
        assert 'dashboard' in current_url

        # 4) Wait for table to appear
        # there may be slight delay, wait up to 20s for table role container
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='table']")))
        time.sleep(1.2)  # small extra buffer

        all_records = []

        page_num = 1
        while True:
            print(f"\n--- Processing page {page_num} ---")

            # Wait for at least one row to be present (header + rows)
            try:
                wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[@role='table']//div[@role='row']")))
            except TimeoutException:
                print("No rows found on page — continuing (maybe empty).")

            # Try a few different row locators (some OrangeHRM versions render rows as 'oxd-table-card' elements)
            row_locators = [
                (By.XPATH, "//div[@role='table']//div[@role='row']"),  # role-based rows
                (By.CSS_SELECTOR, "div.oxd-table-body > div.oxd-table-card"),  # card rows
                (By.CSS_SELECTOR, "div.oxd-table-body div.oxd-table-row")  # alternative class
            ]
            rows = safe_find_elements(row_locators, driver)

            # If the header row is included, skip the first element if it's header
            # Identify header by checking whether row has header cells or contains "Username" text
            processed_on_page = 0
            for i, row in enumerate(rows):
                try:
                    # skip header row which often contains 'Username' or column names
                    row_text_lower = row.text.lower()
                    if "username" in row_text_lower and (
                            "user role" in row_text_lower or "employee name" in row_text_lower):
                        # header row -> skip
                        continue

                    # cells may be in role='cell' or class 'oxd-table-cell'
                    cell_locators = [
                        (By.XPATH, ".//div[@role='cell']"),
                        (By.CSS_SELECTOR, ".oxd-table-cell"),
                        (By.XPATH, ".//div[contains(@class,'oxd-table-cell')]")
                    ]
                    cols = safe_find_elements(cell_locators, row)

                    # Extract texts in a robust way (ignore empty strings from checkboxes/icons)
                    cell_texts = [c.text.strip() for c in cols if c.text and c.text.strip()]
                    # Fallback: if no cell_texts, take the whole row text and split lines

                    if not cell_texts:
                        # split by newline, filter empties
                        parts = [p.strip() for p in row.text.splitlines() if p.strip()]
                        cell_texts = parts

                    # Heuristics: typical order is [Username, User Role, Employee Name, Status, ...]
                    # But sometimes a leading checkbox/icon exists; our cell_texts already removes empties.
                    username = cell_texts[0] if len(cell_texts) >= 1 else ""
                    user_role = cell_texts[1] if len(cell_texts) >= 2 else ""
                    employee_name = cell_texts[2] if len(cell_texts) >= 3 else ""
                    status = cell_texts[3] if len(cell_texts) >= 4 else ""

                    record = {
                        "Username": username,
                        "User Role": user_role,
                        "Employee Name": employee_name,
                        "Status": status,
                        "raw_cells": cell_texts  # keep raw for debugging/fallback
                    }
                    all_records.append(record)
                    processed_on_page += 1
                except Exception as e:
                    # keep processing other rows
                    print(f"  Warning: failed to parse a row: {e}")
                    continue

            print(f"  Collected {processed_on_page} rows from page {page_num}")

            # Try pagination - find Next button and see if it is disabled.
            # We'll attempt several common Next-button selectors used by OrangeHRM UI:
            next_button_selectors = [
                (By.XPATH,
                 "//button[contains(@class,'oxd-pagination-page-item') and contains(@class,'oxd-pagination-next')]"),
                (By.XPATH,
                 "//button[contains(@class,'oxd-pagination-page-item') and .//i[contains(@class,'arrow-right')]]"),
                (By.XPATH, "//button[@aria-label='Go to next page']"),
                (By.CSS_SELECTOR, "button.oxd-pagination-page-item.oxd-pagination-next"),
                (By.XPATH, "//button[normalize-space()='Next']"),
            ]

            next_button = None
            next_parent = None
            for by, sel in next_button_selectors:
                try:
                    candidate = driver.find_element(by, sel)
                    # determine if it is disabled via attribute/class
                    cls = candidate.get_attribute("class") or ""
                    aria_disabled = candidate.get_attribute("disabled") or candidate.get_attribute(
                        "aria-disabled") or ""
                    # If button is present but visually disabled, break pagination
                    if ("disabled" in cls.lower()) or (aria_disabled and aria_disabled.lower() in ("true", "disabled")):
                        next_button = None
                        next_parent = None
                        break
                    next_button = candidate
                    next_parent = candidate
                    break
                except Exception:
                    next_button = None
                    continue

            if not next_button:
                # Could be no next button or disabled -> end loop
                print("  No clickable Next button found or it's disabled -> reached last page.")
                break

            # Click Next and continue
            try:
                # scroll into view before clicking
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(0.2)
                next_button.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", next_button)
                except Exception:
                    print("  Failed to click next button -> stopping pagination.")
                    break

            # wait a bit for next page to load
            time.sleep(1.2)
            page_num += 1

        # Deduplicate records if same rows repeated across pages
        # Use Username + Employee Name + Status as key
        deduped = []
        seen = set()
        for r in all_records:
            key = (r.get("Username", ""), r.get("Employee Name", ""), r.get("Status", ""))
            if key not in seen:
                deduped.append(r)
                seen.add(key)

        print(f"\nTotal raw records captured: {len(all_records)}")
        print(f"Total deduplicated records: {len(deduped)}")

        # Prepare final records without raw_cells for nicer CSV/JSON
        final_records = []
        for r in deduped:
            final_records.append({
                "Username": r.get("Username", ""),
                "User Role": r.get("User Role", ""),
                "Employee Name": r.get("Employee Name", ""),
                "Status": r.get("Status", "")
            })

        # Save CSV & JSON
        df = pd.DataFrame(final_records)
        csv_name = "orangehrm_users.csv"
        json_name = "orangehrm_users.json"
        df.to_csv(csv_name, index=False)
        with open(json_name, "w", encoding="utf-8") as f:
            json.dump(final_records, f, ensure_ascii=False, indent=2)

        print(f"\nSaved {len(final_records)} records to '{csv_name}' and '{json_name}'")

    except Exception as e:
        print("Fatal error:", e)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
