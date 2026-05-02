import os
import zipfile
from openai import OpenAI
from pymongo import MongoClient
from dotenv import load_dotenv
from logger import log
from wordpress_utils import upload_image_to_wordpress, create_edd_product


# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path, override=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "designbundles_scraper")


def setup_database():
    """Connect to MongoDB and return client and database references."""
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[MONGO_DB_NAME]
    log(f"Connected to MongoDB database '{MONGO_DB_NAME}'.", "info")
    return mongo_client, db


def get_images_to_upload(db):
    """Fetch images that have a thumbnail and no wordpress_id yet."""
    try:
        entries = list(db["images"].find({
            "thumbnail": {"$nin": [None, "missing"]},
            "wordpress_id": None
        }))
    except Exception as e:
        log(f"Error querying images collection: {e}", "error")
        entries = []

    return entries


def delete_image_from_database(db, image_id):
    """Delete an image document from the images collection."""
    try:
        db["images"].delete_one({"_id": image_id})
        log(f"Deleted image with ID {image_id} from MongoDB", "info")
    except Exception as e:
        log(f"Error deleting image with ID {image_id}: {e}", "error")


def update_wordpress_id(db, image_id, wordpress_id):
    """Update the wordpress_id field on an image document."""
    try:
        db["images"].update_one(
            {"_id": image_id},
            {"$set": {"wordpress_id": wordpress_id}}
        )
        log(f"Updated WordPress ID for image ID {image_id} to {wordpress_id}", "info")
    except Exception as e:
        log(f"Error updating WordPress ID for image ID {image_id}: {e}", "error")


def process_single_products(db, kind_for_processing="SVG"):
    images_to_upload = get_images_to_upload(db)
    log(f"Found {len(images_to_upload)} images to upload to WordPress", "info")

    for entry in images_to_upload:
        image_id = entry["_id"]
        group_id = entry["group_id"]
        title = entry["title"]
        prompt = entry["prompt"]
        description = entry["description"]
        tags = entry["tags"]
        categories = entry.get("categories")
        kind = entry["kind"]
        filename = entry["filename"]
        thumbnail = entry["thumbnail"]

        if kind != kind_for_processing and kind_for_processing != "All":
            continue

        try:
            log(f"Uploading thumbnail {filename} to WordPress", "info")
            thumbnail_path = f"images/{group_id}/{thumbnail}"

            if not os.path.exists(thumbnail_path):
                log(f"Thumbnail not found at path: {thumbnail_path}", "error")
                update_wordpress_id(db, image_id, -1)
                continue

            thumbnail_url = upload_image_to_wordpress(thumbnail_path)
            if thumbnail_url is not None:
                log(f"Thumbnail uploaded: {thumbnail_url}", "info")
            else:
                log("Thumbnail not uploaded", "error")
                update_wordpress_id(db, image_id, -1)
                continue

            log(f"Uploading download files {filename} to WordPress", "info")
            if kind == "SVG":
                extensions = ["SVG", "PNG", "EPS", "DXF"]
            else:
                extensions = ["PNG"]
            
            zip_filename = f"{filename}.zip"
            zip_path = f"images/{group_id}/{zip_filename}"

            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                for ext in extensions:
                    image_path = f"images/{group_id}/{filename}.{ext.lower()}"
                    if os.path.exists(image_path):
                        zip_file.write(image_path, f"{filename}.{ext.lower()}")
                        log(f"Added {ext} image to zip file", "info")
                    else:
                        log(f"{ext} image not found at path: {image_path}", "error")
            
            zip_url = upload_image_to_wordpress(zip_path)
            if zip_url is not None:
                download_files = [zip_url]
                log(f"Zip file uploaded: {zip_url}", "info")
            else:
                log("Zip file not uploaded", "error")
                update_wordpress_id(db, image_id, -1)
                continue

            log(f"Creating EDD product for image {filename}", "info")
            wordpress_id = create_edd_product(
                title, description, thumbnail_url, tags, categories=categories, product_kind=kind, product_type="single", edd_product_type="single", product_info=download_files, extensions=", ".join(extensions)
            )
            if wordpress_id:
                update_wordpress_id(db, image_id, wordpress_id)
                log(f"Uploaded image {filename} to WordPress with ID {wordpress_id}", "info")
            else:
                log(f"Failed to upload image {filename} to WordPress", "error")
                update_wordpress_id(db, image_id, -1)
        except Exception as e:
            log(f"Failed to upload image {filename} to WordPress: {e}", "error")
            update_wordpress_id(db, image_id, -1)
        break


if __name__ == "__main__":
    mongo_client, db = setup_database()
    process_single_products(db, "All")
    mongo_client.close()
