#!/usr/bin/env python3
"""
SQLAlchemy database models for PiBoat2 server
Defines database schema for boats, commands, logs, and telemetry data
"""

import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, ForeignKey, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid


# Base class for all models
Base = declarative_base()


# Enum definitions
class BoatStatus(enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class CommandStatus(enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CommandType(enum.Enum):
    NAVIGATION = "navigation"
    CONTROL = "control"
    STATUS = "status"
    CONFIG = "config"
    EMERGENCY = "emergency"


class LogLevel(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Boat(Base):
    """Boat registration and status model"""
    __tablename__ = 'boats'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    boat_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(ENUM(BoatStatus), default=BoatStatus.OFFLINE, index=True)
    last_seen = Column(DateTime(timezone=True), index=True)
    
    # Last known GPS position
    last_gps_lat = Column(Numeric(10, 8))
    last_gps_lon = Column(Numeric(11, 8))
    last_gps_heading = Column(Numeric(5, 2))
    last_gps_speed = Column(Numeric(5, 2))
    
    # System status
    battery_level = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    commands = relationship("Command", back_populates="boat", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="boat", cascade="all, delete-orphan")
    gps_tracks = relationship("GPSTrack", back_populates="boat", cascade="all, delete-orphan")
    status_updates = relationship("StatusUpdate", back_populates="boat", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Boat(boat_id='{self.boat_id}', name='{self.name}', status='{self.status}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert boat to dictionary representation"""
        return {
            'id': str(self.id),
            'boat_id': self.boat_id,
            'name': self.name,
            'description': self.description,
            'status': self.status.value if self.status else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'last_gps_lat': float(self.last_gps_lat) if self.last_gps_lat else None,
            'last_gps_lon': float(self.last_gps_lon) if self.last_gps_lon else None,
            'last_gps_heading': float(self.last_gps_heading) if self.last_gps_heading else None,
            'last_gps_speed': float(self.last_gps_speed) if self.last_gps_speed else None,
            'battery_level': self.battery_level,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Command(Base):
    """Command tracking model"""
    __tablename__ = 'commands'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id = Column(String(100), unique=True, nullable=False, index=True)
    boat_id = Column(String(50), ForeignKey('boats.boat_id', ondelete='CASCADE'), nullable=False, index=True)
    command_type = Column(ENUM(CommandType), nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(ENUM(CommandStatus), default=CommandStatus.PENDING, index=True)
    priority = Column(String(20), default='medium')
    timeout_seconds = Column(Integer, default=30)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at = Column(DateTime(timezone=True))
    acknowledged_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Error handling
    error_message = Column(Text)
    
    # Relationships
    boat = relationship("Boat", back_populates="commands")
    
    def __repr__(self):
        return f"<Command(command_id='{self.command_id}', boat_id='{self.boat_id}', type='{self.command_type}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert command to dictionary representation"""
        return {
            'id': str(self.id),
            'command_id': self.command_id,
            'boat_id': self.boat_id,
            'command_type': self.command_type.value if self.command_type else None,
            'payload': self.payload,
            'status': self.status.value if self.status else None,
            'priority': self.priority,
            'timeout_seconds': self.timeout_seconds,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message
        }


class Log(Base):
    """Log entries model"""
    __tablename__ = 'logs'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    boat_id = Column(String(50), ForeignKey('boats.boat_id', ondelete='CASCADE'), index=True)
    level = Column(ENUM(LogLevel), nullable=False, index=True)
    message = Column(Text, nullable=False)
    details = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    boat = relationship("Boat", back_populates="logs")
    
    def __repr__(self):
        return f"<Log(boat_id='{self.boat_id}', level='{self.level}', message='{self.message[:50]}...')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert log to dictionary representation"""
        return {
            'id': str(self.id),
            'boat_id': self.boat_id,
            'level': self.level.value if self.level else None,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class GPSTrack(Base):
    """GPS position tracking model"""
    __tablename__ = 'gps_tracks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    boat_id = Column(String(50), ForeignKey('boats.boat_id', ondelete='CASCADE'), nullable=False, index=True)
    latitude = Column(Numeric(10, 8), nullable=False)
    longitude = Column(Numeric(11, 8), nullable=False)
    heading = Column(Numeric(5, 2))
    speed = Column(Numeric(5, 2))
    altitude = Column(Numeric(8, 2))
    accuracy = Column(Numeric(5, 2))
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    boat = relationship("Boat", back_populates="gps_tracks")
    
    def __repr__(self):
        return f"<GPSTrack(boat_id='{self.boat_id}', lat={self.latitude}, lon={self.longitude})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert GPS track to dictionary representation"""
        return {
            'id': str(self.id),
            'boat_id': self.boat_id,
            'latitude': float(self.latitude) if self.latitude else None,
            'longitude': float(self.longitude) if self.longitude else None,
            'heading': float(self.heading) if self.heading else None,
            'speed': float(self.speed) if self.speed else None,
            'altitude': float(self.altitude) if self.altitude else None,
            'accuracy': float(self.accuracy) if self.accuracy else None,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class StatusUpdate(Base):
    """Boat status update model"""
    __tablename__ = 'status_updates'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    boat_id = Column(String(50), ForeignKey('boats.boat_id', ondelete='CASCADE'), nullable=False, index=True)
    status_data = Column(JSONB, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    boat = relationship("Boat", back_populates="status_updates")
    
    def __repr__(self):
        return f"<StatusUpdate(boat_id='{self.boat_id}', timestamp='{self.timestamp}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert status update to dictionary representation"""
        return {
            'id': str(self.id),
            'boat_id': self.boat_id,
            'status_data': self.status_data,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }