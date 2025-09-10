from app import app

# Gunicorn, by default, looks for a variable called 'application' in this file.
# We are assigning our Flask app instance to it.
application = app
