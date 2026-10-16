
import streamlit as st
import pandas as pd
import requests
from datetime import date, timedelta
from zoneinfo import ZoneInfo

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------
st.set_page_config(
    page_title="CanchaLab IA",
    page_icon="⚽",
    layout="wide"
)

API_URL = "https://v3.football.api-sports.io"
ZONA_CHILE = "America/Santiago"

st.title("⚽ CanchaLab IA")
st.subheader("Tu centro de análisis futbolístico")
st.write(
    "Consulta próximos partidos, probabilidades de resultado "
    "y rendimiento reciente de los equipos."
)

# --------------------------------------------------
# CLAVE API
# --------------------------------------------------
try:
    API_KEY = st.secrets["API_FOOTBALL_KEY"]
except Exception:
    st.error(
        "No encuentro API_FOOTBALL_KEY. Configúrala en "
        "Streamlit Cloud → Settings → Secrets."
    )
    st.stop()


# --------------------------------------------------
# CONEXIÓN CON API-FOOTBALL
# --------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def consultar_api(endpoint, parametros, clave):
    respuesta = requests.get(
        f"{API_URL}/{endpoint}",
        headers={"x-apisports-key": clave},
        params=parametros,
        timeout=25
    )

    respuesta.raise_for_status()
    datos = respuesta.json()

    errores = datos.get("errors")
    if errores:
        raise RuntimeError(f"API-Football: {errores}")

    return datos.get("response", [])


def formato_fecha(fecha_iso):
    if not fecha_iso:
        return "Horario no disponible"

    try:
        fecha_dt = pd.to_datetime(fecha_iso, utc=True)
        return fecha_dt.tz_convert(ZONA_CHILE).strftime(
            "%d/%m/%Y %H:%M"
        )
    except Exception:
        return str(fecha_iso)


