import asyncio
import io
import time
from dataclasses import dataclass

import httpx
from easy_ai18n import PreLocaleSelector
from pydantic import AnyUrl
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified, RPCError
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from yaml import safe_dump

from core import PlatformConfigError, PlatformsConfig, bs, pl_cfg
from core.platform_config import MaskedSecretStr, Platform, url_str
from db import get_session
from i18n import t_
from plugins.admin.inputs import InputError, parse_cookies, parse_proxies
from plugins.admin.render import (
    COOKIES,
    GLOBAL,
    HOME,
    Selection,
    build_page,
    cb,
    cookie_detail_text,
    cookie_status_text,
    get_proxies,
    kind_label,
    list_values,
    platform_name,
    proxy_mode,
)
from plugins.helpers import format_label
from services import ParseService, UserService, cookie_health, platform_config_service

PROXY_TEST_URL = "https://cp.cloudflare.com/generate_204"
MAX_INPUT_FILE_SIZE = 1024 * 1024
COOKIE_TEST_TIMEOUT = 60

admin_filter = filters.user(list[int | str](bs.admin_ids))


@dataclass
class PendingInput:
    kind: str
    """proxy / cookie / cookie_test / import"""
    pid: str
    panel_chat_id: int
    panel_message_id: int
    prompt: str
    proxy_kind: str | None = None
    cookie_index: int | None = None
    test_cookies: list[str] | None = None


PENDING: dict[tuple[int, int], PendingInput] = {}
"""(chat_id, 提示消息 id) -> 等待中的输入"""

SELECTIONS: dict[tuple[int, int], tuple[str, Selection]] = {}
"""(chat_id, 面板消息 id) -> (页面, 多选状态); 离开页面即清空"""


def _selection(chat_id: int, message_id: int, page: str, *, create: bool = False) -> Selection:
    cur = SELECTIONS.get((chat_id, message_id))
    if cur is None or cur[0] != page:
        if not create:
            return {}
        cur = SELECTIONS[(chat_id, message_id)] = (page, {})
    return cur[1]


def _chat_id(msg: Message) -> int:
    return msg.chat.id if msg.chat and msg.chat.id is not None else 0


async def _get_t(user_id: int) -> PreLocaleSelector:
    async with get_session() as session:
        return t_[await UserService(session).get_lang(user_id)]


