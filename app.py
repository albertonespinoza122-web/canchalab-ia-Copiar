
import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta, datetime
from collections import defaultdict

# =========================================================
# CANCHALAB IA - Aplicación de análisis futbolístico
# Fuente de datos: MatchGrind Football API
# =========================================================

st.set_page_config(
    page_title="CanchaLab IA",
    page_icon="⚽",
    layout="wide",
)

BASE_URL = "https://matchgrind.space/get/soccer"
TIMEOUT = 20

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⚽ CanchaLab IA")
st.caption(
    "Análisis de partidos, resultados y forma reciente. "
    "Los datos dependen de la cobertura de la API."
)


# =========================================================
# FUNCIONES PARA CONSULTAR LA API
# =========================================================

def consultar_api(endpoint, params=None):
    """Consulta la API y devuelve el JSON recibido."""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    respuesta = requests.get(
        url,
        params=params or {},
        timeout=TIMEOUT,
        headers={"Accept": "application/json"},
    )

    respuesta.raise_for_status()

    try:
        return respuesta.json()
    except ValueError as exc:
        raise ValueError(
            f"La API no devolvió JSON válido. URL: {respuesta.url}"
        ) from exc


def buscar_lista_partidos(objeto, profundidad=0):
    """
    Busca listas de partidos en distintas estructuras JSON.
    Admite respuestas como:
    - una lista directa
    - {'data': [...]}
    - {'events': [...]}
    - {'fixtures': [...]}
    - {'matches': [...]}
    """
    if profundidad > 6:
        return []

    if isinstance(objeto, list):
        if not objeto:
            return []

        diccionarios = [
            elemento for elemento in objeto
            if isinstance(elemento, dict)
        ]

        if diccionarios and any(
            any(
                clave in elemento
                for clave in (
                    "homeTeam", "awayTeam", "home", "away",
                    "competitors", "teams", "date", "status",
                    "home_team", "away_team",
                )
            )
            for elemento in diccionarios
        ):
            return diccionarios

        for elemento in objeto:
            resultado = buscar_lista_partidos(
                elemento, profundidad + 1
            )
            if resultado:
                return resultado

        return []

    if isinstance(objeto, dict):
        claves_preferidas = [
            "matches", "fixtures", "events",
            "results", "data", "items", "response",
            "games", "schedule",
        ]

        for clave in claves_preferidas:
            if clave in objeto:
                resultado = buscar_lista_partidos(
                    objeto[clave], profundidad + 1
                )
                if resultado:
                    return resultado

        for valor in objeto.values():
            if isinstance(valor, (dict, list)):
                resultado = buscar_lista_partidos(
                    valor, profundidad + 1
                )
                if resultado:
                    return resultado

    return []


def primer_valor(diccionario, claves, predeterminado=None):
    """Devuelve el primer valor existente entre varias claves."""
    if not isinstance(diccionario, dict):
        return predeterminado

    for clave in claves:
        valor = diccionario.get(clave)
        if valor is not None and valor != "":
            return valor

    return predeterminado


def nombre_equipo(objeto):
    """Extrae el nombre de un equipo desde formatos comunes."""
    if isinstance(objeto, str):
        return objeto

    if isinstance(objeto, dict):
        valor = primer_valor(
            objeto,
            ["displayName", "name", "shortName", "teamName", "title"],
        )
        if valor is not None:
            return str(valor)

    return None


def extraer_equipos(partido):
    """Encuentra los equipos local y visitante."""
    local = primer_valor(
        partido,
        ["homeTeam", "home_team", "home", "local", "teamHome"],
    )
    visitante = primer_valor(
        partido,
        ["awayTeam", "away_team", "away", "visitor", "teamAway"],
    )

    if isinstance(partido.get("competitors"), list):
        competidores = partido["competitors"]

        for equipo in competidores:
            if not isinstance(equipo, dict):
                continue

            lado = str(
                primer_valor(
                    equipo,
                    ["homeAway", "qualifier", "side", "location"],
                    "",
                )
            ).lower()

            if lado in ("home", "local", "home team"):
                local = equipo
            elif lado in ("away", "visitor", "away team", "visiting"):
                visitante = equipo

    if isinstance(partido.get("teams"), list):
        equipos = partido["teams"]

        if len(equipos) >= 2 and not local and not visitante:
            local, visitante = equipos[0], equipos[1]

    return nombre_equipo(local), nombre_equipo(visitante)


