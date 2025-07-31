import openai
import os
from datetime import datetime, timedelta
import pytz
import logging
import json
import sys
from appointment_service import AppointmentService
from knowledge_base_service import KnowledgeBaseService
from booking_verification_service import BookingVerificationService
from typing import Optional, List, Dict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Add time formatting utility ---
def format_time_conversational(time_str):
    """Convert 24-hour HH:MM to 12-hour h:mm AM/PM (e.g., '2:00 PM')"""
    try:
        t = datetime.strptime(time_str, '%H:%M')
        if sys.platform == "win32":
            return t.strftime('%I:%M %p').lstrip('0')
        else:
            return t.strftime('%I:%M %p')
    except ValueError:
        return time_str


class SMSCancellationStateMachine:
    """State machine to track SMS cancellation progress and prevent premature function calls"""
    
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
        logger.info(f"📝 SMS Cancellation - Collected {field}: {value}")
        logger.info(f"📊 SMS Cancellation progress: {len(self.collected_data)}/{len(self.required_steps)} steps complete")
        logger.info(f"📋 SMS Cancellation data so far: {list(self.collected_data.keys())}")
        logger.info(f"⏭️ Next SMS cancellation step needed: {self.get_next_step()}")
    
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
        logger.info("🔄 SMS Cancellation state machine reset")
        logger.info(f"📋 Required SMS cancellation steps: {self.required_steps}")
    
    def set_found_appointments(self, appointments: list):
        """Store found appointments for selection"""
        self.found_appointments = appointments
        logger.info(f"📋 SMS Cancellation - Found {len(appointments)} appointments for selection")
    
    def get_found_appointments(self) -> list:
        """Get stored appointments"""
        return self.found_appointments


class SMSBookingStateMachine:
    """State machine to track SMS booking progress and customer type"""
    
    def __init__(self):
        self.state = "initial"
        self.collected_data = {}
        self.customer_type = None  # "new", "returning", "returning_with_up_next"
        
        # Dynamic step configuration based on customer type
        self.new_customer_steps = ["phone", "booking_details"]  # name, service, date, time, specialist in one step
        self.returning_customer_steps = ["phone", "booking_details"]  # service, date, time, specialist in one step
        self.returning_with_up_next_steps = ["phone", "up_next_response", "booking_details"]  # date, time, specialist after up_next decision
        
        self.required_steps = self.new_customer_steps  # Default
        self.step_order = self.new_customer_steps
    
    def set_customer_type(self, customer_type: str, has_up_next: bool = False):
        """Set customer type and update required steps"""
        self.customer_type = customer_type
        
        if customer_type == "new":
            self.required_steps = self.new_customer_steps
            self.step_order = self.new_customer_steps
        elif customer_type == "returning" and has_up_next:
            self.customer_type = "returning_with_up_next"
            self.required_steps = self.returning_with_up_next_steps
            self.step_order = self.returning_with_up_next_steps
        elif customer_type == "returning":
            self.required_steps = self.returning_customer_steps
            self.step_order = self.returning_customer_steps
            
        logger.info(f"📋 SMS Booking - Set customer type: {self.customer_type}")
        logger.info(f"📋 Required steps: {self.required_steps}")
    
    def can_call_function(self, function_name: str) -> bool:
        """Check if a function can be called based on current state"""
        if function_name == "collect_sms_booking_details":
            # Can collect booking details if phone is collected and (for up_next customers) up_next response is collected
            if self.customer_type == "returning_with_up_next":
                return "phone" in self.collected_data and "up_next_response" in self.collected_data
            else:
                return "phone" in self.collected_data
        return True
    
    def add_collected_data(self, field: str, value: str):
        """Add collected data and update state"""
        self.collected_data[field] = value
        logger.info(f"📝 SMS Booking - Collected {field}: {value}")
        logger.info(f"📊 SMS Booking progress: {len(self.collected_data)}/{len(self.required_steps)} steps complete")
        logger.info(f"📋 SMS Booking data so far: {list(self.collected_data.keys())}")
        logger.info(f"⏭️ Next SMS booking step needed: {self.get_next_step()}")
    
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
        self.required_steps = self.new_customer_steps
        self.step_order = self.new_customer_steps
        logger.info("🔄 SMS Booking state machine reset")
        logger.info(f"📋 Default required steps: {self.required_steps}")


