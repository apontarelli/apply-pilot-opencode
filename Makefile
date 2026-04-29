.PHONY: test check

test:
	python3 -m unittest discover -s tests

check: test
