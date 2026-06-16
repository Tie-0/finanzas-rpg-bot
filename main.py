import os
from supabase import create_client
from google import genai
from google.genai import types
from pydantic import BaseModel

# Conexiones
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Esquema Pydantic para Gemini
class Transaccion(BaseModel):
    tipo: str        # "ingreso" o "gasto"
    monto: float
    moneda: str      # "ARS" o "USD"
    categoria: str   # "Comida", "Transporte", "Servicios", "Inversiones", "Ocio"
    descripcion: str

def procesar_mensaje(mensaje: str):
    """Usa Gemini para extraer datos del mensaje en lenguaje natural."""
    resultado = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=mensaje,
        config=types.GenerateContentConfig(
            system_instruction="""Eres un asistente de finanzas personales. 
            Extrae los datos financieros del mensaje del usuario.
            La moneda por defecto es ARS si no se especifica.
            Categorías válidas: Comida, Transporte, Servicios, Inversiones, Ocio.""",
            response_mime_type="application/json",
            response_schema=Transaccion,
        ),
    )
    return Transaccion.model_validate_json(resultado.text)

def guardar_movimiento(jugador_id: int, transaccion: Transaccion, xp: int = 50):
    """Guarda el movimiento en Supabase."""
    supabase.table("movimientos").insert({
        "jugador_id": jugador_id,
        "tipo": transaccion.tipo,
        "monto": transaccion.monto,
        "moneda": transaccion.moneda,
        "categoria": transaccion.categoria,
        "descripcion": transaccion.descripcion,
        "xp_otorgado": xp
    }).execute()

def otorgar_xp(jugador_id: int, xp: int = 50):
    """Suma XP al jugador y sube de nivel si corresponde."""
    jugador = supabase.table("perfil_jugador").select("*").eq("id", jugador_id).execute().data[0]
    nuevo_xp = jugador["xp_actual"] + xp
    nuevo_nivel = jugador["nivel"]

    if nuevo_xp >= jugador["xp_para_siguiente_nivel"]:
        nuevo_xp -= jugador["xp_para_siguiente_nivel"]
        nuevo_nivel += 1
        print(f"⚔️ ¡LEVEL UP! Ahora eres nivel {nuevo_nivel}")

    supabase.table("perfil_jugador").update({
        "xp_actual": nuevo_xp,
        "nivel": nuevo_nivel
    }).eq("id", jugador_id).execute()

    return nuevo_xp, nuevo_nivel

# --- SIMULACIÓN DE MENSAJE ---
JUGADOR_ID = 1
mensaje_prueba = "Gané 30 dólares con la inversión semanal"

print(f"📨 Mensaje recibido: '{mensaje_prueba}'")
transaccion = procesar_mensaje(mensaje_prueba)
print(f"🧠 Gemini extrajo: {transaccion}")

guardar_movimiento(JUGADOR_ID, transaccion)
print("💾 Movimiento guardado en Supabase")

xp_actual, nivel = otorgar_xp(JUGADOR_ID)
print(f"⭐ +50 XP otorgados | XP actual: {xp_actual} | Nivel: {nivel}")

def obtener_resumen(jugador_id: int):
    """Genera un resumen RPG del estado actual del jugador."""
    jugador = supabase.table("perfil_jugador").select("*").eq("id", jugador_id).execute().data[0]
    movimientos = supabase.table("movimientos").select("*").eq("jugador_id", jugador_id).order("created_at", desc=True).limit(5).execute().data

    resumen = f"""
⚔️ === ESTADO DEL AVENTURERO === ⚔️
🧙 Nombre: {jugador['nombre']}
⭐ Nivel: {jugador['nivel']}
✨ XP: {jugador['xp_actual']} / {jugador['xp_para_siguiente_nivel']}

📜 Últimos movimientos:"""

    for m in movimientos:
        emoji = "💰" if m['tipo'] == "ingreso" else "💸"
        resumen += f"\n  {emoji} {m['tipo'].upper()} | {m['monto']} {m['moneda']} | {m['categoria']}"

    return resumen

# --- SIMULACIÓN RESUMEN ---
print("\n" + obtener_resumen(JUGADOR_ID))

def verificar_misiones(jugador_id: int, transaccion):
    """Verifica si alguna misión se completó con este movimiento."""
    misiones = supabase.table("misiones").select("*").eq("jugador_id", jugador_id).eq("activa", True).eq("completada", False).execute().data

    for mision in misiones:
        if mision["categoria"] != transaccion.categoria:
            continue
        if transaccion.moneda != mision["moneda"]:
            continue

        # Sumar gastos de esa categoría esta semana
        gastos = supabase.table("movimientos").select("monto").eq("jugador_id", jugador_id).eq("categoria", transaccion.categoria).eq("tipo", "gasto").execute().data
        total = sum(g["monto"] for g in gastos)

        if total <= mision["limite_monto"]:
            # Misión cumplida
            supabase.table("misiones").update({"completada": True, "activa": False}).eq("id", mision["id"]).execute()
            otorgar_xp(jugador_id, mision["xp_bonus"])
            print(f"🏆 ¡MISIÓN COMPLETADA! '{mision['nombre']}' | +{mision['xp_bonus']} XP bonus")

# --- SIMULACIÓN MISIÓN ---
mensaje_gasto = "Gasté 3000 pesos en el cine"
print(f"\n📨 Mensaje recibido: '{mensaje_gasto}'")
transaccion2 = procesar_mensaje(mensaje_gasto)
print(f"🧠 Gemini extrajo: {transaccion2}")
guardar_movimiento(JUGADOR_ID, transaccion2)
verificar_misiones(JUGADOR_ID, transaccion2)
print("\n" + obtener_resumen(JUGADOR_ID))
