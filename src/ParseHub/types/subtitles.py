from pathlib import Path
from xml.etree import ElementTree
from dataclasses import dataclass
from typing import List


@dataclass
class Subtitle:
    begin: str
    end: str
    text: str


@dataclass
class Subtitles:
    def __init__(self, subtitles: List[Subtitle] | None = None):
        self.subtitles = subtitles

    def parse(self, subtitles_path: str | Path) -> "Subtitles":
        sub_type = str(subtitles_path).split(".")[-1]
        match sub_type:
            case "ttml":
                return self._parse_ttml(subtitles_path)
            case _:
                raise ValueError(f"不支持的字幕格式：{sub_type}")

    @classmethod
    def _parse_ttml(cls, subtitles_path: str) -> "Subtitles":
        tree = ElementTree.parse(subtitles_path)
        root = tree.getroot()
        ns = {"tt": "http://www.w3.org/ns/ttml"}

        subtitles = []
        for p in root.findall(".//tt:p", ns):
            begin = p.get("begin")
            end = p.get("end")
            text = "".join(p.itertext()).strip()
            subtitles.append(Subtitle(begin, end, text))

        return cls(subtitles=subtitles)

    def to_str(self) -> str:
        return "\n".join(
            [f"{i.begin}-{i.end}: {i.text}" for i in self.subtitles]
        ).strip()


if __name__ == "__main__":
    subs = Subtitles().parse(
        r"E:\Downloads\Certificate in Python for Quantitative Analytics - Oct 2024 [CnA8l-UDAk0].en.ttml"
    )
    for sub in subs.subtitles[:5]:
        print(f"{sub.begin} --> {sub.end}: {sub.text}")
