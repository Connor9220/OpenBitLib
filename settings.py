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
