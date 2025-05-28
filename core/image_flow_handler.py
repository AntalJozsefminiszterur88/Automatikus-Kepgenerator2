# core/image_flow_handler.py
import pyautogui
import time
import os # Szükséges lehet, ha a jövőben fájlnevekkel is dolgozna

class ImageFlowHandler:
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

    def monitor_generation_and_download(self):
        """
        Figyeli a kép generálásának befejezését pixel alapján,
        majd rákattint a letöltés gombra.
        """
        if self._check_for_stop_request(): return False
        self._notify_status("KÉP FELDOLGOZÁS: Generálás figyelése és letöltés indítása...")
        
        # 1. Pixel figyelés logika
        self._notify_status("Kép generálásának figyelése pixel alapján...")
        initial_wait_after_generate_click_s = 2
        self._notify_status(f"Várakozás {initial_wait_after_generate_click_s}s a generálás tényleges megkezdésére...")
        time.sleep(initial_wait_after_generate_click_s)
        if self._check_for_stop_request(): return False

        pixel_x_to_watch = 890
        pixel_y_to_watch = 487
        expected_color_during_generation = (217, 217, 217) 
        max_wait_s_for_pixel_change = 45 
        check_interval_s = 0.5 

        self._notify_status(f"Pixel ({pixel_x_to_watch},{pixel_y_to_watch}) színének figyelése. Várt szín generálás közben: {expected_color_during_generation}.")
        start_pixel_watch_time = time.time()
        color_changed = False

        while time.time() - start_pixel_watch_time < max_wait_s_for_pixel_change:
            if self._check_for_stop_request():
                self._notify_status("Pixel figyelés megszakítva felhasználói kéréssel.", is_error=True)
                return False
            try:
                current_pixel_color = pyautogui.pixel(pixel_x_to_watch, pixel_y_to_watch)
                if current_pixel_color[0] != expected_color_during_generation[0] or \
                   current_pixel_color[1] != expected_color_during_generation[1] or \
                   current_pixel_color[2] != expected_color_during_generation[2]:
                    self._notify_status(f"Pixel színe megváltozott! (Új szín: {current_pixel_color}). Generálás befejeződött.")
                    color_changed = True
                    break 
                else:
                    remaining_time = int(max_wait_s_for_pixel_change - (time.time() - start_pixel_watch_time))
                    if remaining_time % 5 == 0 or remaining_time < 5 : 
                        self._notify_status(f"Generálás még folyamatban (pixel színe: {current_pixel_color})... ({remaining_time}s hátra a timeout-ig)")
            except Exception as e_pixel:
                self._notify_status(f"Hiba a pixel ({pixel_x_to_watch},{pixel_y_to_watch}) színének olvasása közben: {e_pixel}", is_error=True)
                time.sleep(check_interval_s * 2) 
            time.sleep(check_interval_s)
        
        if not color_changed:
            self._notify_status(f"Időtúllépés: A pixel színe nem változott meg {max_wait_s_for_pixel_change}s alatt.", is_error=True)
            return False

        wait_after_color_change_s = 2
        self._notify_status(f"Generálás befejeződött (pixel szín alapján). Várakozás {wait_after_color_change_s}s a letöltés előtt...")
        time.sleep(wait_after_color_change_s)
        if self._check_for_stop_request(): return False
        
        self._notify_status("Kép elkészült (pixel figyelés alapján). Letöltés következik...")

        # 2. Letöltés gomb kezelése (mentett vagy fix koordinátákkal)
        download_button_x = None
        download_button_y = None
        if "download_button_click_x" in self.automator.coordinates and \
           "download_button_click_y" in self.automator.coordinates:
            download_button_x = self.automator.coordinates["download_button_click_x"]
            download_button_y = self.automator.coordinates["download_button_click_y"]
            self._notify_status(f"Mentett letöltés gomb pozíció használata: X={download_button_x}, Y={download_button_y}")
        else: # Ha nincs mentett, használjuk a korábbi fixet és mentsük el
            download_button_x = 925 # Alapértelmezett fix koordináta
            download_button_y = 704
            self._notify_status(f"Fix letöltés gomb pozíció használata (és mentése): X={download_button_x}, Y={download_button_y}.")
            self.automator.coordinates["download_button_click_x"] = download_button_x
            self.automator.coordinates["download_button_click_y"] = download_button_y
            self.automator._save_coordinates() # Mentés a fő automator példányon keresztül

        self._notify_status(f"Kattintás a letöltés gombra: X={download_button_x}, Y={download_button_y}")
        try:
            pyautogui.moveTo(download_button_x, download_button_y, duration=0.2)
            pyautogui.click()
            self._notify_status("Letöltés gombra kattintva.")
        except Exception as e_click_download:
            self._notify_status(f"Hiba történt a letöltés gombra való kattintás közben (X:{download_button_x}, Y:{download_button_y}): {e_click_download}", is_error=True)
            return False

        download_confirmation_wait_s = 0.5 
        if download_confirmation_wait_s > 0:                                        
            self._notify_status(f"Rövid várakozás ({download_confirmation_wait_s}s) a letöltés elindulására...")
            time.sleep(download_confirmation_wait_s) 
        
        self._notify_status("Kép letöltése elindítva (feltételezett).")
        self._notify_status("KÉP FELDOLGOZÁS: Sikeres.")
        return True
