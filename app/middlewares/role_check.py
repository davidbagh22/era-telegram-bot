from app.database.models import User


def has_role(user: User | None, allowed: set[str]) -> bool:
    return bool(user and not user.is_blocked and user.role in allowed)
