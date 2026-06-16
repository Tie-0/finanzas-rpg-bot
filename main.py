import os
from supabase import create_client

# Conexión a Supabase
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test de conexión
resultado = supabase.table("perfil_jugador").select("*").execute()
print("✅ Conexión exitosa!")
print(f"Jugador encontrado: {resultado.data}")
