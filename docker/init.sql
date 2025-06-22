-- PiBoat2 Database Initialization Script
-- This script sets up initial database structure and data

-- Enable UUID extension for generating unique IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create enum types
CREATE TYPE boat_status AS ENUM ('online', 'offline', 'error', 'maintenance');
CREATE TYPE command_status AS ENUM ('pending', 'sent', 'acknowledged', 'completed', 'failed', 'timeout');
CREATE TYPE command_type AS ENUM ('navigation', 'control', 'status', 'config', 'emergency');
CREATE TYPE log_level AS ENUM ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL');

-- Boats table
CREATE TABLE IF NOT EXISTS boats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    boat_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    status boat_status DEFAULT 'offline',
    last_seen TIMESTAMP WITH TIME ZONE,
    last_gps_lat DECIMAL(10, 8),
    last_gps_lon DECIMAL(11, 8),
    last_gps_heading DECIMAL(5, 2),
    last_gps_speed DECIMAL(5, 2),
    battery_level INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Commands table
CREATE TABLE IF NOT EXISTS commands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    command_id VARCHAR(100) UNIQUE NOT NULL,
    boat_id VARCHAR(50) NOT NULL REFERENCES boats(boat_id) ON DELETE CASCADE,
    command_type command_type NOT NULL,
    payload JSONB NOT NULL,
    status command_status DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'medium',
    timeout_seconds INTEGER DEFAULT 30,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

-- Logs table
CREATE TABLE IF NOT EXISTS logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    boat_id VARCHAR(50) REFERENCES boats(boat_id) ON DELETE CASCADE,
    level log_level NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- GPS tracks table for storing position history
CREATE TABLE IF NOT EXISTS gps_tracks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    boat_id VARCHAR(50) NOT NULL REFERENCES boats(boat_id) ON DELETE CASCADE,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    heading DECIMAL(5, 2),
    speed DECIMAL(5, 2),
    altitude DECIMAL(8, 2),
    accuracy DECIMAL(5, 2),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Status updates table for storing boat telemetry
CREATE TABLE IF NOT EXISTS status_updates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    boat_id VARCHAR(50) NOT NULL REFERENCES boats(boat_id) ON DELETE CASCADE,
    status_data JSONB NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_boats_boat_id ON boats(boat_id);
CREATE INDEX IF NOT EXISTS idx_boats_status ON boats(status);
CREATE INDEX IF NOT EXISTS idx_boats_last_seen ON boats(last_seen);

CREATE INDEX IF NOT EXISTS idx_commands_boat_id ON commands(boat_id);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
CREATE INDEX IF NOT EXISTS idx_commands_created_at ON commands(created_at);
CREATE INDEX IF NOT EXISTS idx_commands_command_id ON commands(command_id);

CREATE INDEX IF NOT EXISTS idx_logs_boat_id ON logs(boat_id);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);

CREATE INDEX IF NOT EXISTS idx_gps_tracks_boat_id ON gps_tracks(boat_id);
CREATE INDEX IF NOT EXISTS idx_gps_tracks_timestamp ON gps_tracks(timestamp);

CREATE INDEX IF NOT EXISTS idx_status_updates_boat_id ON status_updates(boat_id);
CREATE INDEX IF NOT EXISTS idx_status_updates_timestamp ON status_updates(timestamp);

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to automatically update updated_at
CREATE TRIGGER update_boats_updated_at BEFORE UPDATE ON boats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert a default test boat for development
INSERT INTO boats (boat_id, name, description, status) 
VALUES ('piboat2_001', 'PiBoat2 Test Unit', 'Development and testing boat', 'offline')
ON CONFLICT (boat_id) DO NOTHING;