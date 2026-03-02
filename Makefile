.PHONY: up down build logs seed reset tunnel demo status poll

ifneq (,$(wildcard ./.env))
include .env
export
endif

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f reactive-intelligence

seed:
	@test -n "$(MONGODB_URI)" || (echo "MONGODB_URI is required. Add it to .env" && exit 1)
	MONGODB_URI="$(MONGODB_URI)" MONGODB_DATABASE="$(MONGODB_DATABASE)" python3 setup/seed.py

reset:
	python3 demo.py reset

tunnel:
	cloudflared tunnel --url http://localhost:8092

demo:
	python3 demo.py clean

status:
	python3 demo.py status

ID ?=
poll:
	@test -n "$(ID)" || (echo "Usage: make poll ID=<execution_id>" && exit 1)
	@curl -s http://localhost:8092/api/v1/executions/$(ID) | python3 -m json.tool
