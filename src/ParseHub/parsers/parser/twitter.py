import re
from typing import Callable

import httpx

from ..base.base import Parse
from ...types import Image, Video, Ani, MultimediaParseResult, ParseError


class TwitterParse(Parse):
    __match__ = r"^(http(s)?://)?.+(twitter|x).com/.*/status/\d+"

    async def parse(
        self, url: str, progress: Callable = None, progress_args=()
    ) -> "MultimediaParseResult":
        url = await self.get_raw_url(url)
        x = Twitter()
        try:
            tweet = await x.fetch_tweet(url)
        except Exception as e:
            raise ParseError(e)
        return await self.media_parse(url, tweet)

    @staticmethod
    async def media_parse(url, tweet: "TwitterTweet"):
        media = []
        for i, v in enumerate(tweet.media):
            for t, m in v.items():
                if t == "photo":
                    path = Image(m)
                elif t == "video":
                    path = Video(m)
                elif t == "animated_gif":
                    path = Ani(path=m, ext="mp4")
                else:
                    continue
                media.append(path)
        return MultimediaParseResult(desc=tweet.full_text, media=media, raw_url=url)


class Twitter:
    def __init__(self):
        self.authorization = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

    async def fetch_tweet(self, url: str) -> "TwitterTweet":
        tweet_id = self.get_id_by_url(url)

        headers = {
            "accept-language": "zh-CN,zh;q=0.9",
            "authorization": self.authorization,
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "x-guest-token": await self.get_guest_token(),
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "zh-cn",
        }

        params = {
            "variables": f'{{"tweetId":"{tweet_id}","withCommunity":false,"includePromotedContent":false,"withVoice":false}}',
            "features": '{"creator_subscriptions_tweet_preview_api_enabled":true,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"tweet_with_visibility_results_prefer_gql_media_interstitial_enabled":false,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_enhance_cards_enabled":false}',
            "fieldToggles": '{"withArticleRichContentState":true,"withArticlePlainText":false}',
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.twitter.com/graphql/kPLTRmMnzbPTv70___D06w/TweetResultByRestId",
                params=params,
                headers=headers,
            )
        response.raise_for_status()
        return self.parse(response.json())

    @staticmethod
    def parse(result: dict):
        result = result["data"]["tweetResult"]["result"]
        legacy: dict = result.get("legacy")
        if not legacy:
            raise Exception(result["reason"])

        tweet_id = result["rest_id"]
        full_text = legacy.get("full_text", "")
        media = legacy["entities"].get("media", [])
        media = [
            {
                i["type"]: i["media_url_https"]
                if i["type"] == "photo"
                else i["video_info"]["variants"][-1]["url"]
            }
            for i in media
        ]
        return TwitterTweet(tweet_id=tweet_id, full_text=full_text, media=media)

    @staticmethod
    def get_id_by_url(url: str):
        return re.match(r"\d+", url.split("/")[-1])[0]

    async def get_guest_token(self):
        headers = {
            "Authorization": self.authorization,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.twitter.com/1.1/guest/activate.json", headers=headers
            )
        return response.json()["guest_token"]


class TwitterTweet:
    def __init__(self, tweet_id: str, full_text: str, media: list[dict]):
        self.tweet_id = tweet_id
        self.full_text = (
            re.sub(r"https://t\.co/[^\s,]+$", "", full_text) if media else full_text
        )
        self.media = media
