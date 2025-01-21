import yaml
import os

CONFIG_FILE = "config.yaml"


def load_config(config_file=CONFIG_FILE):
    """
    Load the YAML configuration file.
    :param config_file: Path to the YAML file.
    :return: Dictionary containing the configuration.
    """
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    with open(config_file, "r") as file:
        config = yaml.safe_load(file)
    return config


# Load the entire configuration
CONFIG = load_config()

# Extract the API-specific settings
API_CONFIG = CONFIG.get("api", {})
SECRET_KEY = API_CONFIG.get("SECRET_KEY", "default-key")
API_HOST = API_CONFIG.get("API_HOST", "127.0.0.1")
API_PORT = API_CONFIG.get("API_PORT", 8000)
