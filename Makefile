.PHONY: up down build logs seed demo reset status tunnel list poll

ifneq (,$(wildcard ./.env))
include .env
export
endif

DOMAIN ?= finance
SCENARIO ?= clean

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
	python3 setup/seed.py $(DOMAIN)

seed-all:
	@test -n "$(MONGODB_URI)" || (echo "MONGODB_URI is required. Add it to .env" && exit 1)
	python3 setup/seed.py all

demo:
	python3 demo.py $(DOMAIN) $(SCENARIO)

reset:
	python3 demo.py $(DOMAIN) reset

status:
	python3 demo.py $(DOMAIN) status

list:
	python3 demo.py list

tunnel:
	cloudflared tunnel --url http://localhost:8092

ID ?=
poll:
	@test -n "$(ID)" || (echo "Usage: make poll ID=<execution_id>" && exit 1)
	@curl -s http://localhost:8092/api/v1/executions/$(ID) | python3 -m json.tool
