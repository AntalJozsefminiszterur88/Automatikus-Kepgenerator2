# core/automation_worker.py
from PySide6.QtCore import QObject, Signal, Slot
import time
import traceback
import os
import threading # <<< ÚJ IMPORT

class InterruptedByUserError(Exception):
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
        self._stop_requested_by_main = False # Kemény stop kérés a ProcessControllertől
        
        self._is_paused = False # Új állapotjelző a szüneteltetéshez
        self._pause_event = threading.Event()
        self._pause_event.set() # Kezdetben nincs szünet, az esemény "set" (átenged)

        if hasattr(self.pc_ref.gui_automator, 'stop_requested'):
            self.pc_ref.gui_automator.stop_requested = False
        if hasattr(self.pc_ref.gui_automator, 'page_is_prepared'):
            self.pc_ref.gui_automator.page_is_prepared = False

    def _check_pause_and_stop(self):
        """ Ellenőrzi a szüneteltetési és a kemény stop kérést. """
        if self._stop_requested_by_main: # Kemény stop prioritást élvez
            self.status_updated.emit("Worker: Kemény stop kérés feldolgozva.", False)
            raise InterruptedByUserError("Kemény stop kérés.")

        if self._is_paused:
            self.status_updated.emit("Automatizálás szünetel. Újbóli Numpad 0 a folytatáshoz.", False)
            self._pause_event.wait() # Blokkol, amíg az event nincs "set" (azaz amíg _is_paused True és az event cleared)
            # Miután a wait() visszatér (mert az event "set" lett a folytatáshoz),
            # a ciklus folytatódik. Az _is_paused már False lesz a toggle_pause_state által.
            # Nincs szükség az event újbóli clear()-elésére itt, azt a toggle_pause_state kezeli.
        
        # Extra stop ellenőrzés a pause után is, hátha közben érkezett
        if self._stop_requested_by_main:
            raise InterruptedByUserError("Megszakítva szüneteltetés feloldása után (kemény stop).")


    @Slot()
    def request_hard_stop_from_main(self):
        """Ezt a slotot hívja meg a ProcessController a fő szálról, hogy végleg leállítsa a munkát."""
        self.status_updated.emit("Worker: Kemény leállítási kérelem fogadva.", False)
        self._stop_requested_by_main = True
        # Ha szünetel, fel kell oldani a blokkolást, hogy a stop érvényesülhessen
        if self._is_paused:
            self._is_paused = False # Töröljük a pause állapotot
            self._pause_event.set()   # Engedjük tovább a futást, hogy a stop kivétel dobódhasson

        if hasattr(self.pc_ref.gui_automator, 'request_stop'):
            self.pc_ref.gui_automator.request_stop()

    @Slot()
    def toggle_pause_resume_state(self):
        """Vált a szüneteltetett és a futó állapot között."""
        if not self._is_task_running_in_worker:
            self.status_updated.emit("Worker: Nincs futó feladat, amit szüneteltetni lehetne.", True)
            return

        if self._is_paused: # Ha jelenleg szünetel -> folytatás
            self._is_paused = False
            self._pause_event.set() # Event "set" -> wait() nem blokkol
            self.status_updated.emit("Automatizálás folytatva.", False)
        else: # Ha jelenleg fut -> szüneteltetés
            self._is_paused = True
            self._pause_event.clear() # Event "clear" -> wait() blokkolni fog
            self.status_updated.emit("Automatizálás szüneteltetve. Numpad 0 a folytatáshoz.", False)
            # Nincs szükség itt wait()-re, a fő ciklus _check_pause_and_stop metódusa fog blokkolni.

    @Slot()
    def run_automation_task(self):
        # ... (metódus eleje, komponens referenciák, flag resetek változatlanok)
        if self._is_task_running_in_worker: # Dupla ellenőrzés
            return
        self._is_task_running_in_worker = True
        self._stop_requested_by_main = False
        self._is_paused = False # Biztosítjuk, hogy ne szünetelve induljon
        self._pause_event.set()   # És az event is "set" állapotban legyen

        prompt_handler = self.pc_ref.prompt_handler
        gui_automator = self.pc_ref.gui_automator
        vpn_manager = self.pc_ref.vpn_manager
        browser_manager = self.pc_ref.browser_manager
        
        if hasattr(gui_automator, 'stop_requested'): gui_automator.stop_requested = False
        if hasattr(gui_automator, 'page_is_prepared'): gui_automator.page_is_prepared = False
        
        self.status_updated.emit("Automatizálási folyamat elindítva (worker szálon)...", False)
        # ... (prompts_processed_count, total_prompts_to_process inicializálása) ...
        prompts_processed_count = 0
        total_prompts_to_process = 0

        try:
            self._check_pause_and_stop() # Ellenőrzés a legelején
            self.status_updated.emit(f"Promptok betöltése: '{os.path.basename(self.prompt_file_path)}'", False)
            # ... (prompts betöltése) ...
            prompts = prompt_handler.load_prompts(self.prompt_file_path, self.start_line, self.end_line)
            if not prompts: # ... (hiba és return)
                self.status_updated.emit("Hiba: Nem sikerült promptokat betölteni.", True)
                self.automation_finished.emit("Sikertelen prompt betöltés")
                self._is_task_running_in_worker = False
                return
            
            total_prompts_to_process = len(prompts) # Itt már van értéke
            self.status_updated.emit(f"{total_prompts_to_process} prompt betöltve.", False)
            self.progress_updated.emit(0, total_prompts_to_process)
            self.image_count_updated.emit(0, total_prompts_to_process)

            # VPN és Böngésző szakaszok
            # Minden `time.sleep()` és hosszabb művelet előtt/után `self._check_pause_and_stop()` hívás kell!
            # Példa a böngésző várakozásra:
            # ... (browser_manager.open_target_url() után)
            if browser_opened_successfully: # Feltételezve, hogy ez a változó létezik és be van állítva
                self.show_overlay_requested.emit()
                wait_s = 15
                self.status_updated.emit(f"Várakozás a böngészőre ({wait_s}s)...", False)
                for i in range(wait_s):
                    self._check_pause_and_stop() # <<< FONTOS
                    time.sleep(1)
                    # ... (státuszfrissítés)
            # ... (Hasonlóan a VPN logikában is)

            # PyAutoGUI Előkészítés
            self._check_pause_and_stop()
            if gui_automator:
                # ... (initial_page_setup hívása) ...
                # Az initial_page_setup-nak is tartalmaznia kellene belső ciklusokban _check_pause_and_stop-ot
                # vagy a ProcessController _stop_requested_by_user-t kell figyelnie, amit a
                # request_hard_stop_from_main állít be.
                pass # A jelenlegi initial_page_setup a pc_ref._stop_requested_by_user-t figyeli

            # Prompt Feldolgozási Ciklus
            self.status_updated.emit("Promptok feldolgozásának indítása...", False)
            for i, prompt_text in enumerate(prompts):
                self._check_pause_and_stop() # Minden prompt előtt
                # ... (prompt feldolgozása, process_single_prompt hívása) ...
                # A process_single_prompt-nak is figyelnie kell a stop/pause állapotot.
                # A jelenlegi process_single_prompt a pc_ref._stop_requested_by_user-t figyeli.

                if i < total_prompts_to_process - 1: # Csak ha van következő prompt
                    self._check_pause_and_stop()
                    pause_s = 2
                    self.status_updated.emit(f"Szünet ({pause_s}s)...", False)
                    for _ in range(pause_s):
                        self._check_pause_and_stop() # <<< FONTOS
                        time.sleep(1)
            
            # ... (Befejezési logika, automation_finished.emit()) ...

        # ... (except és finally blokkok, mint korábban, de a _check_pause_and_stop miatt
        # az InterruptedByUserError dobódhat a _stop_requested_by_main miatt is)
        except InterruptedByUserError as e:
            self.status_updated.emit(f"Folyamat megszakítva/szüneteltetve: {e}", True) # Vagy False, ha csak pause
            # Ha ez a kemény stop miatt volt, akkor a befejezési üzenet más lehet.
            # Jelenleg a pause nem dob kivételt, csak blokkol. A kemény stop igen.
            if self._stop_requested_by_main:
                 self.automation_finished.emit(f"Felhasználó által végleg leállítva. Feldolgozva: {prompts_processed_count}/{total_prompts_to_process}.")
            else: # Ez az ág valószínűleg nem fut le, ha a pause nem dob kivételt.
                 self.automation_finished.emit(f"Folyamat megszakadt. Feldolgozva: {prompts_processed_count}/{total_prompts_to_process}.")

        except Exception as e:
            # ... (kritikus hiba kezelése) ...
            pass
        finally:
            self._is_task_running_in_worker = False
            self.hide_overlay_requested.emit()
            # ... (egyéb cleanup, ha szükséges a workerben) ...
