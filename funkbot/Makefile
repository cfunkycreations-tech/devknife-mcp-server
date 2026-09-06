.PHONY: install run cli test check learn model docker clean

MODEL ?= qwen3:32b

install:
	pip install -r requirements.txt

model:                      ## pull the local model
	ollama pull $(MODEL)

run:                        ## web UI at http://localhost:8800
	python server.py

cli:
	python cli.py

test:
	python -m pytest -q tests

check:                      ## full self-verification (what a self-edit must pass)
	python -c "import verify; print(verify.health())"

learn:                      ## run the recursive learning pass by hand
	python cli.py --learn

mcp:                        ## expose FunkBot's tools to other agents over MCP
	python mcp_client.py

docker:
	docker build -t funkbot . && docker run --rm -it --network host \
		-v funkbot-data:/app/data funkbot

clean:
	rm -rf __pycache__ .pytest_cache **/__pycache__ *.bak.*
