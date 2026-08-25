import re

from unidecode import unidecode


def normalized_words(value: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", unidecode(value or "").lower())


def author_key(value: str | None) -> str | None:
    words = normalized_words(value)
    if len(words) == 1:
        return words[0]
    return f"{words[-1]} {words[0][0]}" if words else None


def normalized_institution(value: str | None) -> str:
    return " ".join(word for word in normalized_words(value) if word not in {"at", "and", "the"})


def institutions_match(first: str | None, second: str | None) -> bool:
    first_name = normalized_institution(first)
    second_name = normalized_institution(second)
    return bool(first_name) and first_name == second_name
