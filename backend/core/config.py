"""配置加载工具。"""

import os
from pathlib import Path

import yaml

from backend.core.paths import get_abs_path


def _load_yaml_config(config_path: str, encoding: str = "utf-8"):
    with open(config_path, "r", encoding=encoding) as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def load_model_config(
    config_path: str = get_abs_path("backend/config/models.yml"),
    encoding: str = "utf-8",
):
    return _load_yaml_config(config_path, encoding)


def load_prompt_config(
    config_path: str = get_abs_path("backend/config/prompts.yml"),
    encoding: str = "utf-8",
):
    return _load_yaml_config(config_path, encoding)


def load_rag_config(
    config_path: str = get_abs_path("backend/config/rag.yml"),
    encoding: str = "utf-8",
):
    return _load_yaml_config(config_path, encoding)


def load_postgres_config(
    config_path: str = get_abs_path("backend/config/postgres.yml"),
    encoding: str = "utf-8",
):
    config = _load_yaml_config(config_path, encoding)
    env_overrides = {
        "host": os.getenv("POSTGRES_HOST"),
        "port": os.getenv("POSTGRES_PORT"),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "table_name": os.getenv("PGVECTOR_TABLE_NAME"),
        "embedding_dimension": os.getenv("EMBEDDING_DIMENSION"),
        "distance_strategy": os.getenv("PGVECTOR_DISTANCE_STRATEGY"),
        "fts_regconfig": os.getenv("PGVECTOR_FTS_REGCONFIG"),
        "vector_search_k": os.getenv("PGVECTOR_VECTOR_SEARCH_K"),
        "keyword_search_k": os.getenv("PGVECTOR_KEYWORD_SEARCH_K"),
        "hybrid_top_k": os.getenv("PGVECTOR_HYBRID_TOP_K"),
        "rrf_k": os.getenv("PGVECTOR_RRF_K"),
    }
    for key, value in env_overrides.items():
        if value not in (None, ""):
            config[key] = value
    return config


def _load_prompt(path_key: str) -> str:
    prompt_config = load_prompt_config()
    prompt_path = Path(get_abs_path(prompt_config[path_key]))
    return prompt_path.read_text(encoding="utf-8")


def load_classifier_prompt() -> str:
    return _load_prompt("classifier_prompt_path")


def load_answer_prompt() -> str:
    return _load_prompt("answer_prompt_path")


def load_action_system_prompt() -> str:
    return _load_prompt("action_system_prompt_path")


def load_action_category_classifier_prompt() -> str:
    return _load_prompt("action_category_classifier_prompt_path")
