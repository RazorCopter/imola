"""Impostazioni per pytest: hashing veloce, niente throttling, niente log."""

from .dev import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}
