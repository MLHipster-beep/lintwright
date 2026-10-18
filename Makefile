PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH

.PHONY: all test check rules man deb clean

all: test check

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

check:
	$(PYTHON) -m lintwright.cli check . --fail-on info

rules:
	$(PYTHON) -m lintwright.cli rules

man:
	gzip -9 -n -c debian/lintwright.1 > lintwright.1.gz

deb:
	dpkg-buildpackage -us -uc -b

clean:
	rm -rf build dist src/*.egg-info lintwright.1.gz
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
