
import streamlit as st
import pandas as pd
import requests
from datetime import date, timedelta
from zoneinfo import ZoneInfo

API_URL = "https://v3.football.api-sports.io"
TIMEZONE = "America/Santiago"

st.set_page_config(
    page_title="CanchaLab IA",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ CanchaLab IA")
st.caption("Análisis de fútbol · Próximos partidos · Forma reciente · Probabilidades")

# ---------- API ----------
if "API_FOOTBALL_KEY" not in st.secrets:
    st.error(
        "Falta configurar API_FOOTBALL_KEY en "
        "Streamlit Cloud → Settings → Secrets."
    )
    st.stop()

API_KEY = st.secrets["API_FOOTBALL_KEY"]


@st.cache_data(ttl=900, show_spinner=False)
def api_get(endpoint, params, api_key):
    """Consulta la API y guarda resultados en caché durante 15 minutos."""
    response = requests.get(
        f"{API_URL}/{endpoint}",
        headers={"x-apisports-key": api_key},
        params=params,
        timeout=25
    )
    response.raise_for_status()
    data = response.json()

    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))

    return data.get("response", [])


def fecha_chile(fecha_iso):
    try:
        dt = pd.to_datetime(fecha_iso, utc=True)
        return dt.tz_convert(TIMEZONE).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return fecha_iso or "Horario no disponible"


