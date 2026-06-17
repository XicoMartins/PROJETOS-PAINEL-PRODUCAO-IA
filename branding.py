from __future__ import annotations

import base64
from pathlib import Path

import plotly.express as px
import streamlit as st

from constants import BACKGROUND_PATH, LOGO_PATH, PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE


def _load_base64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def apply_branding() -> None:
    logo_b64 = _load_base64(LOGO_PATH)
    bg_b64 = _load_base64(BACKGROUND_PATH)

    css_parts = []
    if bg_b64:
        css_parts.append(
            f"""
            .stApp {{
                background: url("data:image/png;base64,{bg_b64}") no-repeat center center fixed;
                background-size: cover;
            }}
            """
        )
    css_parts.append(
        f"""
        .stApp {{
            color: #f5f7f8;
            --app-title-size: clamp(2rem, 2vw + 1.2rem, 3.2rem);
            --section-title-size: clamp(1.2rem, 1vw + 0.8rem, 2rem);
            --metric-title-size: clamp(0.72rem, 0.35vw + 0.62rem, 0.98rem);
            --metric-value-size: clamp(1.45rem, 0.95vw + 1rem, 2.2rem);
            --panel-title-size: clamp(0.72rem, 0.3vw + 0.64rem, 0.9rem);
            --panel-value-size: clamp(1.2rem, 0.9vw + 0.9rem, 1.9rem);
            --panel-sub-size: clamp(0.78rem, 0.35vw + 0.7rem, 1rem);
        }}
        .block-container {{
            padding-top: clamp(1rem, 2vw, 2rem);
        }}
        .stApp h1 {{
            font-size: var(--app-title-size);
            line-height: 1.1;
            word-break: break-word;
        }}
        .stApp h2, .stApp h3 {{
            font-size: var(--section-title-size);
            line-height: 1.15;
            word-break: break-word;
        }}
        section.main > div:first-child {{
            background: {SURFACE};
            border-radius: 12px;
            padding: 12px;
        }}
        .stMetric {{
            background: {SURFACE};
            border-radius: 12px;
            padding: 12px;
            height: 100%;
            min-height: 96px;
        }}
        .kpi-card {{
            background: {SURFACE};
            border-radius: 12px;
            padding: 12px;
        }}
        .kpi-title {{
            font-size: var(--metric-title-size);
            margin-bottom: 6px;
            opacity: 0.9;
            line-height: 1.25;
            word-break: break-word;
        }}
        .kpi-value {{
            font-size: var(--metric-value-size);
            font-weight: 700;
            line-height: 1.1;
            overflow-wrap: anywhere;
        }}
        .kpi-name {{
            font-size: clamp(1rem, 0.7vw + 0.8rem, 1.45rem);
            font-weight: 700;
            margin-left: 10px;
            white-space: normal;
            overflow-wrap: anywhere;
        }}
        div[data-testid="stMetric"] > div {{
            gap: 0.25rem;
        }}
        div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {{
            font-size: var(--metric-title-size);
            line-height: 1.25;
            white-space: normal !important;
            overflow: visible !important;
        }}
        div[data-testid="stMetric"] label[data-testid="stMetricLabel"] > div {{
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            word-break: break-word;
        }}
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
            font-size: var(--metric-value-size);
            line-height: 1.1;
        }}
        div[data-testid="stMetric"] [data-testid="stMetricValue"] > div {{
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            overflow-wrap: anywhere;
            word-break: break-word;
        }}
        .display-panel {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .panel-card {{
            border: 2px solid rgba(245, 247, 248, 0.2);
            border-radius: 16px;
            padding: 14px 16px;
            background: rgba(12, 41, 47, 0.55);
        }}
        .panel-title {{
            font-size: var(--panel-title-size);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.85;
            line-height: 1.25;
            word-break: break-word;
        }}
        .panel-value {{
            font-size: var(--panel-value-size);
            font-weight: 700;
            margin-top: 6px;
            line-height: 1.15;
            overflow-wrap: anywhere;
        }}
        .panel-value-inline {{
            display: flex;
            align-items: baseline;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .panel-value-extra {{
            font-weight: 700;
        }}
        .panel-sub {{
            font-size: var(--panel-sub-size);
            opacity: 0.9;
            margin-top: 4px;
            line-height: 1.25;
            word-break: break-word;
        }}
        .st-emotion-cache-1v0mbdj.e1f1d6gn1 {{
            background: {PRIMARY_DARK};
        }}
        .st-emotion-cache-1avcm0n {{
            background: {PRIMARY_DARK};
        }}
        .st-emotion-cache-18ni7ap p, .st-emotion-cache-1v0mbdj p {{
            color: #f5f7f8;
        }}
        .stButton>button {{
            background: {PRIMARY};
            color: #0b1f24;
            border: none;
            border-radius: 8px;
        }}
        section[data-testid="stSidebar"] [data-baseweb="select"] div[aria-live="polite"] {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.25rem;
        }}
        section[data-testid="stSidebar"] [data-baseweb="select"] [data-baseweb="tag"] {{
            max-width: 100% !important;
            height: auto !important;
        }}
        section[data-testid="stSidebar"] [data-baseweb="select"] [data-baseweb="tag"] > span {{
            max-width: none !important;
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: normal !important;
            word-break: break-word !important;
        }}
        @media (max-width: 1400px) {{
            .stMetric, .kpi-card, .panel-card {{
                padding: 10px;
            }}
            .panel-value-inline {{
                gap: 8px;
            }}
        }}
        @media (max-width: 1100px) {{
            section.main > div:first-child {{
                padding: 10px;
            }}
            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}
        }}
        """
    )

    if css_parts:
        st.markdown("<style>" + "\n".join(css_parts) + "</style>", unsafe_allow_html=True)

    header_cols = st.columns([1, 4])
    if logo_b64:
        header_cols[0].markdown(
            f'<img src="data:image/png;base64,{logo_b64}" style="max-height:80px;">',
            unsafe_allow_html=True,
        )
    else:
        header_cols[0].markdown("## MTECH")
    header_cols[1].markdown("### Displays com tecnologia")

    px.defaults.color_discrete_sequence = [PRIMARY, PRIMARY_LIGHT, PRIMARY_DARK, "#111111"]
    px.defaults.template = "plotly_dark"
