# Nexora School Office — public online demo on PythonAnywhere.
# Paste this whole file into the web app's WSGI configuration file and set USERNAME.
import os
import sys

USERNAME = "yourusername"  # <-- change this to your PythonAnywhere username

PROJECT = f"/home/{USERNAME}/Nexora-School"
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["SCHOOL_DEMO"] = "1"                      # fictional school, one-click sign-in, auto-reset
os.environ["SCHOOL_DEMO_RESET_HOURS"] = "24"
os.environ["SCHOOL_DATA_DIR"] = f"/home/{USERNAME}/school-demo-data"
os.environ["SCHOOL_ALLOWED_HOSTS"] = f"{USERNAME}.pythonanywhere.com"
os.environ["SCHOOL_HTTPS"] = "1"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
