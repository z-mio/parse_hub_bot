from dataclasses import dataclass

from telegraph.aio import Telegraph as TelegraphAPI


class Telegraph:
    """Telegraph API 封装"""

    def __init__(self, token: str = None, domain: str = "telegra.ph"):
        self.token = token
        self.domain = domain
        self.telegraph = TelegraphAPI(access_token=token, domain=domain)

    async def create_account(
        self, short_name: str, author_name: str = None, author_url: str = None
    ) -> "TelegraphAccount":
        """创建 Telegraph 账户"""
        account = await self.telegraph.create_account(short_name, author_name, author_url)
        acc_info = await self.get_account_info(account)
        self.token = acc_info.access_token
        return acc_info

    async def get_account_info(self, account_info: dict = None) -> "TelegraphAccount":
        """获取 Telegraph 账户信息"""
        account_info = account_info or await self.telegraph.get_account_info(
            [
                "short_name",
                "author_name",
                "author_url",
                "auth_url",
            ]
        )
        return TelegraphAccount(
            self.telegraph.get_access_token(),
            account_info["short_name"],
            account_info["author_name"],
            account_info["author_url"],
            account_info["auth_url"],
        )

    async def create_page(
        self,
        title,
        content=None,
        html_content=None,
        author_name=None,
        author_url=None,
        return_content=False,
        auto_create_account=True,
    ) -> "TelegraphPage":
        """创建 Telegraph 页面"""
        if auto_create_account and not self.token:
            # 随机用户名
            short_name = "tg_" + str(int(100000 * (1 + 0.5 * (1 + 0.5 * (1 + 0.5 * 1)))))
            await self.create_account(short_name)
        response = await self.telegraph.create_page(
            title,
            content,
            html_content,
            author_name,
            author_url,
            return_content,
        )
        return TelegraphPage(
            response["path"],
            response["url"],
            response["title"],
            response["description"],
            response["views"],
            response["can_edit"],
            await self.get_account_info(),
        )


@dataclass
class TelegraphAccount:
    access_token: str
    short_name: str
    author_name: str
    author_url: str
    auth_url: str


@dataclass
class TelegraphPage:
    path: str
    url: str
    title: str
    description: str
    views: int
    can_edit: bool
    account: TelegraphAccount
