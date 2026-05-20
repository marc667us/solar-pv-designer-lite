"""WSGI entry point for Render / gunicorn."""
from dotenv import load_dotenv
load_dotenv()
from web_app import app, init_db
init_db()

if __name__ == "__main__":
    app.run()