def convertir_porcentaje(valor):
    if valor is None:
        return None

    try:
        return float(str(valor).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def cargar_ultimos_partidos(team_id):
    datos = consultar_api(
        "fixtures",
        {
            "team": team_id,
            "last": 5,
            "timezone": ZONA_CHILE
        },
        API_KEY
    )

    filas = []
    victorias = 0
    empates = 0
    derrotas = 0
    goles_favor = 0
    goles_contra = 0

    for p in datos:
        fixture = p.get("fixture", {})
        equipos = p.get("teams", {})
        goles = p.get("goals", {})

        local = equipos.get("home", {})
        visita = equipos.get("away", {})

        gl = goles.get("home")
        gv = goles.get("away")

        if gl is None or gv is None:
            continue

        if local.get("id") == team_id:
            gf, gc = gl, gv
            rival = visita.get("name", "Rival")
            condicion = "Local"
        else:
            gf, gc = gv, gl
            rival = local.get("name", "Rival")
            condicion = "Visitante"

        if gf > gc:
            resultado = "Victoria"
            victorias += 1
        elif gf == gc:
            resultado = "Empate"
            empates += 1
        else:
            resultado = "Derrota"
            derrotas += 1

        goles_favor += gf
        goles_contra += gc

        filas.append({
            "Fecha": formato_fecha(fixture.get("date")),
            "Rival": rival,
            "Condición": condicion,
            "Marcador": f"{gl} - {gv}",
            "Resultado": resultado
        })

    resumen = {
        "Victorias": victorias,
        "Empates": empates,
        "Derrotas": derrotas,
        "Goles a favor": goles_favor,
        "Goles en contra": goles_contra
    }

    return resumen, pd.DataFrame(filas)


# --------------------------------------------------
# BUSCAR PARTIDOS POR FECHA
# Se utiliza date, sin from/to/timezone en esta consulta.
# --------------------------------------------------
st.divider()
st.header("📅 Próximos partidos")

hoy_chile = date.today()

try:
    hoy_chile = pd.Timestamp.now(tz=ZONA_CHILE).date()
except Exception:
    pass

col1, col2 = st.columns(2)

with col1:
    fecha_inicio = st.date_input(
        "Fecha de inicio",
        value=hoy_chile
    )

with col2:
    cantidad_dias = st.selectbox(
        "Período de búsqueda",
        [1, 3, 7, 14],
        index=0,
        format_func=lambda x: f"{x} día(s)"
    )

fecha_fin = fecha_inicio + timedelta(days=cantidad_dias - 1)

st.caption(
    f"Buscaremos del {fecha_inicio.strftime('%d/%m/%Y')} "
    f"al {fecha_fin.strftime('%d/%m/%Y')}. "
    "La búsqueda utiliza una consulta por día."
)

if st.button(
    "🔎 Buscar partidos",
    type="primary",
    use_container_width=True
):
    st.session_state["partidos_busqueda"] = None
    st.session_state["partidos_error"] = None

    try:
        lista_partidos = []

        with st.spinner("Buscando el calendario..."):
            for numero_dia in range(cantidad_dias):
                dia = fecha_inicio + timedelta(days=numero_dia)

                resultados = consultar_api(
                    "fixtures",
                    {"date": dia.isoformat()},
                    API_KEY
                )

                lista_partidos.extend(resultados)

        # Elimina posibles duplicados por ID de partido.
        unicos = {}
        for p in lista_partidos:
            partido_id = p.get("fixture", {}).get("id")
            if partido_id is not None:
                unicos[partido_id] = p

        lista_partidos = list(unicos.values())

        # Solo encuentros no iniciados.
        lista_partidos = [
            p for p in lista_partidos
            if p.get("fixture", {})
                .get("status", {})
                .get("short") in ("NS", "TBD")
        ]

        lista_partidos.sort(
            key=lambda p: p.get("fixture", {}).get("date", "")
        )

        st.session_state["partidos_busqueda"] = lista_partidos

    except requests.HTTPError as e:
        st.session_state["partidos_error"] = (
            f"Error HTTP al consultar la API: {e}. "
            "Comprueba tu clave y los límites de tu plan."
        )
    except requests.RequestException as e:
        st.session_state["partidos_error"] = (
            f"Problema de conexión: {e}"
        )
    except Exception as e:
        st.session_state["partidos_error"] = str(e)


if st.session_state.get("partidos_error"):
    st.error(st.session_state["partidos_error"])

partidos = st.session_state.get("partidos_busqueda")

if partidos is not None:
    if not partidos:
        st.warning(
            "No encontramos partidos pendientes en esas fechas. "
            "Prueba otro día o amplía el período."
        )
    else:
        st.success(f"Encontramos {len(partidos)} partidos próximos.")

        opciones = {}

        for p in partidos:
            fixture = p.get("fixture", {})
            equipos = p.get("teams", {})
            liga = p.get("league", {})

            local = equipos.get("home", {}).get("name", "Local")
            visita = equipos.get("away", {}).get("name", "Visitante")
            nombre_liga = liga.get("name", "Competición")
            horario = formato_fecha(fixture.get("date"))
            partido_id = fixture.get("id")

            etiqueta = (
                f"{horario} | {local} vs {visita} | "
                f"{nombre_liga} | ID {partido_id}"
            )
            opciones[etiqueta] = p

        seleccion = st.selectbox(
            "Selecciona el partido",
            list(opciones.keys())
        )

        partido = opciones[seleccion]
        fixture = partido.get("fixture", {})
        equipos = partido.get("teams", {})
        liga = partido.get("league", {})

        local = equipos.get("home", {})
        visita = equipos.get("away", {})
        partido_id = fixture.get("id")

        st.divider()
        st.subheader(
            f"{local.get('name', 'Local')} vs "
            f"{visita.get('name', 'Visitante')}"
        )

        st.write(
            f"**Competición:** {liga.get('name', 'No disponible')} "
            f"({liga.get('country', '')})"
        )
        st.write(
            f"**Fecha y hora de Chile:** "
            f"{formato_fecha(fixture.get('date'))}"
        )

        if st.button(
            "📊 Analizar partido",
            type="primary",
            use_container_width=True
        ):
            st.session_state["analisis_id"] = partido_id

        if st.session_state.get("analisis_id") == partido_id:
            try:
                with st.spinner(
                    "Analizando pronóstico y forma reciente..."
                ):
                    predicciones = consultar_api(
                        "predictions",
                        {"fixture": partido_id},
                        API_KEY
                    )

                    pred = {}
                    if predicciones:
                        pred = predicciones[0].get(
                            "predictions", {}
                        ) or {}

                    forma_local, tabla_local = cargar_ultimos_partidos(
                        local.get("id")
                    )
                    forma_visita, tabla_visita = cargar_ultimos_partidos(
                        visita.get("id")
                    )

                st.header("🎯 Probabilidades de resultado")

                porcentaje_pred = pred.get("percent", {}) or {}

                p_local = convertir_porcentaje(
                    porcentaje_pred.get("home")
                )
                p_empate = convertir_porcentaje(
                    porcentaje_pred.get("draw")
                )
                p_visita = convertir_porcentaje(
                    porcentaje_pred.get("away")
                )

                if any(
                    v is not None
                    for v in [p_local, p_empate, p_visita]
                ):
                    c1, c2, c3 = st.columns(3)

                    with c1:
                        st.metric(
                            f"🏠 {local.get('name')}",
                            f"{p_local:g}%"
                            if p_local is not None else "N/D"
                        )

                    with c2:
                        st.metric(
                            "🤝 Empate",
                            f"{p_empate:g}%"
                            if p_empate is not None else "N/D"
                        )

                    with c3:
                        st.metric(
                            f"✈️ {visita.get('name')}",
                            f"{p_visita:g}%"
                            if p_visita is not None else "N/D"
                        )

                    datos_grafico = {
                        "Victoria local": p_local,
                        "Empate": p_empate,
                        "Victoria visitante": p_visita
                    }

                    datos_grafico = {
                        k: v for k, v in datos_grafico.items()
                        if v is not None
                    }

                    st.bar_chart(
                        pd.Series(datos_grafico, name="Probabilidad (%)")
                    )
                else:
                    st.warning(
                        "No hay probabilidades disponibles para este "
                        "partido en API-Football. No inventaremos cifras."
                    )

                ganador = pred.get("winner", {}) or {}
                if isinstance(ganador, dict) and ganador.get("name"):
                    st.write(
                        f"**Ganador señalado por la API:** "
                        f"{ganador['name']}"
                    )

                goles_pred = pred.get("goals", {}) or {}
                gl_pred = goles_pred.get("home")
                gv_pred = goles_pred.get("away")

                if gl_pred is not None or gv_pred is not None:
                    st.write(
                        f"**Marcador estimado por la API:** "
                        f"{local.get('name')} "
                        f"{gl_pred if gl_pred is not None else '?'} - "
                        f"{gv_pred if gv_pred is not None else '?'} "
                        f"{visita.get('name')}"
                    )

                if pred.get("advice"):
                    st.info(f"**Pronóstico de la API:** {pred['advice']}")

                st.caption(
                    "Las probabilidades son estimaciones de API-Football, "
                    "no garantías de resultado."
                )

                st.divider()
                st.header("📈 Últimos cinco partidos")

                col_local, col_visita = st.columns(2)

                with col_local:
                    st.subheader(local.get("name", "Local"))
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Victorias", forma_local["Victorias"])
                    m2.metric("Empates", forma_local["Empates"])
                    m3.metric("Derrotas", forma_local["Derrotas"])

                    st.write(
                        f"Goles a favor: **{forma_local['Goles a favor']}**"
                    )
                    st.write(
                        f"Goles en contra: **{forma_local['Goles en contra']}**"
                    )

                    if not tabla_local.empty:
                        st.dataframe(
                            tabla_local,
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.info("No hay resultados recientes disponibles.")

                with col_visita:
                    st.subheader(visita.get("name", "Visitante"))
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Victorias", forma_visita["Victorias"])
                    m2.metric("Empates", forma_visita["Empates"])
                    m3.metric("Derrotas", forma_visita["Derrotas"])

                    st.write(
                        f"Goles a favor: **{forma_visita['Goles a favor']}**"
                    )
                    st.write(
                        f"Goles en contra: **{forma_visita['Goles en contra']}**"
                    )

                    if not tabla_visita.empty:
                        st.dataframe(
                            tabla_visita,
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.info("No hay resultados recientes disponibles.")

            except requests.HTTPError as e:
                st.error(
                    f"Error HTTP durante el análisis: {e}. "
                    "Puede ser un límite de la API o un endpoint no disponible."
                )
            except requests.RequestException as e:
                st.error(f"Error de conexión durante el análisis: {e}")
            except Exception as e:
                st.error(f"No se pudo completar el análisis: {e}")

st.divider()
st.caption(
    "CanchaLab IA · Datos sujetos a la cobertura de API-Football. "
    "El análisis estadístico no garantiza resultados deportivos."
)

