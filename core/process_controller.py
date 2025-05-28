# core/process_controller.py
import time
import traceback
import os
import threading 
from .prompt_handler import PromptHandler
from .pyautogui_automator import PyAutoGuiAutomator 
from .vpn_manager import VpnManager
from .browser_manager import BrowserManager
from .global_hotkey_listener import GlobalHotkeyListener 
from utils.ip_geolocation import get_public_ip_info 
from PySide6.QtCore import QMetaObject, Qt, Q_ARG, Slot, QObject, QThread, Signal, QEventLoop
from PySide6.QtWidgets import QApplication

try:
    from gui.overlay_window import OverlayWindow
except ImportError:
    OverlayWindow = None
    print("FIGYELEM: Az OverlayWindow osztály nem tölthető be.")


class InterruptedByUserError(Exception):
    """Egyedi kivétel a felhasználói megszakítás jelzésére."""
    pass

class AutomationWorker(QObject):
    status_updated = Signal(str, bool) 
    progress_updated = Signal(int, int) 
    image_count_updated = Signal(int, int) 
    automation_finished = Signal(str) 
    
    show_overlay_requested = Signal()
    hide_overlay_requested = Signal()

    def __init__(self, process_controller_ref, prompt_file_path, start_line, end_line):
        super().__init__()
        self.pc_ref = process_controller_ref 
        self.prompt_file_path = prompt_file_path
        self.start_line = start_line
        self.end_line = end_line
        
        self._is_task_running_in_worker = False 
        self._stop_requested_by_main = False    # Kemény stop kérés
        
        self._is_paused = False 
        self._pause_event = threading.Event()
        self._pause_event.set() 

        if hasattr(self.pc_ref.gui_automator, 'stop_requested'):
            self.pc_ref.gui_automator.stop_requested = False
        if hasattr(self.pc_ref.gui_automator, 'page_is_prepared'): 
            self.pc_ref.gui_automator.page_is_prepared = False
        # print("AutomationWorker inicializálva.")


    def _check_pause_and_stop(self):
        current_qthread = QThread.currentThread()
        if current_qthread:
            current_qthread.msleep(1) # Rövid alvás, hogy a Qt események feldolgozódjanak a worker szálon

        if self._stop_requested_by_main: 
            self.status_updated.emit("Worker: Kemény stop kérés feldolgozva a _check_pause_and_stop-ban.", False)
            # print("Worker DBG: Kemény stop kérés miatt InterruptedByUserError dobása.")
            raise InterruptedByUserError("Kemény stop kérés.")

        if self._is_paused:
            current_thread_id = threading.get_ident()
            self.status_updated.emit(f"Automatizálás szünetel (Worker szál: {current_thread_id}). Várakozás... Numpad 0 a folytatáshoz.", False)
            print(f"Worker DBG (szál: {current_thread_id}): Állapot SZÜNETEL. _is_paused={self._is_paused}. _pause_event.wait() hívás...")
            self._pause_event.wait() 
            print(f"Worker DBG (szál: {current_thread_id}): Szüneteltetés feloldva, _pause_event.wait() visszatért. _is_paused={self._is_paused}")
        
        if self._stop_requested_by_main: 
            self.status_updated.emit("Worker: Kemény stop kérés feldolgozva szünet után.", False)
            # print("Worker DBG: Kemény stop kérés miatt InterruptedByUserError dobása (szünet után).")
            raise InterruptedByUserError("Megszakítva szüneteltetés feloldása után (kemény stop).")

    @Slot()
    def request_hard_stop_from_main(self):
        self.status_updated.emit("Worker: Kemény leállítási kérelem fogadva.", False)
        print("Worker DBG: request_hard_stop_from_main hívva.")
        self._stop_requested_by_main = True
        if hasattr(self.pc_ref.gui_automator, 'request_stop'): 
            self.pc_ref.gui_automator.request_stop()

        if self._is_paused: 
            self._is_paused = False 
            self._pause_event.set()
            print("Worker DBG: Szüneteltetés feloldva kemény stop miatt.")

    @Slot()
    def toggle_pause_resume_state(self):
        current_thread_id = threading.get_ident()
        print(f"Worker DBG (szál: {current_thread_id}): toggle_pause_resume_state HÍVVA. Jelenlegi _is_paused: {self._is_paused}, _is_task_running_in_worker: {self._is_task_running_in_worker}")
        
        if not self._is_task_running_in_worker: 
            self.status_updated.emit("Worker: Nincs futó feladat, amit szüneteltetni/folytatni lehetne.", True)
            print("Worker DBG: toggle_pause_resume_state - nincs futó feladat.")
            return

        if self._is_paused: 
            self._is_paused = False
            self._pause_event.set() 
            self.status_updated.emit("Automatizálás folytatva.", False)
            print(f"Worker DBG (szál: {current_thread_id}): Állapot: FOLYTATVA. _is_paused={self._is_paused}, _pause_event set.")
        else: 
            self._is_paused = True
            self._pause_event.clear() 
            self.status_updated.emit("Automatizálás szüneteltetve. Numpad 0 a folytatáshoz.", False)
            print(f"Worker DBG (szál: {current_thread_id}): Állapot: SZÜNETELTETVE. _is_paused={self._is_paused}, _pause_event clear.")
            
    @Slot()
    def run_automation_task(self):
        if self._is_task_running_in_worker:
            self.status_updated.emit("Worker: run_automation_task már fut, új hívás figyelmen kívül hagyva.", True)
            return
        
        # Javított sor:
        current_thread_id = threading.get_ident()
        print(f"AutomationWorker DBG: run_automation_task elindult a worker szálon (ID: {current_thread_id}).")
        
        self._is_task_running_in_worker = True
        self._stop_requested_by_main = False 
        self._is_paused = False 
        self._pause_event.set()  

        prompt_handler = self.pc_ref.prompt_handler
        gui_automator = self.pc_ref.gui_automator
        vpn_manager = self.pc_ref.vpn_manager
        browser_manager = self.pc_ref.browser_manager
        current_qthread = QThread.currentThread() # Mentsük el a QThread referenciát
        
        if hasattr(gui_automator, 'stop_requested'): gui_automator.stop_requested = False
        if hasattr(gui_automator, 'page_is_prepared'): gui_automator.page_is_prepared = False
        
        self.status_updated.emit("Worker: Folyamat indítása...", False)
        skip_vpn_steps = False
        prompts_processed_count = 0
        total_prompts_to_process = 0

        try:
            self._check_pause_and_stop() 
            self.status_updated.emit(f"Worker: Promptok betöltése: '{os.path.basename(self.prompt_file_path)}'", False)
            prompts = prompt_handler.load_prompts(self.prompt_file_path, self.start_line, self.end_line)
            if not prompts:
                self.status_updated.emit("Worker Hiba: Nem sikerült promptokat betölteni.", True)
                self.automation_finished.emit("Sikertelen prompt betöltés")
                self._is_task_running_in_worker = False
                return
            
            total_prompts_to_process = len(prompts)
            self.status_updated.emit(f"Worker: {total_prompts_to_process} prompt betöltve.", False)
            self.progress_updated.emit(0, total_prompts_to_process)
            self.image_count_updated.emit(0, total_prompts_to_process)

            self._check_pause_and_stop() 

            target_vpn_server_group = "Singapore" 
            target_vpn_country_code = "SG"
            
            self.status_updated.emit("Worker: IP ellenőrzés VPN előtt...", False)
            current_ip_info_before_vpn = get_public_ip_info() 
            if current_ip_info_before_vpn:
                if current_ip_info_before_vpn.get('country_code') == target_vpn_country_code.upper():
                    skip_vpn_steps = True
                    self.status_updated.emit(f"Worker: Már a célországban ({target_vpn_country_code}). VPN kihagyva.", False)
            
            self._check_pause_and_stop() 

            if not skip_vpn_steps:
                if vpn_manager and vpn_manager.nordvpn_executable_path:
                    self.status_updated.emit(f"Worker: VPN kapcsolat ({target_vpn_server_group})...", False)
                    if not vpn_manager.connect_to_server(target_vpn_server_group, target_vpn_country_code):
                        if not self.pc_ref._stop_requested_by_user: 
                             self.status_updated.emit("Worker Figyelmeztetés: VPN csatlakozás sikertelennek tűnik.", True)
                    else: 
                        if not self.pc_ref._stop_requested_by_user:
                            self.status_updated.emit("Worker: VPN csatlakozás sikeresnek tűnik.", False)
                elif not vpn_manager:
                     self.status_updated.emit("Worker Hiba: VPN Manager nincs inicializálva.", True)
                elif vpn_manager and not vpn_manager.nordvpn_executable_path: # type: ignore
                     self.status_updated.emit("Worker Hiba: NordVPN végrehajtható nem található, VPN kihagyva.", True)
            
            self._check_pause_and_stop() 

            browser_opened_successfully = False
            if browser_manager:
                self.status_updated.emit("Worker: Böngésző indítása...", False)
                if browser_manager.open_target_url():
                    browser_opened_successfully = True
                    self.show_overlay_requested.emit() 
                    
                    wait_s = 15 
                    self.status_updated.emit(f"Worker: Várakozás a böngészőre ({wait_s}s)...", False)
                    for i in range(wait_s):
                        self._check_pause_and_stop() 
                        if current_qthread: current_qthread.msleep(1000) 
                        else: time.sleep(1)

                        if (i + 1) % 3 == 0 or i == wait_s -1 :
                             self.status_updated.emit(f"Worker: Böngésző töltődik... ({wait_s - 1 - i}s)", False)
                else:
                    if not self._stop_requested_by_main: 
                        self.status_updated.emit("Worker Hiba: Böngésző megnyitása sikertelen.", True)
            
            self._check_pause_and_stop()
            if not browser_opened_successfully and not self._stop_requested_by_main:
                self.automation_finished.emit("Böngészőhiba")
                self._is_task_running_in_worker = False
                return

            initial_gui_setup_success = False
            if gui_automator and browser_opened_successfully:
                self._check_pause_and_stop()
                self.status_updated.emit("Worker: Oldal előkészítése (PyAutoGUI)...", False)
                if gui_automator.initial_page_setup():
                    initial_gui_setup_success = True
                    self.status_updated.emit("Worker: Oldal előkészítve.", False)
                else: 
                    if not self.pc_ref._stop_requested_by_user and not gui_automator.stop_requested:
                        self.status_updated.emit("Worker Hiba: Oldal előkészítése sikertelen.", True)
            
            self._check_pause_and_stop()
            if not initial_gui_setup_success and not self._stop_requested_by_main and browser_opened_successfully:
                self.automation_finished.emit("PyAutoGUI előkészítési hiba")
                self._is_task_running_in_worker = False
                return
            
            if browser_opened_successfully and initial_gui_setup_success:
                self.status_updated.emit("Worker: Promptok feldolgozásának indítása...", False)
                for i, prompt_text in enumerate(prompts):
                    self._check_pause_and_stop() 
                    
                    current_prompt_no = self.start_line + i
                    self.status_updated.emit(f"Worker: Feldolgozás: Prompt #{current_prompt_no} ({i+1}/{total_prompts_to_process})", False)
                    self.image_count_updated.emit(i + 1, total_prompts_to_process)

                    if gui_automator.process_single_prompt(prompt_text): 
                        prompts_processed_count += 1
                        self.progress_updated.emit(prompts_processed_count, total_prompts_to_process)
                    else: 
                        if not self.pc_ref._stop_requested_by_user and not gui_automator.stop_requested:
                            self.status_updated.emit(f"Worker Hiba: #{current_prompt_no} prompt feldolgozásakor.", True)
                    
                    self._check_pause_and_stop() 

                    if i < total_prompts_to_process - 1: 
                        self._check_pause_and_stop()
                        pause_s = 2
                        self.status_updated.emit(f"Worker: Szünet ({pause_s}s)...", False)
                        for _sec_idx in range(pause_s):
                            self._check_pause_and_stop() 
                            if current_qthread: current_qthread.msleep(1000)
                            else: time.sleep(1) 
            
            self._check_pause_and_stop() 
            summary_msg = f"Feldolgozva: {prompts_processed_count}/{total_prompts_to_process}."
            if self._stop_requested_by_main : 
                summary_msg = f"Végleg leállítva. {summary_msg}"
            self.automation_finished.emit(summary_msg)

        except InterruptedByUserError as e:
            self.status_updated.emit(f"Worker: Folyamat megszakítva - {e}", False) 
            self.automation_finished.emit(f"Felhasználó által megszakítva/leállítva. Feldolgozva: {prompts_processed_count}/{total_prompts_to_process}.")
        except Exception as e:
            error_msg = f"Worker Kritikus Hiba: {e}"
            self.status_updated.emit(error_msg, True)
            print(f"WORKER KRITIKUS HIBA: {e}\n{traceback.format_exc()}")
            self.automation_finished.emit("Kritikus hiba történt a workerben.")
        finally:
            print(f"AutomationWorker DBG: run_automation_task finally blokk. _is_task_running_in_worker -> False")
            self._is_task_running_in_worker = False
            self._is_paused = False 
            self._pause_event.set() 
            self.hide_overlay_requested.emit()

