#!/usr/bin/env python3
"""
PiBoat2 Main Application
Boat-side control system with MQTT communication
"""

import sys
import signal
import logging
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

def setup_logging():
    """Configure logging for the boat application"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('/var/log/piboat2.log'),
            logging.StreamHandler()
        ]
    )

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logging.info("Received shutdown signal, stopping boat systems...")
    # TODO: Implement graceful shutdown
    sys.exit(0)

def main():
    """Main application entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting PiBoat2 control system...")
    
    try:
        # TODO: Initialize hardware components
        # TODO: Initialize MQTT client
        # TODO: Start navigation controller
        # TODO: Start status reporter
        
        logger.info("PiBoat2 system initialized successfully")
        
        # Keep the main thread alive
        while True:
            signal.pause()
            
    except Exception as e:
        logger.error(f"Fatal error in main application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()