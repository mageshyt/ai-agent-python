import tomli
import logging

from pathlib import Path
from typing import Any
from config.config import Config
from platformdirs import user_config_dir, user_data_dir
from lib import CONFIG_FILE_NAME, ConfigError , AGENT_MD_FILE_NAME , APP_NAME


logger = logging.getLogger(__name__)

def get_config_dir()-> Path:
    return Path(user_config_dir(appname=f".{APP_NAME}", appauthor="agent"))

def get_system_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME

def load_config(cwd: Path | None = None) -> Config:
    cwd = cwd if cwd else Path.cwd()
    system_path = get_system_config_path()
    config_dict : dict[str, Any] = {}

    # system level config
    if system_path.is_file():
        try:
            config_dict = _parse_config_file(system_path)
        except ConfigError as e:
            logger.error(f"Error loading config file: {e}")
            raise e
    # project level config - current working directory config

    project_config_path = _get_project_config(cwd)
    if project_config_path:
        try:
            project_config_dict = _parse_config_file(project_config_path)
            config_dict = _merge_configs(config_dict, project_config_dict)
        except ConfigError as e:
            logger.error(f"Error loading project config file: {e}")

    if "cwd" not in config_dict:
        config_dict["cwd"] = str(cwd)

    if "user_instructions" not in config_dict:
        config_dict["user_instructions"] = None

    else:
        # collect the agent.md file
        config_dict["user_instructions"] = _get_agent_md_files(cwd)


    # register mcp tools
    if "mcp_tools" not in config_dict:
        config_dict["mcp_tools"] = []

    try:
        config = Config(**config_dict)
        validation_errors = config.validate()
        if validation_errors:
            error_message = "Configuration validation failed:\n" + "\n".join(validation_errors)
            logger.error(error_message)
            raise ConfigError(error_message)
        return config
    except Exception as e:
        logger.error(f"Error creating Config object: {e}")
        raise ConfigError("Failed to create Config object", cause=e)



def _get_agent_md_files(cwd: Path) -> str | None:
    current = cwd.resolve()

    if current.is_dir():
        agent_md_path = current /AGENT_MD_FILE_NAME

        if agent_md_path.is_file():
            try :
                content = agent_md_path.read_text(encoding="utf-8")
                return content
            except (OSError, IOError) as e:
                logger.error(f"Failed to read {AGENT_MD_FILE_NAME} file: {e}")

    return None



def _merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two configuration dictionaries, with values from the override taking precedence.
     - If both values are dictionaries, merge them recursively.
     - Otherwise, the override value replaces the base value.
     - This allows for deep merging of nested configuration structures.
     - The function returns a new merged dictionary without modifying the original inputs.

    """
    merged = base.copy()
    for key , value in override.items():
        if key in merged and isinstance(merged[key],dict) and isinstance(value,dict):
            merged[key] = _merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged

def _parse_config_file(path: Path):
    try:
        with path.open("rb") as f:
            return tomli.load(f)

    except tomli.TOMLDecodeError as e:
        raise ConfigError("Failed to parse config file", config_file=str(path), cause=e)

    except (OSError, IOError) as e:
        raise ConfigError("Failed to read config file", config_file=str(path), cause=e)


def _get_project_config(cwd:Path) -> Path | None:
    current = cwd.resolve()
    agent_dir = current / ".cyberowl-agent"

    if agent_dir.is_dir():
        config_path = agent_dir / CONFIG_FILE_NAME
        if config_path.is_file():
            return config_path
    return None


def get_data_dir() -> Path:
    data_dir= Path(user_data_dir(appname=f".{APP_NAME}", appauthor="agent"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

