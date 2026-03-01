.PHONY: setup lint test build deploy teardown clean help

SHELL := /bin/bash
PROJECT_ROOT := $(shell pwd)
VENV := $(PROJECT_ROOT)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

GCP_PROJECT ?= $(shell grep -s 'project_id' terraform/terraform.tfvars 2>/dev/null | cut -d'"' -f2)
GCP_REGION ?= us-central1
REGISTRY ?= gcr.io/$(GCP_PROJECT)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install all dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo "Activate with: source .venv/bin/activate"

lint: ## Run ruff linter and mypy type checker
	$(RUFF) check .
	$(RUFF) format --check .

lint-fix: ## Auto-fix lint issues
	$(RUFF) check --fix .
	$(RUFF) format .

test: ## Run all unit tests
	$(PYTEST) tests/ -v --ignore=tests/benchmarks -m "not integration"

test-all: ## Run all tests including integration and benchmarks
	$(PYTEST) tests/ -v

test-security: ## Run security-focused tests
	$(PYTEST) tests/benchmarks/test_security.py -v

test-benchmarks: ## Run benchmark tests
	$(PYTEST) tests/benchmarks/ -v -m benchmark

build: ## Build Docker images
	docker build -t $(REGISTRY)/rh-planner:latest docker/rh-planner/
	docker build -t $(REGISTRY)/lh-executor:latest docker/lh-executor/
	docker build -t $(REGISTRY)/operator:latest operator/

push: ## Push Docker images to registry
	docker push $(REGISTRY)/rh-planner:latest
	docker push $(REGISTRY)/lh-executor:latest
	docker push $(REGISTRY)/operator:latest

infra-init: ## Initialize Terraform
	cd terraform && terraform init

infra-plan: ## Plan Terraform changes
	cd terraform && terraform plan -out=tfplan

infra-apply: ## Apply Terraform infrastructure
	cd terraform && terraform apply tfplan

deploy: ## Full deployment: infra + images + k8s manifests
	scripts/deploy.sh

teardown: ## Destroy all infrastructure
	cd terraform && terraform destroy -auto-approve

clean: ## Remove build artifacts and venv
	rm -rf $(VENV) dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

validate-terraform: ## Validate Terraform configuration
	cd terraform && terraform init -backend=false && terraform validate
