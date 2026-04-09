from lingua import LanguageDetectorBuilder

_DETECTOR = LanguageDetectorBuilder.from_all_languages().build()


def detect_language_code(text: str) -> str:
    language = _DETECTOR.detect_language_of(text)
    if language is None:
        return "unknown"

    iso_code = getattr(language, "iso_code_639_1", None)
    if iso_code is None:
        return language.name.lower()

    value = getattr(iso_code, "name", None) or getattr(iso_code, "value", None)
    if isinstance(value, str):
        return value.lower()
    return language.name.lower()
