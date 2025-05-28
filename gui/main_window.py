# gui/main_window.py
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, Slot # <<< Slot importálása
# from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput # Erre már nincs itt szükség, ha nem közös a lejátszó
from .widgets.title_widget import TitleWidget
from .widgets.prompt_input_widget import PromptInputWidget
from .widgets.music_player_widget import MusicPlayerWidget 
from core.process_controller import ProcessController


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automatikus Képgenerátor")
        self.setGeometry(100, 100, 800, 650)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self._create_widgets() 
        self.process_controller = ProcessController(self)
        self._setup_layout()
        self._connect_signals()
        print("MainWindow inicializálva.")

    def _create_widgets(self):
        print("Widgetek létrehozása...")
        self.title_widget = TitleWidget()
        self.prompt_input_widget = PromptInputWidget()
        
        self.music_player_widget = MusicPlayerWidget(parent=self)

        self.status_label = QLabel("Állapot: Indítás...")
        self.status_label.setAlignment(Qt.AlignCenter)
        font = self.status_label.font()
        font.setPointSize(10)
        self.status_label.setFont(font)
        self.status_label.setWordWrap(True)

    def _setup_layout(self): 
        print("Elrendezés beállítása...") 
        self.main_layout.addWidget(self.title_widget) 
        self.main_layout.addSpacing(15) 
        self.main_layout.addWidget(self.prompt_input_widget) 
        self.main_layout.addSpacing(15) 
        self.main_layout.addWidget(self.status_label)  
        self.main_layout.addStretch(1) 
        self.main_layout.addWidget(self.music_player_widget) 

        self.central_widget.setLayout(self.main_layout) 


    def _connect_signals(self): 
        print("Jelzések összekötése...") 
        if hasattr(self.prompt_input_widget, 'start_button'): 
            self.prompt_input_widget.start_button.clicked.connect(self.handle_start_process) 


    def handle_start_process(self): 
        file_path = self.prompt_input_widget.get_file_path() 
        start_line = self.prompt_input_widget.get_start_line() 
        end_line = self.prompt_input_widget.get_end_line() 

        if not file_path: 
            self.update_status("Hiba: Nincs prompt fájl kiválasztva!") 
            print("Indítási kísérlet fájl nélkül.") 
            return

        if start_line <= 0 or end_line < start_line: 
            self.update_status("Hiba: Érvénytelen kezdő vagy befejező sor!") 
            print(f"Érvénytelen sorok: Start: {start_line}, End: {end_line}") 
            return
        
        print(f"Indítás kérése: {file_path}, Start: {start_line}, End: {end_line}") 
        self.update_status(f"Folyamat indítása a '{file_path.split('/')[-1]}' fájllal ({start_line}-{end_line}. sor)...") 
        
        if self.process_controller: 
            # print("DEBUG: MainWindow calling ProcessController.start_full_automation_process") # Debug
            self.process_controller.start_full_automation_process(file_path, start_line, end_line) 
        else:
            self.update_status("Hiba: ProcessController nincs inicializálva!") 
            print("Hiba: ProcessController nincs inicializálva a handle_start_process-ben.") 

    @Slot(str) # <<< HOZZÁADVA: A metódus Qt slotként való regisztrálása str argumentummal
    def update_status(self, message: str): # Típus-annotáció hozzáadva az egyértelműség kedvéért
        if hasattr(self, 'status_label'): 
            self.status_label.setText(f"Állapot: {message}") 
        else:
            print(f"[MainWindow KORAI STÁTUSZ - HIBA!]: {message}") 
        
        # QApplication.processEvents() # Ezt általában nem itt kell hívni, ha QMetaObject.invokeMethod-ot használunk

    def closeEvent(self, event):
        print("Ablak bezárási esemény (MainWindow)...")
        
        if self.process_controller and hasattr(self.process_controller, 'cleanup_on_exit'):
            self.process_controller.cleanup_on_exit()

        if hasattr(self, 'music_player_widget') and self.music_player_widget and \
           hasattr(self.music_player_widget, 'player') and \
           self.music_player_widget.player.playbackState() == self.music_player_widget.player.PlaybackState.PlayingState: # Helyes Enum használat
            print("Főablak bezárása: Saját zenelejátszó leállítása.")
            self.music_player_widget.player.stop()
        
        if self.process_controller and hasattr(self.process_controller, 'is_running') and self.process_controller.is_running():
            print("Futó folyamat leállítása kérése az ablak bezárásakor (másodlagos ellenőrzés)...")
            if hasattr(self.process_controller, 'stop_automation_process'):
                self.process_controller.stop_automation_process()
        
        event.accept()
