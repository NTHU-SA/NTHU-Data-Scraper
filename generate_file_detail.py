import argparse
import datetime
import json
import subprocess
from pathlib import Path
from typing import List, Optional


def get_file_last_commit_info(filepath: Path) -> tuple[Optional[str], Optional[str]]:
    """
    取得指定檔案最後一次 commit 的 SHA 和時間戳記。

    此函數使用 `git log` 命令來查詢檔案的 commit 資訊。

    Args:
        filepath: 檔案路徑 (Pathlib Path 物件)。

    Returns:
        一個 tuple，包含最後一次 commit 的 SHA (字串) 和 ISO 8601 格式的時間戳記 (字串)。
        如果發生錯誤或檔案沒有 commit 紀錄，則返回 (None, None)。
    """
    try:
        output = (
            subprocess.check_output(
                [
                    "git",
                    "log",
                    "-n",
                    "1",
                    "--pretty=format:%H %ct",
                    "--",
                    str(filepath),
                ],
                stderr=subprocess.DEVNULL,  # 避免 git log 錯誤訊息輸出到標準輸出
            )
            .decode("utf-8")
            .strip()
        )

        if not output:  # 檔案沒有 commit 紀錄
            return None, None

        commit_sha, commit_timestamp_str = output.split(" ", 1)
        commit_timestamp = int(commit_timestamp_str)

        commit_datetime_utc = datetime.datetime.fromtimestamp(
            commit_timestamp, datetime.timezone.utc
        )
        commit_datetime_taipei = commit_datetime_utc.astimezone(
            datetime.timezone(datetime.timedelta(hours=8))
        )
        last_updated = commit_datetime_taipei.isoformat()

        return commit_sha, last_updated

    except subprocess.CalledProcessError:
        print(
            f"錯誤：無法取得 {filepath} 的 commit 資訊。請確認檔案已納入 Git 版本控制。"
        )
        return None, None
    except ValueError as e:
        print(
            f"錯誤：解析 {filepath} 的 commit 時間戳記時發生錯誤: {e}, 輸出: {output}"
        )
        return None, None


def generate_file_detail_json(
    data_folder: Path,
    file_detail_json_path: Path,
    include_folders: Optional[List[str]] = None,
    exclude_folders: Optional[List[str]] = None,
) -> None:
    """
    產生 file_detail.json 檔案，包含指定資料夾中檔案的詳細資訊，並使用 commit 時間戳記作為更新時間。

    Args:
        data_folder: 根資料夾路徑 (Pathlib Path 物件)，程式將在此資料夾下遞迴搜尋檔案。
        file_detail_json_path: 輸出 file_detail.json 檔案的路徑 (Pathlib Path 物件)。
        include_folders: 要包含的資料夾名稱列表 (字串列表)。如果為 None，則包含所有資料夾。
        exclude_folders: 要排除的資料夾名稱列表 (字串列表)。
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_taipei = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
    current_time_iso = now_taipei.isoformat()

    file_details = {}

    for path in data_folder.rglob("*"):
        if not path.is_file() or path.name == file_detail_json_path.name:
            continue

        relative_path = path.relative_to(data_folder)
        parts = relative_path.parts

        if parts:
            folder_key = parts[0]
        else:
            folder_key = "files"

        if exclude_folders and folder_key in exclude_folders:
            continue

        if include_folders and folder_key not in include_folders:
            continue

        if folder_key not in file_details:
            file_details[folder_key] = []

        last_commit_sha, last_updated = get_file_last_commit_info(path)

        file_details[folder_key].append(
            {
                "name": path.name,
                "last_updated": last_updated,
                "last_commit": last_commit_sha,
            }
        )

    detail_data = {"last_updated": current_time_iso, "file_details": file_details}

    data_folder.mkdir(parents=True, exist_ok=True)

    with file_detail_json_path.open("w", encoding="utf-8") as f:
        json.dump(detail_data, f, indent=2, ensure_ascii=False)

    print(f"{file_detail_json_path} 檔案已生成。")


if __name__ == "__main__":
    """
    主程式入口。使用 argparse 解析命令列參數，並生成 file_detail.json 檔案。

    使用者可以透過命令列參數指定資料夾路徑、file_detail.json 輸出路徑、包含和排除的資料夾。
    """
    parser = argparse.ArgumentParser(
        description="從指定資料夾生成 file_detail.json 檔案，包含檔案的最後更新時間 (commit 時間)。"
    )
    parser.add_argument(
        "--data_folder",
        type=str,
        default="data",
        help="要掃描的根資料夾路徑 (預設為 'data')",
    )
    parser.add_argument(
        "--json_path",
        type=str,
        default="file_detail.json",
        help="輸出 file_detail.json 檔案的路徑 (預設為 'file_detail.json')",
    )
    parser.add_argument(
        "--include",
        type=str,
        nargs="+",
        help="要包含的資料夾名稱，多個名稱請用空格分隔 (預設包含所有資料夾)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        nargs="+",
        help="要排除的資料夾名稱，多個名稱請用空格分隔 (預設不排除任何資料夾)",
    )
    args = parser.parse_args()
    generate_file_detail_json(
        Path(args.data_folder), Path(args.json_path), args.include, args.exclude
    )
