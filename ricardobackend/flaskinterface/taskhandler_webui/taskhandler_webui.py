from flask import Blueprint, render_template, abort

taskhandler_webui_bp = Blueprint('taskhandler_webui_bp', __name__,
    template_folder='TaskHandler/build',
    static_folder='TaskHandler/build',
    static_url_path='')

@taskhandler_webui_bp.route('/')
def taskhandler_webui_index():
    return render_template('index.html')