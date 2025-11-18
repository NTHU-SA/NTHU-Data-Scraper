"""File and JSON utility functions."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(file_path: Path) -> Optional[Any]:
    """
    載入 JSON 檔案。

    Args:
        file_path: JSON 檔案路徑。

    Returns:
        若成功載入則返回 JSON 資料，否則返回 None。
    """
    if not file_path.exists():
        print(f"警告：JSON 檔案 '{file_path}' 不存在。")
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"錯誤：JSON 檔案解析失敗 '{file_path}': {e}")
        return None


def save_json(data: Any, file_path: Path, ensure_dir: bool = True) -> bool:
    """
    儲存資料為 JSON 檔案。

    Args:
        data: 要儲存的資料。
        file_path: JSON 檔案路徑。
        ensure_dir: 是否確保目錄存在。

    Returns:
        成功返回 True，失敗返回 False。
    """
    try:
        if ensure_dir:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"錯誤：儲存 JSON 檔案失敗 '{file_path}': {e}")
        return False