@Client.on_message(filters.command("admin") & filters.private & admin_filter)
async def admin(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return
    _t = await _get_t(msg.from_user.id)
    await msg.reply_rich(rich_message=build_page(_t, HOME))


def _set_proxies(cfg: PlatformsConfig, pid: str, kind: str, urls: list[AnyUrl] | None) -> None:
    if pid == GLOBAL:
        setattr(cfg, "default_parser_proxies" if kind == "p" else "default_downloader_proxies", urls or None)
        return
    pc = cfg.platforms.setdefault(pid, Platform())
    setattr(pc, "parser_proxies" if kind == "p" else "downloader_proxies", urls)


def _set_mode(cfg: PlatformsConfig, pid: str, kind: str, mode: str) -> None:
    pc = cfg.platforms.setdefault(pid, Platform())
    disable_field = "disable_parser_proxy" if kind == "p" else "disable_downloader_proxy"
    setattr(pc, disable_field, mode == "direct")
    if mode == "global":
        _set_proxies(cfg, pid, kind, None)
    elif mode == "own" and get_proxies(cfg, pid, kind) is None:
        _set_proxies(cfg, pid, kind, [])


@Client.on_callback_query(filters.regex(r"^adm\|") & admin_filter)
async def admin_callback(cli: Client, cq: CallbackQuery) -> None:
    if not cq.data or not cq.message:
        return
    act, *args = str(cq.data).split("|")[1:]
    _t = await _get_t(cq.from_user.id)
    chat_id = _chat_id(cq.message)
    page = HOME

    try:
        match act:
            case "open":
                page = args[0]
                SELECTIONS.pop((chat_id, cq.message.id), None)
            case "mode":
                pid, kind, mode = args
                page = pid
                if proxy_mode(pl_cfg.get(pid) or Platform(), kind) == mode:
                    await cq.answer()
                    return
                await platform_config_service.edit(lambda cfg: _set_mode(cfg, pid, kind, mode))
            case "sel" | "selall":
                pid, key = args[0], args[1]
                page = pid
                values = list_values(pl_cfg, pid, key)
                selected = _selection(chat_id, cq.message.id, pid, create=True).setdefault(key, set())
                if act == "sel":
                    index = int(args[2])
                    if not 0 <= index < len(values):
                        raise InputError(_t("列表已变化，请刷新后重试"))
                    selected ^= {values[index]}
                elif selected >= set(values):
                    selected.clear()
                else:
                    selected.update(values)
            case "delsel":
                pid, key = args[0], args[1]
                page = pid
                selected = _selection(chat_id, cq.message.id, pid).get(key, set())

                def delete_selected(cfg: PlatformsConfig) -> None:
                    if key == COOKIES:
                        pc = cfg.platforms.setdefault(pid, Platform())
                        pc.cookies = [c for c in pc.cookies or [] if c.get_secret_value() not in selected] or None
                    else:
                        urls = [u for u in get_proxies(cfg, pid, key) or [] if url_str(u) not in selected]
                        _set_proxies(cfg, pid, key, urls)

                await platform_config_service.edit(delete_selected)
                selected.clear()
            case "delpf":
                pid = args[0]

                def delete_platform(cfg: PlatformsConfig) -> None:
                    cfg.platforms.pop(pid, None)

                await platform_config_service.edit(delete_platform)
            case "reload":
                await platform_config_service.reload()
            case "test":
                await _answer_proxy_test(cq, _t, args[0], args[1], int(args[2]))
                return
            case "cdetail":
                await cq.answer(cookie_detail_text(_t, args[0], int(args[1])), show_alert=True)
                return
            case "cstat":
                await cq.answer(cookie_status_text(_t, args[0]), show_alert=True)
                return
            case "export":
                await _export_config(cli, cq.message)
                await cq.answer()
                return
            case "addp" | "addc" | "repc" | "testc" | "testsel" | "import":
                await _send_prompt(cli, cq, _t, act, args)
                await cq.answer()
                return
            case "cancel":
                PENDING.pop((_chat_id(cq.message), cq.message.id), None)
                await cq.message.delete()
                await cq.answer()
                return
            case "retry":
                await _retry(cq, _t, args[0])
                return
            case "done":
                SELECTIONS.pop((chat_id, cq.message.id), None)
                await _close_panel(cq.message)
                await cq.answer()
                return
            case _:
                await cq.answer()
                return
    except (InputError, PlatformConfigError) as e:
        await cq.answer(str(e)[:200], show_alert=True)
        return

    await _edit_panel(cq.message, build_page(_t, page, selection=_selection(chat_id, cq.message.id, page)))
    await cq.answer()


async def _edit_panel(msg: Message, rich_message: object) -> None:
    try:
        await msg.edit_text(rich_message=rich_message)  # type: ignore[arg-type]
    except MessageNotModified:
        pass


async def _close_panel(msg: Message) -> None:
    for m in (msg, msg.reply_to_message):
        if not m:
            continue
        try:
            await m.delete()
        except RPCError:
            pass


async def _answer_proxy_test(cq: CallbackQuery, _t: PreLocaleSelector, pid: str, kind: str, index: int) -> None:
    urls = get_proxies(pl_cfg, pid, kind) or []
    if not 0 <= index < len(urls):
        await cq.answer(_t("列表已变化，请刷新后重试"), show_alert=True)
        return
    proxy = url_str(urls[index])
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=8) as client:
            await client.get(PROXY_TEST_URL)
    except Exception as e:
        err = str(e) or type(e).__name__
        await cq.answer(f"❌ {_t(f'不可用: {err}')}"[:200], show_alert=True)
        return
    ms = int((time.perf_counter() - start) * 1000)
    await cq.answer(f"✅ {_t('可用')} · {ms} ms", show_alert=True)


async def _export_config(cli: Client, msg: Message) -> None:
    data = safe_dump(pl_cfg.to_data(), allow_unicode=True, sort_keys=False)
    file = io.BytesIO(data.encode())
    file.name = f"platform_config_{time.strftime('%Y%m%d-%H%M%S')}.yaml"
    await cli.send_document(_chat_id(msg), file)


