.PHONY: help build up down logs test clean install up-aws down-aws logs-aws status-aws

help:
	@echo "Agentic Thin Waist - Available Commands"
	@echo "======================================="
	@echo "make install    - Install Python dependencies"
	@echo "make build      - Build Docker images"
	@echo "make up         - Start services (development)"
	@echo "make down       - Stop services"
	@echo "make logs       - View service logs"
	@echo "make test       - Run test suite"
	@echo "make clean      - Clean up containers and volumes"
	@echo "make status     - Check service status"
	@echo "make shell      - Open shell in experiment-api container"
	@echo ""
	@echo "AWS Hybrid Mode (local services + AWS EC2 substrate workers):"
	@echo "make up-aws     - Start with AWS substrate workers"
	@echo "make down-aws   - Stop AWS hybrid stack"
	@echo "make logs-aws   - View logs (AWS mode)"
	@echo "make status-aws - Check service status (AWS mode)"

install:
	pip install -r requirements.txt
	for dir in services/*/; do \
		if [ -f "$$dir/requirements.txt" ]; then \
			pip install -r "$$dir/requirements.txt"; \
		fi; \
	done

build:
	docker compose build

up:
	docker compose up -d
	@echo "Services starting..."
	@sleep 2
	@echo "Waiting for services to be ready (max 30 seconds)..."
	@for i in {1..30}; do \
		if curl -s http://localhost:8000/health > /dev/null 2>&1; then \
			echo "✓ All services ready!"; \
			break; \
		fi; \
		if [ $$i -eq 30 ]; then \
			echo "⚠ Services still starting, check with 'make logs'"; \
		else \
			echo -n "."; \
			sleep 1; \
		fi; \
	done
	@echo ""
	@echo "Services running on:"
	@echo "  Experiment API     : http://localhost:8000"
	@echo "  CTP Service        : http://localhost:8001"
	@echo "  Substrate Worker   : http://localhost:8002"
	@echo "  NetGent Service    : http://localhost:8003"
	@echo "  Storage Service    : http://localhost:8004"
	@echo "  Orchestration      : http://localhost:8005"

down:
	docker compose down

logs:
	docker compose logs -f

logs-service:
	@echo "Usage: make logs-service SERVICE=<service-name>"
	@echo "Example: make logs-service SERVICE=experiment-api"
	docker compose logs -f $(SERVICE)

test:
	docker compose -f docker-compose.yml -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from orchestration-tests orchestration-tests
	@echo "Tests completed. Run 'make logs' to see output."

test-local:
	pytest tests/ -v

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".eggs" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info

status:
	@echo "Service Status:"
	@docker compose ps

shell:
	docker compose exec experiment-api /bin/bash

restart:
	docker compose restart

version:
	@echo "Agentic Thin Waist v0.1.0"
	@echo "Development Build"
	@echo "Last Updated: 2026-03-04"

# AWS hybrid deployment: local services + AWS EC2 substrate workers
up-aws:
	@echo "Starting hybrid deployment (local services + AWS substrate workers)..."
	@echo "AWS Region: $${AWS_REGION:-us-west-1}"
	@echo ""
	@echo "NOTE: On first run, AWS infrastructure provisioning takes ~10 minutes."
	@echo "      Subsequent runs reuse the cached AMI."
	@echo ""
	docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d
	@echo ""
	@echo "Waiting for services to be ready (max 30 seconds)..."
	@for i in {1..30}; do \
		if curl -s http://localhost:8005/health > /dev/null 2>&1; then \
			echo "All services ready!"; \
			break; \
		fi; \
		if [ $$i -eq 30 ]; then \
			echo "Services still starting, check with 'make logs-aws'"; \
		else \
			echo -n "."; \
			sleep 1; \
		fi; \
	done
	@echo ""
	@echo "Services running on:"
	@echo "  Experiment API     : http://localhost:8000"
	@echo "  CTP Service        : http://localhost:8001"
	@echo "  Substrate Worker   : AWS EC2 (provisioned on demand)"
	@echo "  Telemetry Service  : http://localhost:8004"
	@echo "  Orchestration      : http://localhost:8005"
	@echo ""
	@echo "Disabled in AWS mode: substrate-worker, netgent-service, netgent-worker"

down-aws:
	docker compose -f docker-compose.yml -f docker-compose.aws.yml down

logs-aws:
	docker compose -f docker-compose.yml -f docker-compose.aws.yml logs -f

status-aws:
	@echo "Service Status (AWS hybrid mode):"
	@docker compose -f docker-compose.yml -f docker-compose.aws.yml ps

# Cloud deployment commands
build-cloud:
	docker compose -f docker-compose.yml -f docker-compose.cloud.yml build

up-cloud:
	@echo "Starting cloud deployment (requires AWS/Azure credentials)"
	docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d

down-cloud:
	docker compose -f docker-compose.yml -f docker-compose.cloud.yml down
