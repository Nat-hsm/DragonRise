"""Gunicorn configuration file"""
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None

# Logging
errorlog = '/var/log/dragonrise/error.log'
accesslog = '/var/log/dragonrise/access.log'
loglevel = 'info'