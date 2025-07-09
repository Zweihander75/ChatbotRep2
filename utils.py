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
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        schema.append({
            "table": table_name,
            "columns": [col[1] for col in columns]
        })
    return schema

def excel_to_sqlite(uploaded_file, output_dir):
    import os
    import pandas as pd
    import sqlite3
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        filename = os.path.splitext(uploaded_file.name)[0]
        db_file = os.path.join(output_dir, f"{filename}.sqlite")
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext == ".xlsx":
            df = pd.read_excel(uploaded_file)
        elif ext == ".ods":
            df = pd.read_excel(uploaded_file, engine="odf")
        else:
            return False, "Formato de archivo no soportado. Solo se permiten .xlsx y .ods.", None
        for col in df.select_dtypes(include=["datetime", "datetimetz"]):
            df[col] = df[col].astype(str)
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x) if "Timestamp" in str(type(x)) else x)
        conn = sqlite3.connect(db_file)
        df.to_sql("imported_data", conn, if_exists="replace", index=False)
        conn.close()
        return True, "Archivo convertido y guardado en la base de datos SQLite exitosamente.", db_file
    except Exception as e:
        return False, f"Error al convertir el archivo: {e}", None
    
def ask_gemini(prompt, model):
    import streamlit as st
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error al interactuar con Gemini AI: {e}")
        return "Lo siento, no puedo responder en este momento."