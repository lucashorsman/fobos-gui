#creates Qapplication and main window, starts the event loop, calls app.exec()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from core.main_window import MainWindow
import sys

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Damascus", 14))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()