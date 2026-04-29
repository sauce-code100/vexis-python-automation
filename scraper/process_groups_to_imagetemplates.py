import sqlite3
import json
import os
import sys
import base64
import requests
from dotenv import load_dotenv
from pprint import pprint
import time


# This script reads the unprocessed entries from database-scraper.db and
# processes them by sending the group image and a big prompt to the LLM.
# It then writes the individual images' prompts into the image_templates table,
# setting the text_gen_flag based on the JSON response from the LLM.

# because of return token limits, the descriptions are not long enough so lets skip those
# and generate them bigger, later when we are writing product pages.

# processed of 2 means problematic json was returned.
# we will deal with this later.


# Add the parent directory to the sys.path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from logger import log, log_token_usage


# Load environment variables from .env file
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    log("OpenAI API Key not found in environment variables.", "error")
else:
    log(f"Using OpenAI API Key: {API_KEY[:5]}...{API_KEY[-5:]}", "info")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database-scraper.db")
PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), "scraper_prompt.txt")
IMAGE_FOLDER = os.path.join(os.path.dirname(__file__), "scraper_images")


def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if image_templates table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_templates'")
    table_exists = cursor.fetchone()

    if not table_exists:
        # Create image_templates table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE image_templates (
                template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                processed INTEGER DEFAULT 0,
                name TEXT,
                prompt TEXT,
                description TEXT,
                tags TEXT,
                categories TEXT,
                kind TEXT,
                text_gen_flag BOOLEAN,
                input_tokens INTEGER,
                output_tokens INTEGER
            )
            """
        )
        conn.commit()
        log("Created image_templates table in the database.", "info")
    else:
        log("image_templates table already exists in the database.", "info")

    return conn


def get_unprocessed_groups(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT group_id, title, kind, input_tokens, output_tokens FROM groups WHERE processed = 0"
    )
    return cursor.fetchall()


def update_group_status(conn, group_id, status, group_description=None, group_tags=None, input_tokens=None, output_tokens=None):
    cursor = conn.cursor()
    update_query = "UPDATE groups SET processed = ?"
    update_params = [status]

    if input_tokens is not None:
        update_query += ", input_tokens = ?"
        update_params.append(input_tokens)
    
    if output_tokens is not None:
        update_query += ", output_tokens = ?"
        update_params.append(output_tokens)
    
    if group_description is not None:
        update_query += ", description = ?"
        update_params.append(group_description)
    
    if group_tags is not None:
        update_query += ", tags = ?"
        update_params.append(group_tags)
    
    update_query += " WHERE group_id = ?"
    update_params.append(group_id)

    cursor.execute(update_query, tuple(update_params))
    conn.commit()


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def is_valid_json(response_text):
    try:
        json.loads(response_text)
        return True
    except json.JSONDecodeError:
        return False


def extract_json_content(response_text):
    # Extract JSON content from a string
    start_index = response_text.find("{")
    end_index = response_text.rfind("}")

    if start_index != -1 and end_index != -1:
        json_content = response_text[start_index : end_index + 1]
        return json_content

    log("No JSON content found in response text.", "error")
    return None


def construct_payload(group_title, prompt_template, base64_image):
    prompt = f"group image name: {group_title}\n{prompt_template}"
    return {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/webp;base64,{base64_image}",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 4000,
    }


def handle_response(
    conn,
    response,
    group_id,
    group_title,
    group_kind,
    input_tokens,
    output_tokens,
):
    response_text = response.text

    json_content = extract_json_content(response_text)
    if json_content is None:
        log(f"No JSON content found for Group {group_title} (ID: {group_id})", "error")
        update_group_status(conn, group_id, 2)
        return

    if not is_valid_json(json_content):
        log(f"Invalid JSON response for Group {group_title} (ID: {group_id})", "error")
        update_group_status(conn, group_id, 2)
        return

    try:
        response_data = json.loads(json_content)
    except json.JSONDecodeError as e:
        log(f"Error decoding JSON content: {e}", "error")
        log(f"Problematic JSON content: {json_content}", "error")
        update_group_status(conn, group_id, 2)
        return

    if "error" in response_data:
        log(f"OpenAI API error: {response_data['error']['message']}", "error")
        update_group_status(conn, group_id, 2)
        return

    # Extract the nested JSON content from the 'content' field
    nested_json_content = response_data["choices"][0]["message"]["content"]
    nested_json_content = extract_json_content(nested_json_content)
    log(f"Nested JSON content: {nested_json_content}", "info")

    try:
        nested_response_data = json.loads(nested_json_content)
    except json.JSONDecodeError as e:
        log(f"Error decoding nested JSON content: {e}", "error")
        log(f"Problematic nested JSON content: {nested_json_content}", "error")
        # update_group_status(conn, group_id, 2)
        return

    group_description = nested_response_data.get("group_description", "")
    group_tags = nested_response_data.get("group_tags", "")
    individual_prompts = nested_response_data.get("individual_prompts", [])

    log(f"Group Description: {group_description}", "info")
    log(f"Group Tags: {group_tags}", "info")
    log(f"Individual Prompts for Group {group_title} (ID: {group_id}): {individual_prompts}", "info")

    prompt_tokens = response_data.get("usage", {}).get("prompt_tokens", 0)
    completion_tokens = response_data.get("usage", {}).get("completion_tokens", 0)
    total_tokens = response_data.get("usage", {}).get("total_tokens", 0)

    input_tokens = input_tokens + prompt_tokens if input_tokens else prompt_tokens
    output_tokens = (
        output_tokens + completion_tokens if output_tokens else completion_tokens
    )

    log_token_usage(group_id, input_tokens, output_tokens)

    for i, prompt_data in enumerate(individual_prompts):
        log(f"Preparing to insert into image_templates for Group {group_title} (ID: {group_id})", "info")
        log(f"Prompt data: {prompt_data}", "info")
        insert_image_template(
            conn,
            group_id,
            prompt_data["name"],
            prompt_data["prompt"],
            prompt_data["description"],
            prompt_data["tags"],
            group_kind,
            prompt_data.get("text_gen_flag", 0)
        )
        log(f"Inserted new image template for Group {group_title} (ID: {group_id})", "info")

    update_group_status(conn, group_id, 1, group_description, group_tags, input_tokens, output_tokens)
    log(f"Marked Group {group_title} (ID: {group_id}) as processed", "info")


def insert_image_template(
    conn, group_id, name, prompt, description, tags, group_kind, text_gen_flag
):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO image_templates (group_id, name, prompt, description, tags, kind, text_gen_flag) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (group_id, name, prompt, description, tags, group_kind, text_gen_flag),
    )
    conn.commit()


def process_groups():
    # Read the prompt file once
    with open(PROMPT_FILE_PATH, "r") as file:
        prompt_template = file.read()

    conn = setup_database()
    unprocessed_groups = get_unprocessed_groups(conn)

    total_groups = len(unprocessed_groups)
    log(f"Total groups to process: {total_groups}", "info")

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

    for idx, (
        group_id,
        group_title,
        group_kind,
        input_tokens,
        output_tokens,
    ) in enumerate(unprocessed_groups, start=1):
        print("")
        log(f"Processing group {group_title} (ID: {group_id}) ({idx}/{total_groups})", "info")

        # Construct image file path
        group_id_str = str(group_id)
        subfolder = group_id_str[0]
        if subfolder.isdigit():
            image_file_path = os.path.join(
                IMAGE_FOLDER, subfolder, f"{group_id_str}.webp"
            )
        else:
            log(f"Invalid Group ID {group_id}, skipping image processing.", "error")
            update_group_status(conn, group_id, 2)
            continue

        log(f"Image file path: {image_file_path}", "info")

        try:
            base64_image = encode_image(image_file_path)
            log(f"Image data length: {len(base64_image)}", "info")
        except FileNotFoundError:
            log(f"Image file not found: {image_file_path}", "error")
            update_group_status(conn, group_id, 2)
            continue

        payload = construct_payload(group_title, prompt_template, base64_image)
        
        try:
            log(
                f"Sending request to OpenAI for image {group_title} (ID: {group_id})",
                "info",
            )
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            handle_response(
                conn,
                response,
                group_id,
                group_title,
                group_kind,
                input_tokens,
                output_tokens,
            )
        except requests.exceptions.RequestException as e:
            log(f"Request error for Group {group_title} (ID: {group_id}): {e}", "error")
        except Exception as e:
            log(f"Unexpected error for Group {group_title} (ID: {group_id}): {e}", "error")
    
    print("")
    log("Processing complete", "info")
    conn.close()


if __name__ == "__main__":
    start_time = time.time()
    process_groups()
    end_time = time.time()
    elapsed_time = end_time - start_time
    log(f"[main] Total execution time: {elapsed_time//60} minutes", "info")