def extraer_goles(partido):
    """Extrae los goles desde distintas estructuras posibles."""
    local = None
    visitante = None

    marcador = partido.get("score")

    if isinstance(marcador, dict):
        local = primer_valor(
            marcador,
            ["home", "homeScore", "home_score", "local"],
        )
        visitante = primer_valor(
            marcador,
            ["away", "awayScore", "away_score", "visitor"],
        )

    home_obj = primer_valor(
        partido, ["homeTeam", "home_team", "home", "local"]
    )
    away_obj = primer_valor(
        partido, ["awayTeam", "away_team", "away", "visitor"]
    )

    if local is None and isinstance(home_obj, dict):
        local = primer_valor(
            home_obj, ["score", "goals", "scoreValue"]
        )

    if visitante is None and isinstance(away_obj, dict):
        visitante = primer_valor(
            away_obj, ["score", "goals", "scoreValue"]
        )

    if local is None:
        local = primer_valor(
            partido,
            ["homeScore", "home_score", "scoreHome", "localScore"],
        )

    if visitante is None:
        visitante = primer_valor(
            partido,
            ["awayScore", "away_score", "scoreAway", "visitorScore"],
        )

    def convertir(valor):
        if valor is None or valor == "":
            return None
        try:
            return int(valor)
        except (ValueError, TypeError):
            return None

    return convertir(local), convertir(visitante)


def extraer_fecha(partido):
    valor = primer_valor(
        partido,
        [
            "date", "startDate", "startTime", "kickoff",
            "kickoffTime", "utcDate", "timestamp",
        ],
    )

    if valor is None:
        return None

    try:
        if isinstance(valor, (int, float)):
            # Algunas API entregan timestamps en milisegundos.
            if valor > 10_000_000_000:
                valor = valor / 1000
            return datetime.fromtimestamp(valor).date()

        texto = str(valor).strip()

        if texto.isdigit():
            numero = int(texto)
            if numero > 10_000_000_000:
                numero = numero / 1000
            return datetime.fromtimestamp(numero).date()

        return date.fromisoformat(texto[:10])

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def extraer_estado(partido):
    estado = primer_valor(
        partido,
        ["status", "state", "matchStatus", "statusName"],
        "Sin información",
    )

    if isinstance(estado, dict):
        estado = primer_valor(
            estado,
            ["description", "name", "detail", "type", "shortName"],
            "Sin información",
        )

    return str(estado)


def normalizar_partido(partido, liga_nombre):
    local, visitante = extraer_equipos(partido)

    if not local or not visitante:
        return None

    goles_local, goles_visitante = extraer_goles(partido)
    fecha_partido = extraer_fecha(partido)
    estado = extraer_estado(partido)

    return {
        "Fecha": fecha_partido,
        "Competición": liga_nombre,
        "Local": local,
        "Visitante": visitante,
        "Goles local": goles_local,
        "Goles visitante": goles_visitante,
        "Estado": estado,
        "_original": partido,
    }


# =========================================================
# CATÁLOGO DE COMPETICIONES
# =========================================================

@st.cache_data(ttl=1800, show_spinner=False)
def cargar_ligas():
    """
    Intenta cargar las competiciones disponibles desde la API.
    Si falla el catálogo, utiliza una lista de respaldo.
    """
    respaldo = [
        {"slug": "eng.1", "name": "Premier League"},
        {"slug": "esp.1", "name": "LaLiga"},
        {"slug": "ger.1", "name": "Bundesliga"},
        {"slug": "ita.1", "name": "Serie A"},
        {"slug": "fra.1", "name": "Ligue 1"},
        {"slug": "uefa.champions", "name": "Champions League"},
        {"slug": "conmebol.libertadores", "name": "Copa Libertadores"},
        {"slug": "chi.1", "name": "Primera División de Chile"},
    ]

    try:
        payload = consultar_api(
            "leagues",
            {"kind": "club", "available": "true"},
        )

        registros = []

        def recorrer(objeto):
            if isinstance(objeto, list):
                for elemento in objeto:
                    recorrer(elemento)

            elif isinstance(objeto, dict):
                slug = primer_valor(
                    objeto,
                    ["slug", "leagueSlug", "id", "leagueId"],
                )
                nombre = primer_valor(
                    objeto,
                    ["name", "displayName", "leagueName", "title"],
                )

                if slug is not None and nombre is not None:
                    registros.append(
                        {
                            "slug": str(slug),
                            "name": str(nombre),
                        }
                    )
                else:
                    for valor in objeto.values():
                        if isinstance(valor, (list, dict)):
                            recorrer(valor)

        recorrer(payload)

        unicas = {}
        for liga in registros:
            unicas[liga["slug"]] = liga

        if unicas:
            return sorted(
                unicas.values(),
                key=lambda liga: liga["name"].lower(),
            ), None

        return respaldo, (
            "La API respondió, pero no reconocí el formato del catálogo."
        )

    except Exception as error:
        return respaldo, str(error)


