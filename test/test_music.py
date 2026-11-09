import asyncio
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from parsehub.types import MusicFile, MusicParseResult, MusicRef
from pyrogram.types import InlineQueryResultCachedAudio, InlineQueryResultPhoto

from plugins.parse.inline import build_cached_inline_results, build_inline_results
from plugins.parse.sender import MessageSender, send_cached_single, send_media
from repo.settings import SettingsConfig
from services import CacheEntry, CacheMedia, CacheMediaType, CacheParseResult
from services.media import ProcessedMedia
from utils.media_processing_unit import MediaProcessingUnit

type FailFn = Callable[[dict[str, Any]], Exception | None]


class FakeMessage:
    def __init__(self, fail: FailFn | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    async def reply_chat_action(self, action: Any) -> None:
        return None

    async def answer_audio(self, audio: Any, **kwargs: Any) -> Any:
        return self._record("audio", audio, kwargs)

    async def answer_document(self, document: Any, **kwargs: Any) -> Any:
        return self._record("document", document, kwargs)

    def _record(self, kind: str, payload: Any, kwargs: dict[str, Any]) -> Any:
        call = {"kind": kind, "payload": payload, **kwargs}
        self.calls.append(call)
        error = self._fail(call) if self._fail else None
        if error is not None:
            raise error
        attrs: dict[str, Any] = {"photo": None, "video": None, "animation": None, "document": None, "audio": None}
        attrs[kind] = SimpleNamespace(file_id=f"{kind}-id")
        return SimpleNamespace(**attrs)


def make_sender(msg: FakeMessage) -> MessageSender:
    return MessageSender(
        cli=cast(Any, None),
        msg=cast(Any, msg),
        config=SettingsConfig(reply_msg=False, video_cover=False),
    )


def make_music_result() -> MusicParseResult:
    return MusicParseResult(
        title="Song",
        music=MusicRef(url="https://x/a.m4a", thumb_url="https://x/c.jpg", duration=200),
    )


def make_processed(tmp_path: Path) -> ProcessedMedia:
    return ProcessedMedia(MusicFile(path=str(tmp_path / "Song.m4a"), duration=200), [tmp_path / "Song.m4a"])


def test_process_audio_passthrough(tmp_path: Path) -> None:
    audio = tmp_path / "a.m4a"
    audio.touch()

    result = asyncio.run(MediaProcessingUnit(tmp_path).process(audio))

    assert result.output_paths == [audio]


def test_send_media_music(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_thumb(url: str, out_path: Any) -> str:
        return "thumb.jpg"

    monkeypatch.setattr("plugins.parse.sender.fetch_thumb", fake_fetch_thumb)
    msg = FakeMessage()
    sender = make_sender(msg)

    entry = asyncio.run(send_media(sender, make_music_result(), [make_processed(tmp_path)], "cap", _t=cast(Any, None)))

    assert entry is not None
    assert entry.media == [CacheMedia(type=CacheMediaType.AUDIO, file_id="audio-id")]
    assert [call["kind"] for call in msg.calls] == ["audio"]
    call = msg.calls[0]
    assert call["payload"] == tmp_path / "Song.m4a"
    assert call["caption"] == "cap"
    assert call["duration"] == 200
    assert call["title"] == "Song"
    assert call["thumb"] == "thumb.jpg"


def test_send_media_music_falls_back_to_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_thumb(url: str, out_path: Any) -> None:
        return None

    monkeypatch.setattr("plugins.parse.sender.fetch_thumb", fake_fetch_thumb)
    msg = FakeMessage(fail=lambda call: Exception("boom") if call["kind"] == "audio" else None)
    sender = make_sender(msg)

    entry = asyncio.run(send_media(sender, make_music_result(), [make_processed(tmp_path)], "cap", _t=cast(Any, None)))

    assert entry is None
    assert [call["kind"] for call in msg.calls] == ["audio", "document"]
    assert msg.calls[1]["force_document"] is True


def test_send_cached_single_audio() -> None:
    msg = FakeMessage()
    sender = make_sender(msg)

    asyncio.run(
        send_cached_single(sender, CacheMedia(type=CacheMediaType.AUDIO, file_id="audio-fid"), "cap", video_cover=False)
    )

    assert [call["kind"] for call in msg.calls] == ["audio"]
    assert msg.calls[0]["payload"] == "audio-fid"
    assert msg.calls[0]["caption"] == "cap"


def test_build_cached_inline_results_audio() -> None:
    entry = CacheEntry(
        parse_result=CacheParseResult(title="Song", content="desc"),
        media=[CacheMedia(type=CacheMediaType.AUDIO, file_id="afid")],
    )

    results = build_cached_inline_results(entry, "https://x", "zh-hans", SettingsConfig())

    audios = [r for r in results if isinstance(r, InlineQueryResultCachedAudio)]
    assert len(audios) == 1
    assert audios[0].audio_file_id == "afid"


def test_build_inline_results_music() -> None:
    parse_result = make_music_result()
    parse_result.raw_url = "https://www.bilibili.com/audio/au2854883"

    results = asyncio.run(build_inline_results(parse_result, cast(Any, None), "zh-hans", SettingsConfig()))

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, InlineQueryResultPhoto)
    assert result.id == "download_0"
    assert result.reply_markup is not None
