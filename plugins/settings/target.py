from easy_ai18n import PreLocaleSelector
from pyrogram import Client
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import CallbackQuery, Message

from db.models.settings import SettingsScope
from plugins.helpers import format_label, get_thread_id, parse_channel_ref
from plugins.settings.models import CfgAction, CfgCQData, CfgScopeCode, CfgTargetOption
from repo.settings import SettingsConfig
from repo.settings.schema import ConfigMetadata
from services.settings import (
    AnySettingsTarget,
    ChannelSettingsTarget,
    ForumTopicMemberSettingsTarget,
    ForumTopicSettingsTarget,
    GroupMemberSettingsTarget,
    GroupSettingsTarget,
    UserSettingsTarget,
)


async def build_cfg_target_options(cli: Client, msg: Message, _t: PreLocaleSelector) -> list[CfgTargetOption]:
    if not msg.from_user or not msg.chat:
        return []

    chat_id = msg.chat.id
    if chat_id is None:
        return []
    thread_id = get_thread_id(msg)
    if msg.chat.type == ChatType.PRIVATE:
        return [
            CfgTargetOption(
                _t("个人配置"),
                CfgScopeCode.USER,
                UserSettingsTarget(telegram_user_id=msg.from_user.id),
            )
        ]

    if msg.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.FORUM]:
        await msg.reply(format_label(_t("请在私聊, 群组, 话题发送 `/cfg` 或使用 `/cfg <频道用户名/链接/id>` 进行配置")))
        return []

    is_admin = await is_chat_admin(cli, chat_id, msg.from_user.id)
    if thread_id:
        if is_admin:
            return [
                CfgTargetOption(
                    _t("话题配置"),
                    CfgScopeCode.FORUM_TOPIC,
                    ForumTopicSettingsTarget(telegram_chat_id=chat_id, telegram_thread_id=thread_id),
                ),
                CfgTargetOption(
                    _t("个人配置"),
                    CfgScopeCode.USER,
                    UserSettingsTarget(telegram_user_id=msg.from_user.id),
                ),
                CfgTargetOption(
                    _t("话题内个人配置"),
                    CfgScopeCode.FORUM_TOPIC_MEMBER,
                    ForumTopicMemberSettingsTarget(
                        telegram_chat_id=chat_id,
                        telegram_thread_id=thread_id,
                        telegram_user_id=msg.from_user.id,
                    ),
                ),
            ]
        return [
            CfgTargetOption(
                _t("个人配置"),
                CfgScopeCode.USER,
                UserSettingsTarget(telegram_user_id=msg.from_user.id),
            ),
            CfgTargetOption(
                _t("话题内个人配置"),
                CfgScopeCode.FORUM_TOPIC_MEMBER,
                ForumTopicMemberSettingsTarget(
                    telegram_chat_id=chat_id,
                    telegram_thread_id=thread_id,
                    telegram_user_id=msg.from_user.id,
                ),
            ),
        ]

    if is_admin:
        return [
            CfgTargetOption(_t("群组配置"), CfgScopeCode.GROUP, GroupSettingsTarget(telegram_chat_id=chat_id)),
            CfgTargetOption(_t("个人配置"), CfgScopeCode.USER, UserSettingsTarget(telegram_user_id=msg.from_user.id)),
            CfgTargetOption(
                _t("群内个人配置"),
                CfgScopeCode.GROUP_MEMBER,
                GroupMemberSettingsTarget(telegram_chat_id=chat_id, telegram_user_id=msg.from_user.id),
            ),
        ]
    return [
        CfgTargetOption(
            _t("个人配置"),
            CfgScopeCode.USER,
            UserSettingsTarget(telegram_user_id=msg.from_user.id),
        ),
        CfgTargetOption(
            _t("群内个人配置"),
            CfgScopeCode.GROUP_MEMBER,
            GroupMemberSettingsTarget(telegram_chat_id=chat_id, telegram_user_id=msg.from_user.id),
        ),
    ]


def restore_cfg_target(cq: CallbackQuery, data: CfgCQData) -> AnySettingsTarget | None:
    if not data.scope or not cq.message or not cq.message.chat:
        return None

    chat_id = cq.message.chat.id
    if chat_id is None:
        return None
    match data.scope:
        case CfgScopeCode.USER:
            return UserSettingsTarget(telegram_user_id=data.user_id or cq.from_user.id)
        case CfgScopeCode.GROUP:
            return GroupSettingsTarget(telegram_chat_id=chat_id)
        case CfgScopeCode.GROUP_MEMBER:
            return GroupMemberSettingsTarget(telegram_chat_id=chat_id, telegram_user_id=data.user_id or cq.from_user.id)
        case CfgScopeCode.FORUM_TOPIC:
            thread_id = get_thread_id(cq.message)
            if not thread_id:
                return None
            return ForumTopicSettingsTarget(telegram_chat_id=chat_id, telegram_thread_id=thread_id)
        case CfgScopeCode.FORUM_TOPIC_MEMBER:
            thread_id = get_thread_id(cq.message)
            if not thread_id:
                return None
            return ForumTopicMemberSettingsTarget(
                telegram_chat_id=chat_id,
                telegram_thread_id=thread_id,
                telegram_user_id=data.user_id or cq.from_user.id,
            )
        case CfgScopeCode.CHANNEL:
            if data.channel_id is None:
                return None
            return ChannelSettingsTarget(telegram_chat_id=data.channel_id)


