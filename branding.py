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


def apply_branding(*, show_header: bool = True, use_background: bool = True) -> None:
    logo_b64 = _load_base64(LOGO_PATH)
    bg_b64 = _load_base64(BACKGROUND_PATH)

    css_parts = []
    if use_background and bg_b64:
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
            background: #0d1117;
            color: #f5f7f8;
            --app-title-size: clamp(2rem, 2vw + 1.2rem, 3.2rem);
            --section-title-size: clamp(1.2rem, 1vw + 0.8rem, 2rem);
            --metric-title-size: clamp(0.72rem, 0.35vw + 0.62rem, 0.98rem);
            --metric-value-size: clamp(1.45rem, 0.95vw + 1rem, 2.2rem);
            --panel-title-size: clamp(0.72rem, 0.3vw + 0.64rem, 0.9rem);
            --panel-value-size: clamp(1.2rem, 0.9vw + 0.9rem, 1.9rem);
            --panel-sub-size: clamp(0.78rem, 0.35vw + 0.7rem, 1rem);
        }}
        header[data-testid="stHeader"] {{
            background: #0d1117;
        }}
        .block-container {{
            max-width: 1180px;
            padding-top: clamp(4rem, 6vw, 6.25rem);
            padding-left: clamp(2rem, 6vw, 5rem);
            padding-right: clamp(2rem, 6vw, 5rem);
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
            background: transparent;
            border-radius: 0;
            padding: 0;
        }}
        section[data-testid="stSidebar"] {{
            background: #2a2b34;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            min-width: 300px !important;
            width: 300px !important;
            max-width: 300px !important;
        }}
        section[data-testid="stSidebar"] > div {{
            background: #2a2b34;
            padding-top: 4.75rem;
        }}
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
            width: 300px !important;
            min-width: 300px !important;
            max-width: 300px !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
            padding-left: 1rem;
            padding-right: 1rem;
        }}
        section[data-testid="stSidebar"] * {{
            color: #e7e9f0;
        }}
        .sidebar-nav-spacer {{
            height: 0.15rem;
        }}
        .sidebar-divider {{
            height: 1px;
            margin: 1.65rem 0 1.15rem;
            background: rgba(255, 255, 255, 0.14);
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] {{
            gap: 0.32rem;
            width: 100%;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label {{
            align-items: center;
            display: flex !important;
            min-height: 38px;
            width: 100%;
            border-radius: 6px;
            padding: 0.42rem 0.72rem;
            margin: 0;
            transition: background 120ms ease, color 120ms ease;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
            background: rgba(255, 255, 255, 0.08);
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
            background: #50525f;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{
            display: none;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] p {{
            font-size: 0.98rem;
            font-weight: 700;
            line-height: 1.25;
            white-space: normal;
            overflow-wrap: anywhere;
        }}
        section[data-testid="stSidebar"] [data-baseweb="select"] {{
            min-height: 42px;
        }}
        section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
            min-height: 42px;
        }}
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stCaptionContainer,
        section[data-testid="stSidebar"] .stMarkdown p {{
            font-size: 0.94rem;
        }}
        .month-range-filter {{
            margin: 0.45rem 0 0.15rem;
        }}
        .month-range-title {{
            font-size: 0.94rem;
            font-weight: 700;
            margin-bottom: 0.38rem;
            color: #f5f7f8;
        }}
        .month-range-labels {{
            display: flex;
            justify-content: flex-end;
            gap: 2rem;
            color: #ff5b64;
            font-size: 1rem;
            font-weight: 800;
            line-height: 1.2;
        }}
        section[data-testid="stSidebar"] .stSlider {{
            padding-top: 0;
        }}
        section[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div {{
            background-color: rgba(255, 255, 255, 0.22);
        }}
        .dashboard-heading {{
            margin-bottom: 1.25rem;
        }}
        .dashboard-heading h1 {{
            margin: 0 0 1.25rem;
            font-size: clamp(2.1rem, 1.5vw + 1.7rem, 3rem);
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.08;
        }}
        .dashboard-version {{
            color: rgba(245, 247, 248, 0.68);
            font-size: 0.9rem;
            font-weight: 600;
        }}
        .section-divider {{
            height: 1px;
            margin: 3rem 0 2.5rem;
            background: rgba(255, 255, 255, 0.18);
        }}
        div[data-testid="stExpander"] {{
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 7px;
            background: transparent;
            margin-bottom: 0;
        }}
        div[data-testid="stExpander"] summary {{
            min-height: 38px;
            font-weight: 700;
            color: #f5f7f8;
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
        .kpi-datetime-card {{
            min-height: 96px;
        }}
        .kpi-datetime-date {{
            white-space: nowrap;
            overflow-wrap: normal;
        }}
        .kpi-datetime-time {{
            margin-top: 0.18rem;
            font-size: clamp(1rem, 0.45vw + 0.85rem, 1.35rem);
            font-weight: 700;
            line-height: 1.1;
            color: #d7e4f3;
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

    if show_header:
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
