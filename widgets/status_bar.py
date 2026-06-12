from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit

class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("<b>Status Readout</b>")
        layout.addWidget(title)
        
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        # Use a monospaced font for better alignment
        self.text_display.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.text_display)

    def update_display(self, positioners_dict):
        lines = []
        for pid in sorted(positioners_dict.keys()):
            state = positioners_dict[pid]
            alpha = state.get("alpha", 0.0)
            beta = state.get("beta", 0.0)
            status = state.get("state", "unknown")
            
            line = f"PID {pid:03d} | α: {alpha:>7.2f}° | β: {beta:>7.2f}° | State: {status.upper()}"
            lines.append(line)
            
        if not lines:
            self.text_display.setText("Waiting for positioners...")
        else:
            self.text_display.setText("\n".join(lines))
