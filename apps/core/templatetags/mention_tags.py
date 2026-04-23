import re
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_TOKEN_RE = re.compile(
    r'(?P<url>(?:https?://|www\.)[^\s<]+|(?<!@)(?<![\w.])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?::\d{2,5})?(?:/[^\s<]*)?)|(?P<mention>(?<![\w.])@(?P<handle>[\w.-]+))|(?P<hashtag>#(?P<tag>[A-Za-z0-9_]+))'
)
_TRAILING_URL_PUNCTUATION = '.,!?;:'


def _split_url_suffix(url: str) -> tuple[str, str]:
    trailing = []
    while url and url[-1] in _TRAILING_URL_PUNCTUATION:
        trailing.append(url[-1])
        url = url[:-1]

    closing_parens = 0
    while url and url[-1] == ')':
        closing_parens += 1
        url = url[:-1]

    opening_parens = url.count('(')
    matched_closing = min(opening_parens, closing_parens)
    if matched_closing:
        url += ')' * matched_closing
        closing_parens -= matched_closing

    suffix = ')' * closing_parens + ''.join(reversed(trailing))
    return url, suffix


@register.filter(is_safe=True, needs_autoescape=True)
def linkify_mentions(value, autoescape=True):
    """Render URLs, @handles, and #hashtags as clickable links."""
    text = '' if value is None else str(value)
    parts = []
    last_end = 0

    for match in _TOKEN_RE.finditer(text):
        start, end = match.span()
        if start > last_end:
            parts.append(escape(text[last_end:start]) if autoescape else text[last_end:start])

        raw_token = match.group(0)
        if match.group('url'):
            url_text, suffix = _split_url_suffix(raw_token)
            if url_text:
                safe_label = escape(url_text) if autoescape else url_text
                href = url_text if url_text.startswith(('http://', 'https://')) else f'https://{url_text}'
                safe_href = escape(href) if autoescape else href
                parts.append(
                    f'<a class="external-link" href="{safe_href}" target="_blank" rel="nofollow noopener noreferrer">{safe_label}</a>'
                )
                if suffix:
                    parts.append(escape(suffix) if autoescape else suffix)
            else:
                parts.append(escape(raw_token) if autoescape else raw_token)
        elif match.group('mention'):
            handle = match.group('handle')
            safe_handle = escape(handle) if autoescape else handle
            parts.append(f'<a class="mention" href="/actors/{safe_handle}/">@{safe_handle}</a>')
        else:
            tag = match.group('tag')
            safe_tag = escape(tag) if autoescape else tag
            parts.append(f'<a class="hashtag" href="/actors/search/?q=%23{safe_tag}">#{safe_tag}</a>')

        last_end = end

    if last_end < len(text):
        parts.append(escape(text[last_end:]) if autoescape else text[last_end:])

    return mark_safe(''.join(parts))  # nosec B308 - tokens and intervening text are escaped before joining.
