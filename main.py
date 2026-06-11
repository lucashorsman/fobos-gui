#creates Qapplication and main window, starts the event loop, calls app.exec()
from PySide6.QtWidgets import QApplication
from main_window import MainWindow
if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
        