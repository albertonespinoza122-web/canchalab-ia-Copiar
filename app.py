
import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from collections import Counter

# =========================================================
# CANCHALAB IA - MATCHGRIND
# Datos reales de partidos, resultados y forma reciente.
# No requiere API key según la documentación pública.
# =========================================================

st.set_page_config(
    page_title="CanchaLab IA",
    page_icon="⚽",
    layout="wide",
)

BASE_URL = "https://www.matchgrind.space/get/soccer"
TIMEOUT = 20

LIGAS = {
    "Premier League (Inglaterra)": "eng.1",
    "Championship (Inglaterra)": "eng.2",
    "La Liga (España)": "esp.1",
    "Segunda División (España)": "esp.2",
    "Bundesliga (Alemania)": "ger.1",
    "2. Bundesliga (Alemania)": "ger.2",
    "Serie A (Italia)": "ita.1",
    "Serie B (Italia)": "ita.2",
    "Ligue 1 (Francia)": "fra.1",
    "Ligue 2 (Francia)": "fra.2",
    "Eredivisie (Países Bajos)": "ned.1",
    "Primeira Liga (Portugal)": "por.1",
    "Scottish Premiership": "sco.1",
    "Belgian Pro League": "bel.1",
    "Turkish Super Lig": "tur.1",
    "Champions League": "uefa.champions",
    "Europa League": "uefa.europa",
    "Conference League": "uefa.europa.conf",
    "MLS (Estados Unidos)": "usa.1",
    "Liga MX (México)": "mex.1",
    "Brasileirão (Brasil)": "bra.1",
    "Liga Profesional (Argentina)": "arg.1",
    "Copa Libertadores": "conmebol.libertadores",
    "Copa Sudamericana": "conmebol.sudamericana",
    "Saudi Pro League": "ksa.1",
    "J1 League (Japón)": "jpn.1",
    "A-League (Australia)": "aus.1",
    "FA Cup (Inglaterra)": "eng.fa",
    "Copa del Rey (España)": "esp.copa_del_rey",
    "DFB-Pokal (Alemania)": "ger.dfb_pokal",
    "Coppa Italia": "ita.coppa_italia",
    "Women's Super League": "eng.w.1",
    # Esta competición puede no estar disponible en MatchGrind.
    "Primera División de Chile (probar cobertura)": "chi.1",
}


# -------------------- API --------------------

