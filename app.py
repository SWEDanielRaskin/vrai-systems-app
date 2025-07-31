#MYRIAD PART 1 YUG

from dotenv import load_dotenv
# Load environment variables
load_dotenv()

from flask import Flask, request, Response, stream_with_context, jsonify
from flask_cors import CORS
import os
import json
import time
import logging
import asyncio
from datetime import datetime
import pytz
from sms_service import SMSService
from ai_service import AIReceptionist
from call_tracking_service import CallTrackingService
from message_scheduler import MessageScheduler
from database_service import DatabaseService
from appointment_service import AppointmentService
from ai_summarizer import AISummarizer
from api_routes import api_bp
from apscheduler.schedulers.background import BackgroundScheduler
import requests as pyrequests
from werkzeug.utils import secure_filename
import pandas as pd
from knowledge_base_service import KnowledgeBaseService
import threading
import queue
from collections import deque

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Enable CORS for all routes
CORS(app, origins=[
    "http://localhost:3000",
    "https://vrai-systems-app-production.up.railway.app",
    "https://your-netlify-app.netlify.app",  # Replace with your actual Netlify URL
    "https://vrai-systems.netlify.app"  # Example domain
], supports_credentials=True, methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'])

# Register API blueprint
app.register_blueprint(api_bp)

# --- SSE Implementation ---
clients = []  # List of queues for each connected client

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 15

# Track last known mode for mode_changed events
last_known_mode = None

# --- Message Deduplication Cache ---
# Store the last 300 processed message IDs to prevent duplicate processing
message_deduplicator = deque(maxlen=300)

def event_stream(client_queue):
    try:
        while True:
            event = client_queue.get()
            yield f"data: {event}\n\n"
    except GeneratorExit:
        pass  # Client disconnected

@app.route('/events')
def sse_events():
    # Enforce a hard cap of 5 clients
    while len(clients) >= 5:
        old_client = clients.pop(0)
        logging.info(f"[SSE] Hard cap reached. Removing oldest client before adding new one. Total clients after removal: {len(clients)}")
    
    client_queue = queue.Queue(maxsize=5)
    clients.append(client_queue)
    logging.info(f"[SSE] Client connected. Total clients: {len(clients)}")
    
    def cleanup():
        if client_queue in clients:
            clients.remove(client_queue)
            logging.info(f"[SSE] Client disconnected. Total clients: {len(clients)}")
    
    @stream_with_context
    def generate():
        try:
            yield from event_stream(client_queue)
        finally:
            cleanup()
    
    headers = {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive'}
    return Response(generate(), headers=headers)

# Heartbeat thread to send keep-alive to all clients
def heartbeat():
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        to_remove = []
        for client in clients[:]:
            try:
                client.put(":heartbeat", block=False)
            except queue.Full:
                to_remove.append(client)
                logging.info(f"[SSE] Heartbeat: Client queue full, removing client. Total clients before removal: {len(clients)}")
            except Exception:
                to_remove.append(client)
                logging.info(f"[SSE] Heartbeat: Exception, removing client. Total clients before removal: {len(clients)}")
        
        if to_remove:
            for client in to_remove:
                if client in clients:
                    clients.remove(client)
            logging.info(f"[SSE] Heartbeat: Removed {len(to_remove)} disconnected client(s). Total clients: {len(clients)}")

heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
heartbeat_thread.start()

def broadcast_event(event_data):
    logging.info(f"[SSE] Broadcasting event to {len(clients)} clients: {event_data}")
    for client in clients[:]:
        try:
            client.put(event_data)
        except Exception:
            pass  # Ignore errors

# Move DatabaseService import here to avoid circular import
from database_service import DatabaseService

# Initialize services
sms_service = SMSService()
db = DatabaseService(broadcast_event=broadcast_event)
ai_receptionist = AIReceptionist(database_service=db)  # FIXED: Pass database service
call_tracker = CallTrackingService()
message_scheduler = MessageScheduler()
ai_summarizer = AISummarizer(database_service=db)  # NEW: Initialize AI summarizer with database service

# Initialize appointment service with database
appointment_service = AppointmentService(database_service=db)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize knowledge base service
kb_service = KnowledgeBaseService(database_service=db)

# Utility to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_business_hours_status():
    """
    Determine if we're in business hours considering the database override
    Returns: True for business hours, False for after hours
    """
    # Check for database override first
    override = db.get_setting('business_hours_override')
    
    if override == 'business':
        logger.info("🧪 Database override: BUSINESS HOURS mode")
        return True
    elif override == 'after_hours':
        logger.info("🧪 Database override: AFTER HOURS mode")
        return False
    else:
        # Use actual business hours from database settings
        ai_hours_json = db.get_setting('ai_operating_hours')
        if ai_hours_json:
            try:
                ai_hours = json.loads(ai_hours_json)
            except json.JSONDecodeError:
                # Fallback to default hours
                ai_hours = {
                    'Monday': {'start': '09:00', 'end': '16:00'},
                    'Tuesday': {'start': '09:00', 'end': '16:00'},
                    'Wednesday': {'start': '09:00', 'end': '16:00'},
                    'Thursday': {'start': '09:00', 'end': '16:00'},
                    'Friday': {'start': '09:00', 'end': '16:00'},
                    'Saturday': {'start': '09:00', 'end': '15:00'},
                    'Sunday': {'start': None, 'end': None}
                }
        else:
            # Default hours if not set
            ai_hours = {
                'Monday': {'start': '09:00', 'end': '16:00'},
                'Tuesday': {'start': '09:00', 'end': '16:00'},
                'Wednesday': {'start': '09:00', 'end': '16:00'},
                'Thursday': {'start': '09:00', 'end': '16:00'},
                'Friday': {'start': '09:00', 'end': '16:00'},
                'Saturday': {'start': '09:00', 'end': '15:00'},
                'Sunday': {'start': None, 'end': None}
            }
        
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')
        
        if current_day == 'Sunday':
            logger.info("📅 Actual time: AFTER HOURS (Sunday)")
            return False
            
        hours = ai_hours.get(current_day)
        if not hours or not hours['start'] or not hours['end']:
            logger.info("📅 Actual time: AFTER HOURS (no hours defined)")
            return False
            
        is_business = hours['start'] <= current_time <= hours['end']
        status = "BUSINESS HOURS" if is_business else "AFTER HOURS"
        logger.info(f"📅 Actual time: {status} ({current_day} {current_time})")
        return is_business

@app.route('/inbound', methods=['POST'])
def inbound_call():
    """Handle all Telnyx Call Control events for inbound calls"""
    try:
        logger.info(f"📞 [TELNYX EVENT] Received call control event")
        logger.info(f"📞 Incoming Call Control event headers: {dict(request.headers)}")
        logger.info(f"📞 Incoming Call Control event data: {request.get_data(as_text=True)}")
        
        data = request.get_json(force=True)
        event_type = data.get('data', {}).get('event_type')
        payload = data.get('data', {}).get('payload', {})
        call_control_id = payload.get('call_control_id')
        caller_number = payload.get('from')
        called_number = payload.get('to')

        if not call_control_id:
            logger.error("❌ No call_control_id found in event")
            return Response(status=400)

        logger.info(f"📞 Processing event: {event_type} for call {call_control_id}")

        # Handle different event types
        if event_type == 'call.initiated':
            # ONLY handle inbound calls for logging and answering - skip outbound calls created by transfers
            if payload.get('direction') == 'outgoing':
                logger.info(f"📞 Skipping outbound call {call_control_id} (created by transfer)")
                return Response(status=200)
            
            # Log call in DB and start tracking (only for inbound calls)
            is_business_hours = get_business_hours_status()
            db.start_call_logging(call_control_id, caller_number, called_number, is_business_hours)
            
            if is_business_hours:
                # BUSINESS HOURS: Answer first, then transfer to front desk
                logger.info(f"🏢 [BUSINESS HOURS] Call {call_control_id} - answering to transfer to front desk")
                call_tracker.start_call_tracking(call_control_id, caller_number, called_number)
                
                # Answer the call immediately
                answer_call(call_control_id)
                
            else:
                # AFTER HOURS: Answer and prepare for AI
                logger.info(f"🌙 [AFTER HOURS] Call {call_control_id} - answering for AI receptionist")
                call_tracker.start_call_tracking(call_control_id, caller_number, called_number)
                
                # Answer the call immediately  
                answer_call(call_control_id)

        elif event_type == 'call.answered':
            # Call has been answered, now determine next action
            is_business_hours = get_business_hours_status()
            
            # FIXED: More robust filtering of outbound call.answered events
            front_desk_number = os.getenv('FORWARD_NUMBER', '+13132044895')
            business_number = os.getenv('TELNYX_NUMBER', '+18773900002')
            
            # Skip if this is an outbound call leg (transfer-created call)
            if (payload.get('direction') == 'outgoing' or 
                called_number == front_desk_number or  # Call TO front desk
                caller_number == business_number):     # Call FROM business number
                logger.info(f"📞 Skipping outbound/transfer call.answered event for {call_control_id}")
                logger.info(f"📞 Details: from={caller_number}, to={called_number}, direction={payload.get('direction')}")
                return Response(status=200)
            
            if is_business_hours:
                # BUSINESS HOURS: Transfer to front desk (only for original inbound calls)
                logger.info(f"🏢 [BUSINESS HOURS] Original call {call_control_id} answered - transferring to front desk")
                transfer_to_front_desk(call_control_id, called_number, caller_number)
            else:
                # AFTER HOURS: Start AI streaming
                logger.info(f"🌙 [AFTER HOURS] Call {call_control_id} answered - starting AI streaming")
                start_ai_streaming(call_control_id)

        elif event_type == 'call.bridged':
            # Call successfully transferred to front desk
            logger.info(f"🏢 [TRANSFERRED] Call {call_control_id} successfully transferred to front desk")
            logger.info(f"🏢 Call details: from={caller_number}, to={called_number}, direction={payload.get('direction')}")
            
            # Mark the ORIGINAL call as answered to prevent missed call SMS
            # We need to find the original call ID and mark it as answered
            original_call_id = find_original_call_id(call_control_id, payload)
            logger.info(f"🏢 Original call ID found: {original_call_id}")
            
            if original_call_id:
                call_tracker.mark_call_answered_sync(original_call_id)
                logger.info(f"✅ Marked original call {original_call_id} as answered")
                
                # Mark as transferred in database for business hours calls
                is_business_hours = get_business_hours_status()
                if is_business_hours:
                    logger.info(f"🏢 Business hours detected - marking call {original_call_id} as transferred")
                    success = db.end_call_logging(original_call_id, [], status='transferred')
                    if success:
                        logger.info(f"🏢 Successfully marked call {original_call_id} as transferred to front desk")
                    else:
                        logger.error(f"❌ Failed to mark call {original_call_id} as transferred")
                else:
                    logger.info(f"🌙 After hours detected - not marking as transferred")
            else:
                logger.warning(f"⚠️ No original call ID found for {call_control_id}")

        elif event_type == 'call.bridge.failed':
            # Transfer failed - treat as missed call
            logger.warning(f"❌ [TRANSFER FAILED] Call {call_control_id} transfer failed")
            call_tracker.handle_call_ended_sync(call_control_id, 'transfer_failed')
            db.end_call_logging(call_control_id, [], status='missed')

        elif event_type in ['call.hangup', 'call.ended']:
            # Handle call completion - only for original inbound calls
            front_desk_number = os.getenv('FORWARD_NUMBER', '+13132044895')
            
            # Skip processing hangup events for transfer legs to front desk
            if called_number == front_desk_number:
                logger.info(f"📞 Skipping hangup event for transfer leg {call_control_id}")
                return Response(status=200)
            
            is_business_hours = get_business_hours_status()
            
            if is_business_hours:
                # For business hours, check if call was already marked as transferred
                logger.info(f"📞 [BUSINESS HOURS] Original call {call_control_id} ended")
                
                # Check current status in database
                current_call = db.get_call_by_id(call_control_id)
                if current_call and current_call.get('status') == 'transferred':
                    logger.info(f"🏢 Call {call_control_id} already marked as transferred - skipping status update")
                    call_tracker.handle_call_ended_sync(call_control_id, event_type)
                else:
                    # Handle as normal business hours call
                    call_info = call_tracker.get_call_info(call_control_id)
                    if call_info:
                        call_tracker.handle_call_ended_sync(call_control_id, event_type)
                        # After running the duration logic, check if the call was truly answered (duration > 8s)
                        # If call_info['answered'] is still True, it was a real call
                        db.end_call_logging(call_control_id, [], status='completed' if call_info.get('answered') else 'missed')
                    else:
                        logger.info(f"❌ Call {call_control_id} not found in tracking - treating as missed")
                        db.end_call_logging(call_control_id, [], status='missed')
            else:
                # For after hours, mark as completed (handled by AI)
                logger.info(f"🌙 [AFTER HOURS] Call {call_control_id} ended")
                call_tracker.mark_call_answered_sync(call_control_id)
                db.end_call_logging(call_control_id, [], status='completed')

        # Acknowledge all events
        return Response(status=200)

    except Exception as e:
        logger.error(f"❌ Error in inbound_call: {str(e)}")
        return Response(status=500)


def find_original_call_id(current_call_id, payload):
    """Find the original inbound call ID from transfer events"""
    try:
        # For call.bridged events, we need to identify which is the original call
        # The original call will have direction='incoming' in the session
        
        # If this is a call TO the front desk, it's likely a transfer leg
        front_desk_number = os.getenv('FORWARD_NUMBER', '+13132044895')
        business_number = os.getenv('TELNYX_NUMBER', '+18773900002')
        
        # Check if this is a transfer leg (call TO front desk)
        if payload.get('to') == front_desk_number:
            logger.info(f"🏢 Transfer leg detected: {current_call_id} (to front desk)")
            # This is a transfer leg, we need to find the original call
            # For now, we'll use the session ID to find the original call
            session_id = payload.get('call_session_id')
            if session_id:
                # Query database for calls with same session ID but different direction
                # For now, return None and let the system handle it
                logger.info(f"🏢 Transfer leg session ID: {session_id}")
                return None
        
        # If this is the original call (direction='incoming' or to business number)
        if (payload.get('direction') == 'incoming' or 
            payload.get('to') == business_number):
            logger.info(f"🏢 Original call detected: {current_call_id}")
            return current_call_id
        
        # Default case
        logger.info(f"🏢 Unknown call type: {current_call_id} (direction: {payload.get('direction')}, to: {payload.get('to')})")
        return current_call_id
        
    except Exception as e:
        logger.error(f"❌ Error finding original call ID: {str(e)}")
        return current_call_id

def transfer_to_front_desk(call_control_id, original_called_number, original_caller_number):
    """Transfer call to front desk number using Call Transfer API"""
    try:
        import requests
        
        front_desk_number = os.getenv('FORWARD_NUMBER', '+13132044895')
        
        # Use the transfer action - this is the correct API for call forwarding
        transfer_url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transfer"
        headers = {
            "Authorization": f"Bearer {os.getenv('API_KEY')}",
            "Content-Type": "application/json"
        }
        
        # FIXED: Transfer data should show the original caller as the "from" number
        transfer_data = {
            "to": front_desk_number,
            "from": original_caller_number,  # FIXED: Use original caller, not business number
            "timeout_secs": 30,  # Ring for 30 seconds before timing out
            "answering_machine_detection": "disabled"  # Disable AMD for faster transfer
        }
        
        logger.info(f"🏢 Transferring call {call_control_id} to {front_desk_number}")
        logger.info(f"🏢 Transfer request data: {transfer_data}")
        logger.info(f"🏢 Customer {original_caller_number} → Front Desk {front_desk_number}")
        
        transfer_response = requests.post(transfer_url, headers=headers, json=transfer_data)
        
        if transfer_response.status_code == 200:
            logger.info(f"✅ Transfer request successful for call {call_control_id}")
            logger.info(f"✅ Transfer response: {transfer_response.text}")
        else:
            logger.error(f"❌ Transfer failed for call {call_control_id}: {transfer_response.status_code}")
            logger.error(f"❌ Transfer error response: {transfer_response.text}")
            # Mark as missed call if transfer fails
            call_tracker.handle_call_ended_sync(call_control_id, 'transfer_failed')
            
    except Exception as e:
        logger.error(f"❌ Error transferring call {call_control_id}: {str(e)}")
        # Mark as missed call if transfer fails
        call_tracker.handle_call_ended_sync(call_control_id, 'transfer_failed')

def answer_call(call_control_id):
    """Answer an incoming call"""
    try:
        import requests
        
        answer_url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/answer"
        headers = {
            "Authorization": f"Bearer {os.getenv('API_KEY')}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"📞 Answering call {call_control_id}")
        answer_response = requests.post(answer_url, headers=headers)
        
        if answer_response.status_code == 200:
            logger.info(f"✅ Call {call_control_id} answered successfully")
        else:
            logger.error(f"❌ Failed to answer call {call_control_id}: {answer_response.status_code}, {answer_response.text}")
            
    except Exception as e:
        logger.error(f"❌ Error answering call {call_control_id}: {str(e)}")


def bridge_to_front_desk(call_control_id, original_called_number):
    """Bridge call to front desk number"""
    try:
        import requests
        
        front_desk_number = os.getenv('FORWARD_NUMBER', '+13132044895')
        
        # Use the bridge action with proper parameters
        bridge_url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/bridge"
        headers = {
            "Authorization": f"Bearer {os.getenv('API_KEY')}",
            "Content-Type": "application/json"
        }
        
        # Bridge data - FIXED: Include call_control_id in the request body
        bridge_data = {
            "call_control_id": call_control_id,  # This was missing!
            "to": front_desk_number,
            "from": original_called_number,  # Use the original business number as caller ID
            "timeout_secs": 30,  # Ring for 30 seconds
            "time_limit_secs": 7200,  # 2 hour call limit
        }
        
        logger.info(f"🏢 Bridging call {call_control_id} to {front_desk_number}")
        logger.info(f"🏢 Bridge request data: {bridge_data}")
        
        bridge_response = requests.post(bridge_url, headers=headers, json=bridge_data)
        
        if bridge_response.status_code == 200:
            logger.info(f"✅ Bridge request successful for call {call_control_id}")
            logger.info(f"✅ Bridge response: {bridge_response.text}")
        else:
            logger.error(f"❌ Bridge failed for call {call_control_id}: {bridge_response.status_code}")
            logger.error(f"❌ Bridge error response: {bridge_response.text}")
            # Mark as missed call if bridge fails
            call_tracker.handle_call_ended_sync(call_control_id, 'bridge_failed')
            
    except Exception as e:
        logger.error(f"❌ Error bridging call {call_control_id}: {str(e)}")
        # Mark as missed call if bridge fails
        call_tracker.handle_call_ended_sync(call_control_id, 'bridge_failed')


def start_ai_streaming(call_control_id):
    """Start AI streaming for after-hours calls"""
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {os.getenv('API_KEY')}",
            "Content-Type": "application/json"
        }
        
        # Get the WebSocket URL from environment or use the one from your config
        websocket_stream_url = "wss://16d3c9815674.ngrok-free.app"  # Update this to your actual ngrok URL
        
        streaming_data = {
            "stream_url": websocket_stream_url,
            "stream_track": "inbound_track",
            "stream_bidirectional_mode": "rtp",
            "stream_bidirectional_codec": "PCMU"
        }
        
        streaming_url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/streaming_start"
        
        logger.info(f"🤖 Starting AI streaming for call {call_control_id}")
        logger.info(f"🤖 Streaming to: {websocket_stream_url}")
        
        streaming_response = requests.post(streaming_url, headers=headers, json=streaming_data)
        
        if streaming_response.status_code == 200:
            logger.info(f"✅ AI streaming started for call {call_control_id}")
        else:
            logger.error(f"❌ Failed to start streaming for call {call_control_id}: {streaming_response.status_code}, {streaming_response.text}")
            
    except Exception as e:
        logger.error(f"❌ Error starting AI streaming for call {call_control_id}: {str(e)}")

@app.route('/message', methods=['POST'])
def incoming_message():
    """Handle incoming SMS messages with enhanced notification analysis"""
    try:
        # Log the raw request
        logger.info(f"📱 SMS received. Headers: {dict(request.headers)}")
        logger.info(f"📱 SMS data: {request.get_data(as_text=True)}")
        
        # Parse the JSON payload
        data = request.get_json(force=True)
        
        # Extract message details from the Telnyx payload structure
        payload = data.get('data', {}).get('payload', {})
        
        # NEW: Message deduplication check
        message_id = payload.get('id')
        if message_id:
            if message_id in message_deduplicator:
                logger.info(f"🔄 Skipping duplicate message: {message_id}")
                return Response(status=200)  # Acknowledge but don't process
            else:
                # Add to cache and continue processing
                message_deduplicator.append(message_id)
                logger.info(f"✅ New message processed: {message_id} (Cache size: {len(message_deduplicator)})")
        else:
            logger.warning(f"⚠️ No message ID found in payload, proceeding without deduplication")
        
        # Only process inbound messages
        if payload.get('direction') != 'inbound':
            logger.info(f"📱 Skipping outbound message: {payload.get('direction')}")
            return Response(status=200)  # Acknowledge but don't process
        
        # Debug the payload structure
        logger.info(f"📱 Debug - Full payload direction: {payload.get('direction')}")
        logger.info(f"📱 Debug - From object: {payload.get('from')}")
        logger.info(f"📱 Debug - To object: {payload.get('to')}")
        
        from_number = payload.get('from', {}).get('phone_number')
        to_number = payload.get('to')[0].get('phone_number') if payload.get('to') else None
        message_text = payload.get('text')
        
        if not all([from_number, to_number, message_text]):
            logger.error(f"❌ Missing required SMS fields: from={from_number}, to={to_number}, text={message_text}")
            return Response(status=400)
        
        # Format phone numbers
        from_number = format_phone_number(from_number)
        to_number = format_phone_number(to_number)
        
        logger.info(f"📱 SMS conversation - Customer: {from_number} → Business: {to_number}")
        logger.info(f"📱 Message: {message_text}")
        
        # Use AI service for SMS response - UPDATED to handle name extraction
        response_data = ai_receptionist.get_ai_response(from_number, message_text)
        
        # Handle both old and new return formats
        if isinstance(response_data, tuple):
            response, extracted_name = response_data
        else:
            response = response_data
            extracted_name = None
        
        # NEW: Check if this is an appointment confirmation message that should trigger interest notification rescission
        if is_appointment_confirmation_message(message_text, from_number, to_number):
            logger.info(f"🎯 Detected appointment confirmation - checking for interest notifications to rescind")
            # Get current timestamp for the rescission
            current_timestamp = datetime.now().isoformat()
            handle_interest_notification_rescission(to_number, current_timestamp)
        
        # Log message exchange to database with extracted name
        db.log_message_exchange(from_number, to_number, message_text, response, extracted_name)
        # Broadcast SSE event to all clients
        broadcast_event('{"type": "new_message", "phone": "%s"}' % from_number)
        
        # Get updated conversation for summary and notification analysis
        conversation = db.get_conversation_by_id(from_number)
        if conversation and conversation.get('messages'):
            try:
                messages = json.loads(conversation['messages'])
                message_count = len(messages)
                last_summary_count = conversation.get('last_summary_message_count', 0)
                
                # UPDATED: Generate/update summary every 4 messages starting from message 4
                should_generate_summary = (
                    message_count >= 4 and 
                    (message_count - last_summary_count) >= 4
                )
                
                if should_generate_summary:
                    logger.info(f"📝 Generating/updating AI summary for conversation {from_number} (messages: {message_count})")
                    result = ai_summarizer.summarize_sms_conversation(
                        messages, 
                        extracted_name or conversation.get('customer_name'),
                        from_number
                    )
                    
                    # Extract summary and customer name from AI response
                    summary = result.get('summary', 'Unable to generate summary')
                    extracted_name = result.get('customer_name')
                    
                    # Update conversation with summary
                    db.update_conversation_summary(from_number, summary)
                    # Update the message count when summary was generated
                    db.update_conversation_message_count_for_summary(from_number, message_count)
                    
                    # NEW: Update conversation name if AI extracted one
                    if extracted_name and extracted_name.lower() != "none":
                        ai_receptionist._update_conversation_name(from_number, extracted_name)
                
                # NEW: Enhanced notification analysis with conversation history truncation
                logger.info(f"🔍 Checking for notifications in conversation {from_number}")
                
                # Get the last notification analysis timestamp
                last_analysis_timestamp = conversation.get('last_notification_analysis_timestamp')
                
                # Filter messages for notification analysis
                messages_for_notification_analysis = messages
                if last_analysis_timestamp:
                    # Only analyze messages after the last notification analysis timestamp
                    messages_for_notification_analysis = [
                        msg for msg in messages 
                        if msg.get('timestamp', '') > last_analysis_timestamp
                    ]
                    logger.info(f"🔍 Analyzing {len(messages_for_notification_analysis)} messages after timestamp {last_analysis_timestamp}")
                else:
                    logger.info(f"🔍 Analyzing all {len(messages_for_notification_analysis)} messages (no previous analysis)")
                
                # Only proceed with notification analysis if we have messages to analyze
                if messages_for_notification_analysis:
                    notification = ai_summarizer.analyze_for_notifications(
                        '',  # Do not pass the summary
                        messages_for_notification_analysis,  # Use filtered messages
                        'sms', 
                        from_number, 
                        extracted_name or conversation.get('customer_name')
                    )
                    
                    if notification:
                        # Create notification with duplicate prevention (handled in database_service)
                        success = db.create_notification(
                            notification['type'],
                            notification['title'],
                            notification['summary'],
                            notification['phone'],
                            notification['customer_name'],
                            notification['conversation_type'],
                            from_number  # Use phone number as conversation_id
                        )
                        
                        if success:
                            logger.info(f"🚨 Notification created: {notification['title']}")
                            broadcast_event('{"type": "notification_created"}')
                        else:
                            logger.info(f"🔄 Notification skipped (duplicate): {notification['title']}")
                else:
                    logger.info(f"🔍 No new messages to analyze for notifications")
                    
            except Exception as e:
                logger.error(f"❌ Error generating summary/notifications: {str(e)}")
        
        # Send response via SMS (FROM business TO customer)
        logger.info(f"📱 Sending reply - Business: {to_number} → Customer: {from_number}")
        success = sms_service.send_sms(
            to_number=from_number,      # Send TO the customer who texted us
            from_number=to_number,      # Send FROM our business number
            message=response
        )
        
        if success:
            logger.info(f"📱 SMS response sent to {from_number}: {response}")
        else:
            # Don't log the error details to reduce terminal flooding
            logger.warning(f"📱 SMS response failed to {from_number} (continuing conversation)")
        
        return Response(status=200)
    except Exception as e:
        logger.error(f"❌ Error in incoming_message: {str(e)}")
        return Response(status=500)

def format_phone_number(phone):
    """Format phone number to E.164 format (+1XXXXXXXXXX)"""
    # Remove any non-digit characters
    digits = ''.join(filter(str.isdigit, phone))
    
    # Ensure it starts with +1
    if not digits.startswith('1'):
        digits = '1' + digits
    
    # Add + prefix
    return '+' + digits

def is_appointment_confirmation_message(message_text: str, from_number: str, to_number: str) -> bool:
    """
    Detect if a message is an appointment confirmation sent by the business
    
    Args:
        message_text: The message content
        from_number: Phone number the message is from
        to_number: Phone number the message is to
        
    Returns:
        True if this appears to be an appointment confirmation message
    """
    try:
        # Check if this is from business to customer (confirmation direction)
        business_number = "+18773900002"
        if from_number != business_number:
            return False
        
        # Check for appointment confirmation keywords
        message_lower = message_text.lower()
        
        # Key phrases that indicate appointment confirmation
        confirmation_indicators = [
            "appointment",
            "confirmed",
            "is confirmed",
            "your appointment",
            "appointment with",
            "price: $",
            "duration:",
            "minutes",
            "see you then"
        ]
        
        # Check if message contains multiple confirmation indicators
        indicator_count = sum(1 for indicator in confirmation_indicators if indicator in message_lower)
        
        # Must have at least 4 confirmation indicators to be considered a confirmation
        # This prevents false positives on simple messages like "Your appointment is confirmed"
        if indicator_count >= 4:
            logger.info(f"✅ Detected appointment confirmation message: {message_text[:100]}...")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Error detecting appointment confirmation: {str(e)}")
        return False

def handle_interest_notification_rescission(phone: str, message_timestamp: str):
    """
    Handle rescission of interest notifications when an appointment is confirmed
    
    Args:
        phone: Customer phone number
        message_timestamp: Timestamp of the confirmation message
    """
    try:
        # Check if there are any unresolved interest notifications for this phone
        interest_notifications = db.get_interest_notifications_by_phone(phone)
        
        if interest_notifications:
            logger.info(f"🎯 Found {len(interest_notifications)} interest notifications to rescind for {phone}")
            
            # Delete all interest notifications for this phone
            success = db.delete_interest_notifications_for_phone(phone)
            
            if success:
                # Update conversation analysis timestamp to prevent re-analysis of old messages
                db.update_conversation_analysis_timestamp_after_rescission(phone, message_timestamp)
                logger.info(f"✅ Successfully rescinded interest notifications for {phone}")
            else:
                logger.error(f"❌ Failed to rescind interest notifications for {phone}")
        else:
            logger.info(f"ℹ️ No interest notifications found to rescind for {phone}")
            
    except Exception as e:
        logger.error(f"❌ Error handling interest notification rescission: {str(e)}")

@app.route('/test-sms', methods=['GET'])
def test_sms():
    """Test SMS sending manually"""
    try:
        # Test SMS sending
        success = sms_service.send_sms(
            to_number="+13132044895",  # Your phone number
            from_number="+18773900002",  # Your Telnyx number
            message="Test SMS from Radiance MD Med Spa! This is a manual test."
        )
        
        if success:
            return {"status": "success", "message": "SMS sent successfully"}
        else:
            return {"status": "error", "message": "SMS failed to send"}
            
    except Exception as e:
        logger.error(f"Error in test SMS: {str(e)}")
        return {"status": "error", "message": str(e)}

# NEW: Manual SMS sending endpoint
@app.route('/send-sms', methods=['POST'])
def send_manual_sms():
    """Send manual SMS message"""
    try:
        data = request.get_json()
        
        to_number = data.get('to_number')
        message = data.get('message')
        from_number = data.get('from_number', '+18773900002')  # Default business number
        
        if not to_number or not message:
            return {"status": "error", "message": "Missing required fields"}, 400
        
        # Format phone number
        to_number = format_phone_number(to_number)
        
        # Send SMS
        success = sms_service.send_sms(
            to_number=to_number,
            from_number=from_number,
            message=message
        )
        
        if success:
            # Log the manual message to database
            db.log_message_exchange(to_number, from_number, "", message, None)  # Empty user message for manual sends
            logger.info(f"📱 Manual SMS sent to {to_number}: {message}")
            broadcast_event('{"type": "appointment_created"}')
            return {"status": "success", "message": "SMS sent successfully"}
        else:
            return {"status": "error", "message": "SMS failed to send"}, 500
            
    except Exception as e:
        logger.error(f"Error in manual SMS: {str(e)}")
        return {"status": "error", "message": str(e)}, 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with business hours status"""
    try:
        # Simple health check that doesn't depend on external services
        status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'message': 'Flask app is running successfully'
        }
        
        return Response(json.dumps(status), mimetype='application/json')
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return Response(json.dumps({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), mimetype='application/json', status=500)

@app.route('/test-connection', methods=['GET'])
def test_connection():
    """Simple test endpoint to verify frontend can reach backend"""
    try:
        logger.info("✅ Test connection endpoint called")
        return jsonify({
            'status': 'success',
            'message': 'Frontend can reach backend!',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Test connection failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/debug/message-cache', methods=['GET'])
def debug_message_cache():
    """Debug endpoint to check message deduplication cache status"""
    try:
        cache_info = {
            'cache_size': len(message_deduplicator),
            'max_size': message_deduplicator.maxlen,
            'recent_ids': list(message_deduplicator)[-10:] if message_deduplicator else [],  # Last 10 IDs
            'timestamp': datetime.now().isoformat()
        }
        
        return Response(json.dumps(cache_info), mimetype='application/json')
    except Exception as e:
        logger.error(f"Debug cache check failed: {str(e)}")
        return Response(json.dumps({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), mimetype='application/json', status=500)

@app.route('/test-scheduler', methods=['GET'])
def test_scheduler():
    """Test the message scheduling system"""
    try:
        from datetime import datetime, timedelta
        import pytz
        
        # Create a test appointment 2 hours in the future
        eastern = pytz.timezone('US/Eastern')
        test_time = datetime.now(eastern) + timedelta(hours=2)
        
        test_appointment = {
            'id': f'test_appointment_{int(test_time.timestamp())}',
            'name': 'Test Customer',
            'phone': '+13132044895',  # Your test number
            'date': test_time.strftime('%Y-%m-%d'),
            'time': test_time.strftime('%H:%M'),
            'service': 'botox',
            'service_name': 'Botox Injections',
            'specialist': 'Test Specialist',
            'duration': 30,
            'payment_url': 'https://test-payment-link.com',
            'deposit_paid': False
        }
        
        # Schedule messages
        result = message_scheduler.schedule_appointment_messages(test_appointment)
        
        return {
            'status': 'success',
            'message': 'Test appointment messages scheduled',
            'test_appointment': test_appointment,
            'scheduling_result': result,
            'reminder_time': (test_time - timedelta(hours=24)).isoformat() if result.get('results', {}).get('reminder_scheduled') else None,
            'thank_you_time': (test_time + timedelta(hours=1, minutes=30)).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in test scheduler: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/test-reschedule', methods=['GET'])
def test_reschedule():
    """Test the message rescheduling functionality"""
    try:
        # First, create a test appointment in the database
        test_appointment = {
            'calendar_event_id': 'test_reschedule_123',
            'id': 'test_reschedule_123',
            'customer_name': 'Test Reschedule Customer',
            'customer_phone': '+13132044895',
            'service': 'Test Reschedule Service',
            'service_name': 'Test Reschedule Service',
            'specialist': 'Test Specialist',
            'price': 150.0,
            'duration': 90,
            'appointment_date': '2025-01-20',
            'appointment_time': '10:00',
            'event_url': 'https://test.com',
            'status': 'confirmed',
            'created_at': datetime.now().isoformat()
        }
        
        # Add to database
        db.create_appointment(test_appointment)
        
        # Schedule initial messages
        initial_result = message_scheduler.schedule_appointment_messages(test_appointment)
        
        # Simulate time change
        updated_appointment_data = {
            'appointment_date': '2025-01-21',  # Moved to next day
            'appointment_time': '15:00',        # Moved to 3 PM
            'customer_name': 'Test Reschedule Customer',
            'customer_phone': '+13132044895',
            'service': 'Test Reschedule Service',
            'service_name': 'Test Reschedule Service',
            'specialist': 'Test Specialist',
            'price': 150.0,
            'duration': 90
        }
        
        # Reschedule messages
        reschedule_result = message_scheduler.reschedule_appointment_messages('test_reschedule_123', updated_appointment_data)
        
        return {
            'status': 'success',
            'initial_scheduling': initial_result,
            'reschedule_result': reschedule_result
        }
        
    except Exception as e:
        logger.error(f"Error testing reschedule: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/test-trigger-reminder/<appointment_id>', methods=['POST'])
def test_trigger_reminder(appointment_id):
    """Immediately trigger the 24-hour reminder message for an appointment"""
    try:
        # Get scheduled messages for this appointment
        messages = message_scheduler.get_scheduled_messages(appointment_id)
        
        # Find the 24-hour reminder message
        reminder_message = None
        for message in messages:
            if message.get('message_type') == '24hr_reminder' and message.get('status') == 'pending':
                reminder_message = message
                break
        
        if not reminder_message:
            return {
                'status': 'error',
                'message': f'No pending 24-hour reminder found for appointment {appointment_id}'
            }
        
        # Trigger the message immediately
        from message_scheduler import send_scheduled_message_standalone
        send_scheduled_message_standalone(reminder_message['message_id'])
        
        return {
            'status': 'success',
            'message': f'Triggered 24-hour reminder for appointment {appointment_id}',
            'message_id': reminder_message['message_id'],
            'customer_phone': reminder_message['customer_phone']
        }
        
    except Exception as e:
        logger.error(f"Error triggering reminder: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/test-trigger-thankyou/<appointment_id>', methods=['POST'])
def test_trigger_thankyou(appointment_id):
    """Immediately trigger the thank you message for an appointment"""
    try:
        # Get scheduled messages for this appointment
        messages = message_scheduler.get_scheduled_messages(appointment_id)
        
        # Find the thank you message
        thankyou_message = None
        for message in messages:
            if message.get('message_type') == 'thank_you_review' and message.get('status') == 'pending':
                thankyou_message = message
                break
        
        if not thankyou_message:
            return {
                'status': 'error',
                'message': f'No pending thank you message found for appointment {appointment_id}'
            }
        
        # Trigger the message immediately
        from message_scheduler import send_scheduled_message_standalone
        send_scheduled_message_standalone(thankyou_message['message_id'])
        
        return {
            'status': 'success',
            'message': f'Triggered thank you message for appointment {appointment_id}',
            'message_id': thankyou_message['message_id'],
            'customer_phone': thankyou_message['customer_phone']
        }
        
    except Exception as e:
        logger.error(f"Error triggering thank you message: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/scheduled-messages', methods=['GET'])
def view_scheduled_messages():
    """View all scheduled messages"""
    try:
        appointment_id = request.args.get('appointment_id')
        messages = message_scheduler.get_scheduled_messages(appointment_id)
        
        return {
            'status': 'success',
            'total_messages': len(messages),
            'messages': messages
        }
        
    except Exception as e:
        logger.error(f"Error viewing scheduled messages: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/cancel-messages/<appointment_id>', methods=['POST'])
def cancel_messages(appointment_id):
    """Cancel scheduled messages for an appointment"""
    try:
        result = message_scheduler.cancel_appointment_messages(appointment_id)
        
        return {
            'status': 'success' if result['success'] else 'error',
            'result': result
        }
        
    except Exception as e:
        logger.error(f"Error cancelling messages: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/reschedule-messages/<appointment_id>', methods=['POST'])
def reschedule_messages(appointment_id):
    """Manually reschedule messages for an appointment (for testing)"""
    try:
        # Get appointment data from database
        appointment = db.get_appointment_by_id(appointment_id)
        if not appointment:
            return {
                'status': 'error',
                'message': f'Appointment {appointment_id} not found'
            }
        
        # Prepare appointment data for rescheduling
        appointment_data = {
            'appointment_date': appointment.get('appointment_date'),
            'appointment_time': appointment.get('appointment_time'),
            'customer_name': appointment.get('customer_name'),
            'customer_phone': appointment.get('customer_phone'),
            'service': appointment.get('service'),
            'service_name': appointment.get('service_name'),
            'specialist': appointment.get('specialist'),
            'price': appointment.get('price'),
            'duration': appointment.get('duration')
        }
        
        # Reschedule messages
        result = message_scheduler.reschedule_appointment_messages(appointment_id, appointment_data)
        
        return {
            'status': 'success' if result['success'] else 'error',
            'result': result
        }
        
    except Exception as e:
        logger.error(f"Error rescheduling messages: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/clear-all-messages', methods=['GET', 'POST'])
def clear_all_messages():
    """Clear all scheduled messages (for testing)"""
    try:
        import sqlite3
        
        # Get all pending message IDs first
        conn = sqlite3.connect('scheduled_messages.db')
        cursor = conn.cursor()
        cursor.execute('SELECT message_id FROM scheduled_messages WHERE status = "pending"')
        message_ids = [row[0] for row in cursor.fetchall()]
        
        # Remove from scheduler
        cancelled_count = 0
        for message_id in message_ids:
            try:
                message_scheduler.scheduler.remove_job(message_id)
                cancelled_count += 1
            except:
                pass  # Job might not exist in scheduler
        
        # Clear the database
        cursor.execute('DELETE FROM scheduled_messages')
        conn.commit()
        conn.close()
        
        logger.info(f"🧹 Cleared all scheduled messages from database and scheduler")
        
        return {
            'status': 'success',
            'message': f'Cleared all scheduled messages',
            'cancelled_from_scheduler': cancelled_count,
            'cleared_from_database': 'all'
        }
        
    except Exception as e:
        logger.error(f"Error clearing messages: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

# --- Mode change detection ---
def check_and_broadcast_mode_change():
    global last_known_mode
    is_business_hours = get_business_hours_status()
    mode = "business_hours" if is_business_hours else "after_hours"
    if last_known_mode != mode:
        last_known_mode = mode
        broadcast_event(f'{{"type": "mode_changed", "mode": "{mode}"}}')
        logger.info(f"[SSE] Broadcasted mode_changed: {mode}")

# Patch set_setting to broadcast mode change if override is changed
orig_set_setting = db.set_setting

def set_setting_with_mode_broadcast(key, value):
    result = orig_set_setting(key, value)
    if key == 'business_hours_override':
        check_and_broadcast_mode_change()
    return result

db.set_setting = set_setting_with_mode_broadcast

# Call check_and_broadcast_mode_change from the scheduler jobs
# (Add to trigger_daily_archive and trigger_weekly_archive)
def trigger_daily_archive():
    try:
        logger.info("⏰ Triggering daily archive job...")
        pyrequests.post('https://vrai-systems-app-production.up.railway.app/api/archive/daily')
        check_and_broadcast_mode_change()
    except Exception as e:
        logger.error(f"❌ Error in daily archive job: {str(e)}")

def trigger_weekly_archive():
    try:
        logger.info("⏰ Triggering weekly archive job...")
        pyrequests.post('https://vrai-systems-app-production.up.railway.app/api/archive/weekly')
        check_and_broadcast_mode_change()
    except Exception as e:
        logger.error(f"❌ Error in weekly archive job: {str(e)}")

scheduler = BackgroundScheduler()
# Daily at midnight
scheduler.add_job(trigger_daily_archive, 'cron', hour=0, minute=0)
# Weekly on Sunday at 1am
scheduler.add_job(trigger_weekly_archive, 'cron', day_of_week='sun', hour=1, minute=0)
scheduler.start()

# Set up APScheduler for polling every 10 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(appointment_service.sync_appointments_with_google_calendar, 'interval', minutes=10)
scheduler.start()

# --- Testing endpoint for instant sync ---
# Usage: curl -X POST http://localhost:5000/admin/sync-appointments
@app.route('/admin/sync-appointments', methods=['POST'])
def admin_sync_appointments():
    appointment_service.sync_appointments_with_google_calendar()
    return jsonify({"status": "sync triggered"})

@app.route('/api/services', methods=['GET'])
def list_services():
    """Return all services as JSON"""
    try:
        services = db.get_services()
        return {"success": True, "services": services}
    except Exception as e:
        logger.error(f"Error listing services: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/services', methods=['POST'])
def add_service():
    """Add a new service"""
    try:
        data = request.get_json()
        name = data['name']
        price = data['price']
        duration = data['duration']
        requires_deposit = data.get('requires_deposit', True)
        deposit_amount = data.get('deposit_amount', 50)
        description = data.get('description')
        source_doc_id = data.get('source_doc_id')
        db.add_service(name, price, duration, requires_deposit, deposit_amount, description, source_doc_id)
        kb_service.sync_services_to_knowledge_base()
        broadcast_event('{"type": "appointment_created"}')
        return {"success": True}
    except Exception as e:
        logger.error(f"Error adding service: {str(e)}")
        return {"success": False, "error": str(e)}, 400

@app.route('/api/services/<int:service_id>', methods=['GET'])
def get_service(service_id):
    """Get a single service by ID"""
    try:
        service = db.get_service_by_id(service_id)
        if service:
            return {"success": True, "service": service}
        else:
            return {"success": False, "error": "Service not found"}, 404
    except Exception as e:
        logger.error(f"Error getting service: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/services/<int:service_id>', methods=['PUT'])
def update_service(service_id):
    """Update a service by ID"""
    try:
        data = request.get_json()
        db.update_service(
            service_id,
            name=data.get('name'),
            price=data.get('price'),
            duration=data.get('duration'),
            requires_deposit=data.get('requires_deposit'),
            deposit_amount=data.get('deposit_amount'),
            description=data.get('description')
        )
        kb_service.sync_services_to_knowledge_base()
        return {"success": True}
    except Exception as e:
        logger.error(f"Error updating service: {str(e)}")
        return {"success": False, "error": str(e)}, 400

@app.route('/api/services/<int:service_id>', methods=['DELETE'])
def delete_service(service_id):
    """Delete a service by ID"""
    try:
        db.delete_service(service_id)
        kb_service.sync_services_to_knowledge_base()
        return {"success": True}
    except Exception as e:
        logger.error(f"Error deleting service: {str(e)}")
        return {"success": False, "error": str(e)}, 400

@app.route('/api/services/upload-document', methods=['POST'])
def upload_services_document():
    """Upload a services document (CSV or Excel)"""
    if 'file' not in request.files:
        return {"success": False, "error": "No file part in request"}, 400
    file = request.files['file']
    if file.filename == '':
        return {"success": False, "error": "No selected file"}, 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        return {"success": True, "file_path": save_path}
    else:
        return {"success": False, "error": "Invalid file type. Only CSV and Excel files are allowed."}, 400

@app.route('/api/services/parse-document', methods=['POST'])
def parse_services_document():
    """Parse an uploaded services document and return a preview of extracted services."""
    data = request.get_json()
    file_path = data.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return {"success": False, "error": "File not found."}, 400
    try:
        ext = file_path.rsplit('.', 1)[1].lower()
        if ext == 'csv':
            df = pd.read_csv(file_path)
        elif ext == 'xlsx':
            df = pd.read_excel(file_path)
        else:
            return {"success": False, "error": "Unsupported file type."}, 400

        # Normalize column names
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
        # Required columns: service name, price, duration
        required = ['service_name', 'price', 'duration']
        for col in required:
            if col not in df.columns:
                return {"success": False, "error": f"Missing required column: {col}"}, 400
        # Optional columns
        desc_col = 'description' if 'description' in df.columns else None
        dep_req_col = 'deposit_required' if 'deposit_required' in df.columns else None
        dep_amt_col = 'deposit_amount' if 'deposit_amount' in df.columns else None
        # Build preview list
        preview = []
        for _, row in df.iterrows():
            service = {
                'name': str(row['service_name']).strip(),
                'price': float(row['price']),
                'duration': int(row['duration']),
                'requires_deposit': True if (dep_req_col and str(row[dep_req_col]).strip().lower() in ['yes', 'true', '1']) else True,  # Default True
                'deposit_amount': float(row[dep_amt_col]) if dep_amt_col and not pd.isnull(row[dep_amt_col]) else 50.0,
                'description': str(row[desc_col]).strip() if desc_col and not pd.isnull(row[desc_col]) else None
            }
            preview.append(service)
        return {"success": True, "services": preview}
    except Exception as e:
        logger.error(f"Error parsing services document: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/services/save', methods=['POST'])
def save_services():
    """Save a list of services (from parsed/edited preview) to the database."""
    data = request.get_json()
    services = data.get('services')
    source_doc_id = data.get('source_doc_id')
    if not services or not isinstance(services, list):
        return {"success": False, "error": "No services provided."}, 400
    added = 0
    for service in services:
        try:
            db.add_service(
                name=service['name'],
                price=service['price'],
                duration=service['duration'],
                requires_deposit=service.get('requires_deposit', True),
                deposit_amount=service.get('deposit_amount', 50),
                description=service.get('description'),
                source_doc_id=source_doc_id
            )
            added += 1
        except Exception as e:
            logger.error(f"Error adding service: {str(e)}")
            continue
    kb_service.sync_services_to_knowledge_base()
    broadcast_event('{"type": "appointment_created"}')
    return {"success": True, "added": added, "total": len(services)}

@app.route('/api/broadcast/call_finished', methods=['POST'])
def api_broadcast_call_finished():
    """Endpoint to broadcast a call_finished SSE event (for use by websocket_server or other services)"""
    try:
        data = request.get_json(force=True)
        call_id = data.get('callId')
        if not call_id:
            return jsonify({'success': False, 'error': 'Missing callId'}), 400
        event_data = json.dumps({'type': 'call_finished', 'callId': call_id})
        broadcast_event(event_data)
        logger.info(f"[SSE] API endpoint broadcasted call_finished for {call_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"[SSE] Error in /api/broadcast/call_finished: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/test-call-forwarding', methods=['GET'])
def test_call_forwarding():
    """Test endpoint to verify call forwarding configuration"""
    try:
        # Get business hours status
        is_business_hours = get_business_hours_status()
        
        # Get phone numbers
        telnyx_number = os.getenv('TELNYX_NUMBER', '+18773900002')
        front_desk_number = os.getenv('FORWARD_NUMBER', '+13132044895')
        
        # Create test response
        response_data = {
            'business_hours_status': 'business_hours' if is_business_hours else 'after_hours',
            'telnyx_number': telnyx_number,
            'front_desk_number': front_desk_number,
            'call_handling': 'forward_to_front_desk' if is_business_hours else 'ai_receptionist',
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"❌ Error in test_call_forwarding: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/debug-call-events', methods=['POST'])
def debug_call_events():
    """Debug endpoint to log and analyze call events from Telnyx"""
    try:
        # Log the raw request
        logger.info(f"🔍 DEBUG: Call event received. Headers: {dict(request.headers)}")
        data_str = request.get_data(as_text=True)
        logger.info(f"🔍 DEBUG: Call event data: {data_str}")
        
        # Parse the data
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = request.get_json(force=True)
        else:
            import urllib.parse
            data = dict(urllib.parse.parse_qsl(data_str))
        
        logger.info(f"🔍 DEBUG: Parsed call event data: {json.dumps(data, indent=2)}")
        
        # Extract key fields for analysis
        call_status = data.get('CallStatus')
        call_control_id = data.get('call_control_id') or data.get('CallSid')
        caller_number = data.get('From')
        called_number = data.get('To')
        call_duration = data.get('call_duration', data.get('CallDuration'))
        
        logger.info(f"🔍 DEBUG: Key fields - Status: {call_status}, ID: {call_control_id}, Duration: {call_duration}")
        
        # Return success
        return Response(status=200)
        
    except Exception as e:
        logger.error(f"❌ Error in debug_call_events: {str(e)}")
        return Response(status=500)

if __name__ == '__main__':
    # Start Flask app (HTTP only)
    logger.info("🚀 Starting Flask HTTP server on port 5000")
    logger.info("📞 Remember to also run: python websocket_server.py")
    
    # Show current business hours status
    is_business_hours = get_business_hours_status()
    mode = "BUSINESS HOURS (SMS for missed calls)" if is_business_hours else "AFTER HOURS (Voice AI active)"
    logger.info(f"🕐 Current mode: {mode}")
    
    app.run(debug=True, port=5000)