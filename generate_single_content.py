import os
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient
import json
from logger import log


# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path, override=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "designbundles_scraper")


def setup_database():
    """Connect to MongoDB and return client and db."""
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[MONGO_DB_NAME]
    log(f"Connected to MongoDB database '{MONGO_DB_NAME}'.", "info")
    return mongo_client, db


def get_images_to_regenerate(db):
    """Return all images where categories is None/null."""
    try:
        entries = list(db["images"].find(
            {"categories": None},
            {"_id": 1, "group_id": 1, "title": 1, "prompt": 1, "tags": 1, "kind": 1,
             "input_tokens": 1, "output_tokens": 1, "filename": 1, "thumbnail": 1},
        ))
    except Exception as e:
        log(f"Error querying images collection: {e}", "error")
        entries = []

    return entries


def regenerate_image_properties(title, prompt, tags, kind, categories_string):
    prompt = f"""
        Write a new product title, tags list, and product page description for a {kind} graphic
        with the name: '{title}',
        the tags of: '{tags}' and that was created with this prompt: '{prompt}'.
        Make a new unique title that describes what's in the image based on the prompt and make it compelling to view. Do not return the same thing that is in the current title. Do not use special characters so that it can be used as a filename.
        Create a new set of tags that are more relevant than the current tags but many more.
        Find up to 5 most relevant categories from the following list: {categories_string}. return them as ', ' separated string.
        Make the description long and explain how they might use it, giving them lots of suggestions to help sell it.
        Use emojis and make it fun, witty, cute and interesting.
        Use puns and other simple humor. Do not write about the tags or the prompt! return it as valid
        json with escaped newslines in the form: {{"title": "title", "description": "description", "tags": "tags", "categories": "categories"}} with no commentary.
    """

    log(f"Asking llm for updated description", "info")
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=2000
    )

    resp = response.choices[0].message.content.strip('"')
    log(f"Got answer from AI", "info")

    # Clean the response string
    if resp.startswith("```json"):
        resp = resp[7:]  # Remove the leading
    if resp.endswith("```"):
        resp = resp[:-3]  # Remove the trailing

    # Convert the response to a JSON object and extract title, description, tags, and categories
    try:
        json_response = json.loads(resp)
        title = json_response.get("title", "")
        description = json_response.get("description", "")
        tags = json_response.get("tags", "")
        categories = json_response.get("categories", "")
        log(f"Extracted title: {title}", "info")
        log(f"Extracted description: {description}", "info")
        log(f"Extracted tags: {tags}", "info")
        log(f"Extracted categories: {categories}", "info")

        # Extract token usage information
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        log(f"Token usage - Prompt tokens: {prompt_tokens}, Completion tokens: {completion_tokens}", "info")

        return title, description, tags, categories, prompt_tokens, completion_tokens

    except json.JSONDecodeError as e:
        log(f"Error decoding JSON response: {e}", "error")
        return None, None, None, None, 0, 0


def delete_image_from_database(db, image_id):
    """Delete an image document from the images collection."""
    try:
        db["images"].delete_one({"_id": image_id})
        log(f"Deleted image with ID {image_id} from images collection", "info")
    except Exception as e:
        log(f"Error deleting image with ID {image_id}: {e}", "error")


def update_product_info(db, image_id, new_title, new_description, new_tags, categories, prompt_tokens, completion_tokens):
    """Update product info fields on an image document."""
    try:
        db["images"].update_one(
            {"_id": image_id},
            {"$set": {
                "title": new_title,
                "description": new_description,
                "tags": new_tags,
                "categories": categories,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "filename": new_title,
            }},
        )
        log(f"Updated product info for image ID {image_id}", "info")
    except Exception as e:
        log(f"Error updating product info for image ID {image_id}: {e}", "error")


def generate_product_content(db, kind_for_processing="All"):
    images_to_regenerate = get_images_to_regenerate(db)
    log(f"Found {len(images_to_regenerate)} images to regenerate content", "info")

    categories_file_path = os.path.join(os.path.dirname(__file__), "categories.txt")
    try:
        with open(categories_file_path, 'r') as file:
            categories_list = [line.strip() for line in file if line.strip()]
        categories_string = ", ".join(categories_list)
        log(f"Categories loaded: {categories_string}", "info")
    except FileNotFoundError:
        log(f"Categories file not found at {categories_file_path}", "error")
        categories_string = ""
    except Exception as e:
        log(f"Error reading categories file: {e}", "error")
        categories_string = ""

    for doc in images_to_regenerate:
        image_id = doc["_id"]
        group_id = doc["group_id"]
        title = doc["title"]
        prompt = doc["prompt"]
        tags = doc["tags"]
        kind = doc["kind"]
        filename = doc["filename"]
        
        if kind != kind_for_processing and kind_for_processing != "All":
            continue

        new_title, new_description, new_tags, categories, prompt_tokens, completion_tokens = (
            regenerate_image_properties(
                title, prompt, tags, kind, categories_string
            )
        )
        
        if new_title:
            new_title = new_title.replace(': ', ' - ').replace(' | ', ' - ')
            old_path = os.path.join("images", str(group_id), f"{filename}.png")
            new_path = os.path.join("images", str(group_id), f"{new_title}.png")
            
            try:
                os.rename(old_path, new_path)
                log(f"Renamed file from {old_path} to {new_path}", "info")
                
                update_product_info(
                    db, image_id, new_title, new_description, new_tags,
                    categories, prompt_tokens, completion_tokens,
                )
            except OSError as e:
                log(f"Error renaming file {old_path}: {e}", "error")
                delete_image_from_database(db, image_id)
        else:
            log(f"Failed to update image {image_id}", "error")
            delete_image_from_database(db, image_id)


if __name__ == "__main__":
    mongo_client, db = setup_database()
    generate_product_content(db)
    mongo_client.close()
