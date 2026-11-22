from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import requests
import streamlit as st
from PIL import Image

BASE = Path(__file__).parent
ICON = Image.open(BASE / "icon.png")

st.set_page_config(
    page_title="Corporación DECA - Monto a pagar",
    page_icon=ICON,
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 480px; padding-top: 1rem; padding-bottom: 2rem;}
    #MainMenu, footer {visibility: hidden;}
    .total {background:#fff4e0; border:2px solid #ff9b00; border-radius:16px;
            padding:16px; text-align:center; margin:10px 0;}
    .total small {color:#6b5a3a; font-size:14px;}
    .total .big {font-size:36px; font-weight:800; color:#14181f; overflow-wrap:anywhere;}
    .chip {background:#fff; border:1px solid #e3d5bd; border-radius:12px;
           padding:8px 4px; text-align:center;}
    .chip small {display:block; color:#7a6a4a; font-size:12px;}
    .chip b {font-size:17px; color:#14181f;}
    .chip .gap {color:#b86e00; font-weight:700; margin-top:2px;}
    @media (prefers-color-scheme: dark) {
      .total {background:#2a2113; border-color:#ff9b00;}
      .total small {color:#d8c39b;} .total .big {color:#fff;}
      .chip {background:#1a1f26; border-color:#3a3322;}
      .chip small {color:#b9a77e;} .chip b {color:#fff;}
      .chip .gap {color:#ffb84d;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- tasas ----
TZ = ZoneInfo("America/Caracas")


def periodo_bcv():
    """Cambia una vez al día, a las 12:00 (hora de Venezuela)."""
    ahora = datetime.now(TZ)
    corte = ahora.replace(hour=12, minute=0, second=0, microsecond=0)
    return (ahora if ahora >= corte else ahora - timedelta(days=1)).date().isoformat()


@st.cache_data(show_spinner=False)
def _bcv(code: str, periodo: str):
    """Tasa BCV (code: 'usd' o 'eur'). Se guarda hasta el próximo corte de las 12:00.
    Si falla lanza error, y los errores no se guardan: se reintenta en la siguiente visita."""
    from pyDolarVenezuela import Monitor
    from pyDolarVenezuela.pages import BCV

    monitor = Monitor(BCV, "USD")
    return float(monitor.get_value_monitors(code, "price")), datetime.now(TZ).strftime("%d/%m %H:%M")


@st.cache_data(ttl=3600, show_spinner=False)
def _binance():
    """Promedio de los 10 anuncios BUY siguientes al primero (patrocinado). Se guarda 1 hora."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    payload = {
        "asset": "USDT",
        "fiat": "VES",
        "tradeType": "BUY",
        "page": 1,
        "rows": 11,
        "payTypes": [],
        "publisherType": None,
        "countries": [],
        "proMerchantAds": False,
        "shieldMerchantAds": False,
    }
    r = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    r.raise_for_status()
    precios = [float(x["adv"]["price"]) for x in r.json()["data"]]
    siguientes = precios[1:11]
    if not siguientes:
        raise ValueError("Binance no devolvió anuncios")
    return sum(siguientes) / len(siguientes), datetime.now(TZ).strftime("%d/%m %H:%M")


def leer(fn, *args):
    try:
        valor, hora = fn(*args)
        return valor, hora, None
    except Exception as e:  # noqa: BLE001
        return None, None, f"{type(e).__name__}: {e}"


def fmt(n, dec=2):
    s = f"{n:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------ UI -----
st.image(str(BASE / "logo.png"), use_container_width=True)

c_actualizar = st.button("🔄 Actualizar ahora", use_container_width=True)
if c_actualizar:
    st.cache_data.clear()

usd, h_usd, e1 = leer(_bcv, "usd", periodo_bcv())
eur, h_eur, e2 = leer(_bcv, "eur", periodo_bcv())
bin_, h_bin, e3 = leer(_binance)

# Si una tasa no se pudo leer, se permite escribirla a mano
with st.expander("Tasas (editar si alguna no cargó)", expanded=not all([usd, eur, bin_])):
    if usd is None:
        usd = st.number_input("Dólar BCV (Bs.)", min_value=0.0, value=0.0, format="%.4f")
    if eur is None:
        eur = st.number_input("Euro BCV (Bs.)", min_value=0.0, value=0.0, format="%.4f")
    if bin_ is None:
        bin_ = st.number_input("Binance (Bs.)", min_value=0.0, value=0.0, format="%.4f")
    errores = [e for e in (e1, e2, e3) if e]
    if errores:
        st.caption("Detalle: " + " | ".join(errores))
    else:
        st.caption("Todas las tasas se cargaron automáticamente.")

def brecha(valor, base):
    """Diferencia porcentual de una tasa respecto al dólar BCV."""
    if not valor or not base:
        return "—"
    p = (valor / base - 1) * 100
    return f"{'+' if p >= 0 else '−'}{fmt(abs(p), 2)}%"


cols = st.columns(3)
chips = [
    ("Dólar BCV", usd, "Referencia"),
    ("Euro BCV", eur, f"Brecha {brecha(eur, usd)}"),
    ("Binance", bin_, f"Brecha {brecha(bin_, usd)}"),
]
for col, (nombre, val, sub) in zip(cols, chips):
    col.markdown(
        f'<div class="chip"><small>{nombre}</small><b>{fmt(val, 2) if val else "—"}</b>'
        f'<small class="gap">{sub}</small></div>',
        unsafe_allow_html=True,
    )
st.caption(
    f"BCV (dólar y euro): {h_usd or 'manual'}, se actualiza a las 12:00. "
    f"Binance: {h_bin or 'manual'}, se actualiza cada hora."
)

tasas = {"Dólar BCV": usd, "Euro BCV": eur, "Binance": bin_}
elegida = st.radio("Tasa que se cobra", list(tasas), horizontal=True)
valor = st.number_input("Valor a cobrar (en divisa)", min_value=0.0, value=0.0, step=1.0, format="%.2f")

tasa = tasas[elegida] or 0.0
total = valor * tasa
st.markdown(
    f'<div class="total"><small>Total en bolívares</small>'
    f'<div class="big">Bs. {fmt(total)}</div>'
    f'<small>{elegida}: {fmt(tasa, 4) if tasa else "sin tasa"}</small></div>',
    unsafe_allow_html=True,
)

with st.expander("Ver el total con las tres tasas"):
    for nombre, val in tasas.items():
        st.write(f"**{nombre}:** Bs. {fmt(valor * (val or 0))}")
