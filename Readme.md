## Project Setup

uv init Intelliversitybackend
cd Intelliversitybackend
uv python pin 3.12.3
uv venv
source .venv/bin/activate
uv add -r requirements/local.txt

#### If you add new packages and that will be used on both (dev + prod), then run:
`uv add <package name>`
#### If the new package is used only in development, then run:
`uv add --dev <package name>`

Then run
`django-admin startproject config .`

Before pushing to branch, 
run:
`black .`
`isort .`
`flake8 .`





