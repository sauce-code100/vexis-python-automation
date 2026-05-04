import os
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from logger import log


# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path, override=True)
SWITCHBOARD_API_KEY = os.getenv("SWITCHBOARD_API_KEY")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "designbundles_scraper")


def setup_database():
    """Connect to MongoDB and return client and database references."""
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[MONGO_DB_NAME]
    log(f"Connected to MongoDB database '{MONGO_DB_NAME}'.", "info")
    return mongo_client, db


def get_images_with_null_thumbnail(db):
    """Fetch images that are converted but have no thumbnail yet."""
    try:
        results = list(db["images"].find(
            {"converted": 1, "thumbnail": None},
            {"_id": 1, "group_id": 1, "title": 1, "kind": 1, "filename": 1}
        ))
    except Exception as e:
        log(f"Error querying images collection: {e}", "error")
        results = []
    return results


def generate_single_thumbnail(group_id, title, kind, filename):
    url = "https://api.canvas.switchboard.ai"
    headers = {
        "X-API-Key": SWITCHBOARD_API_KEY,
        "Content-Type": "application/json"
    }

    if kind == "SVG":
        payload = {
            "template": "single-svg",
            "sizes": [
                {
                    "width": 1500,
                    "height": 1000
                }
            ],
            "elements": {
                "image": {
                    "url": f"https://lawlike-xavier-fiftypenny.ngrok-free.dev/images/{group_id}/{filename.replace(' ', '%20')}.png"
                },
                "extension": {
                    "text": "SVG PNG EPS DXF"
                },
            }
        }
    else:
        payload = {
            "template": "single-sublimation",
            "sizes": [
                {
                    "width": 1500,
                    "height": 1000
                }
            ],
            "elements": {
                "image": {
                    "url": f"https://lawlike-xavier-fiftypenny.ngrok-free.dev/images/{group_id}/{filename.replace(' ', '%20')}.png"
                },
                "title": {
                    "text": "SUBLIMATION PNG DIGITAL DESIGN"
                },
            }
        }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        thumbnail_data = response.json()
        thumbnail_url = thumbnail_data['sizes'][0]['url']  # Get the thumbnail URL
        log(f"Generated thumbnail: {thumbnail_url}", "info")
        
        # Download the thumbnail image
        thumbnail_response = requests.get(thumbnail_url)
        if thumbnail_response.status_code == 200:
            thumbnail_path = os.path.join("images", str(group_id), f"{filename} - thumbnail.png")
            with open(thumbnail_path, 'wb') as f:
                f.write(thumbnail_response.content)
            return thumbnail_path
        else:
            log(f"Error downloading thumbnail: {thumbnail_response.text}", "error")
            return None
    else:
        log(f"Error generating thumbnail: {response.text}", "error")
        return None


def update_thumbnail(db, image_id, thumbnail_path):
    """Update the thumbnail field on an image document."""
    try:
        db["images"].update_one(
            {"_id": image_id},
            {"$set": {"thumbnail": thumbnail_path}}
        )
        log(f"Updated thumbnail for image {image_id}", "info")
    except Exception as e:
        log(f"Error updating thumbnail: {e}", "error")


def process_single_thumbnails(db, kind_for_processing="SVG"):
    images = get_images_with_null_thumbnail(db)
    log(f"Found {len(images)} images for thumbnail generation", "info")
    for entry in images:
        image_id = entry["_id"]
        group_id = entry["group_id"]
        title = entry["title"]
        kind = entry["kind"]
        filename = entry["filename"]

        if kind != kind_for_processing and kind_for_processing != "All":
            continue
        log(f"Processing image {image_id} to generate thumbnail", "info")

        png_path = os.path.join("images", str(group_id), f"{filename}.png")
        if not os.path.exists(png_path):
            log(f"PNG file not found: {png_path}", "error")
            update_thumbnail(db, image_id, "missing")
            continue
        thumbnail_path = generate_single_thumbnail(group_id, title, kind, filename)
        if thumbnail_path:
            update_thumbnail(db, image_id, f"{filename} - thumbnail.png")
        else:
            log("Please check switchboard api status", "error")
            break


if __name__ == "__main__":
    mongo_client, db = setup_database()
    process_single_thumbnails(db, "All")
    mongo_client.close()
