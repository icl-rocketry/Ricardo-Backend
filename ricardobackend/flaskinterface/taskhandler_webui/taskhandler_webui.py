from flask import Blueprint, render_template, abort

taskhandler_webui_bp = Blueprint('taskhandler_webui_bp', __name__,
    template_folder='static',
    static_folder='static',
    static_url_path='')

@taskhandler_webui_bp.route('/')
def taskhandler_webui_index():
    return render_template('taskhandler_webui.html')