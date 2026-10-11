import os
import socket

import altair as alt
import pandas as pd
import psycopg2
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PAISES = {
    "Korea, Rep.": "Corea del Sur",
    "Germany": "Alemania",
    "Mexico": "México",
    "Spain": "España",
    "France": "Francia",
    "Canada": "Canadá",
    "United Kingdom": "Reino Unido",
    "Japan": "Japón",
    "Brazil": "Brasil",
    "United States": "Estados Unidos",
}

INDICADORES = {
    "Trade_pct_GDP": "Comercio total (% del PIB)",
    "Exports_pct_GDP": "Exportaciones (% del PIB)",
    "Imports_pct_GDP": "Importaciones (% del PIB)",
    "GDP_per_capita": "PIB per cápita (US$)",
}


def host_db():
    try:
        with open("/proc/net/route") as f:
            for linea in f.readlines()[1:]:
                campos = linea.split()
                if campos[1] == "00000000":
                    return socket.inet_ntoa(bytes.fromhex(campos[2])[::-1])
    except OSError:
        pass
    return os.getenv("DB_HOST", "localhost")


@st.cache_data(ttl=300)
def cargar_datos():
    conn = psycopg2.connect(
        host=host_db(),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT country_name, country_code, indicator, year, value FROM datos_comercio")
            filas = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(filas, columns=["pais", "codigo", "indicador", "anio", "valor"])
    df["valor"] = df["valor"].astype(float)
    df["pais"] = df["pais"].replace(PAISES)
    return df


st.set_page_config(page_title="Global Trade Automation Hub", layout="wide")
st.title("Global Trade Automation Hub")
st.caption("Consulta de comercio exterior con datos del Banco Mundial, 2015 a 2024")

df = cargar_datos()

lista_paises = sorted(df["pais"].unique())
col1, col2 = st.columns(2)
pais = col1.selectbox("País", lista_paises, index=lista_paises.index("Colombia"))
etiqueta = col2.selectbox("Indicador", list(INDICADORES.values()))
codigo = [k for k, v in INDICADORES.items() if v == etiqueta][0]

codigo_pais = df.loc[df["pais"] == pais, "codigo"].iloc[0]
d = df[df["indicador"] == codigo]
ultimo = int(d["anio"].max())
actual = d[(d["pais"] == pais) & (d["anio"] == ultimo)]["valor"].iloc[0]
previo = d[(d["pais"] == pais) & (d["anio"] == ultimo - 1)]["valor"].iloc[0]
ranking = d[d["anio"] == ultimo].sort_values("valor", ascending=False).reset_index(drop=True)
puesto = int(ranking.index[ranking["pais"] == pais][0]) + 1

m1, m2, m3 = st.columns(3)
m1.metric(f"Valor {ultimo}", f"{actual:,.1f}", f"{actual - previo:+.1f} frente a {ultimo - 1}")
m2.metric("Puesto", f"{puesto} de {len(ranking)}")
m3.metric("Líder", ranking.iloc[0]["pais"], f"{ranking.iloc[0]['valor']:,.1f}", delta_color="off")

g1, g2 = st.columns(2)

serie = d[d["pais"] == pais].sort_values("anio")
g1.subheader(f"Tendencia de {pais}")
g1.line_chart(serie.set_index("anio")["valor"])

g2.subheader(f"Ranking {ultimo}")
barras = (
    alt.Chart(ranking)
    .mark_bar()
    .encode(
        x=alt.X("valor:Q", title=etiqueta),
        y=alt.Y("pais:N", sort="-x", title=None),
        color=alt.condition(alt.datum.pais == pais, alt.value("#F28C28"), alt.value("#B8C4D6")),
        tooltip=["pais", "valor"],
    )
)
g2.altair_chart(barras, use_container_width=True)


st.divider()
st.subheader("Solicitar reporte")
st.caption("Envía la consulta actual al flujo de n8n, que calcula el resumen y registra la solicitud en la base de datos.")

if st.button("Solicitar reporte", type="primary"):
    url = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/solicitar-reporte")
    carga = {
        "codigo_pais": codigo_pais,
        "pais": pais,
        "indicador": codigo,
        "indicador_nombre": etiqueta,
    }
    try:
        resp = requests.post(url, json=carga, timeout=15)
        resp.raise_for_status()
        resultado = resp.json()
        if isinstance(resultado, list):
            resultado = resultado[0]
    except Exception as e:
        st.error(f"No se pudo enviar la solicitud: {e}")
    else:
        st.success(f"Solicitud {resultado['id']} registrada con estado {resultado['estado']}")
        st.write(resultado["resumen"])
