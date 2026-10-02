.PHONY: setup data audit ceiling reference concentration test lint clean

setup:
	pip install -r requirements.txt --break-system-packages

data:
	bash scripts/download_data.sh

audit:
	pytest tests/test_extraction_audit.py -v -s

# Sample sizes come from src/config.py so a clean checkout reproduces the
# committed CSVs. Do not pass a size on the command line unless you intend to
# produce something other than the committed artifact.
ceiling:
	python -m src.extract.ceiling

reference:
	python -m src.analysis.length_control

concentration:
	python -m src.analysis.premise_concentration

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
