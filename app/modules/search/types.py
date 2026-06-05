from __future__ import annotations

from app.modules.search.schemas import SearchType
from app.shared.exceptions import ValidationError


def parse_search_types(raw: str | None) -> set[SearchType]:
    if raw is None or not raw.strip():
        return {SearchType.CONTACTS, SearchType.MESSAGES, SearchType.CHATS}

    result: set[SearchType] = set()
    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue
        try:
            result.add(SearchType(token))
        except ValueError as exc:
            raise ValidationError(
                message=f"Unknown search type: {token}",
                details={"allowed": [t.value for t in SearchType]},
            ) from exc

    if not result:
        raise ValidationError(message="At least one search type is required")
    return result
