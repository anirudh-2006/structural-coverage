.PHONY: setup data audit ceiling reference test lint figures clean

setup:
	pip install -r requirements.txt --break-system-packages

data:
	bash scripts/fetch_mathlib_graph.sh
	bash scripts/fetch_machine_corpora.sh

audit:
	pytest tests/test_extraction_audit.py -v -s

# Sample sizes come from src/config.py so a clean checkout reproduces the
# committed CSVs. Do not pass a size on the command line unless you intend to
# produce something other than the committed artifact.
ceiling:
	python -m src.extract.ceiling

reference:
	python -m src.analysis.length_control

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

figures:
	python -m src.analysis.make_figures

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
