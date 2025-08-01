import asyncio
import websockets
import json
import logging
import os
import requests
from dotenv import load_dotenv
from realtime_service import OpenAIRealtimeService
from database_service import DatabaseService
from ai_summarizer import AISummarizer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track active sessions
active_sessions = {}

# Flask backend URL for database operations
FLASK_BACKEND_URL = "https://vrai-systems-app-production.up.railway.app"

async def handle_media_stream(websocket, path):
    """Handle WebSocket connection for media streaming between Telnyx and OpenAI"""
    logger.info(f"New WebSocket connection established on path: {path}")
    call_sid = None
    realtime_service = None
    
    try:
        # Send initial connected message if needed
        logger.info("WebSocket connected, waiting for Telnyx messages...")
        
        # Wait for Telnyx to send initial message
        async for message in websocket:
            try:
                data = json.loads(message)
                event = data.get('event')
                
                # Only log non-media events to reduce spam
                if event != 'media':
                    logger.info(f"Received event: {event}")
                
                if event == 'connected':
                    logger.info("Telnyx WebSocket connected")
                    
                elif event == 'start':
                    # Extract call information
                    start_data = data.get('start', {})
                    call_sid = start_data.get('call_control_id') or start_data.get('callSid')
                    logger.info(f"Media stream started for call: {call_sid}")
                    caller_phone = start_data.get('from')  # Add this line
                    
                    # NEW: Initialize database and AI summarizer services
                    # Use Flask backend API instead of local database
                    logger.info("🔧 Using Flask backend for database operations")
                    
                    # Initialize OpenAI Realtime Service with Flask backend integration
                    realtime_service = OpenAIRealtimeService()
                    realtime_service.call_sid = call_sid
                    realtime_service.caller_phone_number = caller_phone
                    realtime_service.flask_backend_url = FLASK_BACKEND_URL  # NEW: Pass Flask backend URL
                    
                    # NEW: Set services to use Flask backend
                    realtime_service.set_services_for_flask_backend(FLASK_BACKEND_URL)
                    
                    active_sessions[call_sid] = realtime_service
                    
                    # Connect to OpenAI
                    if await realtime_service.connect_to_openai():
                        # Start handling OpenAI responses in background
                        asyncio.create_task(
                            realtime_service.handle_openai_response(websocket)
                        )
                        
                        # Start the conversation
                        await realtime_service.start_conversation()
                    else:
                        logger.error("Failed to connect to OpenAI")
                        await websocket.close()
                        return
                
                elif event == 'media':
                    # Forward audio to OpenAI (no logging to reduce spam)
                    if realtime_service and realtime_service.session_active:
                        audio_payload = data.get('media', {}).get('payload')
                        if audio_payload:
                            # Log first few audio packets to see if we're getting data
                            if not hasattr(realtime_service, 'audio_count'):
                                realtime_service.audio_count = 0
                            realtime_service.audio_count += 1
                            
                            if realtime_service.audio_count <= 3:  # Log first 3 packets
                                logger.info(f"Received Telnyx audio packet #{realtime_service.audio_count}: {len(audio_payload)} chars")
                            
                            await realtime_service.handle_telnyx_audio(audio_payload)
                
                elif event == 'stop':
                    logger.info(f"Media stream stopped for call: {call_sid}")
                    break
                else:
                    logger.info(f"Unknown event type: {event}")
                    
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON message: {message}")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                
        # Save transcript, summary, and notifications first
        if realtime_service:
            await realtime_service.save_call_transcript()
        # Now broadcast call_finished SSE
        try:
            response = requests.post(
                'https://vrai-systems-app-production.up.railway.app/api/broadcast/call_finished',
                json={'callId': call_sid},
                timeout=2
            )
            print(f"[SSE Notify] POST /api/broadcast/call_finished: {response.status_code} {response.text}")
        except Exception as e:
            print(f"[SSE Notify] Error notifying Flask app for call_finished: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"Error in media stream handler: {str(e)}")
    finally:
        # Clean up
        if realtime_service:
            await realtime_service.close_connections()
        if call_sid and call_sid in active_sessions:
            del active_sessions[call_sid]
        logger.info("Media stream handler cleaned up")

async def main():
    """Start the WebSocket server"""
    # Get port from environment variable (for Railway)
    port = int(os.getenv('PORT', 8080))
    
    logger.info(f"Starting WebSocket server on port {port}...")
    
    # Start WebSocket server
    server = await websockets.serve(
        handle_media_stream,
        "0.0.0.0",
        port
    )
    
    logger.info(f"WebSocket server running on ws://0.0.0.0:{port}")
    logger.info("🚀 WebSocket server deployed and ready for Telnyx connections!")
    
    # Keep server running
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())