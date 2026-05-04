import os
from dotenv import load_dotenv
from pymongo import MongoClient
from PIL import Image
from logger import log
import numpy as np
import subprocess
import time


# Load environment variables from .env file
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "designbundles_scraper")


def setup_database():
    """Connect to MongoDB and return client and db."""
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    log(f"Connected to MongoDB database '{MONGO_DB_NAME}'.", "info")
    return client, db


def convert_image_to_transparent_png(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        log(f"[convert_utils.preprocess_webp_to_transparent_png] {filename} -> Transparent PNG (starting)", "info")

        img = Image.open(source_filepath)

        # Convert to RGBA if not already
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        img_array = np.array(img)
        mask = (img_array[:,:,:3] > 200).all(axis=2)
        img_array[mask, 3] = 0
        img = Image.fromarray(img_array)

        # Prepare output filepath
        output_filepath = os.path.join(
            os.path.dirname(source_filepath),
            os.path.splitext(filename)[0] + ".png"
        )

        # Save as PNG
        img.save(output_filepath, "PNG")

        log(f"{filename} -> Transparent PNG (success)", "info")
        return output_filepath
    except Exception as e:
        log(f"{filename} -> Transparent PNG (failed): {str(e)}", "error")
        return None


def convert_image_to_svg(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        log(f"[convert_utils.convert_image_to_svg] {filename} -> SVG (starting)", "info")

        # Call the vectorizer script using node
        result = subprocess.run(
            ["node", "./vectorizer/convert_image_to_svg.mjs", source_filepath],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log(f"{filename} -> SVG (failed): {result.stderr}", "error")
            raise Exception(result.stderr)

        log(f"{filename} -> SVG (success)", "info")
        return result.stdout.strip()  # Assuming the script outputs the path to the SVG file
    except Exception as e:
        log(f"{filename} -> SVG (failed): {str(e)}", "error")
        return None


def convert_image_to_jpg(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        log(f"[convert_utils.convert_image_to_jpg] {filename} -> JPG (starting)", "info")

        output_filepath = os.path.join(
            os.path.dirname(source_filepath), os.path.splitext(filename)[0] + ".jpg"
        )

        img = Image.open(source_filepath)

        # Convert to RGB mode if the image is in RGBA mode
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        img.save(output_filepath, "JPEG")

        log(f"{filename} -> JPG (success)", "info")
        return output_filepath
    except Exception as e:
        log(f"{filename} -> JPG (failed): {str(e)}", "error")
        return None


def convert_image_to_png(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        log(f"[convert_utils.convert_image_to_png] {filename} -> PNG (starting)", "info")

        output_filepath = os.path.join(
            os.path.dirname(source_filepath), os.path.splitext(filename)[0] + ".png"
        )

        img = Image.open(source_filepath)
        img.save(output_filepath, "PNG")

        log(f"{filename} -> PNG (success)", "info")
        return output_filepath
    except Exception as e:
        log(f"{filename} -> PNG (failed): {str(e)}", "error")
        return None


def convert_svg_to_png(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        log(f"[convert_utils.convert_svg_to_png] {filename} -> PNG (starting)", "info")

        output_filepath = os.path.join(
            os.path.dirname(source_filepath), os.path.splitext(filename)[0] + ".png"
        )

        # Use Inkscape to convert SVG to PNG
        result = subprocess.run(
            ["inkscape", source_filepath, "--export-filename", output_filepath],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log(f"{filename} -> PNG (failed): {result.stderr}", "error")
            raise Exception(result.stderr)

        log(f"{filename} -> PNG (success)", "info")
        return output_filepath
    except Exception as e:
        log(f"{filename} -> PNG (failed): {str(e)}", "error")
        return None


def convert_svg_to_eps(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        filename_without_extension = os.path.splitext(filename)[0]
        svg_filepath = source_filepath
        output_filepath = os.path.join(os.path.dirname(source_filepath), filename_without_extension + ".eps")
        
        log(f"[convert_utils.convert_svg_to_eps] svg filepath: {svg_filepath} -> EPS (starting)", "info")
        log(f"[convert_utils.convert_svg_to_eps] Running Inkscape command: {'inkscape', svg_filepath, '--export-filename', output_filepath}", "info")
        
        result = subprocess.run(
            ["inkscape", svg_filepath, "--export-filename", output_filepath],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log(f"{filename} -> EPS (failed): {result.stderr}", "error")
            raise Exception(result.stderr)
        
        log(f"{filename} -> EPS (success)", "info")
        return output_filepath
    except Exception as e:
        log(f"{filename} -> EPS (failed): {str(e)}", "error")
        return None


def convert_svg_to_dxf(source_filepath):
    try:
        filename = os.path.basename(source_filepath)
        filename_without_extension = os.path.splitext(filename)[0]
        svg_filepath = source_filepath
        output_filepath = os.path.join(os.path.dirname(source_filepath), filename_without_extension + ".dxf")
        
        log(f"[convert_utils.convert_svg_to_dxf] svg filepath: {svg_filepath} -> DXF (starting)", "info")
        log(f"[convert_utils.convert_svg_to_dxf] Running Inkscape command: {'inkscape', svg_filepath, '--export-filename', output_filepath}", "info")
        
        result = subprocess.run(
            ["inkscape", svg_filepath, "--export-filename", output_filepath],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log(f"{filename} -> DXF (failed): {result.stderr}", "error")
            raise Exception(result.stderr)
        
        log(f"{filename} -> DXF (success)", "info")
        return output_filepath
    except Exception as e:
        log(f"{filename} -> DXF (failed): {str(e)}", "error")
        return None


def convert_images_for_svg_kind(source_filepath):
    # Transparent PNG conversion
    transparent_png_filepath = convert_image_to_transparent_png(source_filepath)
    if not transparent_png_filepath:
        return False

    # SVG conversion
    svg_filepath = convert_image_to_svg(transparent_png_filepath)
    if not svg_filepath:
        return False
    svg_filepath = os.path.splitext(source_filepath)[0] + ".svg"

    # EPS conversion
    eps_filepath = convert_svg_to_eps(svg_filepath)
    if not eps_filepath:
        return False

    # DXF conversion
    dxf_filepath = convert_svg_to_dxf(svg_filepath)
    if not dxf_filepath:
        return False
    
    return True


def convert_images_for_sublimation_kind(source_filepath):
    return True


def process_unconverted_images(db, kind_for_processing="SVG"):
    """Find unconverted images and run the appropriate conversion pipeline."""
    images_col = db["images"]

    unconverted_images = list(images_col.find(
        {"converted": 0, "categories": {"$ne": None}},
        {"_id": 1, "group_id": 1, "filename": 1, "kind": 1},
    ))
    log(f"[convert_utils.process_unconverted_images] {len(unconverted_images)} unconverted images found", "info")

    for doc in unconverted_images:
        image_id = doc["_id"]
        group_id = doc["group_id"]
        filename = doc["filename"]
        kind = doc["kind"]

        if kind != kind_for_processing and kind_for_processing != "All":
            continue
        source_filepath = os.path.join("images", f"{group_id}", f"{filename}.png")

        if not os.path.exists(source_filepath):
            images_col.update_one({"_id": image_id}, {"$set": {"converted": 2}})
            log(f"[process_unconverted_images] Image not found: {source_filepath}", "error")
            continue

        image = Image.open(source_filepath)
        image = image.convert("RGB")
        pixel_value1 = image.getpixel((100, 100))
        pixel_value2 = image.getpixel((500, 500))
        pixel_value3 = image.getpixel((1000, 1000))

        if pixel_value1 == (85, 129, 128) and pixel_value2 == (192, 197, 193) and pixel_value3 == (113, 157, 144):
            images_col.update_one({"_id": image_id}, {"$set": {"converted": 2}})
            log(f"[process_unconverted_images] Image is not safe: {source_filepath}", "error")
            continue

        if kind == "SVG":
            conversion_result = convert_images_for_svg_kind(source_filepath)
        elif kind == "Sublimation":
            conversion_result = convert_images_for_sublimation_kind(source_filepath)
        else:
            conversion_result = False
            log(f"[process_unconverted_images] Unknown kind: {kind}", "error")

        if conversion_result:
            images_col.update_one({"_id": image_id}, {"$set": {"converted": 1}})
        else:
            images_col.update_one({"_id": image_id}, {"$set": {"converted": 2}})


if __name__ == "__main__":
    start_time = time.time()
    mongo_client, db = setup_database()
    process_unconverted_images(db, "All")
    mongo_client.close()
    end_time = time.time()
    elapsed_time = end_time - start_time
    log(f"[main] Total execution time: {elapsed_time//60} minutes", "info")
