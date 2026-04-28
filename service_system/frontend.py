from __future__ import annotations

from flask import render_template


def register_service_frontend_routes(blueprint):
    @blueprint.route("/service")
    @blueprint.route("/service/<path:subpath>")
    def service_frontend(subpath=""):
        return render_template("service_app.html")
