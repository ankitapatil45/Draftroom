"""Shared formatting and fallback helpers for the document and slide writers."""
import json
import re

from ..ops import sentences, trim_words


DOC_SCHEMA = '{"title":str,"subtitle":str,"sections":[{"heading":str,"level":1|2,"paragraphs":[str],"bullets":[str]}]}'
DECK_SCHEMA = '{"title":str,"subtitle":str,"slides":[{"title":str,"bullets":[str],"notes":str,"kind":"content"}]}'


def source_block(sources: list[dict], limit: int = 1000) -> str:
    return "\n".join(
        f"[{source['id']}] ({source['kind']}) {source['title']} {source['url']}\n"
        f"    {source['snippet'][:limit]}"
        for source in sources
    )


def style_block(style: dict, which: str) -> str:
    profile = style.get(which) or {}
    headings = [item["text"] for item in profile.get("headings", [])][:14]
    if not headings:
        headings = [slide["title"] for slide in profile.get("slides", [])][:14]

    return json.dumps(
        {
            "tone": profile.get("tone", {}).get("description"),
            "tone_sample": profile.get("tone", {}).get("sample"),
            "template_headings_or_slide_titles": headings,
            "avg_bullets_per_slide": profile.get("avg_bullets_per_slide"),
        },
        indent=1,
    )


def topic_title(topic: str) -> str:
    title = re.sub(r"\s+", " ", topic).strip(" .")
    return (title[:1].upper() + title[1:])[:80]


def sentence_pool(sources: list[dict]) -> list[tuple[str, int]]:
    """Return distinct source sentences, alternating between sources where possible."""
    per_source = [
        [
            (sentence, source["id"])
            for sentence in sentences(re.sub(r"\s+", " ", source["snippet"]))
            if len(sentence.split()) > 5
        ]
        for source in sources
    ]
    output, seen, index = [], set(), 0

    while any(per_source):
        current = per_source[index % len(per_source)]
        while current:
            sentence, source_id = current.pop(0)
            if sentence.lower() not in seen:
                seen.add(sentence.lower())
                output.append((sentence, source_id))
                break
        index += 1

    return output


def first_sentences(snippet: str, count: int = 2, max_words: int = 45) -> str:
    text = " ".join(sentences(re.sub(r"\s+", " ", snippet))[:count])
    return trim_words(text, max_words)
