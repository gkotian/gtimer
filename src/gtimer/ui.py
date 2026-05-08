from __future__ import annotations

from datetime import datetime
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .allowance import AllowanceManager
from .config import AppConfig
from .formatting import format_duration, format_percent, format_signed_duration
from .i3_adapter import I3FocusAdapter
from .models import AllowanceLedgerEntry, AllowanceSummary, TrackerSnapshot
from .persistence import TimeStore
from .system import system_uptime_seconds
from .tracker import FocusTracker, start_of_today


APP_ID = "dev.gtimer.GTimer"


def run(config: AppConfig) -> int:
    app = GTimerApplication(config)
    return app.run(None)


class GTimerApplication(Gtk.Application):
    def __init__(self, config: AppConfig) -> None:
        super().__init__(application_id=APP_ID)
        self.config = config
        self.window: GTimerWindow | None = None

    def do_activate(self) -> None:
        if self.window is None:
            self.window = GTimerWindow(self, self.config)
        self.window.present()

    def do_shutdown(self) -> None:
        if self.window is not None:
            self.window.shutdown()
        Gtk.Application.do_shutdown(self)


class GTimerWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, config: AppConfig) -> None:
        super().__init__(application=app, title="gTimer")
        self.config = config
        self.store = TimeStore(config.database_path)
        self.tracker = FocusTracker(config, self.store)
        self.allowances = AllowanceManager(config, self.store)
        self.i3_connected = False
        self.i3_message = "connecting to i3 IPC"
        self.adapter: I3FocusAdapter | None = None
        self.snapshot: TrackerSnapshot | None = None

        self.set_default_size(1220, 760)
        self.set_size_request(900, 560)
        self._install_css()
        self._build()
        self._start_i3()
        GLib.timeout_add(config.refresh_interval_ms, self._refresh)
        self._refresh()

    def shutdown(self) -> None:
        if self.adapter is not None:
            self.adapter.stop()
        self.tracker.shutdown(time.time())
        self.store.close()

    def _install_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            window {
              background: #10141a;
              color: #eef2f5;
            }
            .root {
              background: #10141a;
              padding: 12px;
            }
            .panel {
              background: #151a21;
              border: 1px solid #2d3540;
              border-radius: 8px;
              padding: 16px;
            }
            .primary-panel {
              border-color: #3f7e42;
              background: #122018;
            }
            .timer-title {
              color: #74d35f;
              font-size: 28px;
              font-weight: 700;
            }
            .timer-value {
              color: #74d35f;
              font-size: 86px;
              font-weight: 800;
              font-feature-settings: "tnum";
            }
            .uptime-value {
              color: #f2f4f6;
              font-size: 66px;
              font-weight: 700;
              font-feature-settings: "tnum";
            }
            .muted {
              color: #aab2bd;
            }
            .ok {
              color: #74d35f;
            }
            .warn {
              color: #f0bf5a;
            }
            .negative {
              color: #ff6b6b;
            }
            .row-border {
              border-top: 1px solid #2d3540;
              padding-top: 8px;
              padding-bottom: 8px;
            }
            .table-header {
              color: #c9d0d8;
              font-weight: 700;
            }
            progressbar trough {
              background: #232a32;
              min-height: 8px;
              border-radius: 6px;
            }
            progressbar progress {
              background: #74d35f;
              min-height: 8px;
              border-radius: 6px;
            }
            button {
              background: #1b222b;
              color: #eef2f5;
              border: 1px solid #303947;
              border-radius: 6px;
              padding: 8px 12px;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.add_css_class("root")
        self.set_child(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.append(header)
        title = Gtk.Label(label="gTimer")
        title.set_hexpand(True)
        title.set_xalign(0)
        title.add_css_class("timer-title")
        header.append(title)
        self.regular_button = Gtk.Button(label="Regular View")
        self.regular_button.connect("clicked", lambda _button: self.stack.set_visible_child_name("regular"))
        header.append(self.regular_button)
        self.advanced_button = Gtk.Button(label="Advanced View")
        self.advanced_button.connect("clicked", lambda _button: self.stack.set_visible_child_name("advanced"))
        header.append(self.advanced_button)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.stack.set_vexpand(True)
        root.append(self.stack)

        self._build_regular_view()
        self._build_advanced_view()
        self.stack.set_visible_child_name("regular")

    def _build_regular_view(self) -> None:
        regular = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.stack.add_titled(_scrolled(regular), "regular", "Regular")

        top = Gtk.Grid(column_spacing=12, row_spacing=12)
        top.set_vexpand(False)
        regular.append(top)
        self.regular_timer_value = Gtk.Label(label="00:00:00")
        self.regular_timer_status = Gtk.Label(label="Waiting for focus data")
        timer_panel = self._timer_panel(
            self.config.prominent_timer().label,
            self.regular_timer_value,
            self.regular_timer_status,
            primary=True,
        )
        top.attach(timer_panel, 0, 0, 1, 1)

        self.regular_uptime_value = Gtk.Label(label="00:00:00")
        uptime_panel = self._timer_panel(
            "System Uptime",
            self.regular_uptime_value,
            Gtk.Label(label="since laptop powered on"),
            primary=False,
        )
        top.attach(uptime_panel, 1, 0, 1, 1)

        status_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_panel.add_css_class("panel")
        status_panel.set_vexpand(True)
        self.regular_ledger = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_panel.append(self.regular_ledger)
        regular.append(status_panel)

    def _build_advanced_view(self) -> None:
        advanced = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.stack.add_titled(_scrolled(advanced), "advanced", "Advanced")

        top = Gtk.Grid(column_spacing=12, row_spacing=12)
        advanced.append(top)
        self.advanced_timer_value = Gtk.Label(label="00:00:00")
        self.advanced_timer_status = Gtk.Label(label="Waiting for focus data")
        top.attach(
            self._timer_panel(
                self.config.prominent_timer().label,
                self.advanced_timer_value,
                self.advanced_timer_status,
                primary=True,
            ),
            0,
            0,
            1,
            1,
        )
        self.advanced_uptime_value = Gtk.Label(label="00:00:00")
        top.attach(
            self._timer_panel(
                "System Uptime",
                self.advanced_uptime_value,
                Gtk.Label(label="since laptop powered on"),
                primary=False,
            ),
            1,
            0,
            1,
            1,
        )
        top.set_column_homogeneous(True)

        focus_status = Gtk.Grid(column_spacing=16)
        focus_status.add_css_class("panel")
        advanced.append(focus_status)
        self.focus_label = _label("Currently Focused Window: none", xalign=0, wrap=False)
        self.focus_meta = _label("Class: -    Instance: -", xalign=0, wrap=False)
        self.advanced_status = _label("", xalign=0)
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_box.append(_label("Tracking Status", css_class="table-header"))
        status_box.append(self.advanced_status)
        focus_status.attach(self.focus_label, 0, 0, 1, 1)
        focus_status.attach(self.focus_meta, 1, 0, 1, 1)
        focus_status.attach(status_box, 2, 0, 1, 1)
        focus_status.set_column_homogeneous(True)

        table_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        table_panel.add_css_class("panel")
        table_panel.set_vexpand(True)
        table_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        table_header.append(_label("Time by Focused Window (Today)", css_class="table-header"))
        self.advanced_total = _label("Total Tracked Time: 00:00:00", xalign=1)
        self.advanced_total.set_hexpand(True)
        table_header.append(self.advanced_total)
        table_panel.append(table_header)
        self.advanced_table = Gtk.Grid(column_spacing=12, row_spacing=8)
        self.advanced_table.set_vexpand(True)
        table_panel.append(self.advanced_table)
        advanced.append(table_panel)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.add_css_class("panel")
        advanced.append(footer)
        self.database_label = _label(f"Database: {self.config.database_path}", xalign=0)
        self.database_label.set_hexpand(True)
        footer.append(self.database_label)
        self.last_updated_label = _label("Last updated: -", xalign=0.5)
        footer.append(self.last_updated_label)
        preferences = Gtk.Button(label="Preferences")
        preferences.connect("clicked", self._show_preferences)
        footer.append(preferences)
        quit_button = Gtk.Button(label="Quit")
        quit_button.connect("clicked", lambda _button: self.close())
        footer.append(quit_button)

    def _timer_panel(
        self,
        title: str,
        value_label: Gtk.Label,
        status_label: Gtk.Label,
        primary: bool,
    ) -> Gtk.Widget:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("panel")
        if primary:
            panel.add_css_class("primary-panel")
        panel.set_hexpand(True)
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("timer-title" if primary else "table-header")
        title_label.set_xalign(0.5)
        panel.append(title_label)
        value_label.add_css_class("timer-value" if primary else "uptime-value")
        value_label.set_xalign(0.5)
        panel.append(value_label)
        status_label.add_css_class("muted")
        status_label.set_xalign(0.5)
        panel.append(status_label)
        return panel

    def _start_i3(self) -> None:
        self.adapter = I3FocusAdapter(
            on_focus=lambda window: GLib.idle_add(self._handle_focus, window),
            on_status=lambda connected, message: GLib.idle_add(
                self._handle_i3_status,
                connected,
                message,
            ),
        )
        self.adapter.start()

    def _handle_i3_status(self, connected: bool, message: str | None) -> bool:
        self.i3_connected = connected
        self.i3_message = "i3 IPC connected" if connected else f"i3 IPC unavailable: {message}"
        self._refresh()
        return GLib.SOURCE_REMOVE

    def _handle_focus(self, window) -> bool:
        self.tracker.focus_changed(window, time.time(), time.monotonic())
        self._refresh()
        return GLib.SOURCE_REMOVE

    def _refresh(self) -> bool:
        now = time.time()
        monotonic_now = time.monotonic()
        self.snapshot = self.tracker.snapshot(now, monotonic_now, start_of_today(now))
        prominent = self.config.prominent_timer()
        all_time_usage = self.tracker.timer_total_seconds(prominent.name, now, monotonic_now)
        allowance = self.allowances.for_timer(prominent.name, all_time_usage, now)
        daily_usage = self.tracker.timer_usage_by_day(prominent.name, now)
        ledger_entries = self.allowances.recent_entries(prominent.name, daily_usage, now)
        uptime = system_uptime_seconds()
        self._render_snapshot(self.snapshot, uptime, now, allowance, ledger_entries)
        return GLib.SOURCE_CONTINUE

    def _render_snapshot(
        self,
        snapshot: TrackerSnapshot,
        uptime: float,
        now: float,
        allowance: AllowanceSummary | None,
        ledger_entries: tuple[AllowanceLedgerEntry, ...],
    ) -> None:
        if allowance is None:
            timer_text = format_duration(snapshot.prominent_timer.total_seconds)
        else:
            timer_text = format_signed_duration(allowance.balance_seconds)
        uptime_text = format_duration(uptime)
        status_text = self._prominent_status(snapshot, allowance)

        self.regular_timer_value.set_text(timer_text)
        self.advanced_timer_value.set_text(timer_text)
        self._set_negative(self.regular_timer_value, allowance)
        self._set_negative(self.advanced_timer_value, allowance)
        self.regular_uptime_value.set_text(uptime_text)
        self.advanced_uptime_value.set_text(uptime_text)
        self.regular_timer_status.set_text(status_text)
        self.advanced_timer_status.set_text(status_text)

        status = self._tracking_status()
        self.advanced_status.set_text(status)

        if snapshot.active_window is None:
            self.focus_label.set_text("Currently Focused Window: none tracked")
            self.focus_meta.set_text("Class: -    Instance: -")
        else:
            active = snapshot.active_window
            self.focus_label.set_text(f"Currently Focused Window: {active.display_title}")
            self.focus_meta.set_text(
                f"Class: {active.window_class or '-'}    Instance: {active.instance or '-'}"
            )

        self.advanced_total.set_text(
            f"Total Tracked Time: {format_duration(snapshot.total_tracked_seconds)}"
        )
        self.last_updated_label.set_text(
            f"Last updated: {datetime.fromtimestamp(now).strftime('%H:%M:%S')}"
        )

        self._render_allowance_ledger(ledger_entries)
        self._render_advanced_table(snapshot)

    def _prominent_status(
        self,
        snapshot: TrackerSnapshot,
        allowance: AllowanceSummary | None,
    ) -> str:
        if allowance is not None:
            return (
                f"Remaining allowance - played all time "
                f"{format_duration(allowance.usage_seconds)}"
            )
        if not self.i3_connected:
            return "Tracking unavailable"
        active = snapshot.active_window
        prominent = self.config.prominent_timer()
        if active is not None and snapshot.prominent_timer.total_seconds >= 0:
            from .matching import matches_rule

            if matches_rule(active, prominent.match):
                return "Counting"
        return "Paused"

    def _set_negative(
        self,
        label: Gtk.Label,
        allowance: AllowanceSummary | None,
    ) -> None:
        if allowance is not None and allowance.balance_seconds < 0:
            label.add_css_class("negative")
        else:
            label.remove_css_class("negative")

    def _tracking_status(self) -> str:
        if self.i3_connected:
            return "i3 IPC connected - tracking active"
        return self.i3_message

    def _render_allowance_ledger(
        self,
        entries: tuple[AllowanceLedgerEntry, ...],
    ) -> None:
        _clear_box(self.regular_ledger)
        if not entries:
            self.regular_ledger.append(
                _label("No Minecraft allowance entries yet.", css_class="muted")
            )
            return
        time_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        amount_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self.regular_ledger.append(self._ledger_header(time_group, amount_group))
        for entry in entries:
            self.regular_ledger.append(self._ledger_row(entry, time_group, amount_group))

    def _ledger_header(
        self,
        time_group: Gtk.SizeGroup,
        amount_group: Gtk.SizeGroup,
    ) -> Gtk.Widget:
        header = Gtk.Grid(column_spacing=10)
        time_header = _label("Time", css_class="table-header", xalign=0, wrap=False)
        time_group.add_widget(time_header)
        header.attach(time_header, 0, 0, 1, 1)
        amount_header = _label("Adjustment", css_class="table-header", xalign=1, wrap=False)
        amount_group.add_widget(amount_header)
        header.attach(amount_header, 1, 0, 1, 1)
        note = _label("Note", css_class="table-header", xalign=0, wrap=False)
        note.set_hexpand(True)
        header.attach(note, 2, 0, 1, 1)
        return header

    def _ledger_row(
        self,
        entry: AllowanceLedgerEntry,
        time_group: Gtk.SizeGroup,
        amount_group: Gtk.SizeGroup,
    ) -> Gtk.Widget:
        row = Gtk.Grid(column_spacing=10)
        row.add_css_class("row-border")
        time_text = datetime.fromtimestamp(entry.timestamp).isoformat(timespec="seconds")
        time_label = _label(time_text, xalign=0, wrap=False)
        time_group.add_widget(time_label)
        amount = _label(format_signed_duration(entry.amount_seconds, include_plus=True), xalign=1)
        amount.add_css_class("ok" if entry.amount_seconds >= 0 else "negative")
        amount_group.add_widget(amount)
        note = _label(entry.label, xalign=0, wrap=False)
        note.set_hexpand(True)
        row.attach(time_label, 0, 0, 1, 1)
        row.attach(amount, 1, 0, 1, 1)
        row.attach(note, 2, 0, 1, 1)
        return row

    def _render_advanced_table(self, snapshot: TrackerSnapshot) -> None:
        while child := self.advanced_table.get_first_child():
            self.advanced_table.remove(child)

        headers = ["Window Title", "Class", "Instance", "Total Time", "Percent", "Last Focused"]
        for column, header in enumerate(headers):
            self.advanced_table.attach(_label(header, css_class="table-header"), column, 0, 1, 1)

        if not snapshot.window_totals:
            empty = _label("No focused-window time recorded today.", css_class="muted")
            self.advanced_table.attach(empty, 0, 1, len(headers), 1)
            return

        for row_number, total in enumerate(snapshot.window_totals[:20], start=1):
            percent_value = total.total_seconds / snapshot.total_tracked_seconds if snapshot.total_tracked_seconds else 0
            last_focused = (
                datetime.fromtimestamp(total.last_focused_at).strftime("%H:%M:%S")
                if total.last_focused_at
                else "-"
            )
            values = [
                total.info.display_title,
                total.info.window_class or "-",
                total.info.instance or "-",
                format_duration(total.total_seconds),
                format_percent(percent_value),
                last_focused,
            ]
            for column, value in enumerate(values):
                label = _label(value, xalign=0 if column < 3 else 1, wrap=False)
                if column == 3:
                    label.add_css_class("ok")
                self.advanced_table.attach(label, column, row_number, 1, 1)

    def _show_preferences(self, _button: Gtk.Button) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Preferences",
            secondary_text=(
                "Edit config.toml, then restart gTimer for now.\n"
                f"Database: {self.config.database_path}"
            ),
        )
        dialog.connect("response", lambda dialog, _response: dialog.destroy())
        dialog.present()


def _label(
    text: str,
    xalign: float = 0,
    css_class: str | None = None,
    wrap: bool = True,
) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_xalign(xalign)
    label.set_wrap(wrap)
    if not wrap:
        label.set_ellipsize(Pango.EllipsizeMode.END)
    if css_class is not None:
        label.add_css_class(css_class)
    return label


def _scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_child(child)
    scrolled.set_hexpand(True)
    scrolled.set_vexpand(True)
    scrolled.set_propagate_natural_height(False)
    scrolled.set_propagate_natural_width(False)
    return scrolled


def _clear_box(box: Gtk.Box) -> None:
    while child := box.get_first_child():
        box.remove(child)
