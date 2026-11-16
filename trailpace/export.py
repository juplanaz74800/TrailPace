"""Export du plan de course : fiche PDF imprimable et GPX avec temps de passage."""
import io
import unicodedata
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREEN = colors.HexColor("#0f6b5c")
GREY = colors.HexColor("#667085")
LIGHT = colors.HexColor("#e4e7ec")


def _hm(h):
    m = int(round(h * 60))
    return f"{m // 60}h{m % 60:02d}"


def _pace(p):
    if not p:
        return "-"
    m, s = int(p), int(round((p - int(p)) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}"


def _x(s):
    return escape(str(s)) if s is not None else ""


def filename(plan, ext):
    """Nom de fichier ASCII (les en-têtes HTTP ne supportent pas bien les accents)."""
    name = unicodedata.normalize("NFKD", plan.get("course_name", "plan")).encode("ascii", "ignore").decode()
    base = "".join(c if c.isalnum() else "-" for c in name).strip("-").lower() or "plan"
    return f"plan-{base}.{ext}"


# ------------------------------------------------------------------ PDF
class ProfileChart(Flowable):
    """Profil altimétrique avec ravitos et repères horaires."""

    def __init__(self, plan, width, height):
        super().__init__()
        self.plan, self.width, self.height = plan, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c, p = self.canv, self.plan
        pf = p["profile"]
        km, ele, th = pf["km"], pf["ele"], pf["t_h"]
        total = km[-1]
        left, bottom, top = 30, 30, self.height - 16
        w = self.width - left - 6
        lo, hi = min(ele) - 40, max(ele) + 40
        X = lambda k: left + k / total * w
        Y = lambda e: bottom + (e - lo) / (hi - lo) * (top - bottom)

        c.setStrokeColor(LIGHT)
        c.setLineWidth(0.4)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(GREY)
        step = 100 if hi - lo > 500 else 50
        for e in range(int(lo // step + 1) * step, int(hi), step):
            c.line(left, Y(e), left + w, Y(e))
            c.drawRightString(left - 3, Y(e) - 2, f"{e} m")
        # surface d'altitude
        path = c.beginPath()
        path.moveTo(X(km[0]), bottom)
        for k, e in zip(km, ele):
            path.lineTo(X(k), Y(e))
        path.lineTo(X(km[-1]), bottom)
        path.close()
        c.setFillColor(colors.HexColor("#eef1f4"))
        c.setStrokeColor(GREY)
        c.setLineWidth(0.8)
        c.drawPath(path, fill=1, stroke=0)
        line = c.beginPath()
        line.moveTo(X(km[0]), Y(ele[0]))
        for k, e in zip(km[1:], ele[1:]):
            line.lineTo(X(k), Y(e))
        c.drawPath(line, fill=0, stroke=1)
        # ravitos
        c.setFont("Helvetica-Bold", 7)
        for i, s in enumerate(p["sections"][:-1]):
            xk = X(s["end_km"])
            c.setStrokeColor(GREEN)
            c.setDash(1.5, 1.5)
            c.setLineWidth(0.6)
            c.line(xk, bottom, xk, top)
            c.setDash()
            c.setFillColor(GREEN)
            c.drawCentredString(xk, top + 8, f"R{i + 1}")
            c.setFont("Helvetica", 6.5)
            c.drawCentredString(xk, top + 1, s["clock"])
            c.setFont("Helvetica-Bold", 7)
        # axe des km et repères horaires
        c.setFillColor(GREY)
        c.setFont("Helvetica", 6.5)
        for kk in range(0, int(total) + 1, 10):
            c.drawCentredString(X(kk), bottom - 9, str(kk))
        c.drawString(left, bottom - 19, "km")
        hours = int(th[-1])
        for hh in range(1, hours + 1):
            j = next((i for i, v in enumerate(th) if v >= hh), None)
            if j:
                clk = datetime.fromisoformat(p["params"]["start"]) + timedelta(hours=hh)
                c.setFillColor(GREEN)
                c.drawCentredString(X(km[j]), bottom - 27, f"{hh}h")
                c.setFillColor(GREY)
                c.drawCentredString(X(km[j]), bottom - 34, clk.strftime("%H:%M"))
                c.setStrokeColor(LIGHT)
                c.line(X(km[j]), bottom - 2, X(km[j]), bottom + 2)


def plan_pdf(plan):
    """Fiche de course A4 paysage -> octets PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm,
                            bottomMargin=10 * mm, title=f"Plan de course - {plan['course_name']}", author="Trailpace")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=17, alignment=0, spaceAfter=1, textColor=GREEN)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=8.5, textColor=GREY)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=7.6, leading=9)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=6.8, leading=8.3, textColor=GREY)
    start = datetime.fromisoformat(plan["params"]["start"])
    pw = plan.get("power")

    story = [Paragraph(_x(plan["course_name"]) + " - plan de course", h1),
             Paragraph(f"Depart {start.strftime('%a %d/%m/%Y %H:%M')} - arrivee estimee {plan['finish_clock']}", sub), Spacer(1, 3 * mm)]

    kpis = [("Temps total", plan["total"]), ("Effort moyen", f"{round(plan['pct'] * 100)} % de la CS")]
    if pw:
        kpis.append(("Puissance moyenne", f"{round(pw['avg'])} W ({round(pw['pct_cp'])} % CP)"))
    kpis.append(("Temps aux ravitos", f"{round(plan['stops_s'] / 60)} min"))
    kpi = ParagraphStyle("kpi", parent=cell, leading=14)
    row = [[Paragraph(f"<font size=6.5 color='#667085'>{_x(k)}</font><br/><b><font size=11>{_x(v)}</font></b>", kpi) for k, v in kpis]]
    t = Table(row, colWidths=[(doc.width) / len(kpis)] * len(kpis))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LIGHT), ("INNERGRID", (0, 0), (-1, -1), 0.5, LIGHT),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 3 * mm), ProfileChart(plan, doc.width, 62 * mm), Spacer(1, 2 * mm)]

    head = ["Section", "Km", "Dist.", "D+ / D-", "Temps", "Allure", "Passage", "Heure", "Arret", "FC cible"]
    if pw:
        head.append("Puissance")
    head += ["Barriere (marge)", "Meteo"]
    data = [[Paragraph(f"<b>{h}</b>", cell) for h in head]]
    for s in plan["sections"]:
        frm = "Depart" if s["n"] == 1 else s["from"]
        r = [Paragraph(f"{_x(frm)} &gt; {_x(s['to'])}", cell), f"{s['start_km']:.1f}-{s['end_km']:.1f}", f"{s['dist_km']:.1f}",
             f"+{s['gain']:.0f} / -{s['loss']:.0f}", s["time"], _pace(s["pace_min_km"]) + "/km", s["arrival"], s["clock"],
             f"{s['stop_min']:.0f} min" if s["stop_min"] else "-", f"{s['hr_target']:.0f} bpm" if s.get("hr_target") else "-"]
        if pw:
            r.append(f"{s['power_w']:.0f} W ({s['power_pct_cp']:.0f} %)" if s.get("power_w") else "-")
        mg = f"{s['cutoff']} ({s['cutoff_margin_min'] / 60:.1f} h)" if s.get("cutoff") else "-"
        wx = f"{s['temp']:.0f} C, {s['wind_kmh']:.0f} km/h" if s.get("temp") is not None else "-"
        data.append(r + [mg, wx])
    colw = [58, 36, 24, 40, 26, 34, 30, 28, 26, 36] + ([52] if pw else []) + [52, 52]
    scale = doc.width / sum(colw)
    tbl = Table(data, colWidths=[w * scale for w in colw], repeatRows=1)
    tbl.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.6), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f4")),
                             ("LINEBELOW", (0, 0), (-1, -1), 0.4, LIGHT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [tbl, Spacer(1, 3 * mm)]

    p = plan["params"]
    hyp = (f"Hypotheses : derive de fatigue {p['drift_pct_h']:g} %/h apres la 1re heure ; ralentissement de nuit {p['night_pen_pct']:g} % (pic 4h30) ; "
           f"chaleur {p['heat_sens_pct']:g} %/C au-dessus de 8 C ; technicite x{p['tech_sens']:g} ; altitude x{p['alt_sens']:g}. "
           f"Profil athlete : vitesse critique {plan['cs_kmh']:g} km/h equivalent plat. Meteo : {_x(plan.get('weather_source') or 'indisponible')}. "
           f"Allure = temps de deplacement, arrets exclus. Estimation a ajuster sur le terrain - genere par Trailpace.")
    story.append(Paragraph(hyp, small))
    doc.build(story)
    return buf.getvalue()


# ------------------------------------------------------------------ GPX
def _utc(dt):
    """Heure locale de la machine -> UTC (le départ est saisi en heure locale)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_gpx(plan):
    """Trace + ravitos avec heures de passage prévues -> texte GPX 1.1."""
    start = datetime.fromisoformat(plan["params"]["start"])
    pf = plan["profile"]
    name = _x(plan["course_name"])
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="Trailpace" xmlns="http://www.topografix.com/GPX/1/1">',
           f"<metadata><name>{name} - plan de course</name><time>{_utc(start)}</time>"
           f"<desc>Temps total {plan['total']} - effort {round(plan['pct'] * 100)} % de la CS</desc></metadata>"]

    def wpt(lat, lon, ele, t_s, title, desc, sym):
        return (f'<wpt lat="{lat}" lon="{lon}"><ele>{ele}</ele><time>{_utc(start + timedelta(seconds=t_s))}</time>'
                f"<name>{_x(title)}</name><desc>{_x(desc)}</desc><sym>{sym}</sym></wpt>")

    def idx_at(km):
        return min(range(len(pf["km"])), key=lambda i: abs(pf["km"][i] - km))

    out.append(wpt(pf["lat"][0], pf["lon"][0], pf["ele"][0], 0, "Depart", f"Depart {start.strftime('%H:%M')}", "Flag, Green"))
    for i, s in enumerate(plan["sections"][:-1]):
        j = idx_at(s["end_km"])
        desc = f"km {s['end_km']:.1f} - passage {s['arrival']} ({s['clock']}) - arret {s['stop_min']:.0f} min"
        if s.get("cutoff"):
            desc += f" - barriere {s['cutoff']}"
        nxt = plan["sections"][i + 1]
        desc += f" - section suivante : {_pace(nxt['pace_min_km'])}/km"
        if nxt.get("power_w"):
            desc += f", {nxt['power_w']:.0f} W"
        out.append(wpt(pf["lat"][j], pf["lon"][j], pf["ele"][j], s["arrival_s"], f"R{i + 1} {s['to']}", desc, "Restaurant"))
    last = plan["sections"][-1]
    out.append(wpt(pf["lat"][-1], pf["lon"][-1], pf["ele"][-1], plan["total_s"], "Arrivee",
                   f"Arrivee estimee {plan['finish_clock']} ({plan['total']})", "Flag, Red"))

    out.append(f"<trk><name>{name}</name><trkseg>")
    prev = -1
    for la, lo, el, th in zip(pf["lat"], pf["lon"], pf["ele"], pf["t_h"]):
        ts = max(th * 3600, prev + 0.001)
        prev = ts
        out.append(f'<trkpt lat="{la}" lon="{lo}"><ele>{el}</ele><time>{_utc(start + timedelta(seconds=ts))}</time></trkpt>')
    out.append("</trkseg></trk></gpx>")
    return "\n".join(out)
