# Ticket-it Discord Backend

This build uses Discord as the shared ticket backend.

## Storage model

- `#ticket-it-backend` is a normal Discord text channel
- each ticket becomes its own Discord thread under that channel
- the first thread message stores ticket metadata as JSON
- later messages in the thread are notes, actions, and work log entries

## Features

- responsive fullscreen PyQt6 GUI
- dashboard stats
- ticket table and detail view
- create ticket
- assign ticket
- set priority
- add note
- AI note cleanup
- AI draft ticket parsing
- AI ticket summary
- Discord settings page with connection test

## Setup

1. Create a Discord bot
2. Invite it to your server
3. Give it access to the backend channel
4. Give the bot these permissions in that channel:
   - View Channel
   - Send Messages
   - Create Public Threads
   - Send Messages in Threads
   - Manage Threads (recommended)
5. Put values in `.env` or in the app Settings page
6. Install requirements and run

## Run

```bash
pip install -r requirements.txt
python run.py
```
