from __future__ import annotations

from django.core.paginator import EmptyPage, Page, Paginator
from django.http import HttpRequest


def paginate_queryset(request: HttpRequest, queryset, per_page: int = 20, page_param: str = "page") -> Page:
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get(page_param, "1")
    try:
        return paginator.page(page_number)
    except EmptyPage:
        return paginator.page(paginator.num_pages)
