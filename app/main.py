import logging
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
from pathlib import Path

# Set up path for imports
current_dir = Path(__file__).parent
sys.path.append(str(current_dir.parent))

from app.config import config
from app.routers import entries
from app.services import database, librelinkup

# Configure logging
logging.basicConfig(
    level=getattr(logging, config['log_level'], logging.INFO),
    format='[%(levelname)s][%(asctime)s][%(name)s]: %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Mini Nightscout",
    description="A lightweight alternative to Nightscout for LibreLink Up data",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Mount static files
static_path = Path(current_dir, "static")
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
else:
    logger.warning(f"Static directory not found at {static_path}")


# Dependency to check database connection
async def check_db_connection():
    try:
        # Test database connection by getting latest reading
        database.get_latest_reading()
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")


# Include routers
app.include_router(entries.router, dependencies=[Depends(check_db_connection)])


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the index.html page."""
    index_path = Path(static_path, "index.html")
    if index_path.exists():
        with open(index_path, "r") as f:
            return f.read()
    else:
        # Return a simple HTML page if index.html doesn't exist
        return """
        <!DOCTYPE html>
        <html>
            <head>
                <title>Mini Nightscout</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f5f5f5;
                    }
                    .container {
                        max-width: 800px;
                        margin: 0 auto;
                        background-color: white;
                        padding: 20px;
                        border-radius: 5px;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    }
                    h1 {
                        color: #3273dc;
                    }
                    p {
                        margin-bottom: 15px;
                    }
                    code {
                        background-color: #f5f5f5;
                        padding: 2px 5px;
                        border-radius: 3px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Mini Nightscout</h1>
                    <p>Welcome to Mini Nightscout, a lightweight alternative to Nightscout for LibreLink Up data.</p>
                    <p>API endpoints:</p>
                    <ul>
                        <li><code>/api/entries/latest</code> - Get the latest glucose reading</li>
                        <li><code>/api/entries?hours=24</code> - Get glucose readings for the last 24 hours</li>
                        <li><code>/api/entries/stats?hours=24</code> - Get glucose statistics for the last 24 hours</li>
                    </ul>
                </div>
            </body>
        </html>
        """


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        database.get_latest_reading()
        
        # Return health status
        return {"status": "healthy", "services": {"database": "connected"}}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "error": str(e)}
        )


@app.get("/test-llu-connection")
async def test_llu_connection():
    """Test LibreLink Up connection."""
    try:
        # Test LibreLink Up connection
        session = librelinkup.requests.Session()
        login_result = librelinkup.login(session)
        
        if not login_result:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Failed to login to LibreLink Up"}
            )
        
        connections = librelinkup.get_connections(session)
        if not connections:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Failed to get LibreLink Up connections"}
            )
        
        # Format connections list for response
        formatted_connections = []
        for conn in connections:
            formatted_connections.append({
                "patientId": conn.get("patientId"),
                "firstName": conn.get("firstName"),
                "lastName": conn.get("lastName")
            })
        
        return {
            "status": "success",
            "message": "Successfully connected to LibreLink Up",
            "connections": formatted_connections
        }
    except Exception as e:
        logger.error(f"LibreLink Up connection test failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


# Startup event to initialize services
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting Mini Nightscout application")
    
    try:
        # Initialize database connection
        database.get_database()
        logger.info("Database connection initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database connection: {e}")


# Shutdown event to clean up resources
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down Mini Nightscout application")
    
    # Close database connection
    database.close_connection()
    logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )