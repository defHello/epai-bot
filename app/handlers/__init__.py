from .client import router as client_router
from .admin import router as admin_router
from .admin_commands import router as admin_commands_router

__all__ = ["client_router", "admin_router", "admin_commands_router"]