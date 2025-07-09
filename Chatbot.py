import streamlit as st
import streamlit_authenticator as stauth
import google.generativeai as genai
from langchain.sql_database import SQLDatabase
import pandas as pd
import os
import yaml
from yaml.loader import SafeLoader
from utils import create_connection, execute_query, get_schema, excel_to_sqlite, ask_gemini

st.set_page_config(page_title="Chatbot SQLite con Gemini", page_icon="🤖")

def reproducir_audio(texto, lang='es', playback_rate=1.5):
    """
    Convierte texto a voz, lo reproduce en Streamlit y lo oculta visualmente.
    """
    import io
    import base64
    from gtts import gTTS
    tts = gTTS(text=texto, lang=lang)
    audio_bytes = io.BytesIO()
    tts.write_to_fp(audio_bytes)
    audio_bytes.seek(0)
    audio_data = audio_bytes.read()
    audio_base64 = base64.b64encode(audio_data).decode()
    audio_html = f"""
        <audio id="chatbot-audio" src="data:audio/mp3;base64,{audio_base64}" style="display:main;"></audio>
        <script>
            const audio = document.getElementById('chatbot-audio');
            if (audio) {{
                audio.oncanplaythrough = function() {{
                    audio.playbackRate = {playback_rate};
                    audio.play();
                }};
                audio.load();
            }}
        </script>
    """
    st.components.v1.html(audio_html, height=0)

