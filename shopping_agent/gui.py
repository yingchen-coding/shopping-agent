"""Desktop UI over the same client, matcher, and scoring code the CLI uses.

The display rules here are domain rules, not styling choices: Unknown renders as
"?" and never as 0, a Representative Price is never labelled a lowest price, and
vetoed products appear in their own list rather than as low-ranked results.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import db
from .preferences import Preference, merge
from .rank import Vetoed, build_candidate, rank
from .recalls import RecallError, fetch_recalls, match
from .scoring import UNKNOWN
from .search import MAX_WATCHES, SearchClient


class Worker(QObject):
    """Runs one zero-argument callable off the UI thread."""

    finished = Signal(object, str)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self._fn(), "")
        except Exception as exc:  # noqa: BLE001 — surfaced in the UI, not swallowed
            self.finished.emit(None, str(exc))


class _Threaded(QWidget):
    """Shared plumbing so a tab never blocks the UI on a network call."""

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: Worker | None = None

    def _run(self, fn, on_done) -> None:
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = Worker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(lambda r, e: self._settle(r, e, on_done))
        self._thread.start()

    def _settle(self, result, error, on_done) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        on_done(result, error)


def format_score(value) -> str:
    """Render a Score for display.

    Unknown shows as "?" and never as a number: a product that could not be
    assessed must not be readable as one that scored badly. See docs/adr/0002.
    """
    return "  ?  " if value is UNKNOWN else f"{float(value):.2f}"


def _prefs_for(conn, member: str | None, category: str | None):
    def load(scope, key):
        if not key:
            return []
        return [
            Preference(r["dimension"], r["weight"], r["note"],
                       frozenset(a for a in r["avoid"].split(",") if a))
            for r in db.get_preferences(conn, scope, key)
        ]

    return merge(load("member", member), load("category", category))


class SearchTab(_Threaded):
    def __init__(self, conn) -> None:
        super().__init__()
        self.conn = conn
        self._rows: list = []
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("what do you need? e.g. toddler booster seat")
        self.query.returnPressed.connect(self.start)
        controls.addWidget(self.query, 1)

        self.member = QComboBox()
        self.member.addItem("(anyone)", None)
        for m in db.list_members(conn):
            self.member.addItem(m["name"], m["name"])
        controls.addWidget(QLabel("for"))
        controls.addWidget(self.member)

        self.category = QLineEdit()
        self.category.setPlaceholderText("category")
        self.category.setMaximumWidth(110)
        controls.addWidget(self.category)

        self.budget = QDoubleSpinBox()
        self.budget.setPrefix("$")
        self.budget.setMaximum(100000)
        self.budget.setSpecialValueText("no budget")
        controls.addWidget(self.budget)

        self.button = QPushButton("Search")
        self.button.clicked.connect(self.start)
        controls.addWidget(self.button)
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Score", "Evidence", "Product", "Price (one merchant)", "Open"]
        )
        head = self.table.horizontalHeader()
        for col, width in ((0, 70), (1, 80), (3, 170), (4, 60)):
            head.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.cellClicked.connect(self._maybe_open)
        layout.addWidget(self.table, 2)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Select a product to see why it scored what it did.")
        layout.addWidget(self.detail, 1)

    @Slot()
    def start(self) -> None:
        query = self.query.text().strip()
        if not query:
            return
        member = self.member.currentData()
        category = self.category.text().strip() or None
        budget = self.budget.value() or None

        self.button.setEnabled(False)
        self.progress.show()
        self.status.setText(f"Searching for {query!r}…")
        self.status.setStyleSheet("color:#65716d;")

        def work():
            client = SearchClient()
            products = client.search(query, limit=20)
            try:
                records = fetch_recalls(query)
                note = f"{len(records)} CPSC recall record(s) checked"
            except RecallError as exc:
                # A failed safety check must never look like a clean result.
                records, note = [], f"⚠️ CPSC check FAILED ({exc}) — safety NOT verified"
            return products, records, note, member, category, budget

        self._run(work, self._done)

    def _done(self, result, error) -> None:
        self.button.setEnabled(True)
        self.progress.hide()
        if error:
            self.status.setText(f"Error: {error}")
            self.status.setStyleSheet("color:#b54137;")
            return

        products, records, note, member_name, category, budget = result
        prefs = _prefs_for(self.conn, member_name, category)
        member = db.get_member(self.conn, member_name) if member_name else None
        blocklist = db.get_blocklist(self.conn)

        candidates, vetoed = [], []
        for product in products:
            text = f"{product.title} {product.merchant or ''}".lower()
            blocked = next((b for b in blocklist if b["value"] in text), None)
            if blocked:
                vetoed.append(Vetoed(product, f"{blocked['kind']} '{blocked['value']}' is blocklisted"))
                continue
            hit = match(product.title, product.brand_guess, records) if records else None
            if hit and hit.vetoes:
                vetoed.append(Vetoed(product, f"confirmed recall — {hit.why}", hit.record.url))
                continue
            candidates.append(build_candidate(product, prefs, recall=hit, budget=budget, member=member))

        self._rows = rank(candidates)
        failed = note.startswith("⚠️")
        self.status.setText(
            f"{len(products)} product(s) · {note} · {len(self._rows)} ranked, {len(vetoed)} excluded"
            + (" · nothing stored for this search, so the baseline "
               f"({', '.join(prefs.dimensions)}) was used" if prefs.is_baseline else "")
        )
        self.status.setStyleSheet("color:#b54137;" if failed else "color:#166534;")

        self.table.setRowCount(0)
        for i, c in enumerate(self._rows):
            self.table.insertRow(i)
            value = c.score.value
            score_item = QTableWidgetItem(format_score(value))
            if value is UNKNOWN:
                score_item.setForeground(QColor("#a26300"))
                score_item.setToolTip("Not enough known dimensions to score — not a low score.")
            self.table.setItem(i, 0, score_item)
            self.table.setItem(i, 1, QTableWidgetItem(c.score.evidence_ratio))
            title = QTableWidgetItem(("⚠️ " if c.warnings else "") + c.product.title)
            self.table.setItem(i, 2, title)
            price = c.product.representative_price
            price_item = QTableWidgetItem(
                f"{f'${price:.2f}' if price is not None else 'no price'} at "
                f"{c.product.merchant or '?'}"
            )
            price_item.setToolTip(
                "One merchant's price chosen by the search source — not the lowest available."
            )
            self.table.setItem(i, 3, price_item)
            open_item = QTableWidgetItem("Open →" if c.product.link else "")
            open_item.setForeground(QColor("#0369a1"))
            self.table.setItem(i, 4, open_item)

        for v in vetoed:
            i = self.table.rowCount()
            self.table.insertRow(i)
            excluded = QTableWidgetItem("EXCLUDED")
            excluded.setForeground(QColor("#b54137"))
            self.table.setItem(i, 0, excluded)
            self.table.setItem(i, 1, QTableWidgetItem("—"))
            item = QTableWidgetItem(f"✗ {v.product.title}  ({v.reason})")
            item.setForeground(QColor("#b54137"))
            self.table.setItem(i, 2, item)
        self.table.resizeRowsToContents()

    def _show_detail(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._rows):
            self.detail.clear()
            return
        c = self._rows[row]
        lines = [c.product.title, ""]
        for d in c.score.dimensions:
            mark = "?" if not d.is_known else f"{float(d.value):.2f}"
            lines.append(f"  {d.dimension:15} {mark:>5}  ×{d.weight:<4g}  {d.reason}")
        if c.score.unknown:
            lines.append("")
            lines.append("  '?' means the listing did not say — excluded from the score, "
                         "not counted as zero.")
        if c.warnings:
            lines.append("")
            lines += [f"  ⚠️  {w}" for w in c.warnings]
        if c.product.multiple_merchants:
            lines.append("")
            lines.append("  Other merchants also sell this; their prices were not retrieved.")
        self.detail.setPlainText("\n".join(lines))

    def _maybe_open(self, row: int, column: int) -> None:
        if column == 4 and 0 <= row < len(self._rows):
            link = self._rows[row].product.link
            if link:
                QDesktopServices.openUrl(QUrl(link))


class WatchTab(_Threaded):
    def __init__(self, conn) -> None:
        super().__init__()
        self.conn = conn
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("what to watch")
        controls.addWidget(self.query, 1)
        self.target = QDoubleSpinBox()
        self.target.setPrefix("$")
        self.target.setMaximum(100000)
        self.target.setValue(20)
        controls.addWidget(QLabel("notify below"))
        controls.addWidget(self.target)
        add = QPushButton("Add watch")
        add.clicked.connect(self.add_watch)
        controls.addWidget(add)
        self.check = QPushButton("Check all now")
        self.check.clicked.connect(self.check_now)
        controls.addWidget(self.check)
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Target", "State", "Last seen", "Watching"])
        head = self.table.horizontalHeader()
        for col, width in ((0, 40), (1, 80), (2, 150), (3, 170)):
            head.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)
        head.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_history)
        layout.addWidget(self.table, 1)

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setPlaceholderText(
            "Select a watch to see its price history — forward-only, from when it was created."
        )
        layout.addWidget(self.history, 1)
        self.refresh()

    def refresh(self) -> None:
        watches = db.list_watches(self.conn)
        self.table.setRowCount(0)
        self._watches = watches
        for i, w in enumerate(watches):
            self.table.insertRow(i)
            snaps = db.price_history(self.conn, w["id"])
            prices = [s["price"] for s in snaps if s["price"] is not None]
            self.table.setItem(i, 0, QTableWidgetItem(str(w["id"])))
            self.table.setItem(i, 1, QTableWidgetItem(f"${w['target_price']:.2f}"))
            state = QTableWidgetItem("notified" if w["notified_at"] else "watching")
            if w["notified_at"]:
                state.setForeground(QColor("#166534"))
            self.table.setItem(i, 2, state)
            self.table.setItem(i, 3, QTableWidgetItem(
                f"${prices[-1]:.2f}  ({len(snaps)} snapshot(s))" if prices
                else f"no price yet ({len(snaps)} snapshot(s))"))
            self.table.setItem(i, 4, QTableWidgetItem(w["query"]))

    @Slot()
    def add_watch(self) -> None:
        query = self.query.text().strip()
        if not query:
            return
        if len(db.list_watches(self.conn)) >= MAX_WATCHES:
            reply = QMessageBox.question(
                self, "Watch limit",
                f"{MAX_WATCHES} watches already exist. Each costs one search per day against a "
                "free monthly allowance. Add anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        db.add_watch(self.conn, query, self.target.value())
        self.query.clear()
        self.refresh()

    @Slot()
    def check_now(self) -> None:
        from .watch import check_all

        self.check.setEnabled(False)
        self.progress.show()
        self.status.setText("Checking every watch…")
        self.status.setStyleSheet("color:#65716d;")
        # Interactive, so the reserve held back from scheduled work does not apply.
        self._run(lambda: check_all(self.conn, SearchClient(), respect_reserve=False), self._done)

    def _done(self, results, error) -> None:
        self.check.setEnabled(True)
        self.progress.hide()
        if error:
            self.status.setText(f"Error: {error}")
            self.status.setStyleSheet("color:#b54137;")
            return
        crossed = [r for r in results if r.crossed]
        failed = [r for r in results if r.error]
        parts = [f"{len(results)} checked"]
        if crossed:
            parts.append(f"{len(crossed)} crossed below target — notified")
        if failed:
            parts.append(f"{len(failed)} failed")
        self.status.setText(" · ".join(parts))
        self.status.setStyleSheet("color:#b54137;" if failed else "color:#166534;")
        self.refresh()

    def _show_history(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._watches):
            return
        watch = self._watches[row]
        snaps = db.price_history(self.conn, watch["id"])
        lines = [
            f"{watch['query']}   target ${watch['target_price']:.2f}",
            "forward-only — nothing is known about prices before this watch was created",
            "",
        ]
        for s in snaps:
            price = f"${s['price']:.2f}" if s["price"] is not None else "(none found)"
            lines.append(f"  {s['observed_at'][:19]}  {price:>12}   "
                         f"{(s['merchant'] or ''):16} {(s['title'] or '')[:44]}")
        self.history.setPlainText("\n".join(lines))


class PreferenceTab(QWidget):
    def __init__(self, conn) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Stored locally only — this never leaves the machine and is not in the repository."
        ))
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        lines = ["MEMBERS", ""]
        for m in db.list_members(conn):
            age = db.member_age_years(m)
            lines.append(f"  {m['name']:12} {m['birthdate'] or '(adult)':12} "
                         f"{f'{age:.1f}y' if age is not None else ''}")
        lines += ["", "PREFERENCES", "",
                  "  member-level and category-level merge at search time; stricter side wins", ""]
        for r in db.all_preferences(conn):
            avoid = f"   avoid: {r['avoid']}" if r["avoid"] else ""
            note = f"   “{r['note']}”" if r["note"] else ""
            lines.append(f"  {r['scope']:9} {r['scope_key']:12} {r['dimension']:15} "
                         f"×{r['weight']:<4g}{avoid}{note}")
        blocked = db.get_blocklist(conn)
        lines += ["", "BLOCKLIST (these can exclude a product outright)", ""]
        lines += [f"  {b['kind']:9} {b['value']}   {b['reason']}" for b in blocked] or ["  (none)"]
        self.text.setPlainText("\n".join(lines))


class MainWindow(QMainWindow):
    def __init__(self, conn) -> None:
        super().__init__()
        self.setWindowTitle("Shopping Agent")
        self.resize(1080, 760)
        tabs = QTabWidget()
        tabs.addTab(SearchTab(conn), "Search")
        tabs.addTab(WatchTab(conn), "Watches")
        tabs.addTab(PreferenceTab(conn), "Preferences")
        self.setCentralWidget(tabs)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Shopping Agent")
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f7faf8"))
    app.setPalette(palette)
    app.setFont(QFont(".AppleSystemUIFont", 13))

    try:
        conn = db.connect()
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(None, "Cannot open the preference store", str(exc))
        return 1

    window = MainWindow(conn)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
