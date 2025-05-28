# core/page_initializer.py
import pyautogui
import time
import os
import numpy as np # Az _find_text_with_easyocr_and_click metódushoz kell

# EasyOCR importálása (a PyAutoGuiAutomator adja át az ocr_reader-t)

class PageInitializer:
    def __init__(self, automator_ref):
        """
        Inicializáló.
        Args:
            automator_ref: Hivatkozás a fő PyAutoGuiAutomator példányra,
                           hogy elérje annak segédfüggvényeit és tagváltozóit.
        """
        self.automator = automator_ref
        self.ocr_reader = self.automator.ocr_reader 

    def _notify_status(self, message, is_error=False):
        self.automator._notify_status(message, is_error)

    def _check_for_stop_request(self):
        return self.automator._check_for_stop_request()

    def _find_text_with_easyocr_and_click(self, target_text, description, 
                                          timeout_s=20,
                                          initial_confidence_threshold=0.6,
                                          min_confidence_threshold=0.2,
                                          confidence_step=0.1,
                                          click_element=True,
                                          search_region=None):
        if self._check_for_stop_request(): return None 
        if not self.ocr_reader:
            self._notify_status("HIBA: EasyOCR olvasó nincs inicializálva a szövegkereséshez (PageInitializer).", is_error=True)
            return None

        region_log_str = f"({search_region[0]},{search_region[1]},{search_region[2]},{search_region[3]})" if search_region else "Teljes képernyő"
        self._notify_status(f"Szöveg keresése (PageInitializer): '{target_text}' ({description}) (max {timeout_s}s, régió: {region_log_str}). Kezdeti konf.: {initial_confidence_threshold:.2f}")
        
        overall_start_time = time.time()
        attempt_confidence = initial_confidence_threshold
        last_screenshot_pil = None 

        while attempt_confidence >= min_confidence_threshold:
            if self._check_for_stop_request(): return None 
            
            elapsed_time = time.time() - overall_start_time
            if elapsed_time > timeout_s:
                self._notify_status(f"Teljes időkorlát ({timeout_s}s) lejárt '{target_text}' keresése közben (utolsó konf.: {attempt_confidence:.2f}).", is_error=True)
                break 
            
            self._notify_status(f"Keresés '{target_text}' ({description}) konfidenciával: {attempt_confidence:.2f}. Fennmaradó idő: {max(0, timeout_s - elapsed_time):.1f}s")
            
            try:
                last_screenshot_pil = pyautogui.screenshot(region=search_region) 
                if self._check_for_stop_request(): return None
                
                screenshot_np = np.array(last_screenshot_pil) 
                ocr_results = self.ocr_reader.readtext(screenshot_np, detail=1, paragraph=False) 
                
                best_match_for_current_confidence = None

                for (bbox, text, prob) in ocr_results:
                    if self._check_for_stop_request(): return None
                    text_strip = text.strip()
                    if prob >= attempt_confidence and target_text.lower() in text_strip.lower():
                        x_coords = [p[0] for p in bbox]
                        y_coords = [p[1] for p in bbox]
                        min_x_rel, max_x_rel = min(x_coords), max(x_coords)
                        min_y_rel, max_y_rel = min(y_coords), max(y_coords)
                        
                        center_x_rel = (min_x_rel + max_x_rel) // 2
                        center_y_rel = (min_y_rel + max_y_rel) // 2

                        abs_center_x = center_x_rel + (search_region[0] if search_region else 0)
                        abs_center_y = center_y_rel + (search_region[1] if search_region else 0)
                        
                        current_match = {"x": abs_center_x, "y": abs_center_y, "text": text_strip, "prob": prob}
                        if best_match_for_current_confidence is None or prob > best_match_for_current_confidence["prob"]:
                            best_match_for_current_confidence = current_match
                
                if best_match_for_current_confidence:
                    found_text_info = best_match_for_current_confidence
                    self._notify_status(f"Szöveg '{found_text_info['text']}' (cél: '{target_text}') MEGTALÁLVA itt: ({found_text_info['x']}, {found_text_info['y']}) konfidenciával: {found_text_info['prob']:.2f} (keresési konf.: {attempt_confidence:.2f})")
                    if click_element:
                        pyautogui.moveTo(found_text_info['x'], found_text_info['y'], duration=0.1)
                        pyautogui.click()
                        self._notify_status(f"'{description}' (EasyOCR alapján) gombra/helyre kattintva.")
                    return (found_text_info['x'], found_text_info['y'])

            except Exception as e_ocr_loop:
                self._notify_status(f"Hiba az EasyOCR feldolgozási ciklusban (konf: {attempt_confidence:.2f}): {e_ocr_loop}", is_error=True)
                time.sleep(0.3) 
            
            attempt_confidence -= confidence_step
            if attempt_confidence < min_confidence_threshold and min_confidence_threshold > 0:
                if abs(attempt_confidence + confidence_step - min_confidence_threshold) < 0.001 :
                     break 
                attempt_confidence = min_confidence_threshold

        self._notify_status(f"'{target_text}' szöveg nem található EasyOCR-rel {timeout_s} másodperc alatt, még {min_confidence_threshold:.2f} minimális konfidenciával sem a(z) {'Teljes képernyő' if not search_region else str(search_region)} régióban.", is_error=True)
        # Hibakereső kép mentése (opcionális, de hasznos lehet)
        try:
            if last_screenshot_pil and self.automator.assets_dir and os.path.exists(self.automator.assets_dir):
                region_str_file = f"region_{search_region[0]}_{search_region[1]}_{search_region[2]}_{search_region[3]}" if search_region else "fullscreen"
                ts = time.strftime("%Y%m%d_%H%M%S")
                safe_target_text = "".join(c if c.isalnum() else "_" for c in target_text[:20])
                debug_img_name = f"debug_ocr_fail_PI_{safe_target_text}_{region_str_file}_{ts}.png" # PI = PageInitializer
                debug_screenshot_path = os.path.join(self.automator.assets_dir, debug_img_name)
                last_screenshot_pil.save(debug_screenshot_path)
                self._notify_status(f"Hibakeresési képernyőkép mentve (PageInitializer OCR sikertelen): {debug_screenshot_path}", is_error=True)
        except Exception as e_screenshot:
            self._notify_status(f"Hiba a hibakeresési képernyőkép mentése közben (PageInitializer): {e_screenshot}", is_error=True)
        return None

    def run_initial_tool_opening_sequence(self):
        """
        Elvégzi az oldal kezdeti előkészítését: "ESZKÖZ MEGNYITÁSA" gombra kattint,
        vár az oldal betöltődésére, majd aktiválja a prompt mezőt.
        """
        if self._check_for_stop_request(): return False
        
        self._notify_status("OLDAL ELŐKÉSZÍTÉS: Kezdeti műveletek indítása...")
        initial_wait_s = 3
        self._notify_status(f"Extra várakozás {initial_wait_s}s az oldalinterakció előtt...")
        for _ in range(initial_wait_s):
            if self._check_for_stop_request(): return False
            time.sleep(1)
        self._notify_status("Oldal stabilizálódott (feltételezett).")

        self._notify_status("'ESZKÖZ MEGNYITÁSA' gomb keresése...")
        
        open_tool_region_top = int(self.automator.screen_height * 0.33) 
        open_tool_region_left = int(self.automator.screen_width * 0.28)
        open_tool_region_width = int(self.automator.screen_width * 0.44)
        open_tool_region_height = int(self.automator.screen_height * 0.15) 
        precise_open_tool_region = (open_tool_region_left, open_tool_region_top, open_tool_region_width, open_tool_region_height)
        target_text_for_button = "ESZKÖZ MEGNYITÁSA"
        
        button_pos = self._find_text_with_easyocr_and_click(
            target_text_for_button, 
            "'ESZKÖZ MEGNYITÁSA' gomb (EasyOCR, pontosított régió)", 
            timeout_s=20, initial_confidence_threshold=0.60, 
            min_confidence_threshold=0.25, confidence_step=0.1,
            search_region=precise_open_tool_region, click_element=True 
        )
        if not button_pos:
            if self._check_for_stop_request(): return False
            self._notify_status("Az 'ESZKÖZ MEGNYITÁSA' gombot a pontosított régióban nem sikerült megtalálni. Próbálkozás teljes képernyőn...", is_error=True)
            button_pos = self._find_text_with_easyocr_and_click(
                target_text_for_button, 
                "'ESZKÖZ MEGNYITÁSA' gomb (EasyOCR, fallback teljes képernyő)", 
                timeout_s=20, initial_confidence_threshold=0.55,
                min_confidence_threshold=0.20, confidence_step=0.1,
                search_region=None, click_element=True 
            )
            if not button_pos:
                 if self._check_for_stop_request(): return False
                 self._notify_status("HIBA: Az 'ESZKÖZ MEGNYITÁSA' gombot nem sikerült megtalálni. Az automatizálás nem folytatható.", is_error=True)
                 return False
        
        self._notify_status("'ESZKÖZ MEGNYITÁSA' gombra kattintás sikeresnek tűnik.")
        wait_after_button_click_s = 8 
        self._notify_status(f"Várakozás {wait_after_button_click_s}s az eszköz felületének betöltődésére...")
        for _ in range(wait_after_button_click_s):
            if self._check_for_stop_request(): return False
            time.sleep(1)
        self._notify_status("Eszköz felülete betöltődött (feltételezett).")

        # A prompt mező első aktiválása a fő automator osztály metódusával
        # Ezt a PyAutoGuiAutomator fogja hívni, miután ez a metódus sikeresen lefutott.
        # Tehát itt csak jelezzük, hogy ez a fázis kész.
        # Vagy, ha ez az osztály felelős a prompt mező első aktiválásáért is, akkor itt hívnánk
        # a self.automator._find_and_activate_prompt_field()-et.
        # A jelenlegi struktúra szerint a PyAutoGuiAutomator hívja majd ezt.
        
        self._notify_status("OLDAL ELŐKÉSZÍTÉS: Sikeres (ESZKÖZ MEGNYITÁSA megtörtént).")
        return True
