"""
This module contains functions to load the configuration file.
"""
import tomllib
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config.toml"


def load_config(config_file: str | Path = CONFIG_FILE) -> dict:
    # Reads the Configuration file and return the content as Dictionary.
    toml_dict = {}

    with open(config_file, "rb") as f:
        try:
            toml_dict = tomllib.load(f)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"Invalid configuration file: {config_file}") from error
    return toml_dict
