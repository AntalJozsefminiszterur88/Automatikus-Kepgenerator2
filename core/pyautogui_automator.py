# core/pyautogui_automator.py
import pyautogui
import time
import os
import json 
import numpy as np # Megtartjuk, ha a PageInitializer-ben az OCR mégis itt lenne definiálva

try:
    from utils.ui_scanner import (find_prompt_area_dynamically, 
                                  find_generate_button_dynamic, 
                                  get_screen_size_util, 
                                  GENERATE_BUTTON_COLOR_TARGET)
except ImportError:
    print("FIGYELEM: Az 'utils.ui_scanner' modul nem található vagy hibás. A dinamikus UI elemkeresés nem lesz teljesen elérhető.")
    find_prompt_area_dynamically = None
    find_generate_button_dynamic = None
    get_screen_size_util = lambda: pyautogui.size() 
    GENERATE_BUTTON_COLOR_TARGET = None 

try:
    import easyocr
except ImportError:
    print("FIGYELEM: Az 'easyocr' könyvtár nincs telepítve vagy nem érhető el.")
    easyocr = None

# Új importok a szétbontott modulokhoz
from .page_initializer import PageInitializer
from .prompt_executor import PromptExecutor
from .image_flow_handler import ImageFlowHandler


class PyAutoGuiAutomator:
    def __init__(self, process_controller_ref=None):
        self.process_controller = process_controller_ref
        self.stop_requested = False
        self.page_is_prepared = False 

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.script_dir)
        self.assets_dir = os.path.join(self.project_root, "automation_assets") # Hibakereső képekhez még kellhet
        self.config_dir = os.path.join(self.project_root, "config") 
        if not os.path.exists(self.config_dir):
            try:
                os.makedirs(self.config_dir)
            except Exception as e_mkdir:
                self._notify_status(f"Hiba a config mappa létrehozásakor: {e_mkdir}", is_error=True)
        self.ui_coords_file = os.path.join(self.config_dir, "ui_coordinates.json")

        self.ocr_reader = None 
        if easyocr: 
            try:
                self._notify_status("EasyOCR olvasó inicializálása ('en', 'hu')...")
                self.ocr_reader = easyocr.Reader(['en', 'hu'], gpu=False)
                self._notify_status("EasyOCR olvasó sikeresen inicializálva.")
            except Exception as e_ocr_init:
                self._notify_status(f"Hiba az EasyOCR olvasó inicializálásakor: {e_ocr_init}", is_error=True)
        
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1 
        
        try:
            self.screen_width, self.screen_height = get_screen_size_util()
        except Exception: 
             self._notify_status("Figyelmeztetés: get_screen_size_util nem volt hívható vagy hibát adott, pyautogui.size() használata.", is_error=True)
             self.screen_width, self.screen_height = pyautogui.size()
            
        self.coordinates = self._load_coordinates() 
        self.last_known_prompt_rect = self.coordinates.get("prompt_rect") if isinstance(self.coordinates.get("prompt_rect"), dict) else None

        # Handler osztályok példányosítása
        self.page_initializer = PageInitializer(self)
        self.prompt_executor = PromptExecutor(self)
        self.image_flow_handler = ImageFlowHandler(self)

        print("PyAutoGuiAutomator inicializálva (moduláris felépítéssel).")

    def _load_coordinates(self):
        try:
            if os.path.exists(self.ui_coords_file):
                with open(self.ui_coords_file, 'r') as f:
                    coords = json.load(f)
                    if coords and isinstance(coords, dict) :
                        self._notify_status(f"UI koordináták betöltve: {self.ui_coords_file}")
                        return coords
            self._notify_status(f"Koordináta fájl ({self.ui_coords_file}) nem található vagy üres. Dinamikus keresés szükséges.")
        except Exception as e:
            self._notify_status(f"Hiba a koordináták betöltése közben: {e}", is_error=True)
        return {} 

    def _save_coordinates(self):
        try:
            if not self.coordinates: 
                self._notify_status("Nincsenek érvényes koordináták a mentéshez (self.coordinates üres).", is_error=True)
                return
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir)
            with open(self.ui_coords_file, 'w') as f:
                json.dump(self.coordinates, f, indent=4)
            self._notify_status(f"UI koordináták elmentve: {self.ui_coords_file}")
        except Exception as e:
            self._notify_status(f"Hiba a koordináták mentése közben: {e}", is_error=True)

    def _notify_status(self, message, is_error=False):
        if self.process_controller and hasattr(self.process_controller, 'update_gui_status'):
            self.process_controller.update_gui_status(message, is_error=is_error)
        else:
            print(f"[{'HIBA' if is_error else 'INFO'} PyAutoGuiAutomator]: {message}")

    def request_stop(self):
        self._notify_status("PyAutoGUI automatizálási folyamat leállítási kérelem érkezett.")
        self.stop_requested = True # Ezt a jelzőt a handler osztályoknak is figyelniük kellene

    def _check_for_stop_request(self):
        # Ezt a közös logikát a handler osztályok is használhatják a self.automator._check_for_stop_request() hívással
        if self.process_controller and hasattr(self.process_controller, '_stop_requested_by_user') and self.process_controller._stop_requested_by_user:
            self.stop_requested = True
        # if self.stop_requested: # Ritkítjuk a logolást, csak akkor logoljon, ha tényleg releváns a hiba
        #     pass 
        return self.stop_requested

    def _find_and_activate_prompt_field(self): # Ez a metódus továbbra is itt van, mert a `coordinates`-t kezeli
        if self._check_for_stop_request(): return False
        click_x, click_y = None, None
        prompt_field_activated_successfully = False

        if "prompt_click_x" in self.coordinates and "prompt_click_y" in self.coordinates:
            click_x = self.coordinates["prompt_click_x"]
            click_y = self.coordinates["prompt_click_y"]
            if "prompt_rect" in self.coordinates and isinstance(self.coordinates.get("prompt_rect"), dict):
                self.last_known_prompt_rect = self.coordinates["prompt_rect"]
            else: 
                self.last_known_prompt_rect = None
            self._notify_status(f"Mentett prompt mező pozíció használata: X={click_x}, Y={click_y}")
            prompt_field_activated_successfully = True
        
        if not prompt_field_activated_successfully and find_prompt_area_dynamically:
            self._notify_status("Prompt mező dinamikus keresése...")
            rect = find_prompt_area_dynamically(self.screen_width, self.screen_height, notify_callback=self._notify_status)
            if rect:
                self.last_known_prompt_rect = rect 
                click_x = rect['x'] + rect['width'] // 2
                click_y = rect['y'] + int(rect['height'] * 0.30) 
                click_x = max(0, min(click_x, self.screen_width - 1))
                click_y = max(0, min(click_y, self.screen_height - 1))
                
                self.coordinates["prompt_click_x"] = click_x
                self.coordinates["prompt_click_y"] = click_y
                self.coordinates["prompt_rect"] = rect 
                self._save_coordinates()
                self._notify_status(f"Dinamikusan talált prompt terület. Kattintás ide: X={click_x}, Y={click_y}")
                prompt_field_activated_successfully = True
            else:
                self._notify_status("HIBA: A prompt területet nem sikerült dinamikusan megtalálni.", is_error=True)
                if not ("prompt_click_x" in self.coordinates and "prompt_click_y" in self.coordinates) : 
                     return False 
        elif not find_prompt_area_dynamically and not prompt_field_activated_successfully:
             self._notify_status("HIBA: Dinamikus prompt kereső nem elérhető és nincsenek mentett koordináták.", is_error=True)
             return False

        if not prompt_field_activated_successfully or click_x is None:
            self._notify_status("HIBA: Nem sikerült meghatározni a prompt mező kattintási pontját (sem mentett, sem dinamikus).", is_error=True)
            return False

        try:
            pyautogui.moveTo(click_x, click_y, duration=0.1)
            pyautogui.click()
            time.sleep(0.3) 
            self._notify_status("Prompt mező aktiválva/újra-aktiválva.")
            return True
        except Exception as e:
            self._notify_status(f"Hiba a prompt mezőre való kattintás közben (X:{click_x}, Y:{click_y}): {e}", is_error=True)
            return False

    # --- PUBLIKUS METÓDUSOK A PROCESSCONTROLLER SZÁMÁRA ---
    def initial_page_setup(self):
        """Elvégzi az oldal kezdeti beállítását a PageInitializer segítségével."""
        if self._check_for_stop_request(): return False
        if not self.page_is_prepared:
            if self.page_initializer.run_initial_tool_opening_sequence(): # Hívjuk az új osztály metódusát
                self.page_is_prepared = True
                return True
            else:
                self.page_is_prepared = False
                return False
        self._notify_status("Az oldal kezdeti beállítása már megtörtént.")
        return True

    def process_single_prompt(self, prompt_text):
        """Feldolgoz egyetlen promptot a megfelelő handler osztályok segítségével."""
        self.stop_requested = False # Minden promptnál alaphelyzetbe állítjuk
        if self._check_for_stop_request(): return False

        if not self.page_is_prepared:
            self._notify_status("HIBA: Az oldal nincs előkészítve a prompt feldolgozásához. Az initial_page_setup nem futott le sikeresen.", is_error=True)
            return False
        
        # 2. Fázis: Prompt beírása és generálás
        if not self.prompt_executor.enter_prompt_and_initiate_generation(prompt_text):
            return False
        if self._check_for_stop_request(): return False
        
        # 3. Fázis: Kép generálásának figyelése és letöltés
        if not self.image_flow_handler.monitor_generation_and_download():
            return False
            
        self._notify_status(f"Prompt ('{prompt_text[:30]}...') sikeresen feldolgozva PyAutoGUI-val.")
        return True
    
    def close_browser(self):
        self._notify_status("PyAutoGUI böngészőműveletek befejezve.")
        pass
