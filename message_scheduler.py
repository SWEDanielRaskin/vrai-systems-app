# message_scheduler.py - FIXED VERSION
import sqlite3
import logging
import json
import os
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from database_service import DatabaseService

logger = logging.getLogger(__name__)

# STANDALONE FUNCTION - This fixes the serialization issue
def send_scheduled_message_standalone(message_id: str):
    """
    Standalone function to send scheduled messages - avoids serialization issues
    This function will be called by APScheduler
    """
    try:
        logger.info(f"🚀 Executing scheduled message: {message_id}")
        
        # Import services here to avoid circular imports
        from sms_service import SMSService
        from google_calendar_service import GoogleCalendarService
        
        sms_service = SMSService()
        calendar_service = GoogleCalendarService()
        
        # Get message details from database
        db_file = 'scheduled_messages.db'
        message_data = _get_scheduled_message_from_db(message_id, db_file)
        
        if not message_data:
            logger.error(f"❌ Message {message_id} not found in database")
            return
        
        # Check if appointment still exists (for reminders)
        if message_data['message_type'] == '24hr_reminder':
            if not _appointment_still_exists(message_data['appointment_id'], calendar_service):
                logger.info(f"📅 Appointment {message_data['appointment_id']} no longer exists - cancelling reminder")
                _update_message_status_in_db(message_id, 'cancelled', 'Appointment no longer exists', db_file)
                return
        
        # Send the SMS
        success = sms_service.send_sms(
            to_number=message_data['customer_phone'],
            from_number="+18773900002",  # Your business number
            message=message_data['message_content']
        )
        
        if success:
            _update_message_status_in_db(message_id, 'sent', None, db_file)
            logger.info(f"✅ Scheduled message sent successfully: {message_id}")
        else:
            _update_message_status_in_db(message_id, 'failed', 'SMS sending failed', db_file)
            logger.error(f"❌ Failed to send scheduled message: {message_id}")
            
    except Exception as e:
        logger.error(f"❌ Error executing scheduled message {message_id}: {str(e)}")
        _update_message_status_in_db(message_id, 'failed', str(e), 'scheduled_messages.db')

