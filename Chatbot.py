import streamlit as st
import streamlit_authenticator as stauth
import google.generativeai as genai
import pandas as pd
import os
from utils import create_connection, execute_query, get_schema, excel_to_sqlite, ask_gemini, obtener_tablas_listas_precios, guardar_interaccion, load_credentials_from_db
import base64
import datetime

st.set_page_config(page_title="Chatbot SQLite con Gemini", page_icon="🤖")

#################### Texto a voz #############################

def reproducir_audio(texto, lang='es', playback_rate=1.5):    
    
    import io
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

#################### Conección a base de datos #############################

db_dir = os.path.dirname(os.path.abspath(__file__))
db_file = os.path.join(db_dir, "Main.sqlite")  # Base de datos principal

#################### Carga de credenciales/Login #############################

credentials = load_credentials_from_db(db_file)

authenticator = stauth.Authenticate(
    credentials,
    "cookie_name",  
    "cookie_key",   
    1               
)

fields = {
    "Form name": "Iniciar sesión",
    "Username": "Usuario",
    "Password": "Contraseña",
    "Login": "Entrar"
}

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
# Usar el modelo seleccionado en el sidebar
model = genai.GenerativeModel(st.session_state.get("modelo_gemini", "gemini-2.0-flash"))

# Función para el panel de administración
def admin_panel(conn, db_file):
    st.subheader("👑 Panel de Administración")

    # 1. Consultar historial de interacciones (expandible)
    with st.expander("📜 Ver historial de interacciones"):
        df_hist = pd.read_sql_query("SELECT * FROM historial_chat ORDER BY id DESC", conn)
        st.dataframe(df_hist, use_container_width=True)

    # 2. Borrar listas de precios
    st.markdown("### Borrar Listas de Precios")
    tablas_listas = obtener_tablas_listas_precios(conn, prefijo="lista_")
    tabla_borrar = st.selectbox("Selecciona una lista para borrar:", tablas_listas, key="borrar_lista")
    if st.button("Borrar lista seleccionada"):
        if tabla_borrar:
            conn.execute(f"DROP TABLE IF EXISTS '{tabla_borrar}'")
            conn.commit()
            st.success(f"Tabla '{tabla_borrar}' eliminada.")
            st.rerun()

    # 3. Descargar respaldo de la base de datos
    st.markdown("### Descargar respaldo de la base de datos")
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"main_{now}.sqlite"
    with open(db_file, "rb") as f:
        st.download_button(
            label="Descargar respaldo",
            data=f,
            file_name=backup_filename,
            mime="application/octet-stream"
        )

