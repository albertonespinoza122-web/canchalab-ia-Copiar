
import streamlit as st
import pandas as pd
import requests
from datetime import date, timedelta

# ==================================================
# CONFIGURACIÓN
# ==================================================
st.set_page_config(
    page_title="CanchaLab IA",
    page_icon="⚽",
    layout="wide"
)

API_URL = "https://v3.football.api-sports.io"
ZONA_CHILE = "America/Santiago"

st.title("⚽ CanchaLab IA")
st.caption("Partidos próximos · Pronósticos · Estadísticas · Forma reciente")

# ==================================================
# CLAVE API
# ==================================================
try:
    API_KEY = st.secrets["API_FOOTBALL_KEY"]
except Exception:
    st.error(
        "No se encontró API_FOOTBALL_KEY. "
        "Configúrala en Streamlit Cloud → Settings → Secrets."
    )
    st.stop()


# ==================================================
# FUNCIONES API
# ==================================================
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

    if datos.get("errors"):
        raise RuntimeError(f"API-Football: {datos['errors']}")

    return datos.get("response", [])


def formato_fecha(fecha_iso):
    if not fecha_iso:
        return "No disponible"

    try:
        fecha_dt = pd.to_datetime(fecha_iso, utc=True)
        return fecha_dt.tz_convert(ZONA_CHILE).strftime(
            "%d/%m/%Y %H:%M"
        )
    except Exception:
        return str(fecha_iso)