# =========================================================
# PARTIDOS Y CACHÉ
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_partidos(slug, fecha_desde, fecha_hasta):
    desde_api = fecha_desde.strftime("%Y%m%d")
    hasta_api = fecha_hasta.strftime("%Y%m%d")

    payload = consultar_api(
        f"{slug}/fixtures",
        {
            "status": "all",
            "from": desde_api,
            "to": hasta_api,
        },
    )

    return payload


# =========================================================
# ANÁLISIS DE FORMA
# =========================================================

def parece_finalizado(estado, goles_local, goles_visitante):
    texto = estado.lower()

    estados_finales = [
        "finished", "final", "full time", "ft", "ended",
        "complete", "completed", "terminado", "finalizado",
    ]

    if any(palabra in texto for palabra in estados_finales):
        return goles_local is not None and goles_visitante is not None

    return False


def calcular_forma(partidos, equipo):
    """
    Calcula los últimos resultados encontrados en los datos disponibles.
    No asume que la API tenga toda la historia del equipo.
    """
    historial = []

    for partido in partidos:
        if not parece_finalizado(
            partido["Estado"],
            partido["Goles local"],
            partido["Goles visitante"],
        ):
            continue

        local = partido["Local"]
        visitante = partido["Visitante"]

        if equipo != local and equipo != visitante:
            continue

        gl = partido["Goles local"]
        gv = partido["Goles visitante"]

        if equipo == local:
            goles_favor, goles_contra = gl, gv
        else:
            goles_favor, goles_contra = gv, gl

        if goles_favor > goles_contra:
            resultado = "G"
        elif goles_favor < goles_contra:
            resultado = "P"
        else:
            resultado = "E"

        historial.append(
            {
                "Fecha": partido["Fecha"],
                "Resultado": resultado,
                "GF": goles_favor,
                "GC": goles_contra,
            }
        )

    historial.sort(
        key=lambda fila: fila["Fecha"] or date.min
    )

    return historial[-5:]


def resumen_forma(historial):
    if not historial:
        return "Sin datos suficientes", 0, 0, 0

    victorias = sum(x["Resultado"] == "G" for x in historial)
    empates = sum(x["Resultado"] == "E" for x in historial)
    derrotas = sum(x["Resultado"] == "P" for x in historial)
    puntos = victorias * 3 + empates

    forma = " - ".join(x["Resultado"] for x in historial)

    return forma, puntos, victorias, empates, derrotas


# =========================================================
# INTERFAZ
# =========================================================

with st.sidebar:
    st.header("⚙️ Configuración")

    fecha_hasta = st.date_input(
        "Hasta la fecha",
        value=date.today(),
    )

    fecha_desde = st.date_input(
        "Desde la fecha",
        value=date.today() - timedelta(days=120),
    )

    st.caption(
        "Para analizar forma reciente, conviene consultar varios "
        "meses de partidos. La cobertura histórica depende de la API."
    )

    actualizar = st.button(
        "🔄 Actualizar datos",
        use_container_width=True,
    )

if fecha_desde > fecha_hasta:
    st.error("La fecha inicial no puede ser posterior a la fecha final.")
    st.stop()

if actualizar:
    st.cache_data.clear()

with st.spinner("Buscando competiciones disponibles..."):
    ligas, error_catalogo = cargar_ligas()

if error_catalogo:
    st.warning(
        "No pude cargar el catálogo automático de competiciones. "
        "Estoy mostrando una lista de respaldo. Algunas ligas podrían "
        "no estar disponibles en MatchGrind."
    )

opciones_ligas = {
    f'{liga["name"]} ({liga["slug"]})': liga
    for liga in ligas
}

seleccion_nombres = st.multiselect(
    "Selecciona las competiciones",
    options=list(opciones_ligas.keys()),
    default=[
        nombre
        for nombre in opciones_ligas
        if any(
            palabra in nombre.lower()
            for palabra in ["premier league", "laliga"]
        )
    ][:2],
)

