"""Standard pagination with strict size bounds (FND-4, SEC-5)."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class DefaultPagination(PageNumberPagination):
    """Bounded page-number pagination with uniform envelope."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: list[object]) -> Response:
        if self.page is None:
            raise RuntimeError("Pagination page is not initialized.")
        req = self.request
        page_size = self.get_page_size(req) if req is not None else self.page_size
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": page_size,
                "results": data,
            }
        )
