import logging
from colorama import init, Fore, Style
import os
import time
import logging


# Initialize colorama
init(autoreset=True)

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s [%(funcName)s] - %(message)s'
)

# Define color mappings
LOG_COLORS = {
    "INFO": Fore.GREEN,
    "ERROR": Fore.RED,
    "DEBUG": Fore.CYAN,
    "WARNING": Fore.YELLOW
}


class ColorFormatter(logging.Formatter):
    def format(self, record):
        log_color = LOG_COLORS.get(record.levelname, Fore.WHITE)
        record.msg = f"{log_color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


# Create a handler with the color formatter
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter('%(levelname)s [%(funcName)s] - %(message)s'))
logger = logging.getLogger()
logger.handlers = [handler]


def log(message, level="info"):
    if level == "info":
        logger.info(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)
    else:
        logger.warning(message)


def log_console(message, level="info"):
    log_color = LOG_COLORS.get(level.upper(), Fore.WHITE)
    if level == "info":
        print(f"{log_color}INFO: {message}{Style.RESET_ALL}")
    elif level == "error":
        print(f"{log_color}ERROR: {message}{Style.RESET_ALL}")
    elif level == "debug":
        print(f"{log_color}DEBUG: {message}{Style.RESET_ALL}")
    else:
        print(f"{log_color}WARNING: {message}{Style.RESET_ALL}")


def take_screenshot(driver, error_type):
    try:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        screenshot_dir = "error_screenshots"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
        screenshot_path = os.path.join(screenshot_dir, f"{error_type}_{timestamp}.png")
        driver.save_screenshot(screenshot_path)
        log(f"Screenshot saved: {screenshot_path}", "info")
    except Exception as e:
        log(f"Failed to take screenshot: {e}", "error")


def log_token_usage(group_id, input_tokens, output_tokens):
    log(f"Group ID: {group_id} - Input Tokens: {input_tokens}, Output Tokens: {output_tokens}", "info")
