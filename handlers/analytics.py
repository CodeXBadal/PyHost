"""7-day analytics table for a project."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import get_project, recent_resources, recent_crashes
from utils.keyboards import back_to_panel_keyboard
from utils.messages import ANALYTICS_HEAD, NOT_FOUND
from handlers.auth import require_member


def _format_table(days: int, requests_per_day, crashes_per_day):
    today = datetime.now(timezone.utc).date()
    rows = ["Day            Reqs   Crash",
            "─" * 28]
    total_r = total_c = 0
    peak_day = "-"; peak_val = -1
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        r = requests_per_day.get(d, 0)
        c = crashes_per_day.get(d, 0)
        total_r += r; total_c += c
        if r > peak_val:
            peak_val = r; peak_day = d.strftime("%a %d")
        rows.append(f"{d.strftime('%a %d'):<12} {r:>6}   {c:>5}")
    rows.append("─" * 28)
    rows.append(f"{'Total':<12} {total_r:>6}   {total_c:>5}")
    return "\n".join(rows), peak_day, total_r, total_c


@require_member
async def analytics_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("ana_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        try:
            await q.message.edit_text(NOT_FOUND)
        except Exception:
            await q.message.reply_text(NOT_FOUND)
        return

    days = 7
    res = await recent_resources(pid, days=days)
    crashes = await recent_crashes(pid, days=days)

    req_pd = defaultdict(int)
    for r in res:
        req_pd[r["timestamp"].date()] += int(r.get("requests_count", 0))
    crash_pd = defaultdict(int)
    for c in crashes:
        crash_pd[c["timestamp"].date()] += 1

    table, peak, total_r, total_c = _format_table(days, req_pd, crash_pd)
    uptime_pct = max(0.0, 100.0 - total_c * 5)   # naive estimate
    await q.message.edit_text(
        ANALYTICS_HEAD.format(name=proj["name"], days=days, table=table,
                              peak=peak, uptime_pct=f"{uptime_pct:.1f}",
                              total_crashes=total_c),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_panel_keyboard(pid),
    )
