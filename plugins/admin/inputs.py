"""解析管理员在面板里输入的代理和 cookie"""

from easy_ai18n import PreLocaleSelector
from pydantic import AnyUrl, TypeAdapter, ValidationError

from core.platform_config import PROXY_SCHEMES


class InputError(ValueError):
    pass


_url_adapter = TypeAdapter(AnyUrl)


def parse_proxies(_t: PreLocaleSelector, raw: str) -> list[AnyUrl]:
    """一行一个代理地址"""
    result: list[AnyUrl] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            url = _url_adapter.validate_python(line)
        except ValidationError as e:
            raise InputError(_t(f"无效的代理地址: {line}")) from e
        if url.scheme not in PROXY_SCHEMES:
            raise InputError(_t(f"不支持的代理协议: {line}"))
        result.append(url)
    if not result:
        raise InputError(_t("没有收到代理地址"))
    return result


def parse_cookies(_t: PreLocaleSelector, raw: str) -> list[str]:
    """一行一条 cookie, 去掉空行和重复行"""
    cookies = list(dict.fromkeys(line.strip() for line in raw.lstrip("\ufeff").splitlines() if line.strip()))
    if not cookies:
        raise InputError(_t("没有收到 Cookie"))
    return cookies
