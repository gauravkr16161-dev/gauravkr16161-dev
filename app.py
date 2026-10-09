import streamlit as st
import pandas as pd
import re
import plotly.graph_objects as go
from io import BytesIO

DAILY_TARGET = 12500
SHIFT_START_HOUR = 6


def read_sql(file):
    text = file.getvalue().decode("utf-8", errors="ignore")

    pattern = re.compile(
        r"values\s*\(\s*(\d+)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*,\s*"
        r"to_date\s*\(\s*'([^']+)'\s*,\s*'[^']+'\s*\)\s*\)",
        re.IGNORECASE
    )

    data = []

    for match in pattern.finditer(text):
        coil_id = int(match.group(1))
        weight = float(match.group(2))

        birth_time = pd.to_datetime(
            match.group(3),
            format="%d-%b-%Y %I:%M:%S %p",
            errors="coerce"
        )

        if pd.notna(birth_time):
            data.append([coil_id, weight, birth_time])

    return pd.DataFrame(
        data,
        columns=["COILID", "COIL_WEIGHT", "BIRTH_TIME"]
    )


def read_excel(file):
    file_data = BytesIO(file.getvalue())
    excel = pd.ExcelFile(file_data)

    required_columns = [
        "COILID",
        "COIL_WEIGHT",
        "BIRTH_TIME"
    ]

    # The uploaded HSM Excel has the production data
    # in the "Export Worksheet" sheet.
    sheet_names = excel.sheet_names

    if "Export Worksheet" in sheet_names:
        sheet_names.remove("Export Worksheet")
        sheet_names.insert(0, "Export Worksheet")

    for sheet in sheet_names:
        df = pd.read_excel(
            BytesIO(file.getvalue()),
            sheet_name=sheet
        )

        df.columns = [
            str(column).strip().upper()
            for column in df.columns
        ]

        if all(column in df.columns for column in required_columns):
            df = df[required_columns].copy()
            return df

    raise ValueError(
        "Excel file must contain COILID, COIL_WEIGHT and BIRTH_TIME columns."
    )


def prepare_data(df):
    df = df.copy()

    df["COILID"] = pd.to_numeric(
        df["COILID"],
        errors="coerce"
    )

    df["COIL_WEIGHT"] = pd.to_numeric(
        df["COIL_WEIGHT"],
        errors="coerce"
    )

    df["BIRTH_TIME"] = pd.to_datetime(
        df["BIRTH_TIME"],
        format="%d-%b-%Y %I:%M:%S %p",
        errors="coerce"
    )

    # Remove rows where important production information is missing.
    df = df.dropna(
        subset=["COILID", "COIL_WEIGHT", "BIRTH_TIME"]
    )

    # Keep one record for each coil.
    df = df.drop_duplicates(
        subset=["COILID"],
        keep="first"
    )

    # Production day starts at 06:00 AM.
    df["PRODUCTION_DATE"] = (
        df["BIRTH_TIME"] -
        pd.Timedelta(hours=SHIFT_START_HOUR)
    ).dt.date

    return df.sort_values("BIRTH_TIME").reset_index(drop=True)


def hourly_report(df, selected_date):
    start_time = pd.Timestamp(selected_date) + pd.Timedelta(
        hours=SHIFT_START_HOUR
    )

    rows = []
    cumulative_actual = 0

    for hour in range(24):
        hour_start = start_time + pd.Timedelta(hours=hour)
        hour_end = hour_start + pd.Timedelta(hours=1)

        hour_data = df[
            (df["BIRTH_TIME"] >= hour_start) &
            (df["BIRTH_TIME"] < hour_end)
        ]

        actual_weight = hour_data["COIL_WEIGHT"].sum()
        coil_count = len(hour_data)

        hours_remaining = 24 - hour
        production_remaining = max(
            DAILY_TARGET - cumulative_actual,
            0
        )

        required_rate = (
            production_remaining / hours_remaining
        )

        rows.append([
            selected_date.strftime("%d %b %Y"),
            hour_start.strftime("%I:00 %p") +
            " - " +
            hour_end.strftime("%I:00 %p"),
            required_rate,
            actual_weight,
            coil_count,
            actual_weight
        ])

        cumulative_actual += actual_weight

    return pd.DataFrame(
        rows,
        columns=[
            "Date",
            "Hour (Start-End)",
            "Required Production Rate (Ton/hr)",
            "Actual Production Rate (Ton/hr)",
            "Actual No. of Coil Rolled",
            "Actual Weight of Coil (Tons)"
        ]
    )


