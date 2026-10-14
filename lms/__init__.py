"""Septaneuron intern LMS — mounted at /portal."""
from flask import Blueprint

bp = Blueprint("lms", __name__, url_prefix="/portal")

from . import utils, auth_routes, intern_routes, admin_routes  # noqa: E402,F401
