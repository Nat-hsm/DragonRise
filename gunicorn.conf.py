# Gunicorn configuration file
bind = "127.0.0.1:8000"
workers = 3
timeout = 120
accesslog = "/var/log/dragonrise/access.log"
errorlog = "/var/log/dragonrise/error.log"
capture_output = True
loglevel = "info"