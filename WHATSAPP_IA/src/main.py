import pandas as pd
import os
import time
import random
from ia_handler import IAHandler
from whatsapp_bot import WhatsAppBot

# Configuración de rutas
# --- CONFIGURACIÓN DE RUTAS AUTOMÁTICA ---
# Esto detecta la carpeta raíz del proyecto (WHATSAPP_IA)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Rutas absolutas para que no fallen nunca
PATH_CSV = os.path.join(BASE_DIR, "data", "CALI - RESTAURANTEHELADERIA.csv")
PATH_PLANTILLA = os.path.join(BASE_DIR, "config", "plantilla.txt")
PATH_LOG = os.path.join(BASE_DIR, "data", "enviados_log.csv")

# Verifica si el CSV existe antes de empezar
if not os.path.exists(PATH_CSV):
    print(f"❌ ERROR: No encontré el archivo en: {PATH_CSV}")
    print("Revisa si el nombre tiene espacios o si está en la carpeta data.")
    exit()

def cargar_plantilla():
    with open(PATH_PLANTILLA, 'r', encoding='utf-8') as f:
        return f.read()

def main():
    ia = IAHandler(model_name="gemma:7b")
    bot = WhatsAppBot()
    plantilla = cargar_plantilla()
    
    # Cargar datos
    df = pd.read_csv(PATH_CSV)
    
    # Cargar o crear log de enviados (para no repetir si el script se detiene)
    if os.path.exists(PATH_LOG):
        enviados = pd.read_csv(PATH_LOG)['phone'].tolist()
    else:
        enviados = []

    print(f"🚀 Iniciando campaña para {len(df)} contactos...")

    for index, row in df.iterrows():
        telefono = str(row['phone']).strip().replace(" ", "")
        if not telefono.startswith('+'): telefono = f"+{telefono}"
        
        # Saltar si ya se envió
        if telefono in enviados:
            continue

        # 1. IA procesa el nombre
        nombre_limpio = ia.limpiar_nombre(row['name'])
        
        # 2. Preparar mensaje
        mensaje_final = plantilla.format(nombre=nombre_limpio)
        
        print(f"Enviando a {nombre_limpio} ({telefono})...")
        
        # 3. Intentar envío
        exito = bot.enviar_mensaje(telefono, mensaje_final)
        
        if exito:
            # Registrar en el log
            log_entry = pd.DataFrame([[row['name'], telefono]], columns=['name', 'phone'])
            log_entry.to_csv(PATH_LOG, mode='a', header=not os.path.exists(PATH_LOG), index=False)
            
            # ESPERA ALEATORIA ANTI-BANEO (Crucial)
            # Entre 40 y 90 segundos para simular comportamiento humano
            espera = random.randint(40, 90)
            print(f"✅ Éxito. Esperando {espera}s para el siguiente...")
            time.sleep(espera)
        else:
            print(f"❌ Falló el envío a {telefono}")

if __name__ == "__main__":
    main()