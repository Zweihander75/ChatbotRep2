def create_connection(db_file):
    import sqlite3
    from sqlite3 import Error
    import streamlit as st
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
    return conn

def execute_query(conn, query):
    from sqlite3 import Error
    import streamlit as st
    try:
        cur = conn.cursor()
        statements = query.split(";")
        rows_affected = 0
        results = None
        columns = None

        for statement in statements:
            if statement.strip():
                cur.execute(statement)
                if statement.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    rows_affected += cur.rowcount
                if statement.strip().upper().startswith("SELECT"):
                    results = cur.fetchall()
                    columns = [desc[0] for desc in cur.description] if cur.description else []

        if rows_affected > 0:
            conn.commit()

        return columns, results, rows_affected
    except Error as e:
        st.error(f"Error al ejecutar la consulta: {e}")
        return None, None, 0
    
def get_schema(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    schema = []
    for table in tables:
        table_name = table[0]        
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        columns = cursor.fetchall()
        schema.append({
            "table": table_name,
            "columns": [col[1] for col in columns]
        })
    return schema

def excel_to_sqlite(uploaded_file, db_path, nombre_tabla, encabezados_esperados=None):
    import pandas as pd
    import sqlite3

    # Lista de encabezados sugeridos (puedes agregar más)
    if encabezados_esperados is None:
        encabezados_esperados = ["Producto", "Precio", "Código", "Descripción", "COD", "DESCRIPCION", "MARCA"]

    # Lee el archivo sin encabezados para analizar las filas
    df_raw = pd.read_excel(uploaded_file, header=None)
    header_row = None

    # Busca la primera fila que tenga al menos una coincidencia parcial con los encabezados esperados
    for i, row in df_raw.iterrows():
        row_str = [str(cell).strip().lower() for cell in row]
        coincidencias = [enc for enc in encabezados_esperados if any(enc.lower() in cell for cell in row_str)]
        if len(coincidencias) > 0:
            header_row = i
            break

    if header_row is None:
        return False, "No se encontraron encabezados válidos en el archivo.", db_path

    # Aplica el prefijo "lista_" al nombre de la tabla
    nombre_tabla_prefijo = f"lista_{nombre_tabla}"

    # Lee el archivo usando la fila detectada como encabezado
    df = pd.read_excel(uploaded_file, header=header_row)
    conn = sqlite3.connect(db_path)
    df.to_sql(nombre_tabla_prefijo, conn, if_exists="replace", index=False)
    conn.close()
    return True, f"Tabla '{nombre_tabla_prefijo}' agregada a la base de datos principal.", db_path

def ask_gemini(prompt, model):
    import streamlit as st
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error al interactuar con Gemini AI: {e}")
        return "Lo siento, no puedo responder en este momento."
    
import sqlite3

def guardar_interaccion(db_path, usuario, pregunta, respuesta):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO historial_chat (usuario, pregunta, respuesta) VALUES (?, ?, ?)",
        (usuario, pregunta, respuesta)
    )
    conn.commit()
    conn.close()

def obtener_tablas_listas_precios(conn, prefijo="lista_"):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (f"{prefijo}%",))
    tablas = [row[0] for row in cursor.fetchall()]
    return tablas

def load_credentials_from_db(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT NombreUsuario, Nombre, Contraseña, Rol FROM usuarios")
    rows = cur.fetchall()
    conn.close()
    credentials = {"usernames": {}}
    for username, name, password, rol in rows:
        credentials["usernames"][username] = {
            "name": name,           
            "password": password,
            "rol": rol
        }
    return credentials