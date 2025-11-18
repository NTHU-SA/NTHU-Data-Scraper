"""Common base pipelines for scrapers."""

from pathlib import Path
from typing import Any, Dict

from nthu_scraper.utils.file_utils import save_json


class JsonFilePipeline:
    """
    基礎 JSON 檔案 Pipeline。
    
    負責將爬取的資料儲存為 JSON 檔案。
    """

    def __init__(self, output_path: Path):
        """
        初始化 Pipeline。

        Args:
            output_path: JSON 檔案輸出路徑。
        """
        self.output_path = output_path
        self.collected_data = []

    def open_spider(self, spider):
        """Spider 開啟時執行，建立必要的資料夾。"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.collected_data = []

    def process_item(self, item, spider):
        """
        處理每一個 Item。

        Args:
            item: 爬蟲產生的 Item。
            spider: 產生 Item 的爬蟲物件。

        Returns:
            傳遞 Item 給下一個 Pipeline。
        """
        self.collected_data.append(dict(item))
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，儲存所有資料到 JSON 檔案。

        Args:
            spider: 關閉的爬蟲物件。
        """
        if save_json(self.collected_data, self.output_path):
            spider.logger.info(f'✅ 成功儲存資料至 "{self.output_path}"')
        else:
            spider.logger.error(f'❌ 儲存資料失敗 "{self.output_path}"')


class DictJsonFilePipeline:
    """
    字典型 JSON 檔案 Pipeline。
    
    負責將爬取的資料儲存為字典格式的 JSON 檔案。
    """

    def __init__(self, output_path: Path):
        """
        初始化 Pipeline。

        Args:
            output_path: JSON 檔案輸出路徑。
        """
        self.output_path = output_path
        self.collected_data = {}

    def open_spider(self, spider):
        """Spider 開啟時執行，建立必要的資料夾。"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.collected_data = {}

    def process_item(self, item, spider):
        """
        處理每一個 Item，使用指定的鍵儲存。

        Args:
            item: 爬蟲產生的 Item。
            spider: 產生 Item 的爬蟲物件。

        Returns:
            傳遞 Item 給下一個 Pipeline。
        """
        # 子類別需要實作此方法來定義如何將 item 加入 collected_data
        return item

    def close_spider(self, spider):
        """
        Spider 關閉時執行，儲存所有資料到 JSON 檔案。

        Args:
            spider: 關閉的爬蟲物件。
        """
        if save_json(self.collected_data, self.output_path):
            spider.logger.info(f'✅ 成功儲存資料至 "{self.output_path}"')
        else:
            spider.logger.error(f'❌ 儲存資料失敗 "{self.output_path}"')