def main():
    db_dir = os.path.dirname(os.path.abspath(__file__))
    db_file = os.path.join(db_dir, "Main.sqlite")  # Base de datos principal

    # Imagen del chatbot
    img_path = os.path.join(db_dir, "bot-conversacional-abierta.png")
    if os.path.exists(img_path):
        with open(img_path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode()
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; margin-bottom: 2rem;">
                <img src="data:image/png;base64,{img_base64}" alt="Chatbot" width="120" style="display: block;"/>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.warning("No se encontró la imagen 'bot-conversacional-abierta.png'.")

    role_prompt = (
        "Eres un robot alegre, diseñado para ayudar a los vendedores de una empresa de repuestos automotrices."
        "No es necesario que saludes todo el tiempo, pero si que utilices el nombre del usuario en tus respuestas."
        "Tu deber es ayudar al usuario basado en sus requerimientos"
        "Cualquier pregunta que no trate del ambiote los repuestos automotrices, debe aclararse que no puedes responderla."
        "Responde de manera natural y amigable"
        "Responde de manera clara y consisa, en ningun caso la explicación puede ser mayor a 4 oraciones"
        "NUNCA DEVUELVAS LA BASE DE DATOS NI EL SQL CUANDO VAYAS A DAR UNA EXPLICACIÓN, NUNCA, TODA LA INFORMACIÓN QUE PIDE EL USUARIO VIENE ADJUNTA EN OTRA PARTE, POR LO QUE NO ES NECESARIO QUE TU DES LISTAS O COSAS ASÍ"
        "Responde como si toda la información la estuvieras entregando tú personalmente, no como si fuera un robot."
        "Ninguna respuesta puede ser mayor a 6 oraciones."
    )

    db_dir = os.path.dirname(os.path.abspath(__file__))
    db_file = os.path.join(db_dir, "Main.sqlite")  # Nombre de la base de datos principal

    if not os.path.exists(db_dir):
        os.makedirs(db_dir)

    with st.sidebar:
        authenticator.logout('Cerrar sesión', 'main')
        if name:
            st.success(f'Bienvenido, {name}!')
        # Selector de modelo de IA
        modelo_gemini = st.selectbox(
            "Modelo de IA",
            ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
            index=0,
            key="modelo_gemini"
        )
        # Switch para modo debug
        debug_mode = st.toggle("Modo Debug", value=False, key="debug_mode")

        st.subheader("📂 Convertir archivo Excel a SQLite")

        # CSS para traducir los textos del widget de subida de archivos
        custom_css = """
        <style>
        /* Botón del uploader: texto original transparente, texto nuevo encima */
        section[data-testid="stFileUploaderDropzone"] > button[data-testid="stBaseButton-secondary"] {
            color: transparent !important;
            position: relative;
        }
        section[data-testid="stFileUploaderDropzone"] > button[data-testid="stBaseButton-secondary"]::after {
            content: "Buscar archivo";
            color: white;
            position: absolute;
            left: 0; right: 0; top: 0; bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: none;
        }
        /* Instrucción principal: texto original transparente, texto nuevo encima */
        div[data-testid="stFileUploaderDropzoneInstructions"] span.st-emotion-cache-9ycgxx {
            color: transparent !important;
            position: relative;
        }
        div[data-testid="stFileUploaderDropzoneInstructions"] > div > span::after {
            content: "Subir archivo";
            color: white;
            position: absolute;
            left: 0; right: 0; top: 0; bottom: 0;
            
            align-items: left;
            justify-content: left;
            pointer-events: none;
        }
        /* Texto del límite de archivo: original transparente, nuevo encima */
        div[data-testid="stFileUploaderDropzoneInstructions"] small {
            color: transparent !important;
            position: relative;
        }
        div[data-testid="stFileUploaderDropzoneInstructions"] small::before {
            content: "Límite de 200MB";
            color: white;
            position: absolute;
            left: 0; right: 0; top: 0; bottom: 0;
            
            align-items: left;
            justify-content: left;
            pointer-events: none;
        }
        </style>
        """

        st.markdown(custom_css, unsafe_allow_html=True)

        uploaded_file = st.file_uploader(
            label="Selecciona el archivo Excel o ODS",
            type=["xlsx", "ods"]
        )
        
        if uploaded_file:
            # Obtener el nombre del archivo sin extensión y reemplazar espacios por "_"
            nombre_tabla = os.path.splitext(uploaded_file.name)[0].replace(" ", "_")
            success, message, _ = excel_to_sqlite(uploaded_file, db_file, nombre_tabla)
            if success:
                st.success(message)
            else:
                st.error(message)

        # Mostrar las tablas de listas de precios disponibles
        conn = create_connection(db_file)
        tablas_listas = obtener_tablas_listas_precios(conn, prefijo="lista_")
        # Si el usuario es admin, agrega historial_chat como opción
        username = st.session_state.get('username', None)
        user_role = None
        for uname, udata in credentials["usernames"].items():
            if udata["name"] == name:
                user_role = udata.get("rol", "usuario")
                break
        if user_role == "administrador":
            tablas_listas = ["historial_chat"] + tablas_listas

        if not tablas_listas:
            st.warning("No hay listas de precios cargadas en la base de datos.")
            tabla_seleccionada = None
        else:
            tabla_seleccionada = st.selectbox("Selecciona una lista de precios:", tablas_listas)

            # --- Botón para descargar la lista seleccionada como Excel ---
            if tabla_seleccionada:
                import io
                import pandas as pd

                df_lista = pd.read_sql_query(f'SELECT * FROM "{tabla_seleccionada}"', conn)
                output = io.BytesIO()
                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                excel_filename = f"{tabla_seleccionada}_{now}.xlsx"

                # Escribir el DataFrame con formato usando xlsxwriter
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_lista.to_excel(writer, index=False, sheet_name='Lista')
                    workbook  = writer.book
                    worksheet = writer.sheets['Lista']

                    # Formato para encabezados
                    header_format = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1})
                    for col_num, value in enumerate(df_lista.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        # Ajustar ancho de columna según el contenido
                        max_len = max(df_lista[value].astype(str).map(len).max(), len(str(value))) + 2
                        worksheet.set_column(col_num, col_num, max_len)

                    # Agregar autofiltro
                    worksheet.autofilter(0, 0, len(df_lista), len(df_lista.columns) - 1)

                st.download_button(
                    label="Descargar lista en Excel",
                    data=output.getvalue(),
                    file_name=excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    if conn and tabla_seleccionada:
        results = None
        suggestions = None
        schema = get_schema(conn)
        # Filtrar solo la tabla seleccionada
        tabla_actual = next((t for t in schema if t['table'] == tabla_seleccionada), None)

        # Mostrar estructura de la tabla solo si debug_mode está activado
        if 'debug_mode' in st.session_state and st.session_state['debug_mode']:
            show_structure = True
        else:
            show_structure = False

        if show_structure:
            with st.expander("📊 Ver estructura de la tabla seleccionada"):
                if tabla_actual:
                    st.write(f"**Tabla: {tabla_actual['table']}**")
                    st.write(f"Columnas: {', '.join(tabla_actual['columns'])}")
                else:
                    st.info("No se encontró la estructura de la tabla seleccionada.")

        user_question = st.text_input("Haz una pregunta sobre la lista de precios seleccionada (ej: ¿Cuál es el producto más caro?):")

        if st.button("Consultar") and user_question:
            with st.spinner("Procesando tu pregunta..."):
                # Prompt especial si la tabla es historial_chat
                if tabla_seleccionada == "historial_chat":
                    sql_prompt = f"""
                    Eres un experto en análisis de conversaciones y registros de chat. Basado en el siguiente esquema de base de datos:
                    {schema}

                    Genera código SQL para responder o analizar la siguiente pregunta sobre el historial de interacciones: '{user_question}'
                    Debes consultar SIEMPRE sobre la tabla 'historial_chat'.

                    Reglas:
                    1. Devuelve SOLO el código SQL, sin explicaciones.
                    2. Usa comillas dobles para identificadores si es necesario.
                    3. Si el usuario pregunta por el historial, devuelve la lista completa con todas sus columnas.
                    4. Si la pregunta es sobre un usuario, utiliza LIKE para buscar coincidencias parciales tanto en el campo usuario de historial_chat como en el campo Nombre o NombreUsuario de la tabla usuarios.
                    5. Si la pregunta es sobre una fecha, filtra por la columna de fecha.
                    6. Si la pregunta no es lo suficientemente específica, sugiere 3 preguntas relevantes.
                    7. Si la pregunta no puede responderse con los datos, sugiere 3 preguntas relevantes.
                    8. Si la pregunta es sobre tendencias, patrones o estadísticas, genera la consulta adecuada.
                    """
                else:
                    sql_prompt = f"""
                    Eres un experto en SQLite. Basado en el siguiente esquema de base de datos:
                    {schema}

                    Genera codigo SQL, ya sea para responder o editar la base de datos deacuerdo a: '{user_question}'
                    Debes consultar SIEMPRE sobre la tabla '{tabla_seleccionada}'.

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
                    12. 
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
                guardar_interaccion(db_file, name, user_question, suggestions)
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
                    # Mostrar SQL generado solo si debug_mode está activado
                    if show_structure:
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

                    en caso de que la consulta esté dirigida sea acerca de las ventas de un usuario, Responde SOLO cuántas veces dijo expresamente que queria vender y qué fue lo que vendió. No incluyas detalles adicionales ni recomendaciones.                                      
                    """
                    explanation = ask_gemini(explanation_prompt, model)
                    st.write("💡 Explicación:", explanation)
                    reproducir_audio(explanation)
                    guardar_interaccion(db_file, name, user_question, explanation)
                else:
                    # Mostrar SQL generado solo si debug_mode está activado
                    if show_structure:
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

    # Carga el rol del usuario autenticado
    username = st.session_state.get('username', None)
    user_role = None
    for uname, udata in credentials["usernames"].items():
        if udata["name"] == name:
            user_role = udata.get("rol", "usuario")
            break

    # Panel de administración solo para administradores
    if user_role == "administrador":
        with st.sidebar.expander("⚙️ Administración", expanded=False):
            conn_admin = create_connection(db_file)
            admin_panel(conn_admin, db_file)
            conn_admin.close()




if __name__ == "__main__":
    main()