async def _send_prompt(cli: Client, cq: CallbackQuery, _t: PreLocaleSelector, act: str, args: list[str]) -> None:
    if not cq.message:
        return
    if act == "import":
        prompt = "\n\n".join(
            [
                format_label(_t("导入配置")),
                _t("发送 platform_config.yaml 文件，或直接粘贴 YAML 内容。导入后会整份替换当前配置"),
            ]
        )
        await _prompt(cli, _t, PendingInput("import", HOME, _chat_id(cq.message), cq.message.id, prompt))
        return
    pid = args[0]
    name = _t("全局默认") if pid == GLOBAL else platform_name(pid)
    pending = PendingInput(
        kind="", pid=pid, panel_chat_id=_chat_id(cq.message), panel_message_id=cq.message.id, prompt=""
    )
    if act == "addp":
        kind = kind_label(_t, args[1])
        pending.kind, pending.proxy_kind = "proxy", args[1]
        pending.prompt = "\n\n".join(
            [
                format_label(_t(f"添加 {name} 的{kind}")),
                _t("支持 http / https / socks5 / socks5h，一行一个可批量添加"),
            ]
        )
    elif act in ("testc", "testsel"):
        values = list_values(pl_cfg, pid, COOKIES)
        if act == "testc":
            index = int(args[1])
            if not 0 <= index < len(values):
                raise InputError(_t("列表已变化，请刷新后重试"))
            cookies = [values[index]]
        else:
            selected = _selection(pending.panel_chat_id, pending.panel_message_id, pid).get(COOKIES, set())
            cookies = [c for c in values if c in selected]
            if not cookies:
                raise InputError(_t("没有选中的 Cookie"))
        count = len(cookies)
        pending.kind, pending.test_cookies = "cookie_test", cookies
        pending.prompt = "\n\n".join(
            [
                format_label(_t(f"测试 {name} 的 {count} 条 Cookie")),
                _t("发送一个链接，会用所选的每条 Cookie 分别解析一次"),
            ]
        )
    else:
        pending.kind = "cookie"
        if act == "repc":
            pending.cookie_index = int(args[1])
            number = pending.cookie_index + 1
            title = _t(f"替换 {name} 的第 {number} 条 Cookie")
        else:
            title = _t(f"添加 {name} 的 Cookie")
        pending.prompt = "\n\n".join(
            [
                format_label(title),
                _t("一行一条 Cookie，可以一次粘贴多行，也可以发送 .txt 文件（同样一行一条）"),
            ]
        )
    await _prompt(cli, _t, pending)


async def _prompt(cli: Client, _t: PreLocaleSelector, pending: PendingInput, error: str | None = None) -> None:
    text = f"❌ {error}\n\n{pending.prompt}" if error else pending.prompt
    m = await cli.send_message(
        pending.panel_chat_id,
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(_t("取消"), callback_data=cb("cancel"))]],
            force_reply=True,
        ),
    )
    if m:
        PENDING[(_chat_id(m), m.id)] = pending


async def _pending_input(_: object, __: Client, msg: Message) -> bool:
    return bool(msg.reply_to_message_id and (_chat_id(msg), msg.reply_to_message_id) in PENDING)


pending_input_filter = filters.create(_pending_input)


@Client.on_message(filters.private & admin_filter & pending_input_filter, group=-1)
async def admin_input(cli: Client, msg: Message) -> None:
    try:
        await _handle_input(cli, msg)
    finally:
        msg.stop_propagation()


async def _handle_input(cli: Client, msg: Message) -> None:
    if not msg.from_user or not msg.reply_to_message_id:
        return
    chat_id = _chat_id(msg)
    pending = PENDING.pop((chat_id, msg.reply_to_message_id))
    _t = await _get_t(msg.from_user.id)

    notice = error = test_url = None
    try:
        raw = await _read_input(_t, msg)
        if pending.kind == "cookie_test":
            test_url = _parse_test_url(_t, pending.pid, raw)
        else:
            notice = await _apply_input(_t, pending, raw)
    except (InputError, PlatformConfigError) as e:
        error = str(e)[:1000]
    finally:
        for message_id in (msg.id, msg.reply_to_message_id):
            try:
                await cli.delete_messages(chat_id, message_id)
            except RPCError:
                pass
    if error is not None:
        await _prompt(cli, _t, pending, error)
        return

    if test_url and pending.test_cookies:
        cookie_health.set_testing(pending.test_cookies, True)
        try:
            await _refresh_panel(cli, _t, pending, None)
            notice = await _test_cookies(_t, pending.pid, test_url, pending.test_cookies)
        finally:
            cookie_health.set_testing(pending.test_cookies, False)
    await _refresh_panel(cli, _t, pending, notice)


async def _refresh_panel(cli: Client, _t: PreLocaleSelector, pending: PendingInput, notice: str | None) -> None:
    page = build_page(_t, pending.pid, notice, _selection(pending.panel_chat_id, pending.panel_message_id, pending.pid))
    try:
        await cli.edit_message_text(pending.panel_chat_id, pending.panel_message_id, rich_message=page)
    except MessageNotModified:
        pass
    except RPCError:
        await cli.send_rich_message(pending.panel_chat_id, page)


