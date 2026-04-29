import os
import sys
import sqlite3
import requests
from dotenv import load_dotenv
import time
import traceback
import uuid
from logger import log


# Load environment variables from .env file
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)
DEZGO_API_KEY = os.getenv("DEZGO_API_KEY")

DB_PATH = os.path.join(os.path.dirname(__file__), "database-scraper.db")


def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
    table_exists = cursor.fetchone()

    if not table_exists:
        cursor.execute(
            """
            CREATE TABLE images (
                image_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                template_id INTEGER,
                converted INTEGER DEFAULT 0,
                title TEXT,
                prompt TEXT,
                description TEXT,
                tags TEXT,
                categories TEXT,
                kind TEXT,
                text_gen_flag BOOLEAN,
                input_tokens INTEGER,
                output_tokens INTEGER,
                spellchecked INTEGER,
                filename TEXT,
                thumbnail TEXT,
                wordpress_id INTEGER
            )
            """
        )
        conn.commit()
        log("Created images table", "info")
    else:
        log("images table already exists", "info")

    return conn


def get_image_templates(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT template_id, group_id, name, prompt, description, tags, kind, text_gen_flag FROM image_templates "
        "WHERE processed = 0"
    )
    entries = cursor.fetchall()

    return entries


def update_template_status(conn, template_id, status):
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE image_templates SET processed = ? WHERE template_id = ?", (status, template_id)
    )
    conn.commit()

    log(f"[update_template_status] Updated template status in images_template table: id = {template_id}, status = {status}", "info")


def insert_image_entry(
    conn,
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
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO images (group_id, template_id, title, prompt, description, tags, kind, text_gen_flag, filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            group_id,
            template_id,
            title,
            prompt,
            description,
            tags,
            kind,
            text_gen_flag,
            filename_without_extension
        ),
    )
    conn.commit()
    log(f"[insert_image_entry] Inserted new image entry in images table: template_id = {template_id}", "info")


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


def process_images(conn, group_number = 72):
    log("[process_images] Starting image processing", "info")
    
    image_templates = get_image_templates(conn)
    if not image_templates:
        log("[process_images] No entries to process. Exiting.", "info")
        return
    log(f"[process_images] Found {len(image_templates)} entries to process", "info")

    group_set = set()
    total_images = 0

    try:
        for entry in image_templates:
            log(f"[process_images] Processing entry: {entry}", "info")
            template_id, group_id, name, prompt, description, tags, kind, text_gen_flag = entry

            group_set.add(group_id)
            if len(group_set) > group_number:
                log(f"[process_images] Reached the desired group number. Exiting.", "info")
                break

            if "birth announcement" in prompt.lower():
                log(f"[process_images] Skipping entry with ID {template_id} due to 'birth announcement' in prompt", "info")
                update_template_status(conn, template_id, 2)
                continue
            
            prompt += " Use a pure white background."
            image_prompt = prompt
            log(f"[process_images] Generating dezgo image for prompt: {image_prompt}", "info")

            transparent = True if kind == "SVG" else False if kind == "Sublimation" else True
            image_data = generate_dezgo_image(image_prompt, transparent=transparent)

            if image_data:
                filename = str(uuid.uuid4().hex[:20])
                download_dezgo_image(image_data, group_id, filename + ".png")

                log(f"[process_images] Appending row to images table", "info")
                insert_image_entry(
                    conn,
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

                update_template_status(conn, template_id, 1)

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
    conn = setup_database()
    process_images(conn)
    end_time = time.time()
    elapsed_time = end_time - start_time
    log(f"[main] Total execution time: {elapsed_time//60} minutes", "info")
