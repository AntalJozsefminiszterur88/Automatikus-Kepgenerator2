# core/prompt_executor.py
import pyautogui
import time
import os # Bár itt lehet, hogy nem lesz rá közvetlenül szükség, de az ui_scanner miatt maradhat

try:
    from utils.ui_scanner import (find_generate_button_dynamic, 
                                  GENERATE_BUTTON_COLOR_TARGET) # Csak ami itt kell
except ImportError:
    print("FIGYELEM: Az 'utils.ui_scanner' modul nem található (PromptExecutor).")
    find_generate_button_dynamic = None
    GENERATE_BUTTON_COLOR_TARGET = None 

class PromptExecutor:
    def __init__(self, automator_ref):
        """
        Inicializáló.
        Args:
            automator_ref: Hivatkozás a fő PyAutoGuiAutomator példányra.
        """
        self.automator = automator_ref

    def _notify_status(self, message, is_error=False):
        self.automator._notify_status(message, is_error)

    def _check_for_stop_request(self):
        return self.automator._check_for_stop_request()

    def enter_prompt_and_initiate_generation(self, prompt_text):
        """
        Aktiválja a prompt mezőt, beírja a promptot, megkeresi és megnyomja a generálás gombot.
        """
        if self._check_for_stop_request(): return False
        self._notify_status(f"PROMPT VÉGREHAJTÁS: Kezdés ('{prompt_text[:20]}...')")

        # 1. Prompt mező újra-aktiválása
        # A _find_and_activate_prompt_field metódus a PyAutoGuiAutomator-ban van,
        # mert az kezeli a koordináták mentését/töltését is.
        if not self.automator._find_and_activate_prompt_field(): 
            self._notify_status("HIBA: Nem sikerült újra-aktiválni a prompt mezőt a beírás előtt (PromptExecutor).", is_error=True)
            return False

        # 2. Prompt beírása
        self._notify_status(f"Prompt beírása: '{prompt_text[:30]}...'")
        try:
            pyautogui.hotkey('ctrl', 'a'); time.sleep(0.05) 
            pyautogui.press('delete'); time.sleep(0.1) 
            pyautogui.typewrite(prompt_text, interval=0.01); time.sleep(0.2)
        except Exception as e_type:
            self._notify_status(f"Hiba a prompt beírása közben: {e_type}", is_error=True)
            return False

        # 3. Generálás Gomb kezelése
        gen_x, gen_y = None, None
        action_taken_for_generate_button = False

        # Először a mentett koordinátákat próbáljuk
        if "generate_button_click_x" in self.automator.coordinates and \
           "generate_button_click_y" in self.automator.coordinates:
            gen_x = self.automator.coordinates["generate_button_click_x"]
            gen_y = self.automator.coordinates["generate_button_click_y"]
            self._notify_status(f"Mentett generálás gomb pozíció használata: X={gen_x}, Y={gen_y}")
            action_taken_for_generate_button = True
        # Ha nincs mentett, és a dinamikus kereső elérhető és van prompt téglalapunk
        elif find_generate_button_dynamic and self.automator.last_known_prompt_rect and GENERATE_BUTTON_COLOR_TARGET:
            self._notify_status(f"Generálás gomb dinamikus keresése szín ({GENERATE_BUTTON_COLOR_TARGET}) alapján...")
            pos = find_generate_button_dynamic(
                self.automator.last_known_prompt_rect, 
                self.automator.screen_width, 
                self.automator.screen_height, 
                notify_callback=self._notify_status
            )
            if pos:
                gen_x, gen_y = pos
                self.automator.coordinates["generate_button_click_x"] = gen_x
                self.automator.coordinates["generate_button_click_y"] = gen_y
                self.automator._save_coordinates() 
                self._notify_status(f"Dinamikusan talált generálás gomb. Kattintás ide: X={gen_x}, Y={gen_y}")
                action_taken_for_generate_button = True
            else: 
                self._notify_status("HIBA: Generálás gombot nem sikerült dinamikusan megtalálni.", is_error=True)
                return False # Ha a dinamikus keresés elindult, de nem talált semmit
        else:
            self._notify_status("HIBA: Generálás gomb pozíciója nem ismert (dinamikus kereső nem elérhető/konfigurálva, vagy a prompt terület ismeretlen, és nincs mentett).", is_error=True)
            return False

        if not action_taken_for_generate_button or gen_x is None:
            self._notify_status("HIBA: Nem sikerült meghatározni a generálás gomb pozícióját a kattintáshoz.", is_error=True)
            return False

        try:
            pyautogui.moveTo(gen_x, gen_y, duration=0.2)
            pyautogui.click()
            self._notify_status("Generálás elindítva.")
            self._notify_status("PROMPT VÉGREHAJTÁS: Sikeres (Prompt beírva, generálás elindítva).")
            return True
        except Exception as e_click_generate:
            self._notify_status(f"Hiba történt a generálás gombra való kattintás közben (X:{gen_x}, Y:{gen_y}): {e_click_generate}", is_error=True)
            # Hiba esetén töröljük a (potenciálisan rossz) mentett koordinátát
            if "generate_button_click_x" in self.automator.coordinates: del self.automator.coordinates["generate_button_click_x"]
            if "generate_button_click_y" in self.automator.coordinates: del self.automator.coordinates["generate_button_click_y"]
            self.automator._save_coordinates()
            return False
