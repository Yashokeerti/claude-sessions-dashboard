.PHONY: run install build-mac install-mac clean

# Run the dashboard
run:
	python -m claude_sessions_dashboard

# Run on a custom port
run-port:
	python -m claude_sessions_dashboard --port $(PORT)

# Install via pip (editable mode for development)
install:
	pip install -e .

# Build native macOS app
build-mac:
	cd macos && bash build.sh

# Install to system Python
install-global:
	pip install .

# Build Python distribution package
dist:
	python -m build

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	rm -rf macos/Claude\ Sessions.app
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

# Show help
help:
	@echo "Claude Sessions Dashboard"
	@echo "========================="
	@echo ""
	@echo "Usage:"
	@echo "  make run          - Start the dashboard (port 8050)"
	@echo "  make run-port PORT=9090  - Start on custom port"
	@echo "  make install      - Install in development mode"
	@echo "  make install-global - Install to system Python"
	@echo "  make build-mac    - Build native macOS app"
	@echo "  make dist         - Build distribution package"
	@echo "  make clean        - Remove build artifacts"
