"""Entry point used by PyInstaller to build the Windows executable.

Keeping this at the repo root makes the spec file simple and avoids the
package-relative import quirks you can hit when freezing a ``-m`` module.
"""

from realgoodsplits.gui import main

if __name__ == "__main__":
    main()