def make_chart(report):
    hours = report["Hour (Start-End)"]
    required = report["Required Production Rate (Ton/hr)"]
    actual = report["Actual Production Rate (Ton/hr)"]

    actual_colors = []

    for i in range(len(report)):
        if actual.iloc[i] >= required.iloc[i]:
            actual_colors.append("#16A34A")
        else:
            actual_colors.append("#DC2626")

    figure = go.Figure()

    figure.add_trace(
        go.Bar(
            x=hours,
            y=required,
            name="Required Production Rate",
            marker_color="#2563EB",
            hovertemplate="Required: %{y:.2f} Ton/hr<extra></extra>"
        )
    )

    figure.add_trace(
        go.Bar(
            x=hours,
            y=actual,
            name="Actual Production Rate",
            marker_color=actual_colors,
            hovertemplate="Actual: %{y:.2f} Ton/hr<extra></extra>"
        )
    )

    figure.add_trace(
        go.Scatter(
            x=hours,
            y=required,
            name="Required Trend",
            mode="lines",
            line=dict(color="#60A5FA", width=3),
            hovertemplate="Required Trend: %{y:.2f} Ton/hr<extra></extra>"
        )
    )

    figure.add_trace(
        go.Scatter(
            x=hours,
            y=actual,
            name="Actual Trend",
            mode="lines+markers",
            line=dict(color="#22C55E", width=3),
            marker=dict(size=6),
            hovertemplate="Actual Trend: %{y:.2f} Ton/hr<extra></extra>"
        )
    )

    figure.update_layout(
        height=620,
        barmode="group",
        bargap=0.12,
        bargroupgap=0.05,
        margin=dict(l=50, r=30, t=35, b=130),
        plot_bgcolor="#111111",
        paper_bgcolor="#111111",
        font=dict(color="white"),
        xaxis=dict(
            title="Hour",
            tickangle=-45,
            showgrid=False,
            color="white",
            linecolor="#555555"
        ),
        yaxis=dict(
            title="Tonnage",
            showgrid=True,
            gridcolor="#333333",
            rangemode="tozero",
            color="white",
            linecolor="#555555"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            font=dict(color="white")
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#222222",
            font=dict(color="white")
        )
    )

    return figure


st.title("HSM Production Monitoring Dashboard")

target_col, shift_col = st.columns(2)

with target_col:
    st.metric("Daily Target", f"{DAILY_TARGET:,} Tons")

with shift_col:
    st.metric("Production Shift", "06:00 AM - 06:00 AM")


file = st.file_uploader(
    "Upload HSM production Excel or SQL file",
    type=["xls", "xlsx", "sql"]
)

if file is not None:
    try:
        if file.name.lower().endswith(".sql"):
            df = read_sql(file)
            source_name = "SQL"
        else:
            df = read_excel(file)
            source_name = "Excel"

        df = prepare_data(df)

        if len(df) == 0:
            st.error(
                "No valid production records were found in the uploaded file."
            )
            st.stop()

        available_dates = sorted(
            df["PRODUCTION_DATE"].unique()
        )

        selected_date = st.selectbox(
            "Select Production Date",
            available_dates,
            format_func=lambda date:
                pd.Timestamp(date).strftime("%d %b %Y")
        )

        report = hourly_report(
            df,
            selected_date
        )

        actual_total = report[
            "Actual Weight of Coil (Tons)"
        ].sum()

        coil_total = report[
            "Actual No. of Coil Rolled"
        ].sum()

        variance = actual_total - DAILY_TARGET

        st.write(
            f"Data Source: {source_name} | "
            f"Records Loaded: {len(df):,} | "
            f"Coils for Selected Day: {coil_total:,}"
        )

        if variance >= 0:
            st.success(
                f"Daily Target: {DAILY_TARGET:,.2f} Tons | "
                f"Actual Production: {actual_total:,.2f} Tons | "
                f"Variance: +{variance:,.2f} Tons"
            )
        else:
            st.error(
                f"Daily Target: {DAILY_TARGET:,.2f} Tons | "
                f"Actual Production: {actual_total:,.2f} Tons | "
                f"Variance: {variance:,.2f} Tons"
            )

        st.subheader("Live Hourly Monitoring")

        st.dataframe(
            report.style.format({
                "Required Production Rate (Ton/hr)": "{:.2f}",
                "Actual Production Rate (Ton/hr)": "{:.2f}",
                "Actual Weight of Coil (Tons)": "{:.2f}"
            }),
            width="stretch",
            height=470,
            hide_index=True
        )

        st.subheader(
            "Required Production Rate vs Actual Production Rate"
        )

        st.plotly_chart(
            make_chart(report),
            width="stretch",
            config={"displayModeBar": False}
        )

    except Exception as error:
        st.error("Error while reading the file:")
        st.write(error)
