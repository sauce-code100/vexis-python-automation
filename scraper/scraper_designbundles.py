import json
import os, sys
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
import time
import re
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
)


URLS = {
    "SVG": "https://designbundles.net/plus?categories=122,123&page=",
    "Sublimation": "https://designbundles.net/plus?categories=122,162&page=",
}

PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "scraper_progress.json")

IMAGE_FOLDER = os.path.join(os.path.dirname(__file__), "scraper_images")
if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)

# Load .env from the project root (one level up from /scraper)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "designbundles_scraper")


def safe_str(x):
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def safe_int(x):
    if x is None:
        return None
    try:
        s = str(x).strip()
        if not s:
            return None
        return int(s)
    except (ValueError, TypeError):
        return None


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as file:
            return json.load(file)
    else:
        return {"SVG": 1, "Sublimation": 1}


def extract_group_id(element, parent_element=None):
    # 1) direct attribute on <a>
    for attr in ["data-algolia-objectid", "data-objectid", "data-id", "data-product-id"]:
        gid = safe_int(element.get_attribute(attr))
        if gid:
            return gid

    # 2) attribute on product-box / parent
    if parent_element is not None:
        for attr in ["data-algolia-objectid", "data-objectid", "data-id", "data-product-id"]:
            gid = safe_int(parent_element.get_attribute(attr))
            if gid:
                return gid

    # 3) parse from href (often contains numeric id)
    href = safe_str(element.get_attribute("href"))
    if href:
        # try to find a long number in the URL path
        path = urlparse(href).path
        m = re.search(r"(\d{5,})", path)
        if m:
            return m.group(1)

    return None


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as file:
        json.dump(progress, file)


def setup_database():
    """Connect to MongoDB and ensure the groups collection has a unique index on group_id."""
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    collection = db["groups"]

    # Ensure a unique index on group_id to prevent duplicate inserts
    collection.create_index("group_id", unique=True)
    print(f"Connected to MongoDB database '{MONGO_DB_NAME}'.")

    return client, db, collection


def get_image_subfolder(group_id):
    subfolder = str(group_id)[0]
    subfolder_path = os.path.join(IMAGE_FOLDER, subfolder)
    
    if not os.path.exists(subfolder_path):
        os.makedirs(subfolder_path)
    
    return subfolder


def download_image(url, image_path):
    try:
        if os.path.exists(image_path):
            print(f"Image already exists at {image_path}, skipping download.")
            return

        response = requests.get(url)
        response.raise_for_status()

        with open(image_path, "wb") as file:
            file.write(response.content)
        print(f"Image saved to {image_path}")
    except requests.RequestException as e:
        print(f"Error downloading image: {e}")


def insert_group(collection, group_id, title, kind):
    """Insert a group document if it doesn't already exist (upsert with $setOnInsert)."""
    result = collection.update_one(
        {"group_id": group_id},
        {
            "$setOnInsert": {
                "group_id": group_id,
                "processed": 0,
                "title": title,
                "description": None,
                "tags": None,
                "categories": None,
                "kind": kind,
                "thumbnail": None,
                "wordpress_id": None,
                "input_tokens": None,
                "output_tokens": None,
            }
        },
        upsert=True,
    )

    if result.upserted_id:
        print(f"Inserted group: {title}")
    else:
        print(f"Group already exists, skipped: {title}")

    return result.upserted_id


def scrape_designbundles(page_number):
    progress = load_progress()
    print(f"Progress: {progress}")
    start_page = progress.copy()

    driver = webdriver.Chrome()
    driver.set_window_position(0, 0)

    client, db, collection = setup_database()

    cookie_button_clicked = False

    while True:
        done = True
        for kind, base_url in URLS.items():
            page = progress[kind]
            if page >= start_page[kind] + page_number:
                print(f"\nDone scraping {page_number} pages of {kind}.")
                continue

            url = base_url + str(page)
            print(f"\nScraping {kind} page {page}: {url}")
            driver.get(url)

            # Check for the cookie accept button without waiting, only if it hasn't been clicked before
            if not cookie_button_clicked:
                try:
                    print("Checking for cookie accept button...")
                    cookie_button = driver.find_element(By.ID, "cookieCheck")
                    cookie_button.click()
                    cookie_button_clicked = True
                    print("Cookie button clicked.")
                except (NoSuchElementException, ElementNotInteractableException):
                    print("No cookie button found or not interactable.")

            try:
                print(f"\nWaiting for Group name elements to be present on the page...")
                WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@class, 'details__product-name__link')]"))
                )
                elements = driver.find_elements(
                    By.XPATH, "//a[contains(@class, 'details__product-name__link')]"
                )
                print(f"Found {len(elements)} Group name elements on {kind} page {page}.")

                if not elements and page > progress[kind]:
                    print(f"No elements found on {kind} page {page}. Marking as done.")
                    progress[kind] = page  # Ensure we continue checking new pages
                    continue

                for element in elements:
                    try:
                        # Find the corresponding image element
                        parent_element = element.find_element(
                            By.XPATH, ".//ancestor::div[contains(@class, 'product-box')]",
                        )

                        # Extract group ID
                        group_id = extract_group_id(element, parent_element)
                        print(f"\nGroup ID: {group_id}")

                        # Extract title
                        title = element.text.strip()
                        print(f"Group Title: {title}")

                        # Attempt to find the <source> element first
                        try:
                            img_element = parent_element.find_element(
                                By.XPATH, ".//source[@type='image/webp']"
                            )
                            img_url = (
                                img_element.get_attribute("srcset")
                                .split(",")[0]
                                .strip()
                                .split(" ")[0]
                            )
                        except NoSuchElementException:
                            # Fallback to the <img> element if <source> is not found
                            try:
                                img_element = parent_element.find_element(
                                    By.XPATH, ".//img"
                                )
                                img_url = img_element.get_attribute("src")
                            except NoSuchElementException:
                                print(f"Image element not found for Group ID {group_id}. Skipping.")
                                continue

                        print(f"Image URL: {img_url}")

                        # Download image
                        subfolder = get_image_subfolder(group_id)
                        img_path = os.path.join(
                            IMAGE_FOLDER, subfolder, f"{group_id}.webp"
                        )
                        download_image(img_url, img_path)

                        # Insert group data into the database
                        insert_group(collection, group_id, title, kind)

                    except Exception as e:
                        print(f"Error processing element: {e}")
                        continue

                progress[kind] = page + 1
                save_progress(progress)
                done = False

            except Exception as e:
                print(f"Error occurred while processing {kind} page {page}: {e}")
                continue

        if done:
            break

    driver.quit()
    client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scraper_designbundles.py <page_number>")
        sys.exit(1)

    try:
        page_number = int(sys.argv[1])
    except ValueError:
        print("Page number must be an integer.")
        sys.exit(1)
    
    start_time = time.time()
    scrape_designbundles(page_number)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Total execution time: {elapsed_time//60} minutes")