def _parse_test_url(_t: PreLocaleSelector, pid: str, raw: str) -> str:
    url = raw.strip()
    if not url:
        raise InputError(_t("没有收到链接"))
    try:
        platform = ParseService().get_platform(url)
    except ValueError as e:
        raise InputError(_t("不支持这个链接")) from e
    if platform.id != pid:
        name = platform_name(pid)
        raise InputError(_t(f"这不是 {name} 的链接"))
    return url


async def _test_cookies(_t: PreLocaleSelector, pid: str, url: str, cookies: list[str]) -> str:
    async def test(cookie: str) -> bool:
        try:
            await asyncio.wait_for(ParseService().test_cookie(url, cookie), COOKIE_TEST_TIMEOUT)
        except TimeoutError as e:
            cookie_health.record_failure(pid, cookie, e, url, alert=False)
            return False
        except Exception:
            return False
        return True

    results = await asyncio.gather(*(test(c) for c in cookies))
    ok = sum(results)
    failed = len(results) - ok
    return f"🧪 {_t(f'测试完成：{ok} 条成功，{failed} 条失败')}"


async def _read_input(_t: PreLocaleSelector, msg: Message) -> str:
    if msg.document:
        if (msg.document.file_size or 0) > MAX_INPUT_FILE_SIZE:
            raise InputError(_t("文件太大"))
        file = await msg.download(in_memory=True)
        try:
            return bytes(file.getbuffer()).decode("utf-8")  # type: ignore[union-attr]
        except UnicodeDecodeError as e:
            raise InputError(_t("文件需要是 UTF-8 文本")) from e
    return msg.text or msg.caption or ""


async def _apply_input(_t: PreLocaleSelector, pending: PendingInput, raw: str) -> str:
    pid = pending.pid
    if pending.kind == "import":
        if not raw.strip():
            raise InputError(_t("没有收到配置"))
        await platform_config_service.replace(PlatformsConfig.parse_text(raw))
        return f"✅ {_t('已导入配置，立即生效')}"
    if pending.kind == "proxy" and pending.proxy_kind:
        kind = pending.proxy_kind
        urls = parse_proxies(_t, raw)
        added = 0

        def add_proxies(cfg: PlatformsConfig) -> None:
            nonlocal added
            current = list(get_proxies(cfg, pid, kind) or [])
            existing = {url_str(u) for u in current}
            for u in urls:
                if url_str(u) not in existing:
                    existing.add(url_str(u))
                    current.append(u)
                    added += 1
            _set_proxies(cfg, pid, kind, current)

        await platform_config_service.edit(add_proxies)
        label = kind_label(_t, kind)
        return f"✅ {_t(f'已添加 {added} 条{label}，立即生效')}" if added else f"ℹ️ {_t('都已存在，没有新增')}"

    new_cookies = parse_cookies(_t, raw)
    index = pending.cookie_index
    added = 0

    def set_cookies(cfg: PlatformsConfig) -> None:
        nonlocal added
        pc = cfg.platforms.setdefault(pid, Platform())
        cookies = list(pc.cookies or [])
        if index is not None and not 0 <= index < len(cookies):
            raise InputError(_t("列表已变化，请刷新后重试"))
        others = {c.get_secret_value() for i, c in enumerate(cookies) if i != index}
        fresh = [MaskedSecretStr(c) for c in new_cookies if c not in others]
        added = len(fresh)
        if index is None:
            cookies.extend(fresh)
        elif fresh:
            cookies[index : index + 1] = fresh
        pc.cookies = cookies

    await platform_config_service.edit(set_cookies)
    if not added:
        return f"ℹ️ {_t('都已存在，没有新增')}"
    if index is None:
        return f"✅ {_t(f'已添加 {added} 条 Cookie，立即生效')}"
    return f"✅ {_t(f'已替换为 {added} 条 Cookie，立即生效')}"


async def _retry(cq: CallbackQuery, _t: PreLocaleSelector, pid: str) -> None:
    if not cq.message:
        return
    if not (url := cookie_health.last_failed_url(pid)):
        await cq.answer(_t("没有可重试的链接"), show_alert=True)
        return
    await cq.answer()
    try:
        await ParseService().parse(url)
    except Exception as e:
        err = str(e) or type(e).__name__
        await cq.message.reply(f"❌ {_t(f'重试仍然失败: {err}')}")
        return
    await cq.message.reply(f"✅ {_t('重试成功')}")