# === ProcessController Osztály Kezdete (A többi része változatlan az előző teljes válaszhoz képest) ===
class ProcessController(QObject): 
    def __init__(self, main_window_ref):
        super().__init__() 
        self.main_window = main_window_ref
        self.overlay_window = None
        self._is_automation_active = False 
        self._stop_requested_by_user = False 

        self.automation_thread = None
        self.worker = None
        
        try:
            current_file_path = os.path.abspath(__file__)
            core_dir_path = os.path.dirname(current_file_path)
            self.project_root_path = os.path.dirname(core_dir_path)
        except Exception: self.project_root_path = os.getcwd()
        
        self.downloads_dir = os.path.join(self.project_root_path, "downloads")
        os.makedirs(self.downloads_dir, exist_ok=True)
        
        self.prompt_handler = PromptHandler(self)
        self.gui_automator = PyAutoGuiAutomator(self) 
        self.vpn_manager = VpnManager(self)           
        self.browser_manager = BrowserManager(self)   

        self.hotkey_listener = GlobalHotkeyListener()
        self._connect_hotkey_signals()
        self.hotkey_listener.start()
        
        print(f"ProcessController inicializálva. Letöltési mappa: {self.downloads_dir}")

    def _connect_hotkey_signals(self):
        if self.hotkey_listener:
            self.hotkey_listener.emitter.pause_resume_requested.connect(self.handle_pause_resume_request)
            self.hotkey_listener.emitter.music_play_pause_requested.connect(self.handle_music_play_pause)
            self.hotkey_listener.emitter.music_next_track_requested.connect(self.handle_music_next_track)
            self.hotkey_listener.emitter.music_prev_track_requested.connect(self.handle_music_prev_track)
            self.hotkey_listener.emitter.music_volume_up_requested.connect(self.handle_music_volume_up)
            self.hotkey_listener.emitter.music_volume_down_requested.connect(self.handle_music_volume_down)
            print("ProcessController: Globális billentyűparancs signálok összekötve.")
    
    @Slot()
    def handle_pause_resume_request(self):
        current_thread_id = threading.get_ident() 
        print(f"ProcessController DBG (szál: {current_thread_id}): Pause/Resume kérés fogadva a hotkey listenertől.")
        if self.worker and self.automation_thread and self.automation_thread.isRunning() and hasattr(self.worker, '_is_task_running_in_worker') and self.worker._is_task_running_in_worker:
            print("ProcessController DBG: Kérés továbbítása a worker.toggle_pause_resume_state felé.")
            QMetaObject.invokeMethod(self.worker, "toggle_pause_resume_state", Qt.QueuedConnection)
        else:
            self.update_gui_status("Nincs aktív folyamat, amit szüneteltetni/folytatni lehetne.", False)
            print("ProcessController DBG: Nincs aktív worker a pause/resume kéréshez.")

    @Slot()
    def handle_music_play_pause(self):
        player_widget = self._get_active_music_player_widget()
        if player_widget: player_widget.play_pause_action()

    @Slot()
    def handle_music_next_track(self):
        player_widget = self._get_active_music_player_widget()
        if player_widget: player_widget.next_track_action()

    @Slot()
    def handle_music_prev_track(self):
        player_widget = self._get_active_music_player_widget()
        if player_widget: player_widget.previous_track_action()

    @Slot()
    def handle_music_volume_up(self):
        player_widget = self._get_active_music_player_widget()
        if player_widget: player_widget.increase_volume_action()

    @Slot()
    def handle_music_volume_down(self):
        player_widget = self._get_active_music_player_widget()
        if player_widget: player_widget.decrease_volume_action()

    def _get_active_music_player_widget(self):
        if self.overlay_window and self.overlay_window.isVisible() and hasattr(self.overlay_window, 'music_player_widget'):
            return self.overlay_window.music_player_widget
        elif self.main_window and hasattr(self.main_window, 'music_player_widget'):
            return self.main_window.music_player_widget
        return None
        
    @Slot(str, bool)
    def _handle_worker_status_update(self, message, is_error):
        self.update_gui_status(message, is_error)

    @Slot(int, int)
    def _handle_worker_progress_update(self, current_step, total_steps):
        if self.overlay_window: 
            self._update_overlay_progress(current_step, total_steps)

    @Slot(int, int)
    def _handle_worker_image_count_update(self, current_image, total_images):
        if self.overlay_window: 
            self._update_overlay_image_count(current_image, total_images)

    @Slot(str)
    def _handle_automation_finished(self, summary_message):
        print(f"ProcessController DBG: _handle_automation_finished, üzenet: {summary_message}")
        self.update_gui_status(f"Automatizálás befejeződött: {summary_message}", False)
        self._is_automation_active = False
        self._stop_requested_by_user = False 

        if hasattr(self.gui_automator, 'close_browser'):
            print("ProcessController: Böngésző bezárási kísérlet a worker után.")
            self.gui_automator.close_browser()

        if self.vpn_manager and hasattr(self.vpn_manager, 'is_connected_to_target_server') and self.vpn_manager.is_connected_to_target_server:
            self.update_gui_status("VPN kapcsolat bontása a folyamat végén (ha aktív)...", False)
            self.vpn_manager.disconnect_vpn()

        if self.automation_thread:
            print("ProcessController DBG: automation_thread.quit() hívása (_handle_automation_finished).")
            if self.automation_thread.isRunning():
                self.automation_thread.quit()
                if not self.automation_thread.wait(1500): 
                    print("ProcessController Figyelmeztetés: Autom. szál nem állt le, terminate.")
                    self.automation_thread.terminate() 
                    self.automation_thread.wait()      
            self.automation_thread = None 
        if self.worker: 
            self.worker.deleteLater()
            self.worker = None 
        print("ProcessController DBG: Autom. szál és worker erőforrásai felszabadítva.")


    @Slot()
    def _handle_show_overlay_request(self):
        if OverlayWindow and self.main_window:
            if not self.overlay_window:
                print("ProcessController DBG: Új OverlayWindow példány (worker kérésére).")
                self.overlay_window = OverlayWindow()
            print("ProcessController DBG: OverlayWindow.show() (worker kérésére).")
            self.overlay_window.show()
            QApplication.processEvents() 

    @Slot()
    def _handle_hide_overlay_request(self):
        if self.overlay_window:
            print("ProcessController DBG: OverlayWindow.close() (worker kérésére).")
            self.overlay_window.close()
            self.overlay_window = None 

    def start_full_automation_process(self, prompt_file_path, start_line, end_line):
        if self._is_automation_active or (self.automation_thread and self.automation_thread.isRunning()):
            self.update_gui_status("Egy automatizálási folyamat már fut!", True)
            return
        
        print("ProcessController DBG: start_full_automation_process hívva, új worker indítása.")
        self._is_automation_active = True
        self._stop_requested_by_user = False 

        self.automation_thread = QThread(self) 
        self.worker = AutomationWorker(self, prompt_file_path, start_line, end_line)
        self.worker.moveToThread(self.automation_thread)

        self.worker.status_updated.connect(self._handle_worker_status_update)
        self.worker.progress_updated.connect(self._handle_worker_progress_update)
        self.worker.image_count_updated.connect(self._handle_worker_image_count_update)
        self.worker.automation_finished.connect(self._handle_automation_finished)
        self.worker.show_overlay_requested.connect(self._handle_show_overlay_request)
        self.worker.hide_overlay_requested.connect(self._handle_hide_overlay_request)
        
        self.automation_thread.started.connect(self.worker.run_automation_task)
        self.automation_thread.finished.connect(self.worker.deleteLater) 
        self.automation_thread.finished.connect(self.automation_thread.deleteLater) 

        self.update_gui_status("Automatizálási szál indítása...", False)
        self.automation_thread.start()
        print("ProcessController DBG: Automatizálási szál elindítva.")

    def stop_automation_process(self): 
        print("ProcessController DBG: KEMÉNY stop_automation_process hívva.")
        self._stop_requested_by_user = True 
        if hasattr(self.gui_automator, 'request_stop'):
             self.gui_automator.request_stop()

        if self.worker and self.automation_thread and self.automation_thread.isRunning():
            self.update_gui_status("Automatizálás KEMÉNY leállítási kérelme elküldve a workernek...", False)
            print("ProcessController DBG: Kérés worker.request_hard_stop_from_main felé.")
            QMetaObject.invokeMethod(self.worker, "request_hard_stop_from_main", Qt.QueuedConnection)
        elif not self._is_automation_active:
             self.update_gui_status("Nincs aktívan futó automatizálási folyamat a kemény leállításhoz.", False)

    def update_gui_status(self, message, is_error=False):
        if self.main_window and hasattr(self.main_window, 'update_status'):
            display_message = message
            if is_error and not any(message.lower().startswith(p) for p in ["hiba:", "vpn hiba:", "web hiba:", "böngésző hiba:", "automatizálási hiba:"]):
                display_message = f"Hiba: {message}"
            QMetaObject.invokeMethod(self.main_window, "update_status", Qt.QueuedConnection, Q_ARG(str, display_message))

        if self.overlay_window and hasattr(self.overlay_window, 'update_action_label'):
            QMetaObject.invokeMethod(self.overlay_window, "update_action_label", Qt.QueuedConnection, Q_ARG(str, message))

    def _update_overlay_progress(self, current_step, total_steps):
        if self.overlay_window and hasattr(self.overlay_window, 'update_progress_bar'):
            QMetaObject.invokeMethod(self.overlay_window, "update_progress_bar", Qt.QueuedConnection,
                                     Q_ARG(int, current_step), Q_ARG(int, total_steps))

    def _update_overlay_image_count(self, current_image, total_images):
        if self.overlay_window and hasattr(self.overlay_window, 'update_image_count_label'):
            QMetaObject.invokeMethod(self.overlay_window, "update_image_count_label", Qt.QueuedConnection,
                                     Q_ARG(int, current_image), Q_ARG(int, total_images))
                                     
    def cleanup_on_exit(self):
        print("ProcessController DBG: Takarítás kilépéskor (cleanup_on_exit)...")
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            print("ProcessController DBG: Globális billentyűfigyelő leállítva.")
        
        if self._is_automation_active and self.worker and self.automation_thread and self.automation_thread.isRunning():
            print("ProcessController DBG cleanup: Aktív worker szál kemény leállítása...")
            self._stop_requested_by_user = True 
            if hasattr(self.gui_automator, 'request_stop'): self.gui_automator.request_stop()
            QMetaObject.invokeMethod(self.worker, "request_hard_stop_from_main", Qt.QueuedConnection)
            if self.automation_thread:
                print("ProcessController DBG cleanup: Várakozás a worker szál leállására...")
                if not self.automation_thread.wait(3000): 
                    print("ProcessController Figyelmeztetés: Worker szál nem állt le a cleanup során időben, terminate.")
                    self.automation_thread.terminate() 
                    self.automation_thread.wait()      
                else:
                    print("ProcessController DBG cleanup: Worker szál sikeresen leállt.")
        elif self.automation_thread and self.automation_thread.isRunning(): 
             print("ProcessController DBG cleanup: Nem aktív worker, de a szál még fut, leállítás...")
             self.automation_thread.quit()
             self.automation_thread.wait(500)
             if self.automation_thread.isRunning(): 
                 print("ProcessController DBG cleanup: A szál nem állt le quit()-re, terminate.")
                 self.automation_thread.terminate() 
                 self.automation_thread.wait()
        
        self.automation_thread = None 
        self.worker = None
        print("ProcessController DBG cleanup befejezve.")

    def is_running(self): 
        return self._is_automation_active
