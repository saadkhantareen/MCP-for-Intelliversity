#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Running database setup..."
bash "$SCRIPT_DIR/databases_setup.sh"

echo "Database setup completed."


echo "Creating Django migrations..."
python3 manage.py makemigrations

echo "Applying Django migrations..."
python3 manage.py migrate

commands=(
  seed_tenants
  migrate_tenants
  seed_roles
  seed_admin_users
  seed_academic_structure
  seed_calender
  seed_batches
  seed_students_and_faculty
  seed_sections
)

for command in "${commands[@]}"; do
  echo "Running: python manage.py $command"
  python manage.py "$command"
done

echo "Data seed pipeline completed successfully."