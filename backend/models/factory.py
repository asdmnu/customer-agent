"""模型工厂。"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values, load_dotenv

from dashscope import TextEmbedding
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from backend.core.config import load_model_config
from backend.core.paths import get_abs_path


ENV_PATH = Path(get_abs_path(".env"))
load_dotenv(dotenv_path=ENV_PATH)
ENV_CONFIG = dotenv_values(ENV_PATH)
MODEL_CONFIG = load_model_config()


def get_required_env(key: str) -> str:
    """从项目 .env 中读取必填配置。"""
    value = ENV_CONFIG.get(key, "")
    if not value:
        raise ValueError(f".env 中缺少必填配置：{key}")
    return value


class DashScopeEmbeddings(Embeddings):
    """基于 DashScope 的向量模型封装。"""

    batch_size = 8

    def __init__(self, model: str):
        self.model = model
        self.api_key = get_required_env("DASHSCOPE_API_KEY")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = TextEmbedding.call(
                model=self.model,
                input=batch,
                api_key=self.api_key,
            )
            if not getattr(response, "output", None) or not response.output.get("embeddings"):
                raise ValueError("DashScope 向量接口返回为空")
            embeddings.extend(item["embedding"] for item in response.output["embeddings"])
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        embeddings = self.embed_documents([text])
        return embeddings[0] if embeddings else []


class BaseModelFactory(ABC):
    """模型工厂基类。"""

    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成模型实例。"""


class ChatModelFactory(BaseModelFactory):
    """聊天模型工厂。"""

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return ChatTongyi(
            model=MODEL_CONFIG["chat_model_name"],
            streaming=True,
            dashscope_api_key=get_required_env("DASHSCOPE_API_KEY"),
        )


class EmbedderFactory(BaseModelFactory):
    """向量模型工厂。"""

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=MODEL_CONFIG["embedding_model_name"])


chat_model = ChatModelFactory().generator()
embed_model = EmbedderFactory().generator()


def get_chat_model() -> BaseChatModel:
    """获取聊天模型实例。"""
    return chat_model


def get_embedding_model() -> Embeddings:
    """获取向量模型实例。"""
    return embed_model
