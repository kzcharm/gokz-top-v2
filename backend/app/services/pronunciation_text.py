import re
import unicodedata

_PREFIX = re.compile(r"^(?:kz|bkz|skz|kzpro|xc|vnl)_", re.IGNORECASE)
_SUFFIX = re.compile(
    r"(?:fix|gfix|go|csgo|v\d+(?:go)?|fix\d+|od\d+|b\d+|c\d+)", re.IGNORECASE
)
_FINAL = re.compile(r"final\d*", re.IGNORECASE)


def spoken_map_name(name: str) -> str:
    tokens = _PREFIX.sub("", name.strip(), count=1).split("_")
    index = len(tokens) - 1
    while index >= 0:
        token = tokens[index].strip()
        if not token or _SUFFIX.fullmatch(token):
            tokens.pop(index)
        elif not _FINAL.fullmatch(token):
            break
        index -= 1
    return " ".join(" ".join(tokens).split())


def spoken_player_name(name: str, steamid64: int) -> str:
    if name.strip() == str(steamid64) or steamid64 <= 0:
        return ""
    normalized = unicodedata.normalize("NFKC", name)
    output: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character in {"\ufe0e", "\ufe0f", "\u20e3"}:
            continue
        if category[0] in {"L", "N"} or character in {"'", "’", "-"}:
            output.append(character)
        elif category[0] == "M" and output and output[-1] != " ":
            output.append(character)
        else:
            output.append(" ")
    text = " ".join("".join(output).split())
    return text if any(unicodedata.category(c)[0] in {"L", "N"} for c in text) else ""
