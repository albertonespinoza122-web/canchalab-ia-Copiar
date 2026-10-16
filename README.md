# CanchaLab IA — fútbol, versión 0.1

Aplicación Streamlit gratuita para explorar partidos históricos de StatsBomb Open Data, estimar probabilidades 1X2 con un modelo Poisson sencillo y hacer un backtest retrospectivo.

## No necesitas instalar nada en tu computador

### Publicar gratis desde el navegador del iPhone o Mac

1. Crea una cuenta en https://github.com/ si aún no tienes una.
2. En GitHub, pulsa **+** → **New repository**.
3. Ponle `canchalab-ia`, selecciona **Public** (necesario para la ruta más sencilla) y crea el repositorio.
4. Dentro del repositorio, pulsa **Add file** → **Upload files**.
5. Sube los tres archivos de esta carpeta: `app.py`, `requirements.txt` y `README.md`. Pulsa **Commit changes**.
6. Abre https://share.streamlit.io/ e inicia sesión con GitHub.
7. Pulsa **Create app** y selecciona el repositorio `canchalab-ia`, rama `main` y archivo principal `app.py`.
8. Pulsa **Deploy**. Espera a que termine. Streamlit te asignará una URL pública terminada en `streamlit.app`.

## Qué hace

- Descarga el catálogo público de competiciones y temporadas de StatsBomb.
- Descarga los marcadores disponibles para la selección elegida.
- Estima goles esperados con forma reciente y promedio de la competición.
- Calcula probabilidades 1X2 mediante distribuciones de Poisson.
- Muestra marcadores probables y una prueba retrospectiva sencilla.

## Límites importantes

- No es un modelo de aprendizaje automático entrenado ni una IA generativa; es una primera base estadística.
- StatsBomb Open Data cubre solo competiciones y temporadas seleccionadas. No garantiza partidos actuales ni datos de la liga chilena.
- No utiliza alineaciones actuales, lesiones, clima, noticias ni cuotas.
- Las probabilidades son estimaciones, no garantías. El backtest es exploratorio y debe mejorarse antes de confiar en el modelo.
- La app requiere conexión a internet para cargar los datos. El alojamiento gratuito puede dormir, limitar recursos o cambiar sus condiciones.

## Datos y atribución

Fuente: [StatsBomb Open Data](https://github.com/hudl/open-data). Si publicas o compartes análisis derivados, atribuye la fuente a StatsBomb y revisa los términos de uso del repositorio.

## Privacidad

Esta app no pide ni almacena datos personales del usuario y no necesita claves API.
