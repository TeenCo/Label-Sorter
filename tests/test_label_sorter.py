"""End-to-end tests of the analysis -> generation -> deletion pipeline (no GUI needed)."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pypdf import PdfReader, PdfWriter  # noqa: E402

from core import file_manager  # noqa: E402
from core import pdf_processor  # noqa: E402
from core.classifier import OcrEngine, classify_text  # noqa: E402
from core.models import AskContext, FlagKind, Platform, Status  # noqa: E402
from core.pdf_analyzer import AnalysisHooks, analyze  # noqa: E402
from sample_data import (A4, FIVE_BY_SEVEN, LABEL, LabelSpec, a4_two_up, build_pdf, label_page)  # noqa: E402

MARK = re.compile(r"ORDER-\d{4}")


class Scripted(AnalysisHooks):
    """Hooks that answer the "which platform?" question from a script (simulated user input)."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.asked: list[AskContext] = []

    def ask_platform(self, ctx):
        self.asked.append(ctx)
        return self.answers.pop(0) if self.answers else None


# ---- independent helpers (pypdf only, so they do not depend on PyMuPDF) ----
def markers(path, page_index):
    return MARK.findall(PdfReader(str(path)).pages[page_index].extract_text() or "")


def page_sequence(path):
    """ORDER markers of each (uncropped) page, in order."""
    return [markers(path, i)[0] for i in range(len(PdfReader(str(path)).pages))]


def crop_topleft(page):
    cb, mb = page.cropbox, page.mediabox
    return (float(cb.left - mb.left), float(mb.top - cb.top), float(cb.right - mb.left), float(mb.top - cb.bottom))


def page_size(page):
    return (float(page.cropbox.width), float(page.cropbox.height))


def content_bytes(page):
    return page.get_contents().get_data()


def image_hashes(page):
    out = []
    xo = (page.get("/Resources") or {}).get("/XObject") or {}
    for key in xo:
        obj = xo[key].get_object()
        if obj.get("/Subtype") == "/Image":
            out.append(hashlib.sha1(obj.get_data()).hexdigest())
    return sorted(out)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lblsort_"))
        self.out = self.tmp / "out"
        self.counter = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def order(self):
        self.counter += 1
        return f"ORDER-{self.counter:04d}"

    def pdf(self, name, pages):
        return build_pdf(self.tmp / name, pages)

    def run_all(self, paths, answers=()):
        hooks = Scripted(answers)
        result = analyze([Path(p) for p in paths], hooks)
        gen = pdf_processor.generate_outputs(result, self.out, date_str="2026-11-15")
        return result, gen, hooks


