from flask import Blueprint, render_template

# Create the blueprint
healthcheck_ui_bp = Blueprint(
    "healthcheck_ui",   # blueprint name (used by url_for)
    __name__,
    template_folder="static"
)

# Route for a single page at /healthcheck/
@healthcheck_ui_bp.route("/")
def healthcheck_ui_index():
    # This file should exist in the templates folder
    return render_template("healthcheck_ui.html")