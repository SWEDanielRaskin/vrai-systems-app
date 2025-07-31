# Updated appointment_service.py with payment integration and database logging
import json
import os
import logging
from message_scheduler import MessageScheduler
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google_calendar_service import GoogleCalendarService
from sms_service import SMSService
from payment_service import PaymentService  # New import

logger = logging.getLogger(__name__)

def format_phone_to_e164(phone: str) -> str:
    """
    Convert any phone number format to E.164 format (+1XXXXXXXXXX)
    
    Args:
        phone: Phone number in any format (e.g., "3132044895", "313-204-4895", "+13132044895")
        
    Returns:
        Phone number in E.164 format (+1XXXXXXXXXX)
    """
    if not phone:
        return phone
    
    # Remove all non-digit characters
    digits = ''.join(filter(str.isdigit, phone))
    
    # Handle different input formats
    if len(digits) == 10:
        # US number without country code: 3132044895 -> +13132044895
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        # US number with country code: 13132044895 -> +13132044895
        return f"+{digits}"
    elif phone.startswith('+1') and len(digits) == 11:
        # Already in correct format
        return phone
    elif phone.startswith('+') and len(digits) == 11:
        # Already in correct format with different country code
        return phone
    else:
        # Default: assume US number and add +1, take last 10 digits
        if len(digits) >= 10:
            return f"+1{digits[-10:]}"
        else:
            # Return as-is if we can't format it properly
            return phone

