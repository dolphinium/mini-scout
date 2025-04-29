"""
Main FastAPI application module.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Add parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import application components
from app.config import get_config
from app.routers import entries

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Get configuration
config = get_config()

# Create FastAPI app
app = FastAPI(
    title="Mini Nightscout API",
    description="A simple API for accessing LibreLink Up glucose data",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(entries.router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint that redirects to the frontend."""
    return {"message": "Welcome to Mini Nightscout API. Visit /static for the frontend."}


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "version": "0.1.0",
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "detail": str(exc)},
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("Starting Mini Nightscout API")
    
    # You could add initial connection checks here
    # For example, ensure MongoDB is accessible
    
    logger.info("Mini Nightscout API started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Mini Nightscout API")
    
    # Close any open connections
    from app.services.database import db_service
    db_service.close()
    
    logger.info("Mini Nightscout API shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)