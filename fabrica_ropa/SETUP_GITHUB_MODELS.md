# 🚀 Guía rápida: GitHub Models

GitHub Models es la **opción recomendada** para correr este proyecto. Free tier generoso y sin tarjeta de crédito.

## 1️⃣ Obtener tu PAT de GitHub

1. Ve a https://github.com/settings/tokens
2. Haz clic en "Generate new token (classic)" → "Tokens (classic)"
3. **Nombre**: `github_models_demo` (o lo que prefieras)
4. **Selecciona scopes**: 
   - ✅ `public_repo` (o dejar sin scopes)
5. Click en "Generate token"
6. **Copia el token** (empieza con `ghp_...`)
   - ⚠️ No lo compartas públicamente

## 2️⃣ Configurar el proyecto

```bash
# En la carpeta fabrica_ropa/
cd fabrica_ropa

# Abre el archivo .env y cambia:
# LLM_PROVIDER=github
# LLM_API_KEY=ghp_xxxxxxxxxxx  ← Tu token aquí
# LLM_MODEL=openai/gpt-4o-mini
# LLM_API_BASE=https://models.github.ai/inference

# Si no existe .env, cópialo desde .env.example:
cp .env.example .env
# Luego edita manualmente
```

## 3️⃣ Instalar dependencias

```bash
python -m venv venv
source venv/bin/activate       # Linux/Mac
# venv\Scripts\Activate.ps1    # Windows PowerShell

pip install -r requirements.txt
```

## 4️⃣ Correr la app

```bash
streamlit run app.py
```

✅ Se abrirá en **http://localhost:8501**

---

## 🤔 Preguntas frecuentes

### ¿Cuál es la cuota de GitHub Models?

No hay cuota diaria publicada. Lo que hay es **rate limit**:
- ~100-150 requests/minuto (aproximado, depende del modelo)
- Muy generoso para demos

### ¿Qué modelos hay disponibles?

```
openai/gpt-4o-mini      ← Recomendado (rápido y bueno)
openai/gpt-4.1
meta/llama-2-7b
mistralai/mistral-7b
Jina-ai/jina-embeddings-v2-base-en
Claude 3 (proximamente)
```

### ¿Cómo cambiar de modelo?

Edita `.env`:
```
LLM_MODEL=meta/llama-2-7b
```

Después reinicia la app.

### ¿Qué pasa si se agota la cuota?

El sistema **detecta automáticamente el error 429** y:
1. Reintentar con backoff (2s → 4s → 8s)
2. Si falla, **fallback a modo mock por 60s**
3. El demo NUNCA se rompe ante el jurado

Para forzar mock (sin API):
```bash
$env:EXECUTION_MODE="mock"; streamlit run app.py
```

### ¿GitHub Models requiere tarjeta de crédito?

**No.** Es 100% gratis con tu cuenta de GitHub.

### ¿Es más rápido que Gemini?

Sí, bastante. Gemini (free) tiene límites muy bajos (15 req/min).

---

## 💡 Tips para la defensa

- **Prueba antes del día:** verifica que funcione 1-2 días antes con tiempo de sobra.
- **Ten un plan B listo:** conoce `EXECUTION_MODE=mock` por si hay problemas de red.
- **Descarga el HTML:** usa el botón en el sidebar para guardar la constancia.
- **Muestra la trazabilidad MCP:** tab "Trazabilidad" es oro puro ante el jurado.

---

Vuelve al [README principal](README.md) para ver las otras opciones de LLM.
