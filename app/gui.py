from __future__ import annotations

import json
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ai_helpers import ai_available, ai_correct_text, ai_extract_ticket, ai_summarize_ticket
from app.config import load_settings, save_settings
from app.discord_backend import DiscordBackend


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.backend = DiscordBackend()
        self.current_ticket = None
        self.current_draft = None

        self.setWindowTitle("Ticket-it")
        self.setMinimumSize(1200, 760)

        self._build_ui()
        self.refresh_all()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.dashboard_page = self._build_dashboard_page()
        self.tickets_page = self._build_tickets_page()
        self.new_ticket_page = self._build_new_ticket_page()
        self.settings_page = self._build_settings_page()

        for page in [self.dashboard_page, self.tickets_page, self.new_ticket_page, self.settings_page]:
            self.stack.addWidget(page)

        outer.addWidget(sidebar)
        outer.addWidget(self.stack, 1)

    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(230)
        sidebar.setMaximumWidth(230)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Ticket-it")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        self.dashboard_btn = QPushButton("Dashboard")
        self.tickets_btn = QPushButton("Tickets")
        self.new_ticket_btn = QPushButton("New Ticket")
        self.settings_btn = QPushButton("Settings")

        for button in [self.dashboard_btn, self.tickets_btn, self.new_ticket_btn, self.settings_btn]:
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(True)
            layout.addWidget(button)

        self.dashboard_btn.setChecked(True)

        self.dashboard_btn.clicked.connect(lambda: self._switch_page(0, self.dashboard_btn))
        self.tickets_btn.clicked.connect(lambda: self._switch_page(1, self.tickets_btn))
        self.new_ticket_btn.clicked.connect(lambda: self._switch_page(2, self.new_ticket_btn))
        self.settings_btn.clicked.connect(lambda: self._switch_page(3, self.settings_btn))

        layout.addStretch()

        self.connection_label = QLabel("Discord: Not connected")
        self.connection_label.setObjectName("mutedLabel")
        self.connection_label.setWordWrap(True)
        layout.addWidget(self.connection_label)

        self.ai_label = QLabel("AI: Ready" if ai_available() else "AI: Not configured")
        self.ai_label.setObjectName("mutedLabel")
        layout.addWidget(self.ai_label)

        return sidebar

    def _switch_page(self, index: int, active_button: QPushButton):
        self.stack.setCurrentIndex(index)
        for btn in [self.dashboard_btn, self.tickets_btn, self.new_ticket_btn, self.settings_btn]:
            btn.setChecked(btn is active_button)

    def _stat_card(self, label_text: str, value_text: str):
        card = QFrame()
        card.setObjectName("statCard")
        card.setMinimumHeight(110)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)

        label = QLabel(label_text)
        label.setObjectName("cardLabel")
        value = QLabel(value_text)
        value.setObjectName("cardValue")

        card.value_widget = value
        layout.addWidget(label)
        layout.addWidget(value)
        layout.addStretch()
        return card

    def _build_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        stats = QHBoxLayout()
        self.total_card = self._stat_card("Total Tickets", "0")
        self.open_card = self._stat_card("Open", "0")
        self.closed_card = self._stat_card("Closed", "0")
        self.assigned_card = self._stat_card("Assigned", "0")
        for card in [self.total_card, self.open_card, self.closed_card, self.assigned_card]:
            stats.addWidget(card)
        layout.addLayout(stats)

        self.dashboard_info = QTextEdit()
        self.dashboard_info.setReadOnly(True)
        layout.addWidget(self.dashboard_info, 1)

        row = QHBoxLayout()
        self.dashboard_refresh_btn = QPushButton("Refresh Tickets")
        self.dashboard_settings_btn = QPushButton("Open Settings")
        row.addWidget(self.dashboard_refresh_btn)
        row.addWidget(self.dashboard_settings_btn)
        row.addStretch()
        layout.addLayout(row)

        self.dashboard_refresh_btn.clicked.connect(self.refresh_all)
        self.dashboard_settings_btn.clicked.connect(lambda: self._switch_page(3, self.settings_btn))
        return page

    def _build_tickets_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Tickets")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by ticket id, customer, device, status, assigned tech")
        self.search_input.textChanged.connect(self.refresh_ticket_table)

        self.tickets_refresh_btn = QPushButton("Refresh")
        self.tickets_refresh_btn.clicked.connect(self.refresh_all)

        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.tickets_refresh_btn)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.tickets_table = QTableWidget(0, 7)
        self.tickets_table.setHorizontalHeaderLabels(
            ["ID", "Created", "Status", "Priority", "Customer", "Device", "Assigned"]
        )
        self.tickets_table.verticalHeader().setVisible(False)
        self.tickets_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tickets_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tickets_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tickets_table.setAlternatingRowColors(False)
        self.tickets_table.setWordWrap(False)
        self.tickets_table.setShowGrid(True)
        self.tickets_table.setSortingEnabled(False)
        self.tickets_table.setCornerButtonEnabled(False)
        self.tickets_table.itemSelectionChanged.connect(self.on_ticket_selected)

        header = self.tickets_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(80)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)   # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)   # Created
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)   # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)   # Priority
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)        # Customer
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)            # Device
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)   # Assigned

        self.tickets_table.setColumnWidth(0, 190)
        self.tickets_table.setColumnWidth(1, 150)
        self.tickets_table.setColumnWidth(2, 90)
        self.tickets_table.setColumnWidth(3, 90)
        self.tickets_table.setColumnWidth(4, 170)
        self.tickets_table.setColumnWidth(6, 110)

        left_layout.addWidget(self.tickets_table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        detail_title = QLabel("Ticket Details")
        detail_title.setObjectName("sectionTitle")
        right_layout.addWidget(detail_title)

        self.ticket_detail = QTextEdit()
        self.ticket_detail.setReadOnly(True)
        right_layout.addWidget(self.ticket_detail, 2)

        assign_row = QHBoxLayout()
        self.assign_input = QLineEdit()
        self.assign_input.setPlaceholderText("Assign to Discord username")
        self.assign_btn = QPushButton("Assign")
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["low", "normal", "high", "urgent"])
        self.priority_btn = QPushButton("Set Priority")
        assign_row.addWidget(self.assign_input, 1)
        assign_row.addWidget(self.assign_btn)
        assign_row.addWidget(self.priority_combo)
        assign_row.addWidget(self.priority_btn)
        right_layout.addLayout(assign_row)

        note_title = QLabel("Add Note")
        note_title.setObjectName("sectionTitle")
        right_layout.addWidget(note_title)

        self.note_input = QPlainTextEdit()
        self.note_input.setPlaceholderText("Write a technician note or update...")
        self.note_input.setFixedHeight(110)
        right_layout.addWidget(self.note_input)

        note_buttons = QHBoxLayout()
        self.add_note_btn = QPushButton("Add Note")
        self.fix_note_btn = QPushButton("AI Fix + Add")
        note_buttons.addWidget(self.add_note_btn)
        note_buttons.addWidget(self.fix_note_btn)
        note_buttons.addStretch()
        right_layout.addLayout(note_buttons)

        work_title = QLabel("Work Summary")
        work_title.setObjectName("sectionTitle")
        right_layout.addWidget(work_title)

        self.work_input = QPlainTextEdit()
        self.work_input.setPlaceholderText("Current work summary for this ticket...")
        self.work_input.setFixedHeight(120)
        right_layout.addWidget(self.work_input)

        work_buttons = QHBoxLayout()
        self.save_work_btn = QPushButton("Save Work Summary")
        self.summarize_btn = QPushButton("AI Summarize")
        self.close_btn = QPushButton("Close Ticket")
        self.reopen_btn = QPushButton("Reopen Ticket")
        work_buttons.addWidget(self.save_work_btn)
        work_buttons.addWidget(self.summarize_btn)
        work_buttons.addWidget(self.close_btn)
        work_buttons.addWidget(self.reopen_btn)
        right_layout.addLayout(work_buttons)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([1050, 850])

        layout.addWidget(splitter, 1)

        self.assign_btn.clicked.connect(self.assign_ticket)
        self.priority_btn.clicked.connect(self.set_priority)
        self.add_note_btn.clicked.connect(self.add_note)
        self.fix_note_btn.clicked.connect(self.fix_and_add_note)
        self.save_work_btn.clicked.connect(self.save_work_summary)
        self.summarize_btn.clicked.connect(self.ai_summarize_selected_ticket)
        self.close_btn.clicked.connect(self.close_ticket)
        self.reopen_btn.clicked.connect(self.reopen_ticket)

        return page

    def _build_new_ticket_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("New Ticket")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.customer_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.device_input = QLineEdit()
        self.issue_input = QPlainTextEdit()
        self.issue_input.setFixedHeight(120)
        self.probable_input = QLineEdit()
        self.create_priority_combo = QComboBox()
        self.create_priority_combo.addItems(["low", "normal", "high", "urgent"])

        form.addRow("Customer Name", self.customer_input)
        form.addRow("Phone", self.phone_input)
        form.addRow("Email", self.email_input)
        form.addRow("Device", self.device_input)
        form.addRow("Issue", self.issue_input)
        form.addRow("Probable Cause", self.probable_input)
        form.addRow("Priority", self.create_priority_combo)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.create_ticket_btn = QPushButton("Create Ticket")
        self.clear_form_btn = QPushButton("Clear")
        row.addWidget(self.create_ticket_btn)
        row.addWidget(self.clear_form_btn)
        row.addStretch()
        layout.addLayout(row)

        draft_title = QLabel("AI Draft Builder")
        draft_title.setObjectName("sectionTitle")
        layout.addWidget(draft_title)

        self.ai_draft_input = QPlainTextEdit()
        self.ai_draft_input.setPlaceholderText("Paste messy customer text here and let AI fill the ticket fields...")
        self.ai_draft_input.setFixedHeight(140)
        layout.addWidget(self.ai_draft_input)

        ai_row = QHBoxLayout()
        self.parse_ai_btn = QPushButton("Parse with AI")
        self.apply_draft_btn = QPushButton("Apply Draft to Form")
        ai_row.addWidget(self.parse_ai_btn)
        ai_row.addWidget(self.apply_draft_btn)
        ai_row.addStretch()
        layout.addLayout(ai_row)

        self.draft_preview = QTextEdit()
        self.draft_preview.setReadOnly(True)
        layout.addWidget(self.draft_preview, 1)

        self.create_ticket_btn.clicked.connect(self.create_ticket)
        self.clear_form_btn.clicked.connect(self.clear_ticket_form)
        self.parse_ai_btn.clicked.connect(self.parse_ai_draft)
        self.apply_draft_btn.clicked.connect(self.apply_draft)

        return page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.discord_token_input = QLineEdit()
        self.discord_token_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.guild_id_input = QLineEdit()
        self.backend_channel_input = QLineEdit()
        self.display_name_input = QLineEdit()

        self.groq_api_key_input = QLineEdit()
        self.groq_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Discord Bot Token", self.discord_token_input)
        form.addRow("Discord Guild ID", self.guild_id_input)
        form.addRow("Backend Channel ID", self.backend_channel_input)
        form.addRow("Display Name", self.display_name_input)
        form.addRow("Groq API Key", self.groq_api_key_input)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.save_settings_btn = QPushButton("Save Settings")
        self.test_connection_btn = QPushButton("Test Connection")
        row.addWidget(self.save_settings_btn)
        row.addWidget(self.test_connection_btn)
        row.addStretch()
        layout.addLayout(row)

        hint = QLabel(
            "Use a normal text channel like #ticket-it-backend. "
            "The app will create one thread per ticket inside that channel."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        self.settings_output = QTextEdit()
        self.settings_output.setReadOnly(True)
        layout.addWidget(self.settings_output, 1)

        self.save_settings_btn.clicked.connect(self.save_settings_from_form)
        self.test_connection_btn.clicked.connect(self.test_connection)

        return page

    def _current_actor(self) -> str:
        display_name = load_settings().get("display_name", "").strip()
        return display_name or "Ticket-it User"

    def _format_iso_datetime(self, value: str) -> str:
        if not value:
            return "—"
        try:
            cleaned = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt.strftime("%m-%d-%Y %I:%M %p")
        except Exception:
            return str(value)

    def _ticket_created_display(self, ticket: dict) -> str:
        ticket_id = str(ticket.get("ticket_id", ""))
        parts = ticket_id.split("/")
        if len(parts) >= 3:
            return f"{parts[1]} {parts[2]}"
        return self._format_iso_datetime(ticket.get("created_at", ""))

    def _parse_action_line(self, content: str) -> str | None:
        if not content.startswith("[TICKETIT_ACTION]"):
            return None

        raw = content[len("[TICKETIT_ACTION]"):].strip()
        try:
            payload = json.loads(raw)
            when = self._format_iso_datetime(payload.get("time", ""))
            actor = payload.get("actor", "") or "System"
            action_type = payload.get("type", "") or "update"
            text = payload.get("text", "") or ""
            return f"• {when}  |  {actor}  |  {action_type}\n  {text}"
        except Exception:
            return None

    def _render_ticket_detail(self, ticket: dict) -> str:
        status = ticket.get("status", "open").title()
        priority = ticket.get("priority", "normal").title()
        assigned = ticket.get("assigned_to", "") or "Unassigned"

        notes = ticket.get("notes", [])
        note_lines = []

        for note in notes:
            content = (note.get("content", "") or "").strip()

            if content.startswith("[TICKETIT_META]"):
                continue

            action_line = self._parse_action_line(content)
            if action_line:
                note_lines.append(action_line)
                continue

            when = self._format_iso_datetime(note.get("created_at", ""))
            author = note.get("author_name", "") or "Unknown"

            note_lines.append(f"• {when}  |  {author}\n  {content}")

        if not note_lines:
            note_lines.append("No notes yet.")

        return (
            f"=== TICKET OVERVIEW ===\n"
            f"ID: {ticket.get('ticket_id', '')}\n"
            f"Created: {self._ticket_created_display(ticket)}\n"
            f"Status: {status}\n"
            f"Priority: {priority}\n"
            f"Assigned To: {assigned}\n"
            f"Created By: {ticket.get('created_by', '') or '—'}\n"
            f"Thread ID: {ticket.get('thread_id', '') or '—'}\n\n"
            f"=== CUSTOMER ===\n"
            f"Name: {ticket.get('customer_name', '') or '—'}\n"
            f"Phone: {ticket.get('phone', '') or '—'}\n"
            f"Email: {ticket.get('email', '') or '—'}\n\n"
            f"=== DEVICE / ISSUE ===\n"
            f"Device: {ticket.get('device', '') or '—'}\n"
            f"Issue: {ticket.get('issue', '') or '—'}\n"
            f"Probable Cause: {ticket.get('probable_cause', '') or '—'}\n\n"
            f"=== WORK SUMMARY ===\n"
            f"{ticket.get('work_summary', '') or 'No work summary yet.'}\n\n"
            f"=== NOTES / TIMELINE ===\n"
            f"{chr(10).join(note_lines)}"
        )

    def refresh_all(self):
        self.load_settings_into_form()
        self.refresh_connection_status()
        self.refresh_dashboard()
        self.refresh_ticket_table()
        self.refresh_selected_ticket()
        self.ai_label.setText("AI: Ready" if ai_available() else "AI: Not configured")

    def load_settings_into_form(self):
        settings = load_settings()

        self.discord_token_input.setText(settings.get("discord_token", ""))
        self.guild_id_input.setText(settings.get("discord_guild_id", ""))
        self.backend_channel_input.setText(settings.get("backend_channel_id", ""))
        self.display_name_input.setText(settings.get("display_name", ""))
        self.groq_api_key_input.setText(settings.get("groq_api_key", ""))

        token_state = "Set" if settings.get("discord_token") else "Not set"
        groq_state = "Set" if settings.get("groq_api_key") else "Not set"

        self.settings_output.setPlainText(
            "Discord / AI configuration\n\n"
            f"Discord Token: {token_state}\n"
            f"Guild ID: {settings.get('discord_guild_id', '') or 'Not set'}\n"
            f"Backend Channel ID: {settings.get('backend_channel_id', '') or 'Not set'}\n"
            f"Display Name: {settings.get('display_name', '') or 'Not set'}\n"
            f"Groq API Key: {groq_state}\n\n"
            "Storage model:\n"
            "- parent text channel holds ticket seed messages\n"
            "- one Discord thread per ticket\n"
            "- first thread message stores the current metadata\n"
            "- later thread messages are notes and actions"
        )

    def save_settings_from_form(self):
        save_settings(
            {
                "discord_token": self.discord_token_input.text().strip(),
                "discord_guild_id": self.guild_id_input.text().strip(),
                "backend_channel_id": self.backend_channel_input.text().strip(),
                "display_name": self.display_name_input.text().strip(),
                "groq_api_key": self.groq_api_key_input.text().strip(),
            }
        )
        self.backend.reload()
        self.refresh_all()
        self.show_info("Settings saved.")

    def refresh_connection_status(self):
        self.connection_label.setText("Discord: Configured" if self.backend.configured() else "Discord: Not configured")

    def test_connection(self):
        try:
            self.show_info(self.backend.test_connection())
            self.refresh_connection_status()
        except Exception as e:
            self.show_error(str(e))

    def _set_card_value(self, card, value: str):
        card.value_widget.setText(value)

    def refresh_dashboard(self):
        if not self.backend.configured():
            for card in [self.total_card, self.open_card, self.closed_card, self.assigned_card]:
                self._set_card_value(card, "0")
            self.dashboard_info.setPlainText(
                "Discord backend is not configured yet.\n\n"
                "Open Settings and add:\n"
                "- Discord Bot Token\n"
                "- Discord Guild ID\n"
                "- Backend Channel ID\n"
                "- Display Name\n"
                "- Groq API Key"
            )
            return

        try:
            tickets = self.backend.list_tickets()
            open_count = sum(1 for t in tickets if t.get("status") == "open")
            closed_count = sum(1 for t in tickets if t.get("status") == "closed")
            assigned_count = sum(1 for t in tickets if t.get("assigned_to"))

            self._set_card_value(self.total_card, str(len(tickets)))
            self._set_card_value(self.open_card, str(open_count))
            self._set_card_value(self.closed_card, str(closed_count))
            self._set_card_value(self.assigned_card, str(assigned_count))

            self.dashboard_info.setPlainText(
                "Discord backend ready.\n\n"
                f"Current actor: {self._current_actor()}\n"
                f"Tickets loaded: {len(tickets)}\n"
                f"AI Available: {'Yes' if ai_available() else 'No'}\n\n"
                "Ticket storage:\n"
                "- one Discord thread per ticket\n"
                "- first thread message holds ticket metadata\n"
                "- later messages are notes and ticket history"
            )
        except Exception as e:
            self.dashboard_info.setPlainText(f"Failed to load tickets.\n\n{e}")

    def _find_row_by_ticket_id(self, ticket_id: str) -> int:
        for row in range(self.tickets_table.rowCount()):
            item = self.tickets_table.item(row, 0)
            if item and item.text() == str(ticket_id):
                return row
        return -1

    def _restore_selected_ticket_row(self, previous_ticket_id: str | None):
        if not previous_ticket_id:
            return

        row = self._find_row_by_ticket_id(previous_ticket_id)
        if row < 0:
            return

        self.tickets_table.blockSignals(True)
        self.tickets_table.selectRow(row)
        self.tickets_table.blockSignals(False)

        item = self.tickets_table.item(row, 0)
        if item:
            self.current_ticket = item.data(Qt.ItemDataRole.UserRole)

    def refresh_ticket_table(self):
        self.tickets_table.setRowCount(0)

        if not self.backend.configured():
            return

        try:
            tickets = self.backend.list_tickets()
        except Exception as e:
            self.show_error(str(e))
            return

        query = self.search_input.text().strip().lower()
        filtered = []

        for ticket in tickets:
            haystack = " ".join(
                [
                    str(ticket.get("ticket_id", "")),
                    ticket.get("status", ""),
                    ticket.get("priority", ""),
                    ticket.get("customer_name", ""),
                    ticket.get("device", ""),
                    ticket.get("assigned_to", ""),
                    ticket.get("issue", ""),
                ]
            ).lower()

            if query and query not in haystack:
                continue

            filtered.append(ticket)

        self.tickets_table.setRowCount(len(filtered))

        for row, ticket in enumerate(filtered):
            values = [
                ticket.get("ticket_id", ""),
                self._ticket_created_display(ticket),
                ticket.get("status", ""),
                ticket.get("priority", ""),
                ticket.get("customer_name", ""),
                ticket.get("device", ""),
                ticket.get("assigned_to", "") or "—",
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, ticket)
                self.tickets_table.setItem(row, col, item)

            status_item = self.tickets_table.item(row, 2)
            priority_item = self.tickets_table.item(row, 3)

            if ticket.get("status", "").lower() == "open":
                status_item.setForeground(QColor("#7ee7a8"))
            else:
                status_item.setForeground(QColor("#9fb3c8"))

            priority = ticket.get("priority", "").lower()
            if priority == "urgent":
                priority_item.setForeground(QColor("#ff6b81"))
            elif priority == "high":
                priority_item.setForeground(QColor("#ffb86c"))
            elif priority == "normal":
                priority_item.setForeground(QColor("#7fd4ff"))
            else:
                priority_item.setForeground(QColor("#b7c6d9"))

        self.tickets_table.resizeRowsToContents()

    def on_ticket_selected(self):
        items = self.tickets_table.selectedItems()
        if not items:
            self.current_ticket = None
            self.refresh_selected_ticket()
            return

        self.current_ticket = items[0].data(Qt.ItemDataRole.UserRole)
        self.refresh_selected_ticket()

    def refresh_selected_ticket(self):
        if not self.current_ticket:
            self.ticket_detail.setPlainText("Select a ticket to view details.")
            self.work_input.clear()
            self.note_input.clear()
            self.assign_input.clear()
            self.priority_combo.setCurrentText("low")
            return

        try:
            fresh = self.backend.get_ticket(str(self.current_ticket["thread_id"]))
            if fresh:
                self.current_ticket = fresh
        except Exception:
            pass

        ticket = self.current_ticket
        self.ticket_detail.setPlainText(self._render_ticket_detail(ticket))
        self.work_input.setPlainText(ticket.get("work_summary", ""))
        self.assign_input.setText(ticket.get("assigned_to", "") or "")
        priority = (ticket.get("priority", "") or "normal").lower()
        if priority in ["low", "normal", "high", "urgent"]:
            self.priority_combo.setCurrentText(priority)

    def create_ticket(self):
        if not self.backend.configured():
            self.show_error("Configure Discord in Settings first.")
            return

        customer_name = self.customer_input.text().strip()
        device = self.device_input.text().strip()
        issue = self.issue_input.toPlainText().strip()

        if not customer_name or not device or not issue:
            self.show_error("Customer name, device, and issue are required.")
            return

        try:
            self.backend.create_ticket(
                customer_name=customer_name,
                device=device,
                issue=issue,
                created_by=self._current_actor(),
                priority=self.create_priority_combo.currentText(),
                phone=self.phone_input.text().strip(),
                email=self.email_input.text().strip(),
                probable_cause=self.probable_input.text().strip(),
            )
            self.clear_ticket_form()
            self.refresh_all()
            self.show_info("Ticket created in Discord backend.")
            self._switch_page(1, self.tickets_btn)
        except Exception as e:
            self.show_error(str(e))

    def clear_ticket_form(self):
        self.customer_input.clear()
        self.phone_input.clear()
        self.email_input.clear()
        self.device_input.clear()
        self.issue_input.clear()
        self.probable_input.clear()
        self.ai_draft_input.clear()
        self.draft_preview.clear()
        self.current_draft = None
        self.create_priority_combo.setCurrentText("normal")

    def parse_ai_draft(self):
        raw = self.ai_draft_input.toPlainText().strip()
        if not raw:
            self.show_error("Paste messy customer text first.")
            return

        try:
            self.current_draft = ai_extract_ticket(raw)
            draft = self.current_draft
            self.draft_preview.setPlainText(
                "AI Draft\n\n"
                f"Customer Name: {draft.get('name', '') or 'N/A'}\n"
                f"Phone: {draft.get('phone', '') or 'N/A'}\n"
                f"Email: {draft.get('email', '') or 'N/A'}\n"
                f"Device: {draft.get('device', '') or 'N/A'}\n"
                f"Issue: {draft.get('issue', '') or 'N/A'}\n"
                f"Probable Cause: {draft.get('probable_cause', '') or 'N/A'}\n"
            )
        except Exception as e:
            self.show_error(f"AI parsing failed: {e}")

    def apply_draft(self):
        if not self.current_draft:
            self.show_error("No AI draft to apply.")
            return

        draft = self.current_draft
        self.customer_input.setText(draft.get("name", ""))
        self.phone_input.setText(draft.get("phone", ""))
        self.email_input.setText(draft.get("email", ""))
        self.device_input.setText(draft.get("device", ""))
        self.issue_input.setPlainText(draft.get("issue", ""))
        self.probable_input.setText(draft.get("probable_cause", ""))

    def _need_selected_ticket(self) -> bool:
        if not self.current_ticket:
            self.show_error("Select a ticket first.")
            return False
        return True

    def assign_ticket(self):
        if not self._need_selected_ticket():
            return

        username = self.assign_input.text().strip()
        if not username:
            self.show_error("Enter a Discord username to assign the ticket.")
            return

        try:
            self.backend.assign_ticket(self.current_ticket, username, self._current_actor())
            self.refresh_all()
            self.show_info(f"Assigned ticket to {username}.")
        except Exception as e:
            self.show_error(str(e))

    def set_priority(self):
        if not self._need_selected_ticket():
            return

        try:
            self.backend.set_priority(self.current_ticket, self.priority_combo.currentText(), self._current_actor())
            self.refresh_all()
            self.show_info("Priority updated.")
        except Exception as e:
            self.show_error(str(e))

    def add_note(self):
        if not self._need_selected_ticket():
            return

        note = self.note_input.toPlainText().strip()
        if not note:
            self.show_error("Write a note first.")
            return

        try:
            self.backend.add_note(self.current_ticket["thread_id"], self._current_actor(), note)
            self.note_input.clear()
            self.refresh_all()
        except Exception as e:
            self.show_error(str(e))

    def fix_and_add_note(self):
        if not self._need_selected_ticket():
            return

        note = self.note_input.toPlainText().strip()
        if not note:
            self.show_error("Write a note first.")
            return

        try:
            fixed = ai_correct_text(note)
            self.backend.add_note(self.current_ticket["thread_id"], self._current_actor(), fixed)
            self.note_input.clear()
            self.refresh_all()
            self.show_info("Corrected note added.")
        except Exception as e:
            self.show_error(str(e))

    def save_work_summary(self):
        if not self._need_selected_ticket():
            return

        text = self.work_input.toPlainText().strip()
        if not text:
            self.show_error("Enter a work summary first.")
            return

        try:
            self.backend.update_work_summary(self.current_ticket, text, self._current_actor())
            self.refresh_all()
            self.show_info("Work summary updated.")
        except Exception as e:
            self.show_error(str(e))

    def ai_summarize_selected_ticket(self):
        if not self._need_selected_ticket():
            return

        try:
            summary = ai_summarize_ticket(self.current_ticket)
            new_summary = summary.get("customer_summary", "") or summary.get("actions_taken", "")
            self.work_input.setPlainText(new_summary)
            self.backend.update_work_summary(self.current_ticket, new_summary, self._current_actor())
            self.refresh_all()
            self.show_info(
                f"Problem: {summary.get('problem', '')}\n\n"
                f"Diagnosis: {summary.get('diagnosis', '')}\n\n"
                f"Actions Taken: {summary.get('actions_taken', '')}\n\n"
                f"Current Status: {summary.get('current_status', '')}\n\n"
                f"Customer Summary: {summary.get('customer_summary', '')}"
            )
        except Exception as e:
            self.show_error(str(e))

    def close_ticket(self):
        if not self._need_selected_ticket():
            return

        try:
            self.backend.close_ticket(self.current_ticket, self._current_actor())
            self.refresh_all()
        except Exception as e:
            self.show_error(str(e))

    def reopen_ticket(self):
        if not self._need_selected_ticket():
            return

        try:
            self.backend.reopen_ticket(self.current_ticket, self._current_actor())
            self.refresh_all()
        except Exception as e:
            self.show_error(str(e))

    def show_error(self, text: str):
        QMessageBox.critical(self, "Error", text)

    def show_info(self, text: str):
        QMessageBox.information(self, "Info", text)