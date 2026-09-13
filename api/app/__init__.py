"""Marks this folder as a Python package.

Intentionally empty of code. Python only treats a folder as importable (package) 
when this file exists, and that is what makes `from app.config import settings`
resolve when the server is started from the api/ directory.
"""
