"""Middleware package for A2A server."""

from .ias_auth import IASAuthMiddleware

__all__ = ['IASAuthMiddleware']