def porcentaje(valor):
    if valor is None:
        return None

    try:
        return float(str(valor).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ==================================================
# ÚLTIMOS CINCO PARTIDOS
# No usa el parámetro "last", restringido en el plan Free.
# Consulta por equipo y temporada.
# ==================================================
@st.cache_data(ttl=900, show_spinner=False)
def cargar_ultimos_partidos(team_id, clave):
    ahora = pd.Timestamp.now(tz=ZONA_CHILE)
    anio_actual = ahora.year

    partidos = []
    errores_consulta = []

    # Prueba la temporada actual y, si es necesario,
    # la anterior. No utiliza el parámetro "last".
    for temporada in [anio_actual, anio_actual - 1]:
        try:
            encontrados = consultar_api(
                "fixtures",
                {
                    "team": team_id,
                    "season": temporada
                },
                clave
            )

            partidos.extend(encontrados)

            finalizados = [
                p for p in partidos
                if p.get("fixture", {}).get("status", {}).get("short")
                in ("FT", "AET", "PEN")
                and p.get("goals", {}).get("home") is not None
                and p.get("goals", {}).get("away") is not None
            ]

            if len(finalizados) >= 5:
                break

        except Exception as e:
            errores_consulta.append(str(e))

    # Elimina duplicados por ID.
    unicos = {}
    for p in partidos:
        partido_id = p.get("fixture", {}).get("id")
        if partido_id is not None:
            unicos[partido_id] = p

    partidos = list(unicos.values())

    # Solo partidos finalizados hasta la fecha actual.
    finalizados = []

    for p in partidos:
        fixture = p.get("fixture", {})
        estado = fixture.get("status", {}).get("short")

        if estado not in ("FT", "AET", "PEN"):
            continue

        goles = p.get("goals", {})
        if goles.get("home") is None or goles.get("away") is None:
            continue

        try:
            fecha_partido = pd.to_datetime(
                fixture.get("date"), utc=True
            )
            if fecha_partido > ahora.tz_convert("UTC"):
                continue
        except Exception:
            continue

        finalizados.append(p)

    finalizados.sort(
        key=lambda p: p.get("fixture", {}).get("date", "")
    )

    recientes = finalizados[-5:]

    victorias = 0
    empates = 0
    derrotas = 0
    goles_favor = 0
    goles_contra = 0
    filas = []

    for p in recientes:
        fixture = p.get("fixture", {})
        equipos = p.get("teams", {})
        goles = p.get("goals", {})

        local = equipos.get("home", {})
        visita = equipos.get("away", {})
        gl = goles["home"]
        gv = goles["away"]

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

    return resumen, pd.DataFrame(filas), errores_consulta


# ==================================================
# BUSCAR PARTIDOS PRÓXIMOS
# Consulta individual por día.
# ==================================================
st.divider()
st.header("📅 Próximos partidos")

hoy = pd.Timestamp.now(tz=ZONA_CHILE).date()

col1, col2 = st.columns(2)

with col1:
    fecha_inicio = st.date_input(
        "Fecha de inicio",
        value=hoy
    )

with col2:
    dias = st.selectbox(
        "Período",
        [1, 3, 7, 14],
        index=0,
        format_func=lambda n: f"{n} día(s)"
    )

fecha_fin = fecha_inicio + timedelta(days=dias - 1)

st.caption(
    f"Fechas: {fecha_inicio.strftime('%d/%m/%Y')} "
    f"al {fecha_fin.strftime('%d/%m/%Y')}"
)

if st.button(
    "🔎 Buscar partidos",
    type="primary",
    use_container_width=True
):
    st.session_state["partidos"] = None
    st.session_state["error_busqueda"] = None
    st.session_state.pop("analisis_id", None)

    try:
        resultados = []

        with st.spinner("Consultando calendario..."):
            for i in range(dias):
                dia = fecha_inicio + timedelta(days=i)

                del_dia = consultar_api(
                    "fixtures",
                    {"date": dia.isoformat()},
                    API_KEY
                )

                resultados.extend(del_dia)

        # Eliminar duplicados.
        unicos = {}
        for p in resultados:
            partido_id = p.get("fixture", {}).get("id")
            if partido_id is not None:
                unicos[partido_id] = p

        resultados = list(unicos.values())

        # Solo encuentros que no hayan comenzado.
        resultados = [
            p for p in resultados
            if p.get("fixture", {}).get("status", {}).get("short")
            in ("NS", "TBD")
        ]

        resultados.sort(
            key=lambda p: p.get("fixture", {}).get("date", "")
        )

        st.session_state["partidos"] = resultados

    except requests.HTTPError as e:
        st.session_state["error_busqueda"] = (
            f"Error HTTP: {e}. Revisa tu clave y tu plan."
        )
    except requests.RequestException as e:
        st.session_state["error_busqueda"] = (
            f"Problema de conexión: {e}"
        )
    except Exception as e:
        st.session_state["error_busqueda"] = str(e)


if st.session_state.get("error_busqueda"):
    st.error(st.session_state["error_busqueda"])

partidos = st.session_state.get("partidos")

if partidos is not None:
    if not partidos:
        st.warning(
            "No hay partidos pendientes para ese período. "
            "Prueba con otra fecha o amplía la búsqueda."
        )
    else:
        st.success(f"Partidos encontrados: {len(partidos)}")

        opciones = {}

        for p in partidos:
            fixture = p.get("fixture", {})
            equipos = p.get("teams", {})
            liga = p.get("league", {})

            local = equipos.get("home", {}).get("name", "Local")
            visita = equipos.get("away", {}).get("name", "Visitante")
            competicion = liga.get("name", "Competición")
            partido_id = fixture.get("id")

            etiqueta = (
                f"{formato_fecha(fixture.get('date'))} | "
                f"{local} vs {visita} | {competicion} | ID {partido_id}"
            )
            opciones[etiqueta] = p

        seleccion = st.selectbox(
            "Selecciona un encuentro",
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
            f"{local.get('name')} vs {visita.get('name')}"
        )

        st.write(
            f"**Competición:** {liga.get('name', 'No disponible')} "
            f"— {liga.get('country', '')}"
        )
        st.write(
            f"**Horario de Chile:** "
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
                with st.spinner("Analizando el encuentro..."):
                    predicciones = consultar_api(
                        "predictions",
                        {"fixture": partido_id},
                        API_KEY
                    )

                    pred = {}
                    if predicciones:
                        pred = (
                            predicciones[0].get("predictions", {}) or {}
                        )

                    forma_local, tabla_local, errores_local = (
                        cargar_ultimos_partidos(local.get("id"), API_KEY)
                    )
                    forma_visita, tabla_visita, errores_visita = (
                        cargar_ultimos_partidos(visita.get("id"), API_KEY)
                    )

                st.header("🎯 Probabilidades")

                porcentajes = pred.get("percent", {}) or {}

                p_local = porcentaje(porcentajes.get("home"))
                p_empate = porcentaje(porcentajes.get("draw"))
                p_visita = porcentaje(porcentajes.get("away"))

                if any(
                    v is not None
                    for v in (p_local, p_empate, p_visita)
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

                    grafico = {
                        "Victoria local": p_local,
                        "Empate": p_empate,
                        "Victoria visitante": p_visita
                    }
                    grafico = {
                        k: v for k, v in grafico.items()
                        if v is not None
                    }

                    st.bar_chart(pd.Series(grafico))
                else:
                    st.warning(
                        "API-Football no entregó probabilidades para "
                        "este encuentro."
                    )

                ganador = pred.get("winner", {}) or {}
                if isinstance(ganador, dict) and ganador.get("name"):
                    st.write(
                        f"**Ganador señalado por la API:** "
                        f"{ganador['name']}"
                    )

                goles = pred.get("goals", {}) or {}
                gl = goles.get("home")
                gv = goles.get("away")

                if gl is not None or gv is not None:
                    st.write(
                        f"**Marcador estimado por la API:** "
                        f"{local.get('name')} {gl if gl is not None else '?'} "
                        f"- {gv if gv is not None else '?'} "
                        f"{visita.get('name')}"
                    )

                if pred.get("advice"):
                    st.info(f"**Consejo de la API:** {pred['advice']}")

                st.caption(
                    "Pronósticos orientativos de API-Football; "
                    "no garantizan el resultado."
                )

                st.divider()
                st.header("📈 Rendimiento reciente")

                col_local, col_visita = st.columns(2)

                for columna, nombre, resumen, tabla, errores in [
                    (
                        col_local,
                        local.get("name", "Local"),
                        forma_local,
                        tabla_local,
                        errores_local
                    ),
                    (
                        col_visita,
                        visita.get("name", "Visitante"),
                        forma_visita,
                        tabla_visita,
                        errores_visita
                    )
                ]:
                    with columna:
                        st.subheader(nombre)

                        a, b, c = st.columns(3)
                        a.metric("Victorias", resumen["Victorias"])
                        b.metric("Empates", resumen["Empates"])
                        c.metric("Derrotas", resumen["Derrotas"])

                        st.write(
                            f"Goles a favor: **{resumen['Goles a favor']}**"
                        )
                        st.write(
                            f"Goles en contra: **{resumen['Goles en contra']}**"
                        )

                        if not tabla.empty:
                            st.dataframe(
                                tabla,
                                hide_index=True,
                                use_container_width=True
                            )
                        else:
                            st.warning(
                                "No se encontraron partidos recientes "
                                "en las temporadas consultadas."
                            )

                        if errores:
                            st.caption(
                                "Aviso de consulta de temporadas: "
                                + "; ".join(errores)
                            )

            except requests.HTTPError as e:
                st.error(f"Error HTTP durante el análisis: {e}")
            except requests.RequestException as e:
                st.error(f"Problema de conexión durante el análisis: {e}")
            except Exception as e:
                st.error(f"No se pudo completar el análisis: {e}")


st.divider()
st.caption(
    "CanchaLab IA · La cobertura depende de API-Football. "
    "Las estadísticas y los pronósticos no aseguran resultados."
)
