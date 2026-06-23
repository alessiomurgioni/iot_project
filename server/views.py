"""HTML pages served to the browser."""
from flask import Blueprint, render_template, session

from auth import login_required

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", username=session["user"])
