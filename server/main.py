#!/usr/bin/env python3
"""
PiBoat2 Server Application
Ground control station with web interface and MQTT broker connection
"""

import sys
import signal
import logging
import asyncio
import threading
import time
import os
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.config.config import get_config
from server.database.database import init_database, get_database_manager
from server.mqtt.client import get_mqtt_client
from server.api.routes import app as api_app


class PiBoat2Server:
    """Main PiBoat2 server application"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)
        self.db_manager = get_database_manager()
        self.mqtt_client = get_mqtt_client()
        self._shutdown_event = threading.Event()
        self._mqtt_thread = None
        
    def setup_logging(self):
        """Configure logging for the server application"""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/piboat2-server.log'),
                logging.StreamHandler()
            ]
        )
        
        # Set third-party library log levels
        logging.getLogger('uvicorn').setLevel(logging.WARNING)
        logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        
    def initialize_database(self):
        """Initialize database connection and create tables"""
        try:
            self.logger.info("Initializing database...")
            init_database()
            
            # Test database connection
            if self.db_manager.health_check():
                self.logger.info("Database connection established successfully")
            else:
                raise Exception("Database health check failed")
                
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise
    
    def initialize_mqtt(self):
        """Initialize MQTT client in separate thread"""
        def mqtt_worker():
            try:
                self.logger.info("Initializing MQTT client...")
                if self.mqtt_client.connect():
                    self.logger.info("MQTT client connected successfully")
                    
                    # Keep MQTT client running
                    while not self._shutdown_event.is_set():
                        time.sleep(1)
                else:
                    self.logger.error("MQTT client connection failed")
                    
            except Exception as e:
                self.logger.error(f"MQTT client error: {e}")
        
        self._mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
        self._mqtt_thread.start()
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self._shutdown_event.set()
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def startup(self):
        """Server startup tasks"""
        self.logger.info("Starting PiBoat2 ground control server...")
        
        try:
            # Setup logging
            self.setup_logging()
            
            # Setup signal handlers
            self.setup_signal_handlers()
            
            # Initialize database
            self.initialize_database()
            
            # Initialize MQTT client
            self.initialize_mqtt()
            
            self.logger.info("PiBoat2 server initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Server startup failed: {e}")
            raise
    
    async def shutdown(self):
        """Server shutdown tasks"""
        self.logger.info("Shutting down PiBoat2 server...")
        
        try:
            # Signal shutdown to all components
            self._shutdown_event.set()
            
            # Disconnect MQTT client
            if self.mqtt_client:
                self.mqtt_client.disconnect()
            
            # Wait for MQTT thread to finish
            if self._mqtt_thread and self._mqtt_thread.is_alive():
                self._mqtt_thread.join(timeout=5)
            
            # Close database connections
            if self.db_manager:
                self.db_manager.close()
            
            self.logger.info("PiBoat2 server shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")


# Global server instance
server_instance = PiBoat2Server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager"""
    # Startup
    await server_instance.startup()
    yield
    # Shutdown
    await server_instance.shutdown()


# Create FastAPI app with lifespan management
app = FastAPI(
    title="PiBoat2 Ground Control",
    version="1.0.0",
    description="Ground control station for PiBoat2 autonomous boat system",
    lifespan=lifespan
)

# Include API routes
app.mount("/api/v1", api_app)

# Mount static files
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

# Add root endpoint that serves the web interface
@app.get("/")
async def root():
    """Root endpoint - serve web interface"""
    from fastapi.responses import FileResponse
    web_file = Path(__file__).parent / "web" / "index.html"
    if web_file.exists():
        return FileResponse(str(web_file))
    else:
        return {
            "service": "PiBoat2 Ground Control",
            "version": "1.0.0",
            "api_docs": "/docs",
            "api_v1": "/api/v1/"
        }


def main():
    """Main server application entry point"""
    try:
        # Load environment variables from .env file
        load_dotenv(Path(__file__).parent.parent / '.env')
        
        config = get_config()
        
        # Run the server
        uvicorn.run(
            "server.main:app",
            host=config.server.host,
            port=config.server.port,
            reload=config.environment == "development",
            log_level="warning",  # Let our custom logging handle output
            access_log=False
        )
        
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Fatal error in server application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()