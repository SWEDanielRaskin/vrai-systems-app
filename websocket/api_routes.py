from flask import Blueprint, request, jsonify
import sqlite3
import json
import logging
from datetime import datetime, timedelta, date
import pytz
from database_service import DatabaseService
from knowledge_base_service import KnowledgeBaseService
import os
from google_sheets_archiver import GoogleSheetsArchiver

logger = logging.getLogger(__name__)

# Create Blueprint for API routes
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Initialize database service
db = DatabaseService()

# NEW: Initialize knowledge base service
kb_service = KnowledgeBaseService(database_service=db)

# FIXED: Helper function for consistent tracking windows
def get_tracking_window():
    """
    Get consistent 24-hour tracking window (midnight to midnight Eastern Time)
    This ensures reliable tracking regardless of operating hours changes
    """
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    
    # Today from midnight to midnight (Eastern Time)
    today_start = eastern.localize(datetime.combine(now.date(), datetime.min.time()))
    today_end = eastern.localize(datetime.combine(now.date(), datetime.max.time()))
    
    return today_start, today_end

# Settings endpoints
@api_bp.route('/settings/<setting_key>', methods=['GET'])
def get_setting(setting_key):
    """Get a specific setting"""
    try:
        value = db.get_setting(setting_key)
        
        if value is None:
            return jsonify({'error': 'Setting not found'}), 404
        
        # Try to parse JSON values
        try:
            parsed_value = json.loads(value)
            return jsonify({'key': setting_key, 'value': parsed_value})
        except json.JSONDecodeError:
            return jsonify({'key': setting_key, 'value': value})
            
    except Exception as e:
        logger.error(f"Error getting setting {setting_key}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/settings/<setting_key>', methods=['PUT'])
def update_setting(setting_key):
    """Update a specific setting"""
    try:
        data = request.get_json()
        
        if 'value' not in data:
            return jsonify({'error': 'Value is required'}), 400
        
        # Convert value to string for storage
        value = data['value']
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        else:
            value = str(value)
        
        success = db.set_setting(setting_key, value)
        
        if success:
            return jsonify({'success': True, 'key': setting_key, 'value': data['value']})
        else:
            return jsonify({'error': 'Failed to update setting'}), 500
            
    except Exception as e:
        logger.error(f"Error updating setting {setting_key}: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Staff endpoints
@api_bp.route('/settings/staff', methods=['GET'])
def get_staff():
    include_inactive = request.args.get('include_inactive', 'true').lower() == 'true'
    staff = db.get_all_staff(include_inactive=include_inactive)
    return jsonify(staff)

@api_bp.route('/settings/staff', methods=['PUT'])
def update_staff():
    """Update staff list"""
    try:
        data = request.get_json()
        
        if 'staff' not in data:
            return jsonify({'error': 'Staff list is required'}), 400
        
        staff_list = data['staff']
        
        # Get current staff to determine what to update/add/remove
        current_staff = db.get_all_staff()
        current_staff_ids = {s['id'] for s in current_staff}
        
        updated_staff_ids = set()
        
        # Process each staff member in the request
        for staff_member in staff_list:
            if 'id' in staff_member and staff_member['id']:
                # Update existing staff member
                staff_id = staff_member['id']
                updated_staff_ids.add(staff_id)
                
                db.update_staff_member(
                    staff_id,
                    staff_member['name'],
                    staff_member.get('position', 'Specialist'),
                    staff_member.get('active', True)
                )
            else:
                # Add new staff member
                db.add_staff_member(
                    staff_member['name'],
                    staff_member.get('position', 'Specialist'),
                    staff_member.get('active', True)
                )
        
        # Remove staff members that are no longer in the list
        for staff_id in current_staff_ids:
            if staff_id not in updated_staff_ids:
                db.remove_staff_member(staff_id)
        
        # Return updated staff list
        updated_staff = db.get_all_staff()
        return jsonify(updated_staff)
        
    except Exception as e:
        logger.error(f"Error updating staff: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Knowledge base endpoints - UPDATED with processing
@api_bp.route('/knowledge_base', methods=['GET'])
def get_knowledge_base():
    """Get all knowledge base items"""
    try:
        items = db.get_all_knowledge_base_items()
        return jsonify({'items': items})
        
    except Exception as e:
        logger.error(f"Error getting knowledge base: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/knowledge_base/add_link', methods=['POST'])
def add_knowledge_base_link():
    """Add a group of links to knowledge base and process as one entry"""
    try:
        data = request.get_json()
        urls = data.get('urls')
        description = data.get('description')
        if not urls or not isinstance(urls, list) or not description:
            return jsonify({'error': 'URLs (array) and description are required'}), 400

        # Normalize and deduplicate URLs
        def normalize_url(url):
            url = url.strip().lower()
            if url.endswith('/'):
                url = url[:-1]
            return url
        norm_urls = list({normalize_url(u) for u in urls})

        # Add to database first (store all URLs as JSON string)
        main_url = norm_urls[0] if norm_urls else ''
        urls_json = json.dumps(norm_urls)
        success = db.add_knowledge_base_item(
            item_type='link',
            name=description,
            description=main_url,
            url=urls_json
        )

        if success:
            # Get the newly created item ID
            items = db.get_all_knowledge_base_items()
            new_item = next((item for item in items if item['url'] == urls_json), None)

            if new_item:
                # Process all links as a group
                logger.info(f"🔗 Processing new grouped links: {norm_urls}")
                processing_success = kb_service.process_links_group(norm_urls, new_item['id'], description)
                if not processing_success:
                    logger.warning(f"⚠️ Failed to process grouped link content for {norm_urls}")

            # Return updated items list
            updated_items = db.get_all_knowledge_base_items()
            return jsonify({'success': True, 'items': updated_items})
        else:
            return jsonify({'error': 'Failed to add grouped links'}), 500
    except Exception as e:
        logger.error(f"Error adding grouped knowledge base links: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/knowledge_base/upload', methods=['POST'])
def upload_knowledge_base_document():
    """Upload a document to knowledge base and process it"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Create uploads directory if it doesn't exist
        uploads_dir = 'uploads'
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)
        
        # Save file
        file_path = os.path.join(uploads_dir, file.filename)
        file.save(file_path)
        
        # Get file extension
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        
        # Add to database
        success = db.add_knowledge_base_item(
            item_type='document',
            name=file.filename,
            description='Recently uploaded document',
            file_path=file_path
        )
        
        if success:
            # Get the newly created item ID
            items = db.get_all_knowledge_base_items()
            new_item = next((item for item in items if item['file_path'] == file_path), None)
            
            if new_item:
                # Process the document content
                logger.info(f"📄 Processing new document: {file.filename}")
                processing_success = kb_service.process_document(file_path, new_item['id'], file_extension)
                
                if not processing_success:
                    logger.warning(f"⚠️ Failed to process document content for {file.filename}")
            
            # Return updated items list
            updated_items = db.get_all_knowledge_base_items()
            return jsonify({'success': True, 'items': updated_items})
        else:
            return jsonify({'error': 'Failed to upload document'}), 500
            
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/knowledge_base/<int:item_id>', methods=['DELETE'])
def remove_knowledge_base_item(item_id):
    """Remove a knowledge base item and its processed content"""
    try:
        # Get item details before deletion
        items = db.get_all_knowledge_base_items()
        item_to_delete = next((item for item in items if item['id'] == item_id), None)
        
        if item_to_delete:
            # Remove file if it exists
            if item_to_delete.get('file_path') and os.path.exists(item_to_delete['file_path']):
                try:
                    os.remove(item_to_delete['file_path'])
                    logger.info(f"🗑️ Removed file: {item_to_delete['file_path']}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not remove file: {str(e)}")
            
            # Remove processed content from kb_content table
            try:
                conn = sqlite3.connect(db.db_file)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM kb_content WHERE source_id = ?', (item_id,))
                conn.commit()
                conn.close()
                logger.info(f"🗑️ Removed processed content for item {item_id}")
            except Exception as e:
                logger.warning(f"⚠️ Could not remove processed content: {str(e)}")
        
        # Remove from knowledge base table
        success = db.remove_knowledge_base_item(item_id)
        
        if success:
            items = db.get_all_knowledge_base_items()
            return jsonify({'success': True, 'items': items})
        else:
            return jsonify({'error': 'Failed to remove item'}), 500
            
    except Exception as e:
        logger.error(f"Error removing knowledge base item: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Dashboard data endpoints - FIXED WITH CONSISTENT 24-HOUR TRACKING
@api_bp.route('/calls/recent', methods=['GET'])
def get_recent_calls():
    """Get recent calls for dashboard - ENHANCED: Returns detailed call list"""
    try:
        # FIXED: Use consistent 24-hour tracking window
        today_start, today_end = get_tracking_window()
        
        # Get today's calls from database
        calls_data = db.get_calls_by_date_range(today_start.isoformat(), today_end.isoformat())
        
        # Calculate statistics
        total_calls = len(calls_data)
        answered_calls = len([c for c in calls_data if c['status'] == 'completed'])
        missed_calls = len([c for c in calls_data if c['status'] == 'missed'])
        
        # Format calls for frontend display
        formatted_calls = []
        for call in calls_data:
            # Parse transcript to determine if it has content
            transcript = []
            if call.get('transcript'):
                try:
                    transcript = json.loads(call['transcript'])
                except (json.JSONDecodeError, TypeError):
                    transcript = []
            
            # Format duration
            duration_str = "0:00"
            if call.get('duration'):
                minutes = call['duration'] // 60
                seconds = call['duration'] % 60
                duration_str = f"{minutes}:{seconds:02d}"
            
            # Format timestamp
            timestamp_str = "Unknown"
            if call.get('start_time'):
                try:
                    dt = datetime.fromisoformat(call['start_time'])
                    timestamp_str = dt.strftime('%I:%M %p').lstrip('0')
                except:
                    timestamp_str = "Unknown"
            
            # Determine call type based on status and business hours
            if call['status'] == 'completed':
                type = 'answered_by_ai'
            elif call['status'] == 'missed':
                type = 'missed_call'
            elif call['status'] == 'transferred':
                type = 'transferred_to_front_desk'
            elif call['status'] == 'active':
                type = 'ongoing_call'
            else:
                type = 'unknown'
            
            formatted_calls.append({
                'id': call['call_control_id'],
                'phone': call['caller_phone'],
                'customerName': call.get('customer_name') or 'Unknown Caller',
                'timestamp': timestamp_str,
                'duration': duration_str,
                'type': type,
                'status': call['status'],
                'has_transcript': len(transcript) > 0
            })
        
        return jsonify({
            'count': total_calls,
            'answered': answered_calls,
            'missed': missed_calls,
            'calls': formatted_calls,  # NEW: Include formatted call list
            'tracking_window': f"{today_start.strftime('%Y-%m-%d %H:%M')} to {today_end.strftime('%Y-%m-%d %H:%M')}",
            'summary': f"{answered_calls} answered by AI, {missed_calls} missed calls" if total_calls > 0 else "No calls today"
        })
        
    except Exception as e:
        logger.error(f"Error getting recent calls: {str(e)}")
        return jsonify({
            'count': 0,
            'answered': 0,
            'missed': 0,
            'calls': [],  # NEW: Empty call list on error
            'summary': "No calls today"
        })

@api_bp.route('/calls/<call_control_id>', methods=['GET'])
def get_call_details(call_control_id):
    """Get detailed information for a specific call including full transcript"""
    try:
        logger.info(f"🔍 Fetching call details for: {call_control_id}")
        
        # Get call from database
        call_data = db.get_call_by_id(call_control_id)
        
        if not call_data:
            logger.warning(f"❌ Call not found: {call_control_id}")
            return jsonify({'error': 'Call not found'}), 404
        
        logger.info(f"📞 Found call data: {call_data.get('call_control_id')} - Status: {call_data.get('status')}")
        
        # Parse transcript
        transcript = []
        if call_data.get('transcript'):
            try:
                transcript = json.loads(call_data['transcript'])
                logger.info(f"📝 Parsed transcript with {len(transcript)} messages")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"❌ Failed to parse transcript for call {call_control_id}: {str(e)}")
                logger.warning(f"❌ Raw transcript data: {call_data.get('transcript')}")
                transcript = []
        else:
            logger.info(f"📝 No transcript data found for call {call_control_id}")
        
        # Format duration
        duration_str = "0:00"
        if call_data.get('duration'):
            minutes = call_data['duration'] // 60
            seconds = call_data['duration'] % 60
            duration_str = f"{minutes}:{seconds:02d}"
        
        # Format timestamp
        timestamp_str = "Unknown"
        if call_data.get('start_time'):
            try:
                dt = datetime.fromisoformat(call_data['start_time'])
                timestamp_str = dt.strftime('%I:%M %p').lstrip('0')
            except:
                timestamp_str = "Unknown"
        
        # Generate AI summary if we have a transcript
        summary = call_data.get('summary') or "No summary available"
        if not call_data.get('summary') and transcript:
            # TODO: Implement AI summarization here
            summary = "AI summary generation will be implemented in the next phase"
        
        # Determine call type based on status
        if call_data['status'] == 'completed':
            type = 'answered_by_ai'
        elif call_data['status'] == 'missed':
            type = 'missed_call'
        elif call_data['status'] == 'transferred':
            type = 'transferred_to_front_desk'
        elif call_data['status'] == 'active':
            type = 'ongoing_call'
        else:
            type = 'unknown'
        
        formatted_call = {
            'id': call_data['call_control_id'],
            'phone': call_data['caller_phone'],
            'customerName': call_data.get('customer_name') or 'Unknown Caller',
            'timestamp': timestamp_str,
            'duration': duration_str,
            'type': type,
            'status': call_data['status'],
            'transcript': transcript,
            'summary': summary
        }
        
        logger.info(f"✅ Returning call details with {len(transcript)} transcript messages")
        return jsonify(formatted_call)
        
    except Exception as e:
        logger.error(f"❌ Error getting call details for {call_control_id}: {str(e)}")
        import traceback
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/messages/recent', methods=['GET'])
def get_recent_messages():
    """Get recent messages for dashboard - ENHANCED: Returns detailed conversation list"""
    try:
        # FIXED: Use consistent 24-hour tracking window
        today_start, today_end = get_tracking_window()
        
        # Get today's message conversations from database
        conversations_data = db.get_conversations_by_date_range(today_start.isoformat(), today_end.isoformat())
        
        # Calculate statistics
        total_conversations = len(conversations_data)
        total_messages = sum(len(json.loads(conv['messages'])) for conv in conversations_data)
        
        # Format conversations for frontend display
        formatted_conversations = []
        for conv in conversations_data:
            # Parse messages
            messages = []
            try:
                messages = json.loads(conv['messages'])
            except (json.JSONDecodeError, TypeError):
                messages = []
            
            # Get last message
            last_message = ""
            last_message_time = "Unknown"
            if messages:
                last_msg = messages[-1]
                last_message = last_msg.get('message', '')
                last_message_time = last_msg.get('timestamp', 'Unknown')
                
                # Format timestamp
                try:
                    if 'T' in last_message_time or '-' in last_message_time:
                        # ISO format
                        dt = datetime.fromisoformat(last_message_time.replace('Z', '+00:00'))
                        last_message_time = dt.strftime('%I:%M %p').lstrip('0')
                except:
                    pass  # Keep original format if parsing fails
            
            # Truncate long messages
            if len(last_message) > 60:
                last_message = last_message[:60] + "..."
            
            formatted_conversations.append({
                'id': conv['conversation_id'],
                'customerName': conv.get('customer_name') or 'Unknown Customer',
                'phone': conv['customer_phone'],
                'lastMessage': last_message,
                'timestamp': last_message_time,
                'messageCount': len(messages),
                'unread': False,  # For now, all messages are considered read
                'summary': conv.get('summary') or "No summary available"
            })
        
        return jsonify({
            'count': total_conversations,
            'total_messages': total_messages,
            'conversations': formatted_conversations,  # NEW: Include formatted conversation list
            'tracking_window': f"{today_start.strftime('%Y-%m-%d %H:%M')} to {today_end.strftime('%Y-%m-%d %H:%M')}",
            'summary': f"{total_conversations} conversations, {total_messages} total messages" if total_conversations > 0 else "No messages today"
        })
        
    except Exception as e:
        logger.error(f"Error getting recent messages: {str(e)}")
        return jsonify({
            'count': 0,
            'total_messages': 0,
            'conversations': [],  # NEW: Empty conversation list on error
            'summary': "No messages today"
        })

@api_bp.route('/messages/<conversation_id>', methods=['GET'])
def get_conversation_details(conversation_id):
    """Get detailed information for a specific conversation including full message history"""
    try:
        logger.info(f"🔍 Fetching conversation details for: {conversation_id}")
        
        # Get conversation from database
        conversation_data = db.get_conversation_by_id(conversation_id)
        
        if not conversation_data:
            logger.warning(f"❌ Conversation not found: {conversation_id}")
            return jsonify({'error': 'Conversation not found'}), 404
        
        logger.info(f"💬 Found conversation data: {conversation_data.get('conversation_id')}")
        
        # Parse messages
        messages = []
        if conversation_data.get('messages'):
            try:
                messages = json.loads(conversation_data['messages'])
                logger.info(f"📝 Parsed conversation with {len(messages)} messages")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"❌ Failed to parse messages for conversation {conversation_id}: {str(e)}")
                messages = []
        else:
            logger.info(f"📝 No messages found for conversation {conversation_id}")
        
        # Generate AI summary if we have messages
        summary = conversation_data.get('summary') or "No summary available"
        if not conversation_data.get('summary') and messages:
            # TODO: Implement AI summarization here
            summary = "AI summary generation will be implemented in the next phase"
        
        # Format last message time
        last_message_time = "Unknown"
        if conversation_data.get('last_message_time'):
            try:
                dt = datetime.fromisoformat(conversation_data['last_message_time'])
                last_message_time = dt.strftime('%I:%M %p').lstrip('0')
            except:
                last_message_time = conversation_data['last_message_time']
        
        formatted_conversation = {
            'id': conversation_data['conversation_id'],
            'customerName': conversation_data.get('customer_name') or 'Unknown Customer',
            'phone': conversation_data['customer_phone'],
            'businessPhone': conversation_data['business_phone'],
            'messages': messages,
            'summary': summary,
            'lastMessageTime': last_message_time,
            'messageCount': len(messages)
        }
        
        logger.info(f"✅ Returning conversation details with {len(messages)} messages")
        return jsonify(formatted_conversation)
        
    except Exception as e:
        logger.error(f"❌ Error getting conversation details for {conversation_id}: {str(e)}")
        import traceback
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/appointments/new_today', methods=['GET'])
def get_new_appointments_today():
    """Get count of appointments created today - FIXED: 24-hour tracking window"""
    try:
        # FIXED: Use consistent 24-hour tracking window
        today_start, today_end = get_tracking_window()
        
        # Get today's appointments from database
        appointments_data = db.get_appointments_by_date_range(today_start.isoformat(), today_end.isoformat())
        
        # Calculate statistics
        total_appointments = len(appointments_data)
        
        # Group by service type
        services = {}
        for apt in appointments_data:
            service = apt['service']
            services[service] = services.get(service, 0) + 1
        
        # Get recent appointments (last 5)
        recent_appointments = appointments_data[:5] if appointments_data else []
        
        return jsonify({
            'count': total_appointments,
            'by_service': services,
            'recent_appointments': recent_appointments,
            'tracking_window': f"{today_start.strftime('%Y-%m-%d %H:%M')} to {today_end.strftime('%Y-%m-%d %H:%M')}",
            'summary': f"{total_appointments} new appointments created today" if total_appointments > 0 else "No new appointments today"
        })
        
    except Exception as e:
        logger.error(f"Error getting new appointments: {str(e)}")
        return jsonify({
            'count': 0,
            'by_service': {},
            'recent_appointments': [],
            'summary': "No new appointments today"
        })

# Analytics endpoints
@api_bp.route('/analytics/weekly_summary', methods=['GET'])
def get_weekly_summary():
    """Get weekly analytics summary"""
    try:
        eastern = pytz.timezone('US/Eastern')
        today = datetime.now(eastern).date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday
        
        week_start_dt = eastern.localize(datetime.combine(week_start, datetime.min.time()))
        week_end_dt = eastern.localize(datetime.combine(week_end, datetime.max.time()))
        
        # Get weekly data
        calls_data = db.get_calls_by_date_range(week_start_dt.isoformat(), week_end_dt.isoformat())
        conversations_data = db.get_conversations_by_date_range(week_start_dt.isoformat(), week_end_dt.isoformat())
        appointments_data = db.get_appointments_by_date_range(week_start_dt.isoformat(), week_end_dt.isoformat())
        
        # Calculate daily breakdown
        daily_stats = {}
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_name = day.strftime('%A')
            daily_stats[day_name] = {
                'date': day.isoformat(),
                'calls': 0,
                'messages': 0,
                'appointments': 0
            }
        
        # Count calls by day
        for call in calls_data:
            call_date = datetime.fromisoformat(call['start_time']).date()
            day_name = call_date.strftime('%A')
            if day_name in daily_stats:
                daily_stats[day_name]['calls'] += 1
        
        # Count conversations by day
        for conv in conversations_data:
            conv_date = datetime.fromisoformat(conv['created_at']).date()
            day_name = conv_date.strftime('%A')
            if day_name in daily_stats:
                daily_stats[day_name]['messages'] += 1
        
        # Count appointments by day
        for apt in appointments_data:
            apt_date = datetime.fromisoformat(apt['created_at']).date()
            day_name = apt_date.strftime('%A')
            if day_name in daily_stats:
                daily_stats[day_name]['appointments'] += 1
        
        return jsonify({
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            'daily_stats': daily_stats,
            'totals': {
                'calls': len(calls_data),
                'conversations': len(conversations_data),
                'appointments': len(appointments_data)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting weekly summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Notifications endpoints
@api_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """Get all notifications"""
    try:
        notifications = db.get_all_notifications()
        return jsonify({
            'notifications': notifications,
            'unresolved_count': len([n for n in notifications if not n['resolved']])
        })
        
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/notifications/<int:notification_id>/resolve', methods=['POST'])
def resolve_notification(notification_id):
    """Mark a notification as resolved"""
    try:
        success = db.resolve_notification(notification_id)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to resolve notification'}), 500
            
    except Exception as e:
        logger.error(f"Error resolving notification: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        success = db.delete_notification(notification_id)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to delete notification'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        return jsonify({'error': str(e)}), 500

# FIXED: Add data archiving endpoint for window resets
@api_bp.route('/analytics/archive_daily_data', methods=['POST'])
def archive_daily_data():
    """
    Archive daily data and reset tracking window
    This would be called automatically at midnight or manually for testing
    """
    try:
        # Get yesterday's data for archiving
        eastern = pytz.timezone('US/Eastern')
        yesterday = datetime.now(eastern).date() - timedelta(days=1)
        yesterday_start = eastern.localize(datetime.combine(yesterday, datetime.min.time()))
        yesterday_end = eastern.localize(datetime.combine(yesterday, datetime.max.time()))
        
        # Get data to archive
        calls_data = db.get_calls_by_date_range(yesterday_start.isoformat(), yesterday_end.isoformat())
        conversations_data = db.get_conversations_by_date_range(yesterday_start.isoformat(), yesterday_end.isoformat())
        appointments_data = db.get_appointments_by_date_range(yesterday_start.isoformat(), yesterday_end.isoformat())
        
        # TODO: Implement Google Sheets archiving here
        # For now, just return the data that would be archived
        
        archive_summary = {
            'date': yesterday.isoformat(),
            'calls': {
                'total': len(calls_data),
                'answered': len([c for c in calls_data if c['status'] == 'completed']),
                'missed': len([c for c in calls_data if c['status'] == 'missed'])
            },
            'messages': {
                'conversations': len(conversations_data),
                'total_messages': sum(len(json.loads(conv['messages'])) for conv in conversations_data)
            },
            'appointments': {
                'total': len(appointments_data),
                'by_service': {}
            }
        }
        
        # Group appointments by service
        for apt in appointments_data:
            service = apt['service']
            archive_summary['appointments']['by_service'][service] = archive_summary['appointments']['by_service'].get(service, 0) + 1
        
        return jsonify({
            'success': True,
            'archived_date': yesterday.isoformat(),
            'summary': archive_summary,
            'message': 'Daily data archived successfully'
        })
        
    except Exception as e:
        logger.error(f"Error archiving daily data: {str(e)}")
        return jsonify({'error': str(e)}), 500

# --- ARCHIVING ENDPOINTS ---

@api_bp.route('/archive/daily', methods=['POST'])
def archive_daily():
    """Archive voice calls, messages, and notifications for the last 24 hours, then clear them from the database."""
    try:
        # CONFIG: Set your spreadsheet IDs here
        VOICE_SHEET_ID = os.environ.get('VOICE_ARCHIVE_SHEET_ID')
        MESSAGES_SHEET_ID = os.environ.get('MESSAGES_ARCHIVE_SHEET_ID')
        NOTIF_SHEET_ID = os.environ.get('NOTIFICATIONS_ARCHIVE_SHEET_ID')
        CREDENTIALS_PATH = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'google-calendar-credentials.json')
        archiver = GoogleSheetsArchiver(CREDENTIALS_PATH, db=db)
        today = date.today()

        # --- Voice Calls ---
        voice_calls = db.get_voice_calls_for_archiving()
        archiver.archive_conversations(VOICE_SHEET_ID, voice_calls, today)
        db.clear_voice_calls_for_archiving()

        # --- Messages ---
        messages = db.get_messages_for_archiving()
        archiver.archive_conversations(MESSAGES_SHEET_ID, messages, today)
        db.clear_messages_for_archiving()

        # --- Notifications (older than 7 days) ---
        notifications = db.get_notifications_for_archiving()
        archiver.archive_notifications(NOTIF_SHEET_ID, notifications, today)
        db.clear_notifications_for_archiving()

        return jsonify({'success': True, 'archived_voice_calls': len(voice_calls), 'archived_messages': len(messages), 'archived_notifications': len(notifications)})
    except Exception as e:
        logger.error(f"Error archiving daily: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/extract_links', methods=['POST'])
def extract_links():
    """Extract all internal links and their titles from a given URL."""
    try:
        data = request.get_json()
        url = data.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        results = kb_service.extract_internal_links_and_titles(url)
        return jsonify({'links': results})
    except Exception as e:
        logger.error(f"Error extracting links: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== CUSTOMER MANAGEMENT ENDPOINTS ====================

@api_bp.route('/customers', methods=['GET'])
def get_customers():
    """Get list of customers with optional search, sorting, and pagination"""
    try:
        # Get query parameters
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'name')
        sort_order = request.args.get('sort_order', 'ASC')
        limit = request.args.get('limit', type=int)
        
        result = db.list_customers(
            search=search if search else None,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit
        )
        
        return jsonify({
            'customers': result['customers'],
            'total': result['total_count'],
            'search': search,
            'sort_by': sort_by,
            'sort_order': sort_order
        })
        
    except Exception as e:
        logger.error(f"Error getting customers: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/customers/<phone_number>', methods=['GET'])
def get_customer_detail(phone_number):
    """Get detailed customer information including appointment history"""
    try:
        customer = db.get_customer_with_appointments(phone_number)
        
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        return jsonify({'customer': customer})
        
    except Exception as e:
        logger.error(f"Error getting customer detail: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/customers', methods=['POST'])
def create_customer():
    """Create a new customer manually"""
    try:
        data = request.get_json()
        
        required_fields = ['phone_number']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        success = db.create_customer(
            phone_number=data['phone_number'],
            name=data.get('name'),
            email=data.get('email'),
            notes=data.get('notes'),
            up_next_from_you=data.get('up_next_from_you')
        )
        
        if success:
            customer = db.get_customer(data['phone_number'])
            return jsonify({'success': True, 'customer': customer}), 201
        else:
            return jsonify({'error': 'Customer already exists or creation failed'}), 400
            
    except Exception as e:
        logger.error(f"Error creating customer: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/customers/<phone_number>', methods=['PUT'])
def update_customer(phone_number):
    """Update customer information"""
    try:
        data = request.get_json()
        
        # Remove phone_number from data to prevent updating the primary key
        update_data = {k: v for k, v in data.items() if k != 'phone_number'}
        
        success = db.update_customer(phone_number, **update_data)
        
        if success:
            customer = db.get_customer(phone_number)
            if customer:
                return jsonify({'success': True, 'customer': customer})
            else:
                return jsonify({'error': 'Customer not found'}), 404
        else:
            return jsonify({'error': 'Update failed'}), 500
            
    except Exception as e:
        logger.error(f"Error updating customer: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/customers/<phone_number>', methods=['DELETE'])
def delete_customer(phone_number):
    """Delete a customer (use with caution)"""
    try:
        success = db.delete_customer(phone_number)
        
        if success:
            return jsonify({'success': True, 'message': 'Customer deleted'})
        else:
            return jsonify({'error': 'Delete failed'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting customer: {str(e)}")
        return jsonify({'error': str(e)}), 500



# ==================== APPOINTMENT NOTES ENDPOINTS ====================

@api_bp.route('/appointments/<appointment_id>/notes', methods=['PUT'])
def update_appointment_notes(appointment_id):
    """Update notes for a specific appointment"""
    try:
        data = request.get_json()
        
        if 'notes' not in data:
            return jsonify({'error': 'Notes are required'}), 400
        
        success = db.update_appointment_notes(appointment_id, data['notes'])
        
        if success:
            return jsonify({'success': True, 'message': 'Appointment notes updated'})
        else:
            return jsonify({'error': 'Failed to update appointment notes'}), 500
            
    except Exception as e:
        logger.error(f"Error updating appointment notes: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== CUSTOMER PROFILE PICTURE UPLOAD ====================

@api_bp.route('/customers/<phone_number>/profile-picture', methods=['POST'])
def upload_customer_profile_picture(phone_number):
    """Upload a profile picture for a customer"""
    try:
        if 'profile_picture' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['profile_picture']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif'}), 400
        
        # Create customer photos directory if it doesn't exist
        import os
        from werkzeug.utils import secure_filename
        
        upload_dir = 'uploads/customer_photos'
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        filename = secure_filename(f"{phone_number}_{file.filename}")
        file_path = os.path.join(upload_dir, filename)
        
        # Save file
        file.save(file_path)
        
        # Update customer record
        success = db.update_customer(phone_number, profile_picture_path=file_path)
        
        if success:
            return jsonify({
                'success': True, 
                'message': 'Profile picture uploaded',
                'file_path': file_path
            })
        else:
            # Clean up file if database update failed
            os.remove(file_path)
            return jsonify({'error': 'Failed to update customer record'}), 500
            
    except Exception as e:
        logger.error(f"Error uploading profile picture: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== MESSAGE TEMPLATES ENDPOINTS ====================

@api_bp.route('/message-templates', methods=['GET'])
def get_message_templates():
    """Get all message templates"""
    try:
        templates = db.get_all_message_templates()
        return jsonify(templates)
    except Exception as e:
        logger.error(f"Error getting message templates: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/message-templates/<template_type>', methods=['GET'])
def get_message_template(template_type):
    """Get a specific message template"""
    try:
        template = db.get_message_template(template_type)
        if template:
            return jsonify(template)
        else:
            return jsonify({'error': 'Template not found'}), 404
    except Exception as e:
        logger.error(f"Error getting message template {template_type}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/message-templates/<template_type>', methods=['PUT'])
def update_message_template(template_type):
    """Update a message template"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields - only require message_content if we're updating message content
        if 'message_content' in data:
            required_fields = ['message_content']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Update template
        success = db.update_message_template(template_type, **data)
        
        if success:
            return jsonify({'success': True, 'message': 'Template updated successfully'})
        else:
            return jsonify({'error': 'Failed to update template'}), 500
            
    except Exception as e:
        logger.error(f"Error updating message template {template_type}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/message-templates/initialize', methods=['POST'])
def initialize_message_templates():
    """Initialize default message templates"""
    try:
        success = db.initialize_default_templates()
        if success:
            return jsonify({'success': True, 'message': 'Default templates initialized successfully'})
        else:
            return jsonify({'error': 'Failed to initialize templates'}), 500
    except Exception as e:
        logger.error(f"Error initializing message templates: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/test-send-sms', methods=['POST'])
def test_send_sms():
    """Send a test SMS message"""
    try:
        data = request.get_json()
        
        if not data or 'to_number' not in data or 'message' not in data:
            return jsonify({'error': 'Missing required fields: to_number, message'}), 400
        
        to_number = data['to_number']
        message = data['message']
        
        # Import SMS service
        from sms_service import SMSService
        sms_service = SMSService()
        
        # Send the test message
        success = sms_service.send_sms(
            from_number="+18773900002",  # Business number
            to_number=to_number,
            message=message
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Test message sent successfully'})
        else:
            return jsonify({'error': 'Failed to send test message'}), 500
            
    except Exception as e:
        logger.error(f"Error sending test SMS: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/message-templates/restore-defaults', methods=['POST'])
def restore_default_templates():
    """Restore message templates to their original default values"""
    try:
        success = db.restore_default_templates()
        if success:
            return jsonify({'success': True, 'message': 'Default templates restored successfully'})
        else:
            return jsonify({'error': 'Failed to restore default templates'}), 500
    except Exception as e:
        logger.error(f"Error restoring default templates: {str(e)}")
        return jsonify({'error': str(e)}), 500