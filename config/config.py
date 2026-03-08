import os
from pydantic import BaseModel, Field
from pathlib import Path
import dotenv

dotenv.load_dotenv()


class ModelConfig(BaseModel):
    name: str = "arcee-ai/trinity-large-preview:free" # NOTE:default model
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="Sampling temperature for the model, between 0 and 1")
    context_window: int  = 128_000 


class Config(BaseModel):
    model:ModelConfig = Field(default_factory=ModelConfig)
    cwd : Path = Field(default_factory=Path.cwd)
    max_turns : int = 100
    max_tool_output_tokens : int = 50_000

    user_instructions:str | None = None
    debug: bool = False


    @property
    def get_api_key(self) -> str | None:
        return os.getenv("API_KEY")

    @property
    def get_base_url(self) -> str | None:
        return os.getenv("BASE_URL")

    @property
    def get_model_name(self) -> str:
        return self.model.name

    @property
    def get_temperature(self) -> float:
        return self.model.temperature

    @get_model_name.setter
    def set_model_name(self, name:str) -> None:
        self.model.name = name

    @get_temperature.setter
    def set_temperature(self, temperature:float) -> None:
        if 0.0 <= temperature <= 1.0:
            self.model.temperature = temperature
        else:
            raise ValueError("Temperature must be between 0 and 1")


    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.get_api_key:
            errors.append("API_KEY environment variable is not set")

        if not self.get_base_url:
            errors.append("BASE_URL environment variable is not set")

        if not self.cwd.exists() or not self.cwd.is_dir():
            errors.append(f"CWD path '{self.cwd}' does not exist or is not a directory")

        return errors