def llamar_api(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(
            url,
            params=params or {},
            headers={
                "Accept": "application/json",
                "User-Agent": "CanchaLabIA/1.0",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"No se pudo conectar con MatchGrind: {exc}"
        ) from exc

    if response.status_code == 404:
        raise RuntimeError(
            "El endpoint o la competición no están disponibles "
            "en esta dirección."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "MatchGrind limitó temporalmente las consultas. "
            "Espera un momento y vuelve a probar."
        )

    if not response.ok:
        raise RuntimeError(
            f"MatchGrind devolvió HTTP {response.status_code}: "
            f"{response.text[:250]}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            "La respuesta recibida no contiene JSON válido."
        ) from exc


def extraer_lista(payload):
    """Admite listas directas y envoltorios JSON comunes."""
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("events", "matches", "fixtures", "data", "items", "results"):
        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            nested = extraer_lista(value)
            if nested:
                return nested

    # Algunos servicios devuelven un evento individual.
    if (
        "competitions" in payload
        or "homeTeam" in payload
        or "home_team" in payload
    ):
        return [payload]

    return []


@st.cache_data(ttl=900, show_spinner=False)
def cargar_fixtures(slug):
    # Documentación pública: /get/soccer/{liga}/fixtures?status=all
    payload = llamar_api(f"{slug}/fixtures", {"status": "all"})
    return extraer_lista(payload)


@st.cache_data(ttl=300, show_spinner=False)
def cargar_marcador_fecha(slug, fecha_yyyymmdd):
    # Documentación pública: /get/soccer/{liga}/scoreboard?dates=YYYYMMDD
    payload = llamar_api(
        f"{slug}/scoreboard",
        {"dates": fecha_yyyymmdd},
    )
    return extraer_lista(payload)


# -------------------- NORMALIZACIÓN --------------------

def primer_valor(obj, keys, default=None):
    if not isinstance(obj, dict):
        return default

    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value

    return default


def fecha_utc(partido):
    valor = primer_valor(
        partido,
        ("date", "utcDate", "startDate", "kickoff", "dateUtc"),
    )

    if valor is None:
        return None

    try:
        if isinstance(valor, (int, float)):
            return datetime.fromtimestamp(valor, tz=timezone.utc)

        texto = str(valor).replace("Z", "+00:00")
        dt = datetime.fromisoformat(texto)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def equipos_partido(partido):
    # Formato tipo ESPN: competitions -> competitors
    competitions = partido.get("competitions", [])
    if competitions and isinstance(competitions[0], dict):
        competitors = competitions[0].get("competitors", [])

        local = next(
            (x for x in competitors if x.get("homeAway") == "home"),
            None,
        )
        visita = next(
            (x for x in competitors if x.get("homeAway") == "away"),
            None,
        )

        if local and visita:
            return local, visita

    # Formatos alternativos
    local = primer_valor(
        partido, ("homeTeam", "home_team", "home", "local"), {}
    )
    visita = primer_valor(
        partido, ("awayTeam", "away_team", "away", "visitante"), {}
    )

    if isinstance(local, str):
        local = {"name": local}
    if isinstance(visita, str):
        visita = {"name": visita}

    return local or {}, visita or {}


def nombre_equipo(equipo):
    if isinstance(equipo, str):
        return equipo

    return str(
        primer_valor(
            equipo,
            ("displayName", "name", "shortName", "team_name", "abbreviation"),
            "Equipo desconocido",
        )
    )


def id_equipo(equipo):
    if not isinstance(equipo, dict):
        return None
    return primer_valor(equipo, ("id", "teamId", "team_id"))


def obtener_marcador(equipo):
    if not isinstance(equipo, dict):
        return None

    score = primer_valor(equipo, ("score", "goals", "total"))
    if score is None:
        return None

    try:
        return int(float(score))
    except (ValueError, TypeError):
        return None


def estado_partido(partido):
    status = partido.get("status", {})

    if isinstance(status, dict):
        estado = primer_valor(
            status,
            ("type", "name", "state", "description", "detail"),
            "",
        )
        if isinstance(estado, dict):
            estado = primer_valor(estado, ("name", "description"), "")
    else:
        estado = status

    estado = str(estado).strip().lower()

    # Valores típicos de feeds deportivos.
    finalizados = (
        "final", "finished", "complete", "completed",
        "full time", "ft", "aet", "after penalties",
        "terminado", "finalizado", "awarded",
    )
    en_juego = (
        "in progress", "in_progress", "live", "halftime",
        "half time", "1h", "2h", "first half", "second half",
    )
    cancelados = ("cancel", "postpon", "abandon", "suspend")

    if any(x in estado for x in finalizados):
        return "FINAL"
    if any(x in estado for x in en_juego):
        return "EN JUEGO"
    if any(x in estado for x in cancelados):
        return "NO DISPONIBLE"

    # Formato ESPN
    if isinstance(status, dict):
        tipo = status.get("type", {})
        if isinstance(tipo, dict):
            estado_espn = str(tipo.get("state", "")).lower()
            if estado_espn == "post":
                return "FINAL"
            if estado_espn == "in":
                return "EN JUEGO"
            if estado_espn == "pre":
                return "PROGRAMADO"

    return "PROGRAMADO"


def normalizar_partido(partido, slug):
    local, visita = equipos_partido(partido)
    dt = fecha_utc(partido)

    goles_local = obtener_marcador(local)
    goles_visita = obtener_marcador(visita)

    # Algunos feeds guardan el marcador en score.fullTime.
    if goles_local is None or goles_visita is None:
        score = partido.get("score", {})
        if isinstance(score, dict):
            full = score.get("fullTime", score.get("full_time", {}))
            if isinstance(full, dict):
                try:
                    goles_local = (
                        goles_local if goles_local is not None
                        else int(full["home"])
                    )
                    goles_visita = (
                        goles_visita if goles_visita is not None
                        else int(full["away"])
                    )
                except (KeyError, ValueError, TypeError):
                    pass

    estado = estado_partido(partido)
    tiene_marcador = (
        goles_local is not None and goles_visita is not None
    )

    if estado == "FINAL" and tiene_marcador:
        finalizado = True
    else:
        finalizado = False

    return {
        "id": str(primer_valor(partido, ("id", "eventId", "matchId"), "")),
        "slug": slug,
        "fecha": dt,
        "local": nombre_equipo(local),
        "visita": nombre_equipo(visita),
        "local_id": id_equipo(local),
        "visita_id": id_equipo(visita),
        "goles_local": goles_local,
        "goles_visita": goles_visita,
        "estado": estado,
        "finalizado": finalizado,
        "raw": partido,
    }


def tiene_marcador(p):
    return p["goles_local"] is not None and p["goles_visita"] is not None


def texto_partido(p):
    if p["fecha"]:
        fecha_txt = p["fecha"].astimezone().strftime("%d-%m %H:%M")
    else:
        fecha_txt = "Fecha desconocida"

    if tiene_marcador(p):
        marcador = f'{p["goles_local"]} - {p["goles_visita"]}'
    else:
        marcador = "vs."

    return f'{fecha_txt} | {p["local"]} {marcador} {p["visita"]}'


def clave_equipo(nombre):
    return str(nombre).strip().casefold()


# -------------------- ESTADÍSTICAS --------------------

def resumen_equipo(partidos, equipo, condicion=None, limite=5):
    nombre = clave_equipo(equipo)
    elegidos = []

    for p in partidos:
        if not p["finalizado"] or not tiene_marcador(p):
            continue

        local = clave_equipo(p["local"])
        visita = clave_equipo(p["visita"])

        if local == nombre:
            lado = "home"
            gf, gc = p["goles_local"], p["goles_visita"]
            rival = p["visita"]
        elif visita == nombre:
            lado = "away"
            gf, gc = p["goles_visita"], p["goles_local"]
            rival = p["local"]
        else:
            continue

        if condicion and lado != condicion:
            continue

        if p["fecha"] is None:
            continue

        elegidos.append((p, gf, gc, rival, lado))

    elegidos.sort(key=lambda x: x[0]["fecha"], reverse=True)
    elegidos = elegidos[:limite]

    victorias = empates = derrotas = gf_total = gc_total = 0
    filas = []

    for p, gf, gc, rival, lado in elegidos:
        gf_total += gf
        gc_total += gc

        if gf > gc:
            victorias += 1
            forma = "V"
        elif gf == gc:
            empates += 1
            forma = "E"
        else:
            derrotas += 1
            forma = "D"

        filas.append({
            "Fecha": p["fecha"].astimezone().strftime("%d-%m-%Y"),
            "Condición": "Local" if lado == "home" else "Visitante",
            "Rival": rival,
            "Marcador": f"{gf} - {gc}",
            "Forma": forma,
        })

    n = len(elegidos)

    return {
        "jugados": n,
        "victorias": victorias,
        "empates": empates,
        "derrotas": derrotas,
        "gf": gf_total,
        "gc": gc_total,
        "prom_gf": gf_total / n if n else None,
        "prom_gc": gc_total / n if n else None,
        "puntos": victorias * 3 + empates,
        "filas": filas,
    }


def mostrar_resumen(titulo, resumen):
    st.markdown(f"#### {titulo}")

    if resumen["jugados"] == 0:
        st.warning(
            "No hay resultados finalizados suficientes en los datos "
            "recibidos para calcular esta sección."
        )
        return

    a, b, c = st.columns(3)
    a.metric("Partidos", resumen["jugados"])
    b.metric(
        "V / E / D",
        f'{resumen["victorias"]} / {resumen["empates"]} / '
        f'{resumen["derrotas"]}',
    )
    c.metric("Goles a favor / en contra", f'{resumen["gf"]} / {resumen["gc"]}')

    st.caption(
        f'Promedio marcado: {resumen["prom_gf"]:.2f} goles por partido. '
        f'Promedio recibido: {resumen["prom_gc"]:.2f}. '
        f'Puntos: {resumen["puntos"]} de {resumen["jugados"] * 3}.'
    )

    st.dataframe(
        pd.DataFrame(resumen["filas"]),
        hide_index=True,
        use_container_width=True,
    )


def comparar(local, visitante):
    st.markdown("### Comparación estadística")

    if not local["jugados"] or not visitante["jugados"]:
        st.warning(
            "No se puede comparar a ambos equipos de manera responsable: "
            "faltan resultados recientes en la respuesta de la fuente."
        )
        return

    pp_local = local["puntos"] / local["jugados"]
    pp_visita = visitante["puntos"] / visitante["jugados"]

    st.write(
        f'**Equipo local:** {pp_local:.2f} puntos por partido; '
        f'{local["prom_gf"]:.2f} goles marcados y '
        f'{local["prom_gc"]:.2f} recibidos por partido.'
    )
    st.write(
        f'**Equipo visitante:** {pp_visita:.2f} puntos por partido; '
        f'{visitante["prom_gf"]:.2f} goles marcados y '
        f'{visitante["prom_gc"]:.2f} recibidos por partido.'
    )

    diferencia = pp_local - pp_visita
    if diferencia > 0.5:
        st.info("Los resultados disponibles favorecen al local en puntos por partido.")
    elif diferencia < -0.5:
        st.info("Los resultados disponibles favorecen al visitante en puntos por partido.")
    else:
        st.info("Los puntos por partido son parecidos en la muestra disponible.")

    st.caption(
        "Esto describe resultados anteriores; no es una probabilidad "
        "de victoria. No incorpora automáticamente lesiones, alineaciones "
        "ni fuerza de los rivales."
    )


# -------------------- INTERFAZ --------------------

st.title("⚽ CanchaLab IA")
st.subheader("Análisis de fútbol con MatchGrind")

st.write(
    "Consulta partidos, resultados y rendimiento reciente. "
    "El análisis utiliza exclusivamente datos que devuelve la fuente."
)

st.caption(
    "MatchGrind declara endpoints públicos sin API key. "
    "La disponibilidad y profundidad de datos pueden variar por competición."
)

with st.sidebar:
    st.header("Configuración")

    nombres_ligas = list(LIGAS.keys())
    seleccion = st.multiselect(
        "Competiciones",
        nombres_ligas,
        default=[
            "Premier League (Inglaterra)",
            "La Liga (España)",
            "Champions League",
            "Copa Libertadores",
            "Copa Sudamericana",
            "Primera División de Chile (probar cobertura)",
        ],
    )

    hoy = date.today()
    desde = st.date_input("Desde", value=hoy)
    hasta = st.date_input("Hasta", value=hoy + timedelta(days=7))

    st.caption(
        "Comienza con 2 o 3 competiciones para probar la cobertura "
        "y reducir las consultas."
    )

if not seleccion:
    st.info("Selecciona al menos una competición.")
    st.stop()

if hasta < desde:
    st.error("La fecha final no puede ser anterior a la fecha inicial.")
    st.stop()

todos = []
errores = []
cobertura = []

with st.spinner("Consultando partidos y resultados en MatchGrind..."):
    for nombre_liga in seleccion:
        slug = LIGAS[nombre_liga]

        try:
            raw = cargar_fixtures(slug)
            normalizados = [
                normalizar_partido(item, slug)
                for item in raw
                if isinstance(item, dict)
            ]

            # Quitar duplicados cuando existe ID.
            vistos = set()
            unicos = []

            for p in normalizados:
                clave = p["id"] or (
                    p["fecha"], p["local"], p["visita"]
                )
                if clave in vistos:
                    continue
                vistos.add(clave)
                p["competicion"] = nombre_liga
                unicos.append(p)

            todos.extend(unicos)
            cobertura.append({
                "Competición": nombre_liga,
                "Partidos recibidos": len(unicos),
                "Resultados finalizados": sum(
                    1 for p in unicos
                    if p["finalizado"] and tiene_marcador(p)
                ),
            })

        except RuntimeError as exc:
            errores.append(f"{nombre_liga}: {exc}")

if errores:
    with st.expander("⚠️ Consultas que no funcionaron"):
        for err in errores:
            st.warning(err)

# Si no se ha recibido ningún partido, no fabricar contenido.
if not todos:
    st.error(
        "MatchGrind no devolvió partidos utilizables para las "
        "competiciones seleccionadas. Puede ser un problema de cobertura "
        "o de formato/respuesta del endpoint."
    )
    st.markdown(
        "Revisa la documentación: "
        "[MatchGrind Football API](https://www.matchgrind.space/football-api)"
    )
    st.stop()

# Eliminar duplicados entre competiciones por ID.
finales = {}
for p in todos:
    clave = (p["id"], p["competicion"]) if p["id"] else (
        p["competicion"], p["fecha"], p["local"], p["visita"]
    )
    finales[clave] = p

todos = list(finales.values())

def en_rango(p):
    if not p["fecha"]:
        return False
    fecha_local = p["fecha"].astimezone().date()
    return desde <= fecha_local <= hasta

partidos_rango = [p for p in todos if en_rango(p)]
partidos_rango.sort(key=lambda p: p["fecha"] or datetime.max.replace(tzinfo=timezone.utc))

pendientes = [
    p for p in partidos_rango
    if not p["finalizado"] and p["estado"] != "NO DISPONIBLE"
]
resultados = [
    p for p in partidos_rango
    if p["finalizado"] and tiene_marcador(p)
]

tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Partidos",
    "📊 Analizar partido",
    "🧾 Resultados",
    "🔎 Cobertura",
])