class AIReceptionist:
    """Enhanced AI service for SMS with appointment booking and knowledge base capabilities"""
    
    def __init__(self, database_service=None):
        # Initialize OpenAI client
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Initialize appointment service with database
        self.appointment_service = AppointmentService(database_service=database_service)
        
        # NEW: Initialize knowledge base service
        self.knowledge_base_service = KnowledgeBaseService(database_service=database_service)
        
        # NEW: Initialize booking verification service
        self.booking_verification_service = BookingVerificationService(database_service=database_service)
        
        # Store database service reference
        self.db = database_service
        
        # Dynamically fetch services and specialists for function enums
        service_names = []
        specialist_names = []
        if self.db:
            try:
                service_names = [s['name'] for s in self.db.get_services()]
                specialist_names = self.db.get_active_staff_names()
            except Exception as e:
                logger.error(f"Error fetching services/specialists for AI function enum: {str(e)}")
        
        # Fallback message if no services
        self.no_services_fallback = "I'm sorry, I don't have access to our list of services at the moment. Please check back soon or contact us directly for more information."
        
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
        
        # Store conversation history for SMS
        self.conversations = {}
        
        # Track booking states
        self.booking_states = {}

        # Track cancellation states per user
        self.cancellation_states = {}

        # Track successful bookings to prevent duplicates
        self.last_successful_booking = {}
        

        
        # NEW: Track name frequencies for SMS conversations (phone_number -> {name: count})
        self.name_frequencies = {}
        
        # Settings for SMS responses
        self.sms_settings = {
            'temperature': 0.3,
            'max_tokens': 150  # Slightly longer for appointment booking
        }
        
        # Function definitions for OpenAI - UPDATED with dynamic service and specialist enums
        self.functions = [
            {
                "name": "book_appointment",
                "description": """Book an appointment for a customer at Radiance MD Med Spa.

            PHONE NUMBER COLLECTION:
            - For SMS: Ask "Is the phone number you're texting from the best number to reach you?"
            - For Voice: Ask "Is the phone number you're calling from the best number to reach you?"
            - If yes, use their current number (caller_id for voice, customer's texting number for SMS)
            - If no, collect their preferred number

            Always collect: customer name, phone confirmation, appointment date/time, service type.
            Try the customer's requested time first. Only suggest alternatives if unavailable.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Customer's full name"
                        },
                        "phone": {
                            "type": "string", 
                            "description": "Customer's phone number"
                        },
                        "date": {
                            "type": "string",
                            "description": "Appointment date in YYYY-MM-DD format"
                        },
                        "time": {
                            "type": "string",
                            "description": "Appointment time in HH:MM format (24-hour)"
                        },
                        "service": {
                            "type": "string",
                            "enum": service_names,
                            "description": "Type of service requested"
                        },
                        "specialist_preference": {
                            "type": "string",
                            "enum": specialist_names,
                            "description": "Preferred specialist (optional)"
                        }
                    },
                    "required": ["name", "phone", "date", "time", "service"]
                }
            },
            {
                "name": "check_availability",
                "description": "Check available appointment slots for a specific date and service",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date to check in YYYY-MM-DD format"
                        },
                        "service": {
                            "type": "string",
                            "enum": service_names,
                            "description": "Type of service to check availability for"
                        }
                    },
                    "required": ["date", "service"]
                }
            },
            {
                "name": "get_business_information",
                "description": """Get specific business information from knowledge base. ONLY use when customer asks about business details like hours, services, location, staff, policies, pricing, etc.

                DO NOT use for appointment booking - use book_appointment function instead.
                DO NOT use for general conversation - only for business information questions.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["hours", "services", "location", "staff", "policies", "pricing", "general"],
                            "description": "Type of business information needed"
                        },
                        "specific_question": {
                            "type": "string",
                            "description": "The customer's specific question"
                        }
                    },
                    "required": ["query_type", "specific_question"]
                }
            },
            {
                "name": "collect_cancellation_phone",
                "description": """Collect phone number to search for appointments to cancel. Use when customer wants to cancel an appointment and needs to provide their phone number. After collecting the phone, IMMEDIATELY call search_appointments_by_phone function - do NOT say phrases like 'let me search' or 'please hold on'.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {
                            "type": "string",
                            "description": "Phone number to search for appointments (customer can provide specific number or indicate they want to use their texting number)"
                        }
                    },
                    "required": ["phone"]
                }
            },
            {
                "name": "search_appointments_by_phone",
                "description": """Search for appointments by phone number for cancellation. Use IMMEDIATELY when customer provides their phone number for cancellation - do NOT use phrases like 'let me search', 'hold on', or 'one moment'. Just call this function directly.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {
                            "type": "string",
                            "description": "Phone number to search for appointments"
                        }
                    },
                    "required": ["phone"]
                }
            },
            {
                "name": "select_appointment_to_cancel",
                "description": """Select which appointment to cancel when multiple appointments are found. Use when customer specifies which appointment they want (1, 2, 3, etc.). This function does NOT cancel appointments - it only selects which one. Use confirm_cancellation to actually cancel.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "Position number (1, 2, 3), event ID, or description of the appointment to select"
                        }
                    },
                    "required": ["event_id"]
                }
            },
            {
                "name": "confirm_cancellation",
                "description": """FINAL STEP: Execute the actual appointment cancellation when customer says YES/confirms. This is the ONLY function that actually cancels appointments. Use when customer confirms with words like 'yes', 'confirm', 'cancel it', etc. after they've selected which appointment to cancel.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "Appointment number or ID (can be '1', '2', etc. - the function will find the real event ID)"
                        }
                    },
                    "required": ["event_id"]
                }
            },
            {
                "name": "collect_phone_for_booking",
                "description": """Collect phone number for booking and detect existing customers. Use when customer wants to book an appointment. This function will check if the customer exists in the database and determine the appropriate booking flow.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {
                            "type": "string",
                            "description": "Phone number for booking (customer can provide specific number or indicate they want to use their texting number)"
                        }
                    },
                    "required": ["phone"]
                }
            },
            {
                "name": "handle_sms_up_next_suggestion",
                "description": """Handle customer response to up_next service suggestion. Use when customer responds to the suggested service with acceptance, decline, or unclear response. This function processes whether they want the suggested service or something different.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "response": {
                            "type": "string",
                            "description": "Customer's response to the up_next service suggestion"
                        }
                    },
                    "required": ["response"]
                }
            },
            {
                "name": "collect_sms_booking_details",
                "description": """Collect booking details based on customer type. For NEW customers: collect name, service, date, time, and specialist preference all together. For EXISTING customers: collect service, date, time, and specialist preference together. For customers who accepted UP_NEXT: collect date, time, and specialist preference together.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Customer's full name (required for new customers only)"
                        },
                        "service": {
                            "type": "string",
                            "enum": service_names,
                            "description": "Type of service requested (not needed if up_next service was accepted)"
                        },
                        "date": {
                            "type": "string",
                            "description": "Preferred appointment date (YYYY-MM-DD format or natural language)"
                        },
                        "time": {
                            "type": "string",
                            "description": "Preferred appointment time"
                        },
                        "specialist": {
                            "type": "string",
                            "enum": specialist_names,
                            "description": "Specialist preference (optional)"
                        }
                    },
                    "required": ["date", "time"]
                }
            },

        ]
    
    def is_business_hours(self):
        """Check if current time is within business hours"""
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')
        
        # Check if we're closed on Sunday
        if current_day == 'Sunday':
            return False
            
        hours = self.business_hours.get(current_day)
        if not hours or not hours['start'] or not hours['end']:
            return False
            
        return hours['start'] <= current_time <= hours['end']
    
    def execute_function(self, function_name: str, arguments: dict, user_id: str = None):
        """Execute the requested function and return results"""
        try:
            logger.info(f"🔧 Executing function: {function_name} with arguments: {arguments}")
            
            if function_name == "book_appointment":
                return self.book_appointment_function(user_id=user_id, **arguments)
            elif function_name == "check_availability":
                return self.check_availability_function(**arguments)
            elif function_name == "get_business_information":
                return self.get_business_information_function(**arguments)
            elif function_name == "collect_cancellation_phone":
                return self.collect_cancellation_phone_function(user_id=user_id, **arguments)
            elif function_name == "search_appointments_by_phone":
                return self.search_appointments_by_phone_function(user_id=user_id, **arguments)
            elif function_name == "select_appointment_to_cancel":
                return self.select_appointment_to_cancel_function(user_id=user_id, **arguments)
            elif function_name == "confirm_cancellation":
                return self.confirm_cancellation_function(user_id=user_id, **arguments)
            elif function_name == "collect_phone_for_booking":
                return self.collect_phone_for_booking_function(user_id=user_id, **arguments)
            elif function_name == "handle_sms_up_next_suggestion":
                return self.handle_sms_up_next_suggestion_function(user_id=user_id, **arguments)
            elif function_name == "collect_sms_booking_details":
                return self.collect_sms_booking_details_function(user_id=user_id, **arguments)
            else:
                return {"error": f"Unknown function: {function_name}"}
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {str(e)}")
            return {"error": f"Function execution failed: {str(e)}"}
    
    def book_appointment_function(self, name: str, phone: str, date: str, time: str, 
                                service: str, specialist_preference: str = None, user_id: str = None):
        """Function to book an appointment (SMS and voice)"""
        logger.info(f"\U0001F4C5 Function call: Booking appointment for {name} - {service} on {date} at {time}")
        if not self.db or not [s['name'] for s in self.db.get_services()]:
            return {"success": False, "error": self.no_services_fallback, "available_slots": []}
        
        # For SMS: use sender's number only if phone is clearly invalid or not provided
        if user_id:
            phone_digits = ''.join(filter(str.isdigit, phone)) if phone else ''
            user_digits = ''.join(filter(str.isdigit, user_id))
            
            # Only fall back to sender's number if:
            # 1. No phone provided
            # 2. Phone is clearly not a number (like "yes" or "texting from")
            # 3. Phone has fewer than 10 digits (invalid)
            if (not phone or 
                phone.lower() == "yes" or 
                "texting from" in phone.lower() or
                len(phone_digits) < 10):
                logger.info(f"\U0001F4F1 Using SMS sender's number {user_id} instead of provided {phone}")
                phone = user_id
            else:
                # Trust the user's provided phone number - don't compare with sender's number
                logger.info(f"\U0001F4F1 Using customer-provided phone number: {phone}")

        # NEW: Log function call for verification
        if user_id:
            self.booking_verification_service.log_function_call(
                user_id=user_id,
                function_name="book_appointment",
                arguments={"name": name, "phone": phone, "date": date, "time": time, "service": service, "specialist_preference": specialist_preference},
                result={}  # Will be updated after booking
            )

        booking_key = (name, phone, date, time, service, specialist_preference)
        if user_id and self.last_successful_booking.get(user_id) == booking_key:
            return {
                "success": True,
                "message": "Your appointment is already booked and confirmed. If you need to make another booking, please start a new request.",
            }

        result = self.appointment_service.book_appointment(
            name=name,
            phone=phone,
            date=date,
            time=time,
            service=service,
            specialist_preference=specialist_preference
        )
        
        # NEW: Update function call result for verification
        if user_id:
            self.booking_verification_service.log_function_call(
                user_id=user_id,
                function_name="book_appointment",
                arguments={"name": name, "phone": phone, "date": date, "time": time, "service": service, "specialist_preference": specialist_preference},
                result=result
            )
        
        if result['success']:
            appointment = result['appointment']
            time_conv = format_time_conversational(appointment['time'])
            logger.info(f"[SMS OUT] Booking confirmation time (converted): {appointment['time']} -> {time_conv}")
            if user_id:
                self.last_successful_booking[user_id] = booking_key
            return {
                "success": True,
                "message": f"Appointment booked successfully! {appointment['service_name']} with {appointment['specialist']} on {appointment['date']} at {time_conv}. Confirmation SMS sent.",
                "appointment_id": appointment['id'],
                "specialist": appointment['specialist'],
                "price": appointment['price']
            }
        else:
            available_slots = result.get('available_slots', [])
            if available_slots:
                # Use the new check_availability with preferred_time
                closest_slots = self.appointment_service.check_availability(date, service, preferred_time=time)
                slots_text = ", ".join(closest_slots)
                logger.info(f"[SMS OUT] Closest available slots: {slots_text}")
                return {
                    "success": False,
                    "error": result['error'],
                    "available_slots": closest_slots,
                    "message": f"That time isn't available. Here are some options: {slots_text}. Which time works for you?"
                }
            else:
                return {
                    "success": False,
                    "error": result['error'],
                    "available_slots": available_slots
                }
    
    def check_availability_function(self, date: str, service: str):
        """Function to check availability for a date and service"""
        logger.info(f"\U0001F4C5 Function call: Checking availability for {service} on {date}")
        if not self.db or not [s['name'] for s in self.db.get_services()]:
            return {"date": date, "service": service, "available_slots": [], "total_slots": 0, "error": self.no_services_fallback}
        
        # For general availability requests, do not pass preferred_time
        available_slots = self.appointment_service.check_availability(date, service)
        
        if available_slots:
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
            
            logger.info(f"[SMS OUT] Available slots (scattered): {slots_text}")
            return {
                "date": date,
                "service": service,
                "available_slots": time_slots,  # Don't include the "more options" text in the slots list
                "total_slots": len(available_slots),
                "message": f"Available times: {slots_text}. Which works for you?"
            }
        else:
            return {
                "date": date,
                "service": service,
                "available_slots": [],
                "total_slots": 0,
                "error": "No available slots for this date/service."
            }
    
    def get_business_information_function(self, query_type: str, specific_question: str):
        """NEW: Function to get business information from knowledge base"""
        logger.info(f"📚 Function call: Getting business info - type: {query_type}, question: {specific_question}")
        
        # Search knowledge base
        information = self.knowledge_base_service.search_knowledge_base(specific_question, query_type)
        
        return {
            "query_type": query_type,
            "question": specific_question,
            "information": information
        }
    
    def is_booking_in_progress(self, user_id):
        """Check if a booking is in progress for this user"""
        return self.booking_states.get(user_id, False)
    
    def set_booking_state(self, user_id, state):
        """Set the booking state for a user"""
        self.booking_states[user_id] = state
    

    
    def _update_conversation_name(self, phone_number: str, extracted_name: str):
        """Update conversation name based on frequency analysis (SMS only)"""
        if not extracted_name or extracted_name.lower() == "none":
            return
        
        # Initialize frequency tracking for this phone number
        if phone_number not in self.name_frequencies:
            self.name_frequencies[phone_number] = {}
        
        # Count this name
        name_lower = extracted_name.lower()
        self.name_frequencies[phone_number][name_lower] = self.name_frequencies[phone_number].get(name_lower, 0) + 1
        
        # Get current conversation name from database
        current_name = self._get_current_conversation_name(phone_number)
        current_name_lower = current_name.lower() if current_name else None
        
        # Find the most frequent name
        most_frequent_name, most_frequent_count = max(self.name_frequencies[phone_number].items(), key=lambda x: x[1])
        
        # Update conversation name if:
        # 1. No current name (first time finding a name)
        # 2. Different name has surpassed current name's count
        should_update = False
        
        if not current_name:
            # First name found - use it immediately
            should_update = True
            logger.info(f"📝 Setting initial conversation name for {phone_number}: {most_frequent_name.capitalize()}")
        elif most_frequent_name != current_name_lower:
            # Check if new name has surpassed current name
            current_count = self.name_frequencies[phone_number].get(current_name_lower, 0)
            if most_frequent_count > current_count:
                should_update = True
                logger.info(f"📝 Updating conversation name for {phone_number}: {current_name} -> {most_frequent_name.capitalize()} (count: {current_count} -> {most_frequent_count})")
        
        if should_update:
            self._set_conversation_name(phone_number, most_frequent_name.capitalize())
    
    def _get_current_conversation_name(self, phone_number: str) -> str:
        """Get the current conversation name from database"""
        if self.db:
            conversation = self.db.get_conversation_by_id(phone_number)
            return conversation.get('customer_name') if conversation else None
        return None
    
    def _set_conversation_name(self, phone_number: str, name: str):
        """Update the conversation name in the database"""
        if self.db:
            success = self.db.update_conversation_customer_name(phone_number, name)
            if success:
                logger.info(f"✅ Database updated with conversation name: {phone_number} -> {name}")
            else:
                logger.error(f"❌ Failed to update database with conversation name: {phone_number} -> {name}")
    
    def cleanup_name_frequencies(self, phone_numbers_to_remove: list):
        """Clean up name frequencies for deleted conversations"""
        for phone_number in phone_numbers_to_remove:
            if phone_number in self.name_frequencies:
                del self.name_frequencies[phone_number]
                logger.info(f"🧹 Cleaned up name frequencies for {phone_number}")
    
    def get_ai_response(self, user_id, message):
        """Get response from AI for SMS interactions with function calling support"""
        # Get conversation history or initialize new one
        history = self.conversations.get(user_id, [])
        
        # Clean history to remove tool-related messages that could cause conflicts
        cleaned_history = []
        for msg in history:
            # Only keep user and assistant messages with content
            if msg.get("role") in ["user", "assistant"] and msg.get("content") is not None:
                cleaned_history.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Extract customer name if not already known
        customer_name = None
        # Note: Name extraction now happens during summary generation, not here
        
        # NEW: Check if we should trigger knowledge base function using hybrid approach
        should_trigger_kb, query_type = self.knowledge_base_service.should_trigger_knowledge_function(message)
        
        if should_trigger_kb:
            logger.info(f"🎯 Knowledge base trigger detected for message: '{message}' (type: {query_type})")
        
        # Add user message to history
        cleaned_history.append({"role": "user", "content": message})
        
        try:
            # System prompt with appointment booking capabilities - UPDATED: Enhanced knowledge base guidance
            system_prompt = f"""You are a professional AI receptionist for Radiance MD Med Spa.

            CRITICAL RULES:
            - When customers ask about business information (hours, services, location, staff, pricing, policies), IMMEDIATELY use the get_business_information function.
            - For appointment booking, follow the ENHANCED SMS FLOW instructions below
            - Keep ALL responses under 160 characters to avoid multi-part SMS messages
            - Today's date is {datetime.now().strftime('%Y-%m-%d')}
            - When customers say "tomorrow", use {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
            - When they say a day name, calculate the correct 2025 date

            KNOWLEDGE BASE USAGE:
            - When you get information from the knowledge base, use it directly in your response
            - DO NOT add generic phrases like "Call us for more information" when you successfully answer questions
            - Only suggest calling if you genuinely cannot answer the question or for complex booking requests
            - When you have the information, just provide it directly without additional suggestions

            STAFF INFORMATION:
            - For staff questions, the system will automatically check staff management settings first
            - If staff is configured in settings, that information takes priority over knowledge base
            - If no staff is configured, the system will fall back to knowledge base content
            - Always use the most current staff information available

            APPOINTMENT BOOKING - ENHANCED SMS FLOW:
            1. When customer wants to book: Ask "What phone number would you like to book with?" THEN call collect_phone_for_booking function
            2A. RETURNING CUSTOMER with UP-NEXT service: System will automatically welcome them back and suggest their up-next service (e.g., "Welcome back, Sarah! I see you're due for your Second Botox. Would you like to book that, or another service?") THEN call handle_sms_up_next_suggestion function with their response
            2B. RETURNING CUSTOMER without up-next: System will ask for all booking details together: "Can you please provide the service you want to book, your preferred date and time, and if you have a specific preference for a specialist?" THEN call collect_sms_booking_details function
            2C. NEW CUSTOMER: Ask for all details together: "Please provide your name, the service you would like to book, your preferred date and time, and if you have a preference for a specific specialist." THEN call collect_sms_booking_details function
            
            CRITICAL SMS BOOKING RULES:
            - ALWAYS start with collect_phone_for_booking function when customer wants to book
            - The phone function will automatically determine customer type and provide appropriate next steps
            - For UP-NEXT suggestions: ALWAYS call handle_sms_up_next_suggestion function when customer responds to up-next suggestion
            - When customer provides booking details (date/time/service): IMMEDIATELY call collect_sms_booking_details function with the EXACT details they provided
            - NEVER use the old book_appointment function for SMS bookings - only use the new SMS booking functions (collect_phone_for_booking, handle_sms_up_next_suggestion, collect_sms_booking_details)
            - NEVER say "wait for confirmation", "processing", "let me book", or "one moment" - book immediately when details are provided
            - Group questions together to minimize SMS back-and-forth

            RESPONSE GUIDELINES:
            - Be professional, friendly, and helpful
            - Keep responses concise and under 160 characters
            - Use the information provided by function calls directly
            - Don't make up information - only use what's provided by the functions"""
            
            # Get AI response with function calling using the new tools format
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Updated to use gpt-4o-mini instead of gpt-3.5-turbo
                messages=[
                    {"role": "system", "content": system_prompt},
                    *cleaned_history
                ],
                tools=[{"type": "function", "function": func} for func in self.functions],
                tool_choice="auto",
                temperature=self.sms_settings['temperature'],
                max_tokens=self.sms_settings['max_tokens']
            )
            
            message = response.choices[0].message
            
            # Check if AI wants to call a function
            if message.tool_calls:
                logger.info(f"🔧 AI chose to call functions: {len(message.tool_calls)} function(s)")
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    
                    try:
                        # Parse function arguments more safely
                        function_args = json.loads(tool_call.function.arguments)
                        logger.info(f"🔧 AI calling function: {function_name} with args: {function_args}")
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON parsing error for function arguments: {e}")
                        logger.error(f"❌ Raw arguments: {tool_call.function.arguments}")
                        return "I'm having trouble processing your request. Please try again or call us."
            else:
                logger.info(f"💬 AI chose conversational response (no function calls) for message: '{message.content[:100]}...'")
            
            # Check if AI wants to call a function
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    
                    try:
                        # Parse function arguments more safely
                        function_args = json.loads(tool_call.function.arguments)
                        logger.info(f"🔧 AI calling function: {function_name} with args: {function_args}")
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON parsing error for function arguments: {e}")
                        logger.error(f"❌ Raw arguments: {tool_call.function.arguments}")
                        return "I'm having trouble processing your request. Please try again or call us."
                    
                    # Check if we're already booking
                    if function_name == "book_appointment" and self.is_booking_in_progress(user_id):
                        return "I'm already processing your appointment booking. Please wait for confirmation."
                    

                    
                    # Set booking state if starting a booking
                    if function_name == "book_appointment":
                        self.set_booking_state(user_id, True)
                    
                    # Execute the function
                    function_result = self.execute_function(function_name, function_args, user_id=user_id)
                    
                    # Clear booking state if booking completed or failed
                    if function_name == "book_appointment":
                        self.set_booking_state(user_id, False)
                    
                    # Create a fresh conversation context for the follow-up response
                    follow_up_messages = [
                        {"role": "system", "content": system_prompt},
                        *cleaned_history,
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": message.tool_calls
                        },
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(function_result)
                        }
                    ]
                    
                    # Get AI's response based on function result
                    follow_up_response = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=follow_up_messages,
                        temperature=self.sms_settings['temperature'],
                        max_tokens=self.sms_settings['max_tokens']
                    )
                    
                    ai_message = follow_up_response.choices[0].message.content
                    break  # Handle first tool call only for SMS
            else:
                # Regular response without function call
                ai_message = message.content
            
            # NEW: Log AI response for verification
            if user_id:
                self.booking_verification_service.log_ai_response(user_id, ai_message)
                
                # Check for false booking confirmation
                is_false_confirmation, alert_message = self.booking_verification_service.check_for_false_booking_confirmation(user_id, ai_message)
                
                if is_false_confirmation:
                    logger.error(f"🚨 FALSE BOOKING CONFIRMATION DETECTED for {user_id}")
                    logger.error(f"🚨 Response: {ai_message}")
                    
                    # Send alert
                    self.booking_verification_service.send_false_booking_alert(user_id, ai_message, alert_message)
                    
                    # Replace the response with a clarification message
                    ai_message = "I apologize for the confusion. Let me check your appointment status and get back to you shortly."
            
            # Add AI response to history (only the final response, not the function call)
            cleaned_history.append({"role": "assistant", "content": ai_message})
            
            # Update conversation history (keep last 10 messages for SMS)
            self.conversations[user_id] = cleaned_history[-10:]
            
            return ai_message, customer_name  # Return both response and extracted name
            
        except Exception as e:
            logger.error(f"Error getting AI response for SMS: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return "I apologize, but I'm having trouble processing your request. Please try calling us instead.", None

    # ===============================
    # CANCELLATION STATE MANAGEMENT
    # ===============================
    
    def get_cancellation_state_machine(self, user_id: str) -> SMSCancellationStateMachine:
        """Get or create cancellation state machine for user"""
        if user_id not in self.cancellation_states:
            self.cancellation_states[user_id] = SMSCancellationStateMachine()
        return self.cancellation_states[user_id]
    
    def reset_cancellation_state(self, user_id: str):
        """Reset cancellation state for user"""
        if user_id in self.cancellation_states:
            self.cancellation_states[user_id].reset()

    # ===============================
    # SMS BOOKING STATE MANAGEMENT
    # ===============================
    
    def get_booking_state_machine(self, user_id: str) -> SMSBookingStateMachine:
        """Get or create booking state machine for user"""
        if user_id not in self.booking_states:
            self.booking_states[user_id] = SMSBookingStateMachine()
        return self.booking_states[user_id]
    
    def reset_booking_state(self, user_id: str):
        """Reset booking state for user"""
        if user_id in self.booking_states:
            self.booking_states[user_id].reset()

    # ===============================
    # CANCELLATION FUNCTION HANDLERS
    # ===============================
    
    def collect_cancellation_phone_function(self, phone: str, user_id: str = None):
        """Handle phone collection for SMS cancellation"""
        logger.info(f"📞 SMS Cancellation - Collected phone: {phone}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to process cancellation request. Please try again.",
                "error": "No user ID available"
            }
        
        # Get state machine for this user
        state_machine = self.get_cancellation_state_machine(user_id)
        
        # Handle sender ID logic - if user indicates they want to use their texting number
        if (phone.lower() in ["same", "yes", "y", "yeah", "sure", "this number", "texting from"] or
            "texting from" in phone.lower() or
            "this number" in phone.lower()):
            logger.info(f"📞 SMS Cancellation - Using sender's number {user_id} instead of '{phone}'")
            phone = user_id
        
        # Format phone number for consistent database searching
        formatted_phone = self.appointment_service._format_phone_for_search(phone)
        
        state_machine.add_collected_data("phone", formatted_phone)
        
        return {
            "success": True,
            "message": "Let me search for your appointments.",
            "collected_phone": formatted_phone
        }
    
    def search_appointments_by_phone_function(self, phone: str, user_id: str = None):
        """Handle appointment search for SMS cancellation"""
        logger.info(f"🔍 SMS Cancellation - Searching appointments for phone: {phone}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to search for appointments. Please try again.",
                "error": "No user ID available"
            }
        
        # Check if database service is available
        if not self.db:
            logger.error("❌ SMS Cancellation - Database service not available")
            return {
                "success": False,
                "message": "I'm sorry, I couldn't search for appointments right now. Please try again or contact us during business hours.",
                "error": "Database service not available"
            }
        
        # Get state machine for this user
        state_machine = self.get_cancellation_state_machine(user_id)
        
        # Use the appointment service to search
        search_result = self.appointment_service.search_appointments_by_phone(phone)
        logger.info(f"🔍 SMS Cancellation - Search result: {search_result}")
        
        if not search_result['success']:
            return {
                "success": False,
                "message": "I'm sorry, I couldn't search for appointments right now. Please try again or contact us during business hours.",
                "error": search_result.get('error', 'Unknown error')
            }
        
        appointments = search_result['appointments']
        formatted_list = search_result['formatted_list']
        
        logger.info(f"🔍 SMS Cancellation - Found {len(appointments)} appointments")
        for i, appt in enumerate(appointments):
            logger.info(f"🔍 SMS Cancellation - Appointment {i+1}: {appt.get('service_name', 'Unknown')} on {appt.get('appointment_date')} at {appt.get('appointment_time')} with {appt.get('specialist', 'team')} (ID: {appt.get('calendar_event_id')})")
        
        # Store appointments in state machine for selection
        state_machine.set_found_appointments(appointments)
        
        if len(appointments) == 0:
            return {
                "success": True,
                "message": formatted_list,
                "appointments_found": 0
            }
        elif len(appointments) == 1:
            # Auto-select single appointment
            appointment = appointments[0]
            state_machine.add_collected_data("appointment_selection", appointment['calendar_event_id'])
            
            # Format appointment details for confirmation
            date_str = datetime.strptime(appointment['appointment_date'], '%Y-%m-%d').strftime('%A, %B %d, %Y')
            time_str = datetime.strptime(appointment['appointment_time'], '%H:%M').strftime('%I:%M %p')
            
            confirmation_message = (f"I found your {appointment['service_name']} appointment on {date_str} at {time_str} "
                                   f"with {appointment['specialist'] or 'our team'}. "
                                   f"Are you sure you want to cancel this appointment?")
            
            return {
                "success": True,
                "message": confirmation_message,
                "appointments_found": 1,
                "auto_selected": True,
                "event_id": appointment['calendar_event_id']
            }
        else:
            # Multiple appointments - format for SMS display
            appointment_list = []
            for i, appt in enumerate(appointments, 1):
                date_str = datetime.strptime(appt['appointment_date'], '%Y-%m-%d').strftime('%B %d')
                time_str = datetime.strptime(appt['appointment_time'], '%H:%M').strftime('%I:%M %p')
                appointment_list.append(f"{i}. {appt['service_name']} on {date_str} at {time_str} with {appt['specialist'] or 'team'}")
            
            appointments_text = f"I found {len(appointments)} appointments:\n\n" + "\n".join(appointment_list) + "\n\nPlease reply with the number of the appointment you'd like to cancel."
            
            return {
                "success": True,
                "message": appointments_text,
                "appointments_found": len(appointments),
                "auto_selected": False
            }
    
    def select_appointment_to_cancel_function(self, event_id: str, user_id: str = None):
        """Handle appointment selection for SMS cancellation"""
        logger.info(f"🎯 SMS Cancellation - Selected appointment: {event_id}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to process selection. Please try again.",
                "error": "No user ID available"
            }
        
        # Get state machine for this user
        state_machine = self.get_cancellation_state_machine(user_id)
        
        # Validate that this appointment exists in our found appointments
        found_appointments = state_machine.get_found_appointments()
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
                    logger.info(f"🎯 SMS Cancellation - Selected appointment by position {event_id}: {selected_appointment['calendar_event_id']}")
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
                    logger.info(f"🎯 SMS Cancellation - Selected appointment by description match: {appt['calendar_event_id']}")
                    break
        
        if not selected_appointment:
            # Log the available appointments for debugging
            available_appts = []
            for i, appt in enumerate(found_appointments, 1):
                available_appts.append(f"{i}. {appt.get('service_name', 'Unknown')} with {appt.get('specialist', 'team')}")
            
            logger.error(f"🎯 SMS Cancellation - Could not find appointment with event_id '{event_id}'. Available: {available_appts}")
            
            return {
                "success": False,
                "message": f"I'm sorry, I couldn't find that appointment. Please reply with the number (1, 2, 3, etc.) of the appointment you'd like to cancel.",
                "error": "Appointment not found in search results",
                "available_appointments": available_appts
            }
        
        # Use the actual event_id from the selected appointment
        actual_event_id = selected_appointment['calendar_event_id']
        state_machine.add_collected_data("appointment_selection", actual_event_id)
        
        # Format appointment details for confirmation
        date_str = datetime.strptime(selected_appointment['appointment_date'], '%Y-%m-%d').strftime('%A, %B %d, %Y')
        time_str = datetime.strptime(selected_appointment['appointment_time'], '%H:%M').strftime('%I:%M %p')
        
        confirmation_message = (f"I found your {selected_appointment['service_name']} appointment on {date_str} at {time_str} "
                               f"with {selected_appointment['specialist'] or 'our team'}. "
                               f"Are you sure you want to cancel this appointment?")
        
        return {
            "success": True,
            "message": confirmation_message,
            "selected_appointment": selected_appointment,
            "event_id": actual_event_id
        }
    
    def confirm_cancellation_function(self, event_id: str, user_id: str = None):
        """Handle final SMS cancellation confirmation"""
        logger.info(f"🗑️ SMS Cancellation - Confirming cancellation for user selection: {event_id}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to process cancellation. Please try again.",
                "error": "No user ID available"
            }
        
        # Get state machine for this user
        state_machine = self.get_cancellation_state_machine(user_id)
        
        # Get the actual Google Calendar event_id from state machine 
        # (select_appointment_to_cancel_function already stored the real event ID)
        actual_event_id = state_machine.collected_data.get("appointment_selection")
        if not actual_event_id:
            return {
                "success": False,
                "message": "No appointment selected for cancellation. Please start over.",
                "error": "No appointment_selection in state machine"
            }
        
        logger.info(f"🗑️ SMS Cancellation - Using actual Google Calendar event_id: {actual_event_id}")
        
        # Use the appointment service for validated cancellation
        cancellation_result = self.appointment_service.cancel_appointment_with_validation(actual_event_id)
        
        if not cancellation_result['success']:
            error_message = cancellation_result.get('message', cancellation_result.get('error', 'Unknown error'))
            return {
                "success": False,
                "message": error_message,
                "error": cancellation_result.get('error')
            }
        
        # Mark cancellation as complete in state machine
        state_machine.add_collected_data("confirmation", "confirmed")
        
        # Format success message for SMS
        appointment = cancellation_result['appointment_details']
        date_str = datetime.strptime(appointment['appointment_date'], '%Y-%m-%d').strftime('%A, %B %d')
        time_str = datetime.strptime(appointment['appointment_time'], '%H:%M').strftime('%I:%M %p')
        
        success_message = (f"Your {appointment['service_name']} appointment on {date_str} at {time_str} "
                          f"has been cancelled successfully.")
        
        # Add refund information if applicable
        if cancellation_result.get('refund_result'):
            success_message += " If you had a deposit, it will be refunded to your payment method."
        
        success_message += " Thank you for letting us know. Please text us if you'd like to reschedule."
        
        # Reset state machine after successful cancellation
        self.reset_cancellation_state(user_id)
        
        return {
            "success": True,
            "message": success_message,
            "cancellation_result": cancellation_result
        }

    # ===============================
    # SMS BOOKING FUNCTION HANDLERS
    # ===============================
    
    def collect_phone_for_booking_function(self, phone: str, user_id: str = None):
        """Handle phone collection for SMS booking with customer detection"""
        logger.info(f"📞 SMS Booking - Phone collection: {phone}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to process booking request. Please try again.",
                "error": "No user ID available"
            }
        
        # Get booking state machine
        booking_state = self.get_booking_state_machine(user_id)
        
        # Handle SMS phone number logic - similar to voice but simpler
        actual_phone = phone
        
        # Check if customer explicitly says "yes" or mentions "texting from"
        phone_lower = phone.lower().strip()
        if phone_lower in ["yes", "y", "yeah", "sure", "okay", "ok"] or "texting from" in phone_lower:
            logger.info(f"📞 SMS - Customer confirmed using texting number: {user_id}")
            actual_phone = user_id
        else:
            # Check if provided phone number is valid format  
            provided_digits = ''.join(filter(str.isdigit, phone))
            
            # Valid phone number formats: 10 digits (US number) or 11 digits (with country code)
            if len(provided_digits) == 10 or len(provided_digits) == 11:
                # Trust the user's provided number
                logger.info(f"📞 SMS - Using user-provided phone number: {phone}")
                actual_phone = phone
            elif len(provided_digits) == 0:
                # No digits provided - fall back to texting number
                logger.info(f"📞 SMS - No phone number provided - using texting number {user_id}")
                actual_phone = user_id
            else:
                # Invalid format - fall back to texting number
                logger.info(f"📞 SMS - Invalid phone number format ({len(provided_digits)} digits) - using texting number {user_id}")
                actual_phone = user_id
        
        # Store the phone number
        booking_state.add_collected_data("phone", actual_phone)
        
        # Perform database lookup for existing customer
        customer_data = None
        if self.db:
            try:
                # Format phone for database search using the same logic as appointment service
                formatted_phone = self.appointment_service._format_phone_for_search(actual_phone)
                customer_data = self.db.get_customer(formatted_phone)
                logger.info(f"🔍 SMS - Customer lookup for {formatted_phone}: {'Found' if customer_data else 'Not found'}")
            except Exception as e:
                logger.error(f"❌ SMS - Error looking up customer: {str(e)}")
        
        if customer_data and customer_data.get('name'):
            # RETURNING CUSTOMER FLOW
            customer_name = customer_data['name']
            up_next_service = customer_data.get('up_next_from_you', '').strip() if customer_data.get('up_next_from_you') else None
            logger.info(f"🎉 SMS - Returning customer found: {customer_name}")
            logger.info(f"🔍 SMS - Up next service: {up_next_service if up_next_service else 'None'}")
            
            # Set customer type and update state machine
            booking_state.set_customer_type("returning", has_up_next=bool(up_next_service))
            booking_state.add_collected_data("customer_name", customer_name)
            
            # Check if there's an up_next service to suggest
            if up_next_service and len(up_next_service) > 0:
                # Store up_next service for suggestion
                booking_state.add_collected_data("up_next_service", up_next_service)
                
                return {
                    "success": True,
                    "customer_type": "returning_with_up_next",
                    "message": f"Welcome back, {customer_name}! I see you're due for {up_next_service}. Would you like to book that, or would you like another service?",
                    "customer_name": customer_name,
                    "up_next_service": up_next_service,
                    "phone": actual_phone
                }
            else:
                # No up_next service - ask for all booking details at once
                return {
                    "success": True,
                    "customer_type": "returning",
                    "message": f"Welcome back, {customer_name}! Can you please provide the service you want to book, your preferred date and time, and if you have a specific preference for a specialist?",
                    "customer_name": customer_name,
                    "phone": actual_phone
                }
        else:
            # NEW CUSTOMER FLOW
            logger.info(f"👤 SMS - New customer (not in database): {formatted_phone if 'formatted_phone' in locals() else actual_phone}")
            
            # Set customer type
            booking_state.set_customer_type("new")
            
            return {
                "success": True,
                "customer_type": "new",
                "message": "Please provide your name, the service you would like to book, your preferred date and time, and if you have a preference for a specific specialist.",
                "phone": actual_phone
            }
    
    def handle_sms_up_next_suggestion_function(self, response: str, user_id: str = None):
        """Handle customer response to up_next service suggestion for SMS"""
        logger.info(f"📋 SMS - Up-next service response: {response}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to process your response. Please try again.",
                "error": "No user ID available"
            }
        
        # Get booking state machine
        booking_state = self.get_booking_state_machine(user_id)
        
        response_lower = response.lower().strip()
        
        # Check if customer accepts the suggested service
        accepts_suggestion = any(word in response_lower for word in [
            "yes", "yeah", "sure", "okay", "ok", "that's perfect", "sounds good", 
            "book that", "that's fine", "correct", "right", "that one"
        ])
        
        # Check if customer wants something different
        wants_different = any(word in response_lower for word in [
            "no", "different", "something else", "other", "another", "change",
            "actually", "instead", "prefer", "rather"
        ])
        
        if accepts_suggestion:
            # Customer accepts the up_next service suggestion
            up_next_service = booking_state.collected_data.get("up_next_service", "")
            booking_state.add_collected_data("service", up_next_service)
            booking_state.add_collected_data("up_next_response", "accepted")
            
            logger.info(f"✅ SMS - Customer accepted up-next service: {up_next_service}")
            
            return {
                "success": True,
                "accepted_up_next": True,
                "message": f"Perfect! I'll book your {up_next_service} appointment. What date and time would you like, and do you have a preference for which specialist?",
                "selected_service": up_next_service
            }
        
        elif wants_different:
            # Customer wants a different service
            booking_state.add_collected_data("up_next_response", "declined")
            logger.info(f"🔄 SMS - Customer declined up-next service, wants different service")
            
            return {
                "success": True,
                "accepted_up_next": False,
                "message": "No problem! Can you please provide the service you want to book, your preferred date and time, and if you have a preference for a specific specialist?",
                "needs_service_selection": True
            }
        
        else:
            # Unclear response - ask for clarification
            up_next_service = booking_state.collected_data.get("up_next_service", "")
            
            return {
                "success": True,
                "needs_clarification": True,
                "message": f"I want to make sure I understand - would you like to book {up_next_service}, or would you prefer a different service today?",
                "up_next_service": up_next_service
            }
    
    def collect_sms_booking_details_function(self, date: str, time: str, name: str = None, 
                                           service: str = None, specialist: str = None, user_id: str = None):
        """Collect booking details based on customer type for SMS"""
        logger.info(f"📝 SMS Booking - Collecting details: name={name}, service={service}, date={date}, time={time}, specialist={specialist}")
        
        if not user_id:
            return {
                "success": False,
                "message": "Unable to process booking details. Please try again.",
                "error": "No user ID available"
            }
        
        # Get booking state machine
        booking_state = self.get_booking_state_machine(user_id)
        
        # Get customer type and existing data
        customer_type = booking_state.customer_type
        existing_data = booking_state.collected_data
        
        # Validate required fields based on customer type
        if customer_type == "new" and not name:
            return {
                "success": False,
                "message": "Please provide your name along with the service, date, and time for your appointment.",
                "error": "Name required for new customer"
            }
        
        # For returning customers with up_next who accepted, service should already be set
        if customer_type == "returning_with_up_next" and existing_data.get("up_next_response") == "accepted":
            service = existing_data.get("service")  # Use the up_next service
        elif not service:
            return {
                "success": False,
                "message": "Please provide the service you'd like to book along with your preferred date and time.",
                "error": "Service required"
            }
        
        # Store collected data
        booking_state.add_collected_data("booking_details", "collected")
        if name:
            booking_state.add_collected_data("customer_name", name)
        if service:
            booking_state.add_collected_data("service", service)
        booking_state.add_collected_data("date", date)
        booking_state.add_collected_data("time", time)
        if specialist:
            booking_state.add_collected_data("specialist", specialist)
        
        # Prepare booking data
        booking_data = {
            "name": existing_data.get("customer_name") or name,
            "phone": existing_data.get("phone"),
            "service": service,
            "date": date,
            "time": time,
            "specialist_preference": specialist
        }
        
        # Determine if this is an up_next service booking
        is_up_next_service = (customer_type == "returning_with_up_next" and 
                            existing_data.get("up_next_response") == "accepted")
        
        # Attempt to book the appointment using appropriate booking method
        try:
            if is_up_next_service:
                # Use custom booking for up_next services (bypasses service validation)
                logger.info(f"📋 SMS - Booking up-next custom service: {booking_data['service']}")
                result = self.appointment_service.book_custom_appointment(
                    name=booking_data["name"],
                    phone=booking_data["phone"],
                    date=booking_data["date"],
                    time=booking_data["time"],
                    service=booking_data["service"],
                    specialist_preference=booking_data["specialist_preference"],
                    price=0.0,  # Default to $0 for up_next services
                    duration=60  # Default to 60 minutes for up_next services
                )
            else:
                # Use regular booking for standard services
                result = self.appointment_service.book_appointment(
                    name=booking_data["name"],
                    phone=booking_data["phone"],
                    date=booking_data["date"],
                    time=booking_data["time"],
                    service=booking_data["service"],
                    specialist_preference=booking_data["specialist_preference"]
                )
            
            if result['success']:
                appointment = result['appointment']
                time_conv = format_time_conversational(appointment['time'])
                
                # Reset booking state after successful booking
                self.reset_booking_state(user_id)
                
                return {
                    "success": True,
                    "message": f"Appointment booked successfully! {appointment['service_name']} with {appointment['specialist']} on {appointment['date']} at {time_conv}. Confirmation SMS sent.",
                    "appointment_id": appointment['id'],
                    "specialist": appointment['specialist'],
                    "price": appointment['price']
                }
            else:
                # Booking failed - provide alternatives
                available_slots = result.get('available_slots', [])
                if available_slots:
                    # For up_next services, suggest using a generic service for availability
                    # since up_next service names might not match database services exactly
                    service_for_availability = service if not is_up_next_service else "Consultation"
                    
                    # Use the appointment service's availability check with preferred time
                    closest_slots = self.appointment_service.check_availability(date, service_for_availability, preferred_time=time)
                    slots_text = ", ".join(closest_slots)
                    
                    return {
                        "success": False,
                        "error": result['error'],
                        "available_slots": closest_slots,
                        "message": f"That time isn't available. Here are some options for {date}: {slots_text}. Which time works for you?"
                    }
                else:
                    return {
                        "success": False,
                        "error": result['error'],
                        "message": f"Sorry, no appointments are available for {service} on {date}. Please try a different date."
                    }
                    
        except Exception as e:
            logger.error(f"❌ SMS Booking - Error during appointment booking: {str(e)}")
            return {
                "success": False,
                "message": "Sorry, there was an error processing your booking. Please try again.",
                "error": str(e)
            }


