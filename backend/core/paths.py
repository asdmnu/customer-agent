"""项目路径工具。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_abs_path(relative_path: str) -> str:
    """把相对路径解析为项目根目录下的绝对路径。"""
    return str(PROJECT_ROOT / relative_path)
