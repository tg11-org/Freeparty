import re
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_MENTION_RE = re.compile(r'@([\w.-]+)')
_HASHTAG_RE = re.compile(r'#([A-Za-z0-9_]+)')


@register.filter(is_safe=True, needs_autoescape=True)
def linkify_mentions(value, autoescape=True):
    """Render @handles and #hashtags as clickable links."""
    escaped = escape(value) if autoescape else value

    def replace(match):
        handle = match.group(1)
        safe_handle = escape(handle)
        return f'<a class="mention" href="/actors/{safe_handle}/">@{safe_handle}</a>'

    linked_mentions = _MENTION_RE.sub(replace, escaped)

    def replace_hashtag(match):
        tag = match.group(1)
        safe_tag = escape(tag)
        return f'<a class="hashtag" href="/actors/search/?q=%23{safe_tag}">#{safe_tag}</a>'

    return mark_safe(_HASHTAG_RE.sub(replace_hashtag, linked_mentions))
