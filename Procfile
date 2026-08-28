# Unused on Railway, which builds from the Dockerfile -- kept in step with it
# so a nixpacks/Heroku-style deploy gets the same timeouts.
web: gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 4 --timeout 300 --graceful-timeout 30
