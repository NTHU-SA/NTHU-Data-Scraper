"""URL processing utility functions."""

from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


# 新增：強制 https 的輔助方法
def force_https(url: str) -> str:
    """將 URL 的 scheme 強制為 https（簡單替換 http:// 與 // 開頭情況）"""
    if not url:
        return url
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def update_url_query_param(
    url: str, param_name: str, param_value: str, force_https: bool = True
) -> str:
    """
    更新網址的查詢參數。可選地強制將 scheme 設為 https。

    Args:
        url: 網址字串。
        param_name: 參數名稱。
        param_value: 參數值。
        force_https: 若為 True，會把 scheme 強制改為 https（若原本為 http 或空）。
    Returns:
        更新參數後的網址字串。
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params[param_name] = [param_value]
    new_query = urlencode(query_params, doseq=True)

    # 若要求強制 https，將 scheme 改為 https；否則保留原本的 scheme（包括空 scheme -> 會保留 //host/... 形式）
    if force_https:
        parsed_url = parsed_url._replace(scheme="https", query=new_query)
    else:
        parsed_url = parsed_url._replace(query=new_query)

    return urlunparse(parsed_url)


def build_multi_lang_urls(
    original_url: str, languages: List[str], lang_param: str = "Lang"
) -> Optional[Dict[str, str]]:
    """
    為給定的原始 URL 建立包含不同語言版本的 URL 字典。

    Args:
        original_url: 原始網址字串。
        languages: 語言代碼列表。
        lang_param: 語言參數名稱。

    Returns:
        一個字典，鍵為語言代碼，值為對應語言版本的 URL。
    """
    lang_urls = {}
    for lang in languages:
        lang_urls[lang] = update_url_query_param(original_url, lang_param, lang)
    return lang_urls


def check_domain_suffix(url: str, suffix: str) -> bool:
    """
    檢查 URL 是否屬於指定的網域後綴。

    Args:
        url: 要檢查的 URL。
        suffix: 網域後綴。

    Returns:
        若 URL 屬於該網域後綴則返回 True，否則返回 False。
    """
    parsed_url = urlparse(url)
    return bool(parsed_url.hostname and parsed_url.hostname.endswith(suffix))
