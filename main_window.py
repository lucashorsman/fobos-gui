#assembles all widgets and components for the main window
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 1200, 800)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)