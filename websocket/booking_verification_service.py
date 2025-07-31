# booking_verification_service.py
import re
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sms_service import SMSService

logger = logging.getLogger(__name__)

class BookingVerificationService:
    """
    Service to prevent false booking confirmations by analyzing AI responses
    and ensuring actual booking functions were called.
    """
    
    def __init__(self, database_service=None):
        self.db = database_service
        self.sms_service = SMSService()
        
        # Booking confirmation patterns that indicate a booking was made
        self.booking_confirmation_patterns = [
            r'\b(?:i\'ve|i have|we\'ve|we have)\s+(?:booked|confirmed|scheduled|made)\s+(?:your|the)\s+appointment\b',
            r'\b(?:your|the)\s+appointment\s+(?:has been|is)\s+(?:booked|confirmed|scheduled)\b',
            r'\b(?:appointment|booking)\s+(?:is|has been)\s+(?:confirmed|booked|scheduled)\b',
            r'\b(?:successfully|perfectly)\s+(?:booked|confirmed|scheduled)\b',
            r'\b(?:confirmation|confirmation text|confirmation sms)\s+(?:sent|will be sent)\b',
            r'\b(?:you\'ll receive|you will receive)\s+(?:a confirmation|confirmation text)\b',
            r'\b(?:appointment\s+)?(?:booked|confirmed|scheduled)\s+(?:successfully|perfectly)\b',
            r'\b(?:perfect|great|excellent)\s*!?\s*(?:i\'ve|i have|we\'ve|we have)\s+(?:booked|confirmed)\b',
            r'\b(?:all set|all done|that\'s it)\s*!?\s*(?:your appointment|appointment)\s+(?:is|has been)\s+(?:booked|confirmed)\b'
        ]
        
        # False positive patterns (phrases that might trigger but don't indicate actual booking)
        self.false_positive_patterns = [
            r'\b(?:let me|i\'ll|i will)\s+(?:check|verify|confirm)\s+(?:availability|if)\b',
            r'\b(?:checking|verifying|confirming)\s+(?:availability|if)\b',
            r'\b(?:i can|i\'ll be able to)\s+(?:book|schedule)\b',
            r'\b(?:would you like me to|should i)\s+(?:book|schedule)\b',
            r'\b(?:i\'m|i am)\s+(?:going to|about to)\s+(?:book|schedule)\b',
            r'\b(?:once|after)\s+(?:i|we)\s+(?:book|schedule)\b',
            r'\b(?:when|if)\s+(?:i|we)\s+(?:book|schedule)\b',
            r'\b(?:i\'ll|i will)\s+(?:book|schedule)\s+(?:it|your appointment)\b',
            r'\b(?:let me|i\'ll|i will)\s+(?:book|schedule)\s+(?:that|it|your appointment)\b'
        ]
        
        # Tracking for each conversation
        self.booking_states = {}  # user_id -> booking state
        self.function_call_logs = {}  # user_id -> list of function calls
        self.response_logs = {}  # user_id -> list of AI responses
        
    def log_function_call(self, user_id: str, function_name: str, arguments: Dict, result: Dict):
        """Log a function call for verification purposes"""
        if user_id not in self.function_call_logs:
            self.function_call_logs[user_id] = []
        
        self.function_call_logs[user_id].append({
            'timestamp': datetime.now().isoformat(),
            'function_name': function_name,
            'arguments': arguments,
            'result': result
        })
        
        # Keep only last 20 function calls per user
        if len(self.function_call_logs[user_id]) > 20:
            self.function_call_logs[user_id] = self.function_call_logs[user_id][-20:]
        
        logger.info(f"📝 Logged function call for {user_id}: {function_name}")
    
    def log_ai_response(self, user_id: str, response_text: str):
        """Log an AI response for verification purposes"""
        if user_id not in self.response_logs:
            self.response_logs[user_id] = []
        
        self.response_logs[user_id].append({
            'timestamp': datetime.now().isoformat(),
            'response': response_text
        })
        
        # Keep only last 10 responses per user
        if len(self.response_logs[user_id]) > 10:
            self.response_logs[user_id] = self.response_logs[user_id][-10:]
        
        logger.info(f"📝 Logged AI response for {user_id}: {response_text[:50]}...")
    
    def detect_booking_confirmation(self, response_text: str) -> bool:
        """
        Detect if AI response indicates a booking was made
        Returns True if response suggests booking was completed
        """
        response_lower = response_text.lower()
        
        # Check for false positives first
        for pattern in self.false_positive_patterns:
            if re.search(pattern, response_lower):
                logger.info(f"🚫 False positive detected: '{pattern}' in response")
                return False
        
        # Check for actual booking confirmations
        for pattern in self.booking_confirmation_patterns:
            if re.search(pattern, response_lower):
                logger.info(f"✅ Booking confirmation detected: '{pattern}' in response")
                return True
        
        return False
    
    def verify_booking_function_called(self, user_id: str, time_window_minutes: int = 5) -> bool:
        """
        Verify that a booking function was actually called recently
        Returns True if book_appointment function was called within time window
        """
        if user_id not in self.function_call_logs:
            return False
        
        recent_calls = []
        cutoff_time = datetime.now().timestamp() - (time_window_minutes * 60)
        
        for call in self.function_call_logs[user_id]:
            try:
                call_time = datetime.fromisoformat(call['timestamp']).timestamp()
                if call_time >= cutoff_time:
                    recent_calls.append(call)
            except Exception as e:
                logger.warning(f"Error parsing call timestamp: {e}")
        
        # Check if any recent calls were book_appointment
        booking_calls = [call for call in recent_calls if call['function_name'] == 'book_appointment']
        
        if booking_calls:
            # Check if any booking calls were successful
            successful_bookings = [call for call in booking_calls if call['result'].get('success', False)]
            if successful_bookings:
                logger.info(f"✅ Verified successful booking function call for {user_id}")
                return True
            else:
                logger.warning(f"⚠️ Booking function called but failed for {user_id}")
                return False
        
        logger.warning(f"❌ No booking function calls found for {user_id}")
        return False
    
    def check_for_false_booking_confirmation(self, user_id: str, response_text: str) -> Tuple[bool, str]:
        """
        Check if AI response indicates booking but no function was called
        Returns (is_false_confirmation, alert_message)
        """
        # Check if response suggests booking was made
        if not self.detect_booking_confirmation(response_text):
            return False, ""
        
        # Check if booking function was actually called
        if not self.verify_booking_function_called(user_id):
            logger.error(f"🚨 FALSE BOOKING CONFIRMATION DETECTED for {user_id}")
            logger.error(f"🚨 Response: {response_text}")
            
            alert_message = (
                f"🚨 CRITICAL: False booking confirmation detected!\n"
                f"User: {user_id}\n"
                f"Response: {response_text}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Action required: Contact customer immediately to clarify booking status."
            )
            
            return True, alert_message
        
        return False, ""
    
    def send_false_booking_alert(self, user_id: str, response_text: str, alert_message: str):
        """Send alert about false booking confirmation"""
        try:
            # Send SMS alert to management
            management_phone = "+13132044895"  # Business number for alerts
            
            alert_sms = (
                f"🚨 FALSE BOOKING ALERT\n"
                f"Customer: {user_id}\n"
                f"AI said: {response_text[:100]}...\n"
                f"Action: Contact customer immediately!"
            )
            
            self.sms_service.send_sms(
                from_number="+18773900002",
                to_number=management_phone,
                message=alert_sms
            )
            
            # Log to database if available
            if self.db:
                self.db.create_notification(
                    'critical',
                    'False Booking Confirmation Detected',
                    alert_message,
                    user_id,
                    'AI System',
                    'sms',
                    f"false_booking_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
            
            logger.error(f"🚨 False booking alert sent for {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error sending false booking alert: {str(e)}")
    
    def analyze_conversation_for_booking_issues(self, user_id: str) -> Dict:
        """
        Analyze entire conversation for booking-related issues
        Returns analysis results
        """
        if user_id not in self.response_logs:
            return {'issues_found': False}
        
        issues = []
        
        # Check each response for false confirmations
        for i, response_log in enumerate(self.response_logs[user_id]):
            response_text = response_log['response']
            timestamp = response_log['timestamp']
            
            # Check if this response indicated booking but no function was called
            is_false, alert_msg = self.check_for_false_booking_confirmation(user_id, response_text)
            
            if is_false:
                issues.append({
                    'type': 'false_booking_confirmation',
                    'timestamp': timestamp,
                    'response': response_text,
                    'alert_message': alert_msg
                })
        
        return {
            'issues_found': len(issues) > 0,
            'issues': issues,
            'total_responses': len(self.response_logs[user_id]),
            'total_function_calls': len(self.function_call_logs.get(user_id, []))
        }
    
    def cleanup_user_data(self, user_id: str):
        """Clean up user data after conversation ends"""
        if user_id in self.booking_states:
            del self.booking_states[user_id]
        if user_id in self.function_call_logs:
            del self.function_call_logs[user_id]
        if user_id in self.response_logs:
            del self.response_logs[user_id]
        
        logger.info(f"🧹 Cleaned up data for user {user_id}")
    
    def get_verification_stats(self) -> Dict:
        """Get verification service statistics"""
        total_users = len(set(list(self.function_call_logs.keys()) + list(self.response_logs.keys())))
        total_function_calls = sum(len(calls) for calls in self.function_call_logs.values())
        total_responses = sum(len(responses) for responses in self.response_logs.values())
        
        return {
            'total_users_tracked': total_users,
            'total_function_calls': total_function_calls,
            'total_responses': total_responses,
            'active_conversations': len(self.booking_states)
        } 