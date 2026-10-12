"""Create a compact PDF report from actual experiment summaries and raw logs."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(__file__).parent
PROJECT = ROOT.parent
OUT = PROJECT / "output" / "pdf" / "agent_course_hw2_report.pdf"


def load_json(path: Path):
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run experiments and analysis scripts before creating the final report.")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    sel = load_json(ROOT / "results/selection_summary.json")
    loops = load_json(ROOT / "results/loop_summary.json")
    if not any(row.get("selection_evaluable") for row in sel):
        raise SystemExit("No successful tool-selection responses; the PDF report would misrepresent an incomplete local run.")
    if not any(row.get("evaluable") for row in loops):
        raise SystemExit("No evaluable loop episodes; the PDF report would misrepresent an incomplete local run.")
    chart = ROOT / "results/selection_accuracy.png"
    if not chart.exists():
        raise SystemExit("Missing accuracy chart; run experiment/analyze_selection.py first.")
    raw_models = Counter()
    raw_count = 0
    for p in ROOT.joinpath("logs").glob("selection_local_*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); raw_count += 1
                if r.get("model_path"):
                    raw_models[r["model_path"]] += 1
            except json.JSONDecodeError:
                pass
    model_text = "локальная Qwen3-4B (" + (raw_models.most_common(1)[0][0] if raw_models else "путь не записан") + ")"

    font_regular = Path("C:/Windows/Fonts/arial.ttf")
    font_bold = Path("C:/Windows/Fonts/arialbd.ttf")
    if not font_regular.exists():
        raise SystemExit("Arial Unicode font was not found; install/choose a Cyrillic-capable font before rendering.")
    pdfmetrics.registerFont(TTFont("Arial", str(font_regular)))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(font_bold if font_bold.exists() else font_regular)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleRu", parent=styles["Title"], fontName="Arial-Bold", fontSize=19, leading=23, alignment=TA_CENTER, textColor=colors.HexColor("#16324F"), spaceAfter=6))
    styles.add(ParagraphStyle(name="H2Ru", parent=styles["Heading2"], fontName="Arial-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#16324F"), spaceBefore=7, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyRu", parent=styles["BodyText"], fontName="Arial", fontSize=8.5, leading=11, spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallRu", parent=styles["BodyText"], fontName="Arial", fontSize=7, leading=9, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="CellRu", parent=styles["BodyText"], fontName="Arial", fontSize=7.2, leading=8.5))
    styles.add(ParagraphStyle(name="CellHeadRu", parent=styles["BodyText"], fontName="Arial-Bold", fontSize=7.2, leading=8.5, textColor=colors.white))
    OUT.parent.mkdir(parents=True, exist_ok=True)

    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5E1")); canvas.line(16*mm, 13*mm, 194*mm, 13*mm)
        canvas.setFont("Arial", 7); canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(16*mm, 8.5*mm, "Курс по агентам - домашнее задание 2")
        canvas.drawRightString(194*mm, 8.5*mm, f"Стр. {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=18*mm,
                            title="Экономика контекста, MCP и эксперимент выбора инструмента")
    story = [Paragraph("Выбор инструментов и петли агента", styles["TitleRu"]),
             Paragraph(f"Отчет по домашнему заданию 2 | {date.today().isoformat()}", styles["SmallRu"]), Spacer(1, 3*mm),
             Paragraph("Протокол", styles["H2Ru"]),
             Paragraph("Пул содержит 100 описаний: 4 инструмента расписания, 24 близких синтетических отвлекающих и 72 из других доменов. Для 30 вручную составленных запросов сравнивались A (все N описаний) и B (top-5 по cosine similarity локальных эмбеддингов) при N = 5, 20, 50, 100, по 3 повтора. Эмбеддинг: sentence-transformers/all-MiniLM-L6-v2; запросы и описания на английском. Генератор: " + model_text + "; temperature=0.25, top_p=0.85. Запуск локальный, расходы на API — 0; RTX 4050 Laptop, 6 ГБ VRAM, часть весов выполнялась на CPU.", styles["BodyRu"]),
             Paragraph("Точность выбора", styles["H2Ru"])]
    img = Image(str(chart), width=164*mm, height=100*mm, kind="proportional")
    story.append(img)
    story.append(Paragraph("Усы показывают 95%-й percentile bootstrap-интервал по 10 000 ресэмплов запросов; все три повтора одного запроса остаются вместе. Незавершенные и неуспешные вызовы считаются ошибками в полном знаменателе.", styles["SmallRu"]))

    story.append(Paragraph("Точность и входные токены", styles["H2Ru"]))
    headers = ["N", "Вариант", "Точность [95% ДИ]", "Recall@5", "Входные токены", "Успешно / 90"]
    data = [[Paragraph(h, styles["CellHeadRu"]) for h in headers]]
    for r in sel:
        accuracy_cell = (f"{r['accuracy']:.3f} [{r['accuracy_ci95_low']:.3f}; {r['accuracy_ci95_high']:.3f}]"
                         if r.get("accuracy") is not None else "N/A")
        data.append([Paragraph(str(r["N"]), styles["CellRu"]),
                     Paragraph("A: все N" if r["arm"] == "A_all" else "B: top-5", styles["CellRu"]),
                     Paragraph(accuracy_cell, styles["CellRu"]),
                     Paragraph(f"{r['recall_at_5']:.3f}", styles["CellRu"]),
                     Paragraph(f"{r['mean_input_tokens']:.1f}" if r["mean_input_tokens"] is not None else "нет данных", styles["CellRu"]),
                     Paragraph(f"{r['successes']}/{r['expected_attempts']}", styles["CellRu"])])
    tbl = Table(data, colWidths=[11*mm, 27*mm, 42*mm, 20*mm, 32*mm, 28*mm], repeatRows=1, hAlign="LEFT")
    tbl.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#16324F")), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#CBD5E1")),
                             ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F1F5F9")]), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                             ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    story += [tbl, Paragraph("Количество входных и выходных токенов измеряется локальным токенизатором Qwen3; ошибки генерации остаются в знаменателе. Coverage сохранен в CSV/JSON summary.", styles["SmallRu"]), PageBreak(),
              Paragraph("Петли, результаты и ограничения", styles["TitleRu"]), Paragraph("20 задач x 3 повтора; знаменатель каждого условия - 60 эпизодов.", styles["BodyRu"])]

    headers = ["Условие", "Петли", "Средние шаги", "Средние токены", "Успех", "Сбой модели"]
    data = [[Paragraph(h, styles["CellHeadRu"]) for h in headers]]
    labels = {"unstable_no_guard": "Пусто, без guard", "unstable_loopguard": "Пусто + LoopGuard", "hint_no_guard": "Пусто с подсказкой"}
    for r in loops:
        loop_cell = f"{r['loop_episodes']}/60 ({r['loop_rate']:.3f})" if r.get("loop_rate") is not None else "N/A"
        steps_cell = f"{r['mean_tool_steps']:.2f}" if r.get("mean_tool_steps") is not None else "N/A"
        tokens_cell = f"{r['mean_total_tokens']:.1f}" if r.get("mean_total_tokens") is not None else "N/A"
        data.append([Paragraph(labels.get(r["condition"], r["condition"]), styles["CellRu"]),
                     Paragraph(loop_cell, styles["CellRu"]), Paragraph(steps_cell, styles["CellRu"]),
                     Paragraph(tokens_cell, styles["CellRu"]),
                     Paragraph(f"{r['successes']}/60 ({r['success_rate']:.3f})", styles["CellRu"]),
                     Paragraph(str(r["runtime_failures"]), styles["CellRu"])])
    tbl = Table(data, colWidths=[37*mm, 31*mm, 27*mm, 29*mm, 32*mm, 24*mm], repeatRows=1)
    tbl.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#16324F")), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#CBD5E1")),
                             ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F1F5F9")]), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                             ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    story += [tbl, Paragraph("Пустые ответы генерировались с вероятностью 0.5. LoopGuard применял окно из 6 последних вызовов и останавливал последовательность после трех одинаковых вызовов подряд или паттерна A-B-A-B. В условии с подсказкой пустой результат сопровождался текстом «ничего не найдено; попробуйте другое значение date».", styles["BodyRu"]),
              Paragraph("Вывод", styles["H2Ru"])]
    best_loop = min((r for r in loops if r.get("loop_rate") is not None), key=lambda r: r["loop_rate"])
    story.append(Paragraph("Подсказка в ответе инструмента дала меньше циклов: 1/60 (1,7%) против 7/60 (11,7%) с LoopGuard; успех составил 60/60 против 53/60. В этом прогоне исправление ответа инструмента помогло сильнее guard в harness. Это наблюдение относится только к данному малому синтетическому прогону.", styles["BodyRu"]))
    story.append(Paragraph("Угрозы валидности", styles["H2Ru"]))
    threats = [
        "Небольшая ручная выборка из 30 запросов и повторение трех типов расписания ограничивают обобщение; повторы внутри запроса зависимы.",
        "Отвлекающие описания, расписание из трех синтетических записей и упрощенный harness могут отличаться от реального MCP-каталога и поведения агента.",
        "Результаты зависят от версии Qwen3-4B, настроек генерации и случайности; они не переносятся автоматически на другие модели и инструменты."
    ]
    for t in threats:
        story.append(Paragraph("- " + t, styles["BodyRu"]))
    story.append(Paragraph(f"Сырые логи выбора: {raw_count} записей. Полный JSONL каждого условия, сводки CSV/JSON и скрипты приложены в репозитории.", styles["SmallRu"]))
    doc.build(story, onFirstPage=page, onLaterPages=page)
    print(f"Created {OUT}")


if __name__ == "__main__":
    main()
