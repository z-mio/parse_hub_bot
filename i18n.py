from easy_ai18n import EasyAI18n
from easy_ai18n.translator import OpenAIBulkTranslator

i18n = EasyAI18n(func_names=["t_", "_t"])

t_ = i18n.i18n()

if __name__ == "__main__":
    i18n.build(
        to_locales=["en-us", "ja-jp", "zh-hant"],
        translator=OpenAIBulkTranslator(model="gpt-4.1-mini"),
    )
