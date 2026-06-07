"""WSGI entry point.

Run in development:  flask --app wsgi run
Run in production:   gunicorn wsgi:app
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Local convenience only. Production uses gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=5000)