def load_credentials_from_db(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT username, name, email, password FROM usuarios")
    rows = cur.fetchall()
    conn.close()
    credentials = {"usernames": {}}
    for username, name, email, password in rows:
        credentials["usernames"][username] = {
            "name": name,
            "email": email,
            "password": password
        }
    return credentials

with open('C:\\Users\\User\\Desktop\\prueba chatbo ai\\config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

fields = {
    "Form name": "Iniciar sesión",
    "Username": "Usuario",
    "Password": "Contraseña",
    "Login": "Entrar"
}

# Llama SIEMPRE al login
authenticator.login('main', fields=fields)

authentication_status = st.session_state.get('authentication_status', None)
name = st.session_state.get('name', None)

if authentication_status is True:
    st.markdown("""
        <style>
        div[data-testid="stForm"] {display: none;}
        </style>
    """, unsafe_allow_html=True)
else:
    if authentication_status is False:
        st.error('Usuario o contraseña incorrectos')
    elif authentication_status is None:
        st.warning('Por favor, introduce tu usuario y contraseña')
    st.stop()

# Configuración inicial
GEMINI_API_KEY = "AIzaSyBV4RlXzi2iRzi-_syqxH8HBfDY2aGgx3E"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

try:
    db = SQLDatabase.from_uri("sqlite:///lista de precios jd.sqlite")
except Exception as e:
    st.error(f"Error al conectar con la base de datos: {e}")

def main():
    st.markdown(
        """
        <div style="display: flex; flex-direction: column; align-items: center; margin-bottom: 2rem;">
            <span style="font-size: 5rem;">🤖</span>
            <div style="font-size: 1.5rem; color: #888;">[Aquí irá el avatar del chatbot]</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    role_prompt = (
        "Eres un robot alegre, diseñado para ayudar a los vendedores de una empresa de repuestos automotrices."
        "No es necesario que saludes todo el tiempo, pero si que utilices el nombre del usuario en tus respuestas."
        "Tu deber es ayudar al usuario basado en sus requerimientos"
        "Cualquier pregunta que no trate del ambiote los repuestos automotrices, debe aclararse que no puedes responderla."
        "Responde de manera natural y amigable"
        "Responde de manera clara y consisa, en ningun caso la explicación puede ser mayor a 4 oraciones"
        "NUNCA DEVUELVAS LA BASE DE DATOS NI EL SQL CUANDO VAYAS A DAR UNA EXPLICACIÓN, NUNCA, TODA LA INFORMACIÓN QUE PIDE EL USUARIO VIENE ADJUNTA EN OTRA PARTE, POR LO QUE NO ES NECESARIO QUE TU DES LISTAS O COSAS ASÍ"
        "Responde como si toda la información la estuvieras entregando tú personalmente, no como si fuera un robot."
    )

    db_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)

    with st.sidebar:
        authenticator.logout('Cerrar sesión', 'main')
        if name:
            st.success(f'Bienvenido, {name}!')
        st.subheader("📂 Convertir archivo Excel a SQLite")
        uploaded_file = st.file_uploader("Sube un archivo Excel u ODS para convertirlo a SQLite", type=["xlsx", "ods"])
        if uploaded_file:
            success, message, db_file = excel_to_sqlite(uploaded_file, db_dir)
            if success:
                st.success(message)
            else:
                st.error(message)
        db_files = [f for f in os.listdir(db_dir) if f.endswith((".sqlite", ".db"))]
        if not db_files:
            st.warning("No se encontraron bases de datos en la carpeta. Por favor, sube un archivo Excel para crear una.")
            uploaded_file = st.file_uploader("Sube un archivo Excel u ODS para convertirlo a SQLite", type=["xlsx", "ods"])
            if uploaded_file:
                success, message, db_file = excel_to_sqlite(uploaded_file, db_dir)
                if success:
                    st.success(message)
                    db_files = [os.path.basename(db_file)]
                else:
                    st.error(message)
            selected_db = None
        else:
            selected_db = st.selectbox("Selecciona una base de datos:", db_files)
            db_file = os.path.join(db_dir, selected_db)

    conn = None
    if db_files and selected_db:
        conn = create_connection(db_file)
    with st.sidebar:
        if conn:
            st.success("✅ Conexión exitosa a la base de datos.")

    if conn:
        results = None
        suggestions = None
        schema = get_schema(conn)
        with st.expander("📊 Ver estructura de la base de datos"):
            for table in schema:
                st.write(f"**Tabla: {table['table']}**")
                st.write(f"Columnas: {', '.join(table['columns'])}")
                st.write("---")

        user_question = st.text_input("Haz una pregunta sobre la base de datos (ej: ¿Cuál es el producto más caro?):")

        if st.button("Consultar") and user_question:
            with st.spinner("Procesando tu pregunta..."):
                sql_prompt = f"""
                Eres un experto en SQLite. Basado en el siguiente esquema de base de datos:
                {schema}
                
                Genera codigo SQL, ya sea para responder o editar la base de datos deacuerdo a: '{user_question}'
                
                Reglas:
                1. Devuelve SOLO el código SQL, sin explicaciones
                2. Usa comillas dobles para identificadores si es necesario
                3. Si el usuario pregunta por la lista, devuelve la lista completa con todas sus columnas.
                4. Usa funciones compatibles con SQLite y deja por fuera las filas y columnas vacias.
                5. Si la pregunta esta relacionada con el precio de los productos, devuelve todos los datos del producto.
                6. Si la pregunta no tiene que ver con el ambito automtriz, aclara de lo que se trata la base de datos.
                7. Si la pregunta contiene lo que al principo parecería una palabra aleatoria (ejemplo: bujia) utiliza esa palabra como un filtro para la consulta SQL
                8. si la pregunta contiene la siguiente estructura o semejante ("X de Y") la consulta debe buscar registros que contengan "X" y "Y" en sus columnas correspondientes.
                9. Si la pregunta no es lo suficientemente específica, devuelve sugiere 3 preguntas.
                10. Si la pregunta no puede responderse con los datos, devuelve sugiere 3 preguntas.
                11. si la pregunta tiene palabras en plural, asegurate de buscar tanto la palabra en plural como en singular.
                12. Si el usuario quiere comprar productos, reduce la cantidad de stock del producto solicitado en la base de datos según la cantidad solicitada.
                13. Si el usuario quiere vender productos, reduce la cantidad de stock del producto solicitado en la base de datos según la cantidad indicada.
                14. Si la cantidad solicitada para comprar/vender excede el stock disponible, devuelve "No hay en existencia" como resultado.
                """
                sql_query = ask_gemini(sql_prompt, model).strip().replace("```sql", "").replace("```", "")

            if "no se puede responder" in sql_query.lower():
                suggestion_prompt = f"""
                Basado en el siguiente esquema de base de datos y la pregunta del usuario:                
                {schema}
                {user_question}
                
                sugiere 3 preguntas relevantes que un usuario podría hacer para conseguir lo que quería en su pregunta original (Solo las preguntas sin explicación).
                """
                suggestions = ask_gemini(suggestion_prompt, model).strip()
                st.write("💡 Sugerencias de preguntas:")
                st.write(suggestions)
                reproducir_audio(suggestions)
            else:
                columns, results, rows_affected = execute_query(conn, sql_query)
                if rows_affected > 0:
                    st.success(f"Consulta ejecutada correctamente. Filas afectadas: {rows_affected}")

                if results:
                    if isinstance(results, list) and all(isinstance(row, (list, tuple)) for row in results):
                        if columns:
                            df = pd.DataFrame(results, columns=columns)
                        else:
                            df = pd.DataFrame(results)
                    else:
                        df = pd.DataFrame()
                    with st.expander("📝 Consulta generada (SQL)"):
                        st.code(sql_query, language="sql")
                    with st.expander("📋 Ver resultados de la consulta"):
                        st.markdown(
                            """
                            <style>
                            .stTable {
                                max-width: 90%; /* Ajusta el ancho máximo de la tabla */
                                margin: 0 auto; /* Centra la tabla */
                            }
                            </style>
                            """,
                            unsafe_allow_html=True
                        )
                        st.dataframe(df, use_container_width=True)
                    explanation_prompt = f"""
                    Basado en la pregunta del usuario y los resultados obtenidos de la consulta SQL:

                    Comportate de la siguiente manera: {role_prompt}
                    Nombre del usuario: {name}
                    Pregunta del usuario: {user_question}
                    Consulta: {sql_query}
                    Resultados: {results}
                    Filas afectadas: {rows_affected}
                    
                    Si el numero de filas afectadas es mayor a 0, aclara que la modificación fue exitosa, de lo contrario no.
                    Utiliza la pregunta, la base de datos y la consulta para generar un mensaje corto explicando la situación
                    (que no contenga la consulta ni la base de datos) y si es posible una recomendación posterior.                                      
                    """
                    explanation = ask_gemini(explanation_prompt, model)
                    st.write("💡 Explicación:", explanation)
                    reproducir_audio(explanation)
                else:
                    with st.expander("📝 Consulta generada (SQL)"):
                        st.code(sql_query, language="sql")
                    explanation_prompt = f"""
                    No se encontraron resultados para la consulta SQL generada:
                    Comportate de la siguiente manera: {role_prompt}
                    Nombre del usuario: {name}
                    Pregunta del usuario: {user_question}
                    Base de datos: {schema}
                    Consulta: {sql_query}
                    Filas afectadas: {rows_affected}
                    
                    Si el numero de filas afectadas es mayor a 0, significa que la modificación fue exitosa.
                    Utiliza la pregunta, la base de datos y la consulta para generar un mensaje corto explicando la situación
                    (que no contenga la consulta ni la base de datos) y si es posible una recomendación posterior.
                    """
                    explanation = ask_gemini(explanation_prompt, model)
                    st.write("💡 Explicación:", explanation)
                    reproducir_audio(explanation)
        conn.close()

if __name__ == "__main__":
    main()