class AppointmentService:
    """Service for managing appointments with specialist assignment, booking, and payments"""
    
    def __init__(self, database_service=None):
        """Initialize appointment service with database connection"""
        self.db = database_service
        self.calendar_service = GoogleCalendarService()
        self.sms_service = SMSService()
        self.payment_service = PaymentService()
        self.message_scheduler = MessageScheduler()
        
        # NEW: Dynamic specialists from staff management (replaces hardcoded list)
        self.specialists = []
        self.specialist_counter = 0
        
        # File to store appointments locally (for backup/tracking)
        self.appointments_file = 'appointments.json'
        
        # Load existing specialist counter
        self.load_specialist_counter()
        
        # NEW: Initialize specialists from database
        self._update_specialists_from_database()
    
    def _update_specialists_from_database(self):
        """Update specialists list from database staff management"""
        if self.db:
            staff_names = self.db.get_active_staff_names()
            if staff_names:
                self.specialists = staff_names
                logger.info(f"👥 Updated specialists from database: {self.specialists}")
            else:
                # No staff configured - use empty list (will book without specific specialist)
                self.specialists = []
                logger.info("👥 No staff configured in database - appointments will be booked without specific specialist")
        else:
            # Fallback to empty list if no database connection
            self.specialists = []
            logger.warning("⚠️ No database connection - using empty specialists list")
    
    def format_time_conversational(self, time_str):
        """Convert 24-hour HH:MM to 12-hour h:mm AM/PM (e.g., '2:00 PM')"""
        try:
            t = datetime.strptime(time_str, '%H:%M')
            if sys.platform == "win32":
                formatted = t.strftime('%I:%M %p').lstrip('0')
            else:
                formatted = t.strftime('%-I:%M %p')
            return formatted
        except Exception:
            return time_str
    
    def _format_date_conversational(self, date_str: str) -> str:
        """Convert date to conversational format with ordinal suffixes"""
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day = date_obj.day
            
            # Add ordinal suffix (1st, 2nd, 3rd, 4th, etc.)
            if 10 <= day % 100 <= 20:
                suffix = 'th'
            else:
                suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
            
            return date_obj.strftime(f'%B {day}{suffix}')
        except ValueError:
            return date_str
    
    def get_next_specialist(self) -> Optional[str]:
        """Get next specialist using round-robin assignment - returns None if no staff configured"""
        # NEW: Update specialists from database on each call to ensure latest data
        self._update_specialists_from_database()
        
        if not self.specialists:
            logger.info("👥 No specialists configured - booking without specific staff member")
            return None
        
        specialist = self.specialists[self.specialist_counter]
        self.specialist_counter = (self.specialist_counter + 1) % len(self.specialists)
        self.save_specialist_counter()
        logger.info(f"👥 Assigned specialist: {specialist}")
        return specialist
    
    def save_specialist_counter(self):
        """Save specialist counter to maintain rotation across restarts"""
        try:
            with open('specialist_counter.json', 'w') as f:
                json.dump({'counter': self.specialist_counter}, f)
        except Exception as e:
            logger.warning(f"Could not save specialist counter: {e}")
    
    def load_specialist_counter(self):
        """Load specialist counter from file"""
        try:
            if os.path.exists('specialist_counter.json'):
                with open('specialist_counter.json', 'r') as f:
                    data = json.load(f)
                    self.specialist_counter = data.get('counter', 0)
                    logger.info(f"👥 Loaded specialist counter: {self.specialist_counter}")
        except Exception as e:
            logger.warning(f"Could not load specialist counter: {e}")
            self.specialist_counter = 0
    
    def check_availability(self, date: str, service: str, preferred_time: Optional[str] = None) -> List[str]:
        """
        Check available appointment slots for a date and service, with optional preferred time for closest slots.
        Args:
            date: Date in YYYY-MM-DD format
            service: Service key (botox, hydrafacial, etc.) or custom service name
            preferred_time: Optional user-preferred time (various formats)
        Returns:
            List of available time slots (formatted for conversation)
        """
        import sys
        try:
            service_config = self.db.get_service_by_name(service)
            if not service_config:
                # For custom services (like up-next services), use default 60-minute duration
                logger.info(f"⚠️ Unknown service '{service}' - using default 60-minute duration for availability check")
                duration = 60
            else:
                duration = service_config['duration']
                
            available_slots = self.calendar_service.get_availability(date, duration)
            if not available_slots:
                logger.info(f"📅 No available slots for {service} on {date}")
                return []

            # Helper to convert time string to minutes since midnight
            def time_to_minutes(tstr):
                try:
                    dt = datetime.strptime(tstr, "%H:%M")
                    return dt.hour * 60 + dt.minute
                except Exception:
                    return None

            # Helper to robustly parse user time input to 'HH:MM' 24-hour format
            def parse_user_time(time_input):
                import re
                from datetime import datetime
                time_input = time_input.strip().lower()
                time_input = time_input.replace(' ', '')
                try:
                    return datetime.strptime(time_input, "%H:%M").strftime("%H:%M")
                except:
                    pass
                try:
                    return datetime.strptime(time_input, "%I:%M%p").strftime("%H:%M")
                except:
                    pass
                try:
                    return datetime.strptime(time_input, "%I:%M").strftime("%H:%M")
                except:
                    pass
                try:
                    return datetime.strptime(time_input, "%I%p").strftime("%H:%M")
                except:
                    pass
                try:
                    return datetime.strptime(time_input, "%H").strftime("%H:%M")
                except:
                    pass
                try:
                    return datetime.strptime(time_input, "%I %p").strftime("%H:%M")
                except:
                    pass
                if re.match(r"^\d{1,2}$", time_input):
                    try:
                        return datetime.strptime(time_input, "%H").strftime("%H:%M")
                    except:
                        pass
                return None

            if preferred_time:
                parsed_time = parse_user_time(preferred_time)
                if not parsed_time:
                    logger.warning(f"Could not parse preferred_time: {preferred_time}")
                    preferred_time = None
                else:
                    preferred_minutes = time_to_minutes(parsed_time)
                    slot_minutes = [(slot, time_to_minutes(slot)) for slot in available_slots]
                    before = [s for s, m in slot_minutes if m is not None and m < preferred_minutes]
                    after = [s for s, m in slot_minutes if m is not None and m > preferred_minutes]
                    closest_before = before[-1] if before else None
                    closest_after = after[0] if after else None
                    result = []
                    if closest_before:
                        result.append(self.format_time_conversational(closest_before))
                    if closest_after:
                        result.append(self.format_time_conversational(closest_after))
                    return result

            n = min(5, len(available_slots))
            if n == 0:
                return []

            def categorize_time(slot):
                hour = int(slot.split(':')[0])
                if hour < 12:
                    return 'morning'
                elif hour < 15:
                    return 'midday'
                else:
                    return 'afternoon'

            morning_slots = [s for s in available_slots if categorize_time(s) == 'morning']
            midday_slots = [s for s in available_slots if categorize_time(s) == 'midday']
            afternoon_slots = [s for s in available_slots if categorize_time(s) == 'afternoon']

            scattered = []
            if morning_slots:
                scattered.append(morning_slots[0])
            if afternoon_slots:
                scattered.append(afternoon_slots[-1])
            if midday_slots:
                scattered.append(midday_slots[len(midday_slots)//2])
            if morning_slots and len(morning_slots) > 1:
                scattered.append(morning_slots[-1])
            if afternoon_slots and len(afternoon_slots) > 1:
                scattered.append(afternoon_slots[0])

            while len(scattered) < n and len(scattered) < len(available_slots):
                for section in [morning_slots, midday_slots, afternoon_slots]:
                    if section and len(scattered) < n:
                        for slot in section:
                            if slot not in scattered:
                                scattered.append(slot)
                                break
            for slot in available_slots:
                if slot not in scattered and len(scattered) < n:
                    scattered.append(slot)

            formatted_slots = [self.format_time_conversational(slot) for slot in scattered]
            if len(available_slots) > n:
                formatted_slots.append(f"and {len(available_slots) - n} more options")
            return formatted_slots
        except Exception as e:
            logger.error(f"❌ Error checking availability: {str(e)}")
            return []
    
    def book_custom_appointment(self, name: str, phone: str, date: str, time: str, 
                               service: str, price: float = 0.0, duration: int = 60,
                               specialist_preference: Optional[str] = None) -> Dict:
        """
        Book a custom appointment bypassing service validation (for up_next services)
        
        Args:
            name: Customer name
            phone: Customer phone number
            date: Appointment date (YYYY-MM-DD)
            time: Appointment time (HH:MM)
            service: Custom service name (doesn't need to exist in services list)
            price: Custom price (defaults to $0.0)
            duration: Custom duration in minutes (defaults to 60)
            specialist_preference: Optional specialist preference
            
        Returns:
            Dict with booking result and details
        """
        try:
            logger.info(f"📝 Booking CUSTOM appointment for {name} - {service} (${price}, {duration}min) on {date} at {time}")
            
            # Check if slot is available (still validate calendar availability)
            if not self.calendar_service.check_slot_available(date, time, duration):
                available_slots = self.calendar_service.get_availability(date, duration)
                # Format available slots for response
                formatted_slots = []
                if available_slots:
                    for slot in available_slots[:3]:  # Show first 3 slots
                        formatted_slots.append(self.format_time_conversational(slot))
                    if len(available_slots) > 3:
                        formatted_slots.append(f"and {len(available_slots) - 3} more options")
                
                return {
                    'success': False,
                    'error': f"Time slot {time} not available on {date}",
                    'available_slots': formatted_slots
                }
            
            # Assign specialist (same logic as regular booking)
            if specialist_preference:
                if specialist_preference.lower() in [s.lower() for s in self.specialists]:
                    assigned_specialist = specialist_preference
                    logger.info(f"👥 Using preferred specialist: {assigned_specialist}")
                else:
                    assigned_specialist = self.get_next_specialist()
                    logger.info(f"👥 Preferred specialist '{specialist_preference}' not available, assigned: {assigned_specialist}")
            else:
                assigned_specialist = self.get_next_specialist()
            
            # Create custom service data
            service_data = {
                'name': service,
                'price': price,
                'duration': duration,
                'requires_deposit': False,  # Custom services don't require deposits by default
                'deposit_amount': 0.0,
                'description': f"Custom service: {service}"
            }
            
            # Create Google Calendar event
            from datetime import datetime
            
            # Parse date and time to create ISO datetime strings
            appointment_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            start_datetime = appointment_datetime.isoformat()
            end_datetime = (appointment_datetime + timedelta(minutes=duration)).isoformat()
            
            # Prepare appointment data for Google Calendar
            calendar_data = {
                'summary': f"{service} - {name}",
                'start_datetime': start_datetime,
                'end_datetime': end_datetime,
                'customer_name': name,
                'customer_phone': phone,
                'service': service,
                'specialist': assigned_specialist or 'Team',
                'price': price,
                'duration': duration
            }
            
            event_result = self.calendar_service.create_appointment(calendar_data)
            
            if not event_result.get('success'):
                return {
                    'success': False,
                    'error': f"Failed to create calendar event: {event_result.get('error', 'Unknown error')}"
                }
            
            # Prepare appointment data for database
            appointment_data = {
                'id': event_result['event_id'],
                'calendar_event_id': event_result['event_id'],
                'customer_name': name,
                'customer_phone': phone,
                'name': name,  # For message scheduler
                'phone': phone,  # For SMS confirmation
                'service': service,
                'service_name': service,
                'specialist': assigned_specialist,
                'appointment_date': date,
                'appointment_time': time,
                'date': date,  # For message scheduler  
                'time': time,  # For message scheduler
                'price': price,
                'duration': duration,
                'event_url': event_result.get('event_url', ''),
                'status': 'confirmed',
                'deposit_required': False,
                'deposit_amount': 0.0,
                'payment_url': None,
                'payment_link_id': None
            }
            
            # Save to database
            if self.db:
                self.db.create_appointment(appointment_data)
                logger.info(f"✅ Custom appointment saved to database: {event_result['event_id']}")
                
                # NEW: Immediately sync this appointment with Google Calendar to get full details
                logger.info(f"🔄 Immediately syncing custom appointment {event_result['event_id']} with Google Calendar...")
                sync_result = self.sync_single_appointment(event_result['event_id'])
                if sync_result['success']:
                    logger.info(f"✅ Custom appointment {event_result['event_id']} synced successfully")
                else:
                    logger.warning(f"⚠️ Failed to sync custom appointment {event_result['event_id']}: {sync_result.get('error')}")
            
            # Send confirmation SMS
            self.send_confirmation_sms(appointment_data)
            
            # Schedule follow-up messages
            if self.message_scheduler:
                try:
                    self.message_scheduler.schedule_appointment_messages(appointment_data)
                    logger.info(f"📅 Messages scheduled for custom appointment: {event_result['event_id']}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not schedule messages for custom appointment: {str(e)}")
            
            logger.info(f"✅ Custom appointment booked successfully: {name} - {service}")
            
            return {
                'success': True,
                'appointment': appointment_data,
                'event_id': event_result['event_id'],
                'message': f"Custom appointment booked: {service}",
                'payment_required': False  # Custom services don't require payment by default
            }
            
        except Exception as e:
            logger.error(f"❌ Error booking custom appointment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def book_appointment(self, name: str, phone: str, date: str, time: str, 
                        service: str, specialist_preference: Optional[str] = None) -> Dict:
        """
        Book an appointment with specialist assignment and payment processing
        
        Args:
            name: Customer name
            phone: Customer phone number
            date: Appointment date (YYYY-MM-DD)
            time: Appointment time (HH:MM)
            service: Service key
            specialist_preference: Optional specialist preference
            
        Returns:
            Dict with booking result and details including payment info
        """
        try:
            logger.info(f"📝 Booking appointment for {name} - {service} on {date} at {time}")
            
            service_config = self.db.get_service_by_name(service)
            if not service_config:
                return {
                    'success': False,
                    'error': f"Unknown service: {service}",
                    'available_services': [s['name'] for s in self.db.get_services()]
                }
            
            duration = service_config['duration']
            
            # Check if slot is available
            if not self.calendar_service.check_slot_available(date, time, duration):
                available_slots = self.check_availability(date, service)
                return {
                    'success': False,
                    'error': f"Time slot {time} not available on {date}",
                    'available_slots': available_slots
                }
            
            # Assign specialist
            if specialist_preference and specialist_preference in self.specialists:
                assigned_specialist = specialist_preference
                logger.info(f"👥 Using preferred specialist: {assigned_specialist}")
            else:
                assigned_specialist = self.get_next_specialist()
            
            # Format datetime for Google Calendar
            start_datetime = self.calendar_service.format_datetime_for_calendar(date, time)
            end_datetime = self.calendar_service.format_datetime_for_calendar(
                date, 
                self._add_minutes_to_time(time, duration)
            )
            
            if not start_datetime or not end_datetime:
                return {
                    'success': False,
                    'error': "Invalid date/time format"
                }
            
            # NEW: Handle appointment summary based on whether specialist is assigned
            if assigned_specialist:
                appointment_summary = f'{service_config["name"]} - {name} with {assigned_specialist}'
            else:
                appointment_summary = f'{service_config["name"]} - {name}'
            
            # Prepare appointment data for Google Calendar
            appointment_data = {
                'summary': appointment_summary,
                'start_datetime': start_datetime,
                'end_datetime': end_datetime,
                'customer_name': name,
                'customer_phone': phone,
                'service': service_config['name'],
                'specialist': assigned_specialist or 'TBD',  # Use 'TBD' if no specialist assigned
                'price': service_config['price'],
                'duration': duration
            }
            
            logger.info(f"📅 Creating Google Calendar event...")
            
            # Create booking in Google Calendar
            calendar_result = self.calendar_service.create_appointment(appointment_data)
            
            if not calendar_result['success']:
                logger.error(f"❌ Google Calendar booking failed: {calendar_result}")
                return {
                    'success': False,
                    'error': f"Calendar booking failed: {calendar_result['error']}"
                }
            
            # Prepare appointment details for response
            appointment_details = {
                'id': calendar_result['event_id'],
                'name': name,
                'phone': phone,
                'date': date,
                'time': time,
                'service': service,
                'service_name': service_config['name'],
                'specialist': assigned_specialist,
                'price': service_config['price'],
                'duration': duration,
                'event_url': calendar_result.get('event_url'),
                'created_at': datetime.now().isoformat(),
                'status': 'confirmed'
            }
            
            # Log appointment creation to database
            if self.db:
                # Format phone number to E.164 before storing in database
                formatted_phone = format_phone_to_e164(phone)
                self.db.log_appointment_creation(
                    calendar_result['event_id'],
                    name,
                    formatted_phone,
                    service_config['name'],
                    assigned_specialist,
                    date,
                    time
                )
                
                # NEW: Create or update customer record when appointment is booked
                appointment_customer_data = {
                    'customer_phone': formatted_phone,
                    'customer_name': name
                }
                self.db.create_or_update_customer_from_appointment(appointment_customer_data)
                
                # NEW: Immediately sync this appointment with Google Calendar to get full details
                logger.info(f"🔄 Immediately syncing appointment {calendar_result['event_id']} with Google Calendar...")
                sync_result = self.sync_single_appointment(calendar_result['event_id'])
                if sync_result['success']:
                    logger.info(f"✅ Appointment {calendar_result['event_id']} synced successfully")
                else:
                    logger.warning(f"⚠️ Failed to sync appointment {calendar_result['event_id']}: {sync_result.get('error')}")
            
            # Create payment link if service requires deposit
            payment_result = None
            if service_config.get('requires_deposit', False):
                logger.info(f"💳 Creating payment link for deposit...")
                payment_result = self.payment_service.create_deposit_payment_link(appointment_details)
                
                if payment_result['success']:
                    appointment_details['deposit_required'] = True
                    appointment_details['deposit_amount'] = payment_result['amount']
                    appointment_details['payment_url'] = payment_result['payment_url']
                    appointment_details['payment_link_id'] = payment_result['payment_link_id']
                else:
                    logger.warning(f"⚠️ Payment link creation failed: {payment_result.get('error')}")
                    appointment_details['deposit_required'] = True
                    appointment_details['payment_error'] = payment_result.get('error')
            
            # Save appointment locally for backup
            self.save_appointment(appointment_details)
            
            # Send confirmation SMS
            confirmation_sent = self.send_confirmation_sms(appointment_details, payment_result)
            
            # NEW: Schedule reminder and thank you messages
            logger.info(f"📅 Scheduling automated messages for {appointment_details['name']}")
            scheduling_result = self.message_scheduler.schedule_appointment_messages(appointment_details)
            
            if scheduling_result['success']:
                logger.info(f"✅ Automated messages scheduled successfully")
                appointment_details['messages_scheduled'] = True
                appointment_details['scheduled_messages'] = scheduling_result['results']
            else:
                logger.warning(f"⚠️ Failed to schedule automated messages: {scheduling_result.get('error')}")
                appointment_details['messages_scheduled'] = False
                appointment_details['message_scheduling_error'] = scheduling_result.get('error')
            
            logger.info(f"✅ Appointment successfully booked: {appointment_details['id']}")
            
            return {
                'success': True,
                'appointment': appointment_details,
                'calendar_event_id': calendar_result['event_id'],
                'confirmation_sent': confirmation_sent,
                'payment_result': payment_result,
                'message_scheduling': scheduling_result  # Add this line
            }
            
        except Exception as e:
            logger.error(f"❌ Error booking appointment: {str(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_appointment(self, event_id: str) -> Dict:
        """
        Cancel an appointment by deleting it from Google Calendar
        Also handles refund if payment was made and cancels scheduled messages
        """
        try:
            logger.info(f"🗑️ Cancelling appointment: {event_id}")
            
            # Cancel scheduled messages first
            logger.info(f"🗑️ Cancelling scheduled messages for appointment {event_id}")
            message_cancel_result = self.message_scheduler.cancel_appointment_messages(event_id)
            
            # Check if there's a payment to refund
            payment_record = self.payment_service.get_payment_by_appointment(event_id)
            refund_result = None
            
            if payment_record and payment_record['status'] == 'pending':
                logger.info(f"💰 Processing refund for cancelled appointment...")
                refund_result = self.payment_service.process_refund(
                    payment_record, 
                    reason="Appointment cancelled"
                )
            
            # Delete from Google Calendar
            result = self.calendar_service.delete_appointment(event_id)
            
            if result['success']:
                logger.info(f"✅ Appointment cancelled successfully: {event_id}")
                return {
                    'success': True,
                    'message': 'Appointment cancelled successfully',
                    'refund_result': refund_result,
                    'messages_cancelled': message_cancel_result  # Add this line
                }
            else:
                logger.error(f"❌ Failed to cancel appointment: {result['error']}")
                return {
                    'success': False,
                    'error': result['error']
                }
                
        except Exception as e:
            logger.error(f"❌ Error cancelling appointment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def search_appointments_by_phone(self, phone: str) -> Dict:
        """
        Search for upcoming appointments by phone number
        
        Args:
            phone: Customer phone number (various formats supported)
            
        Returns:
            Dict with search results and formatted appointment list
        """
        try:
            logger.info(f"🔍 Searching appointments for phone: {phone}")
            
            if not self.db:
                return {
                    'success': False,
                    'error': 'Database service not available'
                }
            
            # Format phone number for consistent searching
            formatted_phone = self._format_phone_for_search(phone)
            
            # Get upcoming appointments from database
            appointments = self.db.get_appointments_by_phone(formatted_phone, only_upcoming=True)
            
            if not appointments:
                logger.info(f"📱 No upcoming appointments found for {formatted_phone}")
                return {
                    'success': True,
                    'appointments': [],
                    'formatted_list': "I couldn't find any upcoming appointments for that phone number. Please double-check the number or contact us during business hours for assistance.",
                    'count': 0
                }
            
            # Format appointments for display
            formatted_appointments = self._format_appointments_for_display(appointments)
            
            logger.info(f"📱 Found {len(appointments)} upcoming appointments for {formatted_phone}")
            
            return {
                'success': True,
                'appointments': appointments,
                'formatted_list': formatted_appointments,
                'count': len(appointments)
            }
            
        except Exception as e:
            logger.error(f"❌ Error searching appointments by phone: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_cancellation_timing(self, appointment_date: str, appointment_time: str) -> Dict:
        """
        Validate if an appointment can be cancelled based on 24-hour policy
        
        Args:
            appointment_date: Appointment date (YYYY-MM-DD)
            appointment_time: Appointment time (HH:MM)
            
        Returns:
            Dict with validation result and timing details
        """
        try:
            logger.info(f"⏰ Validating cancellation timing for {appointment_date} at {appointment_time}")
            
            # Parse appointment datetime
            appointment_datetime = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")
            current_datetime = datetime.now()
            
            # Calculate time difference
            time_difference = appointment_datetime - current_datetime
            hours_until_appointment = time_difference.total_seconds() / 3600
            
            # Check if appointment is in the future
            if time_difference.total_seconds() <= 0:
                return {
                    'success': False,
                    'can_cancel': False,
                    'reason': 'Appointment is in the past',
                    'hours_until_appointment': hours_until_appointment
                }
            
            # Check 24-hour policy
            if hours_until_appointment < 24:
                return {
                    'success': True,
                    'can_cancel': False,
                    'reason': 'Less than 24 hours before appointment',
                    'hours_until_appointment': hours_until_appointment,
                    'message': f"Unfortunately, I cannot cancel this appointment as it's less than 24 hours away. Please contact us during business hours to discuss your situation."
                }
            
            return {
                'success': True,
                'can_cancel': True,
                'hours_until_appointment': hours_until_appointment,
                'message': f"Your appointment is {int(hours_until_appointment)} hours away, so it can be cancelled."
            }
            
        except Exception as e:
            logger.error(f"❌ Error validating cancellation timing: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_appointment_with_validation(self, event_id: str) -> Dict:
        """
        Cancel an appointment with full validation and cleanup
        
        Args:
            event_id: Google Calendar event ID
            
        Returns:
            Dict with cancellation result
        """
        try:
            logger.info(f"🗑️ Starting validated cancellation for appointment: {event_id}")
            
            # Get appointment details from database
            appointment = self.db.get_appointment_by_id(event_id)
            if not appointment:
                return {
                    'success': False,
                    'error': 'Appointment not found in database'
                }
            
            # Validate cancellation timing
            timing_validation = self.validate_cancellation_timing(
                appointment['appointment_date'], 
                appointment['appointment_time']
            )
            
            if not timing_validation['success']:
                return {
                    'success': False,
                    'error': timing_validation['error']
                }
            
            if not timing_validation['can_cancel']:
                return {
                    'success': False,
                    'error': timing_validation['reason'],
                    'message': timing_validation.get('message', 'Cannot cancel this appointment'),
                    'hours_until_appointment': timing_validation.get('hours_until_appointment')
                }
            
            # Proceed with cancellation
            cancellation_result = self.cancel_appointment(event_id)
            
            if cancellation_result['success']:
                # Update database status
                self.db.update_appointment(event_id, {'status': 'cancelled'})
                
                # Send cancellation confirmation SMS
                self._send_cancellation_confirmation_sms(appointment)
                
                logger.info(f"✅ Appointment {event_id} cancelled with full validation")
                
                return {
                    'success': True,
                    'message': 'Appointment cancelled successfully',
                    'appointment_details': appointment,
                    'refund_result': cancellation_result.get('refund_result'),
                    'messages_cancelled': cancellation_result.get('messages_cancelled')
                }
            else:
                return cancellation_result
                
        except Exception as e:
            logger.error(f"❌ Error in validated cancellation: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_phone_for_search(self, phone: str) -> str:
        """Format phone number for consistent database searching"""
        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, phone))
        
        # Handle different formats
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith('1'):
            return f"+{digits}"
        elif len(digits) > 11:
            # Keep only last 10 digits for US numbers
            return f"+1{digits[-10:]}"
        else:
            # Return as-is if we can't format it
            return phone
    
    def _format_appointments_for_display(self, appointments: List[Dict]) -> str:
        """Format appointments for conversational display"""
        if not appointments:
            return "No appointments found."
        
        if len(appointments) == 1:
            appt = appointments[0]
            date_str = self._format_date_conversational(appt['appointment_date'])
            time_str = datetime.strptime(appt['appointment_time'], '%H:%M').strftime('%I:%M %p')
            
            return (
                f"I found your appointment: {appt['service_name']} on {date_str} at {time_str} "
                f"with {appt['specialist'] or 'our team'}. "
                f"Is this the appointment you'd like to cancel?"
            )
        
        # Multiple appointments - simplified format
        appointment_list = []
        for i, appt in enumerate(appointments, 1):
            date_str = self._format_date_conversational(appt['appointment_date'])
            time_str = datetime.strptime(appt['appointment_time'], '%H:%M').strftime('%I:%M %p')
            
            appointment_list.append(f"{i}. {date_str} at {time_str}")
        
        return (
            f"I found {len(appointments)} appointments.\n\n" +
            "\n".join(appointment_list) +
            "\n\nPlease answer with the number of the appointment that you want to cancel."
        )
    
    def _send_cancellation_confirmation_sms(self, appointment: Dict):
        """Send cancellation confirmation SMS to customer"""
        try:
            # Get template from database
            template = self._get_message_template('cancellation_confirmation')
            if not template or not template.get('is_enabled', True):
                logger.info("Cancellation confirmation template disabled or not found, skipping")
                return False
            
            phone = appointment['customer_phone']
            
            # Convert appointment data to template format
            template_appointment_data = {
                'name': appointment['customer_name'],
                'date': appointment['appointment_date'],
                'time': appointment['appointment_time'],
                'service_name': appointment['service_name'],
                'specialist': appointment['specialist'],
                'price': appointment['price'],
                'duration': appointment['duration']
            }
            
            # Format message using template
            message = self._format_message_with_template(template, template_appointment_data)
            
            success = self.sms_service.send_sms(
                from_number="+18773900002",  # Business number
                to_number=phone,
                message=message
            )
            
            if success:
                logger.info(f"✅ Cancellation confirmation SMS sent to {phone}")
            else:
                logger.warning(f"⚠️ Failed to send cancellation confirmation SMS to {phone}")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Error sending cancellation confirmation SMS: {str(e)}")
            return False
    
    def mark_appointment_completed(self, appointment_id: str, showed_up: bool = True) -> Dict:
        """
        Mark appointment as completed and process refund if customer showed up
        
        Args:
            appointment_id: Appointment/event ID
            showed_up: Whether customer showed up
            
        Returns:
            Dict with completion result
        """
        try:
            logger.info(f"✅ Marking appointment {appointment_id} as completed (showed_up: {showed_up})")
            
            # Get payment record
            payment_record = self.payment_service.get_payment_by_appointment(appointment_id)
            refund_result = None
            
            if payment_record and payment_record['status'] == 'pending' and showed_up:
                logger.info(f"💰 Processing show-up refund...")
                refund_result = self.payment_service.process_refund(
                    payment_record, 
                    reason="Customer showed up for appointment"
                )
                
                if refund_result['success']:
                    # Send refund notification SMS
                    self.send_refund_notification_sms(payment_record, refund_result)
            
            return {
                'success': True,
                'message': f'Appointment marked as completed',
                'refund_processed': refund_result['success'] if refund_result else False,
                'refund_result': refund_result
            }
            
        except Exception as e:
            logger.error(f"❌ Error marking appointment completed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_message_template(self, template_type: str) -> Optional[Dict]:
        """Get message template from database"""
        try:
            return self.db.get_message_template(template_type)
        except Exception as e:
            logger.error(f"❌ Error getting message template {template_type}: {str(e)}")
            return None

    def _format_message_with_template(self, template: Dict, appointment_data: Dict) -> str:
        """Format message using template and appointment data"""
        try:
            message_content = template['message_content']
            
            # Format date and time
            date = datetime.strptime(appointment_data['date'], '%Y-%m-%d').strftime('%m/%d/%Y')
            time = datetime.strptime(appointment_data['time'], '%H:%M').strftime('%I:%M %p').lstrip('0')
            
            # Replace template variables
            replacements = {
                '{name}': appointment_data.get('name', ''),
                '{service}': appointment_data.get('service', ''),
                '{time}': time,
                '{date}': date,
                '{specialist}': appointment_data.get('specialist', ''),
                '{price}': str(appointment_data.get('price', '')),
                '{duration}': str(appointment_data.get('duration', ''))
            }
            
            for placeholder, value in replacements.items():
                message_content = message_content.replace(placeholder, value)
            
            return message_content
            
        except Exception as e:
            logger.error(f"❌ Error formatting message with template: {str(e)}")
            return template.get('message_content', '')
    
    def send_confirmation_sms(self, appointment_data, payment_result=None):
        """Send confirmation SMS to customer with payment link if applicable"""
        try:
            # Get template from database
            template = self._get_message_template('appointment_confirmation')
            if not template or not template.get('is_enabled', True):
                logger.info("Appointment confirmation template disabled or not found, skipping")
                return False
            
            # Format phone number to E.164 format
            phone = appointment_data['phone']
            
            # Clean the phone number first
            phone_digits = ''.join(filter(str.isdigit, phone))
            
            # Format to E.164
            if len(phone_digits) == 10:
                phone = f"+1{phone_digits}"
            elif len(phone_digits) == 11 and phone_digits.startswith('1'):
                phone = f"+{phone_digits}"
            elif not phone.startswith('+'):
                phone = f"+{phone}"
            
            logger.info(f"📱 Formatted phone number: {phone}")
            
            # Format message using template
            message = self._format_message_with_template(template, appointment_data)
            
            # Add payment information if applicable
            if payment_result and payment_result['success']:
                message += f"\n\nTo secure your appointment, please pay the $50 show-up deposit: {payment_result['payment_url']}\n\nYou'll get your $50 refund when you show up!"
            elif appointment_data.get('deposit_required') and appointment_data.get('payment_error'):
                message += f"\n\nA $50 show-up deposit is required. Please call us to complete payment."
            
            # Send SMS using the business number
            success = self.sms_service.send_sms(
                from_number="+18773900002",  # Business number
                to_number=phone,
                message=message
            )
            
            if success:
                logger.info(f"✅ Confirmation SMS sent to {phone}")
                # Remove any interest notifications for this phone number
                if self.db:
                    self.db.delete_interest_notifications_for_phone(phone)
                    logger.info(f"🚮 Cleared interest notifications for {phone} after appointment confirmation.")
            else:
                logger.warning(f"⚠️ Failed to send confirmation SMS to {phone}")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Error sending confirmation SMS: {str(e)}")
            return False
    
    def send_refund_notification_sms(self, payment_record, refund_result):
        """Send SMS notification when refund is processed"""
        try:
            # Get template from database
            template = self._get_message_template('refund_notification')
            if not template or not template.get('is_enabled', True):
                logger.info("Refund notification template disabled or not found, skipping")
                return False
            
            phone = payment_record['customer_phone']
            amount = refund_result['amount_refunded']
            
            # Use template message
            message = template['message_content']
            
            success = self.sms_service.send_sms(
                from_number="+18773900002",  # Business number
                to_number=phone,
                message=message
            )
            
            if success:
                logger.info(f"✅ Refund notification SMS sent to {phone}")
            else:
                logger.warning(f"⚠️ Failed to send refund notification SMS to {phone}")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Error sending refund notification SMS: {str(e)}")
            return False
    
    def save_appointment(self, appointment_data: Dict) -> bool:
        """Save appointment details to local backup file"""
        try:
            # Validate required fields
            required_fields = ['name', 'phone', 'date', 'time', 'service', 'specialist']
            for field in required_fields:
                if field not in appointment_data:
                    logger.error(f"❌ Missing required field: {field}")
                    return False
            
            # Format phone number
            phone = appointment_data['phone']
            if not phone.startswith('+'):
                phone = f"+1{phone}" if len(phone) == 10 else f"+{phone}"
            appointment_data['phone'] = phone
            
            # Format date and time
            try:
                date_obj = datetime.strptime(appointment_data['date'], '%Y-%m-%d')
                time_obj = datetime.strptime(appointment_data['time'], '%H:%M')
                appointment_data['formatted_date'] = date_obj.strftime('%A, %B %d, %Y')
                appointment_data['formatted_time'] = time_obj.strftime('%I:%M %p')
            except ValueError as e:
                logger.error(f"❌ Invalid date/time format: {str(e)}")
                return False
            
            # Load existing appointments
            appointments = []
            if os.path.exists(self.appointments_file):
                try:
                    with open(self.appointments_file, 'r') as f:
                        appointments = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not load existing appointments: {e}")
            
            # Add new appointment
            appointments.append(appointment_data)
            
            # Save back to file
            with open(self.appointments_file, 'w') as f:
                json.dump(appointments, f, indent=2)
            
            logger.info(f"📝 Appointment saved to local backup file")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving appointment: {str(e)}")
            return False
    
    def get_service_list(self) -> str:
        """Get formatted list of available services for AI responses"""
        service_list = []
        for config in self.db.get_services():
            deposit_note = f" (+${int(config['deposit_amount'])} deposit)" if config.get('requires_deposit') else ""
            service_list.append(f"{config['name']} (${config['price']}, {config['duration']}min{deposit_note})")
        
        return "\n".join(service_list)
    
    def _add_minutes_to_time(self, time_str: str, minutes: int) -> str:
        """Helper function to add minutes to a time string"""
        try:
            time_obj = datetime.strptime(time_str, "%H:%M")
            new_time = time_obj + timedelta(minutes=minutes)
            return new_time.strftime("%H:%M")
        except Exception as e:
            logger.error(f"Error adding minutes to time: {e}")
            return time_str

    @staticmethod
    def parse_appointment_description(description):
        result = {}
        if not description:
            return result
        import re
        patterns = {
            'customer_name': r'Customer:\s*(.*)',
            'customer_phone': r'Phone:\s*([+\d\-() ]+)',
            'service': r'Service:\s*(.*)',
            'specialist': r'Specialist:\s*(.*)',
            'price': r'Price:\s*\$?([\d.]+)',
            'duration': r'Duration:\s*([\d]+) minutes'
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, description)
            if match:
                value = match.group(1).strip()
                if key == 'price':
                    try:
                        value = float(value)
                    except Exception:
                        value = None
                elif key == 'duration':
                    try:
                        value = int(value)
                    except Exception:
                        value = None
                result[key] = value
        return result

    def sync_appointments_with_google_calendar(self):
        """
        Sync the appointments table with Google Calendar events.
        - Adds new events from Google Calendar to DB
        - Updates moved/edited events
        - Marks as cancelled if deleted/cancelled in Google Calendar
        """
        logger.info("🔄 Starting sync with Google Calendar...")
        events = self.calendar_service.list_all_events()
        if not self.db:
            logger.error("❌ No database service available for appointment sync.")
            return
        # Build a map of event_id -> event
        event_map = {e['id']: e for e in events}
        # Get all appointments in DB (past and future)
        conn = self.db
        all_db_appts = []
        try:
            import sqlite3
            db_conn = sqlite3.connect(conn.db_file)
            cursor = db_conn.cursor()
            cursor.execute('SELECT calendar_event_id FROM appointments')
            all_db_ids = [row[0] for row in cursor.fetchall()]
            db_conn.close()
        except Exception as e:
            logger.error(f"❌ Error fetching all DB appointment IDs: {e}")
            return
        # 1. Update/add all events from Google Calendar
        for event in events:
            event_id = event['id']
            status = event.get('status', 'confirmed')
            start = event.get('start', {}).get('dateTime')
            end = event.get('end', {}).get('dateTime')
            summary = event.get('summary', '')
            description = event.get('description', '')
            html_link = event.get('htmlLink')
            # Extended properties (private fields)
            ext = event.get('extendedProperties', {}).get('private', {})
            # Parse fields
            customer_name = ext.get('customer_name')
            customer_phone = ext.get('customer_phone')
            service = ext.get('service')
            specialist = ext.get('specialist')
            price = float(ext.get('price')) if ext.get('price') else None
            duration = int(ext.get('duration')) if ext.get('duration') else None
            
            # Format phone number to E.164 if present
            if customer_phone:
                customer_phone = format_phone_to_e164(customer_phone)
            # Parse date/time
            from dateutil import parser as dtparser
            appointment_date = None
            appointment_time = None
            if start:
                try:
                    dt = dtparser.parse(start)
                    appointment_date = dt.strftime('%Y-%m-%d')
                    appointment_time = dt.strftime('%H:%M')
                except Exception:
                    pass
            # Always parse from description and let it overwrite any fields found
            parsed = self.parse_appointment_description(description)
            if parsed.get('customer_name'):
                customer_name = parsed['customer_name']
            if parsed.get('customer_phone'):
                customer_phone = format_phone_to_e164(parsed['customer_phone'])
            if parsed.get('service'):
                service = parsed['service']
            if parsed.get('specialist'):
                specialist = parsed['specialist']
            if parsed.get('price') is not None:
                price = parsed['price']
            if parsed.get('duration') is not None:
                duration = parsed['duration']
            # If event is cancelled, mark as cancelled in DB and cancel scheduled messages
            if status == 'cancelled':
                if event_id in all_db_ids:
                    self.db.update_appointment(event_id, {'status': 'cancelled'})
                    
                    # Cancel scheduled messages for cancelled appointment
                    if self.message_scheduler:
                        try:
                            cancel_result = self.message_scheduler.cancel_appointment_messages(event_id)
                            if cancel_result['success']:
                                logger.info(f"🗑️ Cancelled {cancel_result.get('cancelled_count', 0)} scheduled messages for cancelled appointment {event_id}")
                            else:
                                logger.warning(f"⚠️ Failed to cancel messages for cancelled appointment {event_id}: {cancel_result.get('error', 'Unknown error')}")
                        except Exception as e:
                            logger.error(f"❌ Error cancelling messages for cancelled appointment {event_id}: {str(e)}")
                continue
            # If event exists in DB, update it
            if event_id in all_db_ids:
                # Get current appointment data to check for time changes
                current_appointment = self.db.get_appointment_by_id(event_id)
                time_changed = False
                old_date = None
                old_time = None
                
                if current_appointment and appointment_date and appointment_time:
                    old_date = current_appointment.get('appointment_date')
                    old_time = current_appointment.get('appointment_time')
                    
                    # Check if appointment time changed
                    if old_date != appointment_date or old_time != appointment_time:
                        time_changed = True
                        logger.info(f"⏰ Time change detected for appointment {event_id}: {old_date} {old_time} -> {appointment_date} {appointment_time}")
                
                update_fields = {
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'service': service,
                    'specialist': specialist,
                    'price': price,
                    'duration': duration,
                    'appointment_date': appointment_date,
                    'appointment_time': appointment_time,
                    'event_url': html_link,
                    'status': status,
                    'service_name': summary
                }
                # Remove None values so we don't overwrite with None
                update_fields = {k: v for k, v in update_fields.items() if v is not None}
                self.db.update_appointment(event_id, update_fields)
                
                # Reschedule messages if time changed
                if time_changed and self.message_scheduler:
                    try:
                        logger.info(f"🔄 Starting message reschedule for appointment {event_id} with old time: {old_date} {old_time} -> new time: {appointment_date} {appointment_time}")
                        
                        new_appointment_data = {
                            'appointment_date': appointment_date,
                            'appointment_time': appointment_time,
                            'customer_name': customer_name,
                            'customer_phone': customer_phone,
                            'service': service,
                            'service_name': summary,
                            'specialist': specialist,
                            'price': price,
                            'duration': duration
                        }
                        
                        # Pass the old appointment data for proper comparison
                        reschedule_result = self.message_scheduler.reschedule_appointment_messages_with_old_data(
                            event_id, new_appointment_data, old_date, old_time
                        )
                        
                        if reschedule_result['success']:
                            if reschedule_result.get('rescheduled'):
                                logger.info(f"✅ Messages rescheduled for appointment {event_id}: {reschedule_result.get('cancelled_count', 0)} cancelled, {len(reschedule_result.get('new_messages', {}).get('messages', []))} new")
                            else:
                                logger.info(f"ℹ️ No rescheduling needed for appointment {event_id}: {reschedule_result.get('reason', 'Unknown')}")
                        else:
                            logger.warning(f"⚠️ Failed to reschedule messages for appointment {event_id}: {reschedule_result.get('error', 'Unknown error')}")
                            
                    except Exception as e:
                        logger.error(f"❌ Error during message rescheduling for appointment {event_id}: {str(e)}")
            else:
                # New event, add to DB
                appt = {
                    'calendar_event_id': event_id,
                    'id': event_id,
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'service': service,
                    'specialist': specialist,
                    'price': price,
                    'duration': duration,
                    'appointment_date': appointment_date,
                    'appointment_time': appointment_time,
                    'event_url': html_link,
                    'status': status,
                    'service_name': summary
                }
                self.db.create_appointment(appt)
        # 2. For each appointment in DB, if not in Google Calendar, mark as cancelled and cancel messages
        for db_id in all_db_ids:
            if db_id not in event_map:
                self.db.update_appointment(db_id, {'status': 'cancelled'})
                
                # Cancel scheduled messages for deleted appointment
                if self.message_scheduler:
                    try:
                        cancel_result = self.message_scheduler.cancel_appointment_messages(db_id)
                        if cancel_result['success']:
                            logger.info(f"🗑️ Cancelled {cancel_result.get('cancelled_count', 0)} scheduled messages for deleted appointment {db_id}")
                        else:
                            logger.warning(f"⚠️ Failed to cancel messages for deleted appointment {db_id}: {cancel_result.get('error', 'Unknown error')}")
                    except Exception as e:
                        logger.error(f"❌ Error cancelling messages for deleted appointment {db_id}: {str(e)}")
        logger.info("✅ Sync with Google Calendar complete.")
    
    def sync_single_appointment(self, event_id: str) -> Dict:
        """
        Sync a single appointment with Google Calendar to get full details
        
        Args:
            event_id: Google Calendar event ID
            
        Returns:
            Dict with sync result
        """
        try:
            logger.info(f"🔄 Syncing single appointment: {event_id}")
            
            # Get the event from Google Calendar
            event = self.calendar_service.get_event(event_id)
            if not event:
                return {
                    'success': False,
                    'error': f'Event {event_id} not found in Google Calendar'
                }
            
            # Parse event data (same logic as full sync)
            status = event.get('status', 'confirmed')
            start = event.get('start', {}).get('dateTime')
            end = event.get('end', {}).get('dateTime')
            summary = event.get('summary', '')
            description = event.get('description', '')
            html_link = event.get('htmlLink')
            
            # Extended properties (private fields)
            ext = event.get('extendedProperties', {}).get('private', {})
            customer_name = ext.get('customer_name')
            customer_phone = ext.get('customer_phone')
            service = ext.get('service')
            specialist = ext.get('specialist')
            price = float(ext.get('price')) if ext.get('price') else None
            duration = int(ext.get('duration')) if ext.get('duration') else None
            
            # Format phone number to E.164 if present
            if customer_phone:
                customer_phone = format_phone_to_e164(customer_phone)
            
            # Parse date/time
            from dateutil import parser as dtparser
            appointment_date = None
            appointment_time = None
            if start:
                try:
                    dt = dtparser.parse(start)
                    appointment_date = dt.strftime('%Y-%m-%d')
                    appointment_time = dt.strftime('%H:%M')
                except Exception:
                    pass
            
            # Always parse from description and let it overwrite any fields found
            parsed = self.parse_appointment_description(description)
            if parsed.get('customer_name'):
                customer_name = parsed['customer_name']
            if parsed.get('customer_phone'):
                customer_phone = format_phone_to_e164(parsed['customer_phone'])
            if parsed.get('service'):
                service = parsed['service']
            if parsed.get('specialist'):
                specialist = parsed['specialist']
            if parsed.get('price') is not None:
                price = parsed['price']
            if parsed.get('duration') is not None:
                duration = parsed['duration']
            
            # Update appointment in database with full details
            update_fields = {
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'service': service,
                'specialist': specialist,
                'price': price,
                'duration': duration,
                'appointment_date': appointment_date,
                'appointment_time': appointment_time,
                'event_url': html_link,
                'status': status,
                'service_name': summary
            }
            
            # Remove None values so we don't overwrite with None
            update_fields = {k: v for k, v in update_fields.items() if v is not None}
            
            if self.db:
                self.db.update_appointment(event_id, update_fields)
                logger.info(f"✅ Updated appointment {event_id} with full details from Google Calendar")
            
            return {
                'success': True,
                'updated_fields': list(update_fields.keys())
            }
            
        except Exception as e:
            logger.error(f"❌ Error syncing single appointment {event_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