def cfg_callback_data(action: CfgAction, value: str, target: AnySettingsTarget | None) -> str:
    scope: CfgScopeCode | None
    match target:
        case UserSettingsTarget():
            scope = CfgScopeCode.USER
        case GroupSettingsTarget():
            scope = CfgScopeCode.GROUP
        case GroupMemberSettingsTarget():
            scope = CfgScopeCode.GROUP_MEMBER
        case ForumTopicSettingsTarget():
            scope = CfgScopeCode.FORUM_TOPIC
        case ForumTopicMemberSettingsTarget():
            scope = CfgScopeCode.FORUM_TOPIC_MEMBER
        case ChannelSettingsTarget():
            scope = CfgScopeCode.CHANNEL
        case None:
            scope = None

    return CfgCQData(
        action=action,
        value=value,
        scope=scope,
        channel_id=target.telegram_chat_id if isinstance(target, ChannelSettingsTarget) else None,
        user_id=target.telegram_user_id
        if isinstance(target, UserSettingsTarget | GroupMemberSettingsTarget | ForumTopicMemberSettingsTarget)
        else None,
    ).unparse()


def get_allowed_fields(scope: SettingsScope) -> frozenset[str]:
    fields = []
    for field_name, field in SettingsConfig.model_fields.items():
        for metadata in field.metadata:
            if isinstance(metadata, ConfigMetadata) and scope in metadata.scopes:
                fields.append(field_name)
                break
    return frozenset(fields)


async def ensure_cfg_field(
    cq: CallbackQuery, _t: PreLocaleSelector, target: AnySettingsTarget, field_name: str
) -> bool:
    if field_name not in get_allowed_fields(target.scope):
        await cq.answer(_t("不支持的配置项"), show_alert=True)
        return False
    return True


async def ensure_cfg_permission(
    cli: Client, cq: CallbackQuery, _t: PreLocaleSelector, target: AnySettingsTarget
) -> bool:
    match target:
        case UserSettingsTarget(telegram_user_id=user_id):
            if user_id == cq.from_user.id:
                return True
            await cq.answer(_t("这不是你的配置"), show_alert=True)
            return False
        case (
            GroupMemberSettingsTarget(telegram_user_id=user_id)
            | ForumTopicMemberSettingsTarget(telegram_user_id=user_id)
        ):
            if user_id == cq.from_user.id:
                return True
            await cq.answer(_t("这不是你的配置"), show_alert=True)
            return False
        case GroupSettingsTarget(telegram_chat_id=chat_id) | ForumTopicSettingsTarget(telegram_chat_id=chat_id):
            if await is_chat_admin(cli, chat_id, cq.from_user.id):
                return True
            await cq.answer(_t("你不是该聊天的管理员, 无权修改配置"), show_alert=True)
            return False
        case ChannelSettingsTarget(telegram_chat_id=chat_id):
            if await is_chat_owner(cli, chat_id, cq.from_user.id):
                return True
            await cq.answer(_t("你不是该频道的拥有者, 无权修改频道配置"), show_alert=True)
            return False


async def resolve_channel_target(
    cli: Client,
    msg: Message,
    _t: PreLocaleSelector,
    channel_ref: str,
) -> ChannelSettingsTarget | None:
    if not msg.from_user:
        return None

    try:
        channel = parse_channel_ref(channel_ref)
    except Exception:
        await msg.reply(format_label(_t("链接格式无效")))
        return None
    try:
        chat = await cli.get_chat(channel)
    except Exception:
        await msg.reply(format_label(_t("Bot 未加入该频道, 请先将 Bot 加入频道后再配置")))
        return None

    if not chat:
        await msg.reply(format_label(_t("Bot 未加入该频道, 请先将 Bot 加入频道后再配置")))
        return None

    if chat.type != ChatType.CHANNEL:
        await msg.reply(format_label(_t("非频道")))
        return None

    if chat.id is None:
        await msg.reply(format_label(_t("Bot 未加入该频道, 请先将 Bot 加入频道后再配置")))
        return None

    if not await is_chat_owner(cli, chat.id, msg.from_user.id):
        await msg.reply(format_label(_t("你不是该频道的拥有者, 无权修改频道配置")))
        return None

    return ChannelSettingsTarget(telegram_chat_id=chat.id)


async def is_chat_admin(cli: Client, chat_id: int | str, user_id: int) -> bool:
    try:
        member = await cli.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


async def is_chat_owner(cli: Client, chat_id: int | str, user_id: int) -> bool:
    try:
        member = await cli.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in {ChatMemberStatus.OWNER}
