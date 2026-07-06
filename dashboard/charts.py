"""Plotly chart builders for the dashboard."""

from __future__ import annotations

from typing import Any

import plotly.express as px
import plotly.graph_objects as go


def _template() -> str:
    try:
        import streamlit as st

        return st.session_state.get("plotly_template", "plotly_white")
    except Exception:
        return "plotly_white"


def _base_layout(title: str, **kwargs: Any) -> dict[str, Any]:
    layout = dict(
        title=title,
        template=_template(),
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    layout.update(kwargs)
    return layout


def histogram(values: list[float], title: str, x_label: str = "Hours") -> go.Figure:
    fig = px.histogram(x=values, nbins=min(30, max(5, len(values) // 2)), labels={"x": x_label})
    fig.update_layout(**_base_layout(title))
    return fig


def box_plot(values: list[float], title: str, y_label: str = "Hours") -> go.Figure:
    fig = go.Figure(data=[go.Box(y=values, name=y_label, boxpoints="outliers")])
    fig.update_layout(**_base_layout(title), yaxis_title=y_label)
    return fig


def scatter(x: list, y: list, labels: list[str], title: str, x_title: str, y_title: str) -> go.Figure:
    fig = px.scatter(x=x, y=y, text=labels)
    fig.update_traces(textposition="top center")
    fig.update_layout(**_base_layout(title), xaxis_title=x_title, yaxis_title=y_title)
    return fig


def bar_chart(x: list, y: list, title: str, x_title: str = "", y_title: str = "") -> go.Figure:
    fig = px.bar(x=x, y=y, labels={"x": x_title, "y": y_title})
    fig.update_layout(**_base_layout(title))
    return fig


def line_chart(x: list, y: list, title: str, x_title: str = "", y_title: str = "") -> go.Figure:
    fig = px.line(x=x, y=y, markers=True, labels={"x": x_title, "y": y_title})
    fig.update_layout(**_base_layout(title))
    return fig


def pie_chart(labels: list[str], values: list[float], title: str) -> go.Figure:
    fig = px.pie(names=labels, values=values, hole=0.35)
    fig.update_layout(**_base_layout(title))
    return fig


def heatmap(z: list[list[float]], x: list[str], y: list[str], title: str) -> go.Figure:
    fig = go.Figure(
        data=go.Heatmap(z=z, x=x, y=y, colorscale="Blues", hoverongaps=False),
    )
    fig.update_layout(**_base_layout(title))
    return fig


def rolling_average(values: list[float], window: int = 3) -> list[float | None]:
    if not values:
        return []
    result: list[float | None] = []
    for idx in range(len(values)):
        if idx + 1 < window:
            result.append(None)
            continue
        chunk = values[idx + 1 - window : idx + 1]
        result.append(sum(chunk) / len(chunk))
    return result