def porcentaje(valor):
    """Convierte, por ejemplo, '45%' en 45."""
    try:
        return float(str(valor).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def obtener_forma(team_id, team_name):
  
partidos = []

for i in range((fecha_fin - fecha_inicio).days + 1):
    dia = fecha_inicio + timedelta(days=i)

    resultados_dia = api_get(
        "fixtures",
        {"date": dia.isoformat()},
        API_KEY
    )

    partidos.extend(resultados_dia)

    jugados = []

    for partido in partidos:
        local = partido.get("teams", {}).get("home", {})
        visita = partido.get("teams", {}).get("away", {})
        goles = partido.get("goals", {})
        fixture = partido.get("fixture", {})

        gl = goles.get("home")
        gv = goles.get("away")

        if gl is None or gv is None:
            continue

        if local.get("id") == team_id:
            gf, gc = gl, gv
            rival = visita.get("name", "Rival")
            condicion = "L"
        else:
            gf, gc = gv, gl
            rival = local.get("name", "Rival")
            condicion = "V"

        resultado = "E"
        if gf > gc:
            resultado = "G"
        elif gf < gc:
            resultado = "P"

        jugados.append({
            "Fecha": fecha_chile(fixture.get("date")),
            "Rival": rival,
            "Condición": condicion,
            "Marcador": f"{gl}-{gv}",
            "Resultado": resultado,
            "_fecha": fixture.get("date", "")
        })

    jugados.sort(key=lambda x: x["_fecha"])

    resumen = {
        "G": sum(p["Resultado"] == "G" for p in jugados),
        "E": sum(p["Resultado"] == "E" for p in jugados),
        "P": sum(p["Resultado"] == "P" for p in jugados),
        "GF": 0,
        "GC": 0
    }

    for partido in partidos:
        local = partido.get("teams", {}).get("home", {})
        visita = partido.get("teams", {}).get("away", {})
        goles = partido.get("goals", {})
        gl, gv = goles.get("home"), goles.get("away")

        if gl is None or gv is None:
            continue

        if local.get("id") == team_id:
            resumen["GF"] += gl
            resumen["GC"] += gv
        else:
            resumen["GF"] += gv
            resumen["GC"] += gl

    tabla = pd.DataFrame(jugados)
    if not tabla.empty:
        tabla = tabla.drop(columns=["_fecha"])

    return resumen, tabla


# ---------- Filtros ----------
hoy = date.today()
col1, col2 = st.columns(2)

with col1:
    fecha_inicio = st.date_input(
        "Desde",
        value=hoy,
        key="fecha_inicio"
    )

with col2:
    dias = st.selectbox(
        "Buscar próximos días",
        [1, 3, 7, 14],
        index=2,
        format_func=lambda n: f"{n} día(s)"
    )

fecha_fin = fecha_inicio + timedelta(days=dias - 1)

st.caption(
    f"Período: {fecha_inicio.strftime('%d/%m/%Y')} "
    f"al {fecha_fin.strftime('%d/%m/%Y')} · Horario de Chile"
)

if st.button("🔎 Buscar partidos", type="primary", use_container_width=True):
    st.session_state["buscar_partidos"] = True

if st.session_state.get("buscar_partidos", False):
    try:
        with st.spinner("Buscando calendario de partidos..."):
            partidos = api_get(
                "fixtures",
                {
                    "from": fecha_inicio.strftime("%Y-%m-%d"),
"to": fecha_fin.strftime("%Y-%m-%d"),
"timezone": "America/Santiago"
                },
                API_KEY
            )

        # Solo encuentros que todavía no han comenzado.
        proximos = [
            p for p in partidos
            if p.get("fixture", {}).get("status", {}).get("short")
            in ("NS", "TBD")
        ]

        proximos.sort(
            key=lambda p: p.get("fixture", {}).get("date", "")
        )

        if not proximos:
            st.info(
                "No encontramos partidos próximos en ese período. "
                "Prueba con más días o con otra fecha."
            )
            st.stop()

        opciones = {}
        for p in proximos:
            fixture = p.get("fixture", {})
            equipos = p.get("teams", {})
            liga = p.get("league", {})
            local = equipos.get("home", {}).get("name", "Local")
            visita = equipos.get("away", {}).get("name", "Visitante")
            nombre_liga = liga.get("name", "Competición")
            horario = fecha_chile(fixture.get("date"))

            etiqueta = (
                f"{horario} | {local} vs {visita} "
                f"| {nombre_liga}"
            )
            # Evita sobrescribir partidos con etiquetas iguales.
            opciones[f"{etiqueta} · ID {fixture.get('id')}"] = p

        st.success(f"Encontramos {len(opciones)} partidos próximos.")

        seleccion = st.selectbox(
            "Elige el partido que quieres analizar",
            list(opciones.keys())
        )
        partido = opciones[seleccion]

        fixture = partido.get("fixture", {})
        equipos = partido.get("teams", {})
        liga = partido.get("league", {})
        local = equipos.get("home", {})
        visita = equipos.get("away", {})

        st.divider()
        st.subheader(
            f"{local.get('name', 'Local')} vs "
            f"{visita.get('name', 'Visitante')}"
        )
        st.write(
            f"**Competición:** {liga.get('name', 'No disponible')} "
            f"— {liga.get('country', '')}"
        )
        st.write(f"**Inicio:** {fecha_chile(fixture.get('date'))}")

        if st.button("📊 Analizar este partido", type="primary"):
            st.session_state["partido_analizado"] = fixture.get("id")

        if st.session_state.get("partido_analizado") == fixture.get("id"):
            with st.spinner("Consultando pronóstico y últimos partidos..."):
                try:
                    predicciones = api_get(
                        "predictions",
                        {"fixture": fixture.get("id")},
                        API_KEY
                    )

                    pred = (
                        predicciones[0].get("predictions", {})
                        if predicciones else {}
                    )

                    local_forma, local_tabla = obtener_forma(
                        local.get("id"), local.get("name")
                    )
                    visita_forma, visita_tabla = obtener_forma(
                        visita.get("id"), visita.get("name")
                    )

                    st.subheader("🎯 Probabilidades del pronóstico")

                    percent = pred.get("percent", {})
                    p_local = porcentaje(percent.get("home"))
                    p_empate = porcentaje(percent.get("draw"))
                    p_visita = porcentaje(percent.get("away"))

                    if any(x is not None for x in [p_local, p_empate, p_visita]):
                        c1, c2, c3 = st.columns(3)

                        with c1:
                            st.metric(
                                f"🏠 {local.get('name')}",
                                f"{p_local:.1f}%" if p_local is not None else "N/D"
                            )
                        with c2:
                            st.metric(
                                "🤝 Empate",
                                f"{p_empate:.1f}%" if p_empate is not None else "N/D"
                            )
                        with c3:
                            st.metric(
                                f"✈️ {visita.get('name')}",
                                f"{p_visita:.1f}%" if p_visita is not None else "N/D"
                            )

                        valores = {
                            "Victoria local": p_local,
                            "Empate": p_empate,
                            "Victoria visitante": p_visita
                        }
                        valores = {
                            k: v for k, v in valores.items()
                            if v is not None
                        }
                        if valores:
                            st.bar_chart(pd.Series(valores))
                    else:
                        st.warning(
                            "La API no entregó probabilidades para este "
                            "partido. Puede que la competición no tenga "
                            "pronóstico disponible."
                        )

                    ganador = pred.get("winner", {})
                    ganador_nombre = (
                        ganador.get("name")
                        if isinstance(ganador, dict) else None
                    )
                    if ganador_nombre:
                        st.write(f"**Ganador señalado por la API:** {ganador_nombre}")

                    goles_estimados = pred.get("goals", {})
                    gl_est = goles_estimados.get("home")
                    gv_est = goles_estimados.get("away")
                    if gl_est is not None or gv_est is not None:
                        st.write(
                            f"**Marcador estimado por la API:** "
                            f"{local.get('name')} {gl_est if gl_est is not None else '?'} "
                            f"- {gv_est if gv_est is not None else '?'} "
                            f"{visita.get('name')}"
                        )

                    if pred.get("advice"):
                        st.write(f"**Consejo de la API:** {pred['advice']}")

                    st.caption(
                        "Estos pronósticos son estimaciones de API-Football, "
                        "no resultados garantizados."
                    )

                    st.divider()
                    st.subheader("📈 Forma reciente: últimos partidos")

                    fc1, fc2 = st.columns(2)

                    for columna, nombre, forma, tabla in [
                        (fc1, local.get("name"), local_forma, local_tabla),
                        (fc2, visita.get("name"), visita_forma, visita_tabla)
                    ]:
                        with columna:
                            st.markdown(f"**{nombre}**")
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Victorias", forma["G"])
                            m2.metric("Empates", forma["E"])
                            m3.metric("Derrotas", forma["P"])
                            st.caption(
                                f"Goles a favor: {forma['GF']} · "
                                f"Goles en contra: {forma['GC']}"
                            )
                            if not tabla.empty:
                                st.dataframe(
                                    tabla,
                                    hide_index=True,
                                    use_container_width=True
                                )
                            else:
                                st.info("No hay resultados recientes disponibles.")

                except requests.HTTPError as e:
                    st.error(
                        f"Error HTTP de la API: {e}. Revisa tu clave, "
                        "el acceso al endpoint y tu cuota."
                    )
                except requests.RequestException as e:
                    st.error(f"No se pudo conectar con la API: {e}")
                except Exception as e:
                    st.error(f"No se pudo completar el análisis: {e}")

    except requests.HTTPError as e:
        st.error(
            f"Error al buscar partidos: {e}. Revisa tu clave API "
            "y el límite de solicitudes."
        )
    except requests.RequestException as e:
        st.error(f"Problema de conexión: {e}")
    except Exception as e:
        st.error(f"Error al cargar los partidos: {e}")

st.divider()
st.caption(
    "CanchaLab IA · Herramienta informativa. "
    "El fútbol es impredecible; ninguna probabilidad asegura un resultado."
)
