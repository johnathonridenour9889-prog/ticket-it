from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

import requests

from app.config import load_settings

API_BASE = "https://discord.com/api/v10"
META_PREFIX = "[TICKETIT_META]"
ACTION_PREFIX = "[TICKETIT_ACTION]"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DiscordBackendError(Exception):
    pass


class DiscordBackend:
    def __init__(self):
        self.settings = load_settings()

    def reload(self):
        self.settings = load_settings()

    def configured(self) -> bool:
        return all(
            [
                self.settings.get("discord_token", "").strip(),
                self.settings.get("discord_guild_id", "").strip(),
                self.settings.get("backend_channel_id", "").strip(),
            ]
        )

    def _headers(self) -> dict:
        token = self.settings.get("discord_token", "").strip()
        return {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ):
        if not self.configured():
            raise DiscordBackendError(
                "Discord is not configured. Open Settings and add token, guild ID, and backend channel ID."
            )

        response = requests.request(
            method=method,
            url=f"{API_BASE}{path}",
            headers=self._headers(),
            json=json_data,
            params=params,
            timeout=30,
        )

        if response.status_code >= 400:
            raise DiscordBackendError(f"Discord API error {response.status_code}: {response.text[:500]}")

        if response.text:
            return response.json()
        return None

    def test_connection(self) -> str:
        self.reload()
        me = self._request("GET", "/users/@me")
        channel = self._request("GET", f"/channels/{self.settings['backend_channel_id']}")
        return f"Connected as {me.get('username', 'bot')} to #{channel.get('name', 'unknown')}"

    def _split_content(self, content: str, limit: int = 1999):
        if content is None:
            return []

        content = str(content).strip()
        if not content:
            return []

        if len(content) <= limit:
            return [content]

        chunks = []
        remaining = content

        while len(remaining) > limit:
            split_at = remaining.rfind("\n", 0, limit)
            if split_at <= 0:
                split_at = remaining.rfind(" ", 0, limit)
            if split_at <= 0:
                split_at = limit

            chunk = remaining[:split_at].strip()
            if chunk:
                chunks.append(chunk)

            remaining = remaining[split_at:].strip()

        if remaining:
            chunks.append(remaining)

        return chunks

    def _post_message(self, channel_id: str, content: str) -> dict:
        return self._request("POST", f"/channels/{channel_id}/messages", {"content": content})

    def _edit_message(self, channel_id: str, message_id: str, content: str):
        return self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", {"content": content})

    def _post_split_message(self, channel_id: str, content: str) -> dict:
        chunks = self._split_content(content, 1999)
        if not chunks:
            raise DiscordBackendError("Cannot send an empty Discord message.")

        last = None
        for chunk in chunks:
            last = self._post_message(channel_id, chunk)
        return last

    def _start_thread_from_message(self, channel_id: str, message_id: str, name: str) -> dict:
        return self._request(
            "POST",
            f"/channels/{channel_id}/messages/{message_id}/threads",
            {
                "name": name[:95],
                "auto_archive_duration": 10080,
            },
        )

    def _get_messages(self, channel_id: str, limit: int = 100):
        return self._request("GET", f"/channels/{channel_id}/messages", params={"limit": limit}) or []

    def _get_active_threads(self):
        data = self._request("GET", f"/guilds/{self.settings['discord_guild_id']}/threads/active")
        threads = data.get("threads", []) if isinstance(data, dict) else []
        parent_id = str(self.settings["backend_channel_id"])
        return [thread for thread in threads if str(thread.get("parent_id")) == parent_id]

    def _get_archived_threads(self):
        parent_id = str(self.settings["backend_channel_id"])
        archived_threads = []
        seen_ids = set()
        before = None

        while True:
            params = {"limit": 100}
            if before:
                params["before"] = before

            data = self._request(
                "GET",
                f"/channels/{parent_id}/threads/archived/public",
                params=params,
            ) or {}

            threads = data.get("threads", [])
            if not threads:
                break

            for thread in threads:
                thread_id = str(thread.get("id", ""))
                if not thread_id or thread_id in seen_ids:
                    continue
                if str(thread.get("parent_id")) != parent_id:
                    continue
                archived_threads.append(thread)
                seen_ids.add(thread_id)

            if not data.get("has_more"):
                break

            last_thread = threads[-1]
            before = (
                last_thread.get("thread_metadata", {}).get("archive_timestamp")
                or last_thread.get("archive_timestamp")
            )
            if not before:
                break

        return archived_threads

    def _get_all_ticket_threads(self):
        all_threads = []
        seen_ids = set()

        for thread in self._get_active_threads() + self._get_archived_threads():
            thread_id = str(thread.get("id", ""))
            if not thread_id or thread_id in seen_ids:
                continue
            all_threads.append(thread)
            seen_ids.add(thread_id)

        return all_threads

    def _ensure_thread_writable(self, thread_id: str):
        thread = self._request("GET", f"/channels/{thread_id}")
        metadata = thread.get("thread_metadata", {}) if isinstance(thread, dict) else {}

        update_payload = {}

        if metadata.get("archived"):
            update_payload["archived"] = False

        if metadata.get("auto_archive_duration") != 10080:
            update_payload["auto_archive_duration"] = 10080

        if update_payload:
            self._request("PATCH", f"/channels/{thread_id}", update_payload)

    def _trim_text(self, value: str, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _meta_to_message(self, meta: dict) -> str:
        payload = meta.copy()
        payload["customer_name"] = self._trim_text(payload.get("customer_name", ""), 120)
        payload["phone"] = self._trim_text(payload.get("phone", ""), 80)
        payload["email"] = self._trim_text(payload.get("email", ""), 120)
        payload["device"] = self._trim_text(payload.get("device", ""), 200)
        payload["issue"] = self._trim_text(payload.get("issue", ""), 500)
        payload["probable_cause"] = self._trim_text(payload.get("probable_cause", ""), 500)
        payload["assigned_to"] = self._trim_text(payload.get("assigned_to", ""), 120)
        payload["work_summary"] = self._trim_text(payload.get("work_summary", ""), 500)
        payload["created_by"] = self._trim_text(payload.get("created_by", ""), 120)
        payload.pop("notes", None)
        return META_PREFIX + "\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _action_to_message(self, action_type: str, actor: str, text: str) -> str:
        payload = {
            "type": action_type,
            "actor": self._trim_text(actor, 120),
            "time": now_iso(),
            "text": self._trim_text(text, 1200),
        }
        return ACTION_PREFIX + "\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _parse_meta(self, content: str):
        if not content.startswith(META_PREFIX):
            return None

        raw = content[len(META_PREFIX):].strip()

        try:
            return json.loads(raw)
        except Exception:
            try:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
            except Exception:
                pass

        return None

    def _thread_snapshot(self, thread: dict):
        messages = self._get_messages(str(thread["id"]), limit=100)
        if not messages:
            return None

        oldest_first = list(reversed(messages))
        meta = None
        meta_msg = None
        for message in oldest_first:
            parsed = self._parse_meta(message.get("content", ""))
            if parsed:
                meta = parsed
                meta_msg = message
                break

        if not meta or not meta_msg:
            return None

        notes = []
        for message in oldest_first:
            if str(message.get("id")) == str(meta_msg.get("id")):
                continue
            notes.append(
                {
                    "message_id": message.get("id", ""),
                    "author_name": message.get("author", {}).get("username", "unknown"),
                    "content": message.get("content", ""),
                    "created_at": message.get("timestamp", ""),
                }
            )

        meta["thread_id"] = str(thread["id"])
        meta["thread_name"] = thread.get("name", "")
        meta["meta_message_id"] = str(meta_msg["id"])
        meta["notes"] = notes
        return meta

    def list_tickets(self):
        self.reload()
        tickets = []
        for thread in self._get_all_ticket_threads():
            try:
                snap = self._thread_snapshot(thread)
                if snap:
                    tickets.append(snap)
            except Exception:
                continue
        tickets.sort(key=lambda t: t.get("ticket_id", ""), reverse=True)
        return tickets

    def get_ticket(self, thread_id: str):
        messages = self._get_messages(thread_id, limit=100)
        if not messages:
            return None

        oldest_first = list(reversed(messages))
        meta = None
        meta_msg = None
        for message in oldest_first:
            parsed = self._parse_meta(message.get("content", ""))
            if parsed:
                meta = parsed
                meta_msg = message
                break

        if not meta or not meta_msg:
            return None

        notes = []
        for message in oldest_first:
            if str(message.get("id")) == str(meta_msg.get("id")):
                continue
            notes.append(
                {
                    "message_id": message.get("id", ""),
                    "author_name": message.get("author", {}).get("username", "unknown"),
                    "content": message.get("content", ""),
                    "created_at": message.get("timestamp", ""),
                }
            )

        meta["thread_id"] = thread_id
        meta["meta_message_id"] = str(meta_msg["id"])
        meta["notes"] = notes
        return meta

    def _next_ticket_id(self) -> str:
        max_id = 0
        for ticket in self.list_tickets():
            try:
                max_id = max(max_id, int(str(ticket.get("ticket_id", "0")).split("/")[0]))
            except Exception:
                pass
        return str(max_id + 1).zfill(5)

    def create_ticket(
        self,
        customer_name: str,
        device: str,
        issue: str,
        created_by: str,
        priority: str = "normal",
        phone: str = "",
        email: str = "",
        probable_cause: str = "",
    ) -> dict:
        self.reload()
        base_id = self._next_ticket_id()
        timestamp = datetime.now().strftime("%m-%d-%Y/%I:%M%p").lstrip("0")
        ticket_id = f"{base_id}/{timestamp}"
        channel_id = self.settings["backend_channel_id"]

        seed_message = self._post_message(channel_id, f"Ticket-It seed for ticket #{ticket_id}")
        thread_name = f"Ticket {ticket_id} - {customer_name or 'Unknown'} - {issue[:40]}"
        thread = self._start_thread_from_message(channel_id, seed_message["id"], thread_name)

        meta = {
            "ticket_id": ticket_id,
            "status": "open",
            "priority": priority,
            "customer_name": customer_name,
            "phone": phone,
            "email": email,
            "device": device,
            "issue": issue,
            "probable_cause": probable_cause,
            "assigned_to": "",
            "work_summary": "",
            "created_by": created_by,
            "created_at": now_iso(),
            "thread_id": str(thread["id"]),
            "seed_message_id": str(seed_message["id"]),
        }

        meta_message = self._post_message(str(thread["id"]), self._meta_to_message(meta))
        meta["meta_message_id"] = str(meta_message["id"])
        return meta

    def update_ticket_meta(self, ticket: dict):
        ticket["work_summary"] = self._trim_text(ticket.get("work_summary", ""), 500)
        self._ensure_thread_writable(str(ticket["thread_id"]))
        self._edit_message(str(ticket["thread_id"]), str(ticket["meta_message_id"]), self._meta_to_message(ticket))

    def add_note(self, thread_id: str, actor: str, text: str):
        full_text = f"{actor}: {text.strip()}"
        self._ensure_thread_writable(str(thread_id))
        self._post_split_message(thread_id, full_text)

    def add_action(self, thread_id: str, action_type: str, actor: str, text: str):
        self._ensure_thread_writable(str(thread_id))
        self._post_message(thread_id, self._action_to_message(action_type, actor, text))

    def assign_ticket(self, ticket: dict, username: str, actor: str):
        ticket["assigned_to"] = username.strip()
        self.update_ticket_meta(ticket)
        self.add_action(ticket["thread_id"], "assign", actor, f"Assigned to {username.strip()}.")

    def set_priority(self, ticket: dict, priority: str, actor: str):
        ticket["priority"] = priority.strip()
        self.update_ticket_meta(ticket)
        self.add_action(ticket["thread_id"], "priority", actor, f"Priority set to {priority.strip()}.")

    def update_work_summary(self, ticket: dict, text: str, actor: str):
        clean_text = text.strip()
        ticket["work_summary"] = self._trim_text(clean_text, 500)
        self.update_ticket_meta(ticket)
        self.add_note(ticket["thread_id"], actor, clean_text)

    def close_ticket(self, ticket: dict, actor: str):
        ticket["status"] = "closed"
        self.update_ticket_meta(ticket)
        self.add_action(ticket["thread_id"], "status", actor, "Ticket closed.")

    def reopen_ticket(self, ticket: dict, actor: str):
        ticket["status"] = "open"
        self.update_ticket_meta(ticket)
        self.add_action(ticket["thread_id"], "status", actor, "Ticket reopened.")