"""File and JSON utility functions."""

from pathlib import Path
from typing import Any, Optional

from nthu_scraper.storage import read_json_optional, write_json_atomic


def load_json(file_path: Path) -> Optional[Any]:
    """
    載入 JSON 檔案。

    Args:
        file_path: JSON 檔案路徑。

    Returns:
        若檔案不存在則返回 None；JSON 解析及 I/O 錯誤向上傳遞。
    """
    return read_json_optional(file_path)


def save_json(data: Any, file_path: Path, ensure_dir: bool = True) -> bool:
    """
    儲存資料為 JSON 檔案。

    Args:
        data: 要儲存的資料。
        file_path: JSON 檔案路徑。
        ensure_dir: 是否確保目錄存在。

    Returns:
        成功返回 True；序列化及 I/O 錯誤向上傳遞，保留原檔案。
    """
    write_json_atomic(data, file_path, ensure_dir=ensure_dir)
    return True
