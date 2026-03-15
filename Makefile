.PHONY: install run build app clean

install:
	pip3 install -e .

run:
	python3 -m claude_meter

build:
	pip3 install pyinstaller
	pyinstaller "Claude Meter.spec" --noconfirm

app: build
	cp -R dist/Claude\ Meter.app /Applications/Claude\ Meter.app
	@echo "Installed to /Applications/Claude Meter.app"

clean:
	rm -rf build/ dist/ *.egg-info __pycache__ claude_meter/__pycache__ claude_meter/trackers/__pycache__
