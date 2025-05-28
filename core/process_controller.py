# core/process_controller.py fájlban az AutomationWorker osztály

# ... (importok és InterruptedByUserError osztály változatlan)

class AutomationWorker(QObject):
    # ... (signálok és __init__ változatlan)
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
        self._stop_requested_by_main = False    
        
        self._is_paused = False 
        self._pause_event = threading.Event()
        self._pause_event.set() 

        if hasattr(self.pc_ref.gui_automator, 'stop_requested'):
            self.pc_ref.gui_automator.stop_requested = False
        if hasattr(self.pc_ref.gui_automator, 'page_is_prepared'): 
            self.pc_ref.gui_automator.page_is_prepared = False
        # print("AutomationWorker inicializálva.") # Ezt a ProcessController __init__ végénél lehetne


    def _check_pause_and_stop(self):
        # Adjunk esélyt a Qt események (pl. queued slot hívások) feldolgozására ezen a szálon
        current_qthread = QThread.currentThread()
        if current_qthread:
            # print(f"Worker DBG (szál: {threading.get_ident()}): QThread.yieldCurrentThread() hívása _check_pause_and_stop elején.")
            current_qthread.yieldCurrentThread() 
            # Alternatív, agresszívabb eseményfeldolgozás (óvatosan, ritkán használd):
            # current_qthread.eventDispatcher().processEvents(QEventLoop.AllEvents)
            # Vagy egy nagyon rövid msleep, ami szintén processálhatja az eseményeket:
            # current_qthread.msleep(1) # 1 ms alvás, hogy az eseményhurok fusson

        if self._stop_requested_by_main: 
            self.status_updated.emit("Worker: Kemény stop kérés feldolgozva a _check_pause_and_stop-ban.", False)
            print("Worker DBG: Kemény stop kérés miatt InterruptedByUserError dobása.")
            raise InterruptedByUserError("Kemény stop kérés.")

        if self._is_paused:
            current_thread_id = threading.get_ident()
            self.status_updated.emit(f"Automatizálás szünetel (Worker szál: {current_thread_id}). Várakozás... Numpad 0 a folytatáshoz.", False)
            print(f"Worker DBG (szál: {current_thread_id}): Állapot SZÜNETEL. _is_paused={self._is_paused}. _pause_event.wait() hívás...")
            self._pause_event.wait() 
            print(f"Worker DBG (szál: {current_thread_id}): Szüneteltetés feloldva, _pause_event.wait() visszatért. _is_paused={self._is_paused}")
        
        if self._stop_requested_by_main: 
            self.status_updated.emit("Worker: Kemény stop kérés feldolgozva szünet után.", False)
            print("Worker DBG: Kemény stop kérés miatt InterruptedByUserError dobása (szünet után).")
            raise InterruptedByUserError("Megszakítva szüneteltetés feloldása után (kemény stop).")

    @Slot()
    def request_hard_stop_from_main(self):
        # ... (változatlan az előző teljes válaszhoz képest)
        self.status_updated.emit("Worker: Kemény leállítási kérelem fogadva.", False)
        print("Worker DBG: request_hard_stop_from_main hívva.")
        self._stop_requested_by_main = True
        if hasattr(self.pc_ref.gui_automator, 'request_stop'): 
            self.pc_ref.gui_automator.request_stop()
            print("Worker DBG: gui_automator.request_stop() hívva (hard stop).")

        if self._is_paused: 
            self._is_paused = False 
            self._pause_event.set()
            print("Worker DBG: Szüneteltetés feloldva kemény stop miatt.")


    @Slot()
    def toggle_pause_resume_state(self):
        # ... (változatlan az előző teljes válaszhoz képest, a diagnosztikai printekkel együtt)
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
        # ... (A run_automation_task metódus többi része változatlan az előző teljes válaszhoz képest,
        # beleértve a QThread.msleep használatát a time.sleep helyett a belső várakozási ciklusokban,
        # és a _check_pause_and_stop() sűrű hívásait.)
        if self._is_task_running_in_worker: # Metódus eleji védelem
            return
        
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
                    if not vpn_manager.connect_to_server(target_vpn_server_group, target_vpn_country_code): # Ez már figyeli a pc_ref._stop_requested_by_user-t
                        if not self.pc_ref._stop_requested_by_user: 
                             self.status_updated.emit("Worker Figyelmeztetés: VPN csatlakozás sikertelennek tűnik.", True)
                    else: 
                        if not self.pc_ref._stop_requested_by_user:
                            self.status_updated.emit("Worker: VPN csatlakozás sikeresnek tűnik.", False)
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
                        current_qthread = QThread.currentThread()
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
                if gui_automator.initial_page_setup(): # Ez figyeli a pc_ref._stop_requested_by_user-t
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

                    if gui_automator.process_single_prompt(prompt_text): # Ez figyeli a pc_ref._stop_requested_by_user-t
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
                            current_qthread = QThread.currentThread()
                            if current_qthread: current_qthread.msleep(1000)
                            else: time.sleep(1) 
            
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

# A ProcessController osztály többi része változatlan az előző teljes kódban megadotthoz képest.
# Csak az AutomationWorker osztályon belüli _check_pause_and_stop elejére került
# a QThread.yieldCurrentThread() vagy QThread.msleep(1) javaslat.
# És a run_automation_task várakozási ciklusai használják a QThread.msleep()-et.
