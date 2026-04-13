import re
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_MENTION_RE = re.compile(r'@([\w.-]+)')


@register.filter(is_safe=True, needs_autoescape=True)
def linkify_mentions(value, autoescape=True):
    """Render @handle references as clickable profile links."""
    escaped = escape(value) if autoescape else value

    def replace(match):
        handle = match.group(1)
        safe_handle = escape(handle)
        return f'<a class="mention" href="/actors/{safe_handle}/">@{safe_handle}</a>'

    return mark_safe(_MENTION_RE.sub(replace, escaped))
