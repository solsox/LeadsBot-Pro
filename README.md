# LeadAgent PRO

Sistema automatizado de adquisición de clientes para agencias de desarrollo web.
Scraping de Google Maps → Scoring → Mensajes con IA → Envío por email/WhatsApp.

## Requisitos

- Python 3.10+
- Node.js 18+
- Ollama (para IA local)

## Instalación

### 1. Clonar el repo

```bash
git clone https://github.com/tu-usuario/leadagent-pro.git
cd leadagent-pro
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales.

### 3. Instalar dependencias Python

**Mac:**
```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

**Windows:**
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 4. Instalar dependencias frontend

```bash
cd frontend
npm install
cd ..
```

### 5. Instalar Ollama (IA local)

**Mac:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull phi3
```

**Windows:**
Descargar desde https://ollama.com/download e instalar.
Luego en terminal:
```bash
ollama pull phi3
```

### 6. Arrancar

Necesitas 3 terminales abiertas:

**Terminal 1 — Backend:**
```bash
cd backend
python3 main.py        # Mac
python main.py         # Windows
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

**Terminal 3 — Ollama:**
```bash
ollama serve
```

Abrir http://localhost:3000

## Configurar búsquedas

En el dashboard → pestaña Ejecución → editar zonas y temas → Guardar configuración.

## Exportar leads

Dashboard → pestaña Métricas → Exportar leads como CSV.