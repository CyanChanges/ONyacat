#  Copyright (c) Cyan Changes 2024. All rights reserved.

import os
import rtoml
from pathlib import Path
from typing import Any, Dict, Literal, Tuple, Type, Optional

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SecretsSettingsSource,
    SettingsConfigDict,
)

from config import ServerConfig, CSharpConfig, ClientConfig


class LogSection(BaseModel):
    level: Literal["debug", "info", "error", "warn", "notset"] = "info"
    as_json: bool = False


class TOMLConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(
            self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        # This is not necessary for TOML, but the current implementation
        # of PydanticBaseSettingsSource requires it. In case it becomes relevant,
        # we only raise an error to notice it.
        raise NotImplementedError

    def __call__(self) -> Dict[str, Any]:
        toml_file = os.getenv("CLI_CONFIG")
        if not toml_file:
            toml_file = self.config.get("toml_file")
        if not Path(toml_file).exists():
            return {}
        encoding = self.config.get("env_file_encoding")
        return rtoml.loads(Path(toml_file).read_text(encoding=encoding))


class Config(BaseSettings):
    server: Optional[ServerConfig] = None
    csharp: Optional[CSharpConfig] = None
    client: Optional[ClientConfig] = None


class Settings(Config):
    log: LogSection = LogSection(level="info", as_json=False)

    def __init__(self, config_path: Path, *args: Any, **kwargs):
        self.model_config["toml_file"] = config_path
        super().__init__(*args, **kwargs)

    model_config = SettingsConfigDict(
        env_prefix="ONYACAT_",
        env_nested_delimiter="_",
        env_file_encoding="utf-8"
    )

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: Type[BaseSettings],
            init_settings: InitSettingsSource,
            env_settings: EnvSettingsSource,
            dotenv_settings: DotEnvSettingsSource,
            file_secret_settings: SecretsSettingsSource,
    ) -> Tuple[
        InitSettingsSource,
        EnvSettingsSource,
        DotEnvSettingsSource,
        TOMLConfigSettingsSource,
        SecretsSettingsSource,
    ]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TOMLConfigSettingsSource(settings_cls),
            file_secret_settings,
        )
