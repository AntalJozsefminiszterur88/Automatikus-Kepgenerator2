# gui/overlay_window.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication, QFrame
from PySide6.QtCore import Qt, Signal, Slot 
from PySide6.QtGui import QScreen, QKeyEvent
from .widgets.music_player_widget import MusicPlayerWidget

class OverlayWindow(QWidget):
    stop_requested_signal = Signal() 

    def __init__(self): 
        super().__init__()
        
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setStyleSheet("""
            OverlayWindow {
                background-color: #1E1E1E; 
                border-radius: 10px;
            }
            QLabel {
                color: white;
                padding: 3px;
            }
            QProgressBar {
                text-align: center;
                color: white;
                border: 1px solid grey;
                border-radius: 5px;
                background-color: #2E2E2E;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
                margin: 0.5px;
            }
            #ShortcutInfoLabel {
                font-size: 9px;
                color: #AAAAAA;
            }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(6)

        self.progress_bar = QProgressBar()
        self.main_layout.addWidget(self.progress_bar)

        self.action_label = QLabel("Inicializálás...")
        self.action_label.setAlignment(Qt.AlignCenter)
        self.action_label.setWordWrap(True)
        self.main_layout.addWidget(self.action_label)

        self.image_count_label = QLabel("Kép: -/-")
        self.image_count_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.image_count_label)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: grey;")
        self.main_layout.addWidget(line)
        
        self.music_player_widget = MusicPlayerWidget(parent=self)
        self.main_layout.addWidget(self.music_player_widget)
        
        shortcut_text = (
            "Globális: Num0=Szünet/Foly. | Num+=Play/Pause\n" # Frissített leírás
            "Num4=Előző | Num6=Következő | Num8=HangFel | Num2=HangLe"
        )
        self.shortcut_info_label = QLabel(shortcut_text)
        self.shortcut_info_label.setObjectName("ShortcutInfoLabel")
        self.shortcut_info_label.setAlignment(Qt.AlignCenter)
        self.shortcut_info_label.setWordWrap(True)
        self.main_layout.addWidget(self.shortcut_info_label)

        self.setFixedSize(330, 310) 
        self.setFocusPolicy(Qt.StrongFocus)


    @Slot(int, int)
    def update_progress_bar(self, value, total_steps): 
        if total_steps > 0:
            self.progress_bar.setRange(0, total_steps)
            self.progress_bar.setValue(value)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

    @Slot(str)
    def update_action_label(self, text): 
        self.action_label.setText(text)

    @Slot(int, int)
    def update_image_count_label(self, current_image, total_images): 
        if total_images > 0:
            self.image_count_label.setText(f"Kép: {current_image}/{total_images}")
        else:
            self.image_count_label.setText("Kép: -/-")

    def position_in_top_right(self, margin=10): 
        primary_screen = QApplication.primaryScreen()
        if not primary_screen:
            print("Hiba: Nem található elsődleges képernyő a pozicionáláshoz.")
            return
        screen_geometry = primary_screen.availableGeometry()
        self.move(screen_geometry.width() - self.width() - margin, screen_geometry.top() + margin)

    def showEvent(self, event): 
        super().showEvent(event)
        self.position_in_top_right()
        self.activateWindow() 
        self.setFocus()       

    def closeEvent(self, event): 
        print("Overlay ablak bezárási esemény.")
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # A globális listener miatt a zenevezérlő és pause/resume billentyűket
        # itt már nem szükséges expliciten kezelni.
        # Csak akkor kellene, ha fókusz-specifikus eltérő viselkedést szeretnénk.
        super().keyPressEvent(event)

# Teszteléshez
if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    
    overlay = OverlayWindow()    
    overlay.show()
    overlay.update_action_label("Teszt művelet...")
    overlay.update_progress_bar(3, 10)
    overlay.update_image_count_label(2, 5)
    sys.exit(app.exec())
