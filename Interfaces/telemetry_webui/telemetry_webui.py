from re import L
from flask import Blueprint, render_template

telemetry_webui_bp = Blueprint('command_webui_bp',__name__,
    template_folder='static',
    static_folder='static',
    static_url_path='')

@telemetry_webui_bp.route("/")
def command_webui_index():
    return render_template('index.html')

@telemetry_webui_bp.route("/test")
def test_page():
    return render_template('dummy-signal.html')