col1, col2, col3 = st.columns(3)
col1.metric("Competiciones disponibles", len(ligas))
col2.metric("Inicio del análisis", fecha_desde.strftime("%d-%m-%Y"))
col3.metric("Fin del análisis", fecha_hasta.strftime("%d-%m-%Y"))

if not seleccion_nombres:
    st.info("Selecciona al menos una competición para comenzar.")
    st.stop()

partidos_normalizados = []
errores = []
respuestas_vacias = []

with st.spinner("Descargando partidos..."):
    for nombre_seleccionado in seleccion_nombres:
        liga = opciones_ligas[nombre_seleccionado]

        try:
            payload = cargar_partidos(
                liga["slug"],
                fecha_desde,
                fecha_hasta,
            )

            registros = buscar_lista_partidos(payload)

            if not registros:
                respuestas_vacias.append(
                    {
                        "Competición": liga["name"],
                        "Slug": liga["slug"],
                        "Respuesta": payload,
                    }
                )
                continue

            for registro in registros:
                partido = normalizar_partido(
                    registro,
                    liga["name"],
                )

                if partido is None:
                    continue

                if partido["Fecha"] is not None:
                    if not fecha_desde <= partido["Fecha"] <= fecha_hasta:
                        continue

                partidos_normalizados.append(partido)

        except Exception as error:
            errores.append(
                f'{liga["name"]} ({liga["slug"]}): {error}'
            )

# Elimina duplicados por competición, fecha y equipos.
unicos = {}

for partido in partidos_normalizados:
    clave = (
        partido["Competición"],
        partido["Fecha"],
        partido["Local"],
        partido["Visitante"],
    )
    unicos[clave] = partido

partidos_normalizados = list(unicos.values())
partidos_normalizados.sort(
    key=lambda p: (
        p["Fecha"] or date.min,
        p["Competición"],
        p["Local"],
    ),
    reverse=True,
)

if errores:
    with st.expander("⚠️ Errores al consultar algunas competiciones"):
        for error in errores:
            st.error(error)

if not partidos_normalizados:
    st.error(
        "No pude obtener partidos utilizables para las competiciones "
        "seleccionadas. Esto puede deberse a que la liga no está cubierta, "
        "la API está temporalmente caída o la respuesta usa otro formato."
    )

    st.subheader("Diagnóstico")

    st.write("Endpoint base:", BASE_URL)
    st.write("Competiciones seleccionadas:", seleccion_nombres)

    if respuestas_vacias:
        st.write("La API respondió, pero no encontré partidos reconocibles.")

        for vacia in respuestas_vacias:
            with st.expander(
                f'{vacia["Competición"]} — respuesta recibida'
            ):
                st.json(vacia["Respuesta"])

    try:
        meta = consultar_api("meta")
        with st.expander("Respuesta del endpoint meta"):
            st.json(meta)
    except Exception as error:
        st.warning(f"No pude consultar /meta: {error}")

    try:
        catalogo = consultar_api(
            "leagues",
            {"kind": "club", "available": "true"},
        )
        with st.expander("Respuesta original del catálogo de ligas"):
            st.json(catalogo)
    except Exception as error:
        st.warning(f"No pude consultar el catálogo: {error}")

    st.info(
        "Si aparece un JSON en el diagnóstico, envíame una captura. "
        "Con esa respuesta podemos adaptar el lector al formato real."
    )
    st.stop()


# =========================================================
# RESUMEN DE PARTIDOS
# =========================================================

st.success(
    f"Se encontraron {len(partidos_normalizados)} partidos utilizables."
)

datos_tabla = []

for partido in partidos_normalizados:
    gl = partido["Goles local"]
    gv = partido["Goles visitante"]

    marcador = (
        f"{gl} - {gv}"
        if gl is not None and gv is not None
        else "Sin marcador"
    )

    datos_tabla.append(
        {
            "Fecha": (
                partido["Fecha"].strftime("%d-%m-%Y")
                if partido["Fecha"]
                else "Sin fecha"
            ),
            "Competición": partido["Competición"],
            "Local": partido["Local"],
            "Marcador": marcador,
            "Visitante": partido["Visitante"],
            "Estado": partido["Estado"],
        }
    )

df = pd.DataFrame(datos_tabla)

