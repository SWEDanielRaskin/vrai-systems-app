import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from sms_service import SMSService

logger = logging.getLogger(__name__)

class CallTrackingService:
    """Service to track call states and handle missed call SMS notifications"""
    
    def __init__(self):
        self.active_calls: Dict[str, dict] = {}
        self.sms_service = SMSService()
        
    def start_call_tracking(self, call_control_id: str, caller_number: str, called_number: str, ring_time: datetime = None):
        """Start tracking a call for missed call detection, with optional ring timestamp"""
        logger.info(f"📞 Starting call tracking for {call_control_id} from {caller_number}")
        
        call_info = {
            'call_control_id': call_control_id,
            'caller_number': caller_number,
            'called_number': called_number,
            'start_time': ring_time or datetime.now(),  # Ring timestamp
            'connect_time': None,  # When the call is actually connected
            'answered': False,
            'sms_sent': False,
            'timeout_task': None
        }
        
        self.active_calls[call_control_id] = call_info
        return call_info

    def set_connect_time(self, call_control_id: str, connect_time: datetime = None):
        """Set the connect timestamp for a call"""
        if call_control_id in self.active_calls:
            self.active_calls[call_control_id]['connect_time'] = connect_time or datetime.now()
            logger.info(f"⏰ Set connect time for {call_control_id}: {self.active_calls[call_control_id]['connect_time']}")
    
    def mark_call_answered_sync(self, call_control_id: str):
        """Synchronous version of mark_call_answered for use in webhook handlers"""
        if call_control_id in self.active_calls:
            self.active_calls[call_control_id]['answered'] = True
            # Store connect time for duration calculation
            from datetime import datetime
            self.active_calls[call_control_id]['connect_time'] = datetime.now()
            logger.info(f"✅ Call {call_control_id} marked as answered")
    
    async def mark_call_answered(self, call_control_id: str):
        """Mark a call as answered (prevents missed call SMS)"""
        if call_control_id in self.active_calls:
            self.active_calls[call_control_id]['answered'] = True
            logger.info(f"✅ Call {call_control_id} marked as answered")
    
    def handle_call_ended_sync(self, call_control_id: str, reason: str = "unknown"):
        """Synchronous version of handle_call_ended for use in webhook handlers"""
        if call_control_id not in self.active_calls:
            logger.warning(f"Call {call_control_id} not found in tracking")
            return
        call_info = self.active_calls[call_control_id]
        from datetime import datetime
        now = datetime.now()
        # If call was answered, check duration
        if call_info['answered']:
            connect_time = call_info.get('connect_time')
            start_time = call_info.get('start_time')
            if connect_time and start_time:
                duration = (now - connect_time).total_seconds()
                logger.info(f"🐳 Call {call_control_id} duration after answer: {duration:.2f} seconds")
                if duration <= 8:
                    logger.info(f"📞 Call {call_control_id} was answered but duration <= 8s, treating as missed/voicemail")
                    call_info['answered'] = False  # Mark as not truly answered so SMS will be sent
                    # Send missed call SMS
                    import threading
                    import asyncio
                    def run_async_sms():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(self._send_missed_call_sms_after_delay(call_control_id))
                        finally:
                            loop.close()
                    sms_thread = threading.Thread(target=run_async_sms, daemon=True)
                    sms_thread.start()
                    call_info['timeout_task'] = sms_thread
                else:
                    logger.info(f"📞 Call {call_control_id} was answered and duration > 8s, no missed call SMS needed")
                    self.cleanup_call(call_control_id)
            else:
                # Fallback: if no connect_time, treat as answered, no SMS
                logger.info(f"📞 Call {call_control_id} was answered (no connect_time), no missed call SMS needed")
                self.cleanup_call(call_control_id)
            return
        # Call was not answered - start timer for missed call SMS
        logger.info(f"📞 Call {call_control_id} ended without being answered ({reason}) - starting SMS timer")
        import threading
        import asyncio
        def run_async_sms():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._send_missed_call_sms_after_delay(call_control_id))
            finally:
                loop.close()
        sms_thread = threading.Thread(target=run_async_sms, daemon=True)
        sms_thread.start()
        call_info['timeout_task'] = sms_thread

    async def handle_call_ended(self, call_control_id: str, reason: str = "unknown"):
        """Async version of handle_call_ended for compatibility"""
        if call_control_id not in self.active_calls:
            logger.warning(f"Call {call_control_id} not found in tracking")
            return
        
        call_info = self.active_calls[call_control_id]
        
        # If call was answered, no need for missed call SMS
        if call_info['answered']:
            logger.info(f"📞 Call {call_control_id} was answered - no missed call SMS needed")
            self.cleanup_call(call_control_id)
            return
        
        # Call was not answered - start timer for missed call SMS
        logger.info(f"📞 Call {call_control_id} ended without being answered ({reason}) - starting SMS timer")
        
        # Start 3-second timer before sending missed call SMS
        timeout_task = asyncio.create_task(self._send_missed_call_sms_after_delay(call_control_id))
        call_info['timeout_task'] = timeout_task
    
    async def _send_missed_call_sms_after_delay(self, call_control_id: str):
        """Send missed call SMS after 3-second delay"""
        try:
            logger.info(f"⏰ Starting 3-second delay for missed call SMS...")
            await asyncio.sleep(3)  # Wait 3 seconds
            logger.info(f"⏰ 3-second delay completed, checking call status...")
            
            if call_control_id not in self.active_calls:
                logger.warning(f"❌ Call {call_control_id} no longer in active calls")
                return
            
            call_info = self.active_calls[call_control_id]
            logger.info(f"📱 Found call info: {call_info}")
            
            # Double-check call wasn't answered in the meantime
            if call_info['answered']:
                logger.info(f"📞 Call was answered during delay - skipping SMS")
                return
                
            if call_info['sms_sent']:
                logger.info(f"📱 SMS already sent - skipping")
                return
            
            logger.info(f"📱 Proceeding to send missed call SMS...")
            
            # Extract info for SMS
            caller_number = call_info['caller_number']
            called_number = call_info['called_number']
            message = "Hi! We missed your call to Radiance MD Med Spa. I'm here to help! How can I assist you today?"
            
            logger.info(f"📱 Attempting SMS: {called_number} -> {caller_number}")
            logger.info(f"📱 Message: {message}")
            
            # Send SMS using the SMS service
            try:
                success = self.sms_service.send_sms(
                    to_number=caller_number,      # Send TO the caller
                    from_number=called_number,    # Send FROM our Telnyx number
                    message=message
                )
                
                if success:
                    call_info['sms_sent'] = True
                    logger.info(f"✅ Missed call SMS sent successfully to {caller_number}")
                else:
                    logger.error(f"❌ Failed to send missed call SMS to {caller_number}")
                    
            except Exception as sms_error:
                logger.error(f"❌ SMS sending error: {str(sms_error)}")
                import traceback
                logger.error(f"❌ SMS traceback: {traceback.format_exc()}")
            
            # Clean up the call tracking
            self.cleanup_call(call_control_id)
            logger.info(f"🧹 Call tracking cleaned up for {call_control_id}")
            
        except asyncio.CancelledError:
            logger.info(f"⏰ Missed call SMS timer cancelled for {call_control_id}")
        except Exception as e:
            logger.error(f"❌ Error in missed call SMS timer: {str(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
    
    async def _send_missed_call_sms(self, call_info: dict):
        """Send the actual missed call SMS"""
        caller_number = call_info['caller_number']
        called_number = call_info['called_number']  # This is our Telnyx number
        
        # Craft missed call message
        message = "Hi! We missed your call to Radiance MD Med Spa. I'm here to help! How can I assist you today?"
        
        logger.info(f"📱 Sending missed call SMS from {called_number} to {caller_number}")
        
        try:
            # Send SMS using our SMS service (note the parameter order)
            success = self.sms_service.send_sms(
                to_number=caller_number,      # Send TO the caller
                from_number=called_number,    # Send FROM our Telnyx number
                message=message
            )
            
            if success:
                call_info['sms_sent'] = True
                logger.info(f"✅ Missed call SMS sent successfully to {caller_number}")
            else:
                logger.error(f"❌ Failed to send missed call SMS to {caller_number}")
                
        except Exception as e:
            logger.error(f"❌ Error sending missed call SMS: {str(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        finally:
            # Clean up the call tracking
            self.cleanup_call(call_info['call_control_id'])
    
    def cleanup_call(self, call_control_id: str):
        """Clean up call tracking data"""
        if call_control_id in self.active_calls:
            call_info = self.active_calls[call_control_id]
            
            # Cancel any pending timeout task
            if call_info.get('timeout_task'):
                timeout_task = call_info['timeout_task']
                try:
                    # Handle both Thread and asyncio.Task objects
                    if hasattr(timeout_task, 'cancel'):
                        # It's an asyncio.Task
                        timeout_task.cancel()
                    elif hasattr(timeout_task, 'is_alive'):
                        # It's a Thread - we can't cancel it, but we can mark it for cleanup
                        logger.info(f"🧹 Thread task for call {call_control_id} will complete naturally")
                except Exception as e:
                    logger.warning(f"⚠️ Error cleaning up timeout task: {str(e)}")
            
            # Remove from tracking
            del self.active_calls[call_control_id]
            logger.info(f"🧹 Cleaned up tracking for call {call_control_id}")
    
    def get_call_info(self, call_control_id: str) -> Optional[dict]:
        """Get call information"""
        return self.active_calls.get(call_control_id)
    
    def get_active_calls_count(self) -> int:
        """Get number of currently tracked calls"""
        return len(self.active_calls)