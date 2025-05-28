from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QSpinBox, QHBoxLayout, QFileDialog
from PySide6.QtCore import Qt

class PromptInputWidget(QWidget):
    """
    Widget a prompt fájl feltöltéséhez, sorválasztáshoz és az indításhoz.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10)

        # Fájl kiválasztása
        self.file_path_label = QLabel("Prompt fájl (.txt): Még nincs kiválasztva")
        self.file_path_button = QPushButton("Fájl kiválasztása...")
        self.file_path_button.clicked.connect(self.select_file)
        self.selected_file_path = ""

        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_path_label)
        file_layout.addWidget(self.file_path_button)
        self.layout.addLayout(file_layout)

        # Sorszámok
        self.start_line_label = QLabel("Kezdő sor:")
        self.start_line_spinbox = QSpinBox()
        self.start_line_spinbox.setMinimum(1)
        self.start_line_spinbox.setValue(1)

        self.end_line_label = QLabel("Befejező sor (meddig):")
        self.end_line_spinbox = QSpinBox()
        self.end_line_spinbox.setMinimum(1)
        self.end_line_spinbox.setValue(10) # Alapértelmezett érték

        line_layout = QHBoxLayout()
        line_layout.addWidget(self.start_line_label)
        line_layout.addWidget(self.start_line_spinbox)
        line_layout.addSpacing(20)
        line_layout.addWidget(self.end_line_label)
        line_layout.addWidget(self.end_line_spinbox)
        self.layout.addLayout(line_layout)

        # Indítás gomb
        self.start_button = QPushButton("Automatizálás Indítása")
        self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 10px; font-size: 16px; border-radius: 5px; }")
        # A start_button.clicked jelét a MainWindow fogja összekötni a process_controllerrel.

        self.layout.addWidget(self.start_button, alignment=Qt.AlignCenter)

        self.setLayout(self.layout)
        print("PromptInputWidget inicializálva.")

    def select_file(self):
        """Megnyit egy fájl dialógust a .txt fájl kiválasztásához."""
        file_name, _ = QFileDialog.getOpenFileName(self, "Prompt fájl kiválasztása", "", "Text files (*.txt)")
        if file_name:
            self.selected_file_path = file_name
            # Csak a fájlnevet jelenítjük meg a hosszabb elérési út helyett, ha az túl hosszú
            display_name = file_name.split('/')[-1]
            self.file_path_label.setText(f"Kiválasztott fájl: .../{display_name}")
            print(f"Fájl kiválasztva: {self.selected_file_path}")
            # Itt lehetne logikát hozzáadni a sorok maximális értékének beállításához a fájl alapján,
            # de ehhez már a prompt_handlerre lenne szükség.
            # Egyelőre a felhasználónak kell tudnia a helyes értékeket.

    def get_file_path(self):
        return self.selected_file_path

    def get_start_line(self):
        return self.start_line_spinbox.value()

    def get_end_line(self):
        return self.end_line_spinbox.value()