with tab1:
    st.markdown("### Partidos en el rango elegido")

    a, b, c = st.columns(3)
    a.metric("Partidos encontrados", len(partidos_rango))
    b.metric("Pendientes / programados", len(pendientes))
    c.metric("Resultados finalizados", len(resultados))

    if not partidos_rango:
        st.info(
            "No hay partidos en el rango seleccionado. Prueba con otras "
            "fechas o comprueba si la competición está cubierta."
        )
    else:
        for p in partidos_rango:
            with st.container(border=True):
                st.caption(p.get("competicion", "Competición desconocida"))
                st.write(texto_partido(p))
                st.caption(f"Estado reportado: {p['estado']}")

with tab2:
    st.markdown("### Selecciona un partido")

    if not pendientes:
        st.info(
            "No se encontraron partidos pendientes en el rango. "
            "Amplía las fechas o selecciona otra competición."
        )
    else:
        opciones = {
            f"{p['competicion']} | {texto_partido(p)}": p
            for p in pendientes
        }

        etiqueta = st.selectbox("Partido", list(opciones.keys()))
        elegido = opciones[etiqueta]

        local = elegido["local"]
        visitante = elegido["visita"]
        slug = elegido["slug"]

        st.markdown(f"## {local} vs. {visitante}")
        st.write(f"**Competición:** {elegido['competicion']}")
        if elegido["fecha"]:
            st.write(
                "**Fecha:** "
                + elegido["fecha"].astimezone().strftime("%d-%m-%Y %H:%M")
            )

        # Solo comparar partidos de la misma competición, para no
        # presentar como completa una forma que no se ha consultado.
        historial_liga = [
            p for p in todos
            if p["slug"] == slug
            and p["fecha"] is not None
            and p["fecha"] < elegido["fecha"]
        ]

        forma_local = resumen_equipo(historial_liga, local, limite=5)
        forma_visitante = resumen_equipo(historial_liga, visitante, limite=5)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"### 🏠 {local}")
            mostrar_resumen("Últimos partidos disponibles", forma_local)
            local_casa = resumen_equipo(
                historial_liga, local, condicion="home", limite=5
            )
            mostrar_resumen("Últimos partidos como local", local_casa)

        with col2:
            st.markdown(f"### ✈️ {visitante}")
            mostrar_resumen("Últimos partidos disponibles", forma_visitante)
            visita_fuera = resumen_equipo(
                historial_liga, visitante, condicion="away", limite=5
            )
            mostrar_resumen("Últimos partidos como visitante", visita_fuera)

        st.divider()
        comparar(forma_local, forma_visitante)

        st.markdown("### Enfrentamientos directos disponibles")
        h2h = [
            p for p in historial_liga
            if {clave_equipo(p["local"]), clave_equipo(p["visita"])}
            == {clave_equipo(local), clave_equipo(visitante)}
            and p["finalizado"] and tiene_marcador(p)
        ]
        h2h.sort(key=lambda p: p["fecha"], reverse=True)

        if h2h:
            filas = [{
                "Fecha": p["fecha"].astimezone().strftime("%d-%m-%Y"),
                "Local": p["local"],
                "Marcador": f'{p["goles_local"]} - {p["goles_visita"]}',
                "Visitante": p["visita"],
            } for p in h2h[:5]]

            st.dataframe(
                pd.DataFrame(filas),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info(
                "No hay enfrentamientos directos disponibles en los "
                "datos recibidos de esta competición."
            )

with tab3:
    st.markdown("### Resultados finalizados en el rango")

    if not resultados:
        st.info("No se encontraron resultados finalizados en estas fechas.")
    else:
        filas = []
        for p in resultados:
            filas.append({
                "Fecha": (
                    p["fecha"].astimezone().strftime("%d-%m-%Y")
                    if p["fecha"] else "Desconocida"
                ),
                "Competición": p.get("competicion", ""),
                "Local": p["local"],
                "Goles local": p["goles_local"],
                "Goles visitante": p["goles_visita"],
                "Visitante": p["visita"],
            })

        st.dataframe(
            pd.DataFrame(filas),
            hide_index=True,
            use_container_width=True,
        )

with tab4:
    st.markdown("### Cobertura recibida desde MatchGrind")

    if cobertura:
        st.dataframe(
            pd.DataFrame(cobertura),
            hide_index=True,
            use_container_width=True,
        )

    st.write(
        "Esta tabla refleja lo que devolvió la API durante esta consulta. "
        "Una competición con pocos partidos puede tener cobertura limitada "
        "o una temporada incompleta."
    )

    st.markdown(
        "[Documentación oficial de MatchGrind](https://www.matchgrind.space/football-api)"
    )

st.divider()
st.caption(
    "CanchaLab IA · Datos consultados desde MatchGrind. "
    "Los resultados y promedios describen datos disponibles; "
    "no garantizan resultados futuros."
)
