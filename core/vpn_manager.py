# core/vpn_manager.py
import subprocess
import platform
import time
import os
# import json # Erre már nincs itt szükség
# try: # Erre már nincs itt szükség
#     import requests 
# except ImportError:
#     print("A 'requests' könyvtár nincs telepítve. Telepítsd: pip install requests")
#     requests = None

from utils.system_helper import find_executable_path, minimize_window_windows
from utils.ip_geolocation import get_public_ip_info # <<< ÚJ IMPORT

class VpnManager:
    def __init__(self, process_controller_ref=None):
        self.process_controller = process_controller_ref
        self.nordvpn_executable_path = None
        self.is_connected_to_target_server = False
        self.base_ip_info = None
        self._find_nordvpn()

    def _notify_status(self, message, is_error=False):
        # ... (változatlan)
        if self.process_controller and hasattr(self.process_controller, 'update_gui_status'):
            prefix = "VPN Hiba: " if is_error else "VPN Info: "
            self.process_controller.update_gui_status(f"{prefix}{message}")
        else:
            print(f"[VpnManager]: {message}")

    def _find_nordvpn(self):
        # ... (változatlan)
        executable_to_find = "nordvpn.exe" if platform.system() == "Windows" else "nordvpn"
        path_cli = find_executable_path(executable_to_find)
        if path_cli:
            self.nordvpn_executable_path = path_cli
            self._notify_status(f"NordVPN parancssori eszköz (CLI) megtalálva: {path_cli}")
            return
        self._notify_status(f"NordVPN parancssori eszköz ('{executable_to_find}') nem található. VPN műveletek nem lesznek elérhetőek.", is_error=True)


    # Az _get_public_ip_info metódus TÖRÖLVE INNEN, mert átkerült az ip_geolocation.py-ba

    def _launch_nordvpn_if_not_running(self, startup_wait_s=15):
        # ... (változatlan)
        if not self.nordvpn_executable_path:
            return False
        self._notify_status("NordVPN alkalmazás indítási/ébresztési kísérlet (ha szükséges)...")
        command_args_startup = [self.nordvpn_executable_path]
        try:
            subprocess.Popen(command_args_startup) 
            self._notify_status(f"NordVPN indítási parancs ('{self.nordvpn_executable_path}') kiadva a háttérben.")
        except Exception as e:
            self._notify_status(f"Hiba a NordVPN háttérben történő indítása közben: {e}", is_error=True)
            return False
        self._notify_status(f"Várakozás {startup_wait_s} másodperc a NordVPN szolgáltatások stabilizálódására az indítás után...")
        time.sleep(startup_wait_s)
        return True

    def connect_to_server(self, 
                          server_group_name="Singapore", 
                          target_country_code="SG",
                          connection_command_timeout_s=20, 
                          max_ip_check_retries=12, 
                          ip_check_interval_s=5):  
        
        self.is_connected_to_target_server = False
        self.base_ip_info = None

        if not self.nordvpn_executable_path:
            self._notify_status("NordVPN CLI ('nordvpn.exe') nincs beállítva vagy nem található.", is_error=True)
            return False

        self._notify_status("Eredeti publikus IP cím lekérdezése...")
        self.base_ip_info = get_public_ip_info() # <<< AZ IMPORTÁLT FÜGGVÉNY HÍVÁSA
        if self.base_ip_info:
            self._notify_status(f"Eredeti IP: {self.base_ip_info.get('ip')}, Ország: {self.base_ip_info.get('country_code')}")
        else:
            self._notify_status("Nem sikerült lekérdezni az eredeti IP címet. Folytatás IP ellenőrzés nélkül (csak feltételezett kapcsolódás).", is_error=True)
            # Itt dönthetünk, hogy leállunk-e, ha az IP ellenőrzés kritikus.
            # Egyelőre a kód folytatódik, de az IP ellenőrzési ciklus nem fogja tudni, mihez hasonlítson,
            # vagy nem fogja tudni ellenőrizni az országot. Ezért itt False-t kellene visszaadni.
            self._notify_status("Az IP alapú VPN kapcsolat ellenőrzése nem lehetséges az eredeti IP ismerete nélkül.", is_error=True)
            return False # Ha nincs eredeti IP, nem tudjuk megbízhatóan ellenőrizni a váltást.

        if not self._launch_nordvpn_if_not_running(startup_wait_s=10):
            self._notify_status("A NordVPN indítási/ébresztési fázisa sikertelen volt.", is_error=True)
            return False

        command_args_connect = [self.nordvpn_executable_path, "-c", "-g", server_group_name]
        self._notify_status(f"Csatlakozási parancs kiadása: \"{' '.join(command_args_connect)}\"...")
        
        try:
            self._notify_status(f"subprocess.run indítása a csatlakozáshoz, max {connection_command_timeout_s}s várakozással a parancs befejezésére...")
            process = subprocess.run(command_args_connect, capture_output=True, text=True, check=False, timeout=connection_command_timeout_s)

            self._notify_status(f"'{' '.join(command_args_connect)}' parancs befejeződött. Return code: {process.returncode}")
            if process.stdout and process.stdout.strip(): self._notify_status(f"Kimenet (stdout): {process.stdout.strip()}")
            if process.stderr and process.stderr.strip(): self._notify_status(f"Hibakimenet (stderr): {process.stderr.strip()}", is_error=True)

            if process.returncode == 0:
                self._notify_status(f"A csatlakozási parancs elfogadva (return code 0). IP cím ellenőrzése következik...")
                
                for attempt in range(max_ip_check_retries):
                    self._notify_status(f"IP ellenőrzési kísérlet ({attempt + 1}/{max_ip_check_retries})... Várakozás {ip_check_interval_s}s.")
                    time.sleep(ip_check_interval_s)

                    stop_requested = False
                    if self.process_controller and hasattr(self.process_controller, '_stop_requested_by_user'):
                        stop_requested = self.process_controller._stop_requested_by_user
                    if stop_requested:
                        self._notify_status("VPN IP ellenőrzési ciklus megszakítva felhasználói kéréssel.", is_error=True)
                        return False
                    
                    current_ip_info = get_public_ip_info() # <<< AZ IMPORTÁLT FÜGGVÉNY HÍVÁSA
                    if current_ip_info:
                        self._notify_status(f"Aktuális IP: {current_ip_info.get('ip')}, Ország: {current_ip_info.get('country_code')}")
                        if current_ip_info.get("country_code") == target_country_code.upper():
                            # Győződjünk meg róla, hogy az IP cím tényleg megváltozott (ha nem Szingapúrban kezdtünk)
                            if self.base_ip_info and current_ip_info.get("ip") == self.base_ip_info.get("ip") and \
                               self.base_ip_info.get("country_code") != target_country_code.upper(): # Ha az eredeti ország nem a célország volt
                                self._notify_status(f"Figyelem: Az országkód {target_country_code}, de az IP cím nem változott. Lehet, hogy a VPN nem tudott új IP-t kiosztani, vagy a geolokációs API lassan frissül.", is_error=True)
                                # Itt folytathatjuk a ciklust, vagy sikertelennek vehetjük. Egyelőre folytatjuk.
                            else: # Vagy ha az eredeti ország már a célország volt, vagy ha az IP megváltozott
                                self.is_connected_to_target_server = True
                                self._notify_status(f"VPN csatlakozás '{server_group_name}' ({target_country_code}) sikeresen ellenőrizve IP alapján!")
                                return True
                    else:
                        self._notify_status("Nem sikerült lekérdezni az aktuális IP címet az ellenőrzéshez ebben a ciklusban.", is_error=True)
                
                self._notify_status(f"Nem sikerült ellenőrizni a csatlakozást '{target_country_code}'-hoz {max_ip_check_retries} próbálkozás után IP alapján.", is_error=True)
                return False
            else:
                self._notify_status(f"A \"{' '.join(command_args_connect)}\" csatlakozási parancs hibával tért vissza (kód: {process.returncode}).", is_error=True)
                return False
        # ... (a többi except blokk és a disconnect_vpn, minimize_nordvpn_window változatlan)
        except subprocess.TimeoutExpired:
            self._notify_status(f"Időtúllépés a \"{' '.join(command_args_connect)}\" csatlakozási parancs végrehajtása közben.", is_error=True)
            return False
        except Exception as e:
            self._notify_status(f"Váratlan hiba a \"{' '.join(command_args_connect)}\" csatlakozási parancs kiadása közben: {e}", is_error=True)
            import traceback
            print(traceback.format_exc())
            return False

    def disconnect_vpn(self, disconnection_timeout_s=15):
        # Ez a metódus nagyrészt változatlan maradhat
        if not self.nordvpn_executable_path:
            self._notify_status("NordVPN CLI ('nordvpn.exe') nincs beállítva, bontás nem lehetséges.", is_error=True)
            return False
        command_args = [self.nordvpn_executable_path, "-d"]
        self._notify_status(f"VPN kapcsolat bontási parancs kiadása: \"{' '.join(command_args)}\"...")
        try:
            process_execution_timeout = disconnection_timeout_s + 5
            process = subprocess.run(command_args, capture_output=True, text=True, check=False, timeout=process_execution_timeout)
            self._notify_status(f"'{' '.join(command_args)}' parancs befejeződött. Return code: {process.returncode}")
            if process.stdout and process.stdout.strip(): self._notify_status(f"Kimenet (stdout): {process.stdout.strip()}")
            if process.stderr and process.stderr.strip(): self._notify_status(f"Hibakimenet (stderr): {process.stderr.strip()}", is_error=True)
            if process.returncode == 0:
                self._notify_status(f"A bontási parancs sikeresen elfogadva (return code 0). Feltételezzük a kapcsolat bontását.")
                self.is_connected_to_target_server = False
                return True
            else:
                self._notify_status(f"A bontási parancs hibával tért vissza (kód: {process.returncode}).", is_error=True)
                return False
        except subprocess.TimeoutExpired:
            self._notify_status(f"Időtúllépés a bontási parancs közben.", is_error=True)
            return False
        except Exception as e:
            self._notify_status(f"Hiba a VPN kapcsolat bontása közben: {e}", is_error=True)
            import traceback; print(traceback.format_exc())
            return False

    def minimize_nordvpn_window(self, window_title="NordVPN"):
        pass # Valószínűleg nem releváns
