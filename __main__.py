#!/usr/bin/env python

import os

# ctranslate2 and torch both bundle libiomp5md.dll — two OpenMP runtimes in
# the same process cause STATUS_STACK_BUFFER_OVERRUN unless this is set first.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from jarvis.app import main

if __name__ == "__main__":
    main()
