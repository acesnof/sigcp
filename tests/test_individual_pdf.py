import unittest
from collections import Counter
from unittest.mock import patch

from app.reports.individual_pdf import gerar_pdf_welfare_individual


class FakeCanvas:
    instances = []

    def __init__(self, *args, **kwargs):
        self.page = 1
        self.rectangles = {1: []}
        self.__class__.instances.append(self)

    def rect(self, x, y, width, height, **kwargs):
        self.rectangles[self.page].append((x, y, width, height))

    def showPage(self):
        self.page += 1
        self.rectangles[self.page] = []

    def stringWidth(self, text, font, size):
        return len(str(text)) * size * 0.5

    def setLineWidth(self, *args): pass
    def setFillColor(self, *args): pass
    def setFont(self, *args): pass
    def drawCentredString(self, *args): pass
    def drawRightString(self, *args): pass
    def drawString(self, *args): pass
    def setStrokeColor(self, *args): pass
    def line(self, *args): pass
    def save(self): pass


class IndividualPdfTwoPagesTest(unittest.TestCase):
    def test_person_rows_have_exactly_the_same_height_on_both_pages(self):
        for number_of_days in (28, 29, 30, 31):
            with self.subTest(number_of_days=number_of_days):
                FakeCanvas.instances.clear()
                days = [
                    {"dia": day, "weekday": "D", "data_str": f"2026-01-{day:02d}"}
                    for day in range(1, number_of_days + 1)
                ]
                rows = [
                    {"identificacao": f"Pessoa {index}", "cells": {}}
                    for index in range(12)
                ]

                with patch("app.reports.individual_pdf.canvas.Canvas", FakeCanvas):
                    gerar_pdf_welfare_individual(
                        "ignored.pdf", "Titulo", "Periodo", days, rows, {}, modo_paginas=2
                    )

                drawn = FakeCanvas.instances[-1].rectangles
                self.assertEqual(set(drawn), {1, 2})

                # As linhas das pessoas repetem a mesma altura muitas mais
                # vezes do que os cabecalhos e a linha de totais.
                heights = []
                for page in (1, 2):
                    counts = Counter(round(rect[3], 9) for rect in drawn[page])
                    heights.append(counts.most_common(1)[0][0])

                self.assertEqual(heights[0], heights[1])


if __name__ == "__main__":
    unittest.main()
