"""Service-system helpers for the separated API + frontend architecture."""

from flask import Blueprint

from .api import register_service_api_routes
from .frontend import register_service_frontend_routes


def create_service_system_blueprint(api_deps_factory):
    blueprint = Blueprint("service_system", __name__)
    register_service_frontend_routes(blueprint)
    register_service_api_routes(blueprint, api_deps_factory)
    return blueprint


__all__ = ["create_service_system_blueprint"]
