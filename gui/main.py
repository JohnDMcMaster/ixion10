from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Control a TG1B1A / N4962A BERT")
    parser.add_argument("--sim", action="store_true", help="use the bundled pyvisa-sim device")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow(simulate=args.sim)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
