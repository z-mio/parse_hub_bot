from easy_ai18n import EasyAI18n
from easy_ai18n.translator import OpenAIBulkTranslator

i18n = EasyAI18n(func_names=["t_", "_t"])

t_ = i18n.i18n()

LANG_MAP = {
    "zh-hans": "简体中文",
    "zh-hant": "繁体中文",
    "en-us": "English",
    "ja-jp": "日本語",
    "ko-kr": "한국어",
    "fr-fr": "Français",
    "de-de": "Deutsch",
    "es-es": "Español",
    "pt-br": "Português (Brasil)",
    "ru-ru": "Русский",
    "it-it": "Italiano",
    "nl-nl": "Nederlands",
    "pl-pl": "Polski",
    "tr-tr": "Türkçe",
    "vi-vn": "Tiếng Việt",
    "th-th": "ภาษาไทย",
    "id-id": "Bahasa Indonesia",
}

ISO639_MAP = {
    "": "zh-hans",
    "zh": "zh-hans",
    "ja": "ja-jp",
    "en": "en-us",
    "ko": "ko-kr",
    "fr": "fr-fr",
    "de": "de-de",
    "es": "es-es",
    "pt": "pt-br",
    "ru": "ru-ru",
    "it": "it-it",
    "nl": "nl-nl",
    "pl": "pl-pl",
    "tr": "tr-tr",
    "vi": "vi-vn",
    "th": "th-th",
    "id": "id-id",
}

if __name__ == "__main__":
    i18n.build(
        to_locales=list(LANG_MAP.keys()),
        translator=OpenAIBulkTranslator(model="gpt-4.1-mini"),
    )
