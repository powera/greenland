#!/bin/bash

/Users/powera/Library/Python/3.9/bin/pyinstaller \
  --onefile \
  --add-data "audioshoe/sample/test.mp3:audioshoe/sample" \
  devserver.py
