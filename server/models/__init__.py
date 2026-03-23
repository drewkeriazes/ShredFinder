"""Import all models so SQLAlchemy mapper resolves relationships."""

from server.models.base import Base  # noqa: F401
from server.models.user import User  # noqa: F401
from server.models.media import Media  # noqa: F401
from server.models.project import Project, Clip  # noqa: F401
