import html
import re
from collections import Counter
from difflib import SequenceMatcher

from unidecode import unidecode


def get_normalized_words(text):
    return re.findall(r"[a-z0-9]+", unidecode(text or "").lower())


def normalize_text(text):
    if not text:
        return None

    clean_text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(get_normalized_words(clean_text))


def compare_texts(first_text, second_text):
    if not first_text or not second_text:
        return {
            "status": "unavailable",
            "word_overlap": None,
            "character_similarity": None,
        }

    first_normalized = normalize_text(first_text)
    second_normalized = normalize_text(second_text)
    first_words = set(get_normalized_words(first_text))
    second_words = set(get_normalized_words(second_text))
    all_words = first_words | second_words

    if first_text == second_text:
        status = "exact"
    elif first_normalized == second_normalized:
        status = "normalized_match"
    else:
        status = "mismatch"

    return {
        "status": status,
        "word_overlap": len(first_words & second_words) / len(all_words) if all_words else 1,
        "character_similarity": SequenceMatcher(
            None,
            first_normalized,
            second_normalized,
        ).ratio(),
    }


def get_author_keys(authors):
    keys = set()

    for author in authors or []:
        words = get_normalized_words(author)

        if len(words) == 1:
            keys.add(words[0])
        elif words:
            keys.add(f"{words[-1]} {words[0][0]}")

    return keys


def compare_author_lists(first_authors, second_authors):
    first_keys = get_author_keys(first_authors)

    if second_authors is None:
        return {
            "first_count": len(first_keys),
            "second_count": None,
            "shared_count": None,
            "difference": None,
        }

    second_keys = get_author_keys(second_authors)

    return {
        "first_count": len(first_keys),
        "second_count": len(second_keys),
        "shared_count": len(first_keys & second_keys),
        "difference": len(first_keys ^ second_keys),
    }


def get_publication_authors(publication):
    if "authors_list" in publication:
        return publication["authors_list"] or []

    return publication.get("authors")


def compare_publications(first, second):
    first_year = first.get("year")
    second_year = second.get("year")

    return {
        "authors": compare_author_lists(
            get_publication_authors(first),
            get_publication_authors(second),
        ),
        "title": compare_texts(first.get("title"), second.get("title")),
        "year_gap": (
            abs(first_year - second_year)
            if first_year is not None and second_year is not None
            else None
        ),
        "journal": compare_texts(first.get("journal"), second.get("journal")),
    }


def summarize_publication_comparisons(comparisons):
    return {
        "author_differences": dict(Counter(
            comparison["authors"]["difference"]
            for comparison in comparisons
        )),
        "title_matches": dict(Counter(
            comparison["title"]["status"]
            for comparison in comparisons
        )),
        "year_gaps": dict(Counter(
            comparison["year_gap"]
            for comparison in comparisons
        )),
        "journal_matches": dict(Counter(
            comparison["journal"]["status"]
            for comparison in comparisons
        )),
    }
