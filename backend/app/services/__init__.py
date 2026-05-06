"""Service layer — pure business logic, no HTTP coupling.

Modules here are called by:
  - app.api.* (REST API routes — adds HTTP semantics)
  - backend/scripts/*_cli.py (CLI tools — adds prompts/output)

Same logic, different transport surfaces.
"""