# Helper functions for the standalone function
def _get_scheduled_message_from_db(message_id: str, db_file: str) -> Optional[Dict]:
    """Get scheduled message from database"""
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT message_id, appointment_id, customer_name, customer_phone,
                   message_type, scheduled_time, message_content, status
            FROM scheduled_messages 
            WHERE message_id = ?
        ''', (message_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'message_id': row[0],
                'appointment_id': row[1],
                'customer_name': row[2],
                'customer_phone': row[3],
                'message_type': row[4],
                'scheduled_time': row[5],
                'message_content': row[6],
                'status': row[7]
            }
        return None
        
    except Exception as e:
        logger.error(f"❌ Error retrieving scheduled message: {str(e)}")
        return None

def _appointment_still_exists(appointment_id: str, calendar_service) -> bool:
    """Check if appointment still exists in Google Calendar"""
    try:
        return calendar_service.check_event_exists(appointment_id)
    except Exception as e:
        logger.error(f"❌ Error checking appointment existence: {str(e)}")
        return True  # Default to True to avoid cancelling valid reminders

def _update_message_status_in_db(message_id: str, status: str, error_message: str, db_file: str):
    """Update message status in database"""
    try:
        eastern = pytz.timezone('US/Eastern')
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        if status == 'sent':
            cursor.execute('''
                UPDATE scheduled_messages 
                SET status = ?, sent_at = ?
                WHERE message_id = ?
            ''', (status, datetime.now(eastern).isoformat(), message_id))
        else:
            cursor.execute('''
                UPDATE scheduled_messages 
                SET status = ?, error_message = ?
                WHERE message_id = ?
            ''', (status, error_message, message_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Error updating message status: {str(e)}")

class MessageScheduler:
    """Service for scheduling appointment reminders and thank you messages"""
    
    def __init__(self, database_service=None):
        self.timezone = pytz.timezone('US/Eastern')
        
        # Database file for storing scheduled messages
        self.db_file = 'scheduled_messages.db'
        
        # Initialize database service for message templates
        self.db = database_service or DatabaseService()
        
        # Initialize database
        self._init_database()
        
        # Configure APScheduler with SQLite persistence
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{self.db_file}')
        }
        executors = {
            'default': ThreadPoolExecutor(max_workers=5)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        
        # Initialize scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self.timezone
        )
        
        # Start the scheduler
        self.scheduler.start()
        logger.info("✅ Message scheduler initialized with persistence")
    
    def _init_database(self):
        """Initialize SQLite database for tracking scheduled messages"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Create table for scheduled messages tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE NOT NULL,
                    appointment_id TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    message_content TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    error_message TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("📝 Scheduled messages database initialized")
            
        except Exception as e:
            logger.error(f"❌ Error initializing database: {str(e)}")
    
    def schedule_appointment_messages(self, appointment_data: Dict) -> Dict:
        """
        Schedule both 24-hour reminder and thank you messages for an appointment
        """
        try:
            appointment_datetime = self._parse_appointment_datetime(
                appointment_data['date'], 
                appointment_data['time']
            )
            
            if not appointment_datetime:
                return {
                    'success': False,
                    'error': 'Invalid appointment date/time'
                }
            
            results = {
                'reminder_scheduled': False,
                'thank_you_scheduled': False,
                'messages': []
            }
            
            # Get template to check conditions
            template = self._get_message_template('24hr_reminder')
            if template and template.get('is_enabled', True):
                conditions = template.get('conditions', {})
                hours_in_advance = conditions.get('hours_in_advance', 30)
                
                # Check if appointment was booked far enough in advance
                booking_time = datetime.fromisoformat(appointment_data.get('created_at', datetime.now(self.timezone).isoformat()))
                if booking_time.tzinfo is None:
                    booking_time = self.timezone.localize(booking_time)
                hours_booked_in_advance = (appointment_datetime - booking_time).total_seconds() / 3600
                
                if hours_booked_in_advance >= hours_in_advance:
                    reminder_result = self._schedule_reminder_message(appointment_data, appointment_datetime)
                    results['reminder_scheduled'] = reminder_result['success']
                    results['messages'].append(reminder_result)
                    logger.info(f"📅 24-hour reminder scheduled for {appointment_data['name']}")
                else:
                    logger.info(f"⏰ Appointment booked {hours_booked_in_advance:.1f} hours in advance, less than {hours_in_advance} required - skipping reminder")
            else:
                logger.info("24hr reminder template disabled or not found, skipping")
            
            # Schedule thank you message (1 hour after appointment)
            thank_you_result = self._schedule_thank_you_message(appointment_data, appointment_datetime)
            results['thank_you_scheduled'] = thank_you_result['success']
            results['messages'].append(thank_you_result)
            logger.info(f"💫 Thank you message scheduled for {appointment_data['name']}")
            
            return {
                'success': True,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"❌ Error scheduling appointment messages: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _schedule_reminder_message(self, appointment_data: Dict, appointment_datetime: datetime) -> Dict:
        """Schedule 24-hour reminder message"""
        try:
            # Get template from database
            template = self._get_message_template('24hr_reminder')
            if not template or not template.get('is_enabled', True):
                logger.info("24hr reminder template disabled or not found, skipping")
                return {'success': True, 'skipped': True}
            
            # Get conditions
            conditions = template.get('conditions', {})
            hours_before_appointment = conditions.get('hours_before_appointment', 24)
            
            # Calculate reminder time
            reminder_time = appointment_datetime - timedelta(hours=hours_before_appointment)
            
            # Generate unique message ID
            message_id = f"reminder_{appointment_data['id']}_{int(reminder_time.timestamp())}"
            
            # Format the message using template
            message_content = self._format_message_with_template(template, appointment_data, appointment_datetime)
            
            # Store in database
            self._store_scheduled_message({
                'message_id': message_id,
                'appointment_id': appointment_data['id'],
                'customer_name': appointment_data['name'],
                'customer_phone': appointment_data['phone'],
                'message_type': '24hr_reminder',
                'scheduled_time': reminder_time.isoformat(),
                'message_content': message_content
            })
            
            # Schedule with APScheduler - NOW USES STANDALONE FUNCTION
            self.scheduler.add_job(
                func=send_scheduled_message_standalone,  # FIXED: Use standalone function
                trigger='date',
                run_date=reminder_time,
                args=[message_id],  # Only pass the message_id
                id=message_id,
                replace_existing=True
            )
            
            logger.info(f"📝 Reminder scheduled for {reminder_time}")
            
            return {
                'success': True,
                'message_id': message_id,
                'scheduled_time': reminder_time.isoformat(),
                'message_type': '24hr_reminder'
            }
            
        except Exception as e:
            logger.error(f"❌ Error scheduling reminder: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _schedule_thank_you_message(self, appointment_data: Dict, appointment_datetime: datetime) -> Dict:
        """Schedule thank you + review message"""
        try:
            # Get template from database
            template = self._get_message_template('thank_you_review')
            if not template or not template.get('is_enabled', True):
                logger.info("Thank you review template disabled or not found, skipping")
                return {'success': True, 'skipped': True}
            
            # Check conditions
            conditions = template.get('conditions', {})
            hours_after_appointment = conditions.get('hours_after_appointment', 1)
            
            # Calculate thank you time
            appointment_duration = appointment_data.get('duration', 60)
            thank_you_time = appointment_datetime + timedelta(minutes=appointment_duration + (hours_after_appointment * 60))
            
            # Generate unique message ID
            message_id = f"thankyou_{appointment_data['id']}_{int(thank_you_time.timestamp())}"
            
            # Format the message using template
            message_content = self._format_message_with_template(template, appointment_data, appointment_datetime)
            
            # Store in database
            self._store_scheduled_message({
                'message_id': message_id,
                'appointment_id': appointment_data['id'],
                'customer_name': appointment_data['name'],
                'customer_phone': appointment_data['phone'],
                'message_type': 'thank_you_review',
                'scheduled_time': thank_you_time.isoformat(),
                'message_content': message_content
            })
            
            # Schedule with APScheduler - NOW USES STANDALONE FUNCTION
            self.scheduler.add_job(
                func=send_scheduled_message_standalone,  # FIXED: Use standalone function
                trigger='date',
                run_date=thank_you_time,
                args=[message_id],  # Only pass the message_id
                id=message_id,
                replace_existing=True
            )
            
            logger.info(f"📝 Thank you message scheduled for {thank_you_time}")
            
            return {
                'success': True,
                'message_id': message_id,
                'scheduled_time': thank_you_time.isoformat(),
                'message_type': 'thank_you_review'
            }
            
        except Exception as e:
            logger.error(f"❌ Error scheduling thank you message: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _parse_appointment_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse appointment date and time into timezone-aware datetime"""
        try:
            dt_str = f"{date_str} {time_str}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            dt_eastern = self.timezone.localize(dt)
            return dt_eastern
        except Exception as e:
            logger.error(f"❌ Error parsing datetime: {str(e)}")
            return None
    
    def _check_deposit_status(self, appointment_data: Dict) -> bool:
        """Check if customer has paid their deposit"""
        return appointment_data.get('deposit_paid', False)
    
    def _get_short_service_name(self, service_name: str) -> str:
        """Convert service names to shorter versions for SMS"""
        service_mapping = {
            'Botox Injections': 'Botox',
            'HydraFacial': 'HydraFacial',
            'Laser Hair Removal': 'laser treatment',
            'Microneedling': 'microneedling'
        }
        return service_mapping.get(service_name, service_name)

    def _get_message_template(self, template_type: str) -> Optional[Dict]:
        """Get message template from database"""
        try:
            return self.db.get_message_template(template_type)
        except Exception as e:
            logger.error(f"❌ Error getting message template {template_type}: {str(e)}")
            return None

    def _format_message_with_template(self, template: Dict, appointment_data: Dict, appointment_datetime: datetime) -> str:
        """Format message using template and appointment data"""
        try:
            message_content = template['message_content']
            
            # Format time
            formatted_time = appointment_datetime.strftime('%I:%M %p').lstrip('0')
            formatted_date = appointment_datetime.strftime('%m/%d/%Y')
            
            # Get service name
            service_name = self._get_short_service_name(appointment_data.get('service', ''))
            
            # Replace template variables
            replacements = {
                '{name}': appointment_data.get('name', ''),
                '{service}': service_name,
                '{time}': formatted_time,
                '{date}': formatted_date,
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
    
    def _store_scheduled_message(self, message_data: Dict):
        """Store scheduled message in database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO scheduled_messages 
                (message_id, appointment_id, customer_name, customer_phone, 
                 message_type, scheduled_time, message_content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message_data['message_id'],
                message_data['appointment_id'],
                message_data['customer_name'],
                message_data['customer_phone'],
                message_data['message_type'],
                message_data['scheduled_time'],
                message_data['message_content'],
                datetime.now(self.timezone).isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Error storing scheduled message: {str(e)}")
    
    def cancel_appointment_messages(self, appointment_id: str) -> Dict:
        """Cancel all scheduled messages for an appointment"""
        try:
            # Get all pending messages for this appointment
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT message_id FROM scheduled_messages 
                WHERE appointment_id = ? AND status = 'pending'
            ''', (appointment_id,))
            
            message_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            cancelled_count = 0
            for message_id in message_ids:
                try:
                    # Remove from scheduler
                    self.scheduler.remove_job(message_id)
                    # Update database status
                    _update_message_status_in_db(message_id, 'cancelled', 'Appointment cancelled', self.db_file)
                    cancelled_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Could not cancel message {message_id}: {str(e)}")
            
            logger.info(f"🗑️ Cancelled {cancelled_count} scheduled messages for appointment {appointment_id}")
            
            return {
                'success': True,
                'cancelled_count': cancelled_count
            }
            
        except Exception as e:
            logger.error(f"❌ Error cancelling appointment messages: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_scheduled_messages(self, appointment_id: str = None) -> List[Dict]:
        """Get scheduled messages, optionally filtered by appointment"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            if appointment_id:
                cursor.execute('''
                    SELECT * FROM scheduled_messages 
                    WHERE appointment_id = ?
                    ORDER BY scheduled_time
                ''', (appointment_id,))
            else:
                cursor.execute('''
                    SELECT * FROM scheduled_messages 
                    ORDER BY scheduled_time DESC
                    LIMIT 100
                ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convert to list of dicts
            columns = ['id', 'message_id', 'appointment_id', 'customer_name', 
                      'customer_phone', 'message_type', 'scheduled_time', 'status',
                      'message_content', 'created_at', 'sent_at', 'error_message']
            
            messages = []
            for row in rows:
                message_dict = dict(zip(columns, row))
                messages.append(message_dict)
            
            return messages
            
        except Exception as e:
            logger.error(f"❌ Error getting scheduled messages: {str(e)}")
            return []
    
    def shutdown(self):
        """Gracefully shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("📴 Message scheduler shut down")
    
    def reschedule_appointment_messages(self, appointment_id: str, new_appointment_data: Dict) -> Dict:
        """
        Reschedule all messages for an appointment when the appointment time changes
        
        Args:
            appointment_id: The appointment ID to reschedule messages for
            new_appointment_data: Updated appointment data with new date/time
            
        Returns:
            Dict with rescheduling results
        """
        try:
            logger.info(f"🔄 Rescheduling messages for appointment {appointment_id}")
            
            # Get current appointment data from database
            if not self.db:
                return {
                    'success': False,
                    'error': 'Database service not available'
                }
            
            current_appointment = self.db.get_appointment_by_id(appointment_id)
            if not current_appointment:
                return {
                    'success': False,
                    'error': f'Appointment {appointment_id} not found in database'
                }
            
            # Check if appointment time actually changed
            old_date = current_appointment.get('appointment_date')
            old_time = current_appointment.get('appointment_time')
            new_date = new_appointment_data.get('appointment_date')
            new_time = new_appointment_data.get('appointment_time')
            
            if old_date == new_date and old_time == new_time:
                logger.info(f"⏰ No time change detected for appointment {appointment_id} - skipping reschedule")
                return {
                    'success': True,
                    'rescheduled': False,
                    'reason': 'No time change detected'
                }
            
            logger.info(f"⏰ Time change detected for appointment {appointment_id}: {old_date} {old_time} -> {new_date} {new_time}")
            
            # Cancel existing messages
            cancel_result = self.cancel_appointment_messages(appointment_id)
            if not cancel_result['success']:
                logger.warning(f"⚠️ Could not cancel existing messages: {cancel_result.get('error')}")
            
            # Schedule new messages with updated appointment data
            # Merge current appointment data with new data
            updated_appointment_data = {
                'id': appointment_id,
                'name': new_appointment_data.get('customer_name', current_appointment.get('customer_name')),
                'phone': new_appointment_data.get('customer_phone', current_appointment.get('customer_phone')),
                'date': new_date,
                'time': new_time,
                'service': new_appointment_data.get('service', current_appointment.get('service')),
                'service_name': new_appointment_data.get('service_name', current_appointment.get('service_name')),
                'specialist': new_appointment_data.get('specialist', current_appointment.get('specialist')),
                'price': new_appointment_data.get('price', current_appointment.get('price')),
                'duration': new_appointment_data.get('duration', current_appointment.get('duration')),
                'created_at': current_appointment.get('created_at')  # Keep original booking time
            }
            
            # Schedule new messages
            scheduling_result = self.schedule_appointment_messages(updated_appointment_data)
            
            if scheduling_result['success']:
                logger.info(f"✅ Successfully rescheduled messages for appointment {appointment_id}")
                return {
                    'success': True,
                    'rescheduled': True,
                    'cancelled_count': cancel_result.get('cancelled_count', 0),
                    'new_messages': scheduling_result['results']
                }
            else:
                logger.error(f"❌ Failed to reschedule messages for appointment {appointment_id}: {scheduling_result.get('error')}")
                return {
                    'success': False,
                    'error': f"Failed to schedule new messages: {scheduling_result.get('error')}"
                }
                
        except Exception as e:
            logger.error(f"❌ Error rescheduling appointment messages: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def reschedule_appointment_messages_with_old_data(self, appointment_id: str, new_appointment_data: Dict, old_date: str, old_time: str) -> Dict:
        """
        Reschedule all messages for an appointment when the appointment time changes
        This version accepts the old date/time to avoid database timing issues
        
        Args:
            appointment_id: The appointment ID to reschedule messages for
            new_appointment_data: Updated appointment data with new date/time
            old_date: The old appointment date
            old_time: The old appointment time
            
        Returns:
            Dict with rescheduling results
        """
        try:
            logger.info(f"🔄 Rescheduling messages for appointment {appointment_id}")
            
            # Get current appointment data from database
            if not self.db:
                return {
                    'success': False,
                    'error': 'Database service not available'
                }
            
            current_appointment = self.db.get_appointment_by_id(appointment_id)
            if not current_appointment:
                return {
                    'success': False,
                    'error': f'Appointment {appointment_id} not found in database'
                }
            
            # Check if appointment time actually changed using provided old data
            new_date = new_appointment_data.get('appointment_date')
            new_time = new_appointment_data.get('appointment_time')
            
            if old_date == new_date and old_time == new_time:
                logger.info(f"⏰ No time change detected for appointment {appointment_id} - skipping reschedule")
                return {
                    'success': True,
                    'rescheduled': False,
                    'reason': 'No time change detected'
                }
            
            logger.info(f"⏰ Time change detected for appointment {appointment_id}: {old_date} {old_time} -> {new_date} {new_time}")
            
            # Cancel existing messages
            cancel_result = self.cancel_appointment_messages(appointment_id)
            if not cancel_result['success']:
                logger.warning(f"⚠️ Could not cancel existing messages: {cancel_result.get('error')}")
            
            # Schedule new messages with updated appointment data
            # Merge current appointment data with new data
            updated_appointment_data = {
                'id': appointment_id,
                'name': new_appointment_data.get('customer_name', current_appointment.get('customer_name')),
                'phone': new_appointment_data.get('customer_phone', current_appointment.get('customer_phone')),
                'date': new_date,
                'time': new_time,
                'service': new_appointment_data.get('service', current_appointment.get('service')),
                'service_name': new_appointment_data.get('service_name', current_appointment.get('service_name')),
                'specialist': new_appointment_data.get('specialist', current_appointment.get('specialist')),
                'price': new_appointment_data.get('price', current_appointment.get('price')),
                'duration': new_appointment_data.get('duration', current_appointment.get('duration')),
                'created_at': current_appointment.get('created_at')  # Keep original booking time
            }
            
            # Schedule new messages
            scheduling_result = self.schedule_appointment_messages(updated_appointment_data)
            
            if scheduling_result['success']:
                logger.info(f"✅ Successfully rescheduled messages for appointment {appointment_id}")
                return {
                    'success': True,
                    'rescheduled': True,
                    'cancelled_count': cancel_result.get('cancelled_count', 0),
                    'new_messages': scheduling_result['results']
                }
            else:
                logger.error(f"❌ Failed to reschedule messages for appointment {appointment_id}: {scheduling_result.get('error')}")
                return {
                    'success': False,
                    'error': f"Failed to schedule new messages: {scheduling_result.get('error')}"
                }
                
        except Exception as e:
            logger.error(f"❌ Error rescheduling appointment messages: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_messages_needing_reschedule(self, appointment_id: str, new_appointment_datetime: datetime) -> List[Dict]:
        """
        Get messages that need rescheduling for an appointment
        
        Args:
            appointment_id: The appointment ID
            new_appointment_datetime: The new appointment datetime
            
        Returns:
            List of message dicts that need rescheduling
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Get all pending messages for this appointment
            cursor.execute('''
                SELECT * FROM scheduled_messages 
                WHERE appointment_id = ? AND status = 'pending'
                ORDER BY scheduled_time
            ''', (appointment_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            columns = ['id', 'message_id', 'appointment_id', 'customer_name', 
                      'customer_phone', 'message_type', 'scheduled_time', 'status',
                      'message_content', 'created_at', 'sent_at', 'error_message']
            
            messages_needing_reschedule = []
            now = datetime.now(self.timezone)
            
            for row in rows:
                message_dict = dict(zip(columns, row))
                scheduled_time = datetime.fromisoformat(message_dict['scheduled_time'])
                
                # Check if message is too close to being sent (within 1 hour)
                time_until_send = (scheduled_time - now).total_seconds() / 3600
                
                if time_until_send > 1:  # More than 1 hour until send
                    messages_needing_reschedule.append(message_dict)
                else:
                    logger.info(f"⏰ Message {message_dict['message_id']} is too close to send time ({time_until_send:.1f} hours) - skipping reschedule")
            
            return messages_needing_reschedule
            
        except Exception as e:
            logger.error(f"❌ Error getting messages needing reschedule: {str(e)}")
            return []