class TestSingleAndMixed(Base):
    def test01_single_ebay(self):
        f = self.pdf("a.pdf", [label_page("ebay", self.order())])
        result, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(set(gen.outputs), {"PRINTS", "EBAY"})
        self.assertEqual(gen.outputs["EBAY"].name, "2026-11-15_EBAY.pdf")
        self.assertEqual(result.stats().ebay_labels, 1)
        self.assertEqual(result.stats().standard_pages, 1)

    def test02_single_tiktok(self):
        f = self.pdf("a.pdf", [label_page("tiktok", self.order())])
        result, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(set(gen.outputs), {"PRINTS", "TIKTOK"})
        self.assertEqual(result.stats().tiktok_labels, 1)

    def test03_multiple_files_mixed_keep_file_order(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001")])
        b = self.pdf("b.pdf", [label_page("tiktok", "ORDER-0002")])
        c = self.pdf("c.pdf", [label_page("ebay", "ORDER-0003")])
        # Deliberately NOT alphabetical: the given order must win.
        result, gen, _ = self.run_all([c, a, b])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(page_sequence(gen.outputs["EBAY"]), ["ORDER-0003", "ORDER-0001"])
        self.assertEqual(page_sequence(gen.outputs["TIKTOK"]), ["ORDER-0002"])
        self.assertEqual(page_sequence(gen.outputs["PRINTS"]), ["ORDER-0003", "ORDER-0001", "ORDER-0002"])

    def test04_multipage_pdf_with_both_platforms(self):
        f = self.pdf("m.pdf", [label_page("ebay", "ORDER-0001"), label_page("tiktok", "ORDER-0002"),
                               label_page("ebay", "ORDER-0003")])
        result, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(page_sequence(gen.outputs["EBAY"]), ["ORDER-0001", "ORDER-0003"])
        self.assertEqual(page_sequence(gen.outputs["TIKTOK"]), ["ORDER-0002"])
        self.assertEqual([p.prints_page for p in result.pages], [1, 2, 3])


class TestA4(Base):
    def test05_a4_two_labels_same_platform(self):
        e1, e2 = LabelSpec("ebay", "ORDER-0001"), LabelSpec("ebay", "ORDER-0002")
        f = self.pdf("a4.pdf", [a4_two_up(e1, e2)])
        result, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        page = result.pages[0]
        self.assertEqual(len(page.labels), 2)
        self.assertEqual(page.size_class, "A4")
        self.assertIn(FlagKind.MULTI_LABEL, {fl.kind for fl in page.flags()})
        reader = PdfReader(str(gen.outputs["EBAY"]))
        self.assertEqual(len(reader.pages), 2)
        for page_out, spec in zip(reader.pages, (e1, e2)):
            x0, y0, x1, y1 = crop_topleft(page_out)
            self.assertAlmostEqual(x1 - x0, 288, delta=0.6)
            self.assertAlmostEqual(y1 - y0, 432, delta=0.6)
            self.assertLessEqual(x0, spec.x + 0.5)           # fully contains its own label
            self.assertGreaterEqual(x1, spec.x + spec.w - 0.5)
        # left label first, and the crops do not overlap each other
        self.assertLess(crop_topleft(reader.pages[0])[2], crop_topleft(reader.pages[1])[0] + 1)
        self.assertEqual(len(PdfReader(str(gen.outputs["PRINTS"])).pages), 1)

    def test06_a4_two_labels_different_platforms(self):
        e, t = LabelSpec("ebay", "ORDER-0001"), LabelSpec("tiktok", "ORDER-0002")
        f = self.pdf("a4.pdf", [a4_two_up(e, t)])
        result, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual([lab.platform for lab in result.pages[0].labels], [Platform.EBAY, Platform.TIKTOK])
        eb, tk = PdfReader(str(gen.outputs["EBAY"])), PdfReader(str(gen.outputs["TIKTOK"]))
        self.assertEqual((len(eb.pages), len(tk.pages)), (1, 1))
        self.assertLess(crop_topleft(eb.pages[0])[2], 300)     # eBay crop is the LEFT label
        self.assertGreater(crop_topleft(tk.pages[0])[0], 290)  # TikTok crop is the RIGHT label
        rows = result.exception_rows()
        self.assertEqual((rows[0].page_number, rows[0].prints_page), (1, 1))

    def test06b_unsplittable_a4_is_kept_whole_and_flagged(self):
        # Labels with no gap between them cannot be separated reliably.
        e, t = LabelSpec("ebay", "ORDER-0001"), LabelSpec("ebay", "ORDER-0002")
        e.x, e.y, t.x, t.y = 2.0, 40.0, 2.0 + 288, 40.0
        f = self.pdf("touch.pdf", [(A4, [e, t])])
        result, gen, _ = self.run_all([f], answers=["E"])
        page = result.pages[0]
        self.assertTrue(gen.ok, gen.errors)
        if len(page.labels) == 1:   # not separated -> must be flagged for manual handling
            self.assertIn(FlagKind.MULTI_UNSPLIT, {fl.kind for fl in page.flags()})
            self.assertTrue(page.needs_review)
            self.assertEqual(page_size(PdfReader(str(gen.outputs["EBAY"])).pages[0]), (A4[0], A4[1]))


class TestUnrecognized(Base):
    def test07_terminal_classification(self):
        f = self.pdf("u.pdf", [label_page("ebay", "ORDER-0001"), label_page(None, "ORDER-0002"),
                               label_page("ebay", "ORDER-0003")])
        result, gen, hooks = self.run_all([f], answers=["T"])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(len(hooks.asked), 1)
        self.assertEqual((hooks.asked[0].filename, hooks.asked[0].page_number), ("u.pdf", 2))
        self.assertEqual(page_sequence(gen.outputs["EBAY"]), ["ORDER-0001", "ORDER-0003"])
        self.assertEqual(page_sequence(gen.outputs["TIKTOK"]), ["ORDER-0002"])
        self.assertEqual(result.pages[1].labels[0].method, "manual")

    def test07b_skip_is_reported_not_silent(self):
        f = self.pdf("u.pdf", [label_page(None, "ORDER-0001"), label_page("ebay", "ORDER-0002")])
        result, gen, _ = self.run_all([f], answers=["S"])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(page_sequence(gen.outputs["EBAY"]), ["ORDER-0002"])
        self.assertEqual(len(PdfReader(str(gen.outputs["PRINTS"])).pages), 2)   # still in PRINTS
        row = result.exception_rows()[0]
        self.assertEqual((row.page_number, row.prints_page), (1, 1))
        self.assertIn("skipped", row.reason)
        self.assertTrue(gen.report_path.exists() and gen.csv_path.exists())
        self.assertIn("skipped", gen.report_path.read_text(encoding="utf-8"))
        self.assertIn("u.pdf", gen.csv_path.read_text(encoding="utf-8-sig"))

    def test07c_unanswered_blocks_generation(self):
        f = self.pdf("u.pdf", [label_page(None, "ORDER-0001")])
        result, gen, _ = self.run_all([f], answers=[])      # no terminal answer
        self.assertFalse(gen.ok)
        self.assertEqual(len(result.pending_labels()), 1)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test07d_both_platform_names_is_ambiguous(self):
        f = self.pdf("b.pdf", [label_page("both", "ORDER-0001")])
        result, _, hooks = self.run_all([f], answers=["E"])
        self.assertIn("both", hooks.asked[0].reason)
        self.assertEqual(classify_text("eBay and TikTok").platform, None)

    def test07e_answer_codes_and_ask_context(self):
        self.assertIs(Platform.from_code("i"), Platform.INPOST)
        self.assertIs(Platform.from_code(" E "), Platform.EBAY)
        self.assertIsNone(Platform.from_code("S"))
        self.assertIsNone(Platform.from_code(None))
        f = self.pdf("b.pdf", [label_page("both", "ORDER-0001")])
        _, _, hooks = self.run_all([f], answers=["T"])
        ctx = hooks.asked[0]
        self.assertTrue(ctx.ambiguous)
        self.assertEqual(set(ctx.candidates), {Platform.EBAY, Platform.TIKTOK})

    @unittest.skipUnless(OcrEngine().available, "Tesseract not available")
    def test07f_ocr_fallback_reads_platform_from_picture(self):
        f = self.pdf("img.pdf", [label_page("tiktok", "ORDER-0001", platform_as_image=True)])
        result, gen, hooks = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(hooks.asked, [])
        self.assertEqual(result.pages[0].labels[0].method, "ocr")
        self.assertEqual(result.pages[0].labels[0].platform, Platform.TIKTOK)


class TestSizesAndErrors(Base):
    def test08_non_standard_size(self):
        f = self.pdf("odd.pdf", [(FIVE_BY_SEVEN, [LabelSpec("ebay", "ORDER-0001", w=360, h=504)])])
        result, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(result.pages[0].size_class, "other")
        self.assertIn(FlagKind.NON_STANDARD_SIZE, {fl.kind for fl in result.pages[0].flags()})
        self.assertEqual(page_size(PdfReader(str(gen.outputs["EBAY"])).pages[0]), FIVE_BY_SEVEN)
        self.assertEqual(page_size(PdfReader(str(gen.outputs["PRINTS"])).pages[0]), FIVE_BY_SEVEN)

    def test09_corrupted_encrypted_empty_alongside_valid(self):
        good1 = self.pdf("g1.pdf", [label_page("ebay", "ORDER-0001")])
        bad = self.tmp / "bad.pdf"
        bad.write_bytes(b"%PDF-1.4\nthis is not a real pdf \x00\x01\x02")
        empty = self.tmp / "empty.pdf"
        empty.write_bytes(b"")
        locked = self.tmp / "locked.pdf"
        w = PdfWriter()
        w.append(str(good1))
        w.encrypt("secret")
        with open(locked, "wb") as fh:
            w.write(fh)
        good2 = self.pdf("g2.pdf", [label_page("tiktok", "ORDER-0002")])
        result, gen, _ = self.run_all([good1, bad, empty, locked, good2])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual({i.path.name for i in result.issues}, {"bad.pdf", "empty.pdf", "locked.pdf"})
        self.assertIn("password", next(i.reason for i in result.issues if i.path.name == "locked.pdf"))
        self.assertEqual(page_sequence(gen.outputs["PRINTS"]), ["ORDER-0001", "ORDER-0002"])
        self.assertEqual([f.path.name for f in result.good_files], ["g1.pdf", "g2.pdf"])
        self.assertIn("bad.pdf", gen.report_path.read_text())

    def test09b_duplicates_are_flagged_not_removed(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001")])
        b = self.pdf("b.pdf", [label_page("ebay", "ORDER-0001")])
        result, gen, _ = self.run_all([a, b])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(len(PdfReader(str(gen.outputs["EBAY"])).pages), 2)
        self.assertIn(FlagKind.DUPLICATE, {fl.kind for fl in result.pages[1].flags()})
        self.assertFalse(result.pages[1].needs_review)


class TestDeletionAndFailure(Base):
    def test10_declining_deletion_keeps_everything(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001")])
        result, gen, _ = self.run_all([a])
        shown = []
        res = file_manager.request_deletion([f.path for f in result.good_files], gen.verified,
                                            lambda files: shown.append(list(files)) or False, gen.outputs.values())
        self.assertEqual(len(shown), 1)            # exactly ONE confirmation, listing all files
        self.assertTrue(a.exists())
        self.assertEqual(res.deleted, [])

    def test10b_confirmed_deletion_only_touches_selected_files(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001")])
        b = self.pdf("b.pdf", [label_page("tiktok", "ORDER-0002")])
        unrelated = self.tmp / "keep_me.pdf"
        unrelated.write_bytes(b"unrelated")
        bad = self.tmp / "bad.pdf"
        bad.write_bytes(b"garbage")
        result, gen, _ = self.run_all([a, b, bad])
        candidates = [f.path for f in result.good_files]
        res = file_manager.request_deletion(candidates, gen.verified, lambda files: True, gen.outputs.values())
        self.assertEqual(sorted(p.name for p in res.deleted), ["a.pdf", "b.pdf"])
        self.assertTrue(unrelated.exists() and bad.exists())     # unrelated + failed files survive
        self.assertTrue(all(p.exists() for p in gen.outputs.values()))

    def test11_generation_failure_leaves_originals_and_no_outputs(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001")])
        b = self.pdf("b.pdf", [label_page("tiktok", "ORDER-0002")])
        before = {p.name: p.read_bytes() for p in (a, b)}
        calls = {"n": 0}
        real = pdf_processor._save_document

        def flaky(doc, path):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk full (simulated)")
            real(doc, path)

        with mock.patch.object(pdf_processor, "_save_document", flaky):
            result, gen, _ = self.run_all([a, b])
        self.assertFalse(gen.ok)
        self.assertTrue(any("disk full" in e for e in gen.errors))
        self.assertEqual(list(self.out.glob("*")), [])           # no partial/final output left
        self.assertEqual({p.name: p.read_bytes() for p in (a, b)}, before)
        res = file_manager.request_deletion([a, b], gen.verified, lambda files: True)
        self.assertEqual(res.deleted, [])
        self.assertTrue(a.exists() and b.exists())

    def test11b_never_overwrites_existing_outputs(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001")])
        _, gen1, _ = self.run_all([a])
        _, gen2, _ = self.run_all([a])
        self.assertNotEqual(gen1.outputs["EBAY"], gen2.outputs["EBAY"])
        self.assertTrue(gen1.outputs["EBAY"].exists() and gen2.outputs["EBAY"].exists())


class TestIntegrity(Base):
    def test12_prints_keeps_sequence_and_dimensions(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001"), (A4, [LabelSpec("tiktok", "ORDER-0002", x=5, y=40)])])
        b = self.pdf("b.pdf", [(FIVE_BY_SEVEN, [LabelSpec("ebay", "ORDER-0003", w=360, h=504)]),
                               label_page("tiktok", "ORDER-0004")])
        c = self.pdf("c.pdf", [a4_two_up(LabelSpec("ebay", "ORDER-0005"), LabelSpec("tiktok", "ORDER-0006"))])
        result, gen, _ = self.run_all([b, a, c])
        self.assertTrue(gen.ok, gen.errors)
        src_pages = [p for f in (b, a, c) for p in PdfReader(str(f)).pages]
        out_pages = PdfReader(str(gen.outputs["PRINTS"])).pages
        self.assertEqual(len(out_pages), len(src_pages))
        for s, o in zip(src_pages, out_pages):
            self.assertEqual(page_size(s), page_size(o))
            self.assertEqual(content_bytes(s), content_bytes(o))
            self.assertEqual(MARK.findall(s.extract_text()), MARK.findall(o.extract_text()))
        self.assertEqual([p.prints_page for p in result.pages], [1, 2, 3, 4, 5])
        self.assertEqual([(p.filename, p.page_number) for p in result.pages],
                         [("b.pdf", 1), ("b.pdf", 2), ("a.pdf", 1), ("a.pdf", 2), ("c.pdf", 1)])

    def test13_barcodes_and_qr_codes_are_not_rasterized_or_altered(self):
        e = LabelSpec("ebay", "ORDER-0001", raster_qr=True)
        std = self.pdf("std.pdf", [label_page("tiktok", "ORDER-0002", raster_qr=True)])
        a4 = self.pdf("a4.pdf", [a4_two_up(e, LabelSpec("ebay", "ORDER-0003"))])
        result, gen, _ = self.run_all([std, a4])
        self.assertTrue(gen.ok, gen.errors)
        src_std = PdfReader(str(std)).pages[0]
        out_tt = PdfReader(str(gen.outputs["TIKTOK"])).pages[0]
        self.assertEqual(content_bytes(src_std), content_bytes(out_tt))       # content stream identical
        self.assertEqual(image_hashes(src_std), image_hashes(out_tt))         # raster QR bytes identical
        src_a4 = PdfReader(str(a4)).pages[0]
        out_eb = PdfReader(str(gen.outputs["EBAY"])).pages
        for page in out_eb:                                                   # cropped pages: same streams
            self.assertEqual(content_bytes(src_a4), content_bytes(page))
            self.assertEqual(image_hashes(src_a4), image_hashes(page))
        self.assertGreater(len(content_bytes(src_std)), 1000)                 # vector barcode drawn in the stream
        self.assertEqual(len(image_hashes(out_tt)), 1)                        # only the original image, no new ones

    def test14_platform_pdfs_keep_download_order_with_mixed_pages(self):
        a = self.pdf("a.pdf", [label_page("ebay", "ORDER-0001"), label_page("tiktok", "ORDER-0002"),
                               label_page("ebay", "ORDER-0003")])
        b = self.pdf("b.pdf", [label_page("tiktok", "ORDER-0004")])
        c = self.pdf("c.pdf", [a4_two_up(LabelSpec("tiktok", "ORDER-0005"), LabelSpec("ebay", "ORDER-0006")),
                               label_page("ebay", "ORDER-0007")])
        result, gen, _ = self.run_all([a, b, c])
        self.assertTrue(gen.ok, gen.errors)
        eb = PdfReader(str(gen.outputs["EBAY"])).pages
        tk = PdfReader(str(gen.outputs["TIKTOK"])).pages
        self.assertEqual(len(eb), 4)
        self.assertEqual(len(tk), 3)
        self.assertEqual([markers(gen.outputs["EBAY"], i)[0] for i in (0, 1)], ["ORDER-0001", "ORDER-0003"])
        self.assertEqual(markers(gen.outputs["EBAY"], 3)[0], "ORDER-0007")
        # page 3 of eBay is the cropped RIGHT-hand label of the A4 page (ORDER-0006)
        self.assertGreater(crop_topleft(eb[2])[0], 290)
        self.assertLess(crop_topleft(tk[2])[2], 300)                          # TikTok A4 label is the LEFT one
        self.assertEqual(markers(gen.outputs["TIKTOK"], 0)[0], "ORDER-0002")
        self.assertEqual(markers(gen.outputs["TIKTOK"], 1)[0], "ORDER-0004")


class TestFileManager(Base):
    def test_selection_sorting_and_names(self):
        names = ["Download_10.pdf", "Download_2.pdf", "notes.txt", "Download_2.pdf"]
        for n in names:
            (self.tmp / n).write_bytes(b"%PDF-")
        sel = file_manager.normalize_selection([self.tmp / n for n in names])
        self.assertEqual([p.name for p in sel], ["Download_10.pdf", "Download_2.pdf"])
        self.assertEqual([p.name for p in file_manager.order_by_name(sel)], ["Download_2.pdf", "Download_10.pdf"])
        os.utime(sel[1], (1_000_000, 1_000_000))
        os.utime(sel[0], (2_000_000, 2_000_000))
        self.assertEqual(len(file_manager.order_by_download_time(sel)), 2)
        self.assertRegex(file_manager.date_string(), r"^\d{4}-\d{2}-\d{2}$")


class TestInPost(Base):
    def test_classify_text_inpost(self):
        c = classify_text("InPost shop - Scotmid Co-op Scotstoun")
        self.assertIs(c.platform, Platform.INPOST)
        self.assertIsNone(classify_text("signpost, sent in post").platform)
        both = classify_text("eBay InPost")
        self.assertIsNone(both.platform)
        self.assertTrue(both.ambiguous)
        self.assertEqual(set(both.candidates), {Platform.EBAY, Platform.INPOST})
        self.assertIn("both", both.evidence)

    def test_single_inpost_label_gets_its_own_file(self):
        f = self.pdf("a.pdf", [label_page("inpost", self.order())])
        result, gen, hooks = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(set(gen.outputs), {"PRINTS", "INPOST"})
        self.assertEqual(gen.outputs["INPOST"].name, "2026-11-15_INPOST.pdf")
        self.assertEqual(result.stats().inpost_labels, 1)
        self.assertEqual(hooks.asked, [])

    def test_three_platforms_split_into_three_files_in_order(self):
        f = self.pdf("m.pdf", [label_page("ebay", "ORDER-0001"), label_page("inpost", "ORDER-0002"),
                               label_page("tiktok", "ORDER-0003"), label_page("inpost", "ORDER-0004")])
        _, gen, _ = self.run_all([f])
        self.assertTrue(gen.ok, gen.errors)
        self.assertEqual(page_sequence(gen.outputs["EBAY"]), ["ORDER-0001"])
        self.assertEqual(page_sequence(gen.outputs["TIKTOK"]), ["ORDER-0003"])
        self.assertEqual(page_sequence(gen.outputs["INPOST"]), ["ORDER-0002", "ORDER-0004"])
        self.assertEqual(len(PdfReader(str(gen.outputs["PRINTS"])).pages), 4)

    def test_ebay_plus_inpost_text_asks_and_answer_i_routes_to_inpost(self):
        f = self.pdf("b.pdf", [label_page("ebay_inpost", "ORDER-0001")])
        result, gen, hooks = self.run_all([f], answers=["I"])
        self.assertTrue(gen.ok, gen.errors)
        self.assertTrue(hooks.asked[0].ambiguous)
        self.assertEqual(page_sequence(gen.outputs["INPOST"]), ["ORDER-0001"])
        self.assertNotIn("EBAY", gen.outputs)

    def test_output_names_never_overwrite_with_four_kinds(self):
        self.out.mkdir(parents=True)
        (self.out / "2026-11-15_INPOST.pdf").write_bytes(b"x")
        names = file_manager.unique_output_names(self.out, "2026-11-15")
        self.assertEqual(set(names), {"EBAY", "TIKTOK", "INPOST", "PRINTS"})
        self.assertTrue(all(p.name.endswith("_2.pdf") for p in names.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
