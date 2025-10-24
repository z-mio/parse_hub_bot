from parsehub import ParseHub
from pyrogram import filters
from pyrogram.types import InlineQuery, Message


async def _platform_filter(_, __, update: Message | InlineQuery):
    if isinstance(update, Message):
        t = update.caption or update.text
    else:
        t = update.query
    return bool(ParseHub().select_parser(t))


platform_filter = filters.create(_platform_filter)


def filter_inline_query_results(command: str):
    """
    过滤指定字符开头的内联查询结果

    :param command:
    :return:
    """

    async def func(_, __, update):
        return update.query.startswith(command)

    return filters.create(func, commands=command)
