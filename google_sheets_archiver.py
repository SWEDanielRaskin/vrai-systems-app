import os
import datetime
from typing import List, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def format_datetime(dt_str):
    """Format ISO datetime string as MM/DD/YYYY HH:MM AM/PM"""
    if not dt_str:
        return ''
    try:
        # Try parsing with microseconds and timezone
        dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%m/%d/%Y %I:%M %p')
    except Exception:
        return dt_str

def format_duration(seconds):
    """Format duration in seconds as MM:SS"""
    try:
        seconds = int(seconds)
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"
    except Exception:
        return str(seconds)

class GoogleSheetsArchiver:
    def __init__(self, credentials_path: str, db=None):
        self.credentials_path = credentials_path
        self.creds = service_account.Credentials.from_service_account_file(
            self.credentials_path, scopes=SCOPES
        )
        self.service = build('sheets', 'v4', credentials=self.creds)
        self.db = db  # Pass database service for transcript lookup

    def ensure_daily_sheet(self, spreadsheet_id: str, sheet_title: str) -> int:
        """Ensure a sheet/tab exists for the given date, return its sheetId."""
        sheets_metadata = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheets_metadata.get('sheets', [])
        for sheet in sheets:
            if sheet['properties']['title'] == sheet_title:
                return sheet['properties']['sheetId']
        # Sheet doesn't exist, create it
        requests = [{
            'addSheet': {
                'properties': {
                    'title': sheet_title
                }
            }
        }]
        body = {'requests': requests}
        response = self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        ).execute()
        return response['replies'][0]['addSheet']['properties']['sheetId']

    def archive_conversations(self, spreadsheet_id: str, conversations: List[Dict], date: datetime.date):
        """Archive a list of conversations to the given spreadsheet under a new sheet for the date."""
        sheet_title = date.strftime('%Y-%m-%d')
        self.ensure_daily_sheet(spreadsheet_id, sheet_title)
        # Prepare header and rows
        header = [
            'Conversation ID', 'Customer Name', 'Phone', 'Start Time', 'End Time',
            'Duration', 'Transcript', 'AI Summary'
        ]
        rows = [header]
        for convo in conversations:
            rows.append([
                convo.get('id', ''),
                convo.get('customer_name', ''),
                convo.get('phone', ''),
                format_datetime(convo.get('start_time', '')),
                format_datetime(convo.get('end_time', '')),
                format_duration(convo.get('duration', '')),
                self.format_transcript(convo.get('transcript', [])),
                convo.get('ai_summary', '')
            ])
        # Write to sheet
        range_ = f"'{sheet_title}'!A1"
        self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_,
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

    def archive_notifications(self, spreadsheet_id: str, notifications: List[Dict], date: datetime.date):
        """Archive a list of notifications to the given spreadsheet under a new sheet for the date."""
        sheet_title = date.strftime('%Y-%m-%d')
        self.ensure_daily_sheet(spreadsheet_id, sheet_title)
        header = [
            'Notification ID', 'Type', 'Title', 'Phone', 'Conversation ID',
            'Created At', 'Resolved', 'Resolved At', 'Summary', 'Conversation Transcript'
        ]
        rows = [header]
        for notif in notifications:
            transcript_str = ''
            if self.db:
                # Fetch transcript/messages for this notification
                if notif.get('type') and notif.get('conversation_id'):
                    # Try both voice and sms
                    if notif.get('type') == 'voice' or (notif.get('conversation_id') and notif.get('conversation_id').startswith('v3:')):
                        call = self.db.get_call_by_id(notif['conversation_id'])
                        if call and call.get('transcript'):
                            try:
                                transcript = json.loads(call['transcript']) if isinstance(call['transcript'], str) else call['transcript']
                            except Exception:
                                transcript = []
                            transcript_str = self.format_transcript(transcript)
                    else:
                        conv = self.db.get_conversation_by_id(notif['conversation_id'])
                        if conv and conv.get('messages'):
                            try:
                                messages = json.loads(conv['messages']) if isinstance(conv['messages'], str) else conv['messages']
                            except Exception:
                                messages = []
                            transcript_str = self.format_transcript(messages)
            rows.append([
                notif.get('id', ''),
                notif.get('type', ''),
                notif.get('title', ''),
                notif.get('phone', ''),
                notif.get('conversation_id', ''),
                format_datetime(notif.get('created_at', '')),
                notif.get('resolved', ''),
                format_datetime(notif.get('resolved_at', '')),
                notif.get('summary', ''),
                transcript_str
            ])
        range_ = f"'{sheet_title}'!A1"
        self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_,
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

    @staticmethod
    def format_transcript(transcript: List[Dict]) -> str:
        """Format transcript as a multi-line string with sender prefixes, handling both SMS and voice formats."""
        if not transcript:
            return ''
        lines = []
        for msg in transcript:
            # SMS format: {'sender': 'customer'/'ai', 'message': ...}
            if 'sender' in msg and 'message' in msg:
                sender = msg['sender']
                text = msg['message']
            # Voice format: {'speaker': 'ai'/'user', 'text': ...}
            elif 'speaker' in msg and 'text' in msg:
                # Map 'ai' to 'AI', 'user' to 'Customer' for clarity
                sender = 'AI' if msg['speaker'].lower() == 'ai' else 'Customer'
                text = msg['text']
            else:
                sender = msg.get('sender') or msg.get('speaker') or 'Unknown'
                text = msg.get('message') or msg.get('text') or ''
            lines.append(f"{sender}: {text}")
        return '\n'.join(lines) 