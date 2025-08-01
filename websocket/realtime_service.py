import asyncio
import websockets
import json
import base64
import os
import logging
import re
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from appointment_service import AppointmentService
from knowledge_base_service import KnowledgeBaseService
import calendar
from typing import Dict, List, Optional
from message_scheduler import MessageScheduler
from google_calendar_service import GoogleCalendarService
from sms_service import SMSService
from payment_service import PaymentService  # New import

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

def format_date_conversational(date_str):
    """Convert YYYY-MM-DD to 'Month Day, Year' (e.g., 'July 21st, 2025')"""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        day = dt.day
        suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return dt.strftime(f'%B {day}{suffix}, %Y')
    except Exception:
        return date_str

def format_time_conversational(time_str):
    """Convert 24-hour HH:MM to 12-hour h:mm AM/PM (e.g., '2:00 PM')"""
    try:
        t = datetime.strptime(time_str, '%H:%M')
        return t.strftime('%-I:%M %p').replace('AM', 'AM').replace('PM', 'PM')
    except Exception:
        return time_str

class BookingStateMachine:
    """State machine to track booking progress and prevent premature function calls"""
    
    def __init__(self):
        self.state = "initial"
        self.collected_data = {}
        # Phone-first flow: start with phone, then branch based on customer lookup
        self.base_steps = ["phone_first"]
        self.returning_customer_steps = ["phone_first", "service", "datetime", "specialist"]
        self.returning_customer_with_up_next_steps = ["phone_first", "up_next_suggestion", "datetime", "specialist"]
        self.new_customer_steps = ["phone_first", "first_name", "last_name_spelled", "name_confirmation", "service", "datetime", "specialist"]
        self.required_steps = self.base_steps  # Will be updated after phone lookup
        self.step_order = self.base_steps  # Will be updated after phone lookup
        self.customer_type = None  # "returning" or "new"
        self.has_up_next = False  # Track if customer has up_next service
    
    def set_customer_type(self, customer_type: str, has_up_next: bool = False):
        """Set customer type and update required steps accordingly"""
        self.customer_type = customer_type
        self.has_up_next = has_up_next
        
        if customer_type == "returning":
            if has_up_next:
                self.required_steps = self.returning_customer_with_up_next_steps
                self.step_order = self.returning_customer_with_up_next_steps
                logger.info(f"🔄 Customer type set to RETURNING with UP-NEXT - steps: {self.required_steps}")
            else:
                self.required_steps = self.returning_customer_steps
                self.step_order = self.returning_customer_steps
                logger.info(f"🔄 Customer type set to RETURNING - steps: {self.required_steps}")
        elif customer_type == "new":
            self.required_steps = self.new_customer_steps
            self.step_order = self.new_customer_steps
            logger.info(f"🔄 Customer type set to NEW - steps: {self.required_steps}")
        else:
            logger.warning(f"⚠️ Unknown customer type: {customer_type}")
    
    def skip_to_service_selection(self):
        """Skip up_next_suggestion step and go directly to service selection (when customer declines up_next)"""
        if self.customer_type == "returning" and self.has_up_next:
            # Switch from up_next flow to regular returning customer flow
            self.required_steps = self.returning_customer_steps
            self.step_order = self.returning_customer_steps
            # Add service step as next if not already collected
            if "service" not in self.collected_data:
                logger.info(f"🔄 Switching to regular service selection flow")
        
    def can_call_function(self, function_name: str) -> bool:
        """Check if a function can be called based on current state"""
        if function_name == "confirm_booking":
            return len(self.collected_data) == len(self.required_steps)
        return True
    
    def add_collected_data(self, field: str, value: str):
        """Add collected data and update state"""
        self.collected_data[field] = value
        logger.info(f"📝 Collected {field}: {value}")
        logger.info(f"📊 Booking progress: {len(self.collected_data)}/{len(self.required_steps)} steps complete")
        logger.info(f"📋 Collected data so far: {list(self.collected_data.keys())}")
        logger.info(f"⏭️ Next step needed: {self.get_next_step()}")
    
    def get_next_step(self) -> Optional[str]:
        """Get the next required step"""
        for step in self.step_order:
            if step not in self.collected_data:
                return step
        return None
    
    def is_complete(self) -> bool:
        """Check if all required data is collected"""
        return len(self.collected_data) == len(self.required_steps)
    
    def reset(self):
        """Reset the state machine"""
        self.state = "initial"
        self.collected_data = {}
        self.customer_type = None
        self.has_up_next = False
        self.required_steps = self.base_steps
        self.step_order = self.base_steps
        logger.info("🔄 Booking state machine reset")
        logger.info(f"📋 Base steps: {self.base_steps}")
    
    def get_full_name(self) -> str:
        """Combine first name and spelled last name into full name, or return existing name"""
        # If we have a returning customer name, use that
        if "customer_name" in self.collected_data:
            return self.collected_data["customer_name"]
        
        # Otherwise, assemble from first/last name components
        first_name = self.collected_data.get("first_name", "")
        last_name_spelled = self.collected_data.get("last_name_spelled", "")
        
        if first_name and last_name_spelled:
            # Convert spelled letters back to word
            # Handle various formats: "S M I T H", "S-M-I-T-H", "S M I T H", etc.
            last_name = last_name_spelled.strip()
            
            # Remove common separators and convert to single word
            last_name = last_name.replace(" ", "").replace("-", "").replace("_", "")
            
            # Capitalize properly (first letter uppercase, rest lowercase)
            last_name = last_name.capitalize()
            
            return f"{first_name.strip().capitalize()} {last_name}"
        return ""

class CancellationStateMachine:
    """State machine to track cancellation progress and prevent premature function calls"""
    
    def __init__(self):
        self.state = "initial"
        self.collected_data = {}
        self.required_steps = ["phone", "appointment_selection", "confirmation"]
        self.step_order = ["phone", "appointment_selection", "confirmation"]
        self.found_appointments = []  # Store found appointments for selection
    
    def can_call_function(self, function_name: str) -> bool:
        """Check if a function can be called based on current state"""
        if function_name == "confirm_cancellation":
            return len(self.collected_data) == len(self.required_steps)
        return True
    
    def add_collected_data(self, field: str, value: str):
        """Add collected data and update state"""
        self.collected_data[field] = value
        logger.info(f"📝 Cancellation - Collected {field}: {value}")
        logger.info(f"📊 Cancellation progress: {len(self.collected_data)}/{len(self.required_steps)} steps complete")
        logger.info(f"📋 Cancellation data so far: {list(self.collected_data.keys())}")
        logger.info(f"⏭️ Next cancellation step needed: {self.get_next_step()}")
    
    def get_next_step(self) -> Optional[str]:
        """Get the next required step"""
        for step in self.step_order:
            if step not in self.collected_data:
                return step
        return None
    
    def is_complete(self) -> bool:
        """Check if all required data is collected"""
        return len(self.collected_data) == len(self.required_steps)
    
    def reset(self):
        """Reset the state machine"""
        self.state = "initial"
        self.collected_data = {}
        self.found_appointments = []
        logger.info("🔄 Cancellation state machine reset")
        logger.info(f"📋 Required cancellation steps: {self.required_steps}")
    
    def set_found_appointments(self, appointments: list):
        """Store found appointments for selection"""
        self.found_appointments = appointments
        logger.info(f"📋 Cancellation - Found {len(appointments)} appointments for selection")
    
    def get_found_appointments(self) -> list:
        """Get stored appointments"""
        return self.found_appointments

