import os
import sys
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
import time
import traceback
import uuid
from logger import log


# Load environment variables from .env file
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)
DEZGO_API_KEY = os.getenv("DEZGO_API_KEY")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "designbundles_scraper")


def setup_database():
    """Connect to MongoDB and ensure the images collection has indexes."""
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]

    # Ensure images collection exists with useful indexes
    images = db["images"]
    images.create_index("group_id")
    images.create_index("template_id")
    log(f"Connected to MongoDB database '{MONGO_DB_NAME}'.", "info")

    return client, db


def get_image_templates(db):
    """Return all image_templates with processed == 0."""
    return list(db["image_templates"].find(
        {"processed": 0},
        {"_id": 1, "group_id": 1, "name": 1, "prompt": 1, "description": 1, "tags": 1, "kind": 1, "text_gen_flag": 1},
    ))


def update_template_status(db, template_id, status):
    """Update the processed field on an image_template document."""
    db["image_templates"].update_one(
        {"_id": template_id},
        {"$set": {"processed": status}},
    )
    log(f"[update_template_status] Updated template status in image_templates collection: id = {template_id}, status = {status}", "info")


def insert_image_entry(
    db,
    group_id,
    template_id,
    title,
    prompt,
    description,
    tags,
    kind,
    text_gen_flag,
    filename_without_extension
):
    """Insert a new document into the images collection."""
    db["images"].insert_one({
        "group_id": group_id,
        "template_id": template_id,
        "converted": 0,
        "title": title,
        "prompt": prompt,
        "description": description,
        "tags": tags,
        "categories": None,
        "kind": kind,
        "text_gen_flag": text_gen_flag,
        "input_tokens": None,
        "output_tokens": None,
        "spellchecked": None,
        "filename": filename_without_extension,
        "thumbnail": None,
        "wordpress_id": None,
    })
    log(f"[insert_image_entry] Inserted new image entry in images collection: template_id = {template_id}", "info")


def generate_dezgo_image(prompt, width=1024, height=1024, transparent=True, format="png"):
    url = "https://api.dezgo.com/text2image_flux"
    
    headers = {
        'X-Dezgo-Key': DEZGO_API_KEY,
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'prompt': prompt,
        'width': width,
        'height': height,
        'transparent_background': transparent,
        'format': format
    }

    try:
        log(f"[generate_dezgo_image] Sending request to Dezgo API", "info")
        response = requests.post(url, headers=headers, data=data)
        
        if response.status_code == 200:
            log(f"[generate_dezgo_image] Successfully generated image", "info")
            return response.content
        else:
            log(f"[generate_dezgo_image] Failed to generate image. Status code: {response.status_code}", "error")
            log(f"[generate_dezgo_image] Response: {response.text}", "error")
            return None
            
    except Exception as e:
        log(f"[generate_dezgo_image] Error generating image: {str(e)}", "error")
        return None


def download_dezgo_image(image_data, group_id, filename):
    try:
        images_folder = "images"
        if not os.path.exists(images_folder):
            os.makedirs(images_folder)
            log(f"[download_folder_images] Created images folder: {images_folder}", "info")
        
        group_subfolder = os.path.join(images_folder, str(group_id))
        if not os.path.exists(group_subfolder):
            os.makedirs(group_subfolder)
            log(f"[download_folder_images] Created group subfolder: {group_subfolder}", "info")
        
        image_path = os.path.join(group_subfolder, filename)
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        log(f"[download_dezgo_image] Successfully saved image to {image_path}", "info")
        return True
        
    except Exception as e:
        log(f"[download_dezgo_image] Error saving image: {str(e)}", "error")
        return False


def process_images(db, group_number = 72):
    log("[process_images] Starting image processing", "info")
    
    image_templates = get_image_templates(db)
    if not image_templates:
        log("[process_images] No entries to process. Exiting.", "info")
        return
    log(f"[process_images] Found {len(image_templates)} entries to process", "info")

    group_set = set()
    total_images = 0

    try:
        for doc in image_templates:
            log(f"[process_images] Processing entry: {doc}", "info")
            template_id = doc["_id"]
            group_id = doc["group_id"]
            name = doc["name"]
            prompt = doc["prompt"]
            description = doc["description"]
            tags = doc["tags"]
            kind = doc["kind"]
            text_gen_flag = doc["text_gen_flag"]

            group_set.add(group_id)
            if len(group_set) > group_number:
                log(f"[process_images] Reached the desired group number. Exiting.", "info")
                break

            if "birth announcement" in prompt.lower():
                log(f"[process_images] Skipping entry with ID {template_id} due to 'birth announcement' in prompt", "info")
                update_template_status(db, template_id, 2)
                continue
            
            prompt += " Use a pure white background."
            image_prompt = prompt
            log(f"[process_images] Generating dezgo image for prompt: {image_prompt}", "info")

            transparent = True if kind == "SVG" else False if kind == "Sublimation" else True
            image_data = generate_dezgo_image(image_prompt, transparent=transparent)

            if image_data:
                filename = str(uuid.uuid4().hex[:20])
                download_dezgo_image(image_data, group_id, filename + ".png")

                log(f"[process_images] Appending document to images collection", "info")
                insert_image_entry(
                    db,
                    group_id,
                    template_id,
                    name,
                    prompt,
                    description,
                    tags,
                    kind,
                    text_gen_flag,
                    filename
                )
                total_images += 1

                update_template_status(db, template_id, 1)

    except SystemExit as e:
        log(f"[process_images] SystemExit: {str(e)}", "error")
        sys.exit(1)
    except Exception as e:
        log(f"[process_images] Unexpected error: {str(e)}", "error")
        log(f"Traceback: {traceback.format_exc()}", "error")
        sys.exit(1)

    log(f"[process_images] Image processing complete: {total_images} images generated", "info")


if __name__ == "__main__":
    start_time = time.time()
    client, db = setup_database()
    process_images(db)
    client.close()
    end_time = time.time()
    elapsed_time = end_time - start_time
    log(f"[main] Total execution time: {elapsed_time//60} minutes", "info")
