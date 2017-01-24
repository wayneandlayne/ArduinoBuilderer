Arduino Builderer
=================

Arduino Builderer is a tool for running arduino-builder across many sketches and many boards.  It is not yet suitable for general use.

Installation
------------

    virtualenv venv
    source ~/venv/bin/activate
    pip install -e .

If you are looking to run tests or do development:

    source ~/venv/bin/activate
    pip install -r dev-requirements.txt
    tox


Usage
-----

    arduino-builderer --help

Roadmap
-------

* Make tox pass.
* Add testing and get good coverage.
* Add a blacklist for board/sketch combinations
* Make sure PR name, commit message, SHA and date can easily get added to the generated output.
* Make binaries for Windows, macOS, and Linux.
