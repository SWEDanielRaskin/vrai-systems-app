import os
import logging
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GoogleCalendarService:
    """Service for integrating with Google Calendar API"""
    
    def __init__(self):
        self.credentials_file = "google-calendar-credentials.json"
        self.calendar_id = "6c47fac129953096abbd3281541234c4b3158f44bedb7eeeb7d6f52c61dca3c7@group.calendar.google.com"
        self.timezone = "America/New_York"  # EST
        self.service = None
        
        # Business hours configuration
        self.business_hours = {
            'monday': {'start': '09:00', 'end': '16:00'},
            'tuesday': {'start': '09:00', 'end': '16:00'},
            'wednesday': {'start': '09:00', 'end': '16:00'},
            'thursday': {'start': '09:00', 'end': '16:00'},
            'friday': {'start': '09:00', 'end': '16:00'},
            'saturday': {'start': '09:00', 'end': '15:00'},
            'sunday': None  # Closed
        }
        
        # Initialize the service
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Google Calendar service with credentials"""
        try:
            # Load service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            # Build the service
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info("✅ Google Calendar service initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Calendar service: {str(e)}")
            self.service = None
    
    def test_connection(self) -> Dict:
        """Test the Google Calendar API connection"""
        try:
            if not self.service:
                return {
                    'success': False,
                    'error': 'Calendar service not initialized'
                }
            
            # Try to get calendar info
            calendar = self.service.calendars().get(calendarId=self.calendar_id).execute()
            
            return {
                'success': True,
                'calendar_name': calendar.get('summary', 'Unknown'),
                'calendar_id': self.calendar_id,
                'message': 'Successfully connected to Google Calendar'
            }
            
        except HttpError as e:
            logger.error(f"❌ Google Calendar API error: {e}")
            return {
                'success': False,
                'error': f"API Error: {e.resp.status}",
                'details': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_appointment(self, appointment_data: Dict) -> Dict:
        """
        Create a new appointment in Google Calendar
        
        Args:
            appointment_data: {
                'summary': str (event title),
                'start_datetime': str (ISO datetime),
                'end_datetime': str (ISO datetime),
                'customer_name': str,
                'customer_phone': str,
                'service': str,
                'specialist': str,
                'price': float,
                'duration': int
            }
        
        Returns:
            Dict with booking details or error info
        """
        try:
            if not self.service:
                return {
                    'success': False,
                    'error': 'Calendar service not initialized'
                }
            
            # Create event object
            event = {
                'summary': appointment_data['summary'],
                'description': self._create_event_description(appointment_data),
                'start': {
                    'dateTime': appointment_data['start_datetime'],
                    'timeZone': self.timezone,
                },
                'end': {
                    'dateTime': appointment_data['end_datetime'],
                    'timeZone': self.timezone,
                },
                'extendedProperties': {
                    'private': {
                        'customer_name': appointment_data['customer_name'],
                        'customer_phone': appointment_data['customer_phone'],
                        'service': appointment_data['service'],
                        'specialist': appointment_data['specialist'],
                        'price': str(appointment_data['price']),
                        'duration': str(appointment_data['duration'])
                    }
                }
            }
            
            # Create the event
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            logger.info(f"✅ Google Calendar event created: {created_event['id']}")
            
            return {
                'success': True,
                'event_id': created_event['id'],
                'event_url': created_event.get('htmlLink'),
                'data': created_event
            }
            
        except HttpError as e:
            logger.error(f"❌ Google Calendar API error: {e}")
            return {
                'success': False,
                'error': f"API Error: {e.resp.status}",
                'details': str(e)
            }
        except Exception as e:
            logger.error(f"❌ Error creating calendar event: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_event_description(self, appointment_data: Dict) -> str:
        """Create a formatted description for the calendar event"""
        return f"""
Radiance MD Med Spa Appointment

Customer: {appointment_data['customer_name']}
Phone: {appointment_data['customer_phone']}
Service: {appointment_data['service']}
Specialist: {appointment_data['specialist']}
Price: ${appointment_data['price']}
Duration: {appointment_data['duration']} minutes

