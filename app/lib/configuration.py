import tomli
import os

directory = os.getcwd()
CONFIG_FILE = f"{directory}/config.toml"


def load_config(config_file: str = CONFIG_FILE) -> dict:
    # Reads the Configuration file and return the content as Dictionary.
    toml_dict = {}

    with open(config_file, "rb") as f:
        try:
            toml_dict = tomli.load(f)
        except tomli.TOMLDecodeError:
            print("Invalid configuration file. Please check TOML Synthax.")
            exit()
    return toml_dict
