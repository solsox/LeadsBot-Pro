import requests

class IAHandler:
    def __init__(self, model_name="gemma"):
        self.url = "http://localhost:11434/api/generate"
        self.model = model_name

    def limpiar_nombre(self, nombre_sucio):
        """Usa Gemma para extraer solo el nombre comercial."""
        prompt = (f"Instrucción: Extrae solo el nombre principal del negocio, "
                  f"sin direcciones, nit o ciudades. Texto: {nombre_sucio}. "
                  f"Respuesta corta:")
        
        try:
            response = requests.post(self.url, 
                                     json={"model": self.model, "prompt": prompt, "stream": False},
                                     timeout=10)
            return response.json()['response'].strip()
        except Exception:
            return nombre_sucio # Si falla, devuelve el original