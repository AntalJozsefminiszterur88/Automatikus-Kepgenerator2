# core/prompt_handler.py

class PromptHandler:
    """
    Felelős a promptokat tartalmazó TXT fájl beolvasásáért és feldolgozásáért.
    """
    def __init__(self, process_controller_ref=None):
        """
        Inicializáló.
        :param process_controller_ref: Hivatkozás a ProcessController példányra,
                                       ha státuszüzeneteket kellene küldenie (opcionális).
        """
        self.process_controller = process_controller_ref
        print("PromptHandler inicializálva.")

    def _notify_status(self, message):
        """Segédfüggvény a státusz közlésére a ProcessControlleren keresztül."""
        if self.process_controller and hasattr(self.process_controller, 'update_gui_status'):
            self.process_controller.update_gui_status(message)
        else:
            print(f"[PromptHandler]: {message}") # Fallback

    def load_prompts(self, file_path, start_line, end_line):
        """
        Beolvassa a promptokat a megadott fájlból, a megadott start_line és end_line között.
        A sorszámok 1-alapúak.
        """
        prompts_to_process = []
        if not file_path:
            self._notify_status("Hiba: Nincs megadva prompt fájl elérési útja.")
            return prompts_to_process

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                all_lines = [line.strip() for line in f if line.strip()] # Üres sorok kihagyása
        except FileNotFoundError:
            self._notify_status(f"Hiba: A '{file_path}' fájl nem található.")
            return prompts_to_process
        except Exception as e:
            self._notify_status(f"Hiba a '{file_path}' fájl olvasása közben: {e}")
            return prompts_to_process

        total_prompts_in_file = len(all_lines)
        if total_prompts_in_file == 0:
            self._notify_status(f"Hiba: A '{file_path}' fájl üres vagy csak üres sorokat tartalmaz.")
            return prompts_to_process

        # Sorszámok validálása (1-alapú indexelés a felhasználó felé, 0-alapú a listakezeléshez)
        # A start_line és end_line már a GUI-n validálva lehet, de itt is érdemes ellenőrizni.
        actual_start_index = start_line - 1
        actual_end_index = end_line # Az end_line itt a feldolgozandó promptok darabszámát jelöli a start_line-tól,
                                    # VAGY az utolsó feldolgozandó sor sorszámát. Tisztázzuk a GUI logikával.
                                    # A googleprompt.py-ban target_prompt_count volt.
                                    # Maradjunk annál, hogy az end_line az utolsó feldolgozandó sor sorszáma (1-alapú).
                                    # Tehát a szeleteléshez az end_line-ig kell menni.

        if actual_start_index < 0:
            self._notify_status("Hiba: A kezdő sorszám érvénytelen (túl kicsi).")
            return prompts_to_process
        
        if actual_start_index >= total_prompts_in_file:
            self._notify_status(f"Hiba: A kezdő sorszám ({start_line}) nagyobb, mint a fájlban lévő promptok száma ({total_prompts_in_file}).")
            return prompts_to_process
        
        # A szeletelés felső határa exkluzív, ezért ha az end_line az utolsó sor sorszáma, akkor az actual_end_index legyen end_line.
        # A list[start:end] az elemeket adja vissza start-tól end-1-ig.
        # Ha pl. start_line=1, end_line=3, akkor az 1., 2., 3. sort akarjuk.
        # Ez az all_lines[0], all_lines[1], all_lines[2]. Tehát all_lines[actual_start_index : end_line]
        
        # Ha az end_line nagyobb, mint a fájlban lévő sorok, akkor csak a végéig olvasunk.
        effective_end_index = min(end_line, total_prompts_in_file)

        if actual_start_index >= effective_end_index:
             self._notify_status(f"Hiba: A kezdő sor ({start_line}) nem kisebb, mint a befejező sor ({effective_end_index}) a fájl tartalmához igazítva.")
             return prompts_to_process

        prompts_to_process = all_lines[actual_start_index:effective_end_index]
        
        if not prompts_to_process:
            self._notify_status("Nincsenek feldolgozandó promptok a megadott tartományban.")
        else:
            self._notify_status(f"{len(prompts_to_process)} prompt sikeresen betöltve a(z) '{file_path.split('/')[-1]}' fájlból ({start_line}-{effective_end_index}. sor).")
            
        return prompts_to_process