st.subheader("📅 Partidos encontrados")

filtro_texto = st.text_input(
    "Buscar equipo o competición",
    placeholder="Ej.: Arsenal, Colo-Colo, Premier...",
)

if filtro_texto:
    mascara = df.apply(
        lambda fila: fila.astype(str).str.contains(
            filtro_texto,
            case=False,
            regex=False,
        ).any(),
        axis=1,
    )
    df_mostrar = df[mascara]
else:
    df_mostrar = df

st.dataframe(
    df_mostrar,
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "⬇️ Descargar partidos en CSV",
    data=df_mostrar.to_csv(index=False).encode("utf-8-sig"),
    file_name="canchalab_partidos.csv",
    mime="text/csv",
)


# =========================================================
# COMPARADOR DE EQUIPOS
# =========================================================

st.divider()
st.subheader("🧠 Comparador de equipos")

equipos = sorted(
    {
        equipo
        for partido in partidos_normalizados
        for equipo in (partido["Local"], partido["Visitante"])
        if equipo
    }
)

if len(equipos) >= 2:
    c1, c2 = st.columns(2)

    with c1:
        equipo_a = st.selectbox(
            "Equipo A",
            equipos,
            index=0,
        )

    with c2:
        indice_b = 1 if len(equipos) > 1 else 0
        equipo_b = st.selectbox(
            "Equipo B",
            equipos,
            index=indice_b,
        )

    forma_a = calcular_forma(partidos_normalizados, equipo_a)
    forma_b = calcular_forma(partidos_normalizados, equipo_b)

    def metricas_equipo(nombre, historial):
        if not historial:
            return {
                "Equipo": nombre,
                "Partidos encontrados": 0,
                "Forma reciente": "Sin datos",
                "Victorias": 0,
                "Empates": 0,
                "Derrotas": 0,
                "Goles a favor": 0,
                "Goles en contra": 0,
                "Puntos de referencia": 0,
            }

        forma, puntos, victorias, empates, derrotas = resumen_forma(
            historial
        )

        return {
            "Equipo": nombre,
            "Partidos encontrados": len(historial),
            "Forma reciente": forma,
            "Victorias": victorias,
            "Empates": empates,
            "Derrotas": derrotas,
            "Goles a favor": sum(x["GF"] for x in historial),
            "Goles en contra": sum(x["GC"] for x in historial),
            "Puntos de referencia": puntos,
        }

    comparacion = pd.DataFrame(
        [
            metricas_equipo(equipo_a, forma_a),
            metricas_equipo(equipo_b, forma_b),
        ]
    )

    st.dataframe(
        comparacion,
        use_container_width=True,
        hide_index=True,
    )

    if forma_a and forma_b:
        st.caption(
            "G = victoria, E = empate, P = derrota. "
            "La forma utiliza los últimos partidos finalizados que la API "
            "devolvió dentro del período seleccionado; no garantiza que "
            "sean los cinco partidos oficiales más recientes."
        )

    enfrentamientos = [
        partido
        for partido in partidos_normalizados
        if {
            partido["Local"].lower(),
            partido["Visitante"].lower(),
        } == {
            equipo_a.lower(),
            equipo_b.lower(),
        }
    ]

    st.markdown("#### Historial directo disponible")

    if enfrentamientos:
        enfrentamientos_df = pd.DataFrame(
            [
                {
                    "Fecha": (
                        p["Fecha"].strftime("%d-%m-%Y")
                        if p["Fecha"]
                        else "Sin fecha"
                    ),
                    "Local": p["Local"],
                    "Goles local": p["Goles local"],
                    "Goles visitante": p["Goles visitante"],
                    "Visitante": p["Visitante"],
                    "Estado": p["Estado"],
                }
                for p in sorted(
                    enfrentamientos,
                    key=lambda x: x["Fecha"] or date.min,
                    reverse=True,
                )
            ]
        )

        st.dataframe(
            enfrentamientos_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "No encontré enfrentamientos directos entre ambos equipos "
            "en los datos descargados."
        )

else:
    st.info(
        "No hay suficientes equipos en los partidos descargados "
        "para activar el comparador."
    )


# =========================================================
# NOTA FINAL
# =========================================================

st.divider()
st.caption(
    "CanchaLab IA es una herramienta informativa. Las estadísticas "
    "dependen de la disponibilidad y calidad de la fuente. "
    "No garantiza resultados deportivos ni ganancias en apuestas."
)
