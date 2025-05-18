from flask import json, Markup

def tojson_filter(obj):
    """Convert a Python object to a JSON string suitable for embedding in HTML."""
    return Markup(json.dumps(obj))