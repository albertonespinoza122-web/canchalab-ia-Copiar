import math
from datetime import datetime
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CanchaLab IA", page_icon="⚽", layout="wide")

SOURCE = "https://raw.githubusercontent.com/hudl/open-data/master/data/competitions.json"
BASE = "https://raw.githubusercontent.com/hudl/open-data/master/data/matches/{competition_id}/{season_id}.json"

st.markdown("""
<style>
.main {background: #0b1220;}
[data-testid="stAppViewContainer"] {background: radial-gradient(circle at 10% 0%, #142b3b 0%, #0b1220 44%, #080d17 100%); color: #f4f7fb;}
[data-testid="stSidebar"] {background: #101a29;}
.block-container {padding-top: 1.8rem; max-width: 1250px;}
.hero {padding: 1.3rem 1.5rem; border: 1px solid #2b4354; border-radius: 18px; background: linear-gradient(120deg, #142e3c, #111b2c); margin-bottom: 1rem;}
.eyebrow {text-transform: uppercase; letter-spacing: .16em; color: #70e1b3; font-size: .75rem; font-weight: 700;}
.hero h1 {margin: .25rem 0; font-size: 2.35rem; color: #f6fbff;}
.hero p {color: #b7c8d5; margin-bottom: 0;}
.smallnote {font-size: .85rem; color: #9db0c0;}
</style>
<div class="hero"><div class="eyebrow">FOOTBALL INTELLIGENCE · PROTOTIPO GRATUITO</div><h1>⚽ CanchaLab IA</h1><p>Datos históricos verificables · probabilidades calculadas · sin cuotas como entrada del modelo</p></div>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600, show_spinner=False)
def load_competitions():
    r = requests.get(SOURCE, timeout=25)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=3600, show_spinner=False)
def load_matches(competition_id, season_id):
    url = BASE.format(competition_id=competition_id, season_id=season_id)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    raw = r.json()
    rows = []
    for m in raw:
        home = (m.get("home_team") or {}).get("home_team_name", "Local")
        away = (m.get("away_team") or {}).get("away_team_name", "Visita")
        hs, aws = m.get("home_score"), m.get("away_score")
        if hs is None or aws is None:
            continue
        rows.append({
            "date": m.get("match_date", ""), "home": home, "away": away,
            "hg": int(hs), "ag": int(aws),
            "competition": (m.get("competition") or {}).get("competition_name", ""),
            "season": (m.get("season") or {}).get("season_name", ""),
            "match_id": m.get("match_id")
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)
    return df

def team_history(df, team, before=None, n=8):
    hist = df[(df.home == team) | (df.away == team)].copy()
    if before is not None:
        hist = hist[hist.date < before]
    hist = hist.tail(n)
    if hist.empty:
        return None
    gf, ga = [], []
    for _, r in hist.iterrows():
        if r.home == team:
            gf.append(r.hg); ga.append(r.ag)
        else:
            gf.append(r.ag); ga.append(r.hg)
    return {"played": len(hist), "gf": sum(gf)/len(gf), "ga": sum(ga)/len(ga), "wins": sum(a>b for a,b in zip(gf,ga)), "draws": sum(a==b for a,b in zip(gf,ga)), "losses": sum(a<b for a,b in zip(gf,ga))}

def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def prediction_probs(lh, la, max_goals=8):
    ph = [poisson(i, lh) for i in range(max_goals+1)]
    pa = [poisson(i, la) for i in range(max_goals+1)]
    home = draw = away = 0.0
    scores = []
    for i, p1 in enumerate(ph):
        for j, p2 in enumerate(pa):
            p = p1*p2
            if i > j: home += p
            elif i == j: draw += p
            else: away += p
            scores.append((p, i, j))
    total = home+draw+away
    return home/total, draw/total, away/total, sorted(scores, reverse=True)[:3]

def estimate_lambdas(df, home_team, away_team, n=8):
    h = team_history(df, home_team, n=n)
    a = team_history(df, away_team, n=n)
    if not h or not a:
        return None
    league_home = max(0.2, df.hg.mean())
    league_away = max(0.2, df.ag.mean())
    # Regularización: combina forma reciente con promedio global de la competición.
    home_attack = 0.65*h["gf"] + 0.35*league_home
    away_defence = 0.65*a["ga"] + 0.35*league_home
    away_attack = 0.65*a["gf"] + 0.35*league_away
    home_defence = 0.65*h["ga"] + 0.35*league_away
    lh = max(0.15, (home_attack + away_defence)/2)
    la = max(0.15, (away_attack + home_defence)/2)
    return lh, la, h, a

def run_backtest(df, n=8, limit=250):
    # Walk-forward simple: cada partido se estima usando solo partidos anteriores.
    data = df.tail(limit).copy()
    outcomes, predicted, brier = [], [], []
    for idx, row in data.iterrows():
        prior = df[df.date < row.date]
        if len(prior) < 12:
            continue
        est = estimate_lambdas(prior, row.home, row.away, n=n)
        if not est:
            continue
        p1, px, p2, _ = prediction_probs(est[0], est[1])
        actual = 0 if row.hg > row.ag else (1 if row.hg == row.ag else 2)
        probs = [p1, px, p2]
        predicted.append(int(max(range(3), key=lambda k: probs[k])))
        outcomes.append(actual)
        target = [1 if actual == k else 0 for k in range(3)]
        brier.append(sum((probs[k]-target[k])**2 for k in range(3)))
    if not outcomes:
        return None
    acc = sum(p == y for p,y in zip(predicted,outcomes))/len(outcomes)
    return {"n":len(outcomes), "accuracy":acc, "brier":sum(brier)/len(brier)}

with st.sidebar:
    st.header("⚙️ Configuración")
    st.caption("Solo datos públicos históricos de StatsBomb Open Data.")
    st.markdown("[Repositorio oficial de datos ↗](https://github.com/hudl/open-data)")
    recent_n = st.slider("Partidos recientes por equipo", min_value=4, max_value=15, value=8)
    max_backtest = st.slider("Partidos para backtest", min_value=50, max_value=500, value=200, step=50)
    st.divider()
    st.caption("Versión 0.1 · Sin claves API · Sin cuotas de apuestas")

try:
    with st.spinner("Cargando catálogo oficial de competiciones..."):
        competitions = load_competitions()
except Exception as e:
    st.error("No se pudieron cargar los datos de StatsBomb. Comprueba la conexión o inténtalo más tarde.")
    st.caption(f"Detalle técnico: {e}")
    st.stop()

comp_df = pd.DataFrame(competitions)
if comp_df.empty:
    st.error("La fuente no devolvió competiciones.")
    st.stop()
comp_df["label"] = comp_df["competition_name"].astype(str) + " · " + comp_df["season_name"].astype(str) + " · " + comp_df["country_name"].fillna("").astype(str)
comp_df = comp_df.sort_values(["competition_name", "season_name"], ascending=[True, False])
selected = st.selectbox("Competición y temporada", comp_df.index, format_func=lambda i: comp_df.loc[i, "label"])
comp = comp_df.loc[selected]
try:
    with st.spinner("Descargando partidos y preparando estadísticas..."):
        matches = load_matches(int(comp.competition_id), int(comp.season_id))
except Exception as e:
    st.error("No se pudieron cargar los partidos de esta temporada.")
    st.caption(f"Detalle técnico: {e}")
    st.stop()

if matches.empty:
    st.warning("No hay resultados con marcador disponible en esta selección. Prueba otra competición o temporada.")
    st.stop()

c1,c2,c3,c4 = st.columns(4)
c1.metric("Partidos con marcador", f"{len(matches):,}")
c2.metric("Goles por partido", f"{(matches.hg+matches.ag).mean():.2f}")
c3.metric("Promedio local", f"{matches.hg.mean():.2f}")
c4.metric("Promedio visitante", f"{matches.ag.mean():.2f}")

predict_tab, history_tab, test_tab, about_tab = st.tabs(["🔎 Analizar partido", "📚 Historial", "🧪 Validación", "ℹ️ Fuentes y límites"])
with predict_tab:
    st.subheader("Analizador de enfrentamiento")
    teams = sorted(set(matches.home.tolist()+matches.away.tolist()))
    col1,col2 = st.columns(2)
    home_team = col1.selectbox("Equipo local", teams, index=0)
    away_options = [t for t in teams if t != home_team]
    away_team = col2.selectbox("Equipo visitante", away_options, index=min(1, len(away_options)-1))
    if home_team == away_team:
        st.warning("Selecciona dos equipos distintos.")
    else:
        est = estimate_lambdas(matches, home_team, away_team, n=recent_n)
        if not est:
            st.warning("No hay suficientes partidos para calcular una estimación fiable.")
        else:
            lh, la, h, a = est
            p1, px, p2, scores = prediction_probs(lh, la)
            st.markdown("#### Probabilidades estimadas 1X2")
            pcols = st.columns(3)
            pcols[0].metric(f"{home_team} gana", f"{p1:.1%}")
            pcols[1].metric("Empate", f"{px:.1%}")
            pcols[2].metric(f"{away_team} gana", f"{p2:.1%}")
            chart = pd.DataFrame({"Resultado":[home_team+" gana", "Empate", away_team+" gana"], "Probabilidad":[p1,px,p2]}).set_index("Resultado")
            st.bar_chart(chart)
            m1,m2 = st.columns(2)
            m1.metric("Goles esperados · local", f"{lh:.2f}")
            m2.metric("Goles esperados · visita", f"{la:.2f}")
            st.markdown("#### Marcadores más probables")
            st.write(" · ".join([f"**{i}-{j}** ({p:.1%})" for p,i,j in scores]))
            st.markdown("#### Forma reciente utilizada")
            f1,f2 = st.columns(2)
            with f1:
                st.write(f"**{home_team}** · últimos {h['played']} partidos")
                st.write(f"Goles a favor: {h['gf']:.2f} · en contra: {h['ga']:.2f}")
                st.write(f"Balance: {h['wins']} G · {h['draws']} E · {h['losses']} P")
            with f2:
                st.write(f"**{away_team}** · últimos {a['played']} partidos")
                st.write(f"Goles a favor: {a['gf']:.2f} · en contra: {a['ga']:.2f}")
                st.write(f"Balance: {a['wins']} G · {a['draws']} E · {a['losses']} P")
            st.info("Lectura del modelo: estimación estadística basada en goles recientes y promedios de la competición. No incorpora lesiones, alineaciones confirmadas, descanso, viajes, cambios de entrenador ni datos en vivo. No es garantía de resultado.")

with history_tab:
    st.subheader("Resultados históricos de la selección")
    team_filter = st.selectbox("Filtrar por equipo (opcional)", ["Todos"]+teams)
    show = matches.copy()
    if team_filter != "Todos":
        show = show[(show.home == team_filter) | (show.away == team_filter)]
    show = show.sort_values("date", ascending=False).head(100)
    show["Fecha"] = show.date.dt.strftime("%Y-%m-%d")
    show["Marcador"] = show.hg.astype(str)+" - "+show.ag.astype(str)
    st.dataframe(show[["Fecha","home","Marcador","away"]].rename(columns={"home":"Local","away":"Visitante"}), use_container_width=True, hide_index=True)
    st.caption("Se muestran hasta 100 partidos con marcador. La cobertura depende de la competición y temporada disponibles en la fuente abierta.")

with test_tab:
    st.subheader("Prueba retrospectiva (walk-forward)")
    st.write("Compara el resultado más probable del modelo con resultados históricos. Para cada partido intenta usar solo partidos anteriores a su fecha, evitando mirar el futuro en la estimación.")
    if st.button("Ejecutar backtest"):
        with st.spinner("Evaluando resultados históricos..."):
            bt = run_backtest(matches, n=recent_n, limit=max_backtest)
        if not bt:
            st.warning("No hay suficientes partidos previos para validar este modelo en la temporada seleccionada.")
        else:
            b1,b2,b3 = st.columns(3)
            b1.metric("Partidos evaluados", str(bt["n"]))
            b2.metric("Acierto 1X2", f"{bt['accuracy']:.1%}")
            b3.metric("Brier score", f"{bt['brier']:.3f}")
            st.caption("El acierto no basta para juzgar un modelo. Compara el Brier score con una referencia simple y valida en temporadas no usadas para ajustar parámetros. En temporadas cortas, el resultado puede ser inestable.")

with about_tab:
    st.subheader("Qué datos utiliza")
    st.markdown("- **Fuente principal:** StatsBomb Open Data, repositorio público de eventos y partidos de competiciones seleccionadas.")
    st.markdown("- **Estructura:** catálogo de competiciones/temporadas y archivos de partidos con equipos, fecha y marcador.")
    st.markdown("- **Crédito:** si publicas análisis derivados, atribuye los datos a StatsBomb y respeta sus condiciones de uso.")
    st.markdown("- **No es una API en vivo:** el catálogo abierto es selectivo y las actualizaciones son irregulares. Muchas ligas actuales, como la liga chilena actual, no están necesariamente disponibles.")
    st.markdown("- **No se entrena una IA generativa:** la versión inicial aplica un modelo estadístico Poisson con regularización simple. El nombre 'IA' describe el proyecto; todavía no es un sistema avanzado de aprendizaje automático.")
    st.markdown("- **No incluye por ahora:** alineaciones actuales, lesiones, clima, xG universal, cuotas, noticias ni una base completa de todas las ligas.")
    st.markdown("- **Uso responsable:** las probabilidades son estimaciones inciertas. No uses este prototipo como garantía ni como motivo para apostar dinero que necesitas para gastos esenciales.")
    st.markdown("[Datos oficiales StatsBomb Open Data](https://github.com/hudl/open-data) · [Guía de despliegue gratis en Streamlit](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)")

st.divider()
st.markdown('<p class="smallnote">CanchaLab IA · Prototipo educativo · Modelo no profesional · Datos históricos sujetos a disponibilidad de la fuente.</p>', unsafe_allow_html=True)
