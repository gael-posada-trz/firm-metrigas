import os
import json
import boot

TAG = "[CONFIG]"

def save_config_atomic(ssid=None, password=None, device_name=None, is_premium=None):
    """
    Writes parameters atomically to Flash memory to mitigate damage from brownouts.
    Creates a temporary file, and only if successfully written, replaces the master file.
    """
    tmp_file = boot.CONFIG_FILE + ".tmp"
    try:
        # Resolve values: If a parameter is not provided (None), pull it from boot's RAM state
        f_ssid = ssid if ssid is not None else boot.current_credentials["ssid"]
        f_password = password if password is not None else boot.current_credentials["password"]
        f_device_name = device_name if device_name is not None else boot.device_name
        f_is_premium = is_premium if is_premium is not None else boot.is_premium
        
        # 2. Build the new configuration payload using incoming parameters or keeping old values
        payload = {
            "ssid": f_ssid,
            "password": f_password,
            "device_name": f_device_name, 
            "is_premium": f_is_premium,
        }
        
        # 3. Write data to the isolated temporary file buffer
        with open(tmp_file, "w") as f:
            json.dump(payload, f)
            
        # 4. If disk write succeeded, replace the original file securely
        if boot.CONFIG_FILE in os.listdir():
            os.remove(boot.CONFIG_FILE)
        os.rename(tmp_file, boot.CONFIG_FILE)
        
        # 5. Hot-update system runtime context (RAM variables) synchronized from boot.py
        boot.current_credentials["ssid"] = f_ssid
        boot.current_credentials["password"] = f_password
        boot.device_name = f_device_name
        boot.is_premium = f_is_premium
        
        print(f"{TAG} System configuration profile atomically saved and RAM variables updated.")
        return True
        
    except Exception as e:
        print(f"{TAG} CRITICAL ERROR: Atomic write sequence failed. Reverting to previous profile:", e)
        # Attempt minimal cleanup to free storage if temporary file stayed open
        try:
            if tmp_file in os.listdir():
                os.remove(tmp_file)
        except Exception as e:
            print(f"{TAG} ERROR: Failed to cleanup temporary file:", e)
        return False

def force_factory_reset():
    """
    Wipes the system configuration profile from local flash storage.
    """
    try:
        if boot.CONFIG_FILE in os.listdir():
            os.remove(boot.CONFIG_FILE)
            print(f"{TAG} Factory reset successful: master profile config.json removed from storage.")
            return True
        print(f"{TAG} Factory reset skipped: master profile config.json non-existent.")
        return True
    except Exception as e:
        print(f"{TAG} ERROR: Failed to execute hardware disk wipe sequence:", e)
        return False