class OpenAIRealtimeService:
    def __init__(self):
        self.appointment_functions = []  # Ensure this attribute always exists, first line
        self.openai_ws = None
        self.telnyx_ws = None
        self.call_sid = None
        self.session_active = False
        self.ai_speaking = False  # Track when AI is generating audio
        self.hangup_timer = None  # Timer for auto-hangup
        self.conversation_ended = False  # Prevent duplicate hangups
        self.ai_response_text = ""  # Store AI's text response
        
        # Initialize appointment service
        self.appointment_service = AppointmentService()
        
        # NEW: Initialize knowledge base service (will be updated with database service)
        self.knowledge_base_service = KnowledgeBaseService()
        
        # NEW: Initialize booking verification service
        self.booking_verification_service = None
        
        # NEW: Database and AI summarizer services (will be set by websocket_server.py)
        self.db = None
        self.ai_summarizer = None
        
        # NEW: Conversation transcript tracking
        self.conversation_transcript = []  # Store full conversation
        self.customer_name = None  # Track customer name if mentioned
        
        # NEW: Booking state machine
        self.booking_state_machine = BookingStateMachine()
        
        # NEW: Cancellation state machine
        self.cancellation_state_machine = CancellationStateMachine()
        
        # Silence detection
        self.silence_timer = None  # Timer for silence detection
        self.silence_check_sent = False  # Track if "are you still there?" was sent
        self.silence_hangup_timer = None  # Timer for final hangup after silence check
        self.last_user_speech_time = None  # Track when user last spoke
        
        # Initial greeting protection
        self.initial_greeting_active = False  # Track if initial greeting is being said
        self.greeting_protection_timer = None  # Timer to disable protection after greeting
        
        # Business hours configuration
        self.business_hours = {
            'Monday': {'start': '09:00', 'end': '16:00'},
            'Tuesday': {'start': '09:00', 'end': '16:00'},
            'Wednesday': {'start': '09:00', 'end': '16:00'},
            'Thursday': {'start': '09:00', 'end': '16:00'},
            'Friday': {'start': '09:00', 'end': '16:00'},
            'Saturday': {'start': '09:00', 'end': '15:00'},
            'Sunday': {'start': None, 'end': None}  # Closed
        }
        
        # Function definitions for appointment booking (Realtime API format) - UPDATED for stepwise slot-filling
        self.appointment_functions = [
            {
                "type": "function",
                "name": "collect_phone_first",
                "description": "Collect the customer's phone number first to check if they are a returning customer. Ask 'Is the phone number you're calling from the best number to reach you? If not, please provide your preferred number.' If they say 'yes' or confirm, pass 'yes' as the phone parameter. If they provide a different number, pass their actual phone number. The system will validate the format and perform database lookup to determine if customer is returning or new.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number or 'yes' if they confirm using caller ID"}
                    },
                    "required": ["phone"]
                }
            },
            {
                "type": "function",
                "name": "handle_up_next_service_suggestion",
                "description": "Handle customer response when they are presented with their up_next service suggestion. Call this when customer responds to 'I see you're due for your [service]. Would you like to book that, or would you prefer a different service?' If they accept, proceed to date/time. If they decline, proceed to normal service selection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "response": {"type": "string", "description": "Customer's response to the up_next service suggestion"}
                    },
                    "required": ["response"]
                }
            },
            {
                "type": "function",
                "name": "collect_first_name",
                "description": "Collect the customer's first name for NEW customers only. This is called after phone lookup determines customer is not in database. After collecting the first name, immediately call the collect_last_name_spelled function to get the spelled last name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string", "description": "Customer's first name"}
                    },
                    "required": ["first_name"]
                }
            },
            {
                "type": "function",
                "name": "collect_last_name_spelled",
                "description": "Collect the customer's last name spelled out letter by letter for NEW customers only. After collecting the spelled last name, immediately call the confirm_name_collection function to confirm the full name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "last_name_spelled": {"type": "string", "description": "Customer's last name spelled out letter by letter (e.g., 'S M I T H' or 'B O W E')"}
                    },
                    "required": ["last_name_spelled"]
                }
            },
            {
                "type": "function",
                "name": "confirm_name_collection",
                "description": "Confirm the customer's full name (first name + spelled last name) for NEW customers only. After confirmation, immediately call the collect_service function to get the service type.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmation": {"type": "string", "description": "Customer's confirmation response (yes/no or similar)"}
                    },
                    "required": ["confirmation"]
                }
            },
            {
                "type": "function",
                "name": "collect_service",
                "description": "Collect the type of service the customer wants to book. This is called for ALL customers (returning and new) after phone/name collection is complete. After collecting the service, immediately call the collect_date_time function to get the appointment date and time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "enum": [], "description": "Type of service requested"}
                    },
                    "required": ["service"]
                }
            },
            {
                "type": "function",
                "name": "collect_date_time",
                "description": "Collect the appointment date and time from the customer. After collecting both, immediately call the collect_specialist_preference function to get any specialist preference.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Appointment date in YYYY-MM-DD format"},
                        "time": {"type": "string", "description": "Appointment time in HH:MM format (24-hour)"}
                    },
                    "required": ["date", "time"]
                }
            },
            {
                "type": "function",
                "name": "collect_specialist_preference",
                "description": "Collect the customer's preferred specialist, if any. After collecting this, immediately call the confirm_booking function to finalize the booking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "specialist_preference": {"type": "string", "enum": ["Sarah", "Kennedy", "Julia"], "description": "Preferred specialist (optional)"}
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "confirm_booking",
                "description": "ONLY call this function after ALL required information has been collected via the previous functions. This will actually book the appointment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Customer's full name"},
                        "phone": {"type": "string", "description": "Customer's phone number"},
                        "date": {"type": "string", "description": "Appointment date in YYYY-MM-DD format"},
                        "time": {"type": "string", "description": "Appointment time in HH:MM format (24-hour)"},
                        "service": {"type": "string", "enum": [], "description": "Type of service requested"},
                        "specialist_preference": {"type": "string", "enum": ["Sarah", "Kennedy", "Julia"], "description": "Preferred specialist (optional)"}
                    },
                    "required": ["name", "phone", "date", "time", "service"]
                }
            },
            {
                "type": "function",
                "name": "check_availability",
                "description": "Check available appointment slots for a specific date. Call this when customer asks what times or hours are available for booking an appointment. Required for ALL availability requests. Avoid naming all available times. Simply state a general range of availability and/or mention unavailable times",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date to check in YYYY-MM-DD format"},
                        "service": {"type": "string", "enum": [], "description": "Type of service to check availability for"}
                    },
                    "required": ["date", "service"]
                }
            },
            {
                "type": "function",
                "name": "get_business_information",
                "description": "Get specific business information from knowledge base. ONLY use when customer asks about business details like hours, services, location, staff, policies, pricing, etc. DO NOT use for appointment booking - use book_appointment function instead. DO NOT use for general conversation - only for business information questions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {"type": "string", "enum": ["hours", "services", "location", "staff", "policies", "pricing", "general"], "description": "Type of business information needed"},
                        "specific_question": {"type": "string", "description": "The customer's specific question"}
                    },
                    "required": ["query_type", "specific_question"]
                }
            },
            # Cancellation functions
            {
                "type": "function",
                "name": "collect_cancellation_phone",
                "description": "Collect the phone number for appointment cancellation. Ask 'Did you schedule with the number you are calling from? If not, please provide the number you scheduled the appointment with.' If they confirm they're calling from the same number, pass an empty string or 'same' - the function will automatically use the caller ID. If they provide a different number, pass that actual phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number (pass empty string or 'same' if they confirm they're calling from the same number, otherwise pass their actual provided number)"}
                    },
                    "required": ["phone"]
                }
            },
            {
                "type": "function",
                "name": "search_appointments_by_phone",
                "description": "Search for upcoming appointments using the provided phone number. Call this after collecting the cancellation phone number. This will find all upcoming appointments for that phone number and present them to the customer for selection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Phone number to search for appointments"}
                    },
                    "required": ["phone"]
                }
            },
            {
                "type": "function",
                "name": "select_appointment_to_cancel",
                "description": "Handle appointment selection when multiple appointments are found. Call this when the customer specifies which appointment they want to cancel. You can pass: 1) The exact Google Calendar event ID, 2) A position number (1, 2, 3, etc.) corresponding to the appointment in the list, or 3) A description like 'consultation with Sarah' or 'HydraFacial'. If only one appointment was found, this function should be called automatically with that appointment's event_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Google Calendar event ID, position number, or description of the appointment to cancel"}
                    },
                    "required": ["event_id"]
                }
            },
            {
                "type": "function",
                "name": "confirm_cancellation",
                "description": "Confirm and execute the appointment cancellation. This will validate the 24-hour policy, cancel the appointment, and handle all cleanup. Call this after the customer confirms they want to cancel the selected appointment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Google Calendar event ID of the appointment to cancel"}
                    },
                    "required": ["event_id"]
                }
            },
        ] + self.appointment_functions  # Prepend cancellation functions
    
    def get_business_hours_status(self):
        """
        Determine if we're in business hours considering the testing override
        Returns: True for business hours, False for after hours
        """
        # Check for testing override first
        override = os.getenv('BUSINESS_HOURS_OVERRIDE', '').lower()
        
        if override == 'business':
            logger.info("🧪 Testing override: BUSINESS HOURS mode")
            return True
        elif override == 'after_hours':
            logger.info("🧪 Testing override: AFTER HOURS mode")
            return False
        else:
            # Use actual business hours
            return self.is_business_hours()
    
    def is_business_hours(self):
        """Check if current time is within business hours"""
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')
        
        if current_day == 'Sunday':
            return False
            
        hours = self.business_hours.get(current_day)
        if not hours or not hours['start'] or not hours['end']:
            return False
            
        return hours['start'] <= current_time <= hours['end']
    
    async def execute_appointment_function(self, function_name: str, arguments: dict):
        """Execute appointment-related functions"""
        try:
            # TEMPORARILY COMMENTED OUT: Check if function can be called based on state machine
            # if not self.booking_state_machine.can_call_function(function_name):
            #     logger.warning(f"⚠️ Function {function_name} called prematurely - state machine blocked it")
            #     return self.handle_premature_function_call(function_name)
            
            if function_name == "confirm_booking":
                return await self.confirm_booking_function(**arguments)
            elif function_name == "check_availability":
                return await self.check_availability_function(**arguments)
            elif function_name == "get_business_information":
                return await self.get_business_information_function(**arguments)
            # NEW: Add handlers for stepwise slot-filling functions
            elif function_name == "collect_phone_first":
                return await self.collect_phone_first_function(**arguments)
            elif function_name == "handle_up_next_service_suggestion":
                return await self.handle_up_next_service_suggestion_function(**arguments)
            elif function_name == "collect_first_name":
                return await self.collect_first_name_function(**arguments)
            elif function_name == "collect_last_name_spelled":
                return await self.collect_last_name_spelled_function(**arguments)
            elif function_name == "confirm_name_collection":
                return await self.confirm_name_collection_function(**arguments)
            elif function_name == "collect_service":
                return await self.collect_service_function(**arguments)
            elif function_name == "collect_date_time":
                return await self.collect_date_time_function(**arguments)
            elif function_name == "collect_specialist_preference":
                return await self.collect_specialist_preference_function(**arguments)
            # NEW: Add handlers for cancellation functions
            elif function_name == "collect_cancellation_phone":
                return await self.collect_cancellation_phone_function(**arguments)
            elif function_name == "search_appointments_by_phone":
                return await self.search_appointments_by_phone_function(**arguments)
            elif function_name == "select_appointment_to_cancel":
                return await self.select_appointment_to_cancel_function(**arguments)
            elif function_name == "confirm_cancellation":
                return await self.confirm_cancellation_function(**arguments)
            else:
                return {"error": f"Unknown function: {function_name}"}
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {str(e)}")
            return {"error": f"Function execution failed: {str(e)}"}
    
    # NEW: Stepwise slot-filling function handlers
    async def collect_first_name_function(self, first_name: str):
        """Handle first name collection step"""
        logger.info(f"📝 Collected first name: {first_name}")
        self.booking_state_machine.add_collected_data("first_name", first_name.strip())
        return {
            "success": True,
            "message": f"Thank you, {first_name}. Now, could you please spell your last name for me, letter by letter?",
            "collected_first_name": first_name.strip()
        }
    
    async def collect_last_name_spelled_function(self, last_name_spelled: str):
        """Handle last name spelling collection step"""
        logger.info(f"📝 Collected spelled last name: {last_name_spelled}")
        self.booking_state_machine.add_collected_data("last_name_spelled", last_name_spelled.strip())
        
        # Get the first name for confirmation
        first_name = self.booking_state_machine.collected_data.get("first_name", "")
        
        # Format the spelled last name for confirmation (clean up extra spaces)
        cleaned_last_name = last_name_spelled.strip().replace("  ", " ")
        
        return {
            "success": True,
            "message": f"Perfect. Let me confirm - your name is {first_name} {cleaned_last_name}. Is that correct?",
            "collected_last_name_spelled": cleaned_last_name,
            "full_name_preview": f"{first_name} {cleaned_last_name}"
        }
    
    async def confirm_name_collection_function(self, confirmation: str):
        """Handle name confirmation step"""
        logger.info(f"📝 Name confirmation: {confirmation}")
        
        confirmation_lower = confirmation.lower().strip()
        is_confirmed = confirmation_lower in ["yes", "y", "yeah", "correct", "right", "that's right", "that's correct", "true"]
        
        if is_confirmed:
            self.booking_state_machine.add_collected_data("name_confirmation", "confirmed")
            # Store the combined full name for easy access
            full_name = self.booking_state_machine.get_full_name()
            self.booking_state_machine.add_collected_data("full_name", full_name)
            
            return {
                "success": True,
                "message": "Perfect! What type of service would you like to book?",
                "confirmed_full_name": full_name
            }
        else:
            # Reset last name collection if they say no
            self.booking_state_machine.collected_data.pop("last_name_spelled", None)
            return {
                "success": False,
                "message": "I apologize for the error. Could you please spell your last name again, letter by letter?",
                "needs_respelling": True
            }
    
    async def collect_phone_function(self, phone: str):
        """Handle phone collection step"""
        logger.info(f"📞 Collected phone: {phone}")
        self.booking_state_machine.add_collected_data("phone", phone)
        return {
            "success": True,
            "message": "Thank you. What type of service would you like to book?",
            "collected_phone": phone
        }
    
    async def collect_service_function(self, service: str):
        """Handle service collection step (including correction after invalid service)"""
        logger.info(f"\U0001F6CD\uFE0F Collected service: {service}")
        self.booking_state_machine.add_collected_data("service", service)
        # After updating, check if all required slots are filled
        if self.booking_state_machine.is_complete():
            # All info present, proceed to booking
            data = self.booking_state_machine.collected_data
            # Unpack datetime
            date, time = data["datetime"].split(" ", 1)
            return await self.confirm_booking_function(
                name=data["name"],
                phone=data["phone"],
                date=date,
                time=time,
                service=data["service"],
                specialist_preference=data.get("specialist")
            )
        else:
            # Ask for the next missing slot only
            next_step = self.booking_state_machine.get_next_step()
            if next_step == "datetime":
                return {
                    "success": True,
                    "message": f"Great choice. What date and time would you like to schedule your {service} appointment?",
                    "collected_service": service
                }
            elif next_step == "specialist":
                return {
                    "success": True,
                    "message": "Do you have a preference for which specialist you'd like to see, or would you like us to assign one for you?",
                    "collected_service": service
                }
            else:
                return {
                    "success": True,
                    "message": f"Service collected. Next, please provide your {next_step}.",
                    "collected_service": service
                }
    
    async def collect_date_time_function(self, date: str, time: str):
        """Handle date and time collection step (including correction after invalid time)"""
        logger.info(f"\U0001F4C5 Collected date/time: {date} at {time}")
        self.booking_state_machine.add_collected_data("datetime", f"{date} {time}")
        # After updating, check if all required slots are filled
        if self.booking_state_machine.is_complete():
            data = self.booking_state_machine.collected_data
            
            # Get the correct name field based on customer type
            customer_name = data.get("customer_name") or data.get("full_name") or data.get("name", "")
            customer_phone = data.get("phone_first") or data.get("phone", "")
            
            return await self.confirm_booking_function(
                name=customer_name,
                phone=customer_phone,
                date=date,
                time=time,
                service=data["service"],
                specialist_preference=data.get("specialist")
            )
        else:
            next_step = self.booking_state_machine.get_next_step()
            if next_step == "specialist":
                return {
                    "success": True,
                    "message": "Do you have a preference for which specialist you'd like to see, or would you like us to assign one for you?",
                    "collected_date": date,
                    "collected_time": time
                }
            else:
                return {
                    "success": True,
                    "message": f"Date and time collected. Next, please provide your {next_step}.",
                    "collected_date": date,
                    "collected_time": time
                }
    
    async def collect_specialist_preference_function(self, specialist_preference: str = None):
        """Handle specialist preference collection step (including correction after invalid specialist)"""
        logger.info(f"\U0001F465 Collected specialist preference: {specialist_preference}")
        self.booking_state_machine.add_collected_data("specialist", specialist_preference or "auto")
        # After updating, check if all required slots are filled
        if self.booking_state_machine.is_complete():
            data = self.booking_state_machine.collected_data
            date, time = data["datetime"].split(" ", 1)
            return await self.confirm_booking_function(
                name=data["name"],
                phone=data["phone"],
                date=date,
                time=time,
                service=data["service"],
                specialist_preference=data.get("specialist")
            )
        else:
            next_step = self.booking_state_machine.get_next_step()
            return {
                "success": True,
                "message": f"Specialist preference collected. Next, please provide your {next_step}.",
                "collected_specialist": specialist_preference
            }
    
    async def confirm_booking_function(self, name: str, phone: str, date: str, time: str, 
                                      service: str, specialist_preference: str = None):
        """Function to book an appointment during voice call"""
        # Use the phone from phone_first collection (more reliable)
        actual_phone = self.booking_state_machine.collected_data.get("phone_first", phone)
        
        # Use the assembled full name from the state machine if available
        full_name = self.booking_state_machine.collected_data.get("full_name") or \
                   self.booking_state_machine.collected_data.get("customer_name") or \
                   self.booking_state_machine.get_full_name() or name
        
        # Handle service - use up_next_service if regular service not set and we have up_next
        service_to_use = service
        if not service and self.booking_state_machine.collected_data.get("up_next_service"):
            service_to_use = self.booking_state_machine.collected_data.get("up_next_service")
            # Set the is_up_next_service flag since the handler was bypassed
            self.booking_state_machine.add_collected_data("is_up_next_service", "true")
            logger.info(f"📋 Using up_next_service as fallback: {service_to_use}")
        
        if not full_name:
            # Fallback to assembling from components if full_name not set
            full_name = self.booking_state_machine.get_full_name() or name
        
        logger.info(f"\U0001F4C5 Voice booking: {full_name} - {service_to_use} on {date} at {time}")
        logger.info(f"📞 Using phone: {actual_phone} (customer type: {self.booking_state_machine.customer_type})")
        
        if not self.db or not [s['name'] for s in self.db.get_services()]:
            return {"success": False, "message": self.no_services_fallback, "available_slots": []}
        
        self.customer_name = full_name
        
        # For new customers, create customer record in database
        if self.booking_state_machine.customer_type == "new" and self.db:
            try:
                # Format phone for database consistency
                formatted_phone = self.appointment_service._format_phone_for_search(actual_phone)
                self.db.create_customer(formatted_phone, full_name)
                logger.info(f"✅ Created new customer record: {full_name} ({formatted_phone})")
            except Exception as e:
                logger.warning(f"⚠️ Could not create customer record: {str(e)}")
        
        # Check if this is an up_next service (custom service that bypasses validation)
        is_up_next_service = self.booking_state_machine.collected_data.get("is_up_next_service") == "true"
        
        # Continue with existing booking logic using actual_phone and full_name
        user_id = actual_phone
        if self.booking_verification_service and user_id:
            self.booking_verification_service.log_function_call(
                user_id=user_id,
                function_name="confirm_booking",
                arguments={"name": full_name, "phone": actual_phone, "date": date, "time": time, "service": service_to_use, "specialist_preference": specialist_preference},
                result={}  # Will be updated after booking
            )
        booking_key = (full_name, actual_phone, date, time, service_to_use, specialist_preference)
        if getattr(self, "last_successful_booking", None) == booking_key:
            return {
                "success": True,
                "message": "Your appointment is already booked and confirmed. If you need to make another booking, please start a new request.",
            }
        
        # Use custom booking for up_next services or regular booking for standard services
        if is_up_next_service:
            logger.info(f"📋 Booking up-next custom service: {service_to_use}")
            result = self.appointment_service.book_custom_appointment(
                name=full_name,
                phone=actual_phone,
                date=date,
                time=time,
                service=service_to_use,
                specialist_preference=specialist_preference,
                price=0.0,  # Default to $0 for custom services
                duration=60  # Default to 60 minutes for custom services
            )
        else:
            result = self.appointment_service.book_appointment(
                name=full_name,
                phone=actual_phone,
                date=date,
                time=time,
                service=service_to_use,
                specialist_preference=specialist_preference
            )
        
        if self.booking_verification_service and user_id:
            self.booking_verification_service.log_function_call(
                user_id=user_id,
                function_name="confirm_booking",
                arguments={"name": full_name, "phone": actual_phone, "date": date, "time": time, "service": service_to_use, "specialist_preference": specialist_preference},
                result=result
            )
        if result['success']:
            appointment = result['appointment']
            date_conv = format_date_conversational(appointment['date'])
            time_conv = format_time_conversational(appointment['time'])
            self.last_successful_booking = booking_key
            self.booking_state_machine.reset()
            return {
                "success": True,
                "message": f"Perfect! I've booked your {appointment['service_name']} appointment with {appointment['specialist']} on {date_conv} at {time_conv}. You'll receive a confirmation text shortly.",
                "appointment_id": appointment['id'],
                "specialist": appointment['specialist'],
                "price": appointment['price']
            }
        else:
            available_slots = result.get('available_slots', [])
            # If the error is about time, prompt for new time only
            if available_slots:
                # Use the new check_availability with preferred_time
                closest_slots = self.appointment_service.check_availability(date, service_to_use, preferred_time=time)
                slots_text = ", ".join(closest_slots)
                # Update only the datetime slot, keep others
                self.booking_state_machine.add_collected_data("datetime", f"{date} {time}")
                return {
                    "success": False,
                    "message": f"That time isn't available. Here are some options: {slots_text}. Which time works for you?",
                    "available_slots": closest_slots,
                    "next_step": "datetime"
                }
            # If the error is about service, prompt for new service only
            elif result.get('error', '').startswith('Unknown service'):
                self.booking_state_machine.collected_data.pop("service", None)
                return {
                    "success": False,
                    "message": f"That service isn't available. Here are our services: {[s['name'] for s in self.db.get_services()]}. Which would you like?",
                    "available_services": [s['name'] for s in self.db.get_services()],
                    "next_step": "service"
                }
            else:
                return {
                    "success": False,
                    "message": "I'm sorry, that date doesn't have any available appointments. Could you try a different date?",
                    "error": result['error']
                }
    
    async def check_availability_function(self, date: str, service: str):
        """Function to check availability during voice call"""
        logger.info(f"\U0001F4C5 Voice availability check: {service} on {date}")
        
        if not self.db or not [s['name'] for s in self.db.get_services()]:
            return {"message": self.no_services_fallback, "available_slots": [], "total_slots": 0}
        
        # For general availability requests, do not pass preferred_time
        available_slots = self.appointment_service.check_availability(date, service)
        
        if available_slots:
            date_conv = format_date_conversational(date)
            
            # Handle the new format where last element might be "and X more options"
            time_slots = []
            more_options_text = ""
            
            for slot in available_slots:
                if slot.startswith("and ") and "more options" in slot:
                    more_options_text = f" {slot}"
                else:
                    time_slots.append(slot)
            
            slots_text = ", ".join(time_slots)
            if more_options_text:
                slots_text += more_options_text
            
            return {
                "message": f"For {service} on {date_conv}, I have these times available: {slots_text}. Which time would you prefer?",
                "available_slots": time_slots,  # Don't include the "more options" text in the slots list
                "total_slots": len(available_slots)
            }
        else:
            return {
                "message": f"I don't have any appointments available for {service} on {date}. Could you try a different date?",
                "available_slots": [],
                "total_slots": 0
            }
    
    async def get_business_information_function(self, query_type: str, specific_question: str):
        """NEW: Function to get business information from knowledge base during voice call"""
        logger.info(f"📚 Voice business info request - type: {query_type}, question: {specific_question}")
        
        # NEW: Enhanced query type detection for voice
        if query_type == 'general':
            # Use the knowledge base service to detect the proper query type
            should_trigger, detected_type = self.knowledge_base_service.should_trigger_knowledge_function(specific_question)
            if should_trigger and detected_type:
                query_type = detected_type
                logger.info(f"🎯 Voice query type auto-detected: {query_type}")
        
        # Search knowledge base
        information = self.knowledge_base_service.search_knowledge_base(specific_question, query_type)
        
        return {
            "query_type": query_type,
            "question": specific_question,
            "information": information
        }
    
    def detect_goodbye(self, text):
        """Enhanced goodbye detection with variance checks"""
        text_lower = text.lower().strip()
        
        # Pattern-based detection for "have a ____ day" variations
        day_patterns = [
            r'\bhave\s+an?\s+\w+\s+day\b',  # have a/an [adjective] day
            r'\bhave\s+a\s+good\s+\w+\b',   # have a good [time period]
            r'\bhave\s+a\s+great\s+\w+\b',  # have a great [time period]
            r'\bhave\s+a\s+wonderful\s+\w+\b',  # have a wonderful [time period]
            r'\bhave\s+a\s+nice\s+\w+\b',   # have a nice [time period]
            r'\bhave\s+a\s+lovely\s+\w+\b', # have a lovely [time period]
            r'\bhave\s+an?\s+amazing\s+\w+\b', # have an amazing [time period]
            r'\bhave\s+an?\s+excellent\s+\w+\b', # have an excellent [time period]
            r'\bhave\s+an?\s+awesome\s+\w+\b',  # have an awesome [time period]
            r'\bhave\s+an?\s+fantastic\s+\w+\b', # have a fantastic [time period]
            r'\bhave\s+an?\s+marvelous\s+\w+\b', # have a marvelous [time period]
            r'\bhave\s+an?\s+terrific\s+\w+\b',  # have a terrific [time period]
        ]
        
        # Check pattern-based goodbyes first
        for pattern in day_patterns:
            if re.search(pattern, text_lower):
                logger.info(f"Pattern-based goodbye detected: '{text}' matches pattern '{pattern}'")
                return True
        
        # Exact phrase detection for other goodbye types
        goodbye_phrases = [
            # Direct goodbyes
            'goodbye', 'good bye', 'bye', 'bye bye', 'see you', 'see ya',
            'talk to you later', 'ttyl', 'take care', 'farewell',
            'catch you later', 'until next time', 'i\'ll talk to you later',
            'talk soon', 'speak soon', 'until we speak again',
            
            # Conversation endings
            'all set', 'that\'s all', 'that\'s everything', 'that\'s it',
            'thank you so much', 'thanks a lot', 'i appreciate it',
            'you\'ve been helpful', 'that helps', 'that\'s helpful',
            
            # Response acknowledgments that often end conversations
            'you too', 'same to you', 'likewise', 'back at you', 
            'right back at you', 'same here', 'ditto',
            
            # Polite endings
            'i\'ll let you go', 'don\'t want to keep you', 'i should go',
            'i need to go', 'gotta go', 'i have to run',
            
            # Gratitude-based endings
            'thank you for your help', 'thanks for the info', 
            'appreciate your time', 'thanks for everything'
        ]
        
        # Check for exact phrase matches
        for phrase in goodbye_phrases:
            if phrase in text_lower:
                logger.info(f"Exact phrase goodbye detected: '{text}' contains '{phrase}'")
                return True
        
        # Check for abbreviated or partial matches
        abbreviated_goodbyes = [
            'thx', 'ty', 'k thanks', 'ok thanks', 'alright thanks',
            'got it', 'understood', 'perfect', 'great', 'awesome'
        ]
        
        # Only consider abbreviated goodbyes if they're the entire message or end the message
        for abbrev in abbreviated_goodbyes:
            if text_lower == abbrev or text_lower.endswith(abbrev):
                logger.info(f"Abbreviated goodbye detected: '{text}' matches '{abbrev}'")
                return True
        
        logger.debug(f"No goodbye detected in: '{text}'")
        return False
    
    async def start_silence_timer(self):
        """Start 90-second silence detection timer"""
        if self.conversation_ended or self.silence_check_sent:
            return
            
        logger.info("🔇 Starting 90-second silence detection timer...")
        
        # Cancel any existing silence timer
        if self.silence_timer:
            self.silence_timer.cancel()
        
        async def check_silence():
            try:
                await asyncio.sleep(90)  # Wait 90 seconds
                if not self.conversation_ended and not self.silence_check_sent and self.session_active:
                    logger.info("🔇 90 seconds of silence detected - asking if user is still there")
                    await self.send_silence_check()
            except asyncio.CancelledError:
                logger.info("Silence timer cancelled - user spoke")
        
        self.silence_timer = asyncio.create_task(check_silence())
    
    async def send_silence_check(self):
        """Send 'are you still there?' message and start 8-second final timer"""
        if self.conversation_ended or not self.openai_ws:
            return
            
        self.silence_check_sent = True
        logger.info("🤖 Sending silence check: 'Are you still there?'")
        
        try:
            # Send instruction to AI to ask if user is still there
            silence_check_response = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Say exactly: 'Are you still there?'"
                }
            }
            await self.openai_ws.send(json.dumps(silence_check_response))
            
            # Start 8-second final hangup timer
            await self.start_final_silence_timer()
            
        except Exception as e:
            logger.error(f"Error sending silence check: {str(e)}")
    
    async def start_final_silence_timer(self):
        """Start 8-second timer after asking 'are you still there?'"""
        logger.info("⏰ Starting 8-second final silence timer...")
        
        async def final_hangup():
            try:
                await asyncio.sleep(8)  # Wait 8 seconds
                if not self.conversation_ended and self.silence_check_sent:
                    logger.info("🔚 No response to silence check - hanging up")
                    await self.hangup_call(self.telnyx_ws)
            except asyncio.CancelledError:
                logger.info("Final silence timer cancelled - user responded")
        
        self.silence_hangup_timer = asyncio.create_task(final_hangup())
    
    async def reset_silence_detection(self):
        """Reset silence detection when user speaks"""
        # Only reset if we're not in greeting protection mode
        if self.initial_greeting_active:
            return
            
        # Cancel existing timers
        if self.silence_timer:
            self.silence_timer.cancel()
            self.silence_timer = None
        
        if self.silence_hangup_timer:
            self.silence_hangup_timer.cancel()
            self.silence_hangup_timer = None
        
        # Reset flags
        self.silence_check_sent = False
        self.last_user_speech_time = datetime.now()
        
        # Start new silence timer
        await self.start_silence_timer()
    
    async def start_greeting_protection(self):
        """Start protection period to ignore transcriptions during initial greeting"""
        self.initial_greeting_active = True
        logger.info("🛡️ Starting greeting protection - ignoring transcriptions for 5 seconds")
        
        async def disable_protection():
            try:
                await asyncio.sleep(5)  # Wait 5 seconds for greeting to complete
                self.initial_greeting_active = False
                logger.info("🛡️ Greeting protection disabled - now listening for real user speech")
                # Start silence detection after greeting protection ends
                await self.start_silence_timer()
            except asyncio.CancelledError:
                logger.info("Greeting protection timer cancelled")
        
        self.greeting_protection_timer = asyncio.create_task(disable_protection())
    
    async def start_hangup_timer(self, telnyx_ws):
        """Start 20-second countdown for auto-hangup after AI goodbye"""
        if self.conversation_ended:
            logger.info("Not starting timer - conversation already ended")
            return
            
        logger.info("🔥 Starting 20-second hangup timer...")
        
        # Cancel any existing timer
        if self.hangup_timer:
            self.hangup_timer.cancel()
            logger.info("Cancelled previous timer")
        
        async def hangup_after_delay():
            try:
                logger.info("⏰ Timer started - waiting 20 seconds...")
                await asyncio.sleep(20)  # Wait 20 seconds
                if not self.conversation_ended:
                    logger.info("🔚 20 seconds elapsed - hanging up call now!")
                    await self.hangup_call(telnyx_ws)
                else:
                    logger.info("Call already ended, skipping hangup")
            except asyncio.CancelledError:
                logger.info("⏹️ Hangup timer cancelled - conversation continued")
        
        self.hangup_timer = asyncio.create_task(hangup_after_delay())
        logger.info("Timer task created successfully")
    
    async def hangup_call(self, telnyx_ws):
        """End the call using Telnyx API and save transcript to database"""
        if self.conversation_ended:
            logger.info("Call already ended, skipping hangup")
            return
            
        logger.info("🔚 HANGING UP CALL NOW!")
        self.conversation_ended = True
        
        try:
            # NEW: Save conversation transcript to database before hanging up
            await self.save_call_transcript()
            
            # Send hangup command via Telnyx API
            import requests
            
            hangup_url = f"https://api.telnyx.com/v2/calls/{self.call_sid}/actions/hangup"
            headers = {
                "Authorization": f"Bearer {os.getenv('API_KEY')}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"Sending hangup request to: {hangup_url}")
            response = requests.post(hangup_url, headers=headers)
            logger.info(f"📞 Call hangup initiated - Status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Hangup request failed: {response.text}")
            
        except Exception as e:
            logger.error(f"❌ Error hanging up call: {str(e)}")
        
        # Close connections
        await self.close_connections()
    
    async def save_call_transcript(self):
        """Save the conversation transcript to database and generate summary/notifications"""
        try:
            if not self.conversation_transcript:
                logger.info("📝 No transcript to save")
                return
            
            if not self.db:
                logger.warning("📝 No database service available - skipping transcript save")
                return
            
            # Sort transcript by time before saving
            self.conversation_transcript.sort(key=lambda x: x['time'])

            # End call logging with transcript
            success = self.db.end_call_logging(
                call_control_id=self.call_sid,
                transcript=self.conversation_transcript,
                customer_name=self.customer_name,
                status='completed'
            )
            
            if success:
                logger.info(f"✅ Call transcript saved to database: {len(self.conversation_transcript)} messages")
                
                # NEW: Generate AI summary and check for notifications
                if self.ai_summarizer:
                    try:
                        # Generate summary AND extract customer name
                        logger.info(f"📝 Generating AI summary for call {self.call_sid}")
                        result = self.ai_summarizer.summarize_call_transcript(
                            self.conversation_transcript,
                            self.customer_name,
                            getattr(self, 'caller_phone_number', None)
                        )
                        
                        # Extract summary and customer name from AI response
                        summary = result.get('summary', 'Unable to generate summary')
                        extracted_name = result.get('customer_name')
                        
                        # Update call with summary
                        self.db.update_call_summary(self.call_sid, summary)
                        
                        # NEW: Use AI-extracted name if available
                        if extracted_name and extracted_name.lower() != "none":
                            self.customer_name = extracted_name.capitalize()
                            logger.info(f"👤 Using AI-extracted customer name for call: {self.customer_name}")
                        elif not self.customer_name:
                            logger.info(f"👤 No customer name found in call transcript")
                        
                        # Check for notifications
                        logger.info(f"🔍 Checking for notifications in call {self.call_sid}")
                        notification = self.ai_summarizer.analyze_for_notifications(
                            summary,
                            self.conversation_transcript,
                            'voice',
                            getattr(self, 'caller_phone_number', None),
                            self.customer_name
                        )
                        
                        if notification:
                            self.db.create_notification(
                                notification['type'],
                                notification['title'],
                                notification['summary'],
                                notification['phone'],
                                notification['customer_name'],
                                notification['conversation_type'],
                                self.call_sid  # Use call_sid as conversation_id
                            )
                            logger.info(f"🚨 Notification created for call: {notification['title']}")
                        else:
                            logger.info(f"✅ No notifications needed for call {self.call_sid}")
                            
                    except Exception as e:
                        logger.error(f"❌ Error generating summary/notifications for call: {str(e)}")
                        import traceback
                        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            else:
                logger.error("❌ Failed to save call transcript to database")
                
        except Exception as e:
            logger.error(f"❌ Error saving call transcript: {str(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
    
    async def connect_to_openai(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        try:
            self.openai_ws = await websockets.connect(url, extra_headers=headers)
            logger.info("Connected to OpenAI Realtime API")
            
            # Configure the session
            await self.configure_session()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {str(e)}")
            return False
    
    async def configure_session(self):
        """Configure the OpenAI session with instructions and function calling"""
        # Determine greeting based on business hours (with override support)
        is_business_hours = self.get_business_hours_status()
        
        if not is_business_hours:  # Only configure if we're in after-hours mode
            # UPDATED: Enhanced knowledge base guidance for voice calls
            instructions = """You are a professional AI receptionist for Radiance MD Med Spa.

            CRITICAL BOOKING FLOW - FOLLOW THIS EXACT ORDER:
            1. When customer wants to book: Ask "Is the phone number you're calling from the best number to reach you? If not, please provide your preferred number." THEN call collect_phone_first function with their response
            2A. IF RETURNING CUSTOMER with UP-NEXT service: The system will automatically welcome them back and suggest their up-next service (e.g., "Welcome back, Sarah! I see you're due for your Second Botox Dose. Would you like to book that, or would you prefer a different service?") THEN call handle_up_next_service_suggestion function with their response
            2B. IF RETURNING CUSTOMER without up-next: The system will automatically welcome them back and ask "What type of service would you like to book today?" THEN call collect_service function
            2C. IF NEW CUSTOMER (not in database): The system will say they're not in the system and ask "What's your first name?" THEN call collect_first_name function
            3A. FOR UP-NEXT RESPONSES: When customer responds to the up-next suggestion, ALWAYS call handle_up_next_service_suggestion function first with their exact response. This function will automatically handle whether they accept or decline and proceed to the next appropriate step.
            3B. FOR NEW CUSTOMERS ONLY: After collecting first name: Ask "Could you please spell your last name for me, letter by letter?" THEN call collect_last_name_spelled function with their spelled response
            4. FOR NEW CUSTOMERS ONLY: After collecting spelled last name: Read back the full name and ask "Let me confirm - your name is [First Name] [Spelled Last Name]. Is that correct?" THEN call confirm_name_collection function with their confirmation
            5. FOR ALL CUSTOMERS: After phone/name/service collection is complete: Ask "What date and time would you like?" THEN call collect_date_time function
            6. After collecting date/time: Ask "Do you have a preference for which specialist you'd like to see, or would you like us to assign one for you?" THEN call collect_specialist_preference function
            7. After collecting specialist: Call confirm_booking function with ALL collected information

            CRITICAL RULES:
            - ALWAYS start with phone number collection using collect_phone_first function
            - The collect_phone_first function will automatically determine if customer is returning or new, and if they have an up-next service
            - For NEW customers: Follow the complete name collection process (first name → spelled last name → confirmation)
            - ALWAYS call the corresponding function after collecting each piece of information
            - NEVER assume or guess any information (names, dates, times, phone numbers)
            - Today's date is """ + datetime.now().strftime('%Y-%m-%d') + """
            - When customers say "tomorrow", use """ + (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d') + """
            - When they say a day name, calculate the correct 2025 date


            KNOWLEDGE BASE USAGE:
            - When customers ask about business information (hours, services, location, staff, pricing, policies), IMMEDIATELY use the get_business_information function.
            - When you get information from the knowledge base, use it directly in your response
            - DO NOT add generic phrases like "Call us for more information" when you successfully answer questions
            - Only suggest calling if you genuinely cannot answer the question or for complex booking requests
            - When you have the information, just provide it directly without additional suggestions

            STAFF INFORMATION:
            - For staff questions, the system will automatically check staff management settings first
            - If staff is configured in settings, that information takes priority over knowledge base
            - If no staff is configured, the system will fall back to knowledge base content
            - Always use the most current staff information available

            RESPONSE GUIDELINES:
            - Be professional, friendly, and helpful
            - Use the information provided by function calls directly
            - Don't make up information - only use what's provided by the functions
            - Keep responses conversational and natural for voice interactions"""
        else:
            # This shouldn't happen since we only activate voice AI during after hours
            instructions = """You are a professional AI receptionist for Radiance MD Med Spa.

            CRITICAL BOOKING FLOW - FOLLOW THIS EXACT ORDER:
            1. When customer wants to book: Ask "What's your first name?" THEN call collect_first_name function with their response
            2. After collecting first name: Ask "Could you please spell your last name for me, letter by letter?" THEN call collect_last_name_spelled function with their spelled response
            3. After collecting spelled last name: Read back the full name and ask "Let me confirm - your name is [First Name] [Spelled Last Name]. Is that correct?" THEN call confirm_name_collection function with their confirmation
            4. After name confirmation: Ask "Is the phone number you're calling from the best number to reach you? If not, please provide your preferred number." THEN call collect_phone function with their response
            5. After collecting phone: Ask "What type of service would you like to book?" THEN call collect_service function
            6. After collecting service: Ask "What date and time would you like?" THEN call collect_date_time function
            7. After collecting date/time: Ask "Do you have a preference for which specialist you'd like to see, or would you like us to assign one for you?" THEN call collect_specialist_preference function
            8. After collecting specialist: Call confirm_booking function with ALL collected information

            CRITICAL RULES:
            - ALWAYS start with phone number collection using collect_phone_first function
            - The collect_phone_first function will automatically determine if customer is returning or new, and if they have an up-next service
            - For NEW customers: Follow the complete name collection process (first name → spelled last name → confirmation)
            - ALWAYS call the corresponding function after collecting each piece of information
            - NEVER assume or guess any information (names, dates, times, phone numbers)
            - Today's date is """ + datetime.now().strftime('%Y-%m-%d') + """
            - When customers say "tomorrow", use """ + (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d') + """
            - When they say a day name, calculate the correct 2025 date

            KNOWLEDGE BASE USAGE:
            - When customers ask about business information, IMMEDIATELY use the get_business_information function.
            - When you get information from the knowledge base, use it directly in your response
            - DO NOT add generic phrases like "Call us for more information" when you successfully answer questions
            - Only suggest calling if you genuinely cannot answer the question or for complex booking requests
            - When you have the information, just provide it directly without additional suggestions

            STAFF INFORMATION:
            - For staff questions, the system will automatically check staff management settings first
            - If staff is configured in settings, that information takes priority over knowledge base
            - If no staff is configured, the system will fall back to knowledge base content
            - Always use the most current staff information available

            RESPONSE GUIDELINES:
            - Be professional, friendly, and helpful
            - Use the information provided by function calls directly
            - Don't make up information - only use what's provided by the functions
            - Keep responses conversational and natural for voice interactions"""
        
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": instructions,
                "voice": "shimmer",
                "input_audio_format": "g711_ulaw",  # PCMU format as recommended
                "output_audio_format": "g711_ulaw",  # PCMU format as recommended
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.3,
                    "prefix_padding_ms": 600,
                    "silence_duration_ms": 1000  # Updated: longer silence for better flow
                },
                "tools": self.appointment_functions,
                "tool_choice": "auto",  # <-- ADD THIS LINE HERE
                "temperature": 0.7,  # Fixed: minimum 0.6 for Realtime API
                "max_response_output_tokens": 1000
            }
        }
        
        await self.openai_ws.send(json.dumps(session_config))
        logger.info("OpenAI session configured with appointment booking and knowledge base functions")
    
    async def handle_telnyx_audio(self, audio_data):
        """Forward audio from Telnyx to OpenAI"""
        if not self.openai_ws or not self.session_active:
            return
        
        # Skip processing during initial greeting protection period
        if self.initial_greeting_active:
            return  # Don't forward audio during greeting
        
        # Reduce feedback by not processing audio when AI is speaking
        if self.ai_speaking:
            return  # Skip processing while AI is talking
        
        try:
            # No conversion needed - both use PCMU (G.711 µ-law)
            audio_event = {
                "type": "input_audio_buffer.append",
                "audio": audio_data
            }
            await self.openai_ws.send(json.dumps(audio_event))
        except websockets.exceptions.ConnectionClosed:
            logger.warning("OpenAI connection closed while forwarding audio")
            self.session_active = False
        except Exception as e:
            logger.error(f"Error forwarding audio to OpenAI: {str(e)}")
    
    async def handle_openai_response(self, telnyx_ws):
        """Handle responses from OpenAI and forward to Telnyx"""
        try:
            async for message in self.openai_ws:
                data = json.loads(message)
                event_type = data.get("type")
                
                
                if event_type == "session.created":
                    logger.info("OpenAI session created")
                    self.session_active = True
                    # Don't start silence timer yet - wait for greeting protection to end
                    
                elif event_type == "response.audio.delta":
                    # Forward audio directly - both use PCMU format
                    audio_data = data.get("delta")
                    if audio_data and telnyx_ws:
                        self.ai_speaking = True  # Mark AI as speaking
                        
                        telnyx_message = {
                            "event": "media",
                            "media": {
                                "payload": audio_data
                            }
                        }
                        try:
                            await telnyx_ws.send(json.dumps(telnyx_message))
                        except Exception as e:
                            logger.error(f"Error sending audio to Telnyx: {str(e)}")
                
                elif event_type == "response.audio.done":
                    logger.info("OpenAI audio response finished")
                    self.ai_speaking = False  # AI finished speaking
                
                elif event_type == "response.function_call_arguments.done":
                    # Function call arguments completed - execute it
                    call_id = data.get("call_id")
                    function_name = data.get("name")
                    arguments_str = data.get("arguments", "{}")
                    
                    logger.info(f"🔧 Executing function: {function_name} with args: {arguments_str}")
                    
                    try:
                        arguments = json.loads(arguments_str)
                        
                        # Execute the function
                        function_result = await self.execute_appointment_function(function_name, arguments)
                        
                        # Send the result back to OpenAI
                        function_output = {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": json.dumps(function_result)
                            }
                        }
                        await self.openai_ws.send(json.dumps(function_output))
                        
                        # Create a response to continue the conversation
                        response_create = {
                            "type": "response.create"
                        }
                        await self.openai_ws.send(json.dumps(response_create))
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Error parsing function arguments: {e}")
                        logger.error(f"❌ Raw arguments: {arguments_str}")
                
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = data.get("transcript", "")
                    duration = data.get("duration")  # duration in seconds, may be float

                    # Ignore transcriptions during initial greeting protection period
                    if self.initial_greeting_active:
                        logger.info(f"🛡️ Ignoring transcription during greeting protection: '{transcript}'")
                        continue

                    logger.info(f"User said: {transcript}")

                    # Estimate utterance start time
                    event_arrival = datetime.now()
                    if duration:
                        try:
                            # Subtract duration and 2.25 seconds
                            utterance_start = event_arrival - timedelta(seconds=float(duration) + 2.25)
                        except Exception:
                            utterance_start = event_arrival - timedelta(seconds=2.25)
                    else:
                        utterance_start = event_arrival - timedelta(seconds=2.25)

                    self.conversation_transcript.append({
                        "speaker": "user",
                        "text": transcript,
                        "time": utterance_start.strftime('%H:%M:%S')  # No milliseconds for consistency
                    })

                    # Note: Name extraction now happens during summary generation, not here

                    # Reset silence detection since user spoke
                    await self.reset_silence_detection()
                
                elif event_type == "response.text.done":
                    # NEW: Capture AI response for transcript
                    response_text = data.get("text", "")
                    if response_text.strip():
                        self.conversation_transcript.append({
                            "speaker": "ai",
                            "text": response_text,
                            "time": datetime.now().strftime('%H:%M:%S')
                        })
                        logger.info(f"AI said: {response_text}")
                        
                        # NEW: Check for false booking confirmation in voice responses
                        if self.booking_verification_service and self.caller_phone_number:
                            self.booking_verification_service.log_ai_response(self.caller_phone_number, response_text)
                            
                            # Check for false booking confirmation
                            is_false_confirmation, alert_message = self.booking_verification_service.check_for_false_booking_confirmation(self.caller_phone_number, response_text)
                            
                            if is_false_confirmation:
                                logger.error(f"�� FALSE BOOKING CONFIRMATION DETECTED in voice call for {self.caller_phone_number}")
                                logger.error(f"🚨 Response: {response_text}")
                                
                                # Send alert
                                self.booking_verification_service.send_false_booking_alert(self.caller_phone_number, response_text, alert_message)
                                
                                # Note: For voice calls, we can't easily replace the response, but we log it
                                # The alert will ensure management is notified immediately
                        
                    # Check AI's text response for goodbye and start hangup timer
                    if response_text and self.detect_goodbye(response_text):
                        logger.info("AI said goodbye - starting 20-second hangup timer")
                        await self.start_hangup_timer(telnyx_ws)
                
                elif event_type == "input_audio_buffer.speech_started":
                    # Ignore speech detection during initial greeting protection period
                    if self.initial_greeting_active:
                        logger.info("🛡️ Ignoring speech detection during greeting protection")
                        continue
                        
                    logger.info("User started speaking - resetting silence detection")
                    
                    # Reset silence detection since user spoke
                    await self.reset_silence_detection()
                    
                    # Cancel hangup timer if user starts speaking again
                    if self.hangup_timer:
                        self.hangup_timer.cancel()
                        logger.info("Hangup timer cancelled - user speaking")
                
                elif event_type == "response.done":
                    logger.info("OpenAI response completed")
                
                elif event_type == "error":
                    logger.error(f"OpenAI error: {data}")
                    
                elif event_type == "response.audio_transcript.done":
                    transcript = data.get("transcript", "")
                    if transcript.strip():
                        self.conversation_transcript.append({
                            "speaker": "ai",
                            "text": transcript,
                            "time": datetime.now().strftime('%H:%M:%S')
                        })
                        logger.info(f"AI (audio transcript) said: {transcript}")
                        
                        # Check AI's audio transcript for goodbye and start hangup timer
                        if self.detect_goodbye(transcript):
                            logger.info("AI said goodbye (audio transcript) - starting 20-second hangup timer")
                            await self.start_hangup_timer(telnyx_ws)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info("OpenAI connection closed")
        except Exception as e:
            logger.error(f"Error handling OpenAI response: {str(e)}")
    
    async def start_conversation(self):
        """Start the conversation with initial greeting"""
        if not self.openai_ws:
            return
        
        try:
            # Reset booking state machine for new conversation
            self.booking_state_machine.reset()
            
            # Start greeting protection before sending the greeting
            await self.start_greeting_protection()
            
            # Create a conversation item to trigger the initial greeting
            create_response = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Say exactly: 'Thank you for calling Radiance MD Med Spa how can I help you?'"
                }
            }
            await self.openai_ws.send(json.dumps(create_response))
            logger.info("Initial conversation started with greeting protection enabled")
        except Exception as e:
            logger.error(f"Error starting conversation: {str(e)}")
    
    async def close_connections(self):
        """Clean up connections"""
        # Ensure transcript is saved and call is marked as completed for after-hours calls
        if not self.conversation_ended and self.conversation_transcript and self.db:
            # Only do this for after-hours (AI handled) calls
            # (Assume that if self.db is set, we're in an AI session)
            logger.info("[CLOSE] Saving transcript and marking call as completed before closing connections.")
            await self.save_call_transcript()
        if self.hangup_timer:
            self.hangup_timer.cancel()
        if self.silence_timer:
            self.silence_timer.cancel()
        if self.silence_hangup_timer:
            self.silence_hangup_timer.cancel()
        if self.greeting_protection_timer:
            self.greeting_protection_timer.cancel()
        if self.openai_ws:
            await self.openai_ws.close()
        self.session_active = False
        logger.info("Connections closed")

    def set_services(self, db_service, ai_summarizer_service):
        """Set database and AI summarizer services after initialization"""
        self.db = db_service
        self.ai_summarizer = ai_summarizer_service
        
        # Update appointment service with database service
        if db_service:
            self.appointment_service = AppointmentService(database_service=db_service)
            logger.info("✅ Voice system: AppointmentService re-instantiated with database service")
        
        # Update knowledge base service with database service
        if db_service:
            self.knowledge_base_service.db = db_service
            logger.info("✅ Voice system: Database service set for knowledge base")
        
        # Initialize booking verification service
        if db_service:
            from booking_verification_service import BookingVerificationService
            self.booking_verification_service = BookingVerificationService(database_service=db_service)
            logger.info("✅ Voice system: Booking verification service initialized")
        
        # Dynamically fetch services and specialists for function enums
        service_names = []
        specialist_names = []
        if self.db:
            try:
                service_names = [s['name'] for s in self.db.get_services()]
                specialist_names = self.db.get_active_staff_names()
            except Exception as e:
                logger.error(f"Error fetching services/specialists for Realtime function enum: {str(e)}")
        self.no_services_fallback = "I'm sorry, I don't have access to our list of services at the moment. Please check back soon or contact us directly for more information."
        # Update appointment_functions with dynamic enums
        self.appointment_functions = [
            {
                "type": "function",
                "name": "collect_phone_first",
                "description": "Collect the customer's phone number first to check if they are a returning customer. Ask 'Is the phone number you're calling from the best number to reach you? If not, please provide your preferred number.' If they say 'yes' or confirm, pass 'yes' as the phone parameter. If they provide a different number, pass their actual phone number. The system will validate the format and perform database lookup to determine if customer is returning or new.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number or 'yes' if they confirm using caller ID"}
                    },
                    "required": ["phone"]
                }
            },
            {
                "type": "function",
                "name": "handle_up_next_service_suggestion",
                "description": "Handle customer response when they are presented with their up_next service suggestion. Call this when customer responds to 'I see you're due for your [service]. Would you like to book that, or would you prefer a different service?' If they accept, proceed to date/time. If they decline, proceed to normal service selection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "response": {"type": "string", "description": "Customer's response to the up_next service suggestion"}
                    },
                    "required": ["response"]
                }
            },
            {
                "type": "function",
                "name": "collect_first_name",
                "description": "Collect the customer's first name for NEW customers only. This is called after phone lookup determines customer is not in database. After collecting the first name, immediately call the collect_last_name_spelled function to get the spelled last name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string", "description": "Customer's first name"}
                    },
                    "required": ["first_name"]
                }
            },
            {
                "type": "function",
                "name": "collect_last_name_spelled",
                "description": "Collect the customer's last name spelled out letter by letter for NEW customers only. After collecting the spelled last name, immediately call the confirm_name_collection function to confirm the full name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "last_name_spelled": {"type": "string", "description": "Customer's last name spelled out letter by letter (e.g., 'S M I T H' or 'B O W E')"}
                    },
                    "required": ["last_name_spelled"]
                }
            },
            {
                "type": "function",
                "name": "confirm_name_collection",
                "description": "Confirm the customer's full name (first name + spelled last name) for NEW customers only. After confirmation, immediately call the collect_service function to get the service type.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirmation": {"type": "string", "description": "Customer's confirmation response (yes/no or similar)"}
                    },
                    "required": ["confirmation"]
                }
            },
            {
                "type": "function",
                "name": "collect_service",
                "description": "Collect the type of service the customer wants to book. This is called for ALL customers (returning and new) after phone/name collection is complete. After collecting the service, immediately call the collect_date_time function to get the appointment date and time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "enum": service_names, "description": "Type of service requested"}
                    },
                    "required": ["service"]
                }
            },
            {
                "type": "function",
                "name": "collect_date_time",
                "description": "Collect the appointment date and time from the customer. After collecting both, immediately call the collect_specialist_preference function to get any specialist preference.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Appointment date in YYYY-MM-DD format"},
                        "time": {"type": "string", "description": "Appointment time in HH:MM format (24-hour)"}
                    },
                    "required": ["date", "time"]
                }
            },
            {
                "type": "function",
                "name": "collect_specialist_preference",
                "description": "Collect the customer's preferred specialist, if any. After collecting this, immediately call the confirm_booking function to finalize the booking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "specialist_preference": {"type": "string", "enum": specialist_names, "description": "Preferred specialist (optional)"}
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "confirm_booking",
                "description": "ONLY call this function after ALL required information has been collected via the previous functions. This will actually book the appointment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Customer's full name"},
                        "phone": {"type": "string", "description": "Customer's phone number"},
                        "date": {"type": "string", "description": "Appointment date in YYYY-MM-DD format"},
                        "time": {"type": "string", "description": "Appointment time in HH:MM format (24-hour)"},
                        "service": {"type": "string", "enum": service_names, "description": "Type of service requested"},
                        "specialist_preference": {"type": "string", "enum": specialist_names, "description": "Preferred specialist (optional)"}
                    },
                    "required": ["name", "phone", "date", "time", "service"]
                }
            },
            {
                "type": "function",
                "name": "check_availability",
                "description": "Check available appointment slots for a specific date. Call this when customer asks what times or hours are available for booking an appointment. Required for ALL availability requests. Avoid naming all available times. Simply state a general range of availability and/or mention unavailable times",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date to check in YYYY-MM-DD format"},
                        "service": {"type": "string", "enum": service_names, "description": "Type of service to check availability for"}
                    },
                    "required": ["date", "service"]
                }
            },
            {
                "type": "function",
                "name": "get_business_information",
                "description": "Get specific business information from knowledge base. ONLY use when customer asks about business details like hours, services, location, staff, policies, pricing, etc. DO NOT use for appointment booking - use book_appointment function instead. DO NOT use for general conversation - only for business information questions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {"type": "string", "enum": ["hours", "services", "location", "staff", "policies", "pricing", "general"], "description": "Type of business information needed"},
                        "specific_question": {"type": "string", "description": "The customer's specific question"}
                    },
                    "required": ["query_type", "specific_question"]
                }
            },
            # Cancellation functions
            {
                "type": "function",
                "name": "collect_cancellation_phone",
                "description": "Collect the phone number for appointment cancellation. Ask 'Did you schedule with the number you are calling from? If not, please provide the number you scheduled the appointment with.' If they confirm they're calling from the same number, pass an empty string or 'same' - the function will automatically use the caller ID. If they provide a different number, pass that actual phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number (pass empty string or 'same' if they confirm they're calling from the same number, otherwise pass their actual provided number)"}
                    },
                    "required": ["phone"]
                }
            },
            {
                "type": "function",
                "name": "search_appointments_by_phone",
                "description": "Search for upcoming appointments using the provided phone number. Call this after collecting the cancellation phone number. This will find all upcoming appointments for that phone number and present them to the customer for selection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Phone number to search for appointments"}
                    },
                    "required": ["phone"]
                }
            },
            {
                "type": "function",
                "name": "select_appointment_to_cancel",
                "description": "Handle appointment selection when multiple appointments are found. Call this when the customer specifies which appointment they want to cancel. You can pass: 1) The exact Google Calendar event ID, 2) A position number (1, 2, 3, etc.) corresponding to the appointment in the list, or 3) A description like 'consultation with Sarah' or 'HydraFacial'. If only one appointment was found, this function should be called automatically with that appointment's event_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Google Calendar event ID, position number, or description of the appointment to cancel"}
                    },
                    "required": ["event_id"]
                }
            },
            {
                "type": "function",
                "name": "confirm_cancellation",
                "description": "Confirm and execute the appointment cancellation. This will validate the 24-hour policy, cancel the appointment, and handle all cleanup. Call this after the customer confirms they want to cancel the selected appointment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Google Calendar event ID of the appointment to cancel"}
                    },
                    "required": ["event_id"]
                }
            },
        ] + self.appointment_functions  # Prepend cancellation functions
        logger.info(f"✅ Voice system: Appointment functions updated with {len(service_names)} services and {len(specialist_names)} specialists.")
        logger.info("✅ Voice system: Services and specialists initialized")
        # Reset the booking state machine when services are updated
        self.booking_state_machine.reset()

    def get_booking_progress_message(self):
        """Get a message describing the current booking progress"""
        collected = len(self.booking_state_machine.collected_data)
        total = len(self.booking_state_machine.required_steps)
        next_step = self.booking_state_machine.get_next_step()
        
        if next_step == "phone_first":
            return "I need to collect your phone number first. Is the phone number you're calling from the best number to reach you? If not, please provide your preferred number."
        elif next_step == "up_next_suggestion":
            up_next_service = self.booking_state_machine.collected_data.get("up_next_service", "your scheduled service")
            return f"I need to confirm your service choice. Would you like to book your {up_next_service}, or would you prefer a different service?"
        elif next_step == "first_name":
            return "I need to collect your first name. What's your first name?"
        elif next_step == "last_name_spelled":
            return "I need your last name spelled out. Could you please spell your last name for me, letter by letter?"
        elif next_step == "name_confirmation":
            first_name = self.booking_state_machine.collected_data.get("first_name", "")
            last_name_spelled = self.booking_state_machine.collected_data.get("last_name_spelled", "")
            return f"I need to confirm your name. Let me confirm - your name is {first_name} {last_name_spelled}. Is that correct?"
        elif next_step == "service":
            return "I need to know what service you'd like to book. What type of service would you like?"
        elif next_step == "datetime":
            return "I need to know when you'd like your appointment. What date and time would you like?"
        elif next_step == "specialist":
            return "I need to know about specialist preferences. Do you have a preference for which specialist you'd like to see, or would you like us to assign one for you?"
        else:
            return f"Booking progress: {collected}/{total} steps complete. Next step: {next_step}"
    
    def get_cancellation_progress_message(self):
        """Get a message describing the current cancellation progress"""
        collected = len(self.cancellation_state_machine.collected_data)
        total = len(self.cancellation_state_machine.required_steps)
        next_step = self.cancellation_state_machine.get_next_step()
        
        if next_step == "phone":
            return "I need to confirm your phone number. Did you schedule with the number you are calling from? If not, please provide the number you scheduled the appointment with."
        elif next_step == "appointment_selection":
            return "I need to know which appointment you'd like to cancel. Please specify which appointment from the list I provided."
        elif next_step == "confirmation":
            return "I need your confirmation to cancel the appointment. Please confirm that you want to cancel this appointment."
        else:
            return f"Cancellation progress: {collected}/{total} steps complete. Next step: {next_step}"
    
    def handle_premature_function_call(self, function_name: str):
        """Handle when AI tries to call a function before collecting all required information"""
        logger.warning(f"⚠️ AI tried to call {function_name} prematurely")
        
        if function_name == "confirm_booking":
            progress_message = self.get_booking_progress_message()
            return {
                "error": f"I cannot book the appointment yet. {progress_message}",
                "progress": len(self.booking_state_machine.collected_data),
                "total_steps": len(self.booking_state_machine.required_steps),
                "next_step": self.booking_state_machine.get_next_step()
            }
        elif function_name == "collect_last_name_spelled":
            return {
                "error": "I need to collect the first name before asking for the last name. What's your first name?"
            }
        elif function_name == "confirm_name_collection":
            return {
                "error": "I need to collect both first and last name before confirming. Let me get your name step by step."
            }
        else:
            return {
                "error": f"Cannot call {function_name} yet. Please follow the booking flow step by step."
            }
    
    # NEW: Cancellation function handlers
    async def collect_cancellation_phone_function(self, phone: str):
        """Handle phone collection for cancellation"""
        logger.info(f"📞 Cancellation - Collected phone: {phone}")
        
        # Handle caller ID logic - if empty/same, use caller ID
        caller_phone = getattr(self, 'caller_phone_number', None)
        if not phone or phone.lower() in ["same", "yes", "y", "yeah", "sure"]:
            if caller_phone:
                logger.info(f"📞 Cancellation - Using caller ID {caller_phone} instead of '{phone}'")
                phone = caller_phone
            else:
                logger.error("📞 Cancellation - No caller ID available")
                return {
                    "success": False,
                    "message": "I'm sorry, I couldn't determine your phone number. Please provide the number you scheduled your appointment with.",
                    "error": "No caller ID available"
                }
        
        # Format phone number for consistent database searching
        formatted_phone = self.appointment_service._format_phone_for_search(phone)
        
        self.cancellation_state_machine.add_collected_data("phone", formatted_phone)
        
        return {
            "success": True,
            "message": "Thank you. Let me search for your appointments.",
            "collected_phone": formatted_phone
        }
    
    async def search_appointments_by_phone_function(self, phone: str):
        """Handle appointment search for cancellation"""
        logger.info(f"🔍 Cancellation - Searching appointments for phone: {phone}")
        
        # Check if database service is available
        if not self.db:
            logger.error("❌ Cancellation - Database service not available")
            return {
                "success": False,
                "message": "I'm sorry, I couldn't search for appointments right now. Please try again or contact us during business hours.",
                "error": "Database service not available"
            }
        
        # Use the appointment service to search
        search_result = self.appointment_service.search_appointments_by_phone(phone)
        logger.info(f"🔍 Cancellation - Search result: {search_result}")
        
        if not search_result['success']:
            return {
                "success": False,
                "message": "I'm sorry, I couldn't search for appointments right now. Please try again or contact us during business hours.",
                "error": search_result.get('error', 'Unknown error')
            }
        
        appointments = search_result['appointments']
        formatted_list = search_result['formatted_list']
        
        logger.info(f"🔍 Cancellation - Found {len(appointments)} appointments")
        for i, appt in enumerate(appointments):
            logger.info(f"🔍 Cancellation - Appointment {i+1}: {appt.get('service_name', 'Unknown')} on {appt.get('appointment_date')} at {appt.get('appointment_time')} with {appt.get('specialist', 'team')} (ID: {appt.get('calendar_event_id')})")
        
        # Store appointments in state machine for selection
        self.cancellation_state_machine.set_found_appointments(appointments)
        
        if len(appointments) == 0:
            return {
                "success": True,
                "message": formatted_list,
                "appointments_found": 0
            }
        elif len(appointments) == 1:
            # Auto-select single appointment
            appointment = appointments[0]
            self.cancellation_state_machine.add_collected_data("appointment_selection", appointment['calendar_event_id'])
            
            return {
                "success": True,
                "message": formatted_list,
                "appointments_found": 1,
                "auto_selected": True,
                "event_id": appointment['calendar_event_id']
            }
        else:
            # Multiple appointments - wait for user selection
            return {
                "success": True,
                "message": formatted_list,
                "appointments_found": len(appointments),
                "auto_selected": False
            }
    
    async def select_appointment_to_cancel_function(self, event_id: str):
        """Handle appointment selection for cancellation"""
        logger.info(f"🎯 Cancellation - Selected appointment: {event_id}")
        
        # Validate that this appointment exists in our found appointments
        found_appointments = self.cancellation_state_machine.get_found_appointments()
        selected_appointment = None
        
        # First, try to match by exact event_id
        for appt in found_appointments:
            if appt['calendar_event_id'] == event_id:
                selected_appointment = appt
                break
        
        # If not found by event_id, try to match by position number (1, 2, 3, etc.)
        if not selected_appointment and event_id.isdigit():
            try:
                position = int(event_id) - 1  # Convert to 0-based index
                if 0 <= position < len(found_appointments):
                    selected_appointment = found_appointments[position]
                    logger.info(f"🎯 Cancellation - Selected appointment by position {event_id}: {selected_appointment['calendar_event_id']}")
            except (ValueError, IndexError):
                pass
        
        # If still not found, try to match by service name or specialist
        if not selected_appointment:
            event_id_lower = event_id.lower()
            for appt in found_appointments:
                service_name = appt.get('service_name', '').lower()
                specialist = appt.get('specialist', '').lower()
                
                # Check if the event_id contains service name or specialist
                if (service_name in event_id_lower or 
                    event_id_lower in service_name or
                    specialist in event_id_lower or
                    event_id_lower in specialist):
                    selected_appointment = appt
                    logger.info(f"🎯 Cancellation - Selected appointment by description match: {appt['calendar_event_id']}")
                    break
        
        if not selected_appointment:
            # Log the available appointments for debugging
            available_appts = []
            for i, appt in enumerate(found_appointments, 1):
                available_appts.append(f"{i}. {appt.get('service_name', 'Unknown')} with {appt.get('specialist', 'team')}")
            
            logger.error(f"🎯 Cancellation - Could not find appointment with event_id '{event_id}'. Available: {available_appts}")
            
            return {
                "success": False,
                "message": f"I'm sorry, I couldn't find that appointment. Please specify which appointment you'd like to cancel from the list I provided.",
                "error": "Appointment not found in search results",
                "available_appointments": available_appts
            }
        
        # Use the actual event_id from the selected appointment
        actual_event_id = selected_appointment['calendar_event_id']
        self.cancellation_state_machine.add_collected_data("appointment_selection", actual_event_id)
        
        # Format appointment details for confirmation
        date_str = datetime.strptime(selected_appointment['appointment_date'], '%Y-%m-%d').strftime('%A, %B %d, %Y')
        time_str = datetime.strptime(selected_appointment['appointment_time'], '%H:%M').strftime('%I:%M %p')
        
        return {
            "success": True,
            "message": f"I found your {selected_appointment['service_name']} appointment on {date_str} at {time_str} with {selected_appointment['specialist'] or 'our team'}. Are you sure you want to cancel this appointment?",
            "selected_appointment": selected_appointment,
            "event_id": actual_event_id
        }
    
    async def confirm_cancellation_function(self, event_id: str):
        """Handle final cancellation confirmation"""
        logger.info(f"🗑️ Cancellation - Confirming cancellation for: {event_id}")
        
        # Use the appointment service for validated cancellation
        cancellation_result = self.appointment_service.cancel_appointment_with_validation(event_id)
        
        if not cancellation_result['success']:
            error_message = cancellation_result.get('message', cancellation_result.get('error', 'Unknown error'))
            return {
                "success": False,
                "message": error_message,
                "error": cancellation_result.get('error')
            }
        
        # Mark cancellation as complete in state machine
        self.cancellation_state_machine.add_collected_data("confirmation", "confirmed")
        
        # Format success message
        appointment = cancellation_result['appointment_details']
        date_str = datetime.strptime(appointment['appointment_date'], '%Y-%m-%d').strftime('%A, %B %d, %Y')
        time_str = datetime.strptime(appointment['appointment_time'], '%H:%M').strftime('%I:%M %p')
        
        success_message = (
            f"Your {appointment['service_name']} appointment on {date_str} at {time_str} "
            f"has been cancelled successfully. "
        )
        
        # Add refund information if applicable
        if cancellation_result.get('refund_result'):
            success_message += "If you had a deposit, it will be refunded to your payment method. "
        
        success_message += "Thank you for letting us know. Please call us if you'd like to reschedule."
        
        return {
            "success": True,
            "message": success_message,
            "cancellation_result": cancellation_result
        }
    
    def reset_booking_state(self):
        """Reset the booking state machine"""
        self.booking_state_machine.reset()
    
    def reset_cancellation_state(self):
        """Reset the cancellation state machine"""
        self.cancellation_state_machine.reset()

    # NEW: Phone-first collection function with database lookup
    async def collect_phone_first_function(self, phone: str):
        """Handle phone collection with database lookup for returning customers"""
        logger.info(f"📞 Phone-first collection: {phone}")
        
        # Handle caller ID logic first
        caller_phone = getattr(self, 'caller_phone_number', None)
        actual_phone = phone
        
        if caller_phone:
            phone_lower = phone.lower().strip()
            
            # Case 1: User explicitly says "yes" or mentions "calling from"
            if phone_lower in ["yes", "y", "yeah", "sure", "okay", "ok"] or "calling from" in phone_lower:
                logger.info(f"📞 User confirmed using caller ID - using {caller_phone} instead of '{phone}'")
                actual_phone = caller_phone
            else:
                # Case 2: Check if provided phone number is valid format
                provided_digits = ''.join(filter(str.isdigit, phone))
                
                # Valid phone number formats: 10 digits (US number) or 11 digits (with country code)
                if len(provided_digits) == 10 or len(provided_digits) == 11:
                    # Trust the user's provided number
                    logger.info(f"📞 Using user-provided phone number: {phone} (digits: {provided_digits})")
                    actual_phone = phone
                elif len(provided_digits) == 0:
                    # No digits provided - fall back to caller ID
                    logger.info(f"📞 No phone number provided - using caller ID {caller_phone}")
                    actual_phone = caller_phone
                else:
                    # Invalid format - fall back to caller ID
                    logger.info(f"📞 Invalid phone number format ({len(provided_digits)} digits) - using caller ID {caller_phone} instead of {phone}")
                    actual_phone = caller_phone
        
        # Store the phone number
        self.booking_state_machine.add_collected_data("phone_first", actual_phone)
        
        # Perform database lookup for existing customer
        customer_data = None
        if self.db:
            try:
                # Format phone for database search
                formatted_phone = self.appointment_service._format_phone_for_search(actual_phone)
                customer_data = self.db.get_customer(formatted_phone)
                logger.info(f"🔍 Customer lookup for {formatted_phone}: {'Found' if customer_data else 'Not found'}")
            except Exception as e:
                logger.error(f"❌ Error looking up customer: {str(e)}")
        
        if customer_data and customer_data.get('name'):
            # RETURNING CUSTOMER FLOW
            customer_name = customer_data['name']
            up_next_service = customer_data.get('up_next_from_you', '').strip() if customer_data.get('up_next_from_you') else None
            logger.info(f"🎉 Returning customer found: {customer_name}")
            logger.info(f"🔍 Up next service: {up_next_service if up_next_service else 'None'}")
            
            # Set customer type and update state machine
            self.booking_state_machine.set_customer_type("returning", has_up_next=bool(up_next_service))
            self.booking_state_machine.add_collected_data("customer_name", customer_name)
            
            # Store customer data for potential use
            self.customer_name = customer_name
            
            # Check if there's an up_next service to suggest
            if up_next_service and len(up_next_service) > 0:
                # Store up_next service for suggestion
                self.booking_state_machine.add_collected_data("up_next_service", up_next_service)
                
                return {
                    "success": True,
                    "customer_type": "returning",
                    "has_up_next": True,
                    "message": f"Welcome back, {customer_name}! I see you're due for your {up_next_service}. Would you like to book that, or would you prefer a different service?",
                    "customer_name": customer_name,
                    "up_next_service": up_next_service,
                    "phone": actual_phone
                }
            else:
                # No up_next service - proceed with normal service selection
                return {
                    "success": True,
                    "customer_type": "returning",
                    "has_up_next": False,
                    "message": f"Welcome back, {customer_name}! What type of service would you like to book today?",
                    "customer_name": customer_name,
                    "phone": actual_phone
                }
        else:
            # NEW CUSTOMER FLOW
            logger.info(f"👤 New customer - proceeding with name collection")
            
            # Set customer type and update state machine
            self.booking_state_machine.set_customer_type("new")
            
            return {
                "success": True,
                "customer_type": "new",
                "message": "Thank you! I don't see you in our system yet, so I'll need to get some information from you. What's your first name?",
                "phone": actual_phone
            }

    async def handle_up_next_service_suggestion_function(self, response: str):
        """Handle customer response to up_next service suggestion"""
        logger.info(f"📋 Up-next service response: {response}")
        
        response_lower = response.lower().strip()
        
        # Check if customer accepts the suggested service
        accepts_suggestion = any(word in response_lower for word in [
            "yes", "yeah", "sure", "okay", "ok", "that's perfect", "sounds good", 
            "let's book that", "book that", "that's fine", "correct", "right"
        ])
        
        # Check if customer wants something different
        wants_different = any(word in response_lower for word in [
            "no", "different", "something else", "other", "another", "change",
            "actually", "instead", "prefer", "rather"
        ])
        
        if accepts_suggestion:
            # Customer accepts the up_next service suggestion
            up_next_service = self.booking_state_machine.collected_data.get("up_next_service", "")
            self.booking_state_machine.add_collected_data("service", up_next_service)
            self.booking_state_machine.add_collected_data("is_up_next_service", "true")
            
            logger.info(f"✅ Customer accepted up-next service: {up_next_service}")
            
            return {
                "success": True,
                "accepted_up_next": True,
                "message": f"Perfect! I'll book your {up_next_service} appointment. What date and time would you like?",
                "selected_service": up_next_service
            }
        
        elif wants_different or "different" in response_lower:
            # Customer wants a different service - proceed to normal service selection
            logger.info(f"🔄 Customer declined up-next service, wants different service")
            
            return {
                "success": True,
                "accepted_up_next": False,
                "message": "No problem! What type of service would you like to book instead?",
                "needs_service_selection": True
            }
        
        else:
            # Unclear response - ask for clarification
            up_next_service = self.booking_state_machine.collected_data.get("up_next_service", "")
            
            return {
                "success": True,
                "needs_clarification": True,
                "message": f"I want to make sure I understand - would you like to book your {up_next_service}, or would you prefer a different service today?",
                "up_next_service": up_next_service
            }