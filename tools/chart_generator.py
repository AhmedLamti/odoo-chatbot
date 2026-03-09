import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import json
import logging

logger = logging.getLogger(__name__)


class ChartGenerator:
    """
    Génère des graphiques Plotly depuis des données SQL
    """

    ODOO_PRIMARY = "#71639e"
    ODOO_SECONDARY = "#5a4f80"
    ODOO_LIGHT = "#f3f1f8"
    ODOO_COLORS = [
        "#71639e", "#00a09d", "#f06050", "#f7cd1f",
        "#6cc1ed", "#814968", "#30c381", "#d6145f",
    ]

    def generate(self, chart_type: str, data: list, title: str = "",
                 x_label: str = "", y_label: str = "") -> str:
        """
        Génère un graphique et retourne le HTML

        chart_type: bar | line | pie | scatter
        data: liste de dicts depuis SQL
        """
        if not data:
            return self._empty_chart(title)

        try:
            df = pd.DataFrame(data)

            if chart_type == "bar":
                html = self._bar_chart(df, title, x_label, y_label)
            elif chart_type == "line":
                html = self._line_chart(df, title, x_label, y_label)
            elif chart_type == "pie":
                html = self._pie_chart(df, title)
            elif chart_type == "scatter":
                html = self._scatter_chart(df, title, x_label, y_label)
            else:
                html = self._bar_chart(df, title, x_label, y_label)

            return html

        except Exception as e:
            logger.error(f"Erreur génération graphique: {e}")
            return self._error_chart(str(e))

    def _get_layout(self, title: str) -> dict:
        """Layout commun Odoo style"""
        return dict(
            title=dict(
                text=title,
                font=dict(size=16, color=self.ODOO_PRIMARY, family="Roboto, sans-serif"),
                x=0.5,
            ),
            paper_bgcolor="white",
            plot_bgcolor="#fafafa",
            font=dict(family="Roboto, sans-serif", size=12, color="#333"),
            margin=dict(l=50, r=30, t=60, b=50),
            showlegend=True,
            legend=dict(
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor=self.ODOO_LIGHT,
                borderwidth=1,
            ),
            xaxis=dict(
                gridcolor="#eeeeee",
                linecolor="#dddddd",
                showgrid=True,
            ),
            yaxis=dict(
                gridcolor="#eeeeee",
                linecolor="#dddddd",
                showgrid=True,
            ),
        )

    def _bar_chart(self, df: pd.DataFrame, title: str,
                   x_label: str, y_label: str) -> str:
        cols = df.columns.tolist()
        x_col = cols[0]
        y_cols = cols[1:]

        fig = go.Figure()
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Bar(
                x=df[x_col],
                y=df[y_col],
                name=y_col,
                marker_color=self.ODOO_COLORS[i % len(self.ODOO_COLORS)],
                marker_line=dict(color="white", width=1),
                opacity=0.9,
            ))

        layout = self._get_layout(title)
        layout["barmode"] = "group"
        layout["xaxis"]["title"] = x_label or x_col
        layout["yaxis"]["title"] = y_label or (y_cols[0] if y_cols else "")
        fig.update_layout(**layout)

        return self._to_html(fig)

    def _line_chart(self, df: pd.DataFrame, title: str,
                    x_label: str, y_label: str) -> str:
        cols = df.columns.tolist()
        x_col = cols[0]
        y_cols = cols[1:]

        fig = go.Figure()
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[y_col],
                name=y_col,
                mode="lines+markers",
                line=dict(
                    color=self.ODOO_COLORS[i % len(self.ODOO_COLORS)],
                    width=3,
                ),
                marker=dict(size=7, symbol="circle"),
                fill="tozeroy",
                fillcolor=f"rgba(113, 99, 158, 0.1)",
            ))

        layout = self._get_layout(title)
        layout["xaxis"]["title"] = x_label or x_col
        layout["yaxis"]["title"] = y_label or (y_cols[0] if y_cols else "")
        fig.update_layout(**layout)

        return self._to_html(fig)

    def _pie_chart(self, df: pd.DataFrame, title: str) -> str:
        cols = df.columns.tolist()
        label_col = cols[0]
        value_col = cols[1] if len(cols) > 1 else cols[0]

        fig = go.Figure(go.Pie(
            labels=df[label_col],
            values=df[value_col],
            marker=dict(
                colors=self.ODOO_COLORS,
                line=dict(color="white", width=2),
            ),
            hole=0.35,
            textinfo="label+percent",
            textfont=dict(size=12),
        ))

        layout = self._get_layout(title)
        layout.pop("xaxis", None)
        layout.pop("yaxis", None)
        fig.update_layout(**layout)

        return self._to_html(fig)

    def _scatter_chart(self, df: pd.DataFrame, title: str,
                       x_label: str, y_label: str) -> str:
        cols = df.columns.tolist()
        x_col = cols[0]
        y_col = cols[1] if len(cols) > 1 else cols[0]

        fig = go.Figure(go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="markers",
            marker=dict(
                color=self.ODOO_PRIMARY,
                size=10,
                opacity=0.8,
                line=dict(color="white", width=1),
            ),
        ))

        layout = self._get_layout(title)
        layout["xaxis"]["title"] = x_label or x_col
        layout["yaxis"]["title"] = y_label or y_col
        fig.update_layout(**layout)

        return self._to_html(fig)

    def generate_json(self, chart_type: str, data: list, title: str = "",
                      x_label: str = "", y_label: str = "") -> str:
        """Retourne le JSON Plotly au lieu de HTML"""
        import json
        if not data:
            return json.dumps({"error": "no_data", "title": title})

        try:
            df = pd.DataFrame(data)
            if chart_type == "bar":
                fig = self._bar_figure(df, title, x_label, y_label)
            elif chart_type == "line":
                fig = self._line_figure(df, title, x_label, y_label)
            elif chart_type == "pie":
                fig = self._pie_figure(df, title)
            else:
                fig = self._bar_figure(df, title, x_label, y_label)

            return fig.to_json()

        except Exception as e:
            logger.error(f"Erreur: {e}")
            return json.dumps({"error": str(e)})

    def _bar_figure(self, df, title, x_label, y_label):
        cols = df.columns.tolist()
        x_col = cols[0]
        y_cols = cols[1:]
        fig = go.Figure()
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Bar(
                x=df[x_col], y=df[y_col], name=y_col,
                marker_color=self.ODOO_COLORS[i % len(self.ODOO_COLORS)],
            ))
        layout = self._get_layout(title)
        layout["xaxis"]["title"] = x_label or x_col
        layout["yaxis"]["title"] = y_label or (y_cols[0] if y_cols else "")
        fig.update_layout(**layout)
        return fig

    def _line_figure(self, df, title, x_label, y_label):
        cols = df.columns.tolist()
        x_col = cols[0]
        y_cols = cols[1:]
        fig = go.Figure()
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Scatter(
                x=df[x_col], y=df[y_col], name=y_col,
                mode="lines+markers",
                line=dict(color=self.ODOO_COLORS[i % len(self.ODOO_COLORS)], width=3),
                fill="tozeroy",
                fillcolor="rgba(113, 99, 158, 0.1)",
            ))
        layout = self._get_layout(title)
        layout["xaxis"]["title"] = x_label or x_col
        layout["yaxis"]["title"] = y_label or (y_cols[0] if y_cols else "")
        fig.update_layout(**layout)
        return fig

    def _pie_figure(self, df, title):
        cols = df.columns.tolist()
        fig = go.Figure(go.Pie(
            labels=df[cols[0]],
            values=df[cols[1]] if len(cols) > 1 else df[cols[0]],
            marker=dict(colors=self.ODOO_COLORS, line=dict(color="white", width=2)),
            hole=0.35,
        ))
        layout = self._get_layout(title)
        layout.pop("xaxis", None)
        layout.pop("yaxis", None)
        fig.update_layout(**layout)
        return fig

    def _to_html(self, fig) -> str:
        """Convertit le graphique en HTML embarquable"""
        return fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={
                "displayModeBar": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                "displaylogo": False,
                "responsive": True,
            },
        )

    def _empty_chart(self, title: str) -> str:
        return f"""
        <div style="text-align:center;padding:40px;color:#888;font-family:Roboto,sans-serif;">
            <div style="font-size:40px">📊</div>
            <div style="margin-top:10px;font-size:14px">
                Aucune donnée disponible pour "{title}"
            </div>
        </div>
        """

    def _error_chart(self, error: str) -> str:
        return f"""
        <div style="text-align:center;padding:40px;color:#e74c3c;font-family:Roboto,sans-serif;">
            <div style="font-size:40px">⚠️</div>
            <div style="margin-top:10px;font-size:14px">
                Erreur lors de la génération du graphique :<br/>
                <code>{error}</code>
            </div>
        </div>
        """
