import pywhatkit as kit
import pyautogui # Librería para controlar el teclado
import time

class WhatsAppBot:
    def enviar_mensaje(self, telefono, mensaje):
        """Envía el mensaje y cierra la pestaña para evitar conflictos."""
        try:
            # 1. Abre y envía (wait_time es para que cargue la página)
            # tab_close=True cerrará la pestaña automáticamente tras enviar
            kit.sendwhatmsg_instantly(
                phone_no=telefono, 
                message=mensaje, 
                wait_time=20, # Aumentamos a 20 por seguridad en Mac
                tab_close=True, 
                close_time=3  # Segundos que espera antes de cerrar la pestaña
            )
            
            # 2. Forzar un 'Enter' extra (A veces pywhatkit solo pega el texto)
            # Esto ayuda si el mensaje se queda pegado pero no se envía
            pyautogui.press('enter')
            
            return True
        except Exception as e:
            print(f"Error técnico en el envío: {e}")
            return False