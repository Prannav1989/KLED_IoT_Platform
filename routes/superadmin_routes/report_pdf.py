import io
from collections import defaultdict
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from models import SensorData, Parameter, Company


class PDFReportGenerator:
    """
    Professional & visually enhanced PDF generator
    for IoT sensor historical data
    """

    def generate_device_report(self, devices, company_id, start_date=None, end_date=None):
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=24,
            rightMargin=24,
            topMargin=24,
            bottomMargin=24
        )

        styles = getSampleStyleSheet()
        elements = []

        # -------------------------------------------------
        # STYLES
        # -------------------------------------------------
        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Title"],
            fontSize=22,
            textColor=colors.HexColor("#0F766E"),
            spaceAfter=18
        )

        normal_dark = ParagraphStyle(
            "NormalDark",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#111827"),
            alignment=1
        )

        sensor_title_style = ParagraphStyle(
            "SensorTitleStyle",
            parent=styles["Normal"],
            fontSize=13,
            textColor=colors.HexColor("#0F766E"),
            alignment=1,
            spaceAfter=6
        )

        # -------------------------------------------------
        # COVER PAGE
        # -------------------------------------------------
        elements.append(Paragraph(
            "KLED – Sensor Data Report",
            title_style
        ))

        period_text = "All Available Data"
        if start_date and end_date:
            period_text = (
                f"{start_date.strftime('%d %b %Y %H:%M')} → "
                f"{end_date.strftime('%d %b %Y %H:%M')}"
            )

        info_table = Table(
            [
                ["Report Type", "Sensor Data Report"],
                ["Generated On", datetime.now().strftime("%d %b %Y %H:%M")],
                ["Reporting Period", period_text],
                ["Total Sensors", str(len(devices))]
            ],
            colWidths=[200, 450]
        )

        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0F2FE")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ]))

        elements.append(info_table)
        elements.append(PageBreak())

        # -------------------------------------------------
        # SORT DEVICES
        # -------------------------------------------------
        devices = sorted(devices, key=lambda d: d.id)

        # -------------------------------------------------
        # SENSOR SECTIONS (FIXED)
        # -------------------------------------------------
        for device in devices:

            sensor_title = Paragraph(
                f"<b>Sensor: {device.name} (ID: {device.id})</b>",
                sensor_title_style
            )

            parameters = (
                Parameter.query
                .filter_by(device_id=device.id)
                .order_by(Parameter.id)
                .all()
            )

            # -------------------------------
            # NO PARAMETERS
            # -------------------------------
            if not parameters:
                elements.append(KeepTogether([
                    sensor_title,
                    Paragraph("No parameters configured for this sensor.", normal_dark)
                ]))
                elements.append(PageBreak())
                continue

            query = SensorData.query.filter(SensorData.device_id == device.id)
            if start_date:
                query = query.filter(SensorData.timestamp >= start_date)
            if end_date:
                query = query.filter(SensorData.timestamp <= end_date)

            records = query.order_by(SensorData.timestamp).all()

            # -------------------------------
            # NO DATA
            # -------------------------------
            if not records:
                elements.append(KeepTogether([
                    sensor_title,
                    Paragraph("No data available for the selected period.", normal_dark)
                ]))
                elements.append(PageBreak())
                continue

            # -------------------------------
            # DATA EXISTS
            # -------------------------------
            data_map = defaultdict(dict)
            for r in records:
                ts = r.timestamp.replace(second=0, microsecond=0)\
                    .strftime("%Y-%m-%d %H:%M")
                data_map[ts][r.parameter_id] = r.value

            param_values = {p.id: [] for p in parameters}
            for r in records:
                if r.value is not None:
                    param_values[r.parameter_id].append(r.value)

            table_data = [["Timestamp"] + [
                f"{p.name} ({p.unit})" if p.unit else p.name for p in parameters
            ]]

            for ts in sorted(data_map):
                row = [ts]
                for p in parameters:
                    row.append(data_map[ts].get(p.id, ""))
                table_data.append(row)

            min_row = ["Min"]
            max_row = ["Max"]

            for p in parameters:
                values = param_values[p.id]
                min_row.append(round(min(values), 2) if values else "")
                max_row.append(round(max(values), 2) if values else "")

            table_data.append(min_row)
            table_data.append(max_row)

            col_widths = [110] + [80] * len(parameters)
            table = Table(table_data, colWidths=col_widths, repeatRows=1)

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0F2FE")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#DCFCE7")),
                ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
            ]))

            for i in range(1, len(table_data) - 2):
                if i % 2 == 0:
                    table.setStyle(TableStyle([
                        ("BACKGROUND", (0, i), (-1, i), colors.whitesmoke)
                    ]))

            # ✅ TITLE + TABLE KEPT TOGETHER
            elements.append(KeepTogether([
                sensor_title,
                table
            ]))
            elements.append(PageBreak())

        doc.build(elements)
        buffer.seek(0)
        return buffer
