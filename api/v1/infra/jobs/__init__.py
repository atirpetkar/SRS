"""
Jobs infrastructure for Step 11 background processing.

This package provides a production-ready job system with:
- Postgres-backed queue with heartbeats and visibility timeout
- Registry-based pluggable handlers
- Idempotent processing with deduplication keys
- Comprehensive error handling and retry logic
"""
