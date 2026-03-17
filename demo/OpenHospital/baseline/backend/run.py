#!/usr/bin/env python3
"""Script to run the Hospital Simulation Backend API."""

import uvicorn

from config import settings


def main():
    """Run the FastAPI server."""
    print(f"Starting Hospital Simulation Backend API on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()