Booked via AI Assistant
        """.strip()
    
    def get_availability(self, date: str, duration: int = 30) -> List[str]:
        """
        Get available time slots for a given date
        
        Args:
            date: Date in YYYY-MM-DD format
            duration: Appointment duration in minutes
            
        Returns:
            List of available time slots in HH:MM format
        """
        try:
            if not self.service:
                logger.error("Calendar service not initialized")
                return []
            
            # Parse the date
            target_date = datetime.strptime(date, "%Y-%m-%d")
            day_name = target_date.strftime('%A').lower()
            
            # Check if day is within business hours
            if day_name not in self.business_hours or self.business_hours[day_name] is None:
                logger.info(f"📅 {day_name.title()} is not a business day")
                return []
            
            business_day = self.business_hours[day_name]
            start_hour, start_min = map(int, business_day['start'].split(':'))
            end_hour, end_min = map(int, business_day['end'].split(':'))
            
            # Get existing events for the day
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Convert to timezone-aware datetime
            eastern = pytz.timezone(self.timezone)
            start_of_day = eastern.localize(start_of_day)
            end_of_day = eastern.localize(end_of_day)
            
            # Get events from Google Calendar
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Convert events to busy time slots
            busy_slots = []
            for event in events:
                if 'dateTime' in event['start']:
                    start_time = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                    
                    # Convert to local timezone
                    start_time = start_time.astimezone(eastern)
                    end_time = end_time.astimezone(eastern)
                    
                    busy_slots.append((start_time, end_time))
            
            # Generate all possible time slots during business hours
            available_slots = []
            current_time = target_date.replace(hour=start_hour, minute=start_min)
            end_time = target_date.replace(hour=end_hour, minute=end_min)
            
            while current_time + timedelta(minutes=duration) <= end_time:
                slot_start = eastern.localize(current_time)
                slot_end = slot_start + timedelta(minutes=duration)
                
                # Check if this slot conflicts with any busy slot
                is_available = True
                for busy_start, busy_end in busy_slots:
                    if (slot_start < busy_end and slot_end > busy_start):
                        is_available = False
                        break
                
                if is_available:
                    available_slots.append(current_time.strftime("%H:%M"))
                
                current_time += timedelta(minutes=duration)
            
            logger.info(f"📅 Found {len(available_slots)} available slots for {date}")
            return available_slots
            
        except Exception as e:
            logger.error(f"❌ Error getting availability: {str(e)}")
            return []
    
    def check_slot_available(self, date: str, time: str, duration: int = 30) -> bool:
        """
        Check if a specific time slot is available
        
        Args:
            date: Date in YYYY-MM-DD format
            time: Time in HH:MM format
            duration: Duration in minutes
            
        Returns:
            True if slot is available, False otherwise
        """
        try:
            available_slots = self.get_availability(date, duration)
            return time in available_slots
        except Exception as e:
            logger.error(f"❌ Error checking slot availability: {str(e)}")
            return False
    
    def format_datetime_for_calendar(self, date: str, time: str) -> str:
        """
        Format date and time for Google Calendar API (ISO format)
        
        Args:
            date: Date in YYYY-MM-DD format
            time: Time in HH:MM format
            
        Returns:
            ISO formatted datetime string
        """
        try:
            # Create datetime object
            dt_str = f"{date} {time}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            
            # Set timezone to Eastern
            eastern = pytz.timezone(self.timezone)
            dt_eastern = eastern.localize(dt)
            
            # Convert to ISO format
            return dt_eastern.isoformat()
            
        except Exception as e:
            logger.error(f"❌ Error formatting datetime: {str(e)}")
            return None
    

    def get_event(self, event_id: str) -> Optional[Dict]:
        """
        Get a single calendar event by ID
        
        Args:
            event_id: Google Calendar event ID
            
        Returns:
            Event data dict or None if not found
        """
        try:
            if not self.service:
                logger.warning("Calendar service not initialized")
                return None
            
            # Get the event
            event = self.service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            logger.info(f"📅 Retrieved event {event_id} from Google Calendar")
            return event
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.info(f"📅 Event {event_id} not found")
                return None
            else:
                logger.error(f"❌ Google Calendar API error getting event: {e}")
                return None
        except Exception as e:
            logger.error(f"❌ Error getting event {event_id}: {str(e)}")
            return None
    
    def check_event_exists(self, event_id: str) -> bool:
        """
        Check if a calendar event still exists
        
        Args:
            event_id: Google Calendar event ID
            
        Returns:
            True if event exists, False if deleted/not found
        """
        try:
            if not self.service:
                logger.warning("Calendar service not initialized")
                return True  # Default to True to avoid false cancellations
            
            # Try to get the event
            event = self.service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            # Check if event is cancelled
            if event.get('status') == 'cancelled':
                logger.info(f"📅 Event {event_id} is cancelled")
                return False
            
            logger.info(f"📅 Event {event_id} still exists and is active")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.info(f"📅 Event {event_id} not found (deleted)")
                return False
            else:
                logger.error(f"❌ Google Calendar API error checking event: {e}")
                return True  # Default to True on API errors
        except Exception as e:
            logger.error(f"❌ Error checking event existence: {str(e)}")
            return True  # Default to True to avoid false cancellations
    
    def delete_appointment(self, event_id: str) -> Dict:
        """
        Delete an appointment from Google Calendar
        
        Args:
            event_id: Google Calendar event ID
            
        Returns:
            Dict with success status
        """
        try:
            if not self.service:
                return {
                    'success': False,
                    'error': 'Calendar service not initialized'
                }
            
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            logger.info(f"✅ Google Calendar event deleted: {event_id}")
            
            return {
                'success': True,
                'message': f'Event {event_id} deleted successfully'
            }
            
        except HttpError as e:
            logger.error(f"❌ Google Calendar API error: {e}")
            return {
                'success': False,
                'error': f"API Error: {e.resp.status}",
                'details': str(e)
            }
        except Exception as e:
            logger.error(f"❌ Error deleting calendar event: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def list_all_events(self, time_min=None, time_max=None, include_cancelled=True) -> List[Dict]:
        """
        List all events in the configured calendar for a given date range.
        Args:
            time_min: ISO datetime string (default: 1 year ago)
            time_max: ISO datetime string (default: 1 year in future)
            include_cancelled: If True, include cancelled events
        Returns:
            List of event dicts (Google Calendar API format)
        """
        try:
            if not self.service:
                logger.error("Calendar service not initialized")
                return []
            eastern = pytz.timezone(self.timezone)
            now = datetime.now(eastern)
            if not time_min:
                time_min = (now - timedelta(days=365)).isoformat()
            if not time_max:
                time_max = (now + timedelta(days=365)).isoformat()
            events = []
            page_token = None
            while True:
                events_result = self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    showDeleted=include_cancelled,
                    orderBy='startTime',
                    pageToken=page_token
                ).execute()
                items = events_result.get('items', [])
                events.extend(items)
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
            logger.info(f"📅 Fetched {len(events)} events from Google Calendar for sync")
            return events
        except Exception as e:
            logger.error(f"❌ Error listing all events: {str(e)}")
            return []