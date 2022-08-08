from flask import Blueprint, render_template

command_webui_bp = Blueprint('command_webui_bp',__name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/command_webui/static')

@command_webui_bp.route("/command_webui")
def command_webui_index():
    return render_template('index.html')

