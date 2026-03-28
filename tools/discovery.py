import importlib.util
import inspect
import sys
import logging

from pathlib import Path
from typing import Any, List
from config.config import Config
from config.loader import get_config_dir
from lib.constants import APP_NAME
from tools import ToolRegistry, Tool

logger = logging.getLogger(__name__)


class ToolDiscoveryManger:
    def __init__(self,config:Config,registry:ToolRegistry) -> None:
        self.config = config
        self.registry = registry


    def discover_all(self)->None:
        self.discover_from_directory(self.config.cwd)
        self.discover_from_directory(get_config_dir())

    
    def discover_from_directory(self,directory:Path)->None:
        tool_dir = directory / f".{APP_NAME}" / "tools"

        if not tool_dir.exists() or not tool_dir.is_dir():
            logger.info(f"No tools directory found at {tool_dir}, skipping tool discovery.")
            return

        for py_file in tool_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue

            # load the module and find tool classes
            try:
                module = self._load_tool_modules(py_file)
                tool_classes = self._find_tool_classes(module)
                if not tool_classes:
                    logger.info(f"No tool classes found in {py_file}, skipping.")
                    continue

                for tool_class in tool_classes:
                    tool = tool_class(self.config) # type: ignore
                    self.registry.register_tool(tool)
                    logger.info(f"Discovered and registered tool: {tool_class.__name__} from {py_file}")
            except Exception as e:
                logger.error(f"Error loading tools from {py_file}: {e}")




    def _load_tool_modules(self,file_path:Path)->Any:
        module_name = f"discovered_tool {file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            raise ImportError(f"Could not load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore
        return module


    def _find_tool_classes(self,module:Any)->List[Tool]:
        tools:List[Tool] = []

        for name in dir(module):
            obj = getattr(module, name)
            
            if (
                inspect.isclass(obj) and
                issubclass(obj, Tool) and
                obj.__module__ == module.__name__ and # ensure the class is defined in the module, not imported
                obj is not Tool
                ):

                tools.append(obj) # type: ignore

        return tools

if __name__ == "__main__":
    from config.loader import load_config

    config = load_config()
    registry = ToolRegistry(config)
    discovery_manager = ToolDiscoveryManger(config,registry)
    discovery_manager.discover_all()
    print(f"Discovered tools: {registry.get_tools()}")

