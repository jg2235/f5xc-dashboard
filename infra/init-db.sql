-- Enable TimescaleDB for future analytics hypertables (slice 4+)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- gen_random_uuid() support
CREATE EXTENSION IF NOT EXISTS pgcrypto;
