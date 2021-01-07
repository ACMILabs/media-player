help:
	@echo 'Individual commands:'
	@echo ' lint             - Lint the code with pylint and flake8 and check imports'
	@echo '                    have been sorted correctly'
	@echo ' test             - Run tests'
	@echo ''
	@echo 'Grouped commands:'
	@echo ' linttest         - Run lint and test'	
lint:
    # Lint the code and check imports have been sorted correctly
	pylint *
	flake8
	isort --check-only .
test:
	# Run tests
	pytest -v -s
linttest: lint test
