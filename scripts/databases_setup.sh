#!/bin/bash

# Load environment variables (handling spaces and special characters safely)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# Exit immediately if a command exits with a non-zero status, treat unset variables as an error, and prevent errors in a pipeline from being masked
set -euo pipefail

# Enable automatic exporting, source the .env file, then disable it
set -a
source "$PROJECT_ROOT/.env"
set +a

# Set default values if not provided in .env
DB_HOST=${MAIN_POSTGRES_HOST:-localhost}
DB_PORT=${MAIN_POSTGRES_PORT:-5432}

echo "Creating tenant databases..."

# Use a heredoc to pass all SQL commands in a single session
PGPASSWORD="$MAIN_POSTGRES_PASSWORD" psql -U "$MAIN_POSTGRES_USER" -h "$DB_HOST" -p "$DB_PORT" -d postgres <<EOF
  -- Intelliversity Main DB
  DROP DATABASE IF EXISTS intelliversity_main_db;
  CREATE DATABASE intelliversity_main_db;
  GRANT ALL PRIVILEGES ON DATABASE intelliversity_main_db TO $MAIN_POSTGRES_USER;

  -- Intelliversity FAST DB
  DROP DATABASE IF EXISTS intelliversity_fast;
  CREATE DATABASE intelliversity_fast;
  GRANT ALL PRIVILEGES ON DATABASE intelliversity_fast TO $MAIN_POSTGRES_USER;

  -- Intelliversity COMSATS DB
  DROP DATABASE IF EXISTS intelliversity_comsats;
  CREATE DATABASE intelliversity_comsats;
  GRANT ALL PRIVILEGES ON DATABASE intelliversity_comsats TO $MAIN_POSTGRES_USER;
EOF

echo "Databases (old)deleted and (new)created successfully."