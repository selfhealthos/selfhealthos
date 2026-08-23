"""Wearable provider adapters.

One module per provider. Everything provider-specific - OAuth URLs, endpoint
paths, response shapes, rate limits - lives behind these; `connections.py`
orchestrates and knows none of it, which is what makes Withings or Strava a new
file rather than a new subsystem.
"""
