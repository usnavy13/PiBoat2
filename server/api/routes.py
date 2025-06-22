"""
FastAPI routes for PiBoat2 ground control server
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..database.database import get_db, get_database_manager
from ..database.models import Boat, Command, Log, GPSTrack, StatusUpdate, BoatStatus, CommandStatus
from ..mqtt.client import get_mqtt_client

app = FastAPI(title="PiBoat2 Ground Control", version="1.0.0")

class CommandRequest(BaseModel):
    command_type: str = Field(..., description="Type of command (navigation, control, status, config, emergency)")
    payload: Dict[str, Any] = Field(..., description="Command payload")
    priority: Optional[str] = Field("medium", description="Command priority (low, medium, high, critical)")
    timeout_seconds: Optional[int] = Field(30, description="Command timeout in seconds")

class BoatResponse(BaseModel):
    id: str
    boat_id: str
    name: str
    description: Optional[str]
    status: str
    last_seen: Optional[str]
    last_gps_lat: Optional[float]
    last_gps_lon: Optional[float]
    last_gps_heading: Optional[float]
    last_gps_speed: Optional[float]
    battery_level: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]

class CommandResponse(BaseModel):
    id: str
    command_id: str
    boat_id: str
    command_type: str
    payload: Dict[str, Any]
    status: str
    priority: str
    timeout_seconds: int
    created_at: Optional[str]
    sent_at: Optional[str]
    acknowledged_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]

class LogResponse(BaseModel):
    id: str
    boat_id: str
    level: str
    message: str
    details: Optional[Dict[str, Any]]
    timestamp: Optional[str]

class GPSResponse(BaseModel):
    id: str
    boat_id: str
    latitude: float
    longitude: float
    heading: Optional[float]
    speed: Optional[float]
    altitude: Optional[float]
    accuracy: Optional[float]
    timestamp: Optional[str]

@app.get("/")
async def root():
    """Health check endpoint"""
    db_manager = get_database_manager()
    mqtt_client = get_mqtt_client()
    
    return {
        "status": "ok",
        "service": "PiBoat2 Ground Control",
        "version": "1.0.0",
        "database_connected": db_manager.health_check(),
        "mqtt_connected": mqtt_client.is_connected(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/boats", response_model=List[BoatResponse])
async def list_boats(db: Session = Depends(get_db)):
    """List all registered boats"""
    try:
        boats = db.query(Boat).all()
        return [BoatResponse(**boat.to_dict()) for boat in boats]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/boats/{boat_id}", response_model=BoatResponse)
async def get_boat(boat_id: str, db: Session = Depends(get_db)):
    """Get details of a specific boat"""
    try:
        boat = db.query(Boat).filter_by(boat_id=boat_id).first()
        if not boat:
            raise HTTPException(status_code=404, detail=f"Boat {boat_id} not found")
        return BoatResponse(**boat.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/boats/{boat_id}/status")
async def get_boat_status(boat_id: str, db: Session = Depends(get_db)):
    """Get current status of a specific boat"""
    try:
        boat = db.query(Boat).filter_by(boat_id=boat_id).first()
        if not boat:
            raise HTTPException(status_code=404, detail=f"Boat {boat_id} not found")
        
        # Get latest status update
        latest_status = db.query(StatusUpdate).filter_by(boat_id=boat_id).order_by(StatusUpdate.timestamp.desc()).first()
        
        return {
            "boat_id": boat_id,
            "status": boat.status.value if boat.status else "unknown",
            "last_seen": boat.last_seen.isoformat() if boat.last_seen else None,
            "battery_level": boat.battery_level,
            "gps": {
                "latitude": float(boat.last_gps_lat) if boat.last_gps_lat else None,
                "longitude": float(boat.last_gps_lon) if boat.last_gps_lon else None,
                "heading": float(boat.last_gps_heading) if boat.last_gps_heading else None,
                "speed": float(boat.last_gps_speed) if boat.last_gps_speed else None
            },
            "latest_status_data": latest_status.status_data if latest_status else {}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/boats/{boat_id}/command")
async def send_command(boat_id: str, command: CommandRequest, db: Session = Depends(get_db)):
    """Send a command to a specific boat"""
    try:
        # Check if boat exists
        boat = db.query(Boat).filter_by(boat_id=boat_id).first()
        if not boat:
            raise HTTPException(status_code=404, detail=f"Boat {boat_id} not found")
        
        # Check if boat is online
        if boat.status != BoatStatus.ONLINE:
            raise HTTPException(status_code=400, detail=f"Boat {boat_id} is not online (status: {boat.status.value})")
        
        # Send command via MQTT
        mqtt_client = get_mqtt_client()
        if not mqtt_client.is_connected():
            raise HTTPException(status_code=503, detail="MQTT broker not connected")
        
        command_id = mqtt_client.send_command_to_boat(
            boat_id=boat_id,
            command_type=command.command_type,
            payload=command.payload,
            priority=command.priority,
            timeout_seconds=command.timeout_seconds
        )
        
        if not command_id:
            raise HTTPException(status_code=500, detail="Failed to send command")
        
        return {
            "message": "Command sent successfully",
            "command_id": command_id,
            "boat_id": boat_id,
            "command": command.dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending command: {str(e)}")

@app.get("/boats/{boat_id}/commands", response_model=List[CommandResponse])
async def get_boat_commands(
    boat_id: str,
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, description="Filter by command status"),
    db: Session = Depends(get_db)
):
    """Get command history for a specific boat"""
    try:
        query = db.query(Command).filter_by(boat_id=boat_id)
        
        if status:
            try:
                status_enum = CommandStatus(status)
                query = query.filter_by(status=status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        commands = query.order_by(Command.created_at.desc()).limit(limit).all()
        return [CommandResponse(**cmd.to_dict()) for cmd in commands]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/boats/{boat_id}/logs", response_model=List[LogResponse])
async def get_boat_logs(
    boat_id: str,
    limit: int = Query(100, ge=1, le=1000),
    level: Optional[str] = Query(None, description="Filter by log level"),
    hours: Optional[int] = Query(None, ge=1, le=168, description="Filter logs from last N hours"),
    db: Session = Depends(get_db)
):
    """Get recent logs from a specific boat"""
    try:
        query = db.query(Log).filter_by(boat_id=boat_id)
        
        if level:
            query = query.filter_by(level=level)
        
        if hours:
            since = datetime.now() - timedelta(hours=hours)
            query = query.filter(Log.timestamp >= since)
        
        logs = query.order_by(Log.timestamp.desc()).limit(limit).all()
        return [LogResponse(**log.to_dict()) for log in logs]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/boats/{boat_id}/gps", response_model=List[GPSResponse])
async def get_boat_gps_track(
    boat_id: str,
    limit: int = Query(100, ge=1, le=1000),
    hours: Optional[int] = Query(None, ge=1, le=168, description="Filter GPS data from last N hours"),
    db: Session = Depends(get_db)
):
    """Get GPS track for a specific boat"""
    try:
        query = db.query(GPSTrack).filter_by(boat_id=boat_id)
        
        if hours:
            since = datetime.now() - timedelta(hours=hours)
            query = query.filter(GPSTrack.timestamp >= since)
        
        tracks = query.order_by(GPSTrack.timestamp.desc()).limit(limit).all()
        return [GPSResponse(**track.to_dict()) for track in tracks]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/boats/{boat_id}/gps/latest")
async def get_latest_gps(boat_id: str, db: Session = Depends(get_db)):
    """Get the latest GPS position for a specific boat"""
    try:
        latest_track = db.query(GPSTrack).filter_by(boat_id=boat_id).order_by(GPSTrack.timestamp.desc()).first()
        
        if not latest_track:
            raise HTTPException(status_code=404, detail=f"No GPS data found for boat {boat_id}")
        
        return GPSResponse(**latest_track.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/system/status")
async def get_system_status():
    """Get overall system status"""
    try:
        db_manager = get_database_manager()
        mqtt_client = get_mqtt_client()
        
        with db_manager.session_scope() as db:
            total_boats = db.query(Boat).count()
            online_boats = db.query(Boat).filter_by(status=BoatStatus.ONLINE).count()
            offline_boats = db.query(Boat).filter_by(status=BoatStatus.OFFLINE).count()
            
            # Get recent command stats
            recent_commands = db.query(Command).filter(
                Command.created_at >= datetime.now() - timedelta(hours=24)
            ).count()
            
            pending_commands = db.query(Command).filter_by(status=CommandStatus.PENDING).count()
        
        return {
            "system": {
                "status": "operational",
                "database_connected": db_manager.health_check(),
                "mqtt_connected": mqtt_client.is_connected(),
                "timestamp": datetime.now().isoformat()
            },
            "boats": {
                "total": total_boats,
                "online": online_boats,
                "offline": offline_boats,
                "connected_boats": mqtt_client.get_connected_boats()
            },
            "commands": {
                "recent_24h": recent_commands,
                "pending": pending_commands
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"System status error: {str(e)}")

@app.post("/boats/{boat_id}/emergency_stop")
async def emergency_stop(boat_id: str, db: Session = Depends(get_db)):
    """Emergency stop command for a specific boat"""
    try:
        # Check if boat exists and is online
        boat = db.query(Boat).filter_by(boat_id=boat_id).first()
        if not boat:
            raise HTTPException(status_code=404, detail=f"Boat {boat_id} not found")
        
        # Send emergency stop command
        mqtt_client = get_mqtt_client()
        if not mqtt_client.is_connected():
            raise HTTPException(status_code=503, detail="MQTT broker not connected")
        
        command_id = mqtt_client.send_command_to_boat(
            boat_id=boat_id,
            command_type="emergency",
            payload={"action": "emergency_stop", "reason": "user_initiated"},
            priority="critical",
            timeout_seconds=5
        )
        
        if not command_id:
            raise HTTPException(status_code=500, detail="Failed to send emergency stop command")
        
        return {
            "message": "Emergency stop command sent",
            "command_id": command_id,
            "boat_id": boat_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending emergency stop: {str(e)}")