from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from supabase import create_client
from google import genai
from google.genai import types
from pydantic import BaseModel

app = Flask(__name__)

supabase = create_client(os.environ["SUPABASE_URL"].strip(), os.environ["SUPABASE_KEY"].strip())
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())

class Transaccion(BaseModel):
    tipo: str
    monto: float
    moneda: str
    categoria: str
    descripcion: str

def procesar_mensaje(mensaje: str):
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

def obtener_o_crear_jugador(telefono: str):
    resultado = supabase.table("perfil_jugador").select("*").eq("telefono", telefono).execute().data
    if resultado:
        return resultado[0]
    nuevo = supabase.table("perfil_jugador").insert({
        "nombre": telefono,
        "telefono": telefono,
        "nivel": 1,
        "xp_actual": 0,
        "xp_para_siguiente_nivel": 100
    }).execute().data[0]
    return nuevo

def otorgar_xp(jugador_id: int, xp: int = 50):
    jugador = supabase.table("perfil_jugador").select("*").eq("id", jugador_id).execute().data[0]
    nuevo_xp = jugador["xp_actual"] + xp
    nuevo_nivel = jugador["nivel"]
    level_up = False
    if nuevo_xp >= jugador["xp_para_siguiente_nivel"]:
        nuevo_xp -= jugador["xp_para_siguiente_nivel"]
        nuevo_nivel += 1
        level_up = True
    supabase.table("perfil_jugador").update({
        "xp_actual": nuevo_xp,
        "nivel": nuevo_nivel
    }).eq("id", jugador_id).execute()
    return nuevo_xp, nuevo_nivel, level_up

def obtener_resumen(jugador_id: int):
    jugador = supabase.table("perfil_jugador").select("*").eq("id", jugador_id).execute().data[0]
    movimientos = supabase.table("movimientos").select("*").eq("jugador_id", jugador_id).order("created_at", desc=True).limit(5).execute().data
    resumen = f"""⚔️ ESTADO DEL AVENTURERO ⚔️
🧙 {jugador['nombre']} | Nivel {jugador['nivel']}
✨ XP: {jugador['xp_actual']} / {jugador['xp_para_siguiente_nivel']}

📜 Últimos movimientos:"""
    for m in movimientos:
        emoji = "💰" if m['tipo'] == "ingreso" else "💸"
        resumen += f"\n{emoji} {m['tipo'].upper()} | {m['monto']} {m['moneda']} | {m['categoria']}"
    return resumen

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje = request.form.get("Body", "").strip()
    telefono = request.form.get("From", "").replace("whatsapp:", "")
    resp = MessagingResponse()
    try:
        jugador = obtener_o_crear_jugador(telefono)
        jugador_id = jugador["id"]
        if mensaje.lower() in ["mi estado", "estado", "resumen"]:
            resp.message(obtener_resumen(jugador_id))
            return str(resp)
        transaccion = procesar_mensaje(mensaje)
        supabase.table("movimientos").insert({
            "jugador_id": jugador_id,
            "tipo": transaccion.tipo,
            "monto": transaccion.monto,
            "moneda": transaccion.moneda,
            "categoria": transaccion.categoria,
            "descripcion": transaccion.descripcion,
            "xp_otorgado": 50
        }).execute()
        xp_actual, nivel, level_up = otorgar_xp(jugador_id)
        respuesta = f"""⚔️ ¡Registro guardado, Aventurero!

{'💰 INGRESO' if transaccion.tipo == 'ingreso' else '💸 GASTO'} | {transaccion.monto} {transaccion.moneda}
📂 Categoría: {transaccion.categoria}
⭐ +50 XP | Total: {xp_actual} / 100"""
        if level_up:
            respuesta += f"\n\n🎮 ¡LEVEL UP! ¡Ahora eres Nivel {nivel}!"
        resp.message(respuesta)
    except Exception as e:
        resp.message("⚔️ El Master no pudo entender ese mensaje. ¿Podés describir mejor tu gasto o ingreso?")
        import traceback
print(f"Error: {e}")
print(traceback.format_exc